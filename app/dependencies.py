from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.auth import decode_token
from app.models import TokenData, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# In‑memory user store for demo purposes – replace with DB in real app
_fake_user_db = {}

def get_user(email: str) -> User:
    user_dict = _fake_user_db.get(email)
    if user_dict:
        return User(**user_dict)
    return None

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    try:
        token_data = decode_token(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user(token_data.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

def role_required(required_role: str):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires {required_role} role",
            )
        return current_user
    return role_checker
