"""
FastAPI Main Application
Location: app/main.py

Start: uvicorn app.main:app --reload (dev)
       uvicorn app.main:app --host 0.0.0.0 --port 8000 (production)
"""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.database import get_db, init_db, close_db
from app.middlewares import (
    RequestIDMiddleware,
    ErrorHandlingMiddleware,
    LoggingMiddleware,
    JWTValidationMiddleware,
    RateLimitMiddleware
)
from app.services.auth_service import AuthService
from app.routers import auth, products, customers
from app.schemas import ErrorResponse, ValidationErrorResponse
from app.routers import ledger
from app.routers import orders
from app.routers import payments

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        # Optionnel: logging.FileHandler(settings.LOG_FILE)
    ]
)
logger = logging.getLogger(__name__)


# ========== STARTUP & SHUTDOWN ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application"""
    # STARTUP
    logger.info("=" * 80)
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug: {settings.DEBUG}")
    logger.info("=" * 80)
    
    try:
        # Initialise la base de données
        logger.info("Initializing database...")
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    yield
    
    # SHUTDOWN
    logger.info("Shutting down...")
    close_db()
    logger.info("Application stopped")


# ========== CREATE APP ==========

app = FastAPI(
    title=settings.APP_NAME,
    description="WhatsApp Seller Automation Platform",
    version=settings.APP_VERSION,
    docs_url=settings.DOCS_URL,
    redoc_url=settings.REDOC_URL,
    openapi_url=settings.OPENAPI_URL,
    lifespan=lifespan
)


# ========== MIDDLEWARE ==========

# Ordre important: les middlewares sont exécutés en ordre INVERSE
app.add_middleware(LoggingMiddleware)
app.add_middleware(RateLimitMiddleware, auth_service=AuthService())
app.add_middleware(JWTValidationMiddleware, auth_service=AuthService())
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(RequestIDMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_CREDENTIALS,
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
)


# ========== EXCEPTION HANDLERS ==========

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Gère les erreurs de validation Pydantic"""
    fields = {}
    for error in exc.errors():
        field_name = ".".join(str(x) for x in error["loc"][1:])
        fields[field_name] = error["msg"]
    
    error_response = ValidationErrorResponse(
        error="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=422,
        fields=fields
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response.model_dump()
    )


# ========== HEALTH CHECK ==========

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    from app.schemas import HealthCheckResponse
    return HealthCheckResponse()


# ========== ROUTES ==========

# Auth routes
app.include_router(auth.router)

# Product routes
app.include_router(products.router)

# Customer routes
app.include_router(customers.router)

app.include_router(ledger.router)

app.include_router(orders.router)

app.include_router(payments.router)




# ========== ROOT ENDPOINT ==========

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": settings.DOCS_URL,
        "status": "running"
    }


# ========== ERROR RESPONSES ==========

@app.get("/api/v1/error-example/{error_type}")
async def error_example(error_type: str):
    """Endpoint pour tester les différentes erreurs"""
    if error_type == "validation":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Validation error example"
        )
    elif error_type == "auth":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication error example"
        )
    elif error_type == "notfound":
        from fastapi import HTTPException
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found error example"
        )
    else:
        return {"error": "Unknown error type"}


# ========== LOGGING ==========

if settings.DEBUG:
    logger.info("Debug mode enabled - SQL queries will be logged")
    logger.info(f"Allowed CORS origins: {settings.CORS_ORIGINS}")
    logger.info(f"JWT settings: {settings.JWT_ACCESS_TOKEN_EXPIRE_HOURS}h access token")
    logger.info(f"OTP enabled: {settings.ENABLE_OTP}")
    logger.info(f"WhatsApp provider: {settings.WHATSAPP_PROVIDER}")
    logger.info(f"IA provider: {settings.AI_PRIMARY_PROVIDER} (fallback: {settings.AI_FALLBACK_PROVIDER})")


# ========== RUN COMMAND ==========

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info"
    )