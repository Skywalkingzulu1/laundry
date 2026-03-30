import pytest
import asyncio
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_health_and_readiness_endpoints():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        # Liveness probe
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        assert health_resp.json().get("status") == "ok"

        # Readiness probe
        ready_resp = await client.get("/ready")
        assert ready_resp.status_code == 200
        assert ready_resp.json().get("status") == "ready"
