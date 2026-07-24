import logging
from typing import Annotated

import time
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser, decode_access_token, extract_bearer_token
from app.core.database import get_db as _get_db
from app.core.config import get_settings
from app.core.redis_client import get_redis as _get_redis

logger = logging.getLogger(__name__)

_bearer_schema = HTTPBearer(auto_error=False)

# ---------------------------------------------------------------------------
# Infrastructure dependencies
# ---------------------------------------------------------------------------
async def get_db() -> AsyncSession: # type: ignore[return]
    async for session in _get_db():
        yield session   # type: ignore

async def get_redis() -> Redis: # type: ignore[return]
    async for client in _get_redis():
        yield client    # type: ignore

# ---------------------------------------------------------------------------
# Authentication — single gate, no roles
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_schema),
    ],
) -> AuthenticatedUser:
    """
    Validates the Bearer access token and returns the authenticated user.
    This is the only auth gate — no roles, no hierarchy.
    Any valid token from the allowed GitHub user = full access.

    Raises:
        AuthTokenMissingError  (401) — no Authorization header
        AuthTokenInvalidError  (401) — expired or invalid token
    """
    raw = f"Bearer {credentials.credentials}" if credentials else None
    token = extract_bearer_token(raw)
    return decode_access_token(token)

DBSession   = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[Redis, Depends(get_redis)]
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]