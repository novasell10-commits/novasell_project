"""
Ledger Service for NovaSell
Location: app/services/ledger_service.py

Source of truth for all financial transactions.
All balance changes MUST go through ledger entries (never direct updates).

Core Rules:
  1. NEVER update balance directly → ALWAYS create ledger entries
  2. NEVER delete entries → ALWAYS create reversals
  3. ALWAYS idempotency_key unique (prevents double-charging)
  4. ALWAYS DB transactions atomiques
  5. ALWAYS validate available balance before operations

Financial Flow:
  Order Created       → ESCROW_HOLD (+amount, PENDING)
  Payment Received    → ESCROW_HOLD (POSTED)
  Order Confirmed     → ESCROW_RELEASE (-amount) + MERCHANT_CREDIT (+amount) [ATOMIC]
  Payout Requested    → PAYOUT_REQUEST (-amount, PENDING)
  Payout Settled      → PAYOUT_REQUEST (POSTED)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
from uuid import UUID
import uuid

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import (
    LedgerEntry, LedgerTypeEnum, LedgerStatusEnum,
    Order, OrderStatusEnum,
    Payout, PayoutStatusEnum,
    Merchant
)

logger = logging.getLogger(__name__)


class LedgerService:
    """
    Service for managing ledger entries and merchant balances.
    
    All financial operations flow through here:
    - Escrow holds (when order created)
    - Escrow releases (when customer confirms)
    - Merchant credits (when escrow released)
    - Payout requests (when seller requests withdrawal)
    - Payout settlements (when money sent)
    - Refunds (when order cancelled)
    """

    # ========== ESCROW OPERATIONS ==========

    @staticmethod
    def create_escrow_hold(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str
    ) -> LedgerEntry:
        """
        Place funds in escrow when order is created.
        
        Args:
            session: DB session
            merchant_id: Seller ID
            order_id: Order ID
            amount: Amount to hold (in centimes)
            idempotency_key: Unique key to prevent double-charging
        
        Returns:
            LedgerEntry created
        
        Raises:
            IntegrityError: If idempotency_key already exists
        
        Flow:
            1. Create ESCROW_HOLD entry (PENDING)
            2. Entry is counted towards ESCROW balance
            3. When posted, customer can't refund it anymore
        """
        logger.info(
            f"Creating escrow hold | merchant={merchant_id} | "
            f"order={order_id} | amount={amount} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            type=LedgerTypeEnum.ESCROW_HOLD,
            amount=amount,  # Positive for hold
            status=LedgerStatusEnum.PENDING,
            idempotency_key=idempotency_key,
            metadata={"reason": "Order created"}
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Escrow hold created | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Escrow hold already created for this order. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    @staticmethod
    def post_escrow_hold(
        session: Session,
        order_id: UUID
    ) -> LedgerEntry:
        """
        Post (confirm) escrow hold after payment received.
        
        Escrow funds are now "locked" and customer must confirm delivery
        before merchant can access them.
        """
        logger.info(f"Posting escrow hold | order={order_id}")

        entry = session.query(LedgerEntry).filter(
            and_(
                LedgerEntry.order_id == order_id,
                LedgerEntry.type == LedgerTypeEnum.ESCROW_HOLD,
                LedgerEntry.status == LedgerStatusEnum.PENDING
            )
        ).first()

        if not entry:
            raise ValueError(f"No pending escrow hold for order {order_id}")

        entry.status = LedgerStatusEnum.POSTED
        entry.metadata = {**(entry.metadata or {}), "posted_at": datetime.utcnow().isoformat()}
        session.flush()

        logger.info(f"Escrow hold posted | entry_id={entry.id}")
        return entry

    @staticmethod
    def release_escrow(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str
    ) -> LedgerEntry:
        """
        Release escrow funds when customer confirms delivery.
        
        This creates a NEGATIVE escrow entry to offset the hold.
        Funds are removed from ESCROW but NOT yet available (see credit_merchant).
        
        Flow:
            1. ESCROW_HOLD (+50000) was POSTED
            2. Customer confirms
            3. ESCROW_RELEASE (-50000) is created
            4. Net escrow = 0
            5. MERCHANT_CREDIT (+50000) makes it available
        """
        logger.info(
            f"Releasing escrow | merchant={merchant_id} | order={order_id} | "
            f"amount={amount} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            type=LedgerTypeEnum.ESCROW_RELEASE,
            amount=-amount,  # Negative to offset hold
            status=LedgerStatusEnum.POSTED,
            idempotency_key=idempotency_key,
            metadata={"reason": "Customer confirmed delivery"}
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Escrow released | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Escrow already released for this order. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    # ========== MERCHANT CREDIT OPERATIONS ==========

    @staticmethod
    def credit_merchant(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str
    ) -> LedgerEntry:
        """
        Credit merchant account after escrow is released.
        
        This makes funds AVAILABLE for withdrawal.
        
        CRITICAL: This MUST be called atomically with release_escrow().
        Use create_escrow_release_and_credit() instead!
        
        Flow:
            1. Escrow released (funds out of escrow)
            2. Merchant credited (funds available)
            3. Merchant can now request payout
        """
        logger.info(
            f"Crediting merchant | merchant={merchant_id} | order={order_id} | "
            f"amount={amount} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            type=LedgerTypeEnum.MERCHANT_CREDIT,
            amount=amount,  # Positive, available for withdrawal
            status=LedgerStatusEnum.POSTED,
            idempotency_key=idempotency_key,
            metadata={"reason": "Escrow released, credited to merchant"}
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Merchant credited | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Merchant already credited for this escrow release. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    @staticmethod
    def create_escrow_release_and_credit(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        amount: int,  # in centimes
    ) -> Tuple[LedgerEntry, LedgerEntry]:
        """
        Atomically release escrow AND credit merchant.
        
        This is the ONLY correct way to confirm an order financially.
        Both entries use the same idempotency key base to ensure atomicity.
        
        Returns:
            Tuple of (escrow_release_entry, credit_entry)
        
        Raises:
            ValueError: If escrow release already exists or amount mismatch
        """
        logger.info(
            f"Atomic escrow release + credit | merchant={merchant_id} | "
            f"order={order_id} | amount={amount}"
        )

        # Verify escrow hold exists and is POSTED
        hold = session.query(LedgerEntry).filter(
            and_(
                LedgerEntry.order_id == order_id,
                LedgerEntry.type == LedgerTypeEnum.ESCROW_HOLD,
                LedgerEntry.status == LedgerStatusEnum.POSTED
            )
        ).first()

        if not hold:
            raise ValueError(
                f"No posted escrow hold for order {order_id}. "
                f"Cannot confirm without payment."
            )

        if hold.amount != amount:
            raise ValueError(
                f"Amount mismatch for order {order_id}. "
                f"Hold: {hold.amount}, trying to confirm: {amount}"
            )

        # Create both entries with same idempotency base
        idempotency_base = f"order-confirm-{order_id}-{datetime.utcnow().timestamp()}"

        try:
            # 1. Release escrow
            release = LedgerService.release_escrow(
                session=session,
                merchant_id=merchant_id,
                order_id=order_id,
                amount=amount,
                idempotency_key=f"{idempotency_base}-release"
            )

            # 2. Credit merchant
            credit = LedgerService.credit_merchant(
                session=session,
                merchant_id=merchant_id,
                order_id=order_id,
                amount=amount,
                idempotency_key=f"{idempotency_base}-credit"
            )

            session.flush()  # Ensure both are flushed
            logger.info(
                f"Atomic operation successful | "
                f"release_entry={release.id} | credit_entry={credit.id}"
            )
            return (release, credit)

        except Exception as e:
            session.rollback()
            logger.error(f"Atomic operation failed | error={str(e)}")
            raise

    # ========== PAYOUT OPERATIONS ==========

    @staticmethod
    def create_payout_request(
        session: Session,
        merchant_id: UUID,
        payout_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str
    ) -> LedgerEntry:
        """
        Create payout request when merchant asks to withdraw funds.
        
        This RESERVES funds (moves from AVAILABLE to PENDING).
        Merchant cannot spend pending funds.
        
        CRITICAL: Must validate available balance BEFORE this call!
        Use PayoutService.validate_balance() first.
        """
        logger.info(
            f"Creating payout request | merchant={merchant_id} | payout={payout_id} | "
            f"amount={amount} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            type=LedgerTypeEnum.PAYOUT_REQUEST,
            amount=-amount,  # Negative: deduct from available
            status=LedgerStatusEnum.PENDING,
            idempotency_key=idempotency_key,
            metadata={
                "payout_id": str(payout_id),
                "reason": "Merchant requested payout"
            }
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Payout request created | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Payout request already created. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    @staticmethod
    def post_payout_request(
        session: Session,
        payout_id: UUID
    ) -> LedgerEntry:
        """
        Post payout request after payment sent to merchant.
        
        Funds are now truly gone from account.
        """
        logger.info(f"Posting payout request | payout={payout_id}")

        entry = session.query(LedgerEntry).filter(
            and_(
                LedgerEntry.metadata["payout_id"].astext == str(payout_id),
                LedgerEntry.type == LedgerTypeEnum.PAYOUT_REQUEST,
                LedgerEntry.status == LedgerStatusEnum.PENDING
            )
        ).first()

        if not entry:
            raise ValueError(f"No pending payout request for payout {payout_id}")

        entry.status = LedgerStatusEnum.POSTED
        entry.metadata = {**(entry.metadata or {}), "posted_at": datetime.utcnow().isoformat()}
        session.flush()

        logger.info(f"Payout request posted | entry_id={entry.id}")
        return entry

    @staticmethod
    def settle_payout(
        session: Session,
        merchant_id: UUID,
        payout_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str
    ) -> LedgerEntry:
        """
        Record successful payout settlement.
        
        Creates PAYOUT_SETTLED entry to record the transaction.
        This is purely informational (amount already deducted by PAYOUT_REQUEST).
        """
        logger.info(
            f"Settling payout | merchant={merchant_id} | payout={payout_id} | "
            f"amount={amount} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            type=LedgerTypeEnum.PAYOUT_SETTLED,
            amount=0,  # Already deducted by PAYOUT_REQUEST, this is just logging
            status=LedgerStatusEnum.POSTED,
            idempotency_key=idempotency_key,
            metadata={
                "payout_id": str(payout_id),
                "original_amount": amount,
                "reason": "Payout successfully settled"
            }
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Payout settled | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Payout already settled. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    # ========== REFUND OPERATIONS ==========

    @staticmethod
    def create_refund(
        session: Session,
        merchant_id: UUID,
        order_id: UUID,
        amount: int,  # in centimes
        idempotency_key: str,
        reason: str = "Order cancelled"
    ) -> LedgerEntry:
        """
        Process refund when order is cancelled.
        
        Two scenarios:
        1. Escrow still held: Release escrow, customer gets refunded
        2. Already credited: Deduct from merchant (only if merchant agreed)
        
        CRITICAL: Only call this if refund is legitimately requested!
        """
        logger.info(
            f"Creating refund | merchant={merchant_id} | order={order_id} | "
            f"amount={amount} | reason={reason} | idempotency={idempotency_key}"
        )

        entry = LedgerEntry(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            order_id=order_id,
            type=LedgerTypeEnum.REFUND,
            amount=-amount,  # Negative: money goes back
            status=LedgerStatusEnum.POSTED,
            idempotency_key=idempotency_key,
            metadata={
                "reason": reason,
                "order_id": str(order_id)
            }
        )

        session.add(entry)
        try:
            session.flush()
            logger.info(f"Refund created | entry_id={entry.id}")
            return entry
        except IntegrityError as e:
            session.rollback()
            logger.error(f"Idempotency key duplicate | key={idempotency_key}")
            raise ValueError(
                f"Refund already processed for this order. "
                f"Idempotency key: {idempotency_key}"
            ) from e

    # ========== BALANCE CALCULATIONS ==========

    @staticmethod
    def calculate_balance(
        session: Session,
        merchant_id: UUID
    ) -> Dict[str, int]:
        """
        Calculate merchant balance from ledger entries.
        
        Returns:
            {
                "available": <amount>,      # Can withdraw
                "pending": <amount>,        # Waiting for payout
                "escrow": <amount>,         # In customer escrow
                "total": <amount>           # All money
            }
        
        Calculation:
            AVAILABLE = SUM(MERCHANT_CREDIT POSTED) - SUM(PAYOUT_REQUEST POSTED)
            PENDING = SUM(PAYOUT_REQUEST PENDING)
            ESCROW = SUM(ESCROW_HOLD POSTED) - SUM(ESCROW_RELEASE POSTED)
            TOTAL = AVAILABLE + PENDING + ESCROW
        """
        logger.debug(f"Calculating balance | merchant={merchant_id}")

        entries = session.query(LedgerEntry).filter(
            LedgerEntry.merchant_id == merchant_id
        ).all()

        available = 0
        pending = 0
        escrow = 0

        for entry in entries:
            # AVAILABLE: Posted merchant credits and payouts deducted
            if entry.type == LedgerTypeEnum.MERCHANT_CREDIT and entry.status == LedgerStatusEnum.POSTED:
                available += entry.amount

            if entry.type == LedgerTypeEnum.PAYOUT_REQUEST and entry.status == LedgerStatusEnum.POSTED:
                available += entry.amount  # Already negative

            # PENDING: Unposted payout requests
            if entry.type == LedgerTypeEnum.PAYOUT_REQUEST and entry.status == LedgerStatusEnum.PENDING:
                pending += abs(entry.amount)  # Make positive for clarity

            # ESCROW: Posted holds minus releases
            if entry.type == LedgerTypeEnum.ESCROW_HOLD and entry.status == LedgerStatusEnum.POSTED:
                escrow += entry.amount

            if entry.type == LedgerTypeEnum.ESCROW_RELEASE and entry.status == LedgerStatusEnum.POSTED:
                escrow += entry.amount  # Already negative

            # Refunds reduce available
            if entry.type == LedgerTypeEnum.REFUND and entry.status == LedgerStatusEnum.POSTED:
                available += entry.amount  # Already negative

        total = available + pending + escrow

        logger.debug(
            f"Balance calculated | merchant={merchant_id} | "
            f"available={available} | pending={pending} | escrow={escrow} | total={total}"
        )

        return {
            "available": available,
            "pending": pending,
            "escrow": escrow,
            "total": total,
            "currency": "XOF"
        }

    @staticmethod
    def get_balance_details(
        session: Session,
        merchant_id: UUID
    ) -> Dict:
        """
        Get detailed balance breakdown with all ledger entries.
        
        Returns full audit trail for debugging/reporting.
        """
        balance = LedgerService.calculate_balance(session, merchant_id)

        entries = session.query(LedgerEntry).filter(
            LedgerEntry.merchant_id == merchant_id
        ).order_by(LedgerEntry.created_at.desc()).all()

        return {
            "merchant_id": str(merchant_id),
            "balance": balance,
            "entries_count": len(entries),
            "entries": [
                {
                    "id": str(e.id),
                    "type": e.type.value,
                    "amount": e.amount,
                    "status": e.status.value,
                    "order_id": str(e.order_id) if e.order_id else None,
                    "created_at": e.created_at.isoformat(),
                    "metadata": e.metadata
                }
                for e in entries[:50]  # Last 50 entries
            ]
        }

    # ========== VALIDATION HELPERS ==========

    @staticmethod
    def validate_available_balance(
        session: Session,
        merchant_id: UUID,
        amount: int
    ) -> bool:
        """
        Check if merchant has enough available balance.
        
        Args:
            session: DB session
            merchant_id: Merchant ID
            amount: Amount to check (in centimes)
        
        Returns:
            True if balance >= amount
        
        Raises:
            ValueError: If balance < amount
        """
        balance = LedgerService.calculate_balance(session, merchant_id)
        available = balance.get("available", 0)

        if available < amount:
            raise ValueError(
                f"Insufficient balance. Available: {available} centimes, "
                f"requested: {amount} centimes"
            )

        logger.info(
            f"Balance validation passed | merchant={merchant_id} | "
            f"available={available} | requested={amount}"
        )
        return True

    @staticmethod
    def get_ledger_entries(
        session: Session,
        merchant_id: UUID,
        skip: int = 0,
        limit: int = 50,
        entry_type: Optional[str] = None,
        status: Optional[str] = None,
        order_id: Optional[UUID] = None
    ) -> Tuple[int, list]:
        """
        Get ledger entries with optional filters.
        
        Returns:
            (total_count, entries)
        """
        query = session.query(LedgerEntry).filter(
            LedgerEntry.merchant_id == merchant_id
        )

        if entry_type:
            query = query.filter(LedgerEntry.type == LedgerTypeEnum(entry_type))

        if status:
            query = query.filter(LedgerEntry.status == LedgerStatusEnum(status))

        if order_id:
            query = query.filter(LedgerEntry.order_id == order_id)

        total = query.count()
        entries = query.order_by(LedgerEntry.created_at.desc()).offset(skip).limit(limit).all()

        return total, entries


class BalanceService:
    """
    Companion service for balance queries.
    Provides read-only balance information (uses LedgerService internally).
    """

    @staticmethod
    def get_merchant_balance(session: Session, merchant_id: UUID) -> Dict[str, int]:
        """Get current merchant balance."""
        return LedgerService.calculate_balance(session, merchant_id)

    @staticmethod
    def get_balance_history(
        session: Session,
        merchant_id: UUID,
        days: int = 30
    ) -> list:
        """
        Get balance history for the last N days.
        Useful for charts/dashboards.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        entries = session.query(LedgerEntry).filter(
            and_(
                LedgerEntry.merchant_id == merchant_id,
                LedgerEntry.created_at >= cutoff_date
            )
        ).order_by(LedgerEntry.created_at.asc()).all()

        # Build daily balance snapshots
        daily_balances = {}
        running_balance = 0

        for entry in entries:
            date_key = entry.created_at.date().isoformat()

            if entry.status == LedgerStatusEnum.POSTED:
                running_balance += entry.amount

            if date_key not in daily_balances:
                daily_balances[date_key] = running_balance

        return [
            {"date": date, "balance": balance}
            for date, balance in sorted(daily_balances.items())
        ]