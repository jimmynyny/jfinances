"""Link product plans and per-product refresh gating.

Requiring every product in `products` hides institutions that lack one of
them (Robinhood and 529 plans have no liabilities), and calling a product
endpoint for an Item without that product makes Plaid add and bill it. These
tests pin both behaviours down.
"""
from __future__ import annotations

import json
import uuid

import httpx
import pytest

from server.app.models import PlaidItem
from server.app.plaid_client import PlaidClient, link_product_plan


def test_banking_plan_requires_only_transactions():
    assert link_product_plan("banking", ["transactions", "investments", "liabilities"]) == (
        ["transactions"], ["liabilities", "investments"])


def test_investments_plan_requires_only_investments():
    assert link_product_plan("investments", ["transactions", "investments", "liabilities"]) == (
        ["investments"], ["transactions", "liabilities"])


def test_disabled_products_are_dropped_from_extras():
    assert link_product_plan("banking", ["transactions"]) == (["transactions"], [])


def test_unknown_kind_and_disabled_primary_are_errors():
    with pytest.raises(ValueError):
        link_product_plan("crypto", ["transactions"])
    with pytest.raises(ValueError):
        link_product_plan("investments", ["transactions", "liabilities"])


def _capture_client(seen: list[dict]) -> PlaidClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "body": json.loads(request.content)})
        return httpx.Response(200, json={"link_token": "link-sandbox-x", "expiration": "2030-01-01T00:00:00Z"})
    return PlaidClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("kind,required,extras", [
    ("banking", ["transactions"], ["liabilities", "investments"]),
    ("investments", ["investments"], ["transactions", "liabilities"]),
])
def test_link_token_body_per_kind(kind, required, extras):
    seen: list[dict] = []
    _capture_client(seen).link_token_create(user_id="u1", kind=kind)
    body = seen[0]["body"]
    assert seen[0]["path"] == "/link/token/create"
    assert body["products"] == required
    assert body["required_if_supported_products"] == extras
    assert body["transactions"] == {"days_requested": 730}
    assert body["webhook"] == "https://hooks.example.com/plaid/webhook"
    assert body["redirect_uri"] == "https://fin.example.com/link/oauth"


def test_update_mode_sends_no_products():
    seen: list[dict] = []
    _capture_client(seen).link_token_create(user_id="u1", access_token="access-sandbox-abc")
    body = seen[0]["body"]
    assert body["access_token"] == "access-sandbox-abc"
    assert "products" not in body and "required_if_supported_products" not in body


def test_phone_platforms_get_their_own_oauth_return(monkeypatch):
    """The iPhone returns from an OAuth bank by universal link on the API
    hostname; Android by package name, with no redirect URI at all."""
    from server.app.config import reset_settings_cache

    monkeypatch.setenv("API_HOST", "api.example.com")
    reset_settings_cache()
    seen: list[dict] = []
    c = _capture_client(seen)
    c.link_token_create(user_id="u1", platform="ios")
    assert seen[-1]["body"]["redirect_uri"] == "https://api.example.com/plaid/oauth"
    assert "android_package_name" not in seen[-1]["body"]
    c.link_token_create(user_id="u1", platform="android", access_token="access-sandbox-abc")
    assert seen[-1]["body"]["android_package_name"] == "com.daedalustcg.jfinances"
    assert "redirect_uri" not in seen[-1]["body"]
    c.link_token_create(user_id="u1", platform="web")
    assert seen[-1]["body"]["redirect_uri"] == "https://fin.example.com/link/oauth"
    with pytest.raises(ValueError):
        c.link_token_create(user_id="u1", platform="windows")


def test_ios_link_needs_an_api_host(monkeypatch):
    """Without API_HOST there is no hostname for the universal link: refuse
    rather than mint a token whose OAuth return goes nowhere."""
    monkeypatch.delenv("API_HOST", raising=False)
    from server.app.config import reset_settings_cache
    reset_settings_cache()
    with pytest.raises(ValueError):
        _capture_client([]).link_token_create(user_id="u1", platform="ios")


@pytest.mark.parametrize("products,expected", [
    (["transactions"], ["sync_item"]),
    (["transactions", "liabilities"], ["sync_item", "refresh_liabilities"]),
    (["investments"], ["sync_item", "refresh_investments"]),
    (["transactions", "investments", "liabilities"], ["sync_item", "refresh_investments", "refresh_liabilities"]),
    ([], ["sync_item"]),
])
def test_enqueue_item_refresh_follows_item_products(monkeypatch, products, expected):
    import server.app.jobs.queue as queue
    from server.app.jobs.sync_item import enqueue_item_refresh

    kinds: list[str] = []
    monkeypatch.setattr(queue, "enqueue", lambda sess, kind, payload: kinds.append(kind) or "job")
    item = PlaidItem(id=uuid.uuid4(), item_id="item-x", products=products, access_token_enc=b"")
    assert enqueue_item_refresh(None, item) == "job"
    assert kinds == expected
