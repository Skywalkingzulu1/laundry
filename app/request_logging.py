import time
import logging
from fastapi import Request
from starlette.responses import Response
from app.logger import logger


async def log_requests(request: Request, call_next):
    """FastAPI middleware that logs each incoming request and its response.
    The log is emitted as a JSON object using the shared logger.
    """
    start_time = time.time()
    response: Response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": request.client.host if request.client else None,
        },
    )
    return response
