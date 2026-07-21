import secrets
from functools import lru_cache
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="development")
    app_version: str = Field(default="1.0.0")

    # JWT
    jwt_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description=(
            "HS256 signing secret. Set explicitly — random default "
            "resets on every restart. "
            "Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
        ),
    )
    access_token_expire_minutes: int = Field(default=60, ge=1)
    refresh_token_expire_days: int = Field(default=30, ge=1)


    # Database
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=3306)
    db_root_password: str = Field(default="")
    db_name: str = Field(default="d_db")
    db_user: str = Field(default="db_user")
    db_password: str = Field(default="")
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=100)
    db_pool_timeout: int = Field(default=30, ge=5, le=300)

    # Redis
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")

    # -------------------------------------------------------------------------
    # Rate Limiting
    # -------------------------------------------------------------------------
    rate_limit_max: int = Field(default=1000, ge=1)

    @computed_field
    @property
    def redis_url(self) -> str:
        return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/0"

    tz: str = Field(default="Asia/Ulaanbaatar")

    @computed_field
    @property
    def database_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()