"""
Middlewares pour FastAPI - VERSION PRO PRETE PROD
Location: app/middlewares.py
"""

import logging
import time
import uuid

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)


# =========================================================
# 1. REQUEST ID MIDDLEWARE
# =========================================================
class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.3f}"

        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"- {response.status_code} - {process_time:.3f}s"
        )

        return response


# =========================================================
# 2. ERROR HANDLING MIDDLEWARE
# =========================================================
class ErrorHandlingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        try:
            return await call_next(request)

        except Exception as e:

            logger.error("Unhandled exception", exc_info=True)

            return JSONResponse(
                status_code=500,
                content={
                    "error": "INTERNAL_SERVER_ERROR",
                    "message": "Unexpected error occurred",
                    "status_code": 500,
                    "request_id": getattr(request.state, "request_id", None)
                }
            )


# =========================================================
# 3. CORS MIDDLEWARE (CUSTOM SIMPLE)
# =========================================================
class CORSMiddleware:

    def __init__(self, app):
        self.app = app
        self.origins = settings.CORS_ORIGINS

    async def __call__(self, request: Request, call_next):

        origin = request.headers.get("origin")

        if origin in self.origins or "*" in self.origins:

            response = await call_next(request)

            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = ", ".join(settings.CORS_METHODS)
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

            return response

        return await call_next(request)


# =========================================================
# 4. JWT AUTH MIDDLEWARE
# =========================================================
class JWTValidationMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, auth_service: AuthService):
        super().__init__(app)
        self.auth_service = auth_service

        self.public_routes = {
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/api/v1/health",
            "/api/v1/merchants/register",
            "/api/v1/merchants/register-complete",  # ← AJOUTE CETTE LIGNE
            "/api/v1/merchants/login",
            "/api/v1/merchants/verify-otp",
            "/api/v1/docs",
            "/api/v1/redoc",
            "/api/v1/openapi.json",
        }

    async def dispatch(self, request: Request, call_next):

        path = request.url.path

        # Skip auth pour routes publiques
        if path in self.public_routes or path.startswith("/api/v1/payments/webhook"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "MISSING_TOKEN"}
            )

        try:
            scheme, token = auth_header.split()

            if scheme.lower() != "bearer":
                raise ValueError()

        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "INVALID_AUTH_HEADER"}
            )

        payload = self.auth_service.verify_token(token)

        if not payload:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "INVALID_TOKEN"}
            )

        request.state.merchant_id = payload.merchant_id
        request.state.phone = getattr(payload, "phone", None)

        return await call_next(request)


# =========================================================
# 5. RATE LIMIT MIDDLEWARE
# =========================================================
class RateLimitMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, auth_service: AuthService):
        super().__init__(app)
        self.auth_service = auth_service

    async def dispatch(self, request: Request, call_next):

        client_ip = request.client.host if request.client else "unknown"
        key = f"api_calls:{client_ip}"

        if not self.auth_service.check_rate_limit(
            key,
            settings.RATE_LIMIT_API_CALLS,
            settings.RATE_LIMIT_API_WINDOW_MINUTES
        ):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests"
                }
            )

        self.auth_service._increment_rate_limit(
            key,
            settings.RATE_LIMIT_API_WINDOW_MINUTES * 60
        )

        return await call_next(request)


# =========================================================
# 6. LOGGING MIDDLEWARE
# =========================================================
class LoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        body = await request.body()

        logger.debug(
            "Incoming request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "query": str(request.query_params),
                "body": body.decode(errors="ignore") if body else None
            }
        )

        return await call_next(request)