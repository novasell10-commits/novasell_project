"""
Authentication Routes
Location: app/routers/auth.py
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import (
    MerchantRegisterRequest,
    MerchantVerifyOTPRequest,
    MerchantLoginRequest,
    MerchantLoginResponse,
    MerchantRefreshTokenRequest,
    MerchantResponse,
    ErrorResponse
)
from app.services.auth_service import AuthService, OTPError, RateLimitError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/merchants", tags=["auth"])

# Instance du service d'auth
auth_service = AuthService()


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_merchant(
    request: Request,
    payload: MerchantRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Crée un nouveau compte vendeur
    
    1. Valide les données
    2. Envoie un OTP au téléphone
    3. Retourne un status d'attente de vérification OTP
    
    Required: name, phone, country, password
    """
    try:
        # Normalise le phone
        phone = payload.phone.strip()
        
        # Vérifie que le merchant n'existe pas déjà
        from app.models import Merchant
        existing = Merchant.get_by_phone(db, phone)
        if existing:
            logger.warning(f"Registration attempt with existing phone: {phone}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number already registered"
            )
        
        # Envoie l'OTP
        if not settings.ENABLE_OTP:
            logger.warning("OTP disabled, skipping OTP sending")
            otp_sent = True
        else:
            try:
                otp_sent = auth_service.send_otp(phone)
            except RateLimitError as e:
                logger.warning(f"OTP rate limit: {e}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=str(e)
                )
        
        if not otp_sent and settings.OTP_PROVIDER != "mock":
            logger.error(f"Failed to send OTP to {phone}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send OTP. Please try again."
            )
        
        return {
            "status": "otp_sent",
            "message": "OTP sent to your phone. Please verify.",
            "phone": phone,
            "otp_expire_minutes": settings.OTP_EXPIRE_MINUTES
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/verify-otp", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def verify_otp(
    request: Request,
    payload: MerchantVerifyOTPRequest,
    db: Session = Depends(get_db)
):
    """
    Vérifie l'OTP et crée le compte vendeur
    
    1. Vérifie l'OTP
    2. Crée le merchant en base de données
    3. Retourne les infos du merchant
    """
    try:
        phone = payload.phone.strip()
        otp = payload.otp.strip()
        
        # Vérifie l'OTP
        try:
            if not auth_service.verify_otp(phone, otp):
                logger.warning(f"Invalid OTP for {phone}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid OTP"
                )
        except OTPError as e:
            logger.warning(f"OTP error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        # À ce stade, le OTP est vérifié mais on doit récupérer les données du merchant
        # Depuis le cache Redis (set lors du register)
        from app.models import Merchant
        
        # Recherche le merchant par phone (qui était en attente de vérification)
        merchant = Merchant.get_by_phone(db, phone)
        if not merchant:
            # Le merchant n'existe pas encore, on ne peut pas continuer
            logger.error(f"Merchant not found after OTP verification: {phone}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid request. Please register first."
            )
        
        logger.info(f"OTP verified successfully for {phone}")
        
        return MerchantResponse.model_validate(merchant)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTP verification error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OTP verification failed"
        )


@router.post("/register-complete", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def register_complete(
    request: Request,
    payload: MerchantRegisterRequest,
    db: Session = Depends(get_db)
):
    """
    Flux complet: register + OTP en une seule requête (pour MVP)
    
    1. Envoie OTP
    2. Crée le merchant
    3. Retourne les infos
    """
    try:
        phone = payload.phone.strip()
        
        # Envoie l'OTP
        try:
            if settings.ENABLE_OTP:
                auth_service.send_otp(phone)
        except RateLimitError as e:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(e)
            )
        
        # Crée le merchant directement (sans attendre OTP en MVP)
        merchant = auth_service.register_merchant(
            db,
            phone=phone,
            name=payload.name,
            country=payload.country,
            password=payload.password
        )
        
        logger.info(f"Merchant registered: {phone}")
        
        return MerchantResponse.model_validate(merchant)
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Registration validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


@router.post("/login", response_model=MerchantLoginResponse)
async def login(
    request: Request,
    payload: MerchantLoginRequest,
    db: Session = Depends(get_db)
):
    """
    Login du vendeur
    
    1. Récupère l'IP du client
    2. Vérifie les credentials (phone + password)
    3. Retourne les tokens JWT
    """
    try:
        phone = payload.phone.strip()
        password = payload.password
        client_ip = request.client.host if request.client else "unknown"
        
        # Login
        try:
            access_token, refresh_token = auth_service.login_merchant(
                db,
                phone=phone,
                password=password,
                ip=client_ip
            )
        except RateLimitError as e:
            logger.warning(f"Login rate limit exceeded: {phone} from {client_ip}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(e)
            )
        except ValueError as e:
            logger.warning(f"Invalid credentials: {phone}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        logger.info(f"Merchant logged in: {phone}")
        
        return MerchantLoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=int(settings.JWT_ACCESS_TOKEN_EXPIRE.total_seconds())
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/refresh-token", response_model=dict)
async def refresh_token(
    request: Request,
    payload: MerchantRefreshTokenRequest
):
    """
    Renouvelle l'access token avec le refresh token
    
    Returns: nouveau access_token valide 24h
    """
    try:
        refresh_tok = payload.refresh_token
        
        new_access_token = auth_service.refresh_access_token(refresh_tok)
        
        logger.info(f"Access token refreshed")
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": int(settings.JWT_ACCESS_TOKEN_EXPIRE.total_seconds())
        }
    
    except ValueError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


@router.post("/logout")
async def logout(request: Request):
    """
    Logout du vendeur (stateless, juste une confirmation)
    
    Note: JWT est stateless, donc le logout n'a pas besoin de rien faire côté serveur
    Le client supprime le token localement
    """
    try:
        merchant_id = getattr(request.state, 'merchant_id', None)
        logger.info(f"Merchant logged out: {merchant_id}")
        
        return {
            "status": "logged_out",
            "message": "You have been logged out successfully"
        }
    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


@router.get("/profile", response_model=MerchantResponse)
async def get_profile(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Récupère le profil du merchant connecté
    
    Nécessite: token JWT valide
    """
    try:
        merchant_id = UUID(request.state.merchant_id)
        
        from app.models import Merchant
        merchant = Merchant.get_by_id(db, merchant_id)
        
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant not found"
            )
        
        return MerchantResponse.model_validate(merchant)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get profile"
        )