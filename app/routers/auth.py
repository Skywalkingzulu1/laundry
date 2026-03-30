from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.dependencies import (
    add_user,
    get_user_hashed,
    get_user,
    activate_user,
    get_current_user,
)
from app.models import UserCreate, Token, User
from app.auth import create_access_token, verify_password, decode_token

router = APIRouter()


@router.post("/signup", response_model=User)
def signup(user_create: UserCreate):
    """
    Register a new user. The user is created with `is_active=False` and must be
    activated (e.g., via email verification) before they can log in.
    """
    try:
        user = add_user(user_create)
        return user
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and return a JWT access token.
    """
    user_dict = get_user_hashed(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not user_dict.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is not active")
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    access_token = create_access_token(
        data={"sub": user_dict["email"], "role": user_dict["role"]}
    )
    return Token(access_token=access_token)


@router.get("/me", response_model=User)
def read_current_user(current_user: User = Depends(get_current_user)):
    """
    Return the currently authenticated user.
    """
    return current_user


@router.post("/refresh", response_model=Token)
def refresh_token(current_user: User = Depends(get_current_user)):
    """
    Issue a new access token for an already authenticated user.
    """
    new_token = create_access_token(
        data={"sub": current_user.email, "role": current_user.role}
    )
    return Token(access_token=new_token)


@router.post("/activate")
def activate(email: str):
    """
    Simple endpoint to activate a user (for testing purposes).
    In a real application this would be handled via email verification links.
    """
    try:
        activate_user(email)
        return {"detail": "User activated"}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))