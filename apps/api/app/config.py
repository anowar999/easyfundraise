from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="EF_", extra="ignore")

    env: str = "dev"  # dev | uat | prod
    database_url: str = "postgresql+psycopg://ef:ef@localhost:5432/easyfundraise"
    secret_key: str = "dev-insecure-change-me"
    web_origin: str = "http://localhost:3000"

    # AUTH-01: Google OAuth only. Dev login exists so the app is usable before OAuth is configured.
    google_client_id: str = ""
    google_client_secret: str = ""
    dev_login: bool = True

    session_days: int = 30
    admin_emails: str = ""  # comma-separated; these users get is_admin on login

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def dev_login_enabled(self) -> bool:
        return self.dev_login and not self.is_prod


@lru_cache
def get_settings() -> Settings:
    return Settings()
