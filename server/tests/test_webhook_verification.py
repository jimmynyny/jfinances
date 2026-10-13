import hashlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jwt.algorithms import ECAlgorithm

from server.app.services import plaid_webhooks as wv


@pytest.fixture
def keypair():
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    jwk = json.loads(ECAlgorithm.to_jwk(priv.public_key()))
    jwk["kid"] = "kid-1"
    return pem, jwk


class FakeCache(wv.KeyCache):
    def __init__(self, jwk):
        super().__init__(client_factory=lambda: None, ttl=10)
        self.jwk = jwk
        self.fetches = 0

    def _fetch(self, kid):
        self.fetches += 1
        if kid != self.jwk["kid"]:
            raise wv.WebhookVerificationError("unknown kid")
        return self.jwk


def sign(pem, body: bytes, *, iat=None, kid="kid-1", alg="ES256", body_hash=None):
    claims = {"iat": iat if iat is not None else int(time.time()),
              "request_body_sha256": body_hash or hashlib.sha256(body).hexdigest()}
    return jwt.encode(claims, pem, algorithm=alg, headers={"kid": kid})


def test_valid(keypair):
    pem, jwk = keypair
    body = b'{"webhook_type":"TRANSACTIONS","webhook_code":"SYNC_UPDATES_AVAILABLE","item_id":"x"}'
    cache = FakeCache(jwk)
    claims = wv.verify(body, sign(pem, body), cache=cache)
    assert claims["request_body_sha256"] == hashlib.sha256(body).hexdigest()
    wv.verify(body, sign(pem, body), cache=cache)
    assert cache.fetches == 1  # cached


def test_body_tamper(keypair):
    pem, jwk = keypair
    body = b'{"a":1}'
    with pytest.raises(wv.WebhookVerificationError, match="hash"):
        wv.verify(b'{"a":2}', sign(pem, body), cache=FakeCache(jwk))


def test_too_old(keypair):
    pem, jwk = keypair
    body = b"{}"
    with pytest.raises(wv.WebhookVerificationError, match="older"):
        wv.verify(body, sign(pem, body, iat=int(time.time()) - 600), cache=FakeCache(jwk))


def test_wrong_key(keypair):
    pem, jwk = keypair
    other = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with pytest.raises(wv.WebhookVerificationError, match="signature"):
        wv.verify(b"{}", sign(other, b"{}"), cache=FakeCache(jwk))


def test_missing_header(keypair):
    with pytest.raises(wv.WebhookVerificationError):
        wv.verify(b"{}", None, cache=FakeCache(keypair[1]))
