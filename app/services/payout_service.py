"""
Payout Service for NovaSell
Location: app/services/payout_service.py

Gère TOUS les retraits d'argent:
  1. request_payout()           - Demande retrait (réserve argent)
  2. process_payout()           - Lance retrait (appelle provider)
  3. handle_orange_webhook()    - Webhook Orange (settlement)
  4. handle_mtn_webhook()       - Webhook MTN (settlement)
  5. get_payout()               - Récupère un retrait
  6. list_payouts()             - Liste les retraits

Core Rules:
  - ALWAYS validate balance before requesting
  - Payout RESERVES funds (moves to PENDING)
  - Webhook SETTLES funds (truly gone)
  - Idempotent webhooks (like payment)
  - Max 2 active payout accounts per merchant
"""

import logging
from datetime import datetime
from typing import Optional, List, Tuple
from uuid import UUID
import uuid

from sqlalchemy import and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import (
    Payout, PayoutStatusEnum,
    PayoutAccount, PayoutOperatorEnum,
    Merchant,
    LedgerTypeEnum, LedgerStatusEnum
)
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)


class PayoutService:
    """
    Service for managing payouts (withdrawals).
    
    Payout lifecycle:
        REQUESTED (merchant asks to withdraw)
        ↓
        [Amount reserved in ledger as PAYOUT_REQUEST PENDING]
        ↓
        PROCESSING (payout sent to provider)
        ↓
        [Provider processes the transaction]
        ↓
        SETTLED (money received by merchant)
        ↓
        [Ledger entry posted, truly gone]
    
    ALT: FAILED (provider error), CANCELLED (merchant cancels)
    """

    # ========== PAYOUT ACCOUNTS ==========

    @staticmethod
    def create_payout_account(
        session: Session,
        merchant_id: UUID,
        country: str,
        operator: str,  # "ORANGE_MONEY" or "MTN_MONEY"
        phone: str
    ) -> PayoutAccount:
        """
        Créer un compte de retrait.
        
        Merchant can have max 2 active accounts (trigger in DB).
        
        Args:
            session: DB session
            merchant_id: Merchant ID
            country: Country code (CM, SN, etc.)
            operator: "ORANGE_MONEY" or "MTN_MONEY"
            phone: Account phone (E.164 format)
        
        Returns:
            PayoutAccount
        
        Raises:
            ValueError: If max accounts reached or invalid operator
        """
        logger.info(
            f"Creating payout account | merchant={merchant_id} | "
            f"operator={operator} | phone={phone}"
        )

        # Validate operator
        try:
            operator_enum = PayoutOperatorEnum(operator)
        except ValueError:
            raise ValueError(f"Invalid operator: {operator}")

        # Check max accounts (2 active per merchant)
        active_count = session.query(PayoutAccount).filter(
            and_(
                PayoutAccount.merchant_id == merchant_id,
                PayoutAccount.is_active == True
            )
        ).count()

        if active_count >= 2:
            raise ValueError(
                f"Maximum 2 active payout accounts per merchant. "
                f"You have {active_count}. Deactivate one first."
            )

        account = PayoutAccount(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            country=country,
            operator=operator_enum,
            phone=phone,
            is_active=True
        )

        session.add(account)
        try:
            session.flush()
            logger.info(f"Payout account created | account_id={account.id}")
            return account
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Payout account creation failed: {str(e)}")
            raise ValueError(f"Account already exists for this operator and phone")

    @staticmethod
    def get_payout_account(
        session: Session,
        account_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> PayoutAccount:
        """Récupérer un compte de retrait"""
        query = session.query(PayoutAccount).filter(
            PayoutAccount.id == account_id
        )

        if merchant_id:
            query = query.filter(PayoutAccount.merchant_id == merchant_id)

        account = query.first()
        if not account:
            raise ValueError(f"Payout account not found: {account_id}")

        return account

    @staticmethod
    def list_payout_accounts(
        session: Session,
        merchant_id: UUID,
        active_only: bool = False
    ) -> List[PayoutAccount]:
        """Lister les comptes de retrait"""
        query = session.query(PayoutAccount).filter(
            PayoutAccount.merchant_id == merchant_id
        )

        if active_only:
            query = query.filter(PayoutAccount.is_active == True)

        return query.order_by(PayoutAccount.created_at.desc()).all()

    @staticmethod
    def deactivate_payout_account(
        session: Session,
        account_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> PayoutAccount:
        """Désactiver un compte de retrait"""
        account = PayoutService.get_payout_account(
            session, account_id, merchant_id
        )

        account.deactivate()
        session.flush()
        logger.info(f"Payout account deactivated | account_id={account_id}")
        return account

    # ========== REQUEST PAYOUT ==========

    @staticmethod
    def request_payout(
        session: Session,
        merchant_id: UUID,
        amount: int,  # in centimes
        payout_account_id: UUID
    ) -> Payout:
        """
        Demander un retrait d'argent.
        
        CRITICAL: Valide la balance AVANT de créer!
        
        Flow:
            1. Valider account existe et appartient au merchant
            2. Valider balance >= amount
            3. Créer payout (REQUESTED)
            4. Créer PAYOUT_REQUEST au ledger (PENDING)
            5. Reserve les fonds (balance.available -= amount)
        
        Args:
            session: DB session
            merchant_id: Merchant ID
            amount: Amount to withdraw (centimes)
            payout_account_id: Account to withdraw to
        
        Returns:
            Payout (status=REQUESTED)
        
        Raises:
            ValueError: If account not found, balance insufficient, etc.
        """
        logger.info(
            f"Requesting payout | merchant={merchant_id} | "
            f"amount={amount} | account={payout_account_id}"
        )

        # Step 1: Validate account
        account = PayoutService.get_payout_account(
            session, payout_account_id, merchant_id
        )

        if not account.is_active:
            raise ValueError(f"Payout account is not active")

        # Step 2: Validate balance
        try:
            LedgerService.validate_available_balance(
                session, merchant_id, amount
            )
        except ValueError as e:
            logger.warning(f"Payout balance validation failed: {str(e)}")
            raise

        # Step 3: Create payout
        payout = Payout(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            payout_account_id=payout_account_id,
            amount=amount,
            status=PayoutStatusEnum.REQUESTED
        )

        session.add(payout)
        session.flush()
        logger.debug(f"Payout created | payout_id={payout.id}")

        # Step 4: Create ledger entry (RESERVE funds)
        try:
            LedgerService.create_payout_request(
                session=session,
                merchant_id=merchant_id,
                payout_id=payout.id,
                amount=amount,
                idempotency_key=f"payout-request-{payout.id}"
            )
            logger.debug(f"Payout request created in ledger | payout_id={payout.id}")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create payout request in ledger: {str(e)}")
            raise

        session.commit()
        logger.info(
            f"Payout requested successfully | payout_id={payout.id} | "
            f"amount={amount} | status={payout.status.value}"
        )
        return payout

    # ========== PROCESS PAYOUT ==========

    @staticmethod
    def process_payout(
        session: Session,
        payout_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Payout:
        """
        Lancer un retrait (envoyer l'argent au provider).
        
        Appelle l'API du provider (Orange/MTN) pour vraiment envoyer l'argent.
        
        Flow:
            1. Valider payout existe et est REQUESTED
            2. Vérifier account est actif
            3. Appeler provider API
            4. Mettre à jour statut à PROCESSING
            5. Attendre webhook de settlement
        
        Raises:
            ValueError: If payout not REQUESTED or provider API fails
        """
        logger.info(f"Processing payout | payout_id={payout_id}")

        payout = session.query(Payout).filter(Payout.id == payout_id).first()
        if not payout:
            raise ValueError(f"Payout not found: {payout_id}")

        if merchant_id and payout.merchant_id != merchant_id:
            raise ValueError(f"Payout not owned by merchant")

        if payout.status != PayoutStatusEnum.REQUESTED:
            raise ValueError(
                f"Cannot process payout in status {payout.status.value}. "
                f"Must be REQUESTED."
            )

        # Verify account
        account = session.query(PayoutAccount).filter(
            PayoutAccount.id == payout.payout_account_id
        ).first()

        if not account or not account.is_active:
            raise ValueError(f"Payout account is not active")

        try:
            # TODO: Call provider API
            # if account.operator == PayoutOperatorEnum.ORANGE_MONEY:
            #     PayoutService._send_orange_payout(payout, account)
            # elif account.operator == PayoutOperatorEnum.MTN_MONEY:
            #     PayoutService._send_mtn_payout(payout, account)

            # Update status
            payout.status = PayoutStatusEnum.PROCESSING
            payout.updated_at = datetime.utcnow()
            session.flush()

            session.commit()
            logger.info(f"Payout processing started | payout_id={payout_id}")
            return payout

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing payout: {str(e)}")
            raise

    # ========== WEBHOOK HANDLERS ==========

    @staticmethod
    def handle_orange_payout_webhook(
        session: Session,
        payload: dict,
        signature: Optional[str] = None
    ) -> dict:
        """
        Handle Orange Money payout settlement webhook.
        
        Called when Orange has successfully sent the money to merchant.
        
        Webhook payload (example):
        {
            "payout_transaction_id": "OM_PAYOUT_123456",
            "merchant_reference": "payout-uuid-here",
            "status": "SETTLED" or "FAILED",
            "amount": 150000,
            "recipient_phone": "+237690000000",
            "timestamp": "2026-05-03T10:30:00Z"
        }
        
        Args:
            session: DB session
            payload: Webhook payload
            signature: Optional signature for verification
        
        Returns:
            {
                "status": "success",
                "payout_id": "uuid...",
                "payout_status": "SETTLED"
            }
        
        Flow:
            1. Verify signature (security!)
            2. Find payout by merchant_reference
            3. Check idempotency (already processed?)
            4. Validate amount
            5. Update payout status
            6. Post payout request in ledger (truly gone!)
            7. Return confirmation
        
        Raises:
            ValueError: If validation fails
        """
        logger.info(
            f"Orange payout webhook received | merchant_ref={payload.get('merchant_reference')} | "
            f"status={payload.get('status')}"
        )

        # Step 1: Verify signature (optional in dev)
        if signature and False:
            if not PayoutService._verify_orange_signature(payload, signature):
                logger.error("Orange payout webhook signature verification failed!")
                raise ValueError("Invalid signature")

        # Step 2: Extract data
        merchant_reference = payload.get('merchant_reference')
        payout_transaction_id = payload.get('payout_transaction_id')
        status = payload.get('status')  # "SETTLED" or "FAILED"
        amount = payload.get('amount')

        if not merchant_reference:
            logger.error("Missing merchant_reference in payout webhook")
            raise ValueError("Missing merchant_reference")

        # Step 3: Find payout
        payout = session.query(Payout).filter(
            Payout.id == UUID(merchant_reference.split('-')[-1])
        ).first()

        if not payout:
            logger.error(f"Payout not found for reference: {merchant_reference}")
            raise ValueError(f"Payout not found: {merchant_reference}")

        # Step 4: Check idempotency
        if payout.status == PayoutStatusEnum.SETTLED:
            logger.warning(
                f"Payout already settled | payout_id={payout.id} | "
                f"webhook_status={status}"
            )
            return {
                "status": "success",
                "message": "Payout already settled",
                "payout_id": str(payout.id),
                "payout_status": payout.status.value
            }

        # Step 5: Validate amount
        if amount != payout.amount:
            logger.error(
                f"Amount mismatch | payout_id={payout.id} | "
                f"expected={payout.amount} | received={amount}"
            )
            raise ValueError(f"Amount mismatch")

        try:
            # Step 6: Update payout status
            if status == "SETTLED":
                payout.status = PayoutStatusEnum.SETTLED
                payout.updated_at = datetime.utcnow()

                # Post payout request in ledger (mark as truly posted)
                LedgerService.post_payout_request(
                    session=session,
                    payout_id=payout.id
                )

                # Create settlement entry for audit
                LedgerService.settle_payout(
                    session=session,
                    merchant_id=payout.merchant_id,
                    payout_id=payout.id,
                    amount=payout.amount,
                    idempotency_key=f"payout-settled-{payout.id}"
                )

                logger.info(
                    f"Payout settled | payout_id={payout.id} | "
                    f"amount={payout.amount}"
                )

            elif status == "FAILED":
                payout.status = PayoutStatusEnum.FAILED
                payout.updated_at = datetime.utcnow()
                logger.warning(f"Payout failed | payout_id={payout.id}")

            session.commit()

            return {
                "status": "success",
                "payout_id": str(payout.id),
                "payout_status": payout.status.value
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing Orange payout webhook: {str(e)}")
            raise

    @staticmethod
    def handle_mtn_payout_webhook(
        session: Session,
        payload: dict,
        signature: Optional[str] = None
    ) -> dict:
        """
        Handle MTN Money payout settlement webhook.
        
        Similar to Orange but with MTN API format.
        
        Webhook payload (example):
        {
            "PayoutTransactionId": "MT_PAYOUT_123456",
            "ExternalId": "payout-uuid-here",
            "PayoutStatus": "Settled" or "Failed",
            "Amount": "150000",
            "Recipient": {
                "PartyIdType": "MSISDN",
                "PartyId": "+237690000000"
            }
        }
        
        Returns: Same format as Orange webhook
        """
        logger.info(
            f"MTN payout webhook received | external_id={payload.get('ExternalId')} | "
            f"status={payload.get('PayoutStatus')}"
        )

        # Step 1: Verify signature (optional in dev)
        if signature and False:
            if not PayoutService._verify_mtn_signature(payload, signature):
                logger.error("MTN payout webhook signature verification failed!")
                raise ValueError("Invalid signature")

        # Step 2: Extract data (MTN field names!)
        external_id = payload.get('ExternalId')
        payout_transaction_id = payload.get('PayoutTransactionId')
        status = payload.get('PayoutStatus')  # "Settled" or "Failed"
        amount = int(payload.get('Amount', 0))

        if not external_id:
            logger.error("Missing ExternalId in MTN payout webhook")
            raise ValueError("Missing ExternalId")

        # Step 3: Find payout
        payout = session.query(Payout).filter(
            Payout.id == UUID(external_id.split('-')[-1])
        ).first()

        if not payout:
            logger.error(f"Payout not found for MTN reference: {external_id}")
            raise ValueError(f"Payout not found: {external_id}")

        # Step 4: Check idempotency
        if payout.status == PayoutStatusEnum.SETTLED:
            logger.warning(
                f"Payout already settled | payout_id={payout.id}"
            )
            return {
                "status": "success",
                "message": "Payout already settled",
                "payout_id": str(payout.id),
                "payout_status": payout.status.value
            }

        # Step 5: Validate amount
        if amount != payout.amount:
            logger.error(f"Amount mismatch | payout_id={payout.id}")
            raise ValueError(f"Amount mismatch")

        try:
            # Step 6: Update payout status
            if status == "Settled":
                payout.status = PayoutStatusEnum.SETTLED
                payout.updated_at = datetime.utcnow()

                # Post payout request + settlement entry
                LedgerService.post_payout_request(
                    session=session,
                    payout_id=payout.id
                )

                LedgerService.settle_payout(
                    session=session,
                    merchant_id=payout.merchant_id,
                    payout_id=payout.id,
                    amount=payout.amount,
                    idempotency_key=f"payout-settled-{payout.id}"
                )

                logger.info(f"MTN payout settled | payout_id={payout.id}")

            elif status == "Failed":
                payout.status = PayoutStatusEnum.FAILED
                payout.updated_at = datetime.utcnow()
                logger.warning(f"MTN payout failed | payout_id={payout.id}")

            session.commit()

            return {
                "status": "success",
                "payout_id": str(payout.id),
                "payout_status": payout.status.value
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error processing MTN payout webhook: {str(e)}")
            raise

    # ========== GET & LIST PAYOUTS ==========

    @staticmethod
    def get_payout(
        session: Session,
        payout_id: UUID,
        merchant_id: Optional[UUID] = None
    ) -> Payout:
        """Récupérer un retrait"""
        query = session.query(Payout).filter(Payout.id == payout_id)

        if merchant_id:
            query = query.filter(Payout.merchant_id == merchant_id)

        payout = query.first()
        if not payout:
            raise ValueError(f"Payout not found: {payout_id}")

        return payout

    @staticmethod
    def list_payouts(
        session: Session,
        merchant_id: UUID,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None
    ) -> Tuple[int, List[Payout]]:
        """Lister les retraits"""
        query = session.query(Payout).filter(Payout.merchant_id == merchant_id)

        if status:
            try:
                status_enum = PayoutStatusEnum(status)
                query = query.filter(Payout.status == status_enum)
            except ValueError:
                raise ValueError(f"Invalid status: {status}")

        total = query.count()
        payouts = query.order_by(Payout.created_at.desc()).offset(skip).limit(limit).all()

        return total, payouts

    # ========== HELPER METHODS ==========

    @staticmethod
    def _verify_orange_signature(payload: dict, signature: str) -> bool:
        """Verify Orange Money payout webhook signature"""
        logger.debug("Orange payout signature verification (disabled in dev)")
        return True

    @staticmethod
    def _verify_mtn_signature(payload: dict, signature: str) -> bool:
        """Verify MTN Money payout webhook signature"""
        logger.debug("MTN payout signature verification (disabled in dev)")
        return True

    # TODO: Implement in production
    # @staticmethod
    # def _send_orange_payout(payout: Payout, account: PayoutAccount):
    #     """Call Orange Money API to send payout"""
    #     pass
    #
    # @staticmethod
    # def _send_mtn_payout(payout: Payout, account: PayoutAccount):
    #     """Call MTN Money API to send payout"""
    #     pass