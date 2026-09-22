"""Tests for the health check endpoints."""

from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_root_health_check() -> None:
    """Test GET /health returns 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_api_v1_health_check() -> None:
    """Test GET /api/v1/health returns 200 and healthy status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
