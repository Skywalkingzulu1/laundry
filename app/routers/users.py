from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.models import UserCreate, User, Token
from app.dependencies import add_user, get_user_hashed, get_user
from app.auth import verify_password, create_access_token

router = APIRouter()

@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
def signup(user_create: UserCreate):
    """
    Register a new user. Returns the created user (without password hash).
    """
    try:
        user = add_user(user_create)
        return user
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and return a JWT access token.
    The OAuth2PasswordRequestForm provides `username` (used as email) and `password`.
    """
    # Retrieve the stored user record including the hashed password
    stored_user = get_user_hashed(form_data.username)
    if not stored_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    if not verify_password(form_data.password, stored_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )
    # Build a public User model for token payload
    user = get_user(form_data.username)
    access_token = create_access_token(
        data={"sub": user.email, "role": user.role}
    )
    return Token(access_token=access_token)