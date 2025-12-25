"""Tests for the health check endpoint."""
from httpx import AsyncClient

from core.redis import RedisClient, set_redis_client


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
    assert "redis" in data


async def test_health_endpoint_redis_connected(client: AsyncClient) -> None:
    """Test that health endpoint reports Redis as connected."""
    response = await client.get("/health")
    data = response.json()
    assert data["redis"] == "connected"


async def test_health_endpoint_redis_unavailable(
    client: AsyncClient,
) -> None:
    """Test that health endpoint reports Redis unavailable gracefully."""
    # Create a disabled client to simulate unavailable Redis
    disabled_client = RedisClient("redis://localhost:6379", enabled=False)
    await disabled_client.connect()

    # Temporarily swap the Redis client
    original_client = set_redis_client.__globals__.get("_redis_client")
    set_redis_client(disabled_client)

    try:
        response = await client.get("/health")
        data = response.json()

        # App should still be healthy (degraded mode)
        assert data["status"] == "healthy"
        assert data["database"] == "healthy"
        assert data["redis"] == "unavailable"
    finally:
        # Restore original client
        set_redis_client(original_client)
        await disabled_client.close()
