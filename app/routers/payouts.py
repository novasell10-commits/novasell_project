"""
Payout Routes
Location: app/routers/payouts.py

Endpoints pour gérer les retraits:
  POST /payouts → Demander retrait
  GET /payouts → Lister retraits
  GET /payouts/{id} → Détail retrait
  POST /payout-accounts → Créer compte retrait
  GET /payout-accounts → Lister comptes retrait
  GET /payout-accounts/{id} → Détail compte
  DELETE /payout-accounts/{id} → Désactiver compte
  POST /payouts/webhook/orange → Webhook Orange
  POST /payouts/webhook/mtn → Webhook MTN
"""

import logging
from typing import Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middlewares import get_current_merchant
from app.models import Merchant
from app.services.payout_service import PayoutService
from app.services.ledger_service import LedgerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["payouts"])


# ========== SCHEMAS ==========

class CreatePayoutAccountRequest(BaseModel):
    """Request schema for creating payout account"""
    operator: str = Field(..., description="ORANGE_MONEY or MTN_MONEY")
    phone: str = Field(..., description="E.164 format: +237...")


class RequestPayoutRequest(BaseModel):
    """Request schema for requesting payout"""
    amount: int = Field(..., ge=1, description="Amount in centimes")
    account_id: str = Field(..., description="Payout account UUID")


class PayoutAccountResponse(BaseModel):
    """Response schema for payout account"""
    id: str
    operator: str
    phone: str
    is_active: bool
    country: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_model(account):
        return PayoutAccountResponse(
            id=str(account.id),
            operator=account.operator.value,
            phone=account.phone,
            is_active=account.is_active,
            country=account.country,
            created_at=account.created_at.isoformat(),
            updated_at=account.updated_at.isoformat()
        )


class PayoutResponse(BaseModel):
    """Response schema for payout"""
    id: str
    amount: int
    status: str
    provider_reference: Optional[str]
    account_id: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_model(payout):
        return PayoutResponse(
            id=str(payout.id),
            amount=payout.amount,
            status=payout.status.value,
            provider_reference=payout.provider_reference,
            account_id=str(payout.payout_account_id),
            created_at=payout.created_at.isoformat(),
            updated_at=payout.updated_at.isoformat()
        )


# ========== PAYOUT ACCOUNT ENDPOINTS ==========

@router.post("/payout-accounts", status_code=201)
async def create_payout_account(
    req: CreatePayoutAccountRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Créer un compte de retrait pour le merchant.
    
    Max 2 comptes actifs par merchant.
    
    Request:
        {
            "operator": "ORANGE_MONEY",
            "phone": "+237690000000"
        }
    
    Response (201):
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "operator": "ORANGE_MONEY",
                "phone": "+237690000000",
                "is_active": true
            }
        }
    """
    try:
        account = PayoutService.create_payout_account(
            session=db,
            merchant_id=current_merchant.id,
            operator=req.operator,
            phone=req.phone
        )

        return {
            "status": "success",
            "data": PayoutAccountResponse.from_model(account).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Payout account creation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating payout account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payout-accounts")
async def list_payout_accounts(
    active_only: bool = Query(True),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Lister les comptes de retrait du merchant.
    
    Response:
        {
            "status": "success",
            "accounts": [
                {
                    "id": "uuid...",
                    "operator": "ORANGE_MONEY",
                    "phone": "+237690000000",
                    "is_active": true
                },
                ...
            ]
        }
    """
    try:
        accounts = PayoutService.list_payout_accounts(
            db,
            current_merchant.id,
            active_only=active_only
        )

        return {
            "status": "success",
            "total": len(accounts),
            "accounts": [PayoutAccountResponse.from_model(a).dict() for a in accounts],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing payout accounts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payout-accounts/{account_id}")
async def get_payout_account(
    account_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """Récupérer détail d'un compte de retrait"""
    try:
        account_id_parsed = UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account_id format")

    try:
        account = PayoutService.get_payout_account(
            db,
            account_id_parsed,
            current_merchant.id
        )

        return {
            "status": "success",
            "data": PayoutAccountResponse.from_model(account).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting payout account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/payout-accounts/{account_id}", status_code=200)
async def deactivate_payout_account(
    account_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """Désactiver un compte de retrait"""
    try:
        account_id_parsed = UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account_id format")

    try:
        account = PayoutService.deactivate_payout_account(
            db,
            account_id_parsed,
            current_merchant.id
        )

        return {
            "status": "success",
            "message": "Payout account deactivated",
            "data": PayoutAccountResponse.from_model(account).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deactivating payout account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== PAYOUT ENDPOINTS ==========

@router.post("/payouts", status_code=201)
async def request_payout(
    req: RequestPayoutRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Demander un retrait.
    
    ⭐ CRITICAL: Valide la balance avant de créer le payout!
    
    Request:
        {
            "amount": 150000,
            "account_id": "uuid..."
        }
    
    Response (201):
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "amount": 150000,
                "status": "REQUESTED",
                "account_id": "uuid..."
            },
            "message": "Payout requested, funds reserved"
        }
    """
    try:
        account_id_parsed = UUID(req.account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid account_id format")

    try:
        payout = PayoutService.request_payout(
            session=db,
            merchant_id=current_merchant.id,
            amount=req.amount,
            account_id=account_id_parsed
        )

        # Get updated balance
        balance = LedgerService.calculate_balance(db, current_merchant.id)

        return {
            "status": "success",
            "data": PayoutResponse.from_model(payout).dict(),
            "message": "Payout requested, funds reserved",
            "balance_after": balance,
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Payout request error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error requesting payout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payouts")
async def list_payouts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    order_by: str = Query("created_at_desc"),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Lister les retraits du merchant.
    
    Query params:
        skip: Pagination offset
        limit: Limit (max 100)
        status: Filter by status (REQUESTED, PROCESSING, SETTLED, etc.)
        order_by: Sort (created_at_desc, created_at_asc, amount_desc, etc.)
    """
    try:
        total, payouts = PayoutService.list_payouts(
            db,
            current_merchant.id,
            skip=skip,
            limit=limit,
            status=status,
            order_by=order_by
        )

        return {
            "status": "success",
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": [PayoutResponse.from_model(p).dict() for p in payouts],
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Payout listing error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing payouts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payouts/{payout_id}")
async def get_payout(
    payout_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """Récupérer détail d'un payout"""
    try:
        payout_id_parsed = UUID(payout_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payout_id format")

    try:
        payout = PayoutService.get_payout(
            db,
            payout_id_parsed,
            current_merchant.id
        )

        return {
            "status": "success",
            "data": PayoutResponse.from_model(payout).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting payout: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== WEBHOOKS ==========

@router.post("/payouts/webhook/orange")
async def orange_payout_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook Orange Money - Payout settled.
    
    ⚠️ NOT authenticated! Called by Orange's servers.
    
    Orange will POST:
        {
            "payout_id": "OP123456789",
            "merchant_reference": "payout-uuid",
            "status": "SUCCESS",
            "amount": 150000,
            "recipient_phone": "+237690000000"
        }
    
    Must be idempotent!
    """
    try:
        payload = await request.json()
        logger.info(f"Orange payout webhook received")

        result = PayoutService.handle_orange_payout_webhook(
            session=db,
            payload=payload,
            signature=request.headers.get('X-Signature')
        )

        return result

    except ValueError as e:
        logger.warning(f"Orange payout webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing Orange payout webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payouts/webhook/mtn")
async def mtn_payout_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook MTN Money - Payout settled.
    
    ⚠️ NOT authenticated! Called by MTN's servers.
    
    MTN will POST:
        {
            "TransactionId": "MT123456789",
            "ExternalId": "payout-uuid",
            "TransactionStatus": "Succeeded",
            "Amount": "150000",
            "Payee": {...}
        }
    
    Must be idempotent!
    """
    try:
        payload = await request.json()
        logger.info(f"MTN payout webhook received")

        result = PayoutService.handle_mtn_payout_webhook(
            session=db,
            payload=payload,
            signature=request.headers.get('X-Signature')
        )

        return result

    except ValueError as e:
        logger.warning(f"MTN payout webhook error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing MTN payout webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
