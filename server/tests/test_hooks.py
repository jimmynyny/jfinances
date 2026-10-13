"""The hooks service end to end against Postgres: a signed webhook is recorded
and routed; an unsigned one is rejected before touching the database."""
from __future__ import annotations

import hashlib
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from jwt.algorithms import ECAlgorithm

from server.app import db
from server.app.config import reset_settings_cache
from server.app.services import plaid_webhooks as wv
from server.tests.conftest import migrate, pg_url

URL = pg_url()
pytestmark = pytest.mark.skipif(URL is None, reason="TEST_DATABASE_URL not reachable")


@pytest.fixture
def signer(monkeypatch):
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())
    jwk = json.loads(ECAlgorithm.to_jwk(priv.public_key()))
    jwk["kid"] = "k1"
    monkeypatch.setattr(wv.key_cache, "_fetch", lambda kid: jwk)
    wv.key_cache.clear()

    def sign(body: bytes) -> str:
        return jwt.encode({"iat": int(time.time()), "request_body_sha256": hashlib.sha256(body).hexdigest()},
                          pem, algorithm="ES256", headers={"kid": "k1"})
    return sign


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    reset_settings_cache()
    db.reset_engine_cache()
    migrate(URL)
    from server.app.hooks import app
    with TestClient(app) as c:
        yield c


def test_unsigned_rejected(client):
    r = client.post("/plaid/webhook", content=b'{"webhook_type":"ITEM"}')
    assert r.status_code == 401


def test_signed_recorded(client, signer):
    body = json.dumps({"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE",
                       "item_id": "item-unknown", "environment": "sandbox"}).encode()
    r = client.post("/plaid/webhook", content=body,
                    headers={"Plaid-Verification": signer(body), "Content-Type": "application/json"})
    assert r.status_code == 200
    from sqlalchemy import select

    from server.app.models import WebhookEvent
    with db.session() as sess:
        ev = sess.execute(select(WebhookEvent).order_by(WebhookEvent.received_at.desc())).scalars().first()
        assert ev is not None and ev.webhook_code == "SYNC_UPDATES_AVAILABLE" and ev.processed_at is not None


def test_tampered_rejected(client, signer):
    body = b'{"webhook_type":"ITEM","webhook_code":"ERROR"}'
    r = client.post("/plaid/webhook", content=b'{"webhook_type":"ITEM","webhook_code":"ERROR","x":1}',
                    headers={"Plaid-Verification": signer(body)})
    assert r.status_code == 401
