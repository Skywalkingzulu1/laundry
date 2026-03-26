from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import get_password_hash, verify_password, create_access_token
from app.models import UserCreate, User, Token
from app.dependencies import _fake_user_db

router = APIRouter()


@router.post("/signup", response_model=User, status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate):
    """
    Register a new user.

    - Checks for duplicate email.
    - Stores the user with a hashed password in the in‑memory store.
    - Returns the public user representation (without password hash).
    """
    if user.email in _fake_user_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    hashed_password = get_password_hash(user.password)
    user_id = len(_fake_user_db) + 1

    user_record = {
        "id": user_id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": True,
        "hashed_password": hashed_password,
    }

    _fake_user_db[user.email] = user_record

    # Return a User model without the hashed password
    public_user = {k: v for k, v in user_record.items() if k != "hashed_password"}
    return User(**public_user)


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate a user and issue a JWT access token.

    The token payload includes:
    - sub: the user's email
    - role: the user's role (customer, provider, admin)
    """
    user_record = _fake_user_db.get(form_data.username)
    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )

    if not verify_password(form_data.password, user_record["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(
        data={"sub": user_record["email"], "role": user_record["role"]}
    )
    return Token(access_token=access_token)