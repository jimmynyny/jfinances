"""Plaid webhook signature verification (docs/40-auth-and-security.md §3).

Plaid signs every webhook with an ES256 JWT in the `Plaid-Verification`
header. The JWT's `kid` names a key we fetch from
`/webhook_verification_key/get` and cache. The payload carries `iat` and
`request_body_sha256`; we require the token to be under five minutes old and
the hash to match the RAW request body, compared in constant time.

Keys are cached for a day; a `kid` we have not seen forces a fetch; a key
Plaid reports as expired is evicted.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from typing import Any

import jwt
from jwt.algorithms import ECAlgorithm

from ..config import settings
from ..plaid_client import PlaidClient, plaid

log = logging.getLogger(__name__)

MAX_AGE_SECONDS = 5 * 60


class WebhookVerificationError(Exception):
    pass


class KeyCache:
    def __init__(self, client_factory=plaid, ttl: float | None = None):
        self._lock = threading.Lock()
        self._keys: dict[str, tuple[dict[str, Any], float]] = {}
        self._client_factory = client_factory
        self._ttl = ttl

    def _fetch(self, kid: str) -> dict[str, Any]:
        client: PlaidClient = self._client_factory()
        data = client.webhook_verification_key_get(kid)
        key = data.get("key") or {}
        if key.get("expired_at") is not None:
            raise WebhookVerificationError(f"key {kid} is expired")
        return key

    def get(self, kid: str) -> dict[str, Any]:
        ttl = self._ttl if self._ttl is not None else settings().plaid_webhook_key_ttl_seconds
        now = time.monotonic()
        with self._lock:
            cached = self._keys.get(kid)
            if cached and now - cached[1] < ttl:
                return cached[0]
        key = self._fetch(kid)
        with self._lock:
            self._keys[kid] = (key, now)
        return key

    def clear(self) -> None:
        with self._lock:
            self._keys.clear()


key_cache = KeyCache()


def body_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def verify(raw_body: bytes, header: str | None, *, cache: KeyCache | None = None,
           now: float | None = None) -> dict[str, Any]:
    """Return the verified JWT claims or raise WebhookVerificationError."""
    cache = cache or key_cache
    if not header:
        raise WebhookVerificationError("missing Plaid-Verification header")
    try:
        unverified = jwt.get_unverified_header(header)
    except jwt.PyJWTError as e:
        raise WebhookVerificationError(f"malformed JWT header: {e}") from e
    if unverified.get("alg") != "ES256":
        raise WebhookVerificationError(f"unexpected alg {unverified.get('alg')!r}")
    kid = unverified.get("kid")
    if not kid:
        raise WebhookVerificationError("JWT has no kid")

    jwk = cache.get(kid)
    try:
        public_key = ECAlgorithm.from_jwk(jwk)
        claims = jwt.decode(header, public_key, algorithms=["ES256"],
                            options={"require": ["iat", "request_body_sha256"],
                                     "verify_exp": False, "verify_aud": False})
    except (jwt.PyJWTError, ValueError) as e:
        raise WebhookVerificationError(f"signature rejected: {e}") from e

    current = now if now is not None else time.time()
    if current - float(claims["iat"]) > MAX_AGE_SECONDS:
        raise WebhookVerificationError("webhook is older than 5 minutes")
    expected = str(claims["request_body_sha256"])
    actual = body_sha256(raw_body)
    if not hmac.compare_digest(expected.encode(), actual.encode()):
        raise WebhookVerificationError("body hash mismatch")
    return claims
