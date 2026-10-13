import os

import pytest

from server.app import crypto


def test_round_trip():
    key = os.urandom(32)
    blob = crypto.encrypt("access-sandbox-abc", key)
    assert blob[:1] == b"\x01"
    assert crypto.decrypt(blob, key) == "access-sandbox-abc"


def test_wrong_key_fails():
    blob = crypto.encrypt("x", os.urandom(32))
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        crypto.decrypt(blob, os.urandom(32))


def test_distinct_nonces():
    key = os.urandom(32)
    assert crypto.encrypt("same", key) != crypto.encrypt("same", key)


def test_bad_key_length():
    with pytest.raises(ValueError):
        crypto.encrypt("x", b"short")


def test_redaction():
    from server.app.logging import redact
    s = "token access-production-0123456789abcdef0123456789abcdef and eyJabcdefghijk.eyJabcdefghijk.sigsigsigsig"
    out = redact(s)
    assert "access-production" not in out and "eyJ" not in out
