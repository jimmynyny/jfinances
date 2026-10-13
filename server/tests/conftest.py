from __future__ import annotations

import base64
import os

import pytest

from server.app import db
from server.app.config import reset_settings_cache

TEST_KEY = base64.urlsafe_b64encode(b"\x01" * 32).decode()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", TEST_KEY)
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("PLAID_CLIENT_ID", "cid")
    monkeypatch.setenv("PLAID_SECRET", "sec")
    monkeypatch.setenv("CF_ACCESS_TEAM", "testteam")
    monkeypatch.setenv("CF_ACCESS_AUD", "aud-one,aud-two")
    monkeypatch.setenv("ALLOWED_USERS", "jimmy@example.com,wife@example.com")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://fin.example.com")
    monkeypatch.setenv("HOOKS_BASE_URL", "https://hooks.example.com")
    monkeypatch.delenv("DEV_LOGIN_EMAIL", raising=False)
    reset_settings_cache()
    db.reset_engine_cache()
    yield
    reset_settings_cache()
    db.reset_engine_cache()


def pg_url() -> str | None:
    """A real Postgres for integration tests, if one is reachable."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg
        with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), connect_timeout=2):
            return url
    except Exception:  # noqa: BLE001
        return None


def migrate(url: str, *, fresh: bool = False) -> None:
    """Bring the test database to head (optionally from scratch) so a suite
    never depends on another suite having migrated first."""
    import subprocess
    import sys
    from pathlib import Path
    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    env = {**os.environ, "DATABASE_URL": url, "APP_ENV": "local"}
    if fresh:
        subprocess.check_call([sys.executable, "-m", "alembic", "-c", str(ini), "downgrade", "base"], env=env)
    subprocess.check_call([sys.executable, "-m", "alembic", "-c", str(ini), "upgrade", "head"], env=env)
