import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "sqlite:///./app.db"
    router_api_keys: str = "demo-router-key"

    model_config = SettingsConfigDict(env_prefix="")


settings = Settings()


def provider_env_key(provider_name: str, suffix: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_"
        for char in provider_name.upper()
    )
    return f"PROVIDER_{normalized}_{suffix}"


def get_provider_runtime_config(provider_name: str) -> dict[str, str | None]:
    return {
        "base_url": os.getenv(provider_env_key(provider_name, "BASE_URL")),
        "api_key": os.getenv(provider_env_key(provider_name, "API_KEY")),
    }


def get_allowed_router_api_keys() -> set[str]:
    return {
        item.strip()
        for item in settings.router_api_keys.split(",")
        if item.strip()
    }
