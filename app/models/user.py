from datetime import datetime

from sqlalchemy import (
    Index,
    String,
    Enum,
    Text,
    Boolean,
    DateTime,
    literal,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.shared.utils.uuid import generate_uuid

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )
    username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Password hash",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(literal(3)),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.current_timestamp(literal(3)),
        onupdate=func.current_timestamp(literal(3)),
    )

    __table_args__ = (
        Index(
            "idx_user_info",
            "id",
            "username",
            "email",
            info={"description": "Get user info."}
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} username={self.username} "
            f"is_active={self.is_active}>"
        )