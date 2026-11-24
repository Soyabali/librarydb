from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Library Management API"
    app_version: str = "1.0.0"
    debug: bool = False
    timezone: str = "Asia/Kolkata"  # library's local day for due dates and fines

    database_url: str
    db_pool_size: int = 5
    db_max_overflow: int = 10

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # JSON list in env, e.g. CORS_ORIGINS=["http://localhost:3000"]
    cors_origins: list[str] = []

    @property
    def sqlalchemy_url(self) -> str:
        """Neon gives a plain postgresql:// URL; SQLAlchemy needs the psycopg 3 driver name."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = "\n".join(
            f"  - {'.'.join(str(p) for p in err['loc']).upper()}: {err['msg']}" for err in exc.errors()
        )
        raise SystemExit(
            "\nConfiguration error - fix these environment variables "
            "(locally in .env, on Render under Service -> Environment):\n" + problems + "\n"
        ) from None
