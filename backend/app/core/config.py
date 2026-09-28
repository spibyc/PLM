from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables prefixed PLM_."""

    model_config = SettingsConfigDict(env_prefix="PLM_", extra="ignore")

    database_url: str
    filestore_path: str = "/data/filestore"
    public_base_url: str = "http://localhost:8081"
    environment: str = "production"
    log_level: str = "INFO"

    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    cookie_secure: bool = True
    login_max_failures: int = 5
    lockout_minutes: int = 15
    login_rate_limit_per_ip: int = 30  # attempts per 5 minutes per process
    password_min_length: int = 12

    max_upload_mb: int = 50
    enforce_separation_of_duties: bool = True
    skip_schema_check: bool = False

    app_version: str = "0.3.1"
    git_commit: str = "unknown"
    build_time: str = "unknown"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
