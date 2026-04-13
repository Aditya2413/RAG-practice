from __future__ import annotations

import redis.asyncio as redis

from src.core.config import Settings, get_settings

# Module-level reference populated by init_redis() during app lifespan startup.
redis_client: redis.Redis | None = None


async def init_redis(settings: Settings | None = None) -> redis.Redis:
    """Create the Redis connection pool and store it as a module-level singleton."""
    global redis_client
    if settings is None:
        settings = get_settings()

    client = redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        password=settings.redis_password or None,
        db=settings.redis_db,
        decode_responses=True,
    )
    redis_client = client
    return client


async def close_redis() -> None:
    """Close the Redis connection pool — called during app shutdown."""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


def get_redis() -> "redis.Redis":
    """Return the module-level Redis client. Raises RuntimeError if not yet initialised."""
    if redis_client is None:
        raise RuntimeError("Redis has not been initialised. Call init_redis() first.")
    return redis_client


async def check_redis() -> bool:
    """Ping Redis. Used by /health/ready."""
    try:
        if redis_client is None:
            return False
        return await redis_client.ping()  # type: ignore[return-value]
    except Exception:
        return False
