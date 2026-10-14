"""Phone credentials for the API hostname (docs/40 §5).

A phone cannot complete an interactive Access login every day, so after one
Access-protected linking step (auth/mobile.py) it holds a token WE issue.
Only the SHA-256 of the token is stored. The token resolves to a `users` row
and goes through the same allowlist check as an Access session, so disabling
the user disables the phone on its next request.

Listing and revoking are dashboard-only (`/api/v1/tokens`); a phone revokes
its own token with `POST /api/v1/mobile/unlink`.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crypto import random_token, sha256_hex
from ..models import ApiToken, User
from .errors import AuthError, Code
from .human import Principal, principal_for_email

log = logging.getLogger(__name__)

_THROTTLE_WINDOW = 60.0
_THROTTLE_MAX = 20
_throttle_lock = threading.Lock()
_bad_attempts: dict[str, deque[float]] = {}
#: `last_used_at` is written at most this often: a widget polls, and a write
#: per poll buys nothing.
LAST_USED_EVERY = timedelta(minutes=5)


def throttle(client_ip: str) -> None:
    now = time.monotonic()
    with _throttle_lock:
        q = _bad_attempts.setdefault(client_ip, deque())
        while q and now - q[0] > _THROTTLE_WINDOW:
            q.popleft()
        if len(q) >= _THROTTLE_MAX:
            raise AuthError(Code.BAD_TOKEN, "too many bad tokens", status=429)


def record_bad(client_ip: str) -> None:
    with _throttle_lock:
        _bad_attempts.setdefault(client_ip, deque()).append(time.monotonic())
        if len(_bad_attempts) > 10_000:  # a wide scan must not grow this without bound
            _bad_attempts.clear()


def _presented(headers) -> str:
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise AuthError(Code.NO_CREDENTIAL, "expected 'Authorization: Bearer <token>'")
    return auth[7:].strip()


def _find(sess: Session, presented: str, client_ip: str):
    throttle(client_ip)
    if len(presented) < 32:
        record_bad(client_ip)
        raise AuthError(Code.BAD_TOKEN, "token rejected")
    row = sess.execute(
        select(ApiToken, User).join(User, User.id == ApiToken.user_id)
        .where(ApiToken.token_hash == sha256_hex(presented))
    ).first()
    if row is None or row.ApiToken.revoked_at is not None:
        record_bad(client_ip)
        raise AuthError(Code.BAD_TOKEN, "token rejected")
    return row


def authenticate_bearer(headers, sess: Session, client_ip: str = "?") -> Principal:
    row = _find(sess, _presented(headers), client_ip)
    now = datetime.now(UTC)
    if row.ApiToken.last_used_at is None or now - row.ApiToken.last_used_at > LAST_USED_EVERY:
        row.ApiToken.last_used_at = now
    return principal_for_email(row.User.email, sess, via="token")


def revoke_presented(headers, sess: Session, client_ip: str = "?") -> ApiToken:
    """A phone giving its own token back (`POST /mobile/unlink`)."""
    row = _find(sess, _presented(headers), client_ip)
    row.ApiToken.revoked_at = datetime.now(UTC)
    return row.ApiToken


def issue_token(sess: Session, *, user_id, name: str) -> tuple[ApiToken, str]:
    """Create a token. The plaintext is returned ONCE and never stored."""
    plaintext = random_token(32)
    row = ApiToken(user_id=user_id, name=name[:120], token_hash=sha256_hex(plaintext))
    sess.add(row)
    sess.flush()
    return row, plaintext


def revoke_token(sess: Session, *, token_id, user_id) -> bool:
    row = sess.get(ApiToken, token_id)
    if row is None or row.user_id != user_id or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.now(UTC)
    return True
