import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import get_user

client = TestClient(app)

@pytest.fixture(scope="function")
def cleanup_user():
    # Ensure the in‑memory user store is clean before each test
    # The _fake_user_db is internal; we import and clear it directly.
    from app.dependencies import _fake_user_db, _user_id_counter
    _fake_user_db.clear()
    # Reset counter to 1 for deterministic IDs
    globals()["_user_id_counter"] = 1
    yield
    _fake_user_db.clear()
    globals()["_user_id_counter"] = 1

def test_signup_and_login_flow(cleanup_user):
    # 1. Sign up a new user
    signup_payload = {
        "email": "testuser@example.com",
        "full_name": "Test User",
        "password": "StrongP@ssw0rd",
        "role": "customer"
    }
    response = client.post("/auth/signup", json=signup_payload)
    assert response.status_code == 200, f"Signup failed: {response.text}"
    data = response.json()
    # Expect the created user data (without password) and is_active=False
    assert data["email"] == signup_payload["email"]
    assert data["full_name"] == signup_payload["full_name"]
    assert data["role"] == signup_payload["role"]
    assert data["is_active"] is False
    assert "id" in data

    # 2. Activate the user (simulating email verification)
    # Directly call the dependency function to activate
    from app.dependencies import activate_user
    activate_user(signup_payload["email"])

    # 3. Attempt login with correct credentials
    login_payload = {
        "username": signup_payload["email"],
        "password": signup_payload["password"]
    }
    response = client.post("/auth/login", data=login_payload)
    assert response.status_code == 200, f"Login failed: {response.text}"
    token_data = response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 4. Verify that the token can be decoded and corresponds to the user
    from app.auth import decode_token
    decoded = decode_token(token_data["access_token"])
    assert decoded.email == signup_payload["email"]
    assert decoded.role == signup_payload["role"]

    # 5. Ensure the current_user endpoint works with the token
    headers = {"Authorization": f"Bearer {token_data['access_token']}"}
    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200
    me_data = response.json()
    assert me_data["email"] == signup_payload["email"]
    assert me_data["role"] == signup_payload["role"]
