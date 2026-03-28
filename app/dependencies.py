from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.auth import decode_token, get_password_hash
from app.models import TokenData, User, UserCreate

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# In‑memory user store for demo purposes – replace with DB in real app
_fake_user_db = {}
_user_id_counter = 1

def get_user(email: str) -> User:
    """
    Retrieve a user from the in‑memory store.
    The stored dict contains a hashed_password field which is not part of the
    public User model, so we strip it out before constructing the User instance.
    """
    user_dict = _fake_user_db.get(email)
    if user_dict:
        # Create a copy without the password hash for the Pydantic model
        public_user_data = {k: v for k, v in user_dict.items() if k != "hashed_password"}
        return User(**public_user_data)
    return None

def add_user(user_create: UserCreate) -> User:
    """
    Add a new user to the in‑memory store.
    Password is hashed before storage. Raises ValueError if the email already exists.
    """
    global _user_id_counter
    if user_create.email in _fake_user_db:
        raise ValueError("User already exists")
    hashed_password = get_password_hash(user_create.password)
    user_dict = {
        "id": _user_id_counter,
        "email": user_create.email,
        "full_name": user_create.full_name,
        "role": user_create.role,
        "is_active": True,
        "hashed_password": hashed_password,
    }
    _fake_user_db[user_create.email] = user_dict
    _user_id_counter += 1
    # Return a public User model (without password hash)
    public_user_data = {k: v for k, v in user_dict.items() if k != "hashed_password"}
    return User(**public_user_data)

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