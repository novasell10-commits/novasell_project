"""
Order Routes
Location: app/routers/orders.py

Endpoints pour gérer les commandes:
  POST   /orders                   → Créer commande
  GET    /orders                   → Lister commandes
  GET    /orders/{id}              → Détail commande
  PUT    /orders/{id}              → Mettre à jour statut
  DELETE /orders/{id}              → Annuler commande
  PUT    /orders/{id}/confirm      → Confirmer livraison
  GET    /orders/{id}/items        → Items d'une commande
  GET    /orders/{id}/history      → Historique statut
"""

import logging
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.middlewares import get_current_merchant
from app.models import Merchant, OrderStatusEnum
from app.services.order_service import OrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["orders"])


# ========== SCHEMAS ==========

class OrderItemRequest(BaseModel):
    """Request schema for order item"""
    product_id: str = Field(..., description="Product UUID")
    qty: int = Field(..., ge=1, description="Quantity")


class CreateOrderRequest(BaseModel):
    """Request schema for creating order"""
    customer_phone: str = Field(..., description="E.164 format: +237...")
    items: List[OrderItemRequest] = Field(..., min_items=1)
    origin_city: Optional[str] = None
    destination_city: Optional[str] = None
    manual: bool = Field(False, description="True if manually created by merchant")


class UpdateOrderStatusRequest(BaseModel):
    """Request schema for updating order status"""
    status: str = Field(..., description="New status (PROCESSING, SHIPPED, etc.)")


class ConfirmOrderRequest(BaseModel):
    """Request schema for confirming order"""
    pass  # No body needed


class CancelOrderRequest(BaseModel):
    """Request schema for cancelling order"""
    reason: str = Field(default="No reason provided")


class OrderItemResponse(BaseModel):
    """Response schema for order item"""
    id: str
    product_id: Optional[str]
    name_snapshot: str
    qty: int
    unit_price_amount: int
    created_at: str


class OrderResponse(BaseModel):
    """Response schema for order"""
    id: str
    merchant_id: str
    customer_id: Optional[str]
    customer_phone_snapshot: str
    origin_city: Optional[str]
    destination_city: Optional[str]
    manual: bool
    status: str
    subtotal_amount: int
    total_amount: int
    escrow_amount: int
    currency: str
    created_at: str
    updated_at: str

    @staticmethod
    def from_model(order):
        return OrderResponse(
            id=str(order.id),
            merchant_id=str(order.merchant_id),
            customer_id=str(order.customer_id) if order.customer_id else None,
            customer_phone_snapshot=order.customer_phone_snapshot,
            origin_city=order.origin_city,
            destination_city=order.destination_city,
            manual=order.manual,
            status=order.status.value,
            subtotal_amount=order.subtotal_amount,
            total_amount=order.total_amount,
            escrow_amount=order.escrow_amount,
            currency=order.currency,
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat()
        )


class OrderDetailResponse(OrderResponse):
    """Order with items and history"""
    items: List[OrderItemResponse]
    item_count: int


# ========== ENDPOINTS ==========

@router.post("/orders", status_code=201)
async def create_order(
    req: CreateOrderRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Créer une nouvelle commande.
    
    Flow:
        1. Valide les données
        2. Crée la commande
        3. Crée les items (snapshot)
        4. Place l'escrow hold au ledger
        5. Retourne la commande
    
    Response:
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "customer_phone_snapshot": "+237690000000",
                "status": "PAID",
                "total_amount": 150000,
                "escrow_amount": 150000,
                "items": [...]
            }
        }
    """
    try:
        # Convert product IDs to UUID
        items_data = []
        for item in req.items:
            try:
                product_id = UUID(item.product_id)
                items_data.append({
                    'product_id': product_id,
                    'qty': item.qty
                })
            except ValueError:
                raise ValueError(f"Invalid product_id format: {item.product_id}")

        order = OrderService.create_order(
            session=db,
            merchant_id=current_merchant.id,
            customer_phone=req.customer_phone,
            items=items_data,
            origin_city=req.origin_city,
            destination_city=req.destination_city,
            manual=req.manual
        )

        # Get items
        items = OrderService.get_order_items(db, order.id)

        return {
            "status": "success",
            "data": {
                **OrderResponse.from_model(order).dict(),
                "items": [
                    {
                        "id": str(item.id),
                        "product_id": str(item.product_id) if item.product_id else None,
                        "name_snapshot": item.name_snapshot,
                        "qty": item.qty,
                        "unit_price_amount": item.unit_price_amount,
                        "created_at": item.created_at.isoformat()
                    }
                    for item in items
                ],
                "item_count": len(items)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order creation validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None),
    customer_phone: Optional[str] = Query(None),
    order_by: str = Query("created_at_desc"),
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Lister les commandes du merchant.
    
    Query params:
        skip: Pagination offset (default: 0)
        limit: Limit (default: 50, max: 100)
        status: Filter by status (PAID, PROCESSING, SHIPPED, etc.)
        customer_phone: Filter by customer phone
        order_by: Sort (created_at_desc, created_at_asc, total_amount_desc, etc.)
    
    Response:
        {
            "status": "success",
            "total": 10,
            "skip": 0,
            "limit": 50,
            "items": [{order}, ...]
        }
    """
    try:
        total, orders = OrderService.list_orders(
            session=db,
            merchant_id=current_merchant.id,
            skip=skip,
            limit=limit,
            status=status,
            customer_phone=customer_phone,
            order_by=order_by
        )

        return {
            "status": "success",
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": [OrderResponse.from_model(o).dict() for o in orders],
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order listing error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing orders: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Récupérer détail d'une commande avec items et historique.
    
    Response:
        {
            "status": "success",
            "data": {
                "id": "uuid...",
                "status": "PAID",
                "total_amount": 150000,
                "items": [...],
                "item_count": 2
            }
        }
    """
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        order = OrderService.get_order(
            session=db,
            order_id=order_id_parsed,
            merchant_id=current_merchant.id
        )

        items = OrderService.get_order_items(db, order.id)

        return {
            "status": "success",
            "data": {
                **OrderResponse.from_model(order).dict(),
                "items": [
                    {
                        "id": str(item.id),
                        "product_id": str(item.product_id) if item.product_id else None,
                        "name_snapshot": item.name_snapshot,
                        "qty": item.qty,
                        "unit_price_amount": item.unit_price_amount,
                        "created_at": item.created_at.isoformat()
                    }
                    for item in items
                ],
                "item_count": len(items)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order retrieval error: {str(e)}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{order_id}")
async def update_order_status(
    order_id: str,
    req: UpdateOrderStatusRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Mettre à jour le statut d'une commande.
    
    Valid transitions:
        PAID → PROCESSING
        PROCESSING → SHIPPED
        SHIPPED → AWAITING_CONFIRMATION
        AWAITING_CONFIRMATION → CONFIRMED (use /confirm endpoint instead)
        * → CANCELLED
    
    Body:
        {
            "status": "SHIPPED"
        }
    """
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        status_enum = OrderStatusEnum(req.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {req.status}"
        )

    try:
        order = OrderService.update_status(
            session=db,
            order_id=order_id_parsed,
            new_status=status_enum,
            actor='MERCHANT'
        )

        return {
            "status": "success",
            "data": OrderResponse.from_model(order).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order status update error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating order status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/orders/{order_id}/confirm")
async def confirm_order(
    order_id: str,
    req: ConfirmOrderRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Confirmer la réception d'une commande (CLIENT).
    
    ⭐ ATOMIC OPERATION:
        - Release escrow from ledger
        - Credit merchant account
        - Update order to CONFIRMED
    
    This is the critical operation that releases funds to the merchant!
    """
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        order = OrderService.confirm_order(
            session=db,
            order_id=order_id_parsed,
            actor='CUSTOMER'
        )

        return {
            "status": "success",
            "message": "Order confirmed, escrow released to merchant",
            "data": OrderResponse.from_model(order).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order confirmation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error confirming order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    req: CancelOrderRequest,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """
    Annuler une commande.
    
    Creates REFUND entry in ledger.
    Cannot cancel CONFIRMED orders (must go through refund request).
    
    Body:
        {
            "reason": "Out of stock"
        }
    """
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        order = OrderService.cancel_order(
            session=db,
            order_id=order_id_parsed,
            reason=req.reason,
            actor='MERCHANT'
        )

        return {
            "status": "success",
            "message": "Order cancelled, refund processed",
            "data": OrderResponse.from_model(order).dict(),
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        logger.warning(f"Order cancellation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling order: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}/items")
async def get_order_items(
    order_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """Récupérer les items d'une commande"""
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        # Verify order belongs to merchant
        order = OrderService.get_order(
            db, order_id_parsed, current_merchant.id
        )

        items = OrderService.get_order_items(db, order.id)

        return {
            "status": "success",
            "order_id": str(order.id),
            "total_items": len(items),
            "items": [
                {
                    "id": str(item.id),
                    "product_id": str(item.product_id) if item.product_id else None,
                    "name_snapshot": item.name_snapshot,
                    "qty": item.qty,
                    "unit_price_amount": item.unit_price_amount,
                    "subtotal": item.unit_price_amount * item.qty,
                    "created_at": item.created_at.isoformat()
                }
                for item in items
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting order items: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}/history")
async def get_order_history(
    order_id: str,
    current_merchant: Merchant = Depends(get_current_merchant),
    db: Session = Depends(get_db)
):
    """Récupérer l'historique des changements de statut"""
    try:
        order_id_parsed = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    try:
        # Verify order belongs to merchant
        order = OrderService.get_order(
            db, order_id_parsed, current_merchant.id
        )

        history = OrderService.get_order_history(db, order.id)

        return {
            "status": "success",
            "order_id": str(order.id),
            "total_changes": len(history),
            "history": [
                {
                    "id": str(h.id),
                    "from_status": h.from_status.value if h.from_status else None,
                    "to_status": h.to_status.value,
                    "actor": h.actor,
                    "metadata": h.metadata,
                    "created_at": h.created_at.isoformat()
                }
                for h in history
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting order history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))