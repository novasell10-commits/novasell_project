"""
Order Service for NovaSell
Location: app/services/order_service.py

Gère la CRÉATION et la GESTION des commandes.
Utilise LedgerService pour tous les mouvements financiers.

Core Operations:
  1. create_order()      - Crée order + items + escrow hold
  2. update_status()     - Change statut (PAID → PROCESSING → SHIPPED, etc.)
  3. confirm_order()     - Client confirme livraison (atomic: release escrow + credit)
  4. cancel_order()      - Annule commande + crée refund
  5. get_order()         - Récupère une commande
  6. list_orders()       - Liste avec filtres
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple
from uuid import UUID
import uuid

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import (
    Order, OrderItem, OrderStatusEnum, OrderStatusHistory,
    Product, Customer, Merchant,
    LedgerTypeEnum, LedgerStatusEnum
)
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class OrderService:
    """
    Service for managing orders and order items.
    
    Financial flow:
    - Order created     → Escrow hold via Ledger
    - Order confirmed   → Escrow released + Merchant credited (atomic)
    - Order cancelled   → Refund via Ledger
    """

    # ========== CREATE ORDER ==========

    @staticmethod
    def create_order(
        session: Session,
        merchant_id: UUID,
        customer_phone: str,
        items: List[Dict],  # [{product_id, qty}, ...]
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        manual: bool = False
    ) -> Order:
        """
        Créer une nouvelle commande.
        
        Args:
            session: DB session
            merchant_id: Seller ID
            customer_phone: E.164 format (+237...)
            items: List of {product_id, qty}
            origin_city: Origin city (optional)
            destination_city: Destination city (optional)
            manual: True if manually created by merchant (not from WhatsApp)
        
        Returns:
            Order object (PAID status, with escrow hold)
        
        Flow:
            1. Validate customer phone
            2. Get or create customer
            3. Validate products exist and have stock
            4. Create order with status PAID
            5. Create order items (snapshots)
            6. Calculate totals + escrow amount
            7. Create ESCROW_HOLD in ledger
            8. Return order
        
        Raises:
            ValueError: If validation fails
        """
        logger.info(
            f"Creating order | merchant={merchant_id} | customer_phone={customer_phone} | "
            f"items_count={len(items)} | manual={manual}"
        )

        # Step 1: Validate customer phone format
        if not customer_phone.startswith('+'):
            raise ValueError(f"Invalid phone format: {customer_phone}. Must be E.164 (+237...)")

        # Step 2: Get or create customer
        customer = Customer.get_or_create(
            session=session,
            phone=customer_phone,
            merchant_id=merchant_id
        )
        logger.debug(f"Customer resolved | customer_id={customer.id} | phone={customer_phone}")

        # Step 3: Validate products and calculate totals
        if not items:
            raise ValueError("Order must have at least one item")

        order_items_data = []
        subtotal = 0

        for item_spec in items:
            product_id = item_spec.get('product_id')
            qty = item_spec.get('qty', 1)

            if not product_id or qty < 1:
                raise ValueError(f"Invalid item: {item_spec}")

            product = session.query(Product).filter(Product.id == product_id).first()
            if not product:
                raise ValueError(f"Product not found: {product_id}")

            if product.merchant_id != merchant_id:
                raise ValueError(f"Product not owned by merchant: {product_id}")

            if not product.is_available(qty):
                raise ValueError(
                    f"Product not available: {product.name} "
                    f"(stock: {product.stock}, requested: {qty})"
                )

            item_total = product.price_amount * qty
            subtotal += item_total

            order_items_data.append({
                'product_id': product_id,
                'product_name': product.name,
                'qty': qty,
                'unit_price': product.price_amount,
                'subtotal': item_total
            })

        logger.debug(f"Items validated | subtotal={subtotal}")

        # Step 4: Create order
        escrow_amount = subtotal  # 100% escrow (customer holds all funds)
        total_amount = subtotal   # No additional fees for MVP

        order = Order(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            customer_id=customer.id,
            customer_phone_snapshot=customer_phone,
            origin_city=origin_city,
            destination_city=destination_city,
            manual=manual,
            status=OrderStatusEnum.PAID,
            subtotal_amount=subtotal,
            total_amount=total_amount,
            escrow_amount=escrow_amount,
            currency='XOF'
        )

        session.add(order)
        session.flush()
        logger.debug(f"Order created | order_id={order.id} | status={order.status.value}")

        # Step 5: Create order items (snapshots of product at order time)
        for item_data in order_items_data:
            order_item = OrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                product_id=item_data['product_id'],
                name_snapshot=item_data['product_name'],
                qty=item_data['qty'],
                unit_price_amount=item_data['unit_price']
            )
            session.add(order_item)

        session.flush()
        logger.debug(f"Order items created | count={len(order_items_data)}")

        # Step 6: Create initial status history
        history = OrderStatusHistory(
            id=uuid.uuid4(),
            order_id=order.id,
            from_status=None,
            to_status=OrderStatusEnum.PAID,
            actor='SYSTEM' if not manual else 'MERCHANT',
            metadata={'reason': 'Order created'}
        )
        session.add(history)
        session.flush()

        # Step 7: Create ESCROW_HOLD in ledger (CRITICAL!)
        try:
            LedgerService.create_escrow_hold(
                session=session,
                merchant_id=merchant_id,
                order_id=order.id,
                amount=escrow_amount,
                idempotency_key=f"order-hold-{order.id}"
            )
            logger.info(f"Escrow hold created | order_id={order.id} | amount={escrow_amount}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create escrow hold: {str(e)}")
            raise

        session.commit()
        logger.info(f"Order created successfully | order_id={order.id} | total={total_amount}")
        return order

    # ========== UPDATE ORDER STATUS ==========

    @staticmethod
    def update_status(
        session: Session,
        order_id: UUID,
        new_status: OrderStatusEnum,
        actor: str = 'MERCHANT',
        metadata: Optional[Dict] = None
    ) -> Order:
        """
        Mettre à jour le statut d'une commande.
        
        Args:
            session: DB session
            order_id: Order ID
            new_status: New status (PAID, PROCESSING, SHIPPED, etc.)
            actor: Who made the change (MERCHANT, CUSTOMER, SYSTEM)
            metadata: Optional metadata
        
        Returns:
            Updated order
        
        Valid transitions:
            PAID → PROCESSING (merchant starts processing)
            PROCESSING → SHIPPED (merchant ships)
            SHIPPED → AWAITING_CONFIRMATION (customer receives)
            AWAITING_CONFIRMATION → CONFIRMED (customer confirms)
            * → CANCELLED (any state can be cancelled)
        
        Raises:
            ValueError: If invalid transition
        """
        logger.info(
            f"Updating order status | order_id={order_id} | "
            f"new_status={new_status.value} | actor={actor}"
        )

        order = session.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        old_status = order.status

        # Validate transition
        valid_transitions = {
            OrderStatusEnum.PAID: [
                OrderStatusEnum.PROCESSING,
                OrderStatusEnum.CANCELLED
            ],
            OrderStatusEnum.PROCESSING: [
                OrderStatusEnum.SHIPPED,
                OrderStatusEnum.CANCELLED
            ],
            OrderStatusEnum.SHIPPED: [
                OrderStatusEnum.AWAITING_CONFIRMATION,
                OrderStatusEnum.CANCELLED
            ],
            OrderStatusEnum.AWAITING_CONFIRMATION: [
                OrderStatusEnum.CONFIRMED,
                OrderStatusEnum.CANCELLED
            ],
            OrderStatusEnum.CONFIRMED: [
                OrderStatusEnum.CANCELLED  # Can still cancel confirmed? Depends on policy
            ],
            OrderStatusEnum.CANCELLED: []  # Can't transition from CANCELLED
        }

        if new_status not in valid_transitions.get(old_status, []):
            raise ValueError(
                f"Invalid transition: {old_status.value} → {new_status.value}"
            )

        # Update order
        order.status = new_status
        order.updated_at = datetime.utcnow()

        # Create status history
        history = OrderStatusHistory(
            id=uuid.uuid4(),
            order_id=order.id,
            from_status=old_status,
            to_status=new_status,
            actor=actor,
            metadata=metadata or {}
        )
        session.add(history)
        session.flush()

        logger.info(
            f"Order status updated | order_id={order_id} | "
            f"{old_status.value} → {new_status.value}"
        )
        return order

    # ========== CONFIRM ORDER (ATOMIC!) ==========

    @staticmethod
    def confirm_order(
        session: Session,
        order_id: UUID,
        actor: str = 'CUSTOMER'
    ) -> Order:
        """
        Confirmer la réception d'une commande (CLIENT).
        
        C'est l'opération CRUCIALE:
        - Escrow est libéré
        - Merchant est crédité (ATOMIC!)
        - Order passe en CONFIRMED
        
        Args:
            session: DB session
            order_id: Order ID
            actor: Usually 'CUSTOMER', can be 'MERCHANT' for manual confirmation
        
        Returns:
            Confirmed order
        
        Flow:
            1. Get order (must be AWAITING_CONFIRMATION)
            2. Validate escrow hold exists and is POSTED
            3. ATOMIC: Release escrow + Credit merchant
            4. Update order status to CONFIRMED
            5. Create status history
        
        Raises:
            ValueError: If order not in correct status
        """
        logger.info(
            f"Confirming order | order_id={order_id} | actor={actor}"
        )

        order = session.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        if order.status != OrderStatusEnum.AWAITING_CONFIRMATION:
            raise ValueError(
                f"Cannot confirm order in status {order.status.value}. "
                f"Must be AWAITING_CONFIRMATION."
            )

        try:
            # ATOMIC: Release escrow + Credit merchant
            release_entry, credit_entry = LedgerService.create_escrow_release_and_credit(
                session=session,
                merchant_id=order.merchant_id,
                order_id=order.id,
                amount=order.escrow_amount
            )

            logger.debug(
                f"Escrow released and merchant credited | "
                f"release_entry={release_entry.id} | credit_entry={credit_entry.id}"
            )

            # Update order status
            order.status = OrderStatusEnum.CONFIRMED
            order.updated_at = datetime.utcnow()

            # Create history
            history = OrderStatusHistory(
                id=uuid.uuid4(),
                order_id=order.id,
                from_status=OrderStatusEnum.AWAITING_CONFIRMATION,
                to_status=OrderStatusEnum.CONFIRMED,
                actor=actor,
                metadata={
                    'reason': 'Customer confirmed delivery',
                    'escrow_amount': order.escrow_amount
                }
            )
            session.add(history)
            session.flush()

            session.commit()
            logger.info(
                f"Order confirmed successfully | order_id={order_id} | "
                f"merchant_credited={order.escrow_amount}"
            )
            return order

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to confirm order: {str(e)}")
            raise

    # ========== CANCEL ORDER ==========

    @staticmethod
    def cancel_order(
        session: Session,
        order_id: UUID,
        reason: str = 'Unknown reason',
        actor: str = 'SYSTEM'
    ) -> Order:
        """
        Annuler une commande.
        
        Creates REFUND entry in ledger.
        Reverses escrow hold.
        
        Args:
            session: DB session
            order_id: Order ID
            reason: Reason for cancellation
            actor: Who cancelled (MERCHANT, CUSTOMER, SYSTEM)
        
        Returns:
            Cancelled order
        
        Flow:
            1. Get order
            2. Validate not already CANCELLED or CONFIRMED
            3. Create REFUND in ledger
            4. Update order status to CANCELLED
            5. Create status history
        
        Raises:
            ValueError: If order cannot be cancelled
        """
        logger.info(
            f"Cancelling order | order_id={order_id} | reason={reason} | actor={actor}"
        )

        order = session.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        if order.status == OrderStatusEnum.CANCELLED:
            raise ValueError("Order is already cancelled")

        if order.status == OrderStatusEnum.CONFIRMED:
            raise ValueError(
                "Cannot cancel confirmed order. "
                "Contact support for refund requests."
            )

        try:
            # Create refund in ledger
            refund_entry = LedgerService.create_refund(
                session=session,
                merchant_id=order.merchant_id,
                order_id=order.id,
                amount=order.escrow_amount,
                idempotency_key=f"refund-{order.id}",
                reason=reason
            )

            logger.debug(f"Refund created | refund_entry={refund_entry.id}")

            # Update order
            old_status = order.status
            order.status = OrderStatusEnum.CANCELLED
            order.updated_at = datetime.utcnow()

            # Create history
            history = OrderStatusHistory(
                id=uuid.uuid4(),
                order_id=order.id,
                from_status=old_status,
                to_status=OrderStatusEnum.CANCELLED,
                actor=actor,
                metadata={
                    'reason': reason,
                    'refund_amount': order.escrow_amount
                }
            )
            session.add(history)
            session.flush()

            session.commit()
            logger.info(
                f"Order cancelled successfully | order_id={order_id} | "
                f"refund_amount={order.escrow_amount}"
            )
            return order

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to cancel order: {str(e)}")
            raise

    # ========== GET & LIST ORDERS ==========

    @staticmethod
    def get_order(
        session: Session,
        order_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Order:
        """
        Récupérer une commande par ID.
        
        Optionally filter by merchant_id for access control.
        """
        query = session.query(Order).filter(Order.id == order_id)

        if merchant_id:
            query = query.filter(Order.merchant_id == merchant_id)

        order = query.first()
        if not order:
            raise ValueError(f"Order not found: {order_id}")

        return order

    @staticmethod
    def list_orders(
        session: Session,
        merchant_id: UUID,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        customer_phone: Optional[str] = None,
        order_by: str = 'created_at_desc'
    ) -> Tuple[int, List[Order]]:
        """
        Lister les commandes avec filtres.
        
        Args:
            session: DB session
            merchant_id: Filter by merchant
            skip: Pagination offset
            limit: Pagination limit
            status: Filter by status (PAID, PROCESSING, etc.)
            customer_phone: Filter by customer phone
            order_by: Sort order (created_at_desc, total_amount_desc, etc.)
        
        Returns:
            (total_count, orders)
        """
        query = session.query(Order).filter(Order.merchant_id == merchant_id)

        if status:
            try:
                status_enum = OrderStatusEnum(status)
                query = query.filter(Order.status == status_enum)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")

        if customer_phone:
            query = query.filter(Order.customer_phone_snapshot == customer_phone)

        total = query.count()

        # Apply ordering
        if order_by == 'created_at_desc':
            query = query.order_by(Order.created_at.desc())
        elif order_by == 'created_at_asc':
            query = query.order_by(Order.created_at.asc())
        elif order_by == 'total_amount_desc':
            query = query.order_by(Order.total_amount.desc())
        elif order_by == 'total_amount_asc':
            query = query.order_by(Order.total_amount.asc())
        else:
            query = query.order_by(Order.created_at.desc())

        orders = query.offset(skip).limit(limit).all()

        return total, orders

    # ========== ORDER ITEMS ==========

    @staticmethod
    def get_order_items(
        session: Session,
        order_id: UUID
    ) -> List[OrderItem]:
        """Récupérer tous les items d'une commande"""
        items = session.query(OrderItem).filter(
            OrderItem.order_id == order_id
        ).all()
        return items

    # ========== ORDER STATUS HISTORY ==========

    @staticmethod
    def get_order_history(
        session: Session,
        order_id: UUID
    ) -> List[OrderStatusHistory]:
        """Récupérer l'historique des changements de statut"""
        history = session.query(OrderStatusHistory).filter(
            OrderStatusHistory.order_id == order_id
        ).order_by(OrderStatusHistory.created_at.asc()).all()
        return history