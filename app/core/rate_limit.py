import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.dependencies import RedisClient, CurrentUser
from app.core.redis_client import get_redis_client
from app.core.exceptions import RateLimitExceededError

logger = logging.getLogger(__name__)

RATE_LIMIT_PREFIX = "app:ratelimit:"

class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, times: int, seconds: int):
        super().__init__(app)
        self.times = times
        self.seconds = seconds

    async def dispatch(self, request: Request, call_next):
        try:
            redis = await get_redis_client()
        except RuntimeError:
            logger.error("Redis not initialised — skipping global rate limit")
            return await call_next(request)

        identifier = _client_ip(request)
        key = f"{RATE_LIMIT_PREFIX}global:ip:{identifier}"

        try:
            pipe = redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = await pipe.execute()
            if ttl == -1:
                await redis.expire(key, self.seconds)
        except RedisError as exc:
            logger.error("Global rate limiter failed: %s", exc)
            return await call_next(request)  # fail open

        if count > self.times:
            retry_after = ttl if ttl > 0 else self.seconds
            return JSONResponse(
                status_code=429,
                content={"error_code": "RATE_LIMIT_EXCEEDED", "detail": "Too many requests."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)


def _client_ip(request: Request) -> str:
    """Origin sits behind a Cloudflare Tunnel, so request.client.host is
    cloudflared's local address, not the visitor's real IP. CF-Connecting-IP
    is the header Cloudflare sets reliably on tunneled requests."""
    cf_ip = request.headers.get("cf-connecting-ip")
    if cf_ip:
        return cf_ip
    return request.client.host if request.client else "unknown"

async def _check_limit(
    redis: Redis,
    scope: str,
    by: str,
    identifier: str,
    times: int,
    seconds: int,
    fail_open: bool,
) -> None:
    key = f"{RATE_LIMIT_PREFIX}{scope}:{by}:{identifier}"

    try:
        pipe = redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()
        if ttl == -1:
            await redis.expire(key, seconds)
    except RedisError as exc:
        logger.error("Rate limiter failed for key=%s: %s", key, exc)
        if fail_open:
            return
        raise RateLimitExceededError(identifier=identifier, retry_after_seconds=seconds)
    
    if count > times:
        retry_after = ttl if ttl > 0 else seconds
        raise RateLimitExceededError(identifier=identifier, retry_after_seconds=retry_after)

def rate_limit_by_ip(scope: str, times: int, seconds: int, fail_open: bool = True):
    """
    Usage:
        @router.post("/login", dependencies=[Depends(rate_limit_by_ip("login", times=5, seconds=60))])
    """
    async def dependency(request: Request, redis: RedisClient) -> None:
        await _check_limit(redis, scope, "ip", _client_ip(request), times, seconds, fail_open)

    return dependency


def rate_limit_by_user(scope: str, times: int, seconds: int, fail_open: bool = True):
    """
    Requires auth — reuses CurrentUser, so if the route already depends on it,
    the token is decoded once per request, not twice.

    Usage:
        @router.get("/me", dependencies=[Depends(rate_limit_by_user("me", times=60, seconds=60))])
    """
    async def dependency(current_user: CurrentUser, redis: RedisClient) -> None:
        await _check_limit(redis, scope, "user", current_user.username, times, seconds, fail_open)

    return dependency