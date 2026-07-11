import os
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

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


_STARTUP_TIME = datetime.now(UTC)
_STARTUP_PROCESS_ENV = dict(os.environ)
_DIRECT_ENV_DEFAULTS = {
    "CB_FAILURE_THRESHOLD": "5",
    "CB_RECOVERY_TIMEOUT_S": "60",
    "DEBUG": "false",
    "LOG_FORMAT": "json",
    "LOG_RETENTION_DAYS": "90",
    "PORT": "8000",
    "ROUTER_AUTO_OPTIMIZE": "false",
}
_SECRET_MARKERS = ("API_KEY", "PASSWORD", "SECRET", "TOKEN", "DATABASE_URL")


def _is_sensitive_env(name: str) -> bool:
    upper = name.upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def _mask_environment_value(name: str, value: str | None) -> tuple[str | None, bool]:
    """Mask secrets before they cross the backend API boundary."""
    if value in (None, ""):
        return value, _is_sensitive_env(name)
    if not _is_sensitive_env(name):
        return value, False
    if name.upper() == "DATABASE_URL":
        try:
            parsed = urlsplit(value)
            if parsed.password is not None:
                username = parsed.username or ""
                hostname = parsed.hostname or ""
                port = f":{parsed.port}" if parsed.port else ""
                auth = f"{username}:••••@" if username else "••••@"
                return urlunsplit((parsed.scheme, f"{auth}{hostname}{port}", parsed.path, parsed.query, parsed.fragment)), True
        except ValueError:
            pass
    if name.upper() == "ROUTER_API_KEYS":
        count = len([item for item in value.split(",") if item.strip()])
        return f"•••••••• ({count} key{'s' if count != 1 else ''} configured)", True
    return "•••••••• (configured)", True


def _environment_category(name: str) -> str:
    upper = name.upper()
    if upper.startswith("PROVIDER_"):
        return "provider"
    if "DATABASE" in upper or upper.startswith("MYSQL_"):
        return "database"
    if any(marker in upper for marker in ("JWT", "SECRET", "PASSWORD", "API_KEY", "TOKEN", "ALLOWED_ORIGINS")):
        return "security"
    if any(marker in upper for marker in ("TIMEOUT", "CB_", "ROUTER_AUTO_OPTIMIZE")):
        return "routing"
    if any(marker in upper for marker in ("LOG_", "DEBUG")):
        return "observability"
    return "runtime"


def get_startup_environment_snapshot() -> dict:
    """Return the immutable, sanitized configuration captured at process start."""
    setting_names = {field_name.upper() for field_name in Settings.model_fields}
    provider_names = {
        name
        for name in set(_STARTUP_PROCESS_ENV) | set(_ENV_VALUES)
        if name.startswith("PROVIDER_")
    }
    names = setting_names | provider_names | set(_DIRECT_ENV_DEFAULTS) | set(_ENV_VALUES)
    items = []
    for name in sorted(names):
        field_name = name.lower()
        if name in _STARTUP_PROCESS_ENV:
            raw_value = _STARTUP_PROCESS_ENV[name]
            source = "process_env"
            configured = True
        elif name in _ENV_VALUES:
            raw_value = _ENV_VALUES[name]
            source = "dotenv"
            configured = raw_value not in (None, "")
        elif field_name in Settings.model_fields:
            raw_value = str(getattr(settings, field_name))
            source = "default"
            configured = False
        else:
            raw_value = _DIRECT_ENV_DEFAULTS.get(name)
            source = "default"
            configured = False

        value, sensitive = _mask_environment_value(name, raw_value)
        items.append({
            "name": name,
            "value": value,
            "source": source,
            "configured": configured,
            "sensitive": sensitive,
            "category": _environment_category(name),
            "restart_required": True,
        })

    return {
        "startup_time": _STARTUP_TIME.isoformat(),
        "dotenv_path": str(Settings.model_config.get("env_file", ".env")),
        "items": items,
    }


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
