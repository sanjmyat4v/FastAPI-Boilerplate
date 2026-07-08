import logging
import time
from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool: Redis | None = None

def init_redis() -> None:
    global _redis_pool
    settings = get_settings()

    _redis_pool = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )
    logger.info("Redis connection pool initialised.")

async def close_redis() -> None:
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis connection pool closed.")

def get_redis_client() -> Redis:
    if _redis_pool is None:
        raise RuntimeError("Redis not initialised. Call init_redis() at startup.")
    return _redis_pool

async def get_redis() -> AsyncGenerator[Redis, None]:
    if _redis_pool is None:
        raise RuntimeError("Redis not initialised. Call init_redis() at startup.")
    yield _redis_pool

async def ping_redis() -> dict:
    if _redis_pool is None:
        raise RuntimeError("Redis not initialised. Call init_redis() at startup.")
    
    start = time.monotonic()
    try:
        await _redis_pool.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {
            "status": "ok",
            "latency_ms": latency_ms
        }
    except RedisError as exc:
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.error("Redis health check failed: %s", exc)
        return {
            "status": "error",
            "latency_ms": latency_ms,
            "detail": str(exc)
        }