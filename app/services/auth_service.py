"""
Authentication Service
Location: app/services/auth_service.py

Gère JWT, hashing, OTP, rate limiting
"""

import hashlib
import hmac
import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple
from uuid import UUID

import bcrypt
import jwt
import redis
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Merchant, MerchantAuth
from app.schemas import TokenPayload

logger = logging.getLogger(__name__)


class OTPError(Exception):
    """Exception pour les erreurs OTP"""
    pass


class RateLimitError(Exception):
    """Exception pour le rate limiting"""
    pass


class AuthService:
    """Service d'authentification avec JWT, bcrypt et OTP"""

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or self._get_redis_client()
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.bcrypt_rounds = settings.BCRYPT_LOG_ROUNDS

    # Ligne ~25 dans __init__

    @staticmethod
    def _get_redis_client() -> redis.Redis:
        """Crée ou récupère le client Redis"""
        try:
            client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            # Test connection
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using mock cache")
            return None  # ← C'est OK, ça va utiliser la fallback

    '''@staticmethod
    def _get_redis_client() -> redis.Redis:
        """Crée ou récupère le client Redis"""
        try:
            return redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, using in-memory cache")
            return None'''

    # ========== PASSWORD HASHING ==========

    def hash_password(self, password: str) -> Tuple[str, str]:
        """
        Hashe un mot de passe avec bcrypt
        Returns: (password_hash, salt)
        """
        # Valide le mot de passe
        self._validate_password(password)
        
        # Génère le salt
        salt = bcrypt.gensalt(rounds=self.bcrypt_rounds)
        
        # Hashe le mot de passe
        password_hash = bcrypt.hashpw(password.encode('utf-8'), salt)
        
        return password_hash.decode('utf-8'), salt.decode('utf-8')

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Vérifie un mot de passe contre son hash"""
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                password_hash.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

    @staticmethod
    def _validate_password(password: str) -> None:
        """Valide la complexité du mot de passe"""
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            raise ValueError(f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters")
        
        if settings.PASSWORD_REQUIRE_UPPERCASE and not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        
        if settings.PASSWORD_REQUIRE_NUMBERS and not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one number")
        
        if settings.PASSWORD_REQUIRE_SPECIAL and not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
            raise ValueError("Password must contain at least one special character")

    # ========== JWT TOKEN ==========

    def create_access_token(self, merchant_id: UUID, phone: str) -> str:
        """Crée un JWT access token (24h)"""
        now = datetime.utcnow()
        expires = now + settings.JWT_ACCESS_TOKEN_EXPIRE
        
        payload = {
            "sub": str(merchant_id),
            "merchant_id": str(merchant_id),
            "phone": phone,
            "iat": now,
            "exp": expires,
            "type": "access",
            "iss": settings.JWT_ISSUER,
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Created access token for merchant {merchant_id}")
        
        return token

    def create_refresh_token(self, merchant_id: UUID, phone: str) -> str:
        """Crée un JWT refresh token (30j)"""
        now = datetime.utcnow()
        expires = now + settings.JWT_REFRESH_TOKEN_EXPIRE
        
        payload = {
            "sub": str(merchant_id),
            "merchant_id": str(merchant_id),
            "phone": phone,
            "iat": now,
            "exp": expires,
            "type": "refresh",
            "iss": settings.JWT_ISSUER,
        }
        
        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        logger.info(f"Created refresh token for merchant {merchant_id}")
        
        return token

    def verify_token(self, token: str, token_type: str = "access") -> Optional[TokenPayload]:
        """Vérifie et décode un JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                issuer=settings.JWT_ISSUER
            )
            
            # Vérifie le type de token
            if payload.get("type") != token_type:
                logger.warning(f"Token type mismatch: expected {token_type}, got {payload.get('type')}")
                return None
            
            return TokenPayload(**payload)
        
        except jwt.ExpiredSignatureError:
            logger.warning(f"Token expired: {token[:20]}...")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None

    # ========== OTP (One-Time Password) ==========

    def generate_otp(self) -> str:
        """Génère un OTP de 6 chiffres"""
        return ''.join(random.choices(string.digits, k=settings.OTP_LENGTH))

    def send_otp(self, phone: str) -> bool:
        """
        Envoie un OTP au téléphone
        Returns: True si succès, False sinon
        """
        # Check rate limiting
        if not self.check_rate_limit(f"otp_request:{phone}", settings.RATE_LIMIT_OTP_REQUESTS, settings.RATE_LIMIT_OTP_WINDOW_MINUTES):
            raise RateLimitError(f"Too many OTP requests. Try again in {settings.RATE_LIMIT_OTP_WINDOW_MINUTES} minutes")
        
        otp = self.generate_otp()
        
        # Stocke l'OTP dans Redis avec expiration
        cache_key = f"otp:{phone}"
        if self.redis:
            self.redis.setex(
                cache_key,
                settings.OTP_EXPIRE_MINUTES * 60,
                otp
            )
        
        logger.info(f"Generated OTP for {phone}: {otp}")  # À supprimer en production
        
        # Envoie l'OTP via SMS (à implémenter)
        if settings.OTP_PROVIDER == "twilio":
            success = self._send_otp_twilio(phone, otp)
        elif settings.OTP_PROVIDER == "custom":
            success = self._send_otp_custom(phone, otp)
        else:  # mock
            success = True
            logger.warning(f"Mock OTP mode: {otp}")
        
        if success:
            # Enregistre les tentatives
            self._increment_rate_limit(f"otp_request:{phone}", settings.RATE_LIMIT_OTP_WINDOW_MINUTES * 60)
        
        return success

    def verify_otp(self, phone: str, otp: str) -> bool:
        """Vérifie un OTP"""
        cache_key = f"otp:{phone}"
        
        if not self.redis:
            logger.error("Redis not available for OTP verification")
            return False
        
        # Récupère l'OTP stocké
        stored_otp = self.redis.get(cache_key)
        
        if not stored_otp:
            logger.warning(f"OTP expired or not found for {phone}")
            return False
        
        # Vérifie l'OTP (case-sensitive, timing-safe comparison)
        if hmac.compare_digest(stored_otp, otp):
            # Supprime l'OTP utilisé
            self.redis.delete(cache_key)
            # Supprime le compteur d'erreurs
            self.redis.delete(f"otp_attempts:{phone}")
            logger.info(f"OTP verified successfully for {phone}")
            return True
        else:
            # Enregistre la tentative échouée
            attempts = self.redis.incr(f"otp_attempts:{phone}")
            self.redis.expire(f"otp_attempts:{phone}", settings.OTP_EXPIRE_MINUTES * 60)
            
            if attempts >= settings.OTP_MAX_ATTEMPTS:
                self.redis.delete(cache_key)  # Invalide l'OTP
                logger.warning(f"Too many OTP attempts for {phone}")
                raise OTPError("Too many incorrect OTP attempts. Request a new OTP.")
            
            logger.warning(f"Invalid OTP for {phone} (attempt {attempts}/{settings.OTP_MAX_ATTEMPTS})")
            return False

    def _send_otp_twilio(self, phone: str, otp: str) -> bool:
        """Envoie un OTP via Twilio"""
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=f"Your NovaSell verification code is: {otp}",
                from_=settings.TWILIO_WHATSAPP_FROM,
                to=phone
            )
            logger.info(f"OTP sent via Twilio: {message.sid}")
            return True
        except Exception as e:
            logger.error(f"Twilio OTP send error: {e}")
            return False

    def _send_otp_custom(self, phone: str, otp: str) -> bool:
        """Envoie un OTP via provider custom (à implémenter)"""
        logger.warning("Custom OTP provider not implemented")
        return False

    # ========== RATE LIMITING ==========

    def check_login_rate_limit(self, phone: str, ip: str) -> bool:
        """Vérifie le rate limit pour login (IP + phone)"""
        key = f"login_attempts:{ip}:{phone}"
        return self.check_rate_limit(
            key,
            settings.RATE_LIMIT_LOGIN_ATTEMPTS,
            settings.RATE_LIMIT_LOGIN_WINDOW_MINUTES
        )

    def increment_login_attempts(self, phone: str, ip: str) -> None:
        """Enregistre une tentative de login échouée"""
        key = f"login_attempts:{ip}:{phone}"
        self._increment_rate_limit(
            key,
            settings.RATE_LIMIT_LOGIN_WINDOW_MINUTES * 60
        )

    def reset_login_attempts(self, phone: str, ip: str) -> None:
        """Réinitialise les tentatives de login"""
        key = f"login_attempts:{ip}:{phone}"
        if self.redis:
            self.redis.delete(key)

    def check_rate_limit(self, key: str, max_attempts: int, window_minutes: int) -> bool:
        """Vérifie si le rate limit est dépassé"""
        if not self.redis:
            logger.debug("Redis not available, skipping rate limit check")
            return True  # ← Permet toutes les requêtes si Redis est down
        
        attempts = self.redis.get(key)
        return int(attempts or 0) < max_attempts

    '''def _check_rate_limit(self, key: str, max_attempts: int, window_minutes: int) -> bool:
        """Vérifie si le rate limit est dépassé"""
        if not self.redis:
            return True  # Skip if Redis unavailable
        
        attempts = self.redis.get(key)
        return int(attempts or 0) < max_attempts'''

    def _increment_rate_limit(self, key: str, expire_seconds: int) -> int:
        """Incrémente le compteur de rate limit"""
        if not self.redis:
            return 1
        
        attempts = self.redis.incr(key)
        self.redis.expire(key, expire_seconds)
        return attempts

    # ========== MERCHANT AUTH ==========

    def register_merchant(
        self,
        session: Session,
        phone: str,
        name: str,
        country: str,
        password: str
    ) -> Merchant:
        """Crée un nouveau vendeur"""
        # Vérifie que le merchant n'existe pas
        existing = Merchant.get_by_phone(session, phone)
        if existing:
            raise ValueError(f"Merchant with phone {phone} already exists")
        
        # Hash le password
        password_hash, salt = self.hash_password(password)
        
        # Crée le merchant
        merchant = Merchant(
            phone=phone,
            name=name,
            country=country,
            status="ACTIVE"
        )
        session.add(merchant)
        session.flush()  # Génère l'ID
        
        # Crée les credentials
        auth = MerchantAuth(
            merchant_id=merchant.id,
            phone=phone,
            password_hash=password_hash,
            salt=salt
        )
        session.add(auth)
        session.commit()
        
        logger.info(f"Merchant registered: {phone}")
        return merchant

    def login_merchant(
        self,
        session: Session,
        phone: str,
        password: str,
        ip: str
    ) -> Tuple[str, str]:
        """
        Login du merchant
        Returns: (access_token, refresh_token)
        """
        # Check rate limiting
        if not self.check_login_rate_limit(phone, ip):
            logger.warning(f"Login rate limit exceeded: {phone} from {ip}")
            raise RateLimitError("Too many login attempts. Try again later.")
        
        # Récupère les credentials
        merchant_auth = session.query(MerchantAuth).filter(
            MerchantAuth.phone == phone
        ).first()
        
        if not merchant_auth:
            self.increment_login_attempts(phone, ip)
            raise ValueError("Invalid credentials")
        
        # Vérifie le mot de passe
        if not self.verify_password(password, merchant_auth.password_hash):
            self.increment_login_attempts(phone, ip)
            raise ValueError("Invalid credentials")
        
        # Récupère le merchant
        merchant = session.query(Merchant).filter(
            Merchant.id == merchant_auth.merchant_id
        ).first()
        
        if not merchant or merchant.status != "ACTIVE":
            raise ValueError("Merchant account is not active")
        
        # Réinitialise le rate limit
        self.reset_login_attempts(phone, ip)
        
        # Crée les tokens
        access_token = self.create_access_token(merchant.id, phone)
        refresh_token = self.create_refresh_token(merchant.id, phone)
        
        logger.info(f"Merchant logged in: {phone}")
        
        return access_token, refresh_token

    def refresh_access_token(self, refresh_token: str) -> str:
        """Crée un nouveau access token à partir du refresh token"""
        token_payload = self.verify_token(refresh_token, token_type="refresh")
        
        if not token_payload:
            raise ValueError("Invalid refresh token")
        
        # Crée un nouveau access token
        merchant_id = UUID(token_payload.merchant_id)
        access_token = self.create_access_token(merchant_id, token_payload.phone)
        
        logger.info(f"Access token refreshed for merchant {merchant_id}")
        
        return access_token