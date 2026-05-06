"""
Pydantic Schemas for Request/Response Validation
Location: app/schemas.py
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, EmailStr, validator, constr


# ========== MERCHANT SCHEMAS ==========

class MerchantBase(BaseModel):
    """Base merchant fields"""
    name: str = Field(..., min_length=1, max_length=255)
    country: str = Field(..., min_length=2, max_length=2)  # "CM"
    phone: str = Field(..., pattern=r'^\+\d{1,15}$')


class MerchantRegisterRequest(MerchantBase):
    """Inscription vendeur"""
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str = Field(..., min_length=8, max_length=128)

    @validator('password_confirm')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v


class MerchantVerifyOTPRequest(BaseModel):
    """Vérifier OTP après inscription"""
    phone: str = Field(..., pattern=r'^\+\d{1,15}$')
    otp: str = Field(..., min_length=4, max_length=6)


class MerchantLoginRequest(BaseModel):
    """Login vendeur"""
    phone: str = Field(..., pattern=r'^\+\d{1,15}$')
    password: str = Field(..., min_length=8, max_length=128)


class MerchantLoginResponse(BaseModel):
    """Response après login"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # 24h en secondes


class MerchantRefreshTokenRequest(BaseModel):
    """Refresh access token"""
    refresh_token: str


class MerchantResponse(MerchantBase):
    """Response merchant data"""
    id: UUID
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MerchantDetailResponse(MerchantResponse):
    """Détails complets du merchant"""
    total_revenue: int = 0  # XOF centimes
    total_orders: int = 0
    active_customers: int = 0


# ========== PRODUCT SCHEMAS ==========

class ProductBase(BaseModel):
    """Base product fields"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    price_amount: int = Field(..., ge=0)  # in centimes, min 0
    published: bool = True
    stock: int = Field(default=0, ge=0)
    image_url: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    sku: Optional[str] = Field(None, max_length=100)


class ProductCreateRequest(ProductBase):
    """Créer un produit"""
    pass


class ProductUpdateRequest(BaseModel):
    """Modifier un produit"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    price_amount: Optional[int] = Field(None, ge=0)
    published: Optional[bool] = None
    stock: Optional[int] = Field(None, ge=0)
    image_url: Optional[str] = Field(None, max_length=500)
    category: Optional[str] = Field(None, max_length=100)
    sku: Optional[str] = Field(None, max_length=100)


class ProductResponse(ProductBase):
    """Response product data"""
    id: UUID
    merchant_id: UUID
    created_at: datetime
    updated_at: datetime

    @property
    def price_xof(self) -> float:
        """Convert to XOF"""
        return self.price_amount / 100

    class Config:
        from_attributes = True


class ProductListResponse(BaseModel):
    """Liste de produits avec pagination"""
    total: int
    skip: int
    limit: int
    items: List[ProductResponse]


# ========== CUSTOMER SCHEMAS ==========

class CustomerBase(BaseModel):
    """Base customer fields"""
    phone: str = Field(..., pattern=r'^\+\d{1,15}$')
    name: Optional[str] = Field(None, max_length=255)


class CustomerCreateRequest(CustomerBase):
    """Créer un client"""
    pass


class CustomerUpdateRequest(BaseModel):
    """Modifier un client"""
    name: Optional[str] = Field(None, max_length=255)
    pphone: str = Field(..., pattern=r'^\+\d{1,15}$')



class CustomerResponse(CustomerBase):
    """Response customer data"""
    id: UUID
    merchant_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
    total_orders: int = 0
    total_spent: int = 0  # in centimes

    class Config:
        from_attributes = True


class CustomerListResponse(BaseModel):
    """Liste de clients avec pagination"""
    total: int
    skip: int
    limit: int
    items: List[CustomerResponse]


# ========== ORDER SCHEMAS ==========

class OrderItemBase(BaseModel):
    """Base order item"""
    product_id: UUID
    qty: int = Field(..., ge=1)


class OrderCreateRequest(BaseModel):
    """Créer une commande"""
    customer_phone: str = Field(..., pattern=r'^\+\d{1,15}$')
    customer_name: Optional[str] = Field(None, max_length=255)
    origin_city: Optional[str] = Field(None, max_length=100)
    destination_city: Optional[str] = Field(None, max_length=100)
    items: List[OrderItemBase] = Field(..., min_items=1)
    manual: bool = True  # created manually by merchant


class OrderStatusUpdateRequest(BaseModel):
    """Mettre à jour le statut d'une commande"""
    status: str = Field(...)
    metadata: Optional[dict] = None


class OrderConfirmRequest(BaseModel):
    """Client confirme la réception"""
    confirmation_token: Optional[str] = None


class OrderItemResponse(BaseModel):
    """Response order item"""
    id: UUID
    product_id: Optional[UUID]
    name_snapshot: str
    qty: int
    unit_price_amount: int
    created_at: datetime

    @property
    def subtotal_xof(self) -> float:
        """Sous-total en XOF"""
        return (self.unit_price_amount * self.qty) / 100

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    """Response order data"""
    id: UUID
    merchant_id: UUID
    customer_id: Optional[UUID]
    customer_phone_snapshot: str
    status: str
    subtotal_amount: int
    total_amount: int
    escrow_amount: int
    currency: str
    items: List[OrderItemResponse] = []
    created_at: datetime
    updated_at: datetime

    @property
    def total_xof(self) -> float:
        return self.total_amount / 100

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Liste de commandes avec pagination"""
    total: int
    skip: int
    limit: int
    items: List[OrderResponse]


# ========== PAYMENT SCHEMAS ==========

class PaymentResponse(BaseModel):
    """Response payment data"""
    id: UUID
    order_id: UUID
    merchant_id: UUID
    provider: str
    provider_reference: str
    status: str
    amount: int
    currency: str
    created_at: datetime
    updated_at: datetime

    @property
    def amount_xof(self) -> float:
        return self.amount / 100

    class Config:
        from_attributes = True


# ========== LEDGER SCHEMAS ==========

class LedgerEntryResponse(BaseModel):
    """Response ledger entry"""
    id: UUID
    merchant_id: UUID
    order_id: Optional[UUID]
    type: str
    amount: int
    status: str
    created_at: datetime

    @property
    def amount_xof(self) -> float:
        return self.amount / 100

    class Config:
        from_attributes = True


class LedgerListResponse(BaseModel):
    """Liste du ledger avec pagination"""
    total: int
    skip: int
    limit: int
    items: List[LedgerEntryResponse]


# ========== BALANCE SCHEMAS ==========

class BalanceResponse(BaseModel):
    """Solde du vendeur"""
    merchant_id: UUID
    available_amount: int  # in centimes
    escrow_amount: int     # in centimes
    pending_amount: int    # in centimes
    total_amount: int      # in centimes

    @property
    def available_xof(self) -> float:
        return self.available_amount / 100

    @property
    def escrow_xof(self) -> float:
        return self.escrow_amount / 100

    @property
    def pending_xof(self) -> float:
        return self.pending_amount / 100

    @property
    def total_xof(self) -> float:
        return self.total_amount / 100

    class Config:
        from_attributes = True


# ========== PAYOUT SCHEMAS ==========

class PayoutAccountBase(BaseModel):
    """Base payout account"""
    operator: str  # ORANGE_MONEY, MTN_MONEY
    phone: str = Field(..., pattern=r'^\+\d{1,15}$')



class PayoutAccountCreateRequest(PayoutAccountBase):
    """Créer un compte de retrait"""
    pass


class PayoutAccountResponse(PayoutAccountBase):
    """Response payout account"""
    id: UUID
    merchant_id: UUID
    country: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PayoutCreateRequest(BaseModel):
    """Demander un retrait"""
    amount: int = Field(..., ge=100)  # min 1 XOF (100 centimes)
    payout_account_id: UUID


class PayoutResponse(BaseModel):
    """Response payout"""
    id: UUID
    merchant_id: UUID
    payout_account_id: UUID
    amount: int
    status: str
    provider_reference: Optional[str]
    created_at: datetime
    updated_at: datetime

    @property
    def amount_xof(self) -> float:
        return self.amount / 100

    class Config:
        from_attributes = True


class PayoutListResponse(BaseModel):
    """Liste des payouts avec pagination"""
    total: int
    skip: int
    limit: int
    items: List[PayoutResponse]


# ========== ERROR SCHEMAS ==========

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    message: str
    status_code: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: Optional[str] = None
    details: Optional[dict] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response"""
    error: str = "VALIDATION_ERROR"
    message: str
    status_code: int = 422
    fields: dict  # field -> error message


# ========== TOKEN SCHEMAS ==========

class TokenPayload(BaseModel):
    """JWT token payload"""
    sub: str  # merchant_id
    merchant_id: UUID
    phone: str
    iat: datetime
    exp: datetime
    type: str = "access"  # access or refresh


class AuthTokens(BaseModel):
    """Paire de tokens"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 86400  # secondes


# ========== NOTIFICATION SCHEMAS ==========

class NotificationResponse(BaseModel):
    """Response notification log"""
    id: UUID
    merchant_id: UUID
    customer_phone: str
    channel: str
    template: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ========== HEALTH CHECK ==========

class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0.0"
    database: str = "connected"