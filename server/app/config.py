"""Settings, read once from the environment.

Everything secret lives in Railway service variables (docs/10-architecture.md
§3). Nothing here has a default that would let production boot half-configured:
`validate_for_boot()` is called by the web service at startup and by
`tools/release.py` before migrations, and it refuses placeholders.
"""
from __future__ import annotations

import base64
import functools
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_PREFIX = "REPLACE_ME"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- process -----------------------------------------------------------
    service_role: Literal["web", "hooks", "worker"] = "web"
    app_env: Literal["production", "sandbox", "local"] = "local"
    log_level: str = "info"
    port: int = 8000
    web_workers: int = 2

    # --- database ----------------------------------------------------------
    database_url: str = Field(default="postgresql://localhost/jfinances")

    # --- plaid -------------------------------------------------------------
    plaid_env: Literal["production", "sandbox"] = "sandbox"
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_products: list[str] = ["transactions", "investments", "liabilities"]
    plaid_country_codes: list[str] = ["US"]
    plaid_days_requested: int = 730
    plaid_webhook_key_ttl_seconds: int = 24 * 3600

    # --- crypto ------------------------------------------------------------
    token_encryption_key: str = ""   # urlsafe-base64, 32 bytes
    session_secret: str = ""

    # --- cloudflare access -------------------------------------------------
    cf_access_team: str = ""
    cf_access_aud: str = ""          # comma-separated
    allowed_users: str = ""          # comma-separated emails
    dev_login_email: str | None = None

    # --- hostnames ---------------------------------------------------------
    public_base_url: str = "http://localhost:8000"
    hooks_base_url: str = "http://localhost:8001"
    api_host: str = ""

    # --- frontend ----------------------------------------------------------
    spa_dir: str = "frontend/dist"
    about_page: str = "index.html"

    # --- worker ------------------------------------------------------------
    worker_poll_seconds: float = 5.0
    nightly_sync_utc: str = "03:00"
    daily_snapshot_utc: str = "06:00"
    daily_investments_utc: str = "06:30"
    weekly_liabilities_utc: str = "07:00"   # Mondays
    daily_prices_utc: str = "22:30"         # after US markets close
    daily_valuations_utc: str = "09:00"     # each asset at most once a month (services/valuations.py)

    # --- market data (benchmarks, investment history; docs/30 "Market data") -
    fred_api_key: str = ""
    tiingo_api_key: str = ""

    # --- valuations (offline homes and vehicles, monthly; services/valuations.py) -
    rentcast_api_key: str = ""
    marketcheck_api_key: str = ""
    refresh_min_interval_seconds: int = 600

    @field_validator("plaid_products", "plaid_country_codes", mode="before")
    @classmethod
    def _split_csv(cls, v):
        if isinstance(v, str):
            return [p.strip() for p in v.split(",") if p.strip()]
        return v

    # --- derived -----------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cf_access_audiences(self) -> list[str]:
        return [a.strip() for a in self.cf_access_aud.split(",") if a.strip()]

    @property
    def allowed_user_emails(self) -> list[str]:
        """ALLOWED_USERS lowercased and de-duplicated, IN THE ORDER WRITTEN: the
        first email is the owner (see auth.human.seed_allowed_users)."""
        out: list[str] = []
        for raw in self.allowed_users.split(","):
            email = raw.strip().lower()
            if email and email not in out:
                out.append(email)
        return out

    @property
    def plaid_base_url(self) -> str:
        return {
            "production": "https://production.plaid.com",
            "sandbox": "https://sandbox.plaid.com",
        }[self.plaid_env]

    @property
    def plaid_webhook_url(self) -> str:
        return self.hooks_base_url.rstrip("/") + "/plaid/webhook"

    @property
    def plaid_redirect_uri(self) -> str:
        return self.public_base_url.rstrip("/") + "/link/oauth"

    @property
    def encryption_key_bytes(self) -> bytes:
        raw = base64.urlsafe_b64decode(self.token_encryption_key + "=" * (-len(self.token_encryption_key) % 4))
        if len(raw) != 32:
            raise ValueError("TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return raw

    # --- validation --------------------------------------------------------
    def validate_for_boot(self, role: str | None = None) -> list[str]:
        """Return a list of problems. Empty list means safe to boot.

        Production is strict. Sandbox needs real Plaid sandbox credentials and
        Access too (it is a deployed, internet-facing environment). Local is
        permissive so a laptop can run tests with nothing set.
        """
        role = role or self.service_role
        problems: list[str] = []
        deployed = self.app_env in ("production", "sandbox")

        def missing(name: str, value: str) -> bool:
            return not value or value.startswith(PLACEHOLDER_PREFIX)

        if deployed:
            if missing("PLAID_CLIENT_ID", self.plaid_client_id):
                problems.append("PLAID_CLIENT_ID is unset or a placeholder")
            if missing("PLAID_SECRET", self.plaid_secret):
                problems.append("PLAID_SECRET is unset or a placeholder")
            if self.plaid_env != ("production" if self.is_production else "sandbox"):
                problems.append(f"PLAID_ENV={self.plaid_env} does not match APP_ENV={self.app_env}")
            if role in ("web", "worker"):
                if missing("TOKEN_ENCRYPTION_KEY", self.token_encryption_key):
                    problems.append("TOKEN_ENCRYPTION_KEY is unset")
                else:
                    try:
                        _ = self.encryption_key_bytes
                    except Exception as e:  # noqa: BLE001
                        problems.append(f"TOKEN_ENCRYPTION_KEY invalid: {e}")
            if role == "web":
                if missing("CF_ACCESS_TEAM", self.cf_access_team):
                    problems.append("CF_ACCESS_TEAM is unset")
                if missing("CF_ACCESS_AUD", self.cf_access_aud):
                    problems.append("CF_ACCESS_AUD is unset or a placeholder")
                if missing("SESSION_SECRET", self.session_secret):
                    problems.append("SESSION_SECRET is unset")
                if not self.allowed_user_emails:
                    problems.append("ALLOWED_USERS is empty")
                if self.dev_login_email:
                    problems.append("DEV_LOGIN_EMAIL must not be set in a deployed environment")
                if not self.public_base_url.startswith("https://"):
                    problems.append("PUBLIC_BASE_URL must be https in a deployed environment")
            if role in ("web", "hooks", "worker") and not self.hooks_base_url.startswith("https://"):
                problems.append("HOOKS_BASE_URL must be https in a deployed environment")
        return problems


@functools.lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Tests change the environment between cases."""
    settings.cache_clear()
