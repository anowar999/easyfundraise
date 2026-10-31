from functools import lru_cache

from pydantic import AliasChoices, Field
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
    # Sign-in links by email (and other account email). Without SMTP, dev shows the link on screen instead.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "EasyFundraise <hello@easyfundraise.com>"

    session_days: int = 30
    # AUTH-03: base64 32-byte key for AES-256-GCM token encryption. Empty = derived from secret_key (dev only).
    token_key: str = ""
    # MAIL-01: "google" sends through the Gmail API; "fake" records sends locally (dev/tests, never prod).
    gmail_mode: str = "google"
    # TRK-01: public base URL for the open pixel (dedicated subdomain in prod, the API itself in dev).
    tracking_base_url: str = "http://localhost:3000/api"
    # §9 AI layer. The Anthropic SDK reads ANTHROPIC_API_KEY itself; this only turns the AI paths on.
    ai_enabled: bool = True
    # Read from .env too (pydantic-settings doesn't export .env to os.environ, which the SDK reads)
    anthropic_api_key: str = Field("", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "EF_ANTHROPIC_API_KEY"))
    ai_model_frontier: str = "claude-opus-5-5"
    ai_model_small: str = "claude-haiku-5-5"
    # §6 billing
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    admin_mfa: bool = False  # AUTH-08: forced on in prod
    admin_emails: str = ""  # comma-separated; these users get is_admin on login

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def admin_mfa_required(self) -> bool:
        return self.admin_mfa or self.is_prod

    @property
    def gmail_fake(self) -> bool:
        return self.gmail_mode == "fake" and not self.is_prod

    @property
    def dev_login_enabled(self) -> bool:
        return self.dev_login and not self.is_prod


@lru_cache
def get_settings() -> Settings:
    return Settings()
