from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from app.models import UserCreate, User, Token
from app.auth import get_password_hash, verify_password, create_access_token
from app.dependencies import get_user

router = APIRouter()

# Simple in‑memory store – replace with persistent DB later
_user_store = {}

@router.post("/register", response_model=User)
async def register(user_in: UserCreate):
    if user_in.email in _user_store:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed_password = get_password_hash(user_in.password)
    user_dict = {
        "id": len(_user_store) + 1,
        "email": user_in.email,
        "full_name": user_in.full_name,
        "role": user_in.role,
        "hashed_password": hashed_password,
        "is_active": True,
    }
    _user_store[user_in.email] = user_dict
    return User(**{k: v for k, v in user_dict.items() if k != "hashed_password"})

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user_dict = _user_store.get(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    access_token_expires = timedelta(minutes=60)
    access_token = create_access_token(
        data={"sub": user_dict["email"], "role": user_dict["role"]},
        expires_delta=access_token_expires,
    )
    return Token(access_token=access_token)
