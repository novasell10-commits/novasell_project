"""
Application Configuration
Location: app/config.py
"""

import os
from datetime import timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuration globale de l'application"""

    # ========== APP SETTINGS ==========
    APP_NAME: str = "NovaSell API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

    # ========== DATABASE ==========
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://novasell_app:password@localhost:5432/novasell_production"
    )
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "20"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour

    # ========== JWT SETTINGS ==========
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_HOURS: int = 24  # 24 heures
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30  # 30 jours
    JWT_ISSUER: str = "novasell-api"

    @property
    def JWT_ACCESS_TOKEN_EXPIRE(self) -> timedelta:
        """Token d'accès valide 24 heures"""
        return timedelta(hours=self.JWT_ACCESS_TOKEN_EXPIRE_HOURS)

    @property
    def JWT_REFRESH_TOKEN_EXPIRE(self) -> timedelta:
        """Token de refresh valide 30 jours"""
        return timedelta(days=self.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    # ========== PASSWORD SETTINGS ==========
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_NUMBERS: bool = True
    PASSWORD_REQUIRE_SPECIAL: bool = False
    BCRYPT_LOG_ROUNDS: int = 12  # Nombre de rounds pour bcrypt

    # ========== OTP SETTINGS ==========
    OTP_LENGTH: int = 6
    OTP_EXPIRE_MINUTES: int = 10  # OTP valide 10 minutes
    OTP_MAX_ATTEMPTS: int = 5  # Max 5 tentatives
    OTP_PROVIDER: str = os.getenv("OTP_PROVIDER", "twilio")  # twilio, custom, mock
    
    # Twilio settings
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_VERIFY_SERVICE_SID: str = os.getenv("TWILIO_VERIFY_SERVICE_SID", "")

    # ========== RATE LIMITING ==========
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 10  # 10 attempts
    RATE_LIMIT_LOGIN_WINDOW_MINUTES: int = 5  # per 5 minutes
    RATE_LIMIT_OTP_REQUESTS: int = 3  # 3 OTP requests
    RATE_LIMIT_OTP_WINDOW_MINUTES: int = 5  # per 5 minutes
    RATE_LIMIT_API_CALLS: int = 100  # 100 calls
    RATE_LIMIT_API_WINDOW_MINUTES: int = 1  # per minute

    # ========== REDIS (for caching & rate limiting) ==========
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    CACHE_EXPIRE_SECONDS: int = 3600  # 1 hour default

    # ========== CORS SETTINGS ==========
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")
    CORS_CREDENTIALS: bool = True
    CORS_METHODS: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_HEADERS: list = ["*"]

    # ========== WHATSAPP SETTINGS ==========
    WHATSAPP_PROVIDER: str = os.getenv("WHATSAPP_PROVIDER", "META")  # META, BAILEYS, EVOLUTION, TWILIO
    
    # Meta Settings
    META_PHONE_ID: str = os.getenv("META_PHONE_ID", "")
    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    META_BUSINESS_ACCOUNT_ID: str = os.getenv("META_BUSINESS_ACCOUNT_ID", "")
    META_WEBHOOK_VERIFY_TOKEN: str = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "novasell-webhook")
    
    # Baileys Settings (Node.js backend)
    BAILEYS_BASE_URL: str = os.getenv("BAILEYS_BASE_URL", "http://localhost:3000")
    
    # Evolution API Settings
    EVOLUTION_API_URL: str = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    EVOLUTION_API_KEY: str = os.getenv("EVOLUTION_API_KEY", "")
    
    # Twilio WhatsApp
    TWILIO_WHATSAPP_ACCOUNT_SID: str = os.getenv("TWILIO_WHATSAPP_ACCOUNT_SID", "")
    TWILIO_WHATSAPP_AUTH_TOKEN: str = os.getenv("TWILIO_WHATSAPP_AUTH_TOKEN", "")
    TWILIO_WHATSAPP_FROM: str = os.getenv("TWILIO_WHATSAPP_FROM", "")

    # ========== IA SERVICE SETTINGS ==========
    AI_PRIMARY_PROVIDER: str = os.getenv("AI_PRIMARY_PROVIDER", "EXTERNAL")  # EXTERNAL, OPENAI, LOCAL
    AI_EXTERNAL_URL: str = os.getenv("AI_EXTERNAL_URL", "http://localhost:8001")
    AI_EXTERNAL_TIMEOUT: int = int(os.getenv("AI_EXTERNAL_TIMEOUT", "5"))
    
    AI_FALLBACK_PROVIDER: str = os.getenv("AI_FALLBACK_PROVIDER", "OPENAI")
    AI_FALLBACK_TIMEOUT: int = int(os.getenv("AI_FALLBACK_TIMEOUT", "10"))
    
    # OpenAI Settings
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
    OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
    
    # Local LLM Settings
    LOCAL_LLM_URL: str = os.getenv("LOCAL_LLM_URL", "http://localhost:11434")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "llama2")

    # ========== RAG / VECTOR DB ==========
    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "")
    PINECONE_INDEX: str = os.getenv("PINECONE_INDEX", "novasell-kb")
    
    WEAVIATE_URL: str = os.getenv("WEAVIATE_URL", "http://localhost:8080")
    WEAVIATE_CLASS: str = "NovasellKB"

    # ========== PAYMENT SETTINGS ==========
    ORANGE_MONEY_API_KEY: str = os.getenv("ORANGE_MONEY_API_KEY", "")
    ORANGE_MONEY_API_SECRET: str = os.getenv("ORANGE_MONEY_API_SECRET", "")
    ORANGE_MONEY_API_URL: str = os.getenv("ORANGE_MONEY_API_URL", "https://api.orange.com")
    
    MTN_MONEY_API_KEY: str = os.getenv("MTN_MONEY_API_KEY", "")
    MTN_MONEY_API_SECRET: str = os.getenv("MTN_MONEY_API_SECRET", "")
    MTN_MONEY_API_URL: str = os.getenv("MTN_MONEY_API_URL", "https://api.mtn.com")
    
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PUBLISHABLE_KEY: str = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # ========== NOTIFICATION SETTINGS ==========
    # SMS
    SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "twilio")  # twilio, nexmo, custom
    
    # Email
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "sendgrid")  # sendgrid, mailgun, smtp
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    
    MAILGUN_DOMAIN: str = os.getenv("MAILGUN_DOMAIN", "")
    MAILGUN_API_KEY: str = os.getenv("MAILGUN_API_KEY", "")
    
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "noreply@novasell.cm")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "NovaSell")

    # ========== FILE STORAGE ==========
    STORAGE_PROVIDER: str = os.getenv("STORAGE_PROVIDER", "s3")  # s3, cloudinary, local
    
    # AWS S3
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "novasell-assets")
    AWS_S3_REGION: str = os.getenv("AWS_S3_REGION", "us-east-1")
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")
    
    # Local Storage
    LOCAL_STORAGE_PATH: str = os.getenv("LOCAL_STORAGE_PATH", "/tmp/novasell/uploads")

    # ========== LOGGING ==========
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "json"  # json or text
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")

    # ========== MONITORING ==========
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    DATADOG_API_KEY: str = os.getenv("DATADOG_API_KEY", "")
    DATADOG_ENABLED: bool = bool(os.getenv("DATADOG_ENABLED", "false"))

    # ========== API DOCUMENTATION ==========
    OPENAPI_URL: str = "/api/v1/openapi.json"
    DOCS_URL: str = "/api/v1/docs"
    REDOC_URL: str = "/api/v1/redoc"

    # ========== SECURITY ==========
    ALLOWED_HOSTS: list = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    SECURE_COOKIES: bool = ENVIRONMENT == "production"
    HTTPS_REDIRECT: bool = ENVIRONMENT == "production"
    HSTS_MAX_AGE: int = 31536000  # 1 year

    # ========== FEATURE FLAGS ==========
    ENABLE_OTP: bool = os.getenv("ENABLE_OTP", "false").lower() == "true"
    ENABLE_PAYMENT: bool = os.getenv("ENABLE_PAYMENT", "true").lower() == "true"
    ENABLE_PAYOUT: bool = os.getenv("ENABLE_PAYOUT", "true").lower() == "true"
    ENABLE_WHATSAPP: bool = os.getenv("ENABLE_WHATSAPP", "true").lower() == "true"
    ENABLE_AI: bool = os.getenv("ENABLE_AI", "true").lower() == "true"

    def __init__(self):
        """Valide les settings à l'initialisation"""
        self._validate()

    def _validate(self):
        """Validation des settings critiques"""
        if not self.SECRET_KEY or self.SECRET_KEY == "dev-secret-key-change-in-production":
            if self.ENVIRONMENT == "production":
                raise ValueError("SECRET_KEY must be set in production")
        
        if not self.DATABASE_URL:
            raise ValueError("DATABASE_URL must be set")
        
        if self.ENVIRONMENT == "production" and not self.OPENAI_API_KEY and self.AI_PRIMARY_PROVIDER == "EXTERNAL":
            raise ValueError("OPENAI_API_KEY must be set in production if using AI")


# Instance globale des settings
settings = Settings()