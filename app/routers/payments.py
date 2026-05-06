"""
Payment Routes
Location: app/routers/payments.py

Endpoints pour gérer les paiements:
  POST   /payments                    → Créer payment request
  GET    /payments/{id}               → Récupérer paiement
  GET    /orders/{id}/payment         → Paiement d'une commande
  POST   /payments/webhook/orange     → Webhook Orange Money
  POST   /payments/webhook/mtn        → Webhook MTN Money
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
from app.services.payment_service import PaymentService
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["payments"])


# ========== SCHEMAS ==========

class CreatePaymentRequest(BaseModel):
    """Request schema for creating payment"""
    order_id: str = Field(..., description="Order UUID")
    provider: str = Field(..., description="ORANGE_MONEY or MTN_MONEY")


class PaymentResponse(BaseModel):
    """Response schema for payment"""
    id: str
    order_id: str
    provider: str
    status: str
    amount: int
    currency: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_model(payment):
        return PaymentResponse(
            id=str(payment.id),
            order_id=str(payment.order_id),
            provider=payment.provider.value,
            status=payment.status.value,
            amount=payment.amount,
            currency=payment.currency,
            created_at=payment.created_at.isoformat(),
            updated_at=payment.updated_at.isoformat()
        )


# ========== ENDPOINTS ==========

@router.post("/payments", status_code=201)
async def create_payment(
    req: CreatePaymentRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Créer une demande de paiement pour une commande.
    
    Flow:
        1. Valide la commande existe et appartient au merchant
        2. Crée une entrée Payment (PENDING)
        3. Appelle provider API pour initier paiement
        4. Customer reçoit SMS/USSD pour payer
        5. Retourne détail paiement
    
    Request:
        {
            "order_id": "uuid...",
            "provider": "ORANGE_MONEY"
        }
    
    Response (201):
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "order_id": "uuid...",
                "provider": "ORANGE_MONEY",
                "status": "PENDING",
                "amount": 150000
            }
        }
    """
    try:
        order_id_parsed = UUID(req.order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        # Verify order exists and belongs to merchant
        order = OrderService.get_order(
            db,
            order_id=order_id_parsed,
            merchant_id=current_merchant.id
        )

        # Create payment
        payment = PaymentService.create_payment(
            session=db,
            merchant_id=current_merchant.id,
            order_id=order.id,
            customer_id=order.customer_id,
            customer_phone=order.customer_phone_snapshot,
            provider=req.provider,
            amount=order.total_amount
        )

        return {
            "status": "success",
            "data": PaymentResponse.from_model(payment).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Payment creation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Récupérer détail d'un paiement.
    
    Response:
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "order_id": "uuid...",
                "provider": "ORANGE_MONEY",
                "status": "SUCCEEDED",
                "amount": 150000,
                "currency": "XOF"
            }
        }
    """
    try:
        payment_id_parsed = UUID(payment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payment_id format")

    try:
        payment = PaymentService.get_payment(
            db,
            payment_id=payment_id_parsed,
            merchant_id=current_merchant.id
        )

        return {
            "status": "success",
            "data": PaymentResponse.from_model(payment).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Payment retrieval error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting payment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}/payment")
async def get_order_payment(
    order_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Récupérer le paiement d'une commande.
    
    Response:
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "status": "PENDING",
                ...
            }
        }
    """
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        # Verify order belongs to merchant
        order = OrderService.get_order(
            db,
            order_id=order_id_parsed,
            merchant_id=current_merchant.id
        )

        payment = PaymentService.get_order_payment(
            db,
            order_id=order.id
        )

        if not payment:
            raise HTTPException(
                status_code=404,
                detail=f"No payment found for order {order_id}"
            )

        return {
            "status": "success",
            "data": PaymentResponse.from_model(payment).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting order payment: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== WEBHOOKS ==========

@router.post("/payments/webhook/orange")
async def orange_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook Orange Money - Appelé par Orange quand paiement reçu.
    
    ⚠️ CRITICAL: This endpoint is NOT authenticated!
    It's called by Orange's servers, not by clients.
    
    Orange will POST JSON payload like:
        {
            "transaction_id": "OM123456789",
            "merchant_reference": "pay-abc123",
            "status": "SUCCESS",
            "amount": 150000,
            "customer_phone": "+237690000000",
            "timestamp": "2026-05-03T10:30:00Z"
        }
    
    Response:
        {
            "status": "success",
            "transaction_id": "OM123456789",
            "payment_id": "uuid...",
            "order_id": "uuid...",
            "payment_status": "SUCCEEDED"
        }
    
    Must be idempotent - if called twice, process once!
    """
    try:
        payload = await request.json()
        logger.info(f"Orange webhook received | payload={payload}")

        result = PaymentService.handle_orange_webhook(
            session=db,
            payload=payload,
            signature=request.headers.get('X-Signature')
        )

        return result

    except ValueError as e:
        logger.warning(f"Orange webhook validation error: {str(e)}")
        # Return 400 but don't crash - Orange will retry
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing Orange webhook: {str(e)}")
        # Return 500 to tell Orange to retry
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payments/webhook/mtn")
async def mtn_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Webhook MTN Money - Appelé par MTN quand paiement reçu.
    
    ⚠️ CRITICAL: This endpoint is NOT authenticated!
    It's called by MTN's servers.
    
    MTN will POST JSON payload like:
        {
            "TransactionId": "MT123456789",
            "ExternalId": "pay-abc123",
            "TransactionStatus": "Succeeded",
            "Amount": "150000",
            "Currency": "XOF",
            "Payer": {
                "PartyIdType": "MSISDN",
                "PartyId": "+237690000000"
            }
        }
    
    Response:
        {
            "status": "success",
            "transaction_id": "MT123456789",
            "payment_id": "uuid...",
            "order_id": "uuid...",
            "payment_status": "SUCCEEDED"
        }
    
    Must be idempotent!
    """
    try:
        payload = await request.json()
        logger.info(f"MTN webhook received | payload={payload}")

        result = PaymentService.handle_mtn_webhook(
            session=db,
            payload=payload,
            signature=request.headers.get('X-Signature')
        )

        return result

    except ValueError as e:
        logger.warning(f"MTN webhook validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing MTN webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========== HEALTH CHECK ==========

@router.get("/payments/health")
async def payments_health(db: Session = Depends(get_db)):
    """Health check for payment service"""
    return {
        "status": "healthy",
        "service": "payment_service",
        "timestamp": datetime.utcnow().isoformat()
    }