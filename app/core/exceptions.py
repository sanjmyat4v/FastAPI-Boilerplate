from typing import Any

class BaseException(Exception):
    error_code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

# Authentication errors 401
class AuthTokenMissingError(BaseException):
    error_code = "AUTH_TOKEN_MISSING"
    status_code = 401

    def __init__(self) -> None:
        super().__init__("Authorization header is missing.")

class AuthTokenInvalidError(BaseException):
    error_code = "AUTH_TOKEN_INVALID"
    status_code = 401

    def __init__(self, message: str = "Token is invalid or expired.") -> None:
        super().__init__(message)

class InvalidCredentialsError(BaseException):
    error_code = "INVALID_CREDENTIALS"
    status_code = 401

    def __init__(self, message: str = "Invalid credentials.") -> None:
        super().__init__(message)

# Forbidden Errors 403
class ForbiddenError(BaseException):
    error_code = "FORBIDDEN"
    status_code = 403

    def __init__(self) -> None:
        super().__init__("You do not have permission to access this resource.")


# Method not allowed errors 405
class ItemDeleteForbiddenError(BaseException):
    error_code = "METHOD_NOT_ALLOWED"
    status_code = 405

    def __init__(self, method: str) -> None:
        super().__init__(f"{method} operations are not permitted.")



# Validation errors 422
class ValidationError(BaseException):
    error_code: str = "VALIDATION_ERROR"
    status_code: int = 422

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details)

# Not found error 404
class NotFoundError(BaseException):
    error_code = "ITEM_NOT_FOUND"
    status_code = 404

    def __init__(self, item: str) -> None:
        super().__init__(f"{item} not found.")

# User not found error 404
class UserNotFoundError(BaseException):
    error_code = "USER_NOT_FOUND"
    status_code = 404

    def __init__(self, message: str) -> None:
        super().__init__(message)


# Rate limit error
# TODO: Implement rate limit exception properly
class RateLimitExceededError(BaseException):
    error_code = "RATE_LIMIT_EXCEEDED"
    status_code = 429

    def __init__(self, user_email: str, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit exceeded for user {user_email}. " 
            f"Retry after {retry_after_seconds} seconds."
        )

# Dependency failures 503
class DatabaseUnavailableError(BaseException):
    error_code = "DATABASE_UNAVAILABLE"
    status_code = 503

    def __init__(self) -> None:
        super().__init__("Database is currently unavailable. Pleasy retry shortly.")

class CacheUnavailableError(BaseException):
    error_code = "CACHE_UNAVAILABLE"
    status_code = 503

    def __init__(self) -> None:
        super().__init__("Cache layer is currently unavailable.")