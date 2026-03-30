from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, verify_password
from app.dependencies import add_user, get_user_hashed
from app.models import UserCreate, Token, User

router = APIRouter()

@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
def signup(user: UserCreate):
    """Register a new user. Password is hashed and stored in the in‑memory store.
    Returns the public user representation (without password hash)."""
    try:
        new_user = add_user(user)
        return new_user
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT access token.
    The token payload includes the user's email (as "sub") and role.
    """
    user_record = get_user_hashed(form_data.username)
    if not user_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not verify_password(form_data.password, user_record["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = create_access_token(data={"sub": user_record["email"], "role": user_record["role"]})
    return Token(access_token=access_token)
