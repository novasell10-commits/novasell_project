"""
SQLAlchemy ORM Models for NovaSell
Location: app/models.py
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import uuid4

from sqlalchemy import (
    Column, String, Integer, BigInteger, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, Index, JSON, func, event, select
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import and_

Base = declarative_base()


# ========== ENUMS ==========

class MerchantStatusEnum(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class OrderStatusEnum(str, Enum):
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentStatusEnum(str, Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentProviderEnum(str, Enum):
    ORANGE_MONEY = "ORANGE_MONEY"
    MTN_MONEY = "MTN_MONEY"
    CARD = "CARD"


class PayoutStatusEnum(str, Enum):
    REQUESTED = "REQUESTED"
    PROCESSING = "PROCESSING"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class LedgerTypeEnum(str, Enum):
    ESCROW_HOLD = "ESCROW_HOLD"
    ESCROW_RELEASE = "ESCROW_RELEASE"
    MERCHANT_CREDIT = "MERCHANT_CREDIT"
    PAYOUT_REQUEST = "PAYOUT_REQUEST"
    PAYOUT_SETTLED = "PAYOUT_SETTLED"
    REFUND = "REFUND"


class LedgerStatusEnum(str, Enum):
    PENDING = "PENDING"
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class PayoutOperatorEnum(str, Enum):
    ORANGE_MONEY = "ORANGE_MONEY"
    MTN_MONEY = "MTN_MONEY"


# ========== MERCHANT ==========

class Merchant(Base):
    """
    Vendeur WhatsApp - Entité principale
    """
    __tablename__ = "merchant"
    __table_args__ = (
        Index('idx_merchant_phone', 'phone'),
        Index('idx_merchant_status', 'status'),
        Index('idx_merchant_created_at', 'created_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone = Column(String(20), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    country = Column(String(2), nullable=False, index=True)  # "CM", "SN", etc.
    status = Column(
        ENUM(MerchantStatusEnum, name='merchant_status_enum'),
        nullable=False,
        server_default='ACTIVE'
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    products = relationship('Product', back_populates='merchant', cascade='all, delete-orphan')
    orders = relationship('Order', back_populates='merchant', cascade='all, delete-orphan')
    payments = relationship('Payment', back_populates='merchant', cascade='all, delete-orphan')
    ledger_entries = relationship('LedgerEntry', back_populates='merchant', cascade='all, delete-orphan')
    payout_accounts = relationship('PayoutAccount', back_populates='merchant', cascade='all, delete-orphan')
    payouts = relationship('Payout', back_populates='merchant', cascade='all, delete-orphan')
    notifications = relationship('NotificationLog', back_populates='merchant', cascade='all, delete-orphan')
    auth = relationship('MerchantAuth', back_populates='merchant', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Merchant(id={self.id}, phone={self.phone}, name={self.name})>"

    @classmethod
    def get_by_phone(cls, session: Session, phone: str) -> Optional['Merchant']:
        """Récupère un vendeur par téléphone"""
        return session.query(cls).filter(cls.phone == phone).first()

    @classmethod
    def get_by_id(cls, session: Session, merchant_id) -> Optional['Merchant']:
        """Récupère un vendeur par ID"""
        return session.query(cls).filter(cls.id == merchant_id).first()


# ========== MERCHANT_AUTH ==========

class MerchantAuth(Base):
    """
    Credentials du vendeur - Séparé pour sécurité
    """
    __tablename__ = "merchant_auth"
    __table_args__ = (
        Index('idx_merchant_auth_phone', 'phone'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), unique=True, nullable=False)
    phone = Column(String(20), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='auth')

    def __repr__(self):
        return f"<MerchantAuth(merchant_id={self.merchant_id})>"


# ========== PRODUCT ==========

class Product(Base):
    """
    Produit du catalogue
    """
    __tablename__ = "product"
    __table_args__ = (
        Index('idx_product_merchant_id', 'merchant_id'),
        Index('idx_product_published', 'published'),
        Index('idx_product_category', 'category'),
        Index('idx_product_sku', 'sku'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price_amount = Column(BigInteger(), nullable=False)  # in centimes
    currency = Column(String(3), nullable=False, server_default='XOF')
    published = Column(Boolean(), nullable=False, server_default="true")
    stock = Column(Integer(), nullable=False, server_default="0")
    image_url = Column(String(500), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    sku = Column(String(100), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='products')
    order_items = relationship('OrderItem', back_populates='product')

    def __repr__(self):
        return f"<Product(id={self.id}, name={self.name}, price={self.price_amount})>"

    @property
    def price_xof(self) -> float:
        """Convertit centimes en XOF"""
        return self.price_amount / 100

    def is_available(self, qty: int) -> bool:
        """Vérifie la disponibilité"""
        return self.published and self.stock >= qty


# ========== CUSTOMER ==========

class Customer(Base):
    """
    Client (peut appartenir à un vendeur ou être générique)
    """
    __tablename__ = "customer"
    __table_args__ = (
        Index('idx_customer_phone', 'phone'),
        Index('idx_customer_merchant_id', 'merchant_id'),
        UniqueConstraint('phone', 'merchant_id', name='uq_customer_phone_merchant'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    phone = Column(String(20), nullable=False, index=True)
    name = Column(String(255), nullable=True)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant')
    orders = relationship('Order', back_populates='customer')
    payments = relationship('Payment', back_populates='customer')

    def __repr__(self):
        return f"<Customer(id={self.id}, phone={self.phone})>"

    @classmethod
    def get_or_create(cls, session: Session, phone: str, merchant_id=None, name: str = None) -> 'Customer':
        """Récupère ou crée un client"""
        customer = session.query(cls).filter(
            and_(cls.phone == phone, cls.merchant_id == merchant_id)
        ).first()
        
        if not customer:
            customer = cls(phone=phone, merchant_id=merchant_id, name=name)
            session.add(customer)
            session.flush()
        
        return customer


# ========== ORDER ==========

class Order(Base):
    """
    Commande du client
    """
    __tablename__ = "order"
    __table_args__ = (
        Index('idx_order_merchant_id', 'merchant_id'),
        Index('idx_order_customer_id', 'customer_id'),
        Index('idx_order_status', 'status'),
        Index('idx_order_created_at', 'created_at'),
        Index('idx_order_merchant_created', 'merchant_id', 'created_at', postgresql_include=['status']),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customer.id', ondelete='SET NULL'), nullable=True)
    customer_phone_snapshot = Column(String(20), nullable=False)  # Audit
    origin_city = Column(String(100), nullable=True)
    destination_city = Column(String(100), nullable=True)
    manual = Column(Boolean(), nullable=False, server_default="false")  # true = créée manuellement
    status = Column(
        ENUM(OrderStatusEnum, name='order_status_enum'),
        nullable=False,
        server_default='PAID'
    )
    subtotal_amount = Column(BigInteger(), nullable=False)  # in centimes
    total_amount = Column(BigInteger(), nullable=False)  # in centimes
    escrow_amount = Column(BigInteger(), nullable=False)  # in centimes
    currency = Column(String(3), nullable=False, server_default='XOF')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='orders')
    customer = relationship('Customer', back_populates='orders')
    items = relationship('OrderItem', back_populates='order', cascade='all, delete-orphan')
    payment = relationship('Payment', uselist=False, back_populates='order')
    ledger_entries = relationship('LedgerEntry', back_populates='order')
    status_history = relationship('OrderStatusHistory', back_populates='order', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Order(id={self.id}, status={self.status}, total={self.total_amount})>"

    @property
    def total_xof(self) -> float:
        """Convertit centimes en XOF"""
        return self.total_amount / 100

    def confirm(self, session: Session, actor: str = 'CUSTOMER'):
        """Confirme la commande et libère l'escrow"""
        if self.status != OrderStatusEnum.AWAITING_CONFIRMATION:
            raise ValueError(f"Cannot confirm order in status {self.status}")
        
        self.status = OrderStatusEnum.CONFIRMED
        self.updated_at = datetime.utcnow()
        
        # Enregistrer historique
        history = OrderStatusHistory(
            order_id=self.id,
            from_status=OrderStatusEnum.AWAITING_CONFIRMATION,
            to_status=OrderStatusEnum.CONFIRMED,
            actor=actor
        )
        session.add(history)

    def cancel(self, session: Session, reason: str = None):
        """Annule la commande"""
        if self.status == OrderStatusEnum.CANCELLED:
            raise ValueError("Order is already cancelled")
        
        old_status = self.status
        self.status = OrderStatusEnum.CANCELLED
        self.updated_at = datetime.utcnow()
        
        history = OrderStatusHistory(
            order_id=self.id,
            from_status=old_status,
            to_status=OrderStatusEnum.CANCELLED,
            actor='SYSTEM',
            metadata={'reason': reason} if reason else None
        )
        session.add(history)


# ========== ORDER_ITEM ==========

class OrderItem(Base):
    """
    Ligne d'une commande
    """
    __tablename__ = "order_item"
    __table_args__ = (
        Index('idx_order_item_order_id', 'order_id'),
        Index('idx_order_item_product_id', 'product_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey('product.id', ondelete='SET NULL'), nullable=True)
    name_snapshot = Column(String(255), nullable=False)  # Snapshot du nom au moment de la commande
    qty = Column(Integer(), nullable=False)
    unit_price_amount = Column(BigInteger(), nullable=False)  # in centimes
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    order = relationship('Order', back_populates='items')
    product = relationship('Product', back_populates='order_items')

    def __repr__(self):
        return f"<OrderItem(id={self.id}, name={self.name_snapshot}, qty={self.qty})>"

    @property
    def subtotal_amount(self) -> int:
        """Calcule le sous-total de cette ligne"""
        return self.unit_price_amount * self.qty


# ========== ORDER_STATUS_HISTORY ==========

class OrderStatusHistory(Base):
    """
    Historique des changements de statut
    """
    __tablename__ = "order_status_history"
    __table_args__ = (
        Index('idx_order_status_history_order_id', 'order_id'),
        Index('idx_order_status_history_created_at', 'created_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    from_status = Column(ENUM(OrderStatusEnum, name='order_status_enum'), nullable=True)
    to_status = Column(ENUM(OrderStatusEnum, name='order_status_enum'), nullable=False)
    actor = Column(String(50), nullable=True)  # 'CUSTOMER', 'MERCHANT', 'SYSTEM'
    meta_data = Column(JSON(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    order = relationship('Order', back_populates='status_history')

    def __repr__(self):
        return f"<OrderStatusHistory(order_id={self.order_id}, {self.from_status}→{self.to_status})>"


# ========== PAYMENT ==========

class Payment(Base):
    """
    Paiement associé à une commande
    """
    __tablename__ = "payment"
    __table_args__ = (
        Index('idx_payment_merchant_id', 'merchant_id'),
        Index('idx_payment_order_id', 'order_id'),
        Index('idx_payment_provider_reference', 'provider_reference'),
        Index('idx_payment_status', 'status'),
        Index('idx_payment_created_at', 'created_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey('order.id', ondelete='CASCADE'), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customer.id', ondelete='SET NULL'), nullable=True)
    provider = Column(
        ENUM(PaymentProviderEnum, name='payment_provider_enum'),
        nullable=False
    )
    provider_reference = Column(String(255), nullable=False, unique=True)
    status = Column(
        ENUM(PaymentStatusEnum, name='payment_status_enum'),
        nullable=False,
        server_default='PENDING'
    )
    amount = Column(BigInteger(), nullable=False)  # in centimes
    currency = Column(String(3), nullable=False, server_default='XOF')
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='payments')
    order = relationship('Order', back_populates='payment')
    customer = relationship('Customer', back_populates='payments')

    def __repr__(self):
        return f"<Payment(id={self.id}, provider={self.provider}, status={self.status})>"

    @property
    def amount_xof(self) -> float:
        """Convertit centimes en XOF"""
        return self.amount / 100


# ========== LEDGER_ENTRY (Partitionné par date) ==========

class LedgerEntry(Base):
    """
    Entrée de ledger - Partitionné par DATE pour performance
    Source de vérité pour la finance
    """
    __tablename__ = "ledger_entry"
    __table_args__ = (
        Index('idx_ledger_merchant_id', 'merchant_id'),
        Index('idx_ledger_type', 'type'),
        Index('idx_ledger_status', 'status'),
        Index('idx_ledger_idempotency', 'idempotency_key'),
        Index('idx_ledger_created_at', 'created_at'),
        Index('idx_ledger_merchant_type', 'merchant_id', 'type', 'status'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey('order.id', ondelete='SET NULL'), nullable=True)
    type = Column(
        ENUM(LedgerTypeEnum, name='ledger_type_enum'),
        nullable=False
    )
    amount = Column(BigInteger(), nullable=False)  # signed, in centimes
    status = Column(
        ENUM(LedgerStatusEnum, name='ledger_status_enum'),
        nullable=False,
        server_default='PENDING'
    )
    idempotency_key = Column(String(255), nullable=False, unique=True)
    meta_data = Column(JSON(), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='ledger_entries')
    order = relationship('Order', back_populates='ledger_entries')

    def __repr__(self):
        return f"<LedgerEntry(id={self.id}, type={self.type}, amount={self.amount})>"

    @property
    def amount_xof(self) -> float:
        """Convertit centimes en XOF"""
        return self.amount / 100

    def post(self, session: Session):
        """Valide l'entrée"""
        if self.status != LedgerStatusEnum.PENDING:
            raise ValueError(f"Cannot post entry in status {self.status}")
        self.status = LedgerStatusEnum.POSTED

    def reverse(self, session: Session):
        """Annule l'entrée"""
        if self.status != LedgerStatusEnum.POSTED:
            raise ValueError(f"Cannot reverse entry not in POSTED status")
        self.status = LedgerStatusEnum.REVERSED


# ========== PAYOUT_ACCOUNT ==========

class PayoutAccount(Base):
    """
    Compte de retrait du vendeur (Orange Money, MTN Money)
    MAX 2 comptes actifs par vendeur
    """
    __tablename__ = "payout_account"
    __table_args__ = (
        Index('idx_payout_account_merchant_id', 'merchant_id'),
        Index('idx_payout_account_is_active', 'is_active'),
        UniqueConstraint('merchant_id', 'operator', 'phone', name='uq_payout_account'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    country = Column(String(2), nullable=False)  # "CM"
    operator = Column(
        ENUM(PayoutOperatorEnum, name='payout_operator_enum'),
        nullable=False
    )
    phone = Column(String(20), nullable=False)
    is_active = Column(Boolean(), nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='payout_accounts')
    payouts = relationship('Payout', back_populates='account')

    def __repr__(self):
        return f"<PayoutAccount(id={self.id}, operator={self.operator}, phone={self.phone})>"

    def deactivate(self):
        """Désactive le compte"""
        self.is_active = False
        self.updated_at = datetime.utcnow()


# ========== PAYOUT ==========

class Payout(Base):
    """
    Demande de retrait de fonds
    """
    __tablename__ = "payout"
    __table_args__ = (
        Index('idx_payout_merchant_id', 'merchant_id'),
        Index('idx_payout_status', 'status'),
        Index('idx_payout_created_at', 'created_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    payout_account_id = Column(UUID(as_uuid=True), ForeignKey('payout_account.id', ondelete='RESTRICT'), nullable=False)
    amount = Column(BigInteger(), nullable=False)  # in centimes
    status = Column(
        ENUM(PayoutStatusEnum, name='payout_status_enum'),
        nullable=False,
        server_default='REQUESTED'
    )
    provider_reference = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='payouts')
    account = relationship('PayoutAccount', back_populates='payouts')

    def __repr__(self):
        return f"<Payout(id={self.id}, amount={self.amount}, status={self.status})>"

    @property
    def amount_xof(self) -> float:
        """Convertit centimes en XOF"""
        return self.amount / 100

    def settle(self, session: Session, provider_reference: str):
        """Marque le payout comme réglé"""
        if self.status != PayoutStatusEnum.PROCESSING:
            raise ValueError(f"Cannot settle payout in status {self.status}")
        self.status = PayoutStatusEnum.SETTLED
        self.provider_reference = provider_reference
        self.updated_at = datetime.utcnow()

    def fail(self, session: Session):
        """Marque le payout comme échoué"""
        if self.status not in [PayoutStatusEnum.REQUESTED, PayoutStatusEnum.PROCESSING]:
            raise ValueError(f"Cannot fail payout in status {self.status}")
        self.status = PayoutStatusEnum.FAILED
        self.updated_at = datetime.utcnow()

    def cancel(self, session: Session):
        """Annule le payout"""
        if self.status not in [PayoutStatusEnum.REQUESTED, PayoutStatusEnum.PROCESSING]:
            raise ValueError(f"Cannot cancel payout in status {self.status}")
        self.status = PayoutStatusEnum.CANCELLED
        self.updated_at = datetime.utcnow()


# ========== NOTIFICATION_LOG ==========

class NotificationLog(Base):
    """
    Log de toutes les notifications envoyées
    """
    __tablename__ = "notification_log"
    __table_args__ = (
        Index('idx_notification_merchant_id', 'merchant_id'),
        Index('idx_notification_status', 'status'),
        Index('idx_notification_channel', 'channel'),
        Index('idx_notification_created_at', 'created_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey('merchant.id', ondelete='CASCADE'), nullable=False)
    customer_phone = Column(String(20), nullable=False)
    channel = Column(String(50), nullable=False)  # WHATSAPP, SMS, EMAIL
    template = Column(String(100), nullable=False)  # order_shipped, payment_received, etc.
    payload = Column(JSON(), nullable=True)
    status = Column(String(50), nullable=False, server_default='PENDING')  # PENDING, SENT, FAILED
    provider_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    merchant = relationship('Merchant', back_populates='notifications')

    def __repr__(self):
        return f"<NotificationLog(id={self.id}, channel={self.channel}, status={self.status})>"

    def mark_sent(self, provider_reference: str = None):
        """Marque comme envoyée"""
        self.status = 'SENT'
        if provider_reference:
            self.provider_reference = provider_reference

    def mark_failed(self, reason: str = None):
        """Marque comme échouée"""
        self.status = 'FAILED'
        if reason:
            self.payload = self.payload or {}
            self.payload['error_reason'] = reason
