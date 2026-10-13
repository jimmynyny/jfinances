"""End-to-end against a real Postgres when TEST_DATABASE_URL points at one.
Runs migrations, boots the web app with DEV_LOGIN_EMAIL, links a fake item
through a stubbed Plaid client, syncs, snapshots, and reads the overview."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import db
from server.app.config import reset_settings_cache
from server.tests.conftest import migrate, pg_url

URL = pg_url()
pytestmark = pytest.mark.skipif(URL is None, reason="TEST_DATABASE_URL not reachable")



def _jobs():
    from sqlalchemy import select

    from server.app.db import session
    from server.app.models import Job
    with session() as sess:
        return sess.execute(select(Job.kind, Job.status)).all()

class FakePlaid:
    def __init__(self):
        self.webhook_updates = []

    def link_token_create(self, **kw):
        return {"link_token": "link-sandbox-fake", "expiration": "2030-01-01T00:00:00Z"}

    def item_public_token_exchange(self, public_token):
        return {"access_token": "access-sandbox-fake-token-0000000000000000", "item_id": "item-1"}

    def institutions_get_by_id(self, iid):
        return {"institution": {"name": "First Platypus Bank"}}

    def accounts_get(self, token):
        # Like real Plaid: the Item reports the products Link initialised. A banking link to
        # this institution got liabilities (it has a card) but not investments.
        return {"item": {"institution_id": "ins_1", "institution_name": "First Platypus Bank",
                         "products": ["transactions", "liabilities"]},
                "accounts": [
                    {"account_id": "acc-chk", "name": "Plaid Checking", "mask": "0000", "type": "depository",
                     "subtype": "checking",
                     "balances": {"current": 110.5, "available": 100, "iso_currency_code": "USD"}},
                    {"account_id": "acc-cc", "name": "Plaid Credit", "mask": "3333", "type": "credit",
                     "subtype": "credit card", "balances": {"current": 410, "limit": 2000, "iso_currency_code": "USD"}},
                ]}

    accounts_balance_get = accounts_get

    def transactions_sync(self, token, cursor, count=500):
        if cursor is None:
            return {"added": [{"transaction_id": "t1", "account_id": "acc-chk", "date": "2026-10-01", "amount": 12.5,
                               "name": "Coffee", "pending": False, "iso_currency_code": "USD",
                               "personal_finance_category": {"primary": "FOOD_AND_DRINK", "detailed": "COFFEE"}}],
                    "modified": [], "removed": [], "next_cursor": "c1", "has_more": True,
                    "transactions_update_status": "INITIAL_UPDATE_COMPLETE"}
        return {"added": [{"transaction_id": "t2", "account_id": "acc-cc", "date": "2026-10-02", "amount": 99,
                           "name": "Store", "pending": True, "iso_currency_code": "USD"}],
                "modified": [], "removed": [{"transaction_id": "nope"}], "next_cursor": "c2", "has_more": False,
                "transactions_update_status": "HISTORICAL_UPDATE_COMPLETE"}

    def investments_holdings_get(self, token):
        from server.app.plaid_client import PlaidError
        raise PlaidError(400, {"error_code": "PRODUCTS_NOT_SUPPORTED", "error_type": "INVALID_REQUEST"})

    def liabilities_get(self, token):
        return {"accounts": self.accounts_get(token)["accounts"], "item": {},
                "liabilities": {"credit": [{"account_id": "acc-cc", "aprs": [{"apr_type": "purchase_apr",
                                                                              "apr_percentage": 24.99}],
                                            "minimum_payment_amount": 35, "next_payment_due_date": "2026-11-01",
                                            "is_overdue": False}]}}

    def item_remove(self, token):
        return {"removed": True}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("DEV_LOGIN_EMAIL", "jimmy@example.com")
    reset_settings_cache()
    db.reset_engine_cache()
    migrate(URL, fresh=True)
    fake = FakePlaid()
    import server.app.plaid_client as pc
    monkeypatch.setattr(pc, "_client", fake)
    from server.app.web import app
    with TestClient(app) as c:
        yield c


def test_full_flow(client):
    assert client.get("/healthz").json()["ok"]
    me = client.get("/api/v1/me").json()
    assert me["email"] == "jimmy@example.com" and me["role"] == "owner"

    tok = client.post("/api/v1/link/token", json={}).json()
    assert tok["link_token"].startswith("link-")
    assert tok["redirect_uri"] == "https://fin.example.com/link/oauth"

    item = client.post("/api/v1/link/exchange", json={"public_token": "public-sandbox-x",
                                                      "link_session_id": tok["link_session_id"]}).json()
    assert item["status"] == "active" and item["account_count"] == 2

    # run the queued jobs like the worker would
    from server.app.worker import loop_once
    ran = 0
    while loop_once():
        ran += 1
    # sync_item + refresh_liabilities. No refresh_investments: the Item does not
    # have that product, and calling it would make Plaid add (and bill) it.
    assert ran >= 2
    kinds = {r[0] for r in _jobs()}
    assert "refresh_investments" not in kinds and {"sync_item", "refresh_liabilities"} <= kinds

    status = client.get("/api/v1/sync/status").json()
    assert not [j for j in status["jobs"] if j["status"] == "failed"], status["jobs"]

    txs = client.get("/api/v1/transactions").json()
    assert txs["total"] == 2
    assert client.get("/api/v1/transactions?q=coffee").json()["total"] == 1

    manual = client.post("/api/v1/accounts/manual", json={"name": "House", "manual_category": "real_estate",
                                                          "value": "400000"}).json()
    assert manual["is_liability"] is False
    client.put(f"/api/v1/accounts/{manual['id']}/value", json={"value": "410000"})

    client.post("/api/v1/sync/snapshot")
    while loop_once():
        pass
    ov = client.get("/api/v1/overview").json()
    assert ov["assets"] == "410110.50" and ov["liabilities"] == "410.00"
    assert ov["net_worth"] == "409700.50"
    hist = client.get("/api/v1/networth/history?range=1m").json()
    assert hist["points"][-1]["net"] == "409700.50"

    liab = client.get("/api/v1/liabilities").json()
    assert liab["accounts"][0]["detail"]["interest_rate_pct"] == "24.99"

    # token issuing is dashboard-only and never stores plaintext
    t = client.post("/api/v1/tokens", json={"name": "phone"}).json()
    assert len(t["token"]) > 32
    assert client.get("/api/v1/tokens").json()["tokens"][0]["name"] == "phone"

    # unlink keeps history
    gone = client.delete(f"/api/v1/items/{item['id']}").json()
    assert gone["status"] == "removed"
    ov2 = client.get("/api/v1/overview").json()
    assert ov2["net_worth"] == "410000.00"


def test_reorder_accounts(client):
    def manual(name):
        r = client.post("/api/v1/accounts/manual", json={"name": name, "manual_category": "vehicle", "value": "1000"})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    a, b, c = manual("Car A"), manual("Car B"), manual("Car C")
    r = client.put("/api/v1/accounts/order", json={"account_ids": [c, a, b]})
    assert r.status_code == 200 and r.json() == {"ok": True, "count": 3}
    names = [x["name"] for x in client.get("/api/v1/accounts").json()["accounts"] if x["name"].startswith("Car ")]
    assert names == ["Car C", "Car A", "Car B"]
    assert client.put("/api/v1/accounts/order", json={"account_ids": [a, a]}).status_code == 400
    assert client.put("/api/v1/accounts/order",
                      json={"account_ids": [a, "00000000-0000-0000-0000-000000000000"]}).status_code == 404


def test_account_trend_is_daily_and_ends_at_current_balance(client):
    from datetime import UTC, datetime, timedelta

    from server.app.models import BalanceSnapshot

    r = client.post("/api/v1/accounts/manual", json={"name": "Trend car", "manual_category": "vehicle", "value": "900"})
    acct_id = r.json()["id"]
    today = datetime.now(UTC).date()
    with db.session() as sess:  # an older manual value, 10 days back
        sess.add(BalanceSnapshot(account_id=acct_id, as_of=today - timedelta(days=10),
                                 current_balance=1000, source="manual"))
    rows = {a["id"]: a for a in client.get("/api/v1/accounts").json()["accounts"]}
    trend = rows[acct_id]["trend"]
    assert len(trend) == 11 and trend[0] == "1000.00" and trend[-1] == "900.00"
    overview_rows = {a["id"]: a for g in client.get("/api/v1/overview").json()["groups"] for a in g["accounts"]}
    assert overview_rows[acct_id]["trend"] == trend


def test_summary_splits_in_and_out_and_excludes_transfers(client):
    from datetime import date

    from server.app.models import Transaction

    acct = client.post("/api/v1/accounts/manual",
                       json={"name": "Summary cash", "manual_category": "cash", "value": "0"}).json()["id"]
    rows = [  # (date, amount: Plaid sign, + = out, primary, detailed)
        (date(2026, 8, 3), "-1000.00", "INCOME", "INCOME_WAGES"),
        (date(2026, 8, 4), "50.00", "FOOD_AND_DRINK", "FOOD_AND_DRINK_GROCERIES"),
        (date(2026, 8, 5), "500.00", "TRANSFER_OUT", "TRANSFER_OUT_SAVINGS"),
        (date(2026, 8, 6), "300.00", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"),
        (date(2026, 9, 2), "-20.00", "TRAVEL", "TRAVEL_FLIGHTS"),
        (date(2026, 9, 3), "80.00", "FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT"),
    ]
    with db.session() as sess:
        for i, (d, amt, primary, detailed) in enumerate(rows):
            sess.add(Transaction(account_id=acct, plaid_transaction_id=f"sum-{i}", date=d, amount=amt, name=primary,
                                 pending=False, category_primary=primary, category_detailed=detailed))

    def months(**extra):
        r = client.get("/api/v1/transactions/summary",
                       params={"group_by": "month", "account_id": acct, "from": "2026-08-01", **extra})
        assert r.status_code == 200, r.text
        return [(x["key"], x["inflow"], x["outflow"], x["total"]) for x in r.json()["rows"]]

    # Chronological; both directions present; transfers and card payments left out.
    assert months() == [("2026-08", "1000.00", "50.00", "-950.00"), ("2026-09", "20.00", "80.00", "60.00")]
    assert months(include_transfers="true")[0] == ("2026-08", "1000.00", "850.00", "-150.00")
