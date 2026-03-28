from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, verify_password, get_password_hash
from app.dependencies import get_user
from app.models import UserCreate, User, Token

router = APIRouter()

# Simple in‑memory auto‑increment ID generator
_user_id_counter = 1

@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
async def signup(user_in: UserCreate):
    """Register a new user.
    Stores the user in the in‑memory DB with a hashed password.
    """
    # Check for existing email
    if get_user(user_in.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    global _user_id_counter
    hashed_password = get_password_hash(user_in.password)
    user_dict = {
        "id": _user_id_counter,
        "email": user_in.email,
        "full_name": user_in.full_name,
        "role": user_in.role,
        "is_active": True,
        "hashed_password": hashed_password,
    }
    # Store in the fake DB defined in dependencies
    from app.dependencies import _fake_user_db
    _fake_user_db[user_in.email] = user_dict
    _user_id_counter += 1
    # Return public user model (without password)
    return User(**{k: v for k, v in user_dict.items() if k != "hashed_password"})

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate user and return a JWT.
    The OAuth2PasswordRequestForm provides ``username`` (used as email) and ``password``.
    """
    from app.dependencies import _fake_user_db
    user_dict = _fake_user_db.get(form_data.username)
    if not user_dict:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Create JWT with email (sub) and role
    access_token = create_access_token(data={"sub": user_dict["email"], "role": user_dict["role"]})
    return Token(access_token=access_token)
