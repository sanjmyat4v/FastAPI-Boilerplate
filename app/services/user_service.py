import logging

from sqlalchemy import select, and_
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


async def _validate_user(db: AsyncSession, email: str) -> None:
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    exists = result.scalar_one_or_none()

    if exists:
        raise ValidationError(f"User with {email} email already exists.")


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
    await _validate_user(db, request.email)

    password_hash = get_password_hash(request.password)

    user_entry = User(
        email=request.email,
        username=request.username,
        password_hash=password_hash,
    )
    db.add(user_entry)
    await db.flush()
    await db.refresh(user_entry)

    return RegisterUserResponse(
        id=user_entry.id,
        email=user_entry.email,
        username=user_entry.username,
    )