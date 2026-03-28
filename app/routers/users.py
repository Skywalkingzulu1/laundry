from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.models import UserCreate, Token, User
from app.auth import create_access_token, verify_password
from app.dependencies import add_user, get_user, _fake_user_db

router = APIRouter()

@router.post("/signup", response_model=Token)
def signup(user_in: UserCreate):
    """
    Register a new user and return a JWT token.
    """
    try:
        user = add_user(user_in)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    return Token(access_token=access_token)

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and return a JWT token.
    """
    user = get_user(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    stored = _fake_user_db.get(form_data.username)
    if not stored or not verify_password(form_data.password, stored["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    return Token(access_token=access_token)