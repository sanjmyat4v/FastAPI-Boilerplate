from datetime import datetime
from enum import Enum
from typing import Any, Literal
from app.shared.utils.datetime import to_ulaanbaatar

from pydantic import BaseModel, Field, field_validator, model_validator, field_serializer

class UserInfo(BaseModel):
    @field_serializer("created_at", when_used="always")
    def serialize_datetime(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return to_ulaanbaatar(dt).isoformat()
    
    id: str
    email: str
    username: str
    is_active: bool
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class RegisterUserRequest(BaseModel):
    email: str = Field(
        ...,
        max_length=255,
        examples=["user@example.com"],
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        description="User's email address.",
    )
    username: str = Field(
        ...,
        max_length=100,
        examples=["user1"],
        description="Username.",
    )
    password: str = Field(
        ...,
        max_length=255,
        examples=["SupeSecret123!"],
        description="User's password",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    model_config = {
        "str_strip_whitespace": True,
        "extra": "forbid",
    }

class RegisterUserResponse(BaseModel):
    id: str
    email: str
    username: str

    model_config = {"from_attributes": True}