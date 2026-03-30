import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_signup_success():
    """
    Test that a new user can register successfully.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "email": "test_success@example.com",
            "full_name": "Test Success",
            "password": "StrongPass123!",
            "role": "customer"
        }
        response = await client.post("/auth/signup", json=payload)

    assert response.status_code == 200, f"Unexpected status: {response.text}"
    data = response.json()
    # The endpoint should return the public User model (no password hash)
    assert data["email"] == payload["email"]
    assert data["full_name"] == payload["full_name"]
    assert data["role"] == payload["role"]
    assert "id" in data
    assert isinstance(data["id"], int)


@pytest.mark.asyncio
async def test_signup_duplicate_email():
    """
    Registering with an email that already exists should return an error.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "email": "duplicate@example.com",
            "full_name": "First User",
            "password": "Password123!",
            "role": "customer"
        }
        # First registration should succeed
        first_resp = await client.post("/auth/signup", json=payload)
        assert first_resp.status_code == 200

        # Second registration with the same email should fail
        second_resp = await client.post("/auth/signup", json=payload)

    # The router is expected to raise a 400 Bad Request for duplicates
    assert second_resp.status_code == 400, f"Expected 400, got {second_resp.status_code}: {second_resp.text}"


@pytest.mark.asyncio
async def test_signup_missing_required_field():
    """
    Omitting a required field (e.g., role) should trigger a validation error (422).
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "email": "missing_role@example.com",
            "full_name": "No Role User",
            "password": "Password123!"
            # 'role' is intentionally omitted
        }
        response = await client.post("/auth/signup", json=payload)

    # FastAPI/Pydantic returns 422 for validation errors
    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"