"""Humans: Cloudflare Access proves WHO, the `users` table decides WHETHER.

We take exactly one fact from Access, a cryptographically verified email, and
every decision after that is ours. Swapping Access for another identity
provider later is a change to this file only.

Verification (docs/40-auth-and-security.md §2):
- token from `Cf-Access-Jwt-Assertion` header, else `CF_Authorization` cookie
- signature against https://{team}.cloudflareaccess.com/cdn-cgi/access/certs
- `aud` must be one of CF_ACCESS_AUD (a list: each Access app has its own)
- `iss` must be https://{team}.cloudflareaccess.com
- `exp`, `iat`, `aud`, `iss` are all required claims
- email is read from the VERIFIED claims, never from the
  `Cf-Access-Authenticated-User-Email` header, which anyone can send.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import jwt
from jwt import PyJWKClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..models import User
from .errors import AuthError, Code

log = logging.getLogger(__name__)

_JWK_TTL = 3600.0
_jwk_lock = threading.Lock()
_jwk_client: PyJWKClient | None = None
_jwk_fetched_at = 0.0


@dataclass(frozen=True)
class Principal:
    user_id: object
    email: str
    role: str
    via: str                      # "access" | "token" | "dev"
    session_expires_at: datetime | None = None
    display_name: str | None = None


def _jwks() -> PyJWKClient:
    global _jwk_client, _jwk_fetched_at
    s = settings()
    with _jwk_lock:
        if _jwk_client is None or time.monotonic() - _jwk_fetched_at > _JWK_TTL:
            url = f"https://{s.cf_access_team}.cloudflareaccess.com/cdn-cgi/access/certs"
            _jwk_client = PyJWKClient(url, cache_keys=True)
            _jwk_fetched_at = time.monotonic()
        return _jwk_client


def verify_access_jwt(token: str) -> dict:
    s = settings()
    if not (s.cf_access_team and s.cf_access_audiences):
        raise AuthError(Code.NOT_CONFIGURED, "Cloudflare Access is not configured", status=500)
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=s.cf_access_audiences,
            issuer=f"https://{s.cf_access_team}.cloudflareaccess.com",
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as e:
        raise AuthError(Code.BAD_ACCESS_JWT, f"Access token rejected: {e}") from e


def authenticate_human(headers, cookies, sess: Session) -> Principal:
    s = settings()
    token = headers.get("cf-access-jwt-assertion") or cookies.get("CF_Authorization")
    if token:
        claims = verify_access_jwt(token)
        email = (claims.get("email") or "").strip().lower()
        if not email:
            raise AuthError(Code.BAD_ACCESS_JWT, "Access token carries no email")
        expires = datetime.fromtimestamp(int(claims["exp"]), UTC) if claims.get("exp") else None
        return principal_for_email(email, sess, via="access", expires_at=expires)

    if s.dev_login_email and s.app_env == "local":
        log.warning("DEV_LOGIN_EMAIL in use; no Access token presented")
        return principal_for_email(s.dev_login_email.lower(), sess, via="dev")

    raise AuthError(Code.NO_CREDENTIAL, "no Cloudflare Access token")


def principal_for_email(email: str, sess: Session, *, via: str,
                        expires_at: datetime | None = None) -> Principal:
    user = sess.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        raise AuthError(Code.NOT_ALLOWED, f"{email} passed the perimeter but is not an allowed user",
                        status=403)
    if user.disabled_at is not None:
        raise AuthError(Code.NOT_ALLOWED, f"{email} is disabled", status=403)
    user.last_seen_at = datetime.now(UTC)
    return Principal(user_id=user.id, email=user.email, role=user.role, via=via,
                     session_expires_at=expires_at, display_name=user.display_name)


#: Serialises concurrent seeding. uvicorn starts several worker processes and
#: each seeds at startup; without the lock two of them INSERT the same email,
#: one fails its startup, and uvicorn then stops the whole server.
SEED_LOCK_KEY = 0x6A667573  # "jfus"


def seed_allowed_users(sess: Session) -> int:
    """Make `users` match ALLOWED_USERS. Idempotent; safe to run concurrently.

    * Every listed email exists and is enabled.
    * ALLOWED_USERS is authoritative for roles: the FIRST listed email is
      `owner`, every other one is `member`, for new and existing rows alike.
    * An email no longer listed is not deleted (history references it); it gets
      disabled_at, so the person is refused at their next request.
    """
    s = settings()
    allowed = s.allowed_user_emails
    if not allowed:
        return 0
    if sess.get_bind().dialect.name == "postgresql":
        # Held until this transaction commits; a concurrent seeder waits here and
        # then sees the rows this one inserted (READ COMMITTED, per statement).
        sess.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": SEED_LOCK_KEY})
    existing = {u.email: u for u in sess.execute(select(User)).scalars()}
    now = datetime.now(UTC)
    for i, email in enumerate(allowed):
        role = "owner" if i == 0 else "member"
        u = existing.get(email)
        if u is None:
            sess.add(User(email=email, role=role))
            continue
        if u.disabled_at is not None:
            u.disabled_at = None
        if u.role != role:
            log.info("role of %s: %s -> %s (ALLOWED_USERS order)", email, u.role, role)
            u.role = role
    for email, u in existing.items():
        if email not in allowed and u.disabled_at is None:
            u.disabled_at = now
            log.warning("disabled %s: no longer in ALLOWED_USERS", email)
    sess.flush()
    return len(allowed)


def reset_jwks_cache() -> None:
    global _jwk_client, _jwk_fetched_at
    with _jwk_lock:
        _jwk_client = None
        _jwk_fetched_at = 0.0
