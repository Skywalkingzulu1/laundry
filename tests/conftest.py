import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session")
def client():
    """
    Provide a TestClient instance for integration tests.
    """
    return TestClient(app)