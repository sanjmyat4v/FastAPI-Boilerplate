from typing import Any
from pydantic import BaseModel, Field

class ErrorResponse(BaseModel):

    error_code: str = Field(
        ...,
        description="Machine-readable error code.",
        examples=["VALIDATION_ERROR", "AUTH_TOKEN_INVALID", "USER_NOT_FOUND"],
    )
    message: str = Field(
        ...,
        description="Human-readable error description.",
        examples=["Request body or parameters failed schema validation."]
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Validation field errors or debug context. "
            "Omitted (null) in production environments. "
        ),
    )
    request_id: str = Field(
        ...,
        description="UUID for log correlation. Always present on every response.",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "error_code": "VALIDATION_ERROR",
                "message": "Request body or parameters failed schema validation.",
                "details": {
                    "field_errors": {
                        "body -> level": [
                            "Input should be 'DEBUG', 'INFO', 'WARN', 'ERROR' or 'FATAL'"
                        ]
                    }
                },
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
            }
        }
    }