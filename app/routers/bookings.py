from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import role_required, get_current_user
from app.models import User

router = APIRouter()

@router.get("/customer-area")
async def customer_endpoint(current_user: User = Depends(role_required("customer"))):
    return {"msg": f"Hello Customer {current_user.email}"}

@router.get("/provider-area")
async def provider_endpoint(current_user: User = Depends(role_required("provider"))):
    return {"msg": f"Hello Provider {current_user.email}"}

@router.get("/admin-area")
async def admin_endpoint(current_user: User = Depends(role_required("admin"))):
    return {"msg": f"Hello Admin {current_user.email}"}
