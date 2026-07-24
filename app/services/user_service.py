import logging

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.exceptions import (
    UserNotFoundError,
    ValidationError,
)
from app.schemas.user_schemas import (
    UserInfo,
    RegisterUserRequest,
    RegisterUserResponse,
)
from app.models.user import User
from app.shared.utils.password import get_password_hash

logger = logging.getLogger(__name__)


async def _validate_user(db: AsyncSession, email: str, username: str) -> None:
    stmt = select(User).where(or_(User.email == email, User.username == username))
    result = await db.execute(stmt)
    existing_user = result.scalar_one_or_none()

    if existing_user:
        if existing_user.email == email:
            raise ValidationError(f"User with {email} email already exists.")
        if existing_user.username == username:
            raise ValidationError(f"Username '{username}' is already taken.")

async def get_user_for_auth(
    identifier: str, db: AsyncSession
) -> User | None:
    stmt = select(User).where(
        or_(User.email == identifier, User.username == identifier)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()

async def get_user_by_email_or_username(
    identifier: str, db: AsyncSession
) -> UserInfo:
    """
    Fetches a user by either email or username.
    Useful for login endpoints that accept either credential type.
    """
    condition = or_(User.email == identifier, User.username == identifier)
    return await _get_user_by(
        db,
        condition,
        f"User with identifier '{identifier}' not found.",
    )

async def _get_user_by(
    db: AsyncSession,
    condition: ColumnElement,
    not_found_msg: str,
) -> UserInfo:
    stmt = select(User).where(condition)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()

    if not row:
        raise UserNotFoundError(not_found_msg)

    return UserInfo(
        id=row.id,
        email=row.email,
        username=row.username,
        is_active=row.is_active,
        is_deleted=row.is_deleted,
        created_at=row.created_at,
    )


async def get_user_by_email(email: str, db: AsyncSession) -> UserInfo:
    return await _get_user_by(
        db, User.email == email, f"User with {email} email not found."
    )


async def get_user_by_id(id: str, db: AsyncSession) -> UserInfo:
    return await _get_user_by(
        db, User.id == id, f"User with {id} id not found."
    )


async def get_user_by_username(username: str, db: AsyncSession) -> UserInfo:
    return await _get_user_by(
        db, User.username == username, f"User with {username} username not found."
    )

async def add_user(
    db: AsyncSession,
    request: RegisterUserRequest,
) -> RegisterUserResponse:
    await _validate_user(db, request.email, request.username)

    password_hash = get_password_hash(request.password)

    user_entry = User(
        email=request.email,
        username=request.username,
        password_hash=password_hash,
    )
    db.add(user_entry)
    await db.flush()
    await db.refresh(user_entry)

    return RegisterUserResponse.model_validate(user_entry)