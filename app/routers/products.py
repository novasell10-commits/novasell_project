"""
Product Routes - CRUD
Location: app/routers/products.py
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.models import Product, Merchant
from app.schemas import (
    ProductCreateRequest,
    ProductUpdateRequest,
    ProductResponse,
    ProductListResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/products", tags=["products"])


def get_current_merchant_id(request: Request) -> UUID:
    """Récupère l'ID du merchant depuis le token JWT"""
    merchant_id = getattr(request.state, 'merchant_id', None)
    if not merchant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Merchant not authenticated"
        )
    return UUID(merchant_id)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    payload: ProductCreateRequest,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Crée un nouveau produit
    
    Nécessite: token JWT valide
    """
    try:
        # Vérifie que le merchant existe
        merchant = Merchant.get_by_id(db, merchant_id)
        if not merchant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Merchant not found"
            )
        
        # Crée le produit
        product = Product(
            merchant_id=merchant_id,
            name=payload.name,
            description=payload.description,
            price_amount=payload.price_amount,
            published=payload.published,
            stock=payload.stock,
            image_url=payload.image_url,
            category=payload.category,
            sku=payload.sku
        )
        
        db.add(product)
        db.commit()
        db.refresh(product)
        
        logger.info(f"Product created: {product.id} by merchant {merchant_id}")
        
        return ProductResponse.model_validate(product)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Create product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product"
        )


@router.get("", response_model=ProductListResponse)
async def list_products(
    request: Request,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    published: Optional[bool] = None,
    category: Optional[str] = None,
    search: Optional[str] = None
):
    """
    Liste tous les produits du merchant
    
    Query params:
    - skip: nombre de produits à passer (pagination)
    - limit: nombre max de produits (max 100)
    - published: filtrer par état (true/false)
    - category: filtrer par catégorie
    - search: chercher par nom ou description
    """
    try:
        # Construit la query
        query = db.query(Product).filter(Product.merchant_id == merchant_id)
        
        # Applique les filtres
        if published is not None:
            query = query.filter(Product.published == published)
        
        if category:
            query = query.filter(Product.category == category)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (Product.name.ilike(search_term)) |
                (Product.description.ilike(search_term))
            )
        
        # Count total
        total = query.count()
        
        # Pagination
        items = query.offset(skip).limit(limit).all()
        
        logger.info(f"Listed {len(items)} products for merchant {merchant_id}")
        
        return ProductListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=[ProductResponse.model_validate(p) for p in items]
        )
    
    except Exception as e:
        logger.error(f"List products error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list products"
        )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    request: Request,
    product_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Récupère les détails d'un produit
    
    Vérifie que le produit appartient au merchant authentifié
    """
    try:
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.merchant_id == merchant_id
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        return ProductResponse.model_validate(product)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get product"
        )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    request: Request,
    product_id: UUID,
    payload: ProductUpdateRequest,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Met à jour un produit
    
    Tous les champs sont optionnels (PATCH-like behavior)
    """
    try:
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.merchant_id == merchant_id
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Met à jour les champs non-None
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if value is not None:
                setattr(product, key, value)
        
        db.commit()
        db.refresh(product)
        
        logger.info(f"Product updated: {product_id} by merchant {merchant_id}")
        
        return ProductResponse.model_validate(product)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Update product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product"
        )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    request: Request,
    product_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """
    Supprime un produit
    """
    try:
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.merchant_id == merchant_id
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        db.delete(product)
        db.commit()
        
        logger.info(f"Product deleted: {product_id} by merchant {merchant_id}")
        
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete product"
        )


@router.post("/{product_id}/publish")
async def publish_product(
    request: Request,
    product_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """Publie un produit (le rend visible aux clients)"""
    try:
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.merchant_id == merchant_id
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product.published = True
        db.commit()
        
        logger.info(f"Product published: {product_id}")
        
        return {"status": "published", "product_id": str(product_id)}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Publish product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish product"
        )


@router.post("/{product_id}/unpublish")
async def unpublish_product(
    request: Request,
    product_id: UUID,
    db: Session = Depends(get_db),
    merchant_id: UUID = Depends(get_current_merchant_id)
):
    """Dépublie un produit (le rend invisible aux clients)"""
    try:
        product = db.query(Product).filter(
            and_(
                Product.id == product_id,
                Product.merchant_id == merchant_id
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        product.published = False
        db.commit()
        
        logger.info(f"Product unpublished: {product_id}")
        
        return {"status": "unpublished", "product_id": str(product_id)}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unpublish product error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unpublish product"
        )