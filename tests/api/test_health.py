"""Tests for the health check endpoint."""
from httpx import AsyncClient


async def test_health_endpoint_returns_200(client: AsyncClient) -> None:
    """Test that the health endpoint returns 200 OK."""
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_endpoint_returns_healthy_status(client: AsyncClient) -> None:
    """Test that the health endpoint returns healthy status."""
    response = await client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"


async def test_health_endpoint_response_structure(client: AsyncClient) -> None:
    """Test that the health endpoint returns the expected structure."""
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "database" in data
