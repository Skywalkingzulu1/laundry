from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from app.auth import decode_token
from app.models import TokenData

async def jwt_auth_middleware(request: Request, call_next):
    """
    Global JWT authentication middleware.
    All routes (except explicitly whitelisted) require a valid Bearer token.
    """
    # Whitelisted endpoints that do not require authentication
    whitelist = [
        "/health",
        "/api/health",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    ]

    if any(request.url.path.startswith(path) for path in whitelist):
        # Skip authentication for whitelisted routes
        return await call_next(request)

    # Expect Authorization header with Bearer token
    auth: str = request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Not authenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth.split(" ", 1)[1]
    try:
        # Decode token to ensure it's valid; we don't need the payload here
        _ = decode_token(token)  # will raise JWTError if invalid
    except Exception:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Could not validate credentials"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Token is valid; proceed to the endpoint
    response = await call_next(request)
    return response