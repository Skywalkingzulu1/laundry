from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_current_user, role_required
from app.models import Order, OrderCreate, OrderUpdate, User

router = APIRouter()


# In‑memory store for orders (replace with DB in production)
_fake_order_db = {}
_order_id_counter = 1


def _get_order_or_404(order_id: int) -> Order:
    order = _fake_order_db.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/", response_model=Order, status_code=status.HTTP_201_CREATED)
def create_order(
    order_in: OrderCreate,
    current_user: User = Depends(get_current_user),
):
    """
    Create a new laundry order for the authenticated user.
    """
    global _order_id_counter
    order = Order(
        id=_order_id_counter,
        user_id=current_user.id,
        description=order_in.description,
        status=order_in.status,
        created_at=datetime.utcnow(),
    )
    _fake_order_db[_order_id_counter] = order
    _order_id_counter += 1
    return order


@router.get("/", response_model=List[Order])
def list_orders(
    current_user: User = Depends(get_current_user),
):
    """
    Return all orders belonging to the authenticated user.
    """
    return [
        order
        for order in _fake_order_db.values()
        if order.user_id == current_user.id
    ]


@router.get("/{order_id}", response_model=Order)
def get_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve a specific order. Users can only access their own orders.
    """
    order = _get_order_or_404(order_id)
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this order",
        )
    return order


@router.put("/{order_id}", response_model=Order)
def update_order(
    order_id: int,
    order_in: OrderUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    Update an existing order. Only the owner can modify.
    """
    order = _get_order_or_404(order_id)
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this order",
        )
    update_data = order_in.dict(exclude_unset=True)
    updated_order = order.copy(update=update_data)
    _fake_order_db[order_id] = updated_order
    return updated_order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Delete an order. Only the owner can delete.
    """
    order = _get_order_or_404(order_id)
    if order.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this order",
        )
    del _fake_order_db[order_id]
    return None