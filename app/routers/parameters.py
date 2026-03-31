from fastapi import APIRouter
from app.config import settings

router = APIRouter()

@router.get("/", summary="Get application parameters")
async def get_parameters():
    """Return non-sensitive configuration parameters.
    Sensitive values like SECRET_KEY are deliberately omitted.
    """
    return {
        "algorithm": settings.ALGORITHM,
        "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    }
