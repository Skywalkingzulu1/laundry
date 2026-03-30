from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import add_user, get_user_hashed
from app.auth import create_access_token, verify_password
from app.models import UserCreate, User, Token

router = APIRouter()


@router.post(
    "/register",
    response_model=User,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with a hashed password and store it in the in‑memory store.",
)
async def register(user: UserCreate):
    """
    Register a new user.
    """
    try:
        new_user = add_user(user)
        return new_user
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post(
    "/login",
    response_model=Token,
    summary="User login",
    description="Authenticate a user and return a JWT access token containing the user's email and role.",
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return JWT token.
    """
    # OAuth2PasswordRequestForm uses `username` field for the identifier; we treat it as email.
    user_dict = get_user_hashed(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    access_token = create_access_token(
        data={"sub": user_dict["email"], "role": user_dict["role"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}