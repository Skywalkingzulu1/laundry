import time
from typing import Callable, List

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

# Simple in‑memory rate limiter for the /auth/signup endpoint.
# Allows up to `MAX_REQUESTS` requests per `WINDOW_SECONDS` per client IP.
MAX_REQUESTS = 5
WINDOW_SECONDS = 60

# Store timestamps of recent signup attempts per IP address.
_signup_attempts: dict[str, List[float]] = {}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces a basic rate limit on the signup endpoint.
    If the limit is exceeded, a 429 Too Many Requests response is returned.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # Only apply rate limiting to the signup route.
        if request.url.path.startswith("/auth/signup"):
            client_ip = request.client.host if request.client else "anonymous"

            now = time.time()
            attempts = _signup_attempts.get(client_ip, [])

            # Remove timestamps that are outside the current window.
            attempts = [ts for ts in attempts if now - ts < WINDOW_SECONDS]

            if len(attempts) >= MAX_REQUESTS:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many signup attempts. Please try again later."},
                )

            # Record the current attempt and store back.
            attempts.append(now)
            _signup_attempts[client_ip] = attempts

        # Continue processing the request.
        response = await call_next(request)
        return response