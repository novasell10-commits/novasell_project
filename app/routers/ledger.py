"""
Ledger & Balance Routes
Location: app/routers/ledger.py

Endpoints pour:
  - Consulter le ledger (audit trail)
  - Voir la balance détaillée
  - Voir l'historique de balance
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.database import get_db
from app.middlewares import get_current_merchant
from app.services.ledger_service import LedgerService, BalanceService
from app.models import Merchant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["ledger"])


# ========== SCHEMAS ==========

class LedgerEntryResponse:
    """Response schema for ledger entry"""
    def __init__(self, entry):
        self.id = str(entry.id)
        self.merchant_id = str(entry.merchant_id)
        self.order_id = str(entry.order_id) if entry.order_id else None
        self.type = entry.type.value
        self.amount = entry.amount
        self.status = entry.status.value
        self.idempotency_key = entry.idempotency_key
        self.metadata = entry.metadata
        self.created_at = entry.created_at.isoformat()

    def dict(self):
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "order_id": self.order_id,
            "type": self.type,
            "amount": self.amount,
            "status": self.status,
            "idempotency_key": self.idempotency_key,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


# ========== ENDPOINTS ==========

@router.get("/balance")
async def get_balance(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Get current merchant balance.
    
    Returns:
        {
            "available": 150000,      # 1500 XOF - can withdraw
            "pending": 50000,         # 500 XOF - waiting for payout
            "escrow": 75000,          # 750 XOF - in customer escrow
            "total": 275000,          # 2750 XOF - all money
            "currency": "XOF"
        }
    """
    try:
        balance = LedgerService.calculate_balance(db, current_merchant.id)
        
        return {
            "status": "success",
            "merchant_id": str(current_merchant.id),
            "balance": balance,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching balance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance/details")
async def get_balance_details(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Get detailed balance with full ledger entry breakdown.
    
    Includes last 50 ledger entries for audit trail.
    """
    try:
        details = LedgerService.get_balance_details(db, current_merchant.id)
        
        return {
            "status": "success",
            "data": details,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching balance details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balance/history")
async def get_balance_history(
    days: int = Query(30, ge=1, le=365),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Get balance history for the last N days.
    
    Useful for charts and dashboards showing balance trends.
    
    Query params:
        days: Number of days to look back (default: 30, max: 365)
    
    Returns:
        [{
            "date": "2026-05-03",
            "balance": 150000
        }, ...]
    """
    try:
        history = BalanceService.get_balance_history(db, current_merchant.id, days=days)
        
        return {
            "status": "success",
            "merchant_id": str(current_merchant.id),
            "days": days,
            "history": history,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching balance history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ledger")
async def get_ledger(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    entry_type: Optional[str] = Query(None),  # ESCROW_HOLD, MERCHANT_CREDIT, etc.
    status: Optional[str] = Query(None),      # PENDING, POSTED, REVERSED
    order_id: Optional[str] = Query(None),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Get ledger entries for this merchant.
    
    This is the AUDIT TRAIL - shows all financial transactions.
    
    Query params:
        skip: Pagination offset (default: 0)
        limit: Number of entries (default: 50, max: 100)
        entry_type: Filter by type (ESCROW_HOLD, ESCROW_RELEASE, MERCHANT_CREDIT, etc.)
        status: Filter by status (PENDING, POSTED, REVERSED)
        order_id: Filter by specific order
    
    Response:
        {
            "total": 150,
            "skip": 0,
            "limit": 50,
            "items": [
                {
                    "id": "uuid...",
                    "type": "MERCHANT_CREDIT",
                    "amount": 50000,
                    "status": "POSTED",
                    "order_id": "uuid...",
                    "created_at": "2026-05-03T10:30:00.000000",
                    "metadata": {...}
                },
                ...
            ]
        }
    """
    try:
        order_id_parsed = None
        if order_id:
            try:
                order_id_parsed = UUID(order_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid order_id format")

        total, entries = LedgerService.get_ledger_entries(
            db,
            merchant_id=current_merchant.id,
            skip=skip,
            limit=limit,
            entry_type=entry_type,
            status=status,
            order_id=order_id_parsed
        )

        return {
            "status": "success",
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": [LedgerEntryResponse(e).dict() for e in entries],
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching ledger: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ledger/summary")
async def get_ledger_summary(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics for ledger.
    
    Useful for dashboards showing counts of each type.
    """
    try:
        total, _ = LedgerService.get_ledger_entries(db, current_merchant.id, limit=1)
        
        # Count by type
        all_entries = db.query(db.query(db.models.LedgerEntry).filter(
            db.models.LedgerEntry.merchant_id == current_merchant.id
        ).all())

        counts_by_type = {}
        for entry in all_entries:
            entry_type = entry.type.value
            counts_by_type[entry_type] = counts_by_type.get(entry_type, 0) + 1

        counts_by_status = {}
        for entry in all_entries:
            entry_status = entry.status.value
            counts_by_status[entry_status] = counts_by_status.get(entry_status, 0) + 1

        return {
            "status": "success",
            "merchant_id": str(current_merchant.id),
            "total_entries": total,
            "by_type": counts_by_type,
            "by_status": counts_by_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching ledger summary: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== HEALTH CHECK FOR LEDGER ==========

@router.post("/ledger/test-entry")
async def test_ledger_entry(
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Test endpoint to create a test ledger entry.
    
    WARNING: Only use for testing/debugging!
    
    Creates a small test entry to verify ledger is working.
    """
    if True:  # In production, check DEBUG mode
        raise HTTPException(status_code=403, detail="Test endpoint disabled in production")

    try:
        import uuid as uuid_module
        test_idempotency_key = f"test-{uuid_module.uuid4()}"
        
        from app.models import LedgerTypeEnum
        entry = LedgerService.create_escrow_hold(
            db,
            merchant_id=current_merchant.id,
            order_id=uuid_module.uuid4(),
            amount=1000,  # 10 XOF
            idempotency_key=test_idempotency_key
        )
        
        db.commit()

        return {
            "status": "success",
            "message": "Test entry created",
            "entry_id": str(entry.id),
            "amount": entry.amount
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating test entry: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))