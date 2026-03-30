from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import verify_password, create_access_token
from app.dependencies import add_user, get_user_hashed
from app.models import UserCreate, Token, User

router = APIRouter()

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    """Create a new user with a hashed password.
    Returns the public User model (without password hash)."""
    try:
        created_user = add_user(user)
        return created_user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT access token.
    The OAuth2PasswordRequestForm provides 'username' (email) and 'password'."""
    user_record = get_user_hashed(form_data.username)
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
    # Create JWT token containing email (as sub) and role
    token_data = {"sub": user_record["email"], "role": user_record["role"]}
    access_token = create_access_token(data=token_data)
    return Token(access_token=access_token)
