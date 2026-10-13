import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from server.app.auth import human
from server.app.auth.errors import AuthError


@pytest.fixture
def rsa_key(monkeypatch):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    pub = priv.public_key()

    class FakeJWKS:
        def get_signing_key_from_jwt(self, token):
            return SimpleNamespace(key=pub)

    monkeypatch.setattr(human, "_jwks", lambda: FakeJWKS())
    return pem


def make(pem, **over):
    claims = {"email": "Jimmy@Example.com", "aud": "aud-two", "iss": "https://testteam.cloudflareaccess.com",
              "iat": int(time.time()), "exp": int(time.time()) + 600}
    claims.update(over)
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "k"})


def test_valid(rsa_key):
    claims = human.verify_access_jwt(make(rsa_key))
    assert claims["email"] == "Jimmy@Example.com"


def test_wrong_aud(rsa_key):
    with pytest.raises(AuthError):
        human.verify_access_jwt(make(rsa_key, aud="someone-else"))


def test_wrong_iss(rsa_key):
    with pytest.raises(AuthError):
        human.verify_access_jwt(make(rsa_key, iss="https://evil.cloudflareaccess.com"))


def test_expired(rsa_key):
    with pytest.raises(AuthError):
        human.verify_access_jwt(make(rsa_key, exp=int(time.time()) - 5))


def test_missing_token_without_dev_login():
    class S:
        def execute(self, *a, **k):
            raise AssertionError("should not query")
    with pytest.raises(AuthError) as e:
        human.authenticate_human({}, {}, S())
    assert e.value.status == 401
