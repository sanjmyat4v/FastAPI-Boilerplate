import logging
from fastapi import APIRouter
from redis.asyncio import Redis

from app.core.dependencies import DBSession, RedisClient
from app.core.exceptions import RateLimitExceededError
from app.schemas.user_schemas import (
    RegisterUserRequest, RegisterUserResponse,
)
from app.schemas.error_schemas import ErrorResponse
from app.services.user_service import add_user
from app.services.cache_service import check_and_increment_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth router"])

async def _enforce_rate_limit(redis: Redis, user_email: str) -> None:
    allowed, retry_after = await check_and_increment_rate_limit(redis, user_email)
    if not allowed:
        raise RateLimitExceededError(user_email=user_email, retry_after_seconds=retry_after)

@router.post("/register", status_code=201, response_model=RegisterUserResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
async def register(
    request: RegisterUserRequest,
    db: DBSession, redis: RedisClient,
) -> RegisterUserResponse:
    return await add_user(db=db, request=request)