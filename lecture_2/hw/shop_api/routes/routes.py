from fastapi import APIRouter, HTTPException, Query, Depends, Response
from typing import List, Optional, Annotated
from http import HTTPStatus

from sqlalchemy.orm import Session
from pydantic import NonNegativeInt, PositiveInt

from shop_api.database.database import get_db
from shop_api.tables.model import Cart, Item, CartItem
from shop_api.models import models

router = APIRouter()


@router.post("/cart", response_model=dict, status_code=HTTPStatus.CREATED)
async def create_cart(response: Response, db: Session = Depends(get_db)):
    cart = Cart()
    db.add(cart)
    db.commit()
    db.refresh(cart)
    response.headers["location"] = f"/cart/{cart.id}"
    return {"id": cart.id}


@router.get(
    "/cart/{cart_id}",
    response_model=models.CartResponse,
    responses={
        HTTPStatus.OK.value: {
            "description": "Successfully returned requested cart",
        },
        HTTPStatus.NOT_FOUND.value: {
            "description": "Cart not found!",
        },
    },
)
async def get_cart(cart_id: int, db: Session = Depends(get_db)):
    cart = db.query(Cart).filter(Cart.id == cart_id).first()
    if not cart:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Cart with id {cart_id} not found",
        )
    items = []
    total_price = 0.0
    for ci in cart.items:
        item = db.query(Item).filter(Item.id == ci.item_id).first()
        if item:
            items.append(models.CartItemResponse(
                id=item.id,
                name=item.name,
                quantity=ci.quantity,
                available=not item.deleted
            ))
            total_price += item.price * ci.quantity
    return models.CartResponse(id=cart.id, items=items, price=total_price)


@router.get("/cart", response_model=List[models.CartResponse])
async def get_carts(
    offset: Annotated[NonNegativeInt, Query()] = 0,
    limit: Annotated[PositiveInt, Query()] = 10,
    min_price: Optional[float] = Query(None, ge=0.0),
    max_price: Optional[float] = Query(None, ge=0.0),
    min_quantity: Optional[NonNegativeInt] = Query(None),
    max_quantity: Optional[NonNegativeInt] = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(Cart)

    carts = query.offset(offset).limit(limit).all()
    result = []
    for cart in carts:
        items = []
        total_price = 0.0
        total_quantity = 0
        for ci in cart.items:
            item = db.query(Item).filter(Item.id == ci.item_id).first()
            if item:
                items.append(models.CartItemResponse(
                    id=item.id,
                    name=item.name,
                    quantity=ci.quantity,
                    available=not item.deleted
                ))
                total_price += item.price * ci.quantity
                total_quantity += ci.quantity
        if min_price is not None and total_price < min_price:
            continue
        if max_price is not None and total_price > max_price:
            continue
        if min_quantity is not None and total_quantity < min_quantity:
            continue
        if max_quantity is not None and total_quantity > max_quantity:
            continue
        result.append(models.CartResponse(id=cart.id, items=items, price=total_price))
    return result


@router.post(
    "/cart/{cart_id}/add/{item_id}",
    response_model=dict,
    responses={
        HTTPStatus.OK.value: {
            "description": "Item added to cart successfully",
        },
        HTTPStatus.NOT_FOUND.value: {
            "description": "Cart or Item not found",
        },
    },
)
async def add_item_to_cart(cart_id: int, item_id: int, db: Session = Depends(get_db)):
    cart = db.query(Cart).filter(Cart.id == cart_id).first()
    item = db.query(Item).filter(Item.id == item_id).first()
    if not cart:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Cart with id {cart_id} not found"
        )
    if not item or item.deleted:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Item with id {item_id} not found or is deleted"
        )

    cart_item = db.query(CartItem).filter(
        CartItem.cart_id == cart_id,
        CartItem.item_id == item_id
    ).first()
    if cart_item:
        cart_item.quantity += 1
    else:
        cart_item = CartItem(cart_id=cart_id, item_id=item_id, quantity=1)
        db.add(cart_item)
        cart.items.append(cart_item)
    db.commit()
    return {"message": "Item added to cart"}


# Маршруты для товара

@router.post("/item", response_model=models.ItemResponse, status_code=HTTPStatus.CREATED)
async def create_item(
    item: models.ItemCreate,
    db: Session = Depends(get_db)
):
    db_item = Item(name=item.name, price=item.price, deleted=False)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get(
    "/item/{item_id}",
    response_model=models.ItemResponse,
    responses={
        HTTPStatus.OK.value: {
            "description": "Successfully returned requested item",
        },
        HTTPStatus.NOT_FOUND.value: {
            "description": "Failed to return requested item as it was not found",
            },
    },
)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item or item.deleted:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Item with id {item_id} not found",
        )
    return item


@router.get("/item", response_model=List[models.ItemResponse])
async def get_items(
    offset: Annotated[NonNegativeInt, Query()] = 0,
    limit: Annotated[PositiveInt, Query()] = 10,
    min_price: Optional[float] = Query(None, ge=0.0),
    max_price: Optional[float] = Query(None, ge=0.0),
    show_deleted: bool = Query(False),
    db: Session = Depends(get_db)
):
    query = db.query(Item)
    if not show_deleted:
        query = query.filter(Item.deleted == False)
    if min_price is not None:
        query = query.filter(Item.price >= min_price)
    if max_price is not None:
        query = query.filter(Item.price <= max_price)

    items = query.offset(offset).limit(limit).all()
    return items


@router.put(
    "/item/{item_id}",
    response_model=models.ItemResponse,
    responses={
        HTTPStatus.OK.value: {
            "description": "Item updated successfully",
        },
        HTTPStatus.NOT_FOUND.value: {
            "description": "Failed to update item as it was not found",
        },
    },
)
async def update_item(
    item_id: int,
    item: models.ItemCreate,
    db: Session = Depends(get_db)
):
    """Замена товара по ID"""
    db_item = db.query(Item).filter(Item.id == item_id).first()
    if not db_item or db_item.deleted:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Item with id {item_id} not found",
        )
    db_item.name = item.name
    db_item.price = item.price
    db.commit()
    db.refresh(db_item)
    return db_item


@router.patch(
    "/item/{item_id}",
    response_model=models.ItemResponse,
    responses={
        HTTPStatus.OK.value: {
            "description": "Item partially updated successfully",
        },
        HTTPStatus.NOT_MODIFIED.value: {
            "description": "Failed to update item",
        },
    },
)
async def partial_update_item(
    item_id: int,
    item: models.ItemUpdate,
    db: Session = Depends(get_db)
):
    db_item = db.query(Item).filter(Item.id == item_id).first()
    if not db_item or db_item.deleted:
        raise HTTPException(
            status_code=HTTPStatus.NOT_MODIFIED.value,
            detail=f"Item with id {item_id} not modified",
        )
    if item.name is not None:
        db_item.name = item.name
    if item.price is not None:
        db_item.price = item.price
    db.commit()
    db.refresh(db_item)
    return db_item


@router.delete(
    "/item/{item_id}",
    response_model=dict,
    responses={
        HTTPStatus.OK.value: {
            "description": "Item deleted successfully",
        },
        HTTPStatus.NOT_FOUND.value: {
            "description": "Failed to delete item as it was not found",
        },
    },
)
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    db_item = db.query(Item).filter(Item.id == item_id).first()
    if not db_item:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND.value,
            detail=f"Item with id {item_id} not found",
        )
    db_item.deleted = True
    db.commit()
    return {"message": "Item deleted"}