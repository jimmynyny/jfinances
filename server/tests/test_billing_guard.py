"""Calling Plaid is a billing decision: only allowlisted endpoints leave the process.

Per-call products (real-time Balance, the refresh endpoints) and products we
don't use (Recurring Transactions) would add charges, so the client refuses
them before any request is made.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from server.app import plaid_client as pc


def _client(base_url: str, seen: list[str]) -> pc.PlaidClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"ok": True})
    return pc.PlaidClient(base_url=base_url, client_id="cid", secret="sec", transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("path", [
    "/accounts/balance/get",       # Balance: per call, not in the contract
    "/transactions/refresh",       # per call
    "/investments/refresh",        # per call
    "/transactions/recurring/get",  # adds the Recurring Transactions subscription
    "/auth/get",                   # products we never use
    "/identity/get",
])
def test_billed_endpoints_never_leave_the_process(path):
    seen: list[str] = []
    with pytest.raises(pc.BillingGuardError):
        _client("https://production.plaid.com", seen).post(path, {"access_token": "access-x"})
    assert seen == []


def test_allowed_endpoint_goes_through():
    seen: list[str] = []
    assert _client("https://production.plaid.com", seen).post("/accounts/get", {"access_token": "a"}) == {"ok": True}
    assert seen == ["/accounts/get"]


def test_sandbox_helpers_only_reach_sandbox():
    seen: list[str] = []
    with pytest.raises(pc.BillingGuardError):
        _client("https://production.plaid.com", seen).post("/sandbox/item/fire_webhook", {})
    _client("https://sandbox.plaid.com", seen).post("/sandbox/item/fire_webhook", {})
    assert seen == ["/sandbox/item/fire_webhook"]


def test_every_endpoint_the_client_calls_is_allowlisted():
    src = Path(pc.__file__).read_text()
    called = set(re.findall(r'self\.post\("(/[^"]+)"', src))
    assert len(called) >= 10, called
    assert called <= pc.ALLOWED_ENDPOINTS | pc.SANDBOX_ENDPOINTS, called - pc.ALLOWED_ENDPOINTS
    assert not hasattr(pc.PlaidClient, "accounts_balance_get")
