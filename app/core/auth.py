import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.exceptions import AuthTokenInvalidError, AuthTokenMissingError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis key patterns for token storage
# ---------------------------------------------------------------------------
REFRESH_TOKEN_KEY_PREFIX = "app:auth:refresh:"   # lms:auth:refresh:{jti}

@dataclass
class AuthenticatedUser:
    """Represents a verified, authenticated session."""
    username: str
    jti: str

# ---------------------------------------------------------------------------
# Token creation and storage
# ---------------------------------------------------------------------------
def _create_access_token(username: str, jti: str) -> str:
    """
    Issues a short-lived HS-256 access token.

    Payload:
        Payload:
        sub  — Username
        jti  — JWT ID (links to refresh token in Redis)
        type — "access"
    """

    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub":  username,
        "jti":  jti,
        "type": "access",
        "iat":  int(now.timestamp()),
        "exp":  int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")

async def _create_and_store_refresh_token(
    redis: Redis,
    username: str,
    jti: str,
) -> str:
    """
    Creates a refresh token and stores it securely in Redis.

    The refresh token itself is a random opaque string (not a JWT) stored
    in Redis under lms:auth:refresh:{jti}. The JTI is embedded in the access
    token — this links the access/refresh pair without exposing the refresh
    token value in the JWT.

    TTL = REFRESH_TOKEN_EXPIRE_DAYS.
    """
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)

    key = f"{REFRESH_TOKEN_KEY_PREFIX}{jti}"
    ttl_seconds = settings.refresh_token_expire_days * 86400

    try:
        await redis.set(
            key,
            f"{username}:{refresh_token}",
            ex=ttl_seconds,
        )
    except RedisError as exc:
        logger.error("Failed to store refresh token in Redis: %s", exc)
        raise AuthTokenInvalidError("Could not create session. Please try again.")
    
    return refresh_token

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
    new_access_token = _create_access_token(username, new_jti)  # type: ignore
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

def decode_access_token(token: str) -> AuthenticatedUser:
    """
    Decodes and validates our own HS256 access token.

    Returns:
        AuthenticatedUser with github_username and jti.

    Raises:
        AuthTokenInvalidError on any failure.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS-256"],
            options={"verify_exp": True},
        )
    except ExpiredSignatureError:
        raise AuthTokenInvalidError("Access token has expired. Please refresh.")
    except JWTError as exc:
        raise AuthTokenInvalidError(f"Invalid access token: {exc}")
    
    if payload.get("type") != "access":
        raise AuthTokenInvalidError("Token is nor an access token.")
    
    username = payload.get("sub", "")
    jti = payload.get("jti", "")

    if not username or not jti:
        raise AuthTokenInvalidError("Access token is missing required claims.")
    
    return AuthenticatedUser(username=username, jti=jti)

def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise AuthTokenMissingError
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthTokenInvalidError("Authorization header must be: 'Bearer <token>'")
    return parts[1]