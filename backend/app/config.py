from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "dev"
    database_url: str = "sqlite:///./app.db"

    # v1.4.0: Admin console auth
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_expire_minutes: int = 120
    admin_user: str = "admin"
    admin_password: str = "admin123"   # override via ADMIN_PASSWORD env var

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
