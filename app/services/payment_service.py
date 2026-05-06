"""
Payment Service for NovaSell
Location: app/services/payment_service.py

Gère TOUS les paiements:
  1. create_payment()           - Créer payment request (initie paiement)
  2. handle_orange_webhook()    - Webhook Orange Money
  3. handle_mtn_webhook()       - Webhook MTN Money
  4. verify_payment()           - Vérifier statut paiement
  5. refund_payment()           - Remboursement
  6. get_payment()              - Récupérer un paiement

Core Rules:
  - Webhooks MUST be idempotent (handle duplicate calls)
  - ALWAYS verify provider signature
  - Payment state must sync with Order state
  - Create ledger entries AFTER payment confirmed
"""

import logging
import hashlib
import hmac
from datetime import datetime
from typing import Optional, Dict
from uuid import UUID
import uuid

from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import (
    Payment, PaymentStatusEnum, PaymentProviderEnum,
    Order, OrderStatusEnum,
    LedgerTypeEnum, LedgerStatusEnum
)
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Service for managing payments and payment webhooks.
    
    Payment lifecycle:
        PENDING (created, awaiting customer payment)
        ↓
        SUCCEEDED (customer paid successfully)
        ↓
        [Order can be processed]
    
    ALT: FAILED (payment failed), REFUNDED (refund processed)
    """

    # ========== CREATE PAYMENT ==========

    @staticmethod
    def create_payment(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        customer_id: UUID,
        customer_phone: str,
        provider: str,  # "ORANGE_MONEY" or "MTN_MONEY"
        amount: int  # in centimes
    ) -> Payment:
        """
        Créer une demande de paiement.
        
        This initiates the payment flow with the provider.
        Customer will receive SMS/USSD prompt to pay.
        
        Args:
            session: DB session
            merchant_id: Seller ID
            order_id: Order ID
            customer_id: Customer ID
            customer_phone: E.164 format
            provider: "ORANGE_MONEY" or "MTN_MONEY"
            amount: Amount in centimes
        
        Returns:
            Payment object (status=PENDING)
        
        Flow:
            1. Validate provider
            2. Generate unique provider_reference (idempotency)
            3. Create payment (PENDING)
            4. Call provider API to initiate payment
            5. Return payment
        
        Raises:
            ValueError: If provider invalid or provider API fails
        """
        logger.info(
            f"Creating payment | merchant={merchant_id} | order={order_id} | "
            f"provider={provider} | amount={amount}"
        )

        # Validate provider
        try:
            provider_enum = PaymentProviderEnum(provider)
        except ValueError:
            raise ValueError(f"Invalid provider: {provider}")

        # Generate unique provider reference for idempotency
        provider_reference = PaymentService._generate_provider_reference(
            merchant_id, order_id
        )

        # Create payment (PENDING)
        payment = Payment(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            customer_id=customer_id,
            provider=provider_enum,
            provider_reference=provider_reference,
            status=PaymentStatusEnum.PENDING,
            amount=amount,
            currency='XOF'
        )

        session.add(payment)
        try:
            session.flush()
            logger.debug(f"Payment created | payment_id={payment.id}")
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Payment creation failed (duplicate?): {str(e)}")
            raise ValueError(f"Payment already exists for this order")

        # TODO: Call provider API to initiate payment
        # In production:
        # if provider == PaymentProviderEnum.ORANGE_MONEY:
        #     PaymentService._initiate_orange_payment(payment, customer_phone)
        # elif provider == PaymentProviderEnum.MTN_MONEY:
        #     PaymentService._initiate_mtn_payment(payment, customer_phone)

        session.commit()
        logger.info(f"Payment created | payment_id={payment.id}")
        return payment

    # ========== WEBHOOK HANDLERS ==========

    @staticmethod
    def handle_orange_webhook(
        session: Session,
        payload: Dict,
        signature: Optional[str] = None
    ) -> Dict:
        """
        Handle Orange Money webhook callback.
        
        CRITICAL: Must be idempotent (handle duplicate calls)!
        
        Webhook payload (example):
        {
            "transaction_id": "OM123456789",
            "merchant_reference": "payment-uuid-here",
            "status": "SUCCESS" or "FAILED",
            "amount": 50000,
            "customer_phone": "+237690000000",
            "timestamp": "2026-05-03T10:30:00Z"
        }
        
        Args:
            session: DB session
            payload: Webhook payload from Orange
            signature: Signature for verification (optional in dev)
        
        Returns:
            {
                "status": "success",
                "transaction_id": "OM123456789",
                "order_id": "uuid...",
                "payment_status": "SUCCEEDED"
            }
        
        Flow:
            1. Verify signature (security!)
            2. Find payment by merchant_reference
            3. Check idempotency (already processed?)
            4. Validate amount matches
            5. Update payment status
            6. Post escrow hold (if successful)
            7. Return confirmation
        
        Raises:
            ValueError: If signature invalid, payment not found, etc.
        """
        logger.info(
            f"Orange webhook received | merchant_ref={payload.get('merchant_reference')} | "
            f"status={payload.get('status')}"
        )

        # Step 1: Verify signature (optional in dev, critical in prod)
        if signature and False:  # Disabled in dev
            if not PaymentService._verify_orange_signature(payload, signature):
                logger.error("Orange webhook signature verification failed!")
                raise ValueError("Invalid signature")

        # Step 2: Extract data
        merchant_reference = payload.get('merchant_reference')
        transaction_id = payload.get('transaction_id')
        status = payload.get('status')  # "SUCCESS" or "FAILED"
        amount = payload.get('amount')

        if not merchant_reference:
            logger.error("Missing merchant_reference in webhook")
            raise ValueError("Missing merchant_reference")

        # Step 3: Find payment
        payment = session.query(Payment).filter(
            Payment.provider_reference == merchant_reference
        ).first()

        if not payment:
            logger.error(f"Payment not found for reference: {merchant_reference}")
            raise ValueError(f"Payment not found: {merchant_reference}")

        # Step 4: Check idempotency (already processed?)
        if payment.status != PaymentStatusEnum.PENDING:
            logger.warning(
                f"Payment already processed | payment_id={payment.id} | "
                f"current_status={payment.status.value} | webhook_status={status}"
            )
            # Return success anyway (idempotent)
            return {
                "status": "success",
                "message": "Payment already processed",
                "transaction_id": transaction_id,
                "payment_id": str(payment.id),
                "payment_status": payment.status.value
            }

        # Step 5: Validate amount
        if amount != payment.amount:
            logger.error(
                f"Amount mismatch | payment_id={payment.id} | "
                f"expected={payment.amount} | received={amount}"
            )
            raise ValueError(
                f"Amount mismatch: expected {payment.amount}, got {amount}"
            )

        try:
            # Step 6: Update payment status
            if status == "SUCCESS":
                payment.status = PaymentStatusEnum.SUCCEEDED
                payment.updated_at = datetime.utcnow()

                # Post escrow hold (payment confirmed)
                order = session.query(Order).filter(
                    Order.id == payment.order_id
                ).first()

                if order and order.status == OrderStatusEnum.PAID:
                    LedgerService.post_escrow_hold(
                        session=session,
                        order_id=order.id
                    )
                    logger.debug(
                        f"Escrow hold posted | order_id={order.id}"
                    )

                logger.info(
                    f"Payment succeeded | payment_id={payment.id} | "
                    f"transaction_id={transaction_id}"
                )

            elif status == "FAILED":
                payment.status = PaymentStatusEnum.FAILED
                payment.updated_at = datetime.utcnow()
                logger.warning(
                    f"Payment failed | payment_id={payment.id} | "
                    f"transaction_id={transaction_id}"
                )

            session.commit()

            return {
                "status": "success",
                "transaction_id": transaction_id,
                "payment_id": str(payment.id),
                "order_id": str(payment.order_id),
                "payment_status": payment.status.value
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing Orange webhook: {str(e)}")
            raise

    @staticmethod
    def handle_mtn_webhook(
        session: Session,
        payload: Dict,
        signature: Optional[str] = None
    ) -> Dict:
        """
        Handle MTN Money webhook callback.
        
        Similar to Orange webhook but with MTN API format.
        
        Webhook payload (example):
        {
            "TransactionId": "MT123456789",
            "ExternalId": "payment-uuid-here",
            "FinancialTransactionId": "...",
            "TransactionStatus": "Succeeded" or "Failed",
            "Amount": "50000",
            "Currency": "XOF",
            "Payer": {
                "PartyIdType": "MSISDN",
                "PartyId": "+237690000000"
            },
            "Timestamp": "2026-05-03T10:30:00Z"
        }
        
        Args:
            session: DB session
            payload: Webhook payload from MTN
            signature: Signature for verification
        
        Returns:
            Same format as Orange webhook
        
        Raises:
            ValueError: If validation fails
        """
        logger.info(
            f"MTN webhook received | external_id={payload.get('ExternalId')} | "
            f"status={payload.get('TransactionStatus')}"
        )

        # Step 1: Verify signature (optional in dev)
        if signature and False:
            if not PaymentService._verify_mtn_signature(payload, signature):
                logger.error("MTN webhook signature verification failed!")
                raise ValueError("Invalid signature")

        # Step 2: Extract data (MTN uses different field names!)
        external_id = payload.get('ExternalId')
        transaction_id = payload.get('TransactionId')
        status = payload.get('TransactionStatus')  # "Succeeded" or "Failed"
        amount = int(payload.get('Amount', 0))

        if not external_id:
            logger.error("Missing ExternalId in MTN webhook")
            raise ValueError("Missing ExternalId")

        # Step 3: Find payment
        payment = session.query(Payment).filter(
            Payment.provider_reference == external_id
        ).first()

        if not payment:
            logger.error(f"Payment not found for MTN reference: {external_id}")
            raise ValueError(f"Payment not found: {external_id}")

        # Step 4: Check idempotency
        if payment.status != PaymentStatusEnum.PENDING:
            logger.warning(
                f"Payment already processed | payment_id={payment.id} | "
                f"current_status={payment.status.value} | webhook_status={status}"
            )
            return {
                "status": "success",
                "message": "Payment already processed",
                "transaction_id": transaction_id,
                "payment_id": str(payment.id),
                "payment_status": payment.status.value
            }

        # Step 5: Validate amount
        if amount != payment.amount:
            logger.error(
                f"Amount mismatch | payment_id={payment.id} | "
                f"expected={payment.amount} | received={amount}"
            )
            raise ValueError(
                f"Amount mismatch: expected {payment.amount}, got {amount}"
            )

        try:
            # Step 6: Update payment status
            if status == "Succeeded":
                payment.status = PaymentStatusEnum.SUCCEEDED
                payment.updated_at = datetime.utcnow()

                # Post escrow hold
                order = session.query(Order).filter(
                    Order.id == payment.order_id
                ).first()

                if order and order.status == OrderStatusEnum.PAID:
                    LedgerService.post_escrow_hold(
                        session=session,
                        order_id=order.id
                    )
                    logger.debug(
                        f"Escrow hold posted | order_id={order.id}"
                    )

                logger.info(
                    f"MTN payment succeeded | payment_id={payment.id} | "
                    f"transaction_id={transaction_id}"
                )

            elif status == "Failed":
                payment.status = PaymentStatusEnum.FAILED
                payment.updated_at = datetime.utcnow()
                logger.warning(
                    f"MTN payment failed | payment_id={payment.id}"
                )

            session.commit()

            return {
                "status": "success",
                "transaction_id": transaction_id,
                "payment_id": str(payment.id),
                "order_id": str(payment.order_id),
                "payment_status": payment.status.value
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing MTN webhook: {str(e)}")
            raise

    # ========== VERIFY & REFUND ==========

    @staticmethod
    def verify_payment(
        session: Session,
        payment_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Dict:
        """
        Vérifier le statut d'un paiement.
        
        Optionally filter by merchant_id for access control.
        """
        payment = session.query(Payment).filter(
            Payment.id == payment_id
        ).first()

        if not payment:
            raise ValueError(f"Payment not found: {payment_id}")

        if merchant_id and payment.merchant_id != merchant_id:
            raise ValueError(f"Payment not owned by merchant")

        return {
            "id": str(payment.id),
            "order_id": str(payment.order_id),
            "provider": payment.provider.value,
            "status": payment.status.value,
            "amount": payment.amount,
            "currency": payment.currency,
            "created_at": payment.created_at.isoformat(),
            "updated_at": payment.updated_at.isoformat()
        }

    @staticmethod
    def refund_payment(
        session: Session,
        payment_id: UUID,
        reason: str = "Customer requested"
    ) -> Payment:
        """
        Refund un paiement.
        
        CRITICAL: Only works if payment is SUCCEEDED!
        
        In production, would call provider API to reverse transaction.
        For MVP, just mark as REFUNDED.
        """
        logger.info(
            f"Refunding payment | payment_id={payment_id} | reason={reason}"
        )

        payment = session.query(Payment).filter(
            Payment.id == payment_id
        ).first()

        if not payment:
            raise ValueError(f"Payment not found: {payment_id}")

        if payment.status != PaymentStatusEnum.SUCCEEDED:
            raise ValueError(
                f"Cannot refund payment in status {payment.status.value}. "
                f"Must be SUCCEEDED."
            )

        try:
            payment.status = PaymentStatusEnum.REFUNDED
            payment.updated_at = datetime.utcnow()

            # TODO: Call provider API to reverse transaction
            # if payment.provider == PaymentProviderEnum.ORANGE_MONEY:
            #     PaymentService._refund_orange_payment(payment)
            # elif payment.provider == PaymentProviderEnum.MTN_MONEY:
            #     PaymentService._refund_mtn_payment(payment)

            session.commit()
            logger.info(f"Payment refunded | payment_id={payment.id}")
            return payment

        except Exception as e:
            session.rollback()
            logger.error(f"Error refunding payment: {str(e)}")
            raise

    # ========== GET PAYMENT ==========

    @staticmethod
    def get_payment(
        session: Session,
        payment_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Payment:
        """Récupérer un paiement"""
        query = session.query(Payment).filter(Payment.id == payment_id)

        if merchant_id:
            query = query.filter(Payment.merchant_id == merchant_id)

        payment = query.first()
        if not payment:
            raise ValueError(f"Payment not found: {payment_id}")

        return payment

    @staticmethod
    def get_order_payment(
        session: Session,
        order_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Optional[Payment]:
        """Récupérer le paiement d'une commande"""
        query = session.query(Payment).filter(Payment.order_id == order_id)

        if merchant_id:
            query = query.filter(Payment.merchant_id == merchant_id)

        return query.first()

    # ========== HELPER METHODS ==========

    @staticmethod
    def _generate_provider_reference(merchant_id: UUID, order_id: UUID) -> str:
        """
        Generate unique provider reference for idempotency.
        
        Format: merchant-order-timestamp-hash
        This ensures same order always gets same reference.
        """
        base = f"{merchant_id}-{order_id}"
        hash_digest = hashlib.md5(base.encode()).hexdigest()[:8]
        return f"pay-{hash_digest}"

    @staticmethod
    def _verify_orange_signature(payload: Dict, signature: str) -> bool:
        """
        Verify Orange Money webhook signature.
        
        In production:
            payload_string = json.dumps(payload, sort_keys=True)
            expected_sig = hmac.new(
                key=ORANGE_SECRET,
                msg=payload_string.encode(),
                digestmod=hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(signature, expected_sig)
        """
        logger.debug("Orange signature verification (disabled in dev)")
        return True

    @staticmethod
    def _verify_mtn_signature(payload: Dict, signature: str) -> bool:
        """
        Verify MTN Money webhook signature.
        
        Similar to Orange but with MTN-specific format.
        """
        logger.debug("MTN signature verification (disabled in dev)")
        return True

    # TODO: Implement in production
    # @staticmethod
    # def _initiate_orange_payment(payment: Payment, customer_phone: str):
    #     """Call Orange Money API to initiate payment"""
    #     pass
    #
    # @staticmethod
    # def _initiate_mtn_payment(payment: Payment, customer_phone: str):
    #     """Call MTN Money API to initiate payment"""
    #     pass
    #
    # @staticmethod
    # def _refund_orange_payment(payment: Payment):
    #     """Call Orange Money API to refund"""
    #     pass
    #
    # @staticmethod
    # def _refund_mtn_payment(payment: Payment):
    #     """Call MTN Money API to refund"""
    #     pass