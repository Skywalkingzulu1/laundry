from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token, verify_password
from app.dependencies import add_user, get_user_hashed
from app.models import UserCreate, Token, User

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    """Register a new user and return a JWT token.

    The password is hashed inside ``add_user``. If the email already exists a
    ``ValueError`` is raised which we translate to a 400 response.
    """
    try:
        created_user: User = add_user(user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        )
    access_token = create_access_token(data={"sub": created_user.email, "role": created_user.role})
    return Token(access_token=access_token)

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT token.

    ``OAuth2PasswordRequestForm`` provides ``username`` and ``password`` fields.
    ``username`` is treated as the user's email.
    """
    user_dict = get_user_hashed(form_data.username)
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
    access_token = create_access_token(data={"sub": user_dict["email"], "role": user_dict["role"]})
    return Token(access_token=access_token)
