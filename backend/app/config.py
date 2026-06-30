import os

from dotenv import dotenv_values
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env values into a dict for dynamic lookups (provider credentials etc.)
_ENV_VALUES: dict[str, str | None] = dotenv_values(".env")


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "sqlite:///./app.db"
    router_api_keys: str = "demo-router-key"
    allowed_origins: str = "http://localhost:5159,http://localhost:5173"

    # v1.4.0: Admin console auth
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_expire_minutes: int = 1440  # 24 hours
    admin_user: str = "admin"
    admin_password: str = "admin123"   # override via ADMIN_PASSWORD env var
    router_secret_key: str = ""
    provider_timeout_internal_s: float = 15.0
    provider_timeout_external_s: float = 300.0
    request_type_timeout_ms: str = (
        "tool_use=180000,"
        "long_context=300000,"
        "report=300000,"
        "mcp_search=300000,"
        "batch=600000"
    )

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def provider_env_key(provider_name: str, suffix: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_"
        for char in provider_name.upper()
    )
    return f"PROVIDER_{normalized}_{suffix}"


def get_provider_runtime_config(provider_name: str) -> dict[str, str | None]:
    base_url_key = provider_env_key(provider_name, "BASE_URL")
    api_key_key = provider_env_key(provider_name, "API_KEY")
    return {
        "base_url": os.getenv(base_url_key) or _ENV_VALUES.get(base_url_key),
        "api_key": os.getenv(api_key_key) or _ENV_VALUES.get(api_key_key),
    }


def get_allowed_router_api_keys() -> set[str]:
    keys = {
        item.strip()
        for item in settings.router_api_keys.split(",")
        if item.strip()
    }
    if settings.app_env.lower() == "production" and (
        not keys or "demo-router-key" in keys
    ):
        raise RuntimeError("ROUTER_API_KEYS must be set to non-demo values in production")
    return keys
