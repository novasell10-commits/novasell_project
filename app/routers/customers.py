"""
Customer Routes - CRUD
Location: app/routers/customers.py
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.database import get_db
from app.models import Customer, Order
from app.schemas import (
    CustomerCreateRequest,
    CustomerUpdateRequest,
    CustomerResponse,
    CustomerListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def get_current_merchant_id(request: Request) -> UUID:
    """Récupère l'ID du merchant depuis le token JWT"""
    merchant_id = getattr(request.state, 'merchant_id', None)
    if not merchant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant not authenticated"
        )
    return UUID(merchant_id)


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    request: Request,
    payload: CustomerCreateRequest,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Crée un nouveau client
    
    Nécessite: token JWT valide
    """
    try:
        phone = payload.phone.strip()
        
        # Vérifie que le client n'existe pas déjà pour ce merchant
        existing = db.query(Customer).filter(
            and_(
                Customer.phone == phone,
                Customer.merchant_id == merchant_id
            )
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer with this phone already exists for this merchant"
            )
        
        # Crée le client
        customer = Customer(
            phone=phone,
            name=payload.name,
            merchant_id=merchant_id
        )
        
        db.add(customer)
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Customer created: {customer.id} by merchant {merchant_id}")
        
        return CustomerResponse.model_validate(customer)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Create customer error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer"
        )


@router.get("", response_model=CustomerListResponse)
async def list_customers(
    request: Request,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(created_at|name|total_spent)$")
):
    """
    Liste tous les clients du merchant
    
    Query params:
    - skip: nombre de clients à passer (pagination)
    - limit: nombre max de clients (max 100)
    - search: chercher par téléphone ou nom
    - sort_by: trier par (created_at, name, total_spent)
    """
    try:
        # Construit la query
        query = db.query(Customer).filter(Customer.merchant_id == merchant_id)
        
        # Applique le filtre de recherche
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Customer.phone.ilike(search_term)) |
                (Customer.name.ilike(search_term))
            )
        
        # Count total
        total = query.count()
        
        # Tri
        if sort_by == "name":
            query = query.order_by(Customer.name)
        elif sort_by == "total_spent":
            # Tri par montant total dépensé (join avec orders)
            query = query.outerjoin(Order).group_by(Customer.id).order_by(
                func.sum(Order.total_amount).desc()
            )
        else:  # created_at (default)
            query = query.order_by(Customer.created_at.desc())
        
        # Pagination
        items = query.offset(skip).limit(limit).all()
        
        # Enrichit avec stats
        customers_response = []
        for customer in items:
            # Total orders
            total_orders = db.query(func.count(Order.id)).filter(
                Order.customer_id == customer.id
            ).scalar() or 0
            
            # Total spent
            total_spent = db.query(func.sum(Order.total_amount)).filter(
                Order.customer_id == customer.id
            ).scalar() or 0
            
            response = CustomerResponse.model_validate(customer)
            response.total_orders = total_orders
            response.total_spent = int(total_spent)
            customers_response.append(response)
        
        logger.info(f"Listed {len(items)} customers for merchant {merchant_id}")
        
        return CustomerListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=customers_response
        )
    
    except Exception as e:
        logger.error(f"List customers error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list customers"
        )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    request: Request,
    customer_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Récupère les détails d'un client
    
    Vérifie que le client appartient au merchant authentifié
    """
    try:
        customer = db.query(Customer).filter(
            and_(
                Customer.id == customer_id,
                Customer.merchant_id == merchant_id
            )
        ).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        # Enrichit avec stats
        total_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == customer.id
        ).scalar() or 0
        
        total_spent = db.query(func.sum(Order.total_amount)).filter(
            Order.customer_id == customer.id
        ).scalar() or 0
        
        response = CustomerResponse.model_validate(customer)
        response.total_orders = total_orders
        response.total_spent = int(total_spent)
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get customer error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer"
        )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    request: Request,
    customer_id: UUID,
    payload: CustomerUpdateRequest,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Met à jour un client
    
    Tous les champs sont optionnels
    """
    try:
        customer = db.query(Customer).filter(
            and_(
                Customer.id == customer_id,
                Customer.merchant_id == merchant_id
            )
        ).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        # Met à jour les champs non-None
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                # Vérifie l'unicité du phone si changé
                if key == "phone" and value != customer.phone:
                    existing = db.query(Customer).filter(
                        and_(
                            Customer.phone == value,
                            Customer.merchant_id == merchant_id,
                            Customer.id != customer_id
                        )
                    ).first()
                    if existing:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Phone already in use"
                        )
                
                setattr(customer, key, value)
        
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Customer updated: {customer_id} by merchant {merchant_id}")
        
        return CustomerResponse.model_validate(customer)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update customer error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer"
        )


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    request: Request,
    customer_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Supprime un client
    
    Note: Les commandes du client ne sont pas supprimées (cascade preserve data)
    """
    try:
        customer = db.query(Customer).filter(
            and_(
                Customer.id == customer_id,
                Customer.merchant_id == merchant_id
            )
        ).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        db.delete(customer)
        db.commit()
        
        logger.info(f"Customer deleted: {customer_id} by merchant {merchant_id}")
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete customer error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer"
        )


@router.get("/{customer_id}/orders", response_model=dict)
async def get_customer_orders(
    request: Request,
    customer_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100)
):
    """
    Récupère tous les commandes d'un client
    """
    try:
        # Vérifie que le client appartient au merchant
        customer = db.query(Customer).filter(
            and_(
                Customer.id == customer_id,
                Customer.merchant_id == merchant_id
            )
        ).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        # Récupère les commandes
        query = db.query(Order).filter(Order.customer_id == customer_id)
        total = query.count()
        items = query.order_by(Order.created_at.desc()).offset(skip).limit(limit).all()
        
        from app.schemas import OrderResponse
        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": [OrderResponse.model_validate(o) for o in items]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get customer orders error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer orders"
        )