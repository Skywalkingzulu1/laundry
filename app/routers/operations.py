from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# Simple Prometheus metrics for demonstration
REQUEST_COUNT = Counter(
    "app_requests_total", "Total number of requests", ["method", "endpoint"]
)

router = APIRouter()


@router.get("/health")
async def ops_health():
    """
    Operational health check – identical to the root /health but scoped under /ops.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness_probe():
    """
    Readiness probe used by orchestration tools to verify the app can serve traffic.
    """
    # In a real app you would check DB connections, external services, etc.
    return {"ready": True}


@router.get("/metrics")
async def metrics():
    """
    Expose Prometheus metrics.
    """
    # Increment a generic request counter for demonstration
    REQUEST_COUNT.inc(labels={"method": "GET", "endpoint": "/ops/metrics"})
    data = generate_latest()
    return JSONResponse(content=data, media_type=CONTENT_TYPE_LATEST)


@router.get("/admin/users")
async def list_all_users(admin: dict = Depends(lambda: None)):
    """
    Placeholder admin endpoint to list all users.
    In production, replace the dummy dependency with proper role checking.
    """
    # Simple role enforcement using the JWT middleware's token data
    # This is a stub; actual implementation would query a database.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="User listing not implemented in beta.",
    )