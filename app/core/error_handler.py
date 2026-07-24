import uuid
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import get_settings
from app.core.exceptions import (
    BaseException,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)

def _build_error_response(
    request_id: str,
    error_code: str,
    message: str,
    status_code: int,
    details: dict | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    settings = get_settings()

    body: dict = {
        "error_code": error_code,
        "message": message,
        "request_id": request_id,
    }

    if details is not None and settings.app_env != "production":
        body["details"] = details
    else:
        body["details"] = None
    
    return JSONResponse(
        status_code=status_code,
        content=body,
        headers=headers,
    )

def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))

def register_exception_handlers(app: FastAPI) -> None:
    
    # -------------------------------------------------------------------------
    # domain exceptions (app/core/exceptions.py)
    # -------------------------------------------------------------------------
    @app.exception_handler(BaseException)
    async def lms_exception_handler(
        request: Request,
        exc: BaseException
    ) -> JSONResponse:
        request_id = _get_request_id(request)

        if exc.status_code >= 500:
            logger.error(
                "Server error [%s] request_id=%s: %s",
                exc.error_code,
                request_id,
                exc.message,
                exc_info=True,
            )
        else:
            logger.warning(
                "Client error [%s] request_id=%s: %s",
                exc.error_code,
                request_id,
                exc.message,
            )
        
        # Special case rate limit requires Retry-After header
        extra_headers = None
        if isinstance(exc, RateLimitExceededError):
            extra_headers = {"Retry-After": str(exc.retry_after_seconds)}
        
        return _build_error_response(
            request_id=request_id,
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
            headers=extra_headers,
        )
    
    # -------------------------------------------------------------------------
    # FastAPI / Pydantic request validation errors (HTTP 422)
    # -------------------------------------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = _get_request_id(request)

        logger.warning(
            "Request validation error request_id=%s path=%s: %s",
            request_id,
            request.url.path,
            exc.errors(),
        )

        field_errors: dict[str, list[str]] = {}
        for error in exc.errors():
            # error["loc"] is a tuple like ("body", "field_name") or ("query", "param")
            location = " -> ".join(str(loc) for loc in error["loc"])
            field_errors.setdefault(location, []).append(error["msg"])
        
        return _build_error_response(
            request_id=request_id,
            error_code="VALIDATION_ERROR",
            message="Request body or parameters failed schema validation.",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"field_errors": field_errors},
        )
    
    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_error(
        request: Request,
        exc: PydanticValidationError,
    ) -> JSONResponse:
        request_id = _get_request_id(request)
        logger.error(
            "Unexpected Pydantic validation error request_id=%s: %s",
            request_id,
            str(exc),
            exc_info=True,
        )
        return _build_error_response(
            request_id=request_id,
            error_code="VALIDATION_ERROR",
            message="Internal data validation error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details={"pydantic_errors": exc.errors()}
        )
    

    # -------------------------------------------------------------------------
    # Starlette / FastAPI HTTP exceptions (404, 405, etc.)
    # -------------------------------------------------------------------------
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        request_id = _get_request_id(request)

        code_map: dict[int, str] = {
            400: "BAD_REQUEST",
            401: "AUTH_TOKEN_INVALID",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            429: "RATE_LIMIT_EXCEEDED",
            503: "SERVICE_UNAVAILABLE",
        }
        error_code = code_map.get(exc.status_code, "HTTP_ERROR")

        return _build_error_response(
            request_id=request_id,
            error_code=error_code,
            message=exc.detail or "An HTTP error occured",
            status_code=exc.status_code,
        )
    

    # -------------------------------------------------------------------------
    # Catch-all for any unhandled Python exception (HTTP 500)
    # -------------------------------------------------------------------------
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = _get_request_id(request)

        logger.critical(
            "Unhandled exception request_id=%s path=%s method=%s: %s",
            request_id,
            request.url.path,
            request.method,
            str(exc),
            exc_info=True,
        )

        settings = get_settings()
        details = None
        if settings.app_env != "production":
            details = {"exception_type": type(exc).__name__, "detail": str(exc)}
        
        return _build_error_response(
            request_id=request_id,
            error_code="INTERNAL_ERROR",
            message="An unexpected internal error occured. Please contact support.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )