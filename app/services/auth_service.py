import logging
import secrets
import uuid
import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import _create_access_token
from app.core.exceptions import AuthTokenInvalidError
from app.core.security import verify_password
from app.core.exceptions import (
    InvalidCredentialsError
)

from app.services import user_service
from app.schemas.user_schemas import UserInfo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis key patterns for token storage
# ---------------------------------------------------------------------------
REFRESH_TOKEN_KEY_PREFIX = "app:auth:refresh:"   # app:auth:refresh:{jti}

# ---------------------------------------------------------------------------
# Auth service
# ---------------------------------------------------------------------------
async def authenticate_user(
    db: AsyncSession,
    email_or_username: str,
    password: str
) -> UserInfo:
    user = await user_service.get_user_for_auth(
        identifier=email_or_username, db=db
    )
    if not user or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    return UserInfo(
        id=user.id,
        email=user.email,
        username=user.username,
        is_active=user.is_active,
        is_deleted=user.is_deleted,
        created_at=user.created_at
    )


async def _create_and_store_refresh_token(
    redis: Redis,
    username: str,
    jti: str,
) -> str:
    """
    Creates a refresh token and stores it securely in Redis.

    The refresh token itself is a random opaque string (not a JWT) stored
    in Redis under app:auth:refresh:{jti}. The JTI is embedded in the access
    token — this links the access/refresh pair without exposing the refresh
    token value in the JWT.

    TTL = REFRESH_TOKEN_EXPIRE_DAYS.
    """
    settings = get_settings()
    raw_refresh_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()

    key = f"{REFRESH_TOKEN_KEY_PREFIX}{jti}"
    ttl_seconds = settings.refresh_token_expire_days * 86400

    try:
        await redis.set(
            key,
            f"{username}:{token_hash}",
            ex=ttl_seconds,
        )
    except RedisError as exc:
        logger.error("Failed to store refresh token in Redis: %s", exc)
        raise AuthTokenInvalidError("Could not create session. Please try again.")
    
    return raw_refresh_token

async def refresh_access_token(
    refresh_token: str,
    jti: str,
    redis: Redis,
) -> tuple[str, str]:
    """
    Validates a refresh token and issues a new access token + refresh token.
    Implements refresh token rotation — old refresh token is deleted on use.

    Args:
        refresh_token: The opaque refresh token string from the client.
        jti:           The JTI from the (possibly expired) access token.
        redis:         Redis client.

    Returns:
        Tuple of (new_access_token, new_refresh_token).

    Raises:
        AuthTokenInvalidError if the refresh token is invalid or expired.
    """
    key = f"{REFRESH_TOKEN_KEY_PREFIX}{jti}"

    try:
        stored = await redis.get(key)
    except RedisError as exc:
        logger.error("Failed to get refresh token from Redis: %s", exc)
        raise AuthTokenInvalidError("Session store unavailable. Please login again.")
    
    if not stored:
        raise AuthTokenInvalidError("Refresh token has expired or been revoked. Please login again.")
    
    parts = stored.split(":",1) # type: ignore
    if len(parts) != 2 or parts[1] != refresh_token:
        raise AuthTokenInvalidError("Invalid refresh token.")
    
    username = parts[0]

    await redis.delete(key)

    new_jti = str(uuid.uuid4())
    new_access_token = _create_access_token(
        username, new_jti   # type: ignore
    )
    new_refresh_token = await _create_and_store_refresh_token(
        redis, username, new_jti    # type: ignore
    )

    logger.info("Refresh token rotated for user: %s", username)
    return new_access_token, new_refresh_token


async def revoke_session(jti: str, redis: Redis) -> None:
    """
    Revokes a session by deleting the refresh token from Redis.
    Called on logout.
    """
    key = f"{REFRESH_TOKEN_KEY_PREFIX}{jti}"
    try:
        await redis.delete(key)
        logger.info("Session revoked (jti=%s)", jti)
    except RedisError as exc:
        logger.warning("Failed to revoke session in Redis: %s", exc)
