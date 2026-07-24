from pydantic import BaseModel, Field, field_validator, field_serializer
from app.schemas.user_schemas import UserInfo

from datetime import datetime
from app.shared.utils.datetime import to_ulaanbaatar


class LoginRequest(BaseModel):
    identifier: str = Field(
        ...,
        description="Username or email address",
        examples=["johne_doe", "john@example.com"],
        max_length=255,
    )
    password: str = Field(
        ...,
        description="Plain text password",
        examples=["SecurePass123!"],
        max_length=255,
    )

    model_config = {"from_attributes": True}

class TokenResponse(BaseModel):
    access_token: str = Field(
        ...,
        description="Short-lived JWT access token",
    )
    refresh_token: str = Field(
        ...,
        description="Long-lived opaque refresh token",
    )
    token_type: str = Field(
        default="bearer",
        description="Token authorization type",
        examples=["bearer"],
    )

class LoginResponse(BaseModel):
    token: TokenResponse
    user: UserInfo

    model_config = {"from_attributes": True}

class RefreshRequest(BaseModel):
    refresh_token: str = Field(
        ...,
        description="Refresh token for re-issue access token",
    )

    model_config = {"from_attributes": True}