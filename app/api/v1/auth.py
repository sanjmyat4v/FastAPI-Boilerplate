import logging
from fastapi import APIRouter, status

from app.core.dependencies import DBSession, RedisClient, CurrentUser
from app.core.exceptions import RateLimitExceededError
from app.services import auth_service
from app.services.user_service import get_user_by_username
from app.schemas.user_schemas import (
    RegisterUserRequest, RegisterUserResponse,
    UserInfo,
)
from app.schemas.auth_schemas import (
    LoginRequest, LoginResponse,
    RefreshRequest, TokenResponse,
)
from app.schemas.error_schemas import ErrorResponse
from app.services.user_service import add_user
from app.services.cache_service import check_and_increment_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth router"])

async def _enforce_rate_limit(redis: RedisClient, user_email: str) -> None:
    allowed, retry_after = await check_and_increment_rate_limit(redis, user_email)
    if not allowed:
        raise RateLimitExceededError(user_email=user_email, retry_after_seconds=retry_after)

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=RegisterUserResponse,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}})
async def register(
    request: RegisterUserRequest,
    db: DBSession, redis: RedisClient,
) -> RegisterUserResponse:
    return await add_user(db=db, request=request)

@router.post("/login", status_code=status.HTTP_200_OK, response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db: DBSession,
    redis: RedisClient,
) -> LoginResponse:
    user = await auth_service.authenticate_user(db, email_or_username=request.identifier, password=request.password)
    access_token, refresh_token = await auth_service.create_user_session(redis, user.username)
    token_response = TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
    return LoginResponse(
        token=token_response,
        user=user,
    )

@router.post("/refresh", status_code=status.HTTP_200_OK, response_model=TokenResponse)
async def refresh(
    request: RefreshRequest,
    redis: RedisClient,
) -> TokenResponse:
    access_token, refresh_token = await auth_service.refresh_access_token(
        refresh_token=request.refresh_token,
        redis=redis
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token
    )

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: CurrentUser,
    redis: RedisClient,
) -> None:
    await auth_service.revoke_session(redis=redis, jti=current_user.jti)
    return None

@router.get("/me", status_code=status.HTTP_200_OK, response_model=UserInfo)
async def me(
    current_user: CurrentUser,
    redis: RedisClient,
    db: DBSession,
) -> UserInfo:
    user = await get_user_by_username(username=current_user.username, db=db)
    return UserInfo.model_validate(user)