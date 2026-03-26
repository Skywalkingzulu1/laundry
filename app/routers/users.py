from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.auth import get_password_hash, verify_password, create_access_token
from app.dependencies import _fake_user_db, get_user
from app.models import UserCreate, Token, User

router = APIRouter()

# Simple incremental ID generator for demo purposes
def _generate_user_id() -> int:
    return len(_fake_user_db) + 1

class SignupResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int

@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(user_in: UserCreate):
    """
    Register a new user.
    - Checks for existing email.
    - Stores hashed password.
    - Returns a JWT token containing the user's email and role.
    """
    if user_in.email in _fake_user_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    hashed_pw = get_password_hash(user_in.password)
    user_id = _generate_user_id()
    # Store all needed fields; password hash is kept for verification only
    _fake_user_db[user_in.email] = {
        "id": user_id,
        "email": user_in.email,
        "full_name": user_in.full_name,
        "role": user_in.role,
        "is_active": True,
        "hashed_password": hashed_pw,
    }
    access_token = create_access_token(data={"sub": user_in.email, "role": user_in.role})
    return SignupResponse(access_token=access_token, user_id=user_id)

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and issue a JWT.
    The OAuth2PasswordRequestForm provides `username` (used as email) and `password`.
    """
    user_record = _fake_user_db.get(form_data.username)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user_record["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Successful authentication – issue token
    access_token = create_access_token(
        data={"sub": user_record["email"], "role": user_record["role"]}
    )
    return Token(access_token=access_token)