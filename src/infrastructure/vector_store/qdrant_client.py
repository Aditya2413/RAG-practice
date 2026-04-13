from __future__ import annotations

from qdrant_client import AsyncQdrantClient

from src.core.config import Settings, get_settings

# Module-level reference populated by init_qdrant() during app lifespan startup.
qdrant_client: AsyncQdrantClient | None = None


async def init_qdrant(settings: Settings | None = None) -> AsyncQdrantClient:
    """Create the async Qdrant client and store it as a module-level singleton."""
    global qdrant_client
    if settings is None:
        settings = get_settings()

    client = AsyncQdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        api_key=settings.qdrant_api_key or None,
    )
    qdrant_client = client
    return client


async def close_qdrant() -> None:
    """Close the Qdrant client — called during app shutdown."""
    global qdrant_client
    if qdrant_client is not None:
        await qdrant_client.close()
        qdrant_client = None


async def check_qdrant() -> bool:
    """Verify Qdrant is reachable. Used by /health/ready."""
    try:
        if qdrant_client is None:
            return False
        # list_collections() is a lightweight call that confirms connectivity.
        await qdrant_client.get_collections()
        return True
    except Exception:
        return False
