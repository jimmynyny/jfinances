"""Encryption at rest for Plaid access tokens.

AES-256-GCM with a random 96-bit nonce per value. The stored form is
`nonce || ciphertext || tag`, as one bytea column. The key is
`TOKEN_ENCRYPTION_KEY` (32 random bytes, urlsafe-base64), which only the `web`
and `worker` services hold. A Postgres dump without the key is useless.

Rotation: see docs/60-runbook.md. Tokens carry a one-byte version prefix so a
second key can be introduced without a flag day.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = b"\x01"
_NONCE_LEN = 12


def encrypt(plaintext: str, key: bytes) -> bytes:
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), _VERSION)
    return _VERSION + nonce + ct


def decrypt(blob: bytes, key: bytes) -> str:
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    if not blob or blob[:1] != _VERSION:
        raise ValueError("unknown ciphertext version")
    nonce, ct = blob[1 : 1 + _NONCE_LEN], blob[1 + _NONCE_LEN :]
    return AESGCM(key).decrypt(nonce, ct, _VERSION).decode("utf-8")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def random_token(nbytes: int = 32) -> str:
    """256 random bits, urlsafe. Used for API tokens; only the hash is stored."""
    return secrets.token_urlsafe(nbytes)
