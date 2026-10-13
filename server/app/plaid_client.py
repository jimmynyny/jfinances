"""A thin, typed-enough Plaid client over httpx.

Why not plaid-python: the generated SDK wraps every field in a model class
and breaks on each major version. We call a dozen endpoints. A JSON client is
forty lines, testable with a fake transport, and the raw dicts go straight
into our `raw` jsonb columns. Endpoint reference: https://plaid.com/docs/api/

Every request passes `ALLOWED_ENDPOINTS` first: calling Plaid is a billing
decision, so an endpoint that is not on the list never leaves the process.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import settings

log = logging.getLogger(__name__)


class PlaidError(Exception):
    def __init__(self, status: int, body: dict[str, Any]):
        self.status = status
        self.body = body
        self.error_type = body.get("error_type")
        self.error_code = body.get("error_code")
        self.request_id = body.get("request_id")
        super().__init__(f"{self.error_type}/{self.error_code}: {body.get('error_message')}")


class BillingGuardError(RuntimeError):
    """A call to a Plaid endpoint outside `ALLOWED_ENDPOINTS`. Raised before
    any request is made."""


#: Every Plaid endpoint the app may call. Each one is free, or covered by the
#: monthly per-Item price of a product we use (docs/30-plaid.md, "Cost model").
#: Left off on purpose, because each would add a charge:
#:   /accounts/balance/get, /transactions/refresh, /investments/refresh
#:       billed per call;
#:   /transactions/recurring/get
#:       adds the Recurring Transactions subscription to the Item.
#: Adding an endpoint here is a billing decision: update docs/30 with it.
ALLOWED_ENDPOINTS = frozenset({
    "/link/token/create",
    "/item/public_token/exchange",
    "/item/get",
    "/item/remove",
    "/item/webhook/update",
    "/institutions/get_by_id",
    "/accounts/get",
    "/transactions/sync",                 # Transactions
    "/investments/holdings/get",          # Investments Holdings
    "/investments/transactions/get",      # Investments Transactions (also adds Holdings)
    "/liabilities/get",                   # Liabilities
    "/webhook_verification_key/get",
})
#: Test helpers; allowed only against sandbox.plaid.com.
SANDBOX_ENDPOINTS = frozenset({"/sandbox/item/fire_webhook", "/sandbox/public_token/create"})



#: What each "Connect" button asks Plaid for.
#:
#: Plaid hides every institution that does not support ALL of `products`, so
#: each kind requires exactly one product. The rest go in
#: `required_if_supported_products`: Plaid adds them only when the institution
#: AND the accounts the user selects support them, and bills them only then.
#: Requiring all three at once would hide Robinhood and the 529 plans (no
#: liabilities) and investment-less banks from Link.
LINK_KINDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "banking": ("transactions", ("liabilities", "investments")),
    "investments": ("investments", ("transactions", "liabilities")),
}


def link_product_plan(kind: str, enabled: list[str]) -> tuple[list[str], list[str]]:
    """(products, required_if_supported_products) for a link kind, limited to
    the products PLAID_PRODUCTS enables."""
    if kind not in LINK_KINDS:
        raise ValueError(f"unknown link kind {kind!r}; expected one of {sorted(LINK_KINDS)}")
    primary, extras = LINK_KINDS[kind]
    if primary not in enabled:
        raise ValueError(f"link kind {kind!r} needs the {primary!r} product, which PLAID_PRODUCTS disables")
    return [primary], [p for p in extras if p in enabled]


class PlaidClient:
    def __init__(self, *, base_url: str | None = None, client_id: str | None = None,
                 secret: str | None = None, transport: httpx.BaseTransport | None = None,
                 timeout: float = 60.0):
        s = settings()
        self.base_url = (base_url or s.plaid_base_url).rstrip("/")
        self.client_id = client_id if client_id is not None else s.plaid_client_id
        self.secret = secret if secret is not None else s.plaid_secret
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout, transport=transport,
                                  headers={"Content-Type": "application/json",
                                           "Plaid-Version": "2020-09-14"})

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        sandbox = urlparse(self.base_url).hostname == "sandbox.plaid.com"
        if path not in ALLOWED_ENDPOINTS and not (sandbox and path in SANDBOX_ENDPOINTS):
            raise BillingGuardError(f"refusing Plaid {path}: not in plaid_client.ALLOWED_ENDPOINTS")
        payload = {"client_id": self.client_id, "secret": self.secret, **(body or {})}
        resp = self._http.post(path, json=payload)
        data = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            raise PlaidError(resp.status_code, data)
        return data

    # --- link ---------------------------------------------------------------
    def link_token_create(self, *, user_id: str, access_token: str | None = None,
                          kind: str = "banking") -> dict[str, Any]:
        s = settings()
        body: dict[str, Any] = {
            "user": {"client_user_id": user_id},
            "client_name": "Mooney Household Ledger",
            "language": "en",
            "country_codes": s.plaid_country_codes,
            "webhook": s.plaid_webhook_url,
            "redirect_uri": s.plaid_redirect_uri,
        }
        if access_token:
            body["access_token"] = access_token          # update mode
            body["update"] = {"account_selection_enabled": True}
        else:
            products, extras = link_product_plan(kind, s.plaid_products)
            body["products"] = products
            if extras:
                body["required_if_supported_products"] = extras
            if "transactions" in products + extras:
                body["transactions"] = {"days_requested": s.plaid_days_requested}
        return self.post("/link/token/create", body)

    def item_public_token_exchange(self, public_token: str) -> dict[str, Any]:
        return self.post("/item/public_token/exchange", {"public_token": public_token})

    # --- item ---------------------------------------------------------------
    def item_get(self, access_token: str) -> dict[str, Any]:
        return self.post("/item/get", {"access_token": access_token})

    def item_remove(self, access_token: str) -> dict[str, Any]:
        return self.post("/item/remove", {"access_token": access_token})

    def item_webhook_update(self, access_token: str, webhook: str) -> dict[str, Any]:
        return self.post("/item/webhook/update", {"access_token": access_token, "webhook": webhook})

    def institutions_get_by_id(self, institution_id: str) -> dict[str, Any]:
        return self.post("/institutions/get_by_id",
                         {"institution_id": institution_id,
                          "country_codes": settings().plaid_country_codes})

    # --- accounts -----------------------------------------------------------
    def accounts_get(self, access_token: str) -> dict[str, Any]:
        return self.post("/accounts/get", {"access_token": access_token})

    # --- transactions -------------------------------------------------------
    def transactions_sync(self, access_token: str, cursor: str | None, count: int = 500) -> dict[str, Any]:
        body: dict[str, Any] = {"access_token": access_token, "count": count,
                                "options": {"include_personal_finance_category": True,
                                            "include_logo_and_counterparty_beta": True}}
        if cursor:
            body["cursor"] = cursor
        return self.post("/transactions/sync", body)

    # --- investments --------------------------------------------------------
    def investments_holdings_get(self, access_token: str) -> dict[str, Any]:
        return self.post("/investments/holdings/get", {"access_token": access_token})

    def investments_transactions_get(self, access_token: str, start_date: str, end_date: str,
                                     offset: int = 0, count: int = 500) -> dict[str, Any]:
        return self.post("/investments/transactions/get",
                         {"access_token": access_token, "start_date": start_date,
                          "end_date": end_date, "options": {"offset": offset, "count": count}})

    # --- liabilities --------------------------------------------------------
    def liabilities_get(self, access_token: str) -> dict[str, Any]:
        return self.post("/liabilities/get", {"access_token": access_token})

    # --- webhooks -----------------------------------------------------------
    def webhook_verification_key_get(self, key_id: str) -> dict[str, Any]:
        return self.post("/webhook_verification_key/get", {"key_id": key_id})

    # --- sandbox ------------------------------------------------------------
    def sandbox_item_fire_webhook(self, access_token: str, webhook_code: str,
                                  webhook_type: str = "TRANSACTIONS") -> dict[str, Any]:
        return self.post("/sandbox/item/fire_webhook",
                         {"access_token": access_token, "webhook_type": webhook_type,
                          "webhook_code": webhook_code})

    def sandbox_public_token_create(self, institution_id: str = "ins_109508") -> dict[str, Any]:
        s = settings()
        return self.post("/sandbox/public_token/create",
                         {"institution_id": institution_id, "initial_products": s.plaid_products,
                          "options": {"webhook": s.plaid_webhook_url}})


_client: PlaidClient | None = None


def plaid() -> PlaidClient:
    global _client
    if _client is None:
        _client = PlaidClient()
    return _client


def reset_client() -> None:
    global _client
    _client = None
