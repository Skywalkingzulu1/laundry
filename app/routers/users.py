from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, verify_password
from app.dependencies import add_user, get_user_hashed
from app.models import UserCreate, User, Token

router = APIRouter()


@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
def signup(user_create: UserCreate):
    """
    Register a new user.

    The password is hashed before being stored in the in‑memory user store.
    Returns the public user representation (without the password hash).
    """
    try:
        user = add_user(user_create)
        return user
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and return a JWT access token.

    The endpoint expects ``username`` (email) and ``password`` fields as per
    OAuth2PasswordRequestForm. On successful authentication a JWT containing the
    user's email (as ``sub``) and role is returned.
    """
    user_record = get_user_hashed(form_data.username)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    hashed_password = user_record.get("hashed_password")
    if not hashed_password or not verify_password(form_data.password, hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create JWT token with email (sub) and role
    access_token = create_access_token(
        data={"sub": user_record["email"], "role": user_record["role"]}
    )
    return Token(access_token=access_token)