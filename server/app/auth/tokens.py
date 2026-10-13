"""Device credentials for the API hostname (future iOS app).

A phone cannot complete an interactive Access login every day, so after one
Access-protected linking step it receives a token WE issue. Only the SHA-256
of the token is stored. The token resolves to a `users` row and goes through
the same allowlist check as an Access session, so disabling the user disables
the phone on its next request.

The issuing endpoints are dashboard-only (`/api/v1/tokens`, Access-authed).
The phone link flow itself (deep link + nonce) is deferred; see
docs/40-auth-and-security.md §5.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import UTC, datetime

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


def _throttle(client_ip: str) -> None:
    now = time.monotonic()
    with _throttle_lock:
        q = _bad_attempts.setdefault(client_ip, deque())
        while q and now - q[0] > _THROTTLE_WINDOW:
            q.popleft()
        if len(q) >= _THROTTLE_MAX:
            raise AuthError(Code.BAD_TOKEN, "too many bad tokens", status=429)


def _record_bad(client_ip: str) -> None:
    with _throttle_lock:
        _bad_attempts.setdefault(client_ip, deque()).append(time.monotonic())


def authenticate_bearer(headers, sess: Session, client_ip: str = "?") -> Principal:
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        raise AuthError(Code.NO_CREDENTIAL, "expected 'Authorization: Bearer <token>'")
    _throttle(client_ip)
    presented = auth[7:].strip()
    if len(presented) < 32:
        _record_bad(client_ip)
        raise AuthError(Code.BAD_TOKEN, "token rejected")
    row = sess.execute(
        select(ApiToken, User).join(User, User.id == ApiToken.user_id)
        .where(ApiToken.token_hash == sha256_hex(presented))
    ).first()
    if row is None or row.ApiToken.revoked_at is not None:
        _record_bad(client_ip)
        raise AuthError(Code.BAD_TOKEN, "token rejected")
    row.ApiToken.last_used_at = datetime.now(UTC)
    return principal_for_email(row.User.email, sess, via="token")


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
