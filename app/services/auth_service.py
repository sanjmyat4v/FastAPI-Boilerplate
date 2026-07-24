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
REFRESH_PREFIX = "app:auth:refresh:"
SESSION_PREFIX = "app:auth:session:"
FAMILY_PREFIX = "app:auth:family:"

# Atomically: read the primary key, and if it hasn't already been consumed,
# tombstone it (prefix with "USED:") for a short grace window instead of
# deleting it outright. If it HAS already been tombstoned, we return that
# tombstoned value so the caller can detect reuse — this is what makes
# reuse detection race-safe: two concurrent requests can't both "win".

_CONSUME_SCRIPT = """
local value = redis.call('GET', KEYS[1])
if not value then
    return false
end
if string.sub(value, 1, 5) == 'USED:' then
    return value
end
redis.call('SET', KEYS[1], 'USED:' .. value, 'EX', ARGV[1])
return value
"""

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

async def create_user_session(redis: Redis, username: str) -> tuple[str, str]:
    jti = str(uuid.uuid4())
    family_id = str(uuid.uuid4())
    access_token = _create_access_token(username=username, jti=jti)
    refresh_token = await _create_and_store_refresh_token(redis, username, jti, family_id)
    return access_token, refresh_token


async def _create_and_store_refresh_token(
    redis: Redis,
    username: str,
    jti: str,
    family_id: str,
) -> str:
    settings = get_settings()
    raw_refresh_token = secrets.token_urlsafe(48)
    refresh_hash = hashlib.sha256(raw_refresh_token.encode()).hexdigest()

    refresh_key = f"{REFRESH_PREFIX}{refresh_hash}"
    session_key = f"{SESSION_PREFIX}{jti}"
    family_key = f"{FAMILY_PREFIX}{family_id}"
    ttl_seconds = settings.refresh_token_expire_days * 86400
    payload = f"{username}:{jti}:{family_id}"

    try:
        pipe = redis.pipeline(transaction=True)
        pipe.set(refresh_key, payload, ex=ttl_seconds)
        pipe.set(session_key, refresh_hash, ex=ttl_seconds)
        pipe.set(family_key, jti, ex=ttl_seconds)
        await pipe.execute()
    except RedisError as exc:
        logger.error("Failed to store refresh token in Redis: %s", exc)
        raise AuthTokenInvalidError("Could not create session. Please try again.")

    return raw_refresh_token


async def refresh_access_token(refresh_token: str, redis: Redis) -> tuple[str, str]:
    settings = get_settings()
    refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    refresh_key = f"{REFRESH_PREFIX}{refresh_hash}"

    try:
        stored = await redis.eval(
            _CONSUME_SCRIPT, 1, refresh_key, str(settings.refresh_reuse_grace_seconds)
        )
    except RedisError as exc:
        logger.error("Failed to consume refresh token in Redis: %s", exc)
        raise AuthTokenInvalidError("Session store unavailable. Please login again.")

    if not stored:
        raise AuthTokenInvalidError("Refresh token has expired or been revoked. Please login again.")

    stored = stored.decode() if isinstance(stored, bytes) else stored

    if stored.startswith("USED:"):
        _, username, jti, family_id = stored.split(":", 3)
        logger.warning(
            "Refresh token reuse detected (user=%s, family=%s) — revoking session",
            username, family_id,
        )
        await _revoke_family(redis, family_id)
        raise AuthTokenInvalidError(
            "Refresh token reuse detected. Session revoked for safety. Please login again."
        )

    username, jti, family_id = stored.split(":", 2)

    # Primary key is already tombstoned by the script; clean up its secondary index.
    try:
        await redis.delete(f"{SESSION_PREFIX}{jti}")
    except RedisError as exc:
        logger.warning("Failed to clean up session index for jti=%s: %s", jti, exc)

    new_jti = str(uuid.uuid4())
    new_access_token = _create_access_token(username=username, jti=new_jti)
    new_refresh_token = await _create_and_store_refresh_token(redis, username, new_jti, family_id)

    logger.info("Refresh token rotated for user: %s", username)
    return new_access_token, new_refresh_token


async def revoke_session(jti: str, redis: Redis) -> None:
    """Revoke a single session, e.g. on explicit logout using the current access token's jti."""
    session_key = f"{SESSION_PREFIX}{jti}"
    try:
        refresh_hash = await redis.get(session_key)
        family_id = None
        if refresh_hash:
            refresh_hash = refresh_hash.decode() if isinstance(refresh_hash, bytes) else refresh_hash
            refresh_payload = await redis.get(f"{REFRESH_PREFIX}{refresh_hash}")
            if refresh_payload:
                refresh_payload = refresh_payload.decode() if isinstance(refresh_payload, bytes) else refresh_payload
                _, _, family_id = refresh_payload.split(":", 2)

        pipe = redis.pipeline(transaction=True)
        pipe.delete(session_key)
        if refresh_hash:
            pipe.delete(f"{REFRESH_PREFIX}{refresh_hash}")
        if family_id:
            pipe.delete(f"{FAMILY_PREFIX}{family_id}")
        await pipe.execute()
        logger.info("Session revoked (jti=%s)", jti)
    except RedisError as exc:
        logger.warning("Failed to revoke session in Redis: %s", exc)


async def _revoke_family(redis: Redis, family_id: str) -> None:
    """Kill the current live token in a family. Called when a rotated-out (already-used)
    refresh token is replayed — a strong signal of theft."""
    family_key = f"{FAMILY_PREFIX}{family_id}"
    try:
        active_jti = await redis.get(family_key)
        if not active_jti:
            return
        active_jti = active_jti.decode() if isinstance(active_jti, bytes) else active_jti
        session_key = f"{SESSION_PREFIX}{active_jti}"
        refresh_hash = await redis.get(session_key)

        pipe = redis.pipeline(transaction=True)
        pipe.delete(session_key)
        pipe.delete(family_key)
        if refresh_hash:
            refresh_hash = refresh_hash.decode() if isinstance(refresh_hash, bytes) else refresh_hash
            pipe.delete(f"{REFRESH_PREFIX}{refresh_hash}")
        await pipe.execute()
    except RedisError as exc:
        logger.error("Failed to revoke token family %s: %s", family_id, exc)