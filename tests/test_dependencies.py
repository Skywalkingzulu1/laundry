import pytest
from app.dependencies import add_user, get_user, get_user_hashed, role_required
from app.models import UserCreate, User, TokenData

@pytest.fixture(autouse=True)
def clear_fake_db(monkeypatch):
    """
    Ensure that the in‑memory user store is reset before each test.
    """
    from app import dependencies
    monkeypatch.setattr(dependencies, "_fake_user_db", {}, raising=False)
    monkeypatch.setattr(dependencies, "_user_id_counter", 1, raising=False)


def test_add_and_get_user():
    user_create = UserCreate(
        email="john.doe@example.com",
        password="StrongPass!23",
        full_name="John Doe",
        role="customer",
    )
    # Add user
    user: User = add_user(user_create)

    # Verify returned public user fields
    assert user.id == 1
    assert user.email == user_create.email
    assert user.full_name == user_create.full_name
    assert user.role == user_create.role
    assert user.is_active is True

    # Retrieve via get_user (public view)
    fetched_user = get_user(user_create.email)
    assert fetched_user == user

    # Retrieve raw dict (includes hashed password)
    raw = get_user_hashed(user_create.email)
    assert "hashed_password" in raw
    assert raw["email"] == user_create.email


def test_add_user_duplicate_raises():
    user_create = UserCreate(
        email="duplicate@example.com",
        password="Pass123!",
        full_name="Dup User",
        role="customer",
    )
    add_user(user_create)
    with pytest.raises(ValueError):
        add_user(user_create)


@pytest.mark.asyncio
async def test_role_required_dependency():
    # Prepare a user with role "admin"
    user_create = UserCreate(
        email="admin@example.com",
        password="AdminPass!23",
        full_name="Admin User",
        role="admin",
    )
    add_user(user_create)

    # Simulate a token payload that would be decoded by the auth layer
    token_data = TokenData(email=user_create.email, role="admin")

    # Mock get_current_user to return the admin user
    async def mock_get_current_user():
        return get_user(user_create.email)

    # Use the role_required dependency
    checker = role_required("admin")
    # FastAPI's Depends will call the inner function; we invoke it directly
    result_user = await checker(current_user=await mock_get_current_user())
    assert result_user.role == "admin"

    # Now require a different role and expect HTTPException
    checker_wrong = role_required("customer")
    with pytest.raises(Exception) as exc_info:
        await checker_wrong(current_user=await mock_get_current_user())
    # The exception should be an HTTPException with 403 status
    assert exc_info.value.status_code == 403