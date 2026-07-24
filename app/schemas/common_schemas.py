from pydantic import BaseModel, Field

class MessageResponse(BaseModel):
    message: str = Field(
        ...,
        examples=["Logged out successfully."],
    )

class AuthenticatedUser(BaseModel):
    username: str = Field(
        ...,
        description="Authentcated user's username."
    )
    jti: str = Field(
        ...,
        description="Unique token identifier.",
    )