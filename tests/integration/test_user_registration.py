import pytest
from httpx import AsyncClient
from fastapi import status

from app.main import app
from app.dependencies import _fake_user_db  # type: ignore


@pytest.fixture(autouse=True)
def clear_user_db():
    """
    Ensure the in‑memory user store is empty before each test.
    """
    _fake_user_db.clear()
    yield
    _fake_user_db.clear()


@pytest.mark.asyncio
async def test_successful_user_registration():
    """
    Register a new user with valid data.
    Expect a 201 response and the returned payload to contain the user fields
    (excluding the password).
    """
    payload = {
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "StrongP@ssw0rd!",
        "role": "customer",
    }

    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        response = await ac.post("/auth/signup", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    # The endpoint should return the created user (id, email, full_name, role, is_active)
    assert "id" in data
    assert data["email"] == payload["email"]
    assert data["full_name"] == payload["full_name"]
    assert data["role"] == payload["role"]
    assert data["is_active"] is True
    # Password must never be echoed back
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_duplicate_user_registration():
    """
    Attempt to register a user with an email that already exists.
    Expect a 400 Bad Request response.
    """
    payload = {
        "email": "duplicate@example.com",
        "full_name": "First User",
        "password": "FirstPass123!",
        "role": "customer",
    }

    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        # First registration should succeed
        first_resp = await ac.post("/auth/signup", json=payload)
        assert first_resp.status_code == status.HTTP_201_CREATED

        # Second registration with same email should fail
        second_resp = await ac.post("/auth/signup", json=payload)
        assert second_resp.status_code == status.HTTP_400_BAD_REQUEST
        error_detail = second_resp.json().get("detail", "")
        assert "already exists" in error_detail.lower()


@pytest.mark.asyncio
async def test_registration_missing_fields():
    """
    Send an incomplete payload (missing password) and expect FastAPI's validation
    to return a 422 Unprocessable Entity response.
    """
    incomplete_payload = {
        "email": "incomplete@example.com",
        "full_name": "Incomplete User",
        # "password" is omitted intentionally
        "role": "customer",
    }

    async with AsyncClient(app=app, base_url="http://testserver") as ac:
        response = await ac.post("/auth/signup", json=incomplete_payload)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    errors = response.json().get("detail", [])
    # Ensure the validation error mentions the missing password field
    assert any(err.get("loc") == ["body", "password"] for err in errors)