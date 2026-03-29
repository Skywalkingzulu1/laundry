from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import create_access_token
from app.dependencies import add_user, get_user_hashed
from app.models import Token, UserCreate

router = APIRouter()

@router.post("/signup", response_model=Token)
async def signup(user: UserCreate):
    """Create a new user and return a JWT.
    
    The password is hashed inside add_user. After creation we issue a token
    containing the user's email (as ``sub``) and role.
    """
    try:
        created_user = add_user(user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    access_token = create_access_token(data={"sub": created_user.email, "role": created_user.role})
    return Token(access_token=access_token)

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Authenticate a user and return a JWT.
    
    The OAuth2PasswordRequestForm provides ``username`` (email) and ``password``.
    We verify the password against the stored hash and issue a token containing
    the email and role.
    """
    user_dict = get_user_hashed(form_data.username)
    if not user_dict:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    # Verify password
    from app.auth import verify_password
    if not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    # Create token
    access_token = create_access_token(data={"sub": user_dict["email"], "role": user_dict["role"]})
    return Token(access_token=access_token)
