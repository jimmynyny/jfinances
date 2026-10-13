"""User seeding against a real Postgres: order-driven roles, reconciliation,
disabling, and concurrent seeders (uvicorn runs several workers, and each
seeds at startup; on 2026-10-13 two of them raced and took production down)."""
from __future__ import annotations

import threading

import pytest
from sqlalchemy import delete, select

from server.app import db
from server.app.auth.human import seed_allowed_users
from server.app.config import reset_settings_cache
from server.app.models import User
from server.tests.conftest import migrate, pg_url

URL = pg_url()
pytestmark = pytest.mark.skipif(URL is None, reason="TEST_DATABASE_URL not reachable")


@pytest.fixture
def pg(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    # anna sorts first alphabetically: catches any code that sorts the list.
    monkeypatch.setenv("ALLOWED_USERS", "jimmy@example.com,anna@example.com")
    reset_settings_cache()
    db.reset_engine_cache()
    migrate(URL)
    with db.session() as sess:
        sess.execute(delete(User))
    yield
    with db.session() as sess:
        sess.execute(delete(User))


def users() -> dict[str, tuple[str, bool]]:
    with db.session() as sess:
        return {u.email: (u.role, u.disabled_at is None) for u in sess.execute(select(User)).scalars()}


def test_concurrent_seeders_do_not_collide(pg):
    n = 6
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def run():
        try:
            barrier.wait()
            with db.session() as sess:
                seed_allowed_users(sess)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert users() == {"jimmy@example.com": ("owner", True), "anna@example.com": ("member", True)}


def test_roles_follow_allowed_users_order(pg):
    with db.session() as sess:  # the wrong roles production got on 2026-10-13
        sess.add_all([User(email="anna@example.com", role="owner"), User(email="jimmy@example.com", role="member")])
    with db.session() as sess:
        seed_allowed_users(sess)
    assert users() == {"jimmy@example.com": ("owner", True), "anna@example.com": ("member", True)}


def test_unlisted_user_is_disabled_not_deleted(pg, monkeypatch):
    with db.session() as sess:
        seed_allowed_users(sess)
    monkeypatch.setenv("ALLOWED_USERS", "jimmy@example.com")
    reset_settings_cache()
    with db.session() as sess:
        seed_allowed_users(sess)
    assert users() == {"jimmy@example.com": ("owner", True), "anna@example.com": ("member", False)}
