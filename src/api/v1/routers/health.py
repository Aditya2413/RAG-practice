import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.infrastructure.database.postgres.connection import check_db
from src.infrastructure.database.redis.connection import check_redis
from src.infrastructure.vector_store.qdrant_client import check_qdrant

router = APIRouter()


@router.get("/health", tags=["health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — returns 200 as long as the process is running."""
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def readiness() -> JSONResponse:
    """
    Readiness probe — checks all three infrastructure dependencies in parallel.
    Returns 200 if all pass, 503 if any fail.
    """
    db_ok, redis_ok, qdrant_ok = await asyncio.gather(
        check_db(),
        check_redis(),
        check_qdrant(),
    )

    checks = {
        "postgres": db_ok,
        "redis": redis_ok,
        "qdrant": qdrant_ok,
    }
    all_ok = all(checks.values())

    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "ok" if all_ok else "degraded",
            "checks": checks,
        },
    )
