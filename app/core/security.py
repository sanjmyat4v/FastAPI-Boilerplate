import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pwdlib import PasswordHash

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import get_settings
from app.core.exceptions import AuthTokenInvalidError, AuthTokenMissingError
from app.schemas.common_schemas import AuthenticatedUser

logger = logging.getLogger(__name__)
password_hash = PasswordHash.recommended()


# ---------------------------------------------------------------------------
# Token creation and storage
# ---------------------------------------------------------------------------
def _create_access_token(username: str, jti: str) -> str:
    """
    Issues a short-lived HS-256 access token.

    Payload:
        Payload:
        sub  — Username
        jti  — JWT ID (links to refresh token in Redis)
        type — "access"
    """

    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub":  username,
        "jti":  jti,
        "type": "access",
        "iat":  int(now.timestamp()),
        "exp":  int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> AuthenticatedUser:
    """
    Decodes and validates our own HS256 access token.

    Returns:
        AuthenticatedUser with github_username and jti.

    Raises:
        AuthTokenInvalidError on any failure.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except ExpiredSignatureError:
        raise AuthTokenInvalidError("Access token has expired. Please refresh.")
    except JWTError as exc:
        raise AuthTokenInvalidError(f"Invalid access token: {exc}")
    
    if payload.get("type") != "access":
        raise AuthTokenInvalidError("Token is nor an access token.")
    
    username = payload.get("sub", "")
    jti = payload.get("jti", "")

    if not username or not jti:
        raise AuthTokenInvalidError("Access token is missing required claims.")
    
    return AuthenticatedUser(username=username, jti=jti)

def extract_bearer_token(authorization_header: str | None) -> str:
    if not authorization_header:
        raise AuthTokenMissingError
    parts = authorization_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthTokenInvalidError("Authorization header must be: 'Bearer <token>'")
    return parts[1]


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)