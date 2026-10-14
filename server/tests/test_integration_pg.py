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

    # unlink keeps history
    gone = client.delete(f"/api/v1/items/{item['id']}").json()
    assert gone["status"] == "removed"
    ov2 = client.get("/api/v1/overview").json()
    assert ov2["net_worth"] == "410000.00"


def test_phone_link_flow(client, monkeypatch):
    """Access session mints a code, the phone redeems it on the API host for a
    read-only token, and can give it back."""
    from datetime import UTC, datetime, timedelta
    from urllib.parse import parse_qs, urlparse

    from sqlalchemy import update

    from server.app.auth import tokens as tok
    from server.app.db import session
    from server.app.models import MobileLinkCode

    monkeypatch.setenv("API_HOST", "api.example.com")
    reset_settings_cache()
    tok._bad_attempts.clear()
    api = {"host": "api.example.com"}

    def mint(nonce="nonce-1234"):
        r = client.get(f"/api/v1/mobile/link?nonce={nonce}&name=Test%20iPhone", follow_redirects=False)
        assert r.status_code == 302, r.text
        loc = urlparse(r.headers["location"])
        assert (loc.scheme, loc.netloc) == ("jfinances", "linked")
        q = parse_qs(loc.query)
        assert q["nonce"] == [nonce]
        return q["code"][0]

    assert client.get("/api/v1/mobile/link?nonce=bad", follow_redirects=False).status_code == 400
    code = mint()
    # redeeming is for the API hostname only, and needs the matching nonce
    assert client.post("/api/v1/mobile/redeem", json={"code": code, "nonce": "nonce-1234"}).status_code == 404
    assert client.post("/api/v1/mobile/redeem", headers=api,
                       json={"code": code, "nonce": "nonce-9999"}).status_code == 400
    r = client.post("/api/v1/mobile/redeem", headers=api, json={"code": code, "nonce": "nonce-1234", "name": ""})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "jimmy@example.com" and body["name"] == "Test iPhone" and len(body["token"]) > 32
    # a code works once
    assert client.post("/api/v1/mobile/redeem", headers=api,
                       json={"code": code, "nonce": "nonce-1234"}).status_code == 400

    phone = {**api, "authorization": f"Bearer {body['token']}"}
    g = client.get("/api/v1/glance", headers=phone)
    assert g.status_code == 200, g.text
    g = g.json()
    assert set(g) >= {"net_worth", "month", "upcoming", "accounts", "groups", "alerts", "attention"}
    assert {"net", "points", "change_1m"} <= set(g["net_worth"])
    assert {"income", "spending", "categories"} <= set(g["month"])
    me = client.get("/api/v1/me", headers=phone).json()
    assert me["via"] == "token" and me["email"] == "jimmy@example.com"
    assert client.get("/api/v1/overview", headers=phone).status_code == 200
    # read-only, whatever the endpoint
    r = client.post("/api/v1/alerts/dismiss-all", headers=phone)
    assert r.status_code == 403 and r.json()["error"]["code"] == "auth.read_only"
    assert client.post("/api/v1/sync/all", headers=phone).status_code == 403
    # a phone cannot mint codes for another phone
    assert client.get("/api/v1/mobile/link?nonce=nonce-5678", headers=phone, follow_redirects=False).status_code == 403
    # the dashboard bundle is not served on the API host
    assert client.get("/", headers=api).status_code == 404
    assert client.get("/insights", headers=api).status_code == 404
    # the dashboard lists the phone
    listed = client.get("/api/v1/tokens").json()["tokens"]
    assert [t["name"] for t in listed] == ["Test iPhone"] and listed[0]["last_used_at"]

    # an expired code is refused
    code2 = mint("nonce-abcd")
    with session() as s:
        s.execute(update(MobileLinkCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    r = client.post("/api/v1/mobile/redeem", headers=api, json={"code": code2, "nonce": "nonce-abcd"})
    assert r.status_code == 400 and "expired" in r.json()["error"]["message"]

    # the phone gives its token back; it stops working at once
    r = client.post("/api/v1/mobile/unlink", headers=phone)
    assert r.status_code == 200 and r.json()["revoked"] is True
    assert client.get("/api/v1/overview", headers=phone).status_code == 401
    assert client.get("/api/v1/tokens").json()["tokens"][0]["revoked_at"]
    tok._bad_attempts.clear()


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


def test_month_change_holds_newly_linked_accounts_flat(client):
    """An account first tracked today has no month-ago balance. The chart holds it
    flat, so the month's change must too, not count its whole balance as a gain."""
    from datetime import UTC, datetime, timedelta

    def manual(name, category, value):
        r = client.post("/api/v1/accounts/manual", json={"name": name, "manual_category": category, "value": value})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    cash = manual("Old cash", "cash", "1000")
    forty_days_ago = (datetime.now(UTC) - timedelta(days=40)).date().isoformat()
    r = client.put(f"/api/v1/accounts/{cash}/value", json={"value": "900", "as_of": forty_days_ago})
    assert r.status_code == 200, r.text
    manual("New house", "real_estate", "500000")  # tracked from today only
    ov = client.get("/api/v1/overview").json()
    assert ov["net_worth"] == "501000.00"
    assert ov["change_1m"]["amount"] == "100.00"  # was 500100.00: the house counted as a month's gain
    groups = {g["key"]: g["change_1m"] for g in ov["groups"]}
    assert groups["cash"]["amount"] == "100.00"
    assert groups["real_estate"] is None  # nothing to compare with yet
    history = client.get("/api/v1/networth/history?range=3m").json()["points"]
    month_ago = ov["change_1m"]["since"]
    assert [p["net"] for p in history if p["date"] == month_ago] == ["500900.00"]  # the chart agrees


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
    with db.session() as sess:  # no category at all (Plaid sends none sometimes): still counted
        sess.add(Transaction(account_id=acct, plaid_transaction_id="sum-nocat", date=date(2026, 9, 9),
                             amount="5.00", name="MYSTERY", pending=False))
    assert months()[1] == ("2026-09", "20.00", "85.00", "65.00")
    assert months(include_transfers="true")[0] == ("2026-08", "1000.00", "850.00", "-150.00")


# --- Plaid billing safety: no duplicate Items, never lose an access token ----------------------
def _meta(inst="ins_1", name="First Platypus Bank",
          accounts=(("Plaid Checking", "0000", "checking"), ("Plaid Credit", "3333", "credit card"))):
    """The onSuccess metadata Link hands the browser."""
    return {"institution": {"institution_id": inst, "name": name},
            "accounts": [{"id": f"link-{m}", "name": n, "mask": m, "subtype": st} for n, m, st in accounts]}


@pytest.fixture
def plaid_calls(monkeypatch):
    """Each exchange makes a distinct Item (own token, own account ids), counted."""
    calls = {"exchange": 0, "removed": []}
    accounts_get = FakePlaid.accounts_get

    def exchange(self, public_token):
        calls["exchange"] += 1
        n = calls["exchange"]
        return {"access_token": f"access-sandbox-fake-token-{n:032d}", "item_id": f"item-{n}"}

    def accounts(self, token):
        data = accounts_get(self, token)
        for a in data["accounts"]:
            a["account_id"] = f"{a['account_id']}-{token[-4:]}"
        return data

    def remove(self, token):
        calls["removed"].append(token)
        return {"removed": True}

    monkeypatch.setattr(FakePlaid, "item_public_token_exchange", exchange)
    monkeypatch.setattr(FakePlaid, "accounts_get", accounts)
    monkeypatch.setattr(FakePlaid, "item_remove", remove)
    return calls


def _exchange(client, meta, **kw):
    return client.post("/api/v1/link/exchange", json={"public_token": "public-sandbox-x", "metadata": meta, **kw})


def test_duplicate_guard_runs_before_the_exchange(client, plaid_calls):
    assert _exchange(client, _meta()).status_code == 201
    assert plaid_calls["exchange"] == 1

    # The same login again: every selected account is already connected. Refused before
    # the exchange (so Plaid never bills it), and no confirm value gets it through.
    r = _exchange(client, _meta())
    err = r.json()["error"]
    assert r.status_code == 409 and err["code"] == "link.duplicate" and err["confirm"] is None
    assert err["accounts"] == ["Plaid Checking ··0000", "Plaid Credit ··3333"]
    assert _exchange(client, _meta(), confirm="overlap").status_code == 409
    assert _exchange(client, _meta(), confirm="new_login").status_code == 409

    # A second login sharing one account (a joint checking): asks first.
    joint = _meta(accounts=(("Plaid Checking", "0000", "checking"), ("Her Card", "9999", "credit card")))
    r = _exchange(client, joint)
    assert r.status_code == 409 and r.json()["error"]["code"] == "link.overlap"
    assert r.json()["error"]["accounts"] == ["Plaid Checking ··0000"]
    assert _exchange(client, joint, confirm="new_login").status_code == 409

    # A second login with only its own accounts: asks first.
    own = _meta(accounts=(("Her Savings", "7777", "savings"),))
    r = _exchange(client, own)
    assert r.status_code == 409 and r.json()["error"]["code"] == "link.same_institution"
    assert r.json()["error"]["confirm"] == "new_login"
    assert plaid_calls["exchange"] == 1

    assert _exchange(client, own, confirm="new_login").status_code == 201
    assert _exchange(client, joint, confirm="overlap").status_code == 201
    # Another institution goes straight through.
    assert _exchange(client, _meta(inst="ins_2", name="Tartan Bank")).status_code == 201
    assert plaid_calls["exchange"] == 4


def test_token_is_kept_when_the_first_fetch_fails(client, plaid_calls, monkeypatch):
    from sqlalchemy import select

    from server.app.models import Account, PlaidItem
    from server.app.plaid_client import PlaidError
    from server.app.services import plaid_sync
    from server.app.worker import loop_once

    working = FakePlaid.accounts_get

    def down(self, token):
        raise PlaidError(500, {"error_code": "INTERNAL_SERVER_ERROR", "error_type": "API_ERROR"})

    monkeypatch.setattr(FakePlaid, "accounts_get", down)
    r = _exchange(client, _meta())
    assert r.status_code == 201, r.text
    with db.session() as sess:
        item = sess.execute(select(PlaidItem)).scalar_one()
        assert plaid_sync.access_token_for(item) == f"access-sandbox-fake-token-{1:032d}"
    assert ("sync_item", "queued") in _jobs()

    # Connecting the bank again before its accounts arrive is refused too.
    r = _exchange(client, _meta())
    assert r.status_code == 409 and "still loading" in r.json()["error"]["message"]
    assert plaid_calls["exchange"] == 1

    # Plaid answers again: the queued sync stores the accounts and queues the
    # product refreshes the link-time fetch would have.
    monkeypatch.setattr(FakePlaid, "accounts_get", working)
    while loop_once():
        pass
    kinds = {k for k, _ in _jobs()}
    assert {"sync_item", "refresh_liabilities"} <= kinds and "refresh_investments" not in kinds
    with db.session() as sess:
        assert sess.execute(select(PlaidItem.status)).scalar_one() == "active"
        assert len(sess.execute(select(Account)).scalars().all()) == 2


def test_unsaveable_item_is_removed_at_plaid(client, plaid_calls, monkeypatch):
    from sqlalchemy import func, select

    from server.app.models import PlaidItem
    from server.app.services import plaid_sync

    def broken(item, token):
        raise RuntimeError("disk full")

    monkeypatch.setattr(plaid_sync, "store_access_token", broken)
    with pytest.raises(RuntimeError):
        _exchange(client, _meta())
    assert plaid_calls["removed"] == [f"access-sandbox-fake-token-{1:032d}"]
    with db.session() as sess:
        assert sess.execute(select(func.count()).select_from(PlaidItem)).scalar() == 0


def test_new_accounts_webhook_flags_item_until_update_mode(client):
    from server.app.hooks import route_event

    item = _exchange(client, _meta()).json()
    with db.session() as sess:
        assert route_event(sess, {"webhook_type": "ITEM", "webhook_code": "NEW_ACCOUNTS_AVAILABLE",
                                  "item_id": item["plaid_item_id"]}) == "item:new_accounts"
    assert client.get("/api/v1/items").json()["items"][0]["new_accounts_at"] is not None
    lt = client.post(f"/api/v1/items/{item['id']}/relink").json()
    assert lt["mode"] == "update"
    done = client.post("/api/v1/link/update-complete",
                       json={"public_token": "", "link_session_id": lt["link_session_id"]}).json()
    assert done["new_accounts_at"] is None


def test_refresh_button_uses_free_accounts_get(client, monkeypatch):
    _exchange(client, _meta())
    seen = []
    accounts_get = FakePlaid.accounts_get
    monkeypatch.setattr(FakePlaid, "accounts_get", lambda self, token: seen.append(token) or accounts_get(self, token))
    acct = next(a for a in client.get("/api/v1/accounts").json()["accounts"] if a["kind"] == "plaid")
    r = client.post(f"/api/v1/accounts/{acct['id']}/refresh")
    assert r.status_code == 200, r.text
    assert len(seen) == 1


def test_loan_can_be_secured_by_an_offline_asset(client):
    from server.app.models import Account

    def manual(name, category, value="1000"):
        r = client.post("/api/v1/accounts/manual", json={"name": name, "manual_category": category, "value": value})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    house, cash = manual("Lien house", "real_estate", "500000"), manual("Lien cash", "cash")
    with db.session() as sess:
        mortgage = Account(kind="plaid", name="Lien mortgage", type="loan", subtype="mortgage",
                           is_liability=True, current_balance=300000)
        card = Account(kind="plaid", name="Lien card", type="credit", subtype="credit card", is_liability=True)
        sess.add_all([mortgage, card])
        sess.flush()
        mortgage_id, card_id = str(mortgage.id), str(card.id)

    def link(loan, asset):
        return client.patch(f"/api/v1/accounts/{loan}", json={"secured_by_id": asset})

    r = link(mortgage_id, house)
    assert r.status_code == 200 and r.json()["secured_by_id"] == house
    renamed = client.patch(f"/api/v1/accounts/{mortgage_id}", json={"name": "Lien mortgage 2"}).json()
    assert renamed["secured_by_id"] == house  # a patch without the field keeps the link
    flagged = client.patch(f"/api/v1/accounts/{mortgage_id}", json={"is_business": True}).json()
    assert flagged["is_business"] is True and flagged["secured_by_id"] == house
    assert link(card_id, house).status_code == 400  # cards aren't secured by anything
    assert link(mortgage_id, cash).status_code == 400  # cash isn't collateral
    assert link(mortgage_id, card_id).status_code == 400  # only offline assets
    assert link(mortgage_id, None).json()["secured_by_id"] is None  # explicit null unlinks
    assert link(mortgage_id, house).status_code == 200
    assert client.delete(f"/api/v1/accounts/{house}").status_code == 204
    rows = {a["id"]: a for a in client.get("/api/v1/accounts").json()["accounts"]}
    assert rows[mortgage_id]["secured_by_id"] is None  # deleting the asset clears the link


def test_account_details_fill_gaps_and_infer_the_rest(client):
    """A loan the lender says nothing about: the person enters three numbers and
    the rate, payoff and schedule follow; bank values always win; a card takes an
    entered limit everywhere utilization is read."""
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from server.app.models import Account, Liability, RecurringStream
    from server.app.services import loanmath as lm

    with db.session() as sess:
        auto = Account(kind="plaid", name="PNC Auto Loan", type="loan", subtype="auto", is_liability=True,
                       current_balance=Decimal("12792.72"))
        mortgage = Account(kind="plaid", name="Chase Mortgage", type="loan", subtype="mortgage", is_liability=True,
                           current_balance=Decimal("407727.00"))
        card = Account(kind="plaid", name="Amex Gold Card", type="credit", subtype="credit card", is_liability=True,
                       current_balance=Decimal("2500.00"))
        sess.add_all([auto, mortgage, card])
        sess.flush()
        sess.add(Liability(account_id=mortgage.id, kind="mortgage", interest_rate_pct=Decimal("6.125"),
                           origination_principal=Decimal("440000"), origination_date=date(2021, 6, 15),
                           loan_term="30 year", next_payment_amount=Decimal("2950.12")))
        today = date.today()
        sess.add(RecurringStream(merchant="Pnc Auto Loan", cadence="monthly", interval_days=30,
                                 amount=Decimal("541.37"), last_amount=Decimal("541.37"), first_date=date(2026, 1, 15),
                                 last_date=today, next_date=today, charge_count=9, category="LOAN_PAYMENTS",
                                 status="detected", seen_at=datetime.now(UTC)))
        auto_id, mortgage_id, card_id = str(auto.id), str(mortgage.id), str(card.id)

    d = client.get(f"/api/v1/accounts/{auto_id}/details").json()
    assert d["kind"] == "loan"
    terms = {f["key"]: f for f in d["sections"][0]["facts"]}
    assert terms["rate"]["value"] is None and terms["rate"]["field"] == "interest_rate_pct"  # missing: offer to add
    assert d["suggestions"]["payment_amount"]["value"] == "541.37"  # from the person's own payments
    assert {f["key"] for f in d["fields"]} >= {"interest_rate_pct", "original_principal", "term_months"}

    body = {"original_principal": "30000", "origination_date": "2023-06-15", "term_months": 72,
            "payment_amount": "541.37"}
    d = client.put(f"/api/v1/accounts/{auto_id}/terms", json=body).json()
    facts = {f["key"]: f for s in d["sections"] for f in s["facts"]}
    expected = lm.solve_rate(Decimal("30000"), 72, Decimal("541.37"))
    assert facts["rate"]["value"] == format(expected.normalize(), "f") and facts["rate"]["source"] == "calc"
    assert facts["original"]["source"] == "you" and facts["maturity"]["value"] == "2029-06-15"
    assert facts["payoff"]["source"] == "calc" and facts["schedule"]["label"] in (
        "schedule", "ahead of schedule", "behind schedule")

    preview = client.post(f"/api/v1/accounts/{auto_id}/terms/preview", json={"interest_rate_pct": "5"}).json()
    assert {f["key"]: f for f in preview["sections"][0]["facts"]}["rate"]["source"] == "you"
    stored = client.get(f"/api/v1/accounts/{auto_id}/details").json()  # a preview saves nothing
    assert {f["key"]: f for f in stored["sections"][0]["facts"]}["rate"]["source"] == "calc"

    assert client.put(f"/api/v1/accounts/{auto_id}/terms", json={"interest_rate_pct": "99"}).status_code == 422
    assert client.put(f"/api/v1/accounts/{auto_id}/terms", json={"credit_limit": "5000"}).status_code == 400

    liab = {x["account"]["id"]: x["detail"] for x in client.get("/api/v1/liabilities").json()["accounts"]}
    assert liab[auto_id]["sources"]["interest_rate_pct"] == "calc" and liab[auto_id]["maturity_date"] == "2029-06-15"
    loans = {x["id"]: x for x in client.get("/api/v1/insights/loans").json()["loans"]}
    assert loans[auto_id]["schedule"] is not None and loans[auto_id]["rate_source"] == "calc"

    # The lender's rate wins over an entered one; escrow follows from the bill.
    client.put(f"/api/v1/accounts/{mortgage_id}/terms", json={"interest_rate_pct": "4"})
    m = client.get(f"/api/v1/accounts/{mortgage_id}/details").json()
    mf = {f["key"]: f for s in m["sections"] for f in s["facts"]}
    assert mf["rate"]["value"] == "6.125" and mf["rate"]["source"] == "bank"
    assert mf["payment"]["value"] == "2673.49" and mf["payment"]["source"] == "calc"
    assert mf["escrow"]["value"] == "276.63" and mf["total"]["value"] == "2950.12"

    client.put(f"/api/v1/accounts/{card_id}/terms", json={"credit_limit": "10000", "interest_rate_pct": "24.99"})
    c = {f["key"]: f for s in client.get(f"/api/v1/accounts/{card_id}/details").json()["sections"] for f in s["facts"]}
    assert c["limit"]["source"] == "you" and c["utilization"]["value"] == 0.25 and c["carry"]["source"] == "calc"
    liab = {x["account"]["id"]: x["detail"] for x in client.get("/api/v1/liabilities").json()["accounts"]}
    assert liab[card_id]["credit_limit"] == "10000.00" and liab[card_id]["sources"]["credit_limit"] == "you"
    cards = {x["id"]: x for x in client.get("/api/v1/insights/cards").json()["cards"]}
    assert cards[card_id]["utilization"] == 0.25

    # Clearing every field removes the row.
    cleared = {k: None for k in ("credit_limit", "interest_rate_pct")}
    assert client.put(f"/api/v1/accounts/{card_id}/terms", json=cleared).status_code == 200
    with db.session() as sess:
        from server.app.models import AccountTerms
        assert sess.get(AccountTerms, card.id) is None


def test_bank_export_import_never_double_counts(client):
    """A checking export reaching back before the connection's history: rows the
    connection has are matched, older ones added with their balances, unmatched
    ones inside its period wait for a tick; re-uploads add nothing, undo removes
    it all, and when the connection later sends the same rows the imported
    copies retire."""
    import base64
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from sqlalchemy import select

    from server.app.models import Account, BalanceSnapshot, ImportRow, Transaction
    from server.app.services import importer

    with db.session() as sess:
        acct = Account(kind="plaid", name="Everyday Checking", type="depository", subtype="checking", mask="4821",
                       current_balance=Decimal("1500.00"))
        sess.add(acct)
        sess.flush()
        for d, amt, name, cat in ((date(2026, 9, 2), "6.38", "STARBUCKS STORE 123", "FOOD_AND_DRINK"),
                                  (date(2026, 9, 4), "-2000.00", "ACME PAYROLL", "INCOME"),
                                  (date(2026, 10, 1), "50.00", "SHELL OIL", "TRANSPORTATION")):
            sess.add(Transaction(account_id=acct.id, source="plaid", plaid_transaction_id=f"p-{d}-{amt}", date=d,
                                 amount=Decimal(amt), name=name, merchant_name=name.split()[0].title(),
                                 category_primary=cat, pending=False))
        sess.add(BalanceSnapshot(account_id=acct.id, as_of=date(2026, 10, 13), current_balance=Decimal("1500.00"),
                                 source="plaid"))
        acct_id = str(acct.id)

    csv_text = (
        "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
        "DEBIT,09/05/2026,\"CORNER DELI\",-12.00,DEBIT_CARD,3481.62,,\n"  # in the connection's period, unmatched
        "CREDIT,09/04/2026,\"ACME PAYROLL PPD\",2000.00,ACH_CREDIT,3493.62,,\n"   # matched
        "DEBIT,09/02/2026,\"STARBUCKS STORE 123\",-6.38,DEBIT_CARD,1493.62,,\n"  # matched
        "DEBIT,08/20/2026,\"CHASE CREDIT CRD AUTOPAY\",-500.00,ACH_DEBIT,1500.00,,\n"
        "DEBIT,08/15/2026,\"STARBUCKS STORE 99\",-4.00,DEBIT_CARD,2000.00,,\n"
        "CREDIT,08/01/2026,\"ACME PAYROLL PPD\",2000.00,ACH_CREDIT,2004.00,,\n")
    body = {"filename": "Chase4821_Activity_20261014.CSV", "content_b64": base64.b64encode(csv_text.encode()).decode()}

    pv = client.post("/api/v1/imports/preview", json=body).json()
    assert pv["account_id"] == acct_id  # recognized by the last four digits in the file name
    assert pv["counts"] == {"total": 6, "new": 3, "review": 1, "matched": 2, "duplicate": 0, "problems": 0}
    assert pv["sign"]["basis"] == "matched" and pv["connection_from"] == "2026-09-02"
    assert pv["balances"]["days"] == 6
    review = [r["index"] for r in pv["rows"] if r["status"] == "review"]

    done = client.post("/api/v1/imports", json={**body, "account_id": acct_id, "include": []}).json()
    assert (done["rows_added"], done["rows_matched"], done["rows_skipped"], done["balances_added"]) == (3, 2, 1, 6)
    with db.session() as sess:
        q = select(Transaction).where(Transaction.source == "import")
        rows = {t.name: t for t in sess.execute(q).scalars()}
        assert rows["CHASE CREDIT CRD AUTOPAY"].category_detailed == "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
        assert rows["STARBUCKS STORE 99"].category_primary == "FOOD_AND_DRINK"  # learned from the connection's rows
        assert rows["STARBUCKS STORE 99"].merchant_name == "Starbucks"
        assert rows["ACME PAYROLL PPD"].category_primary == "INCOME"
    hist = client.get(f"/api/v1/accounts/{acct_id}/history?range=all").json()["points"]
    by_day = {p["date"]: p for p in hist}
    assert by_day["2026-08-15"] == {**by_day["2026-08-15"], "source": "import", "balance": "2000.00"}

    again = client.post("/api/v1/imports/preview", json=body).json()["counts"]
    assert again["new"] == 0 and again["duplicate"] == 5 and again["review"] == 1  # the unticked one can still be added
    added = client.post("/api/v1/imports", json={**body, "account_id": acct_id, "include": review}).json()
    assert added["rows_added"] == 1
    overlap = csv_text + "DEBIT,07/20/2026,\"OLD BOOKSTORE\",-30.00,DEBIT_CARD,2034.00,,\n"
    body2 = {**body, "content_b64": base64.b64encode(overlap.encode()).decode()}
    assert client.post("/api/v1/imports/preview", json=body2).json()["counts"]["new"] == 1

    # Undo the first import: its rows and balances go, the matched pairs are forgotten.
    undone = client.delete(f"/api/v1/imports/{done['id']}").json()
    assert undone["status"] == "undone" and undone["removed"] == 3
    assert client.post("/api/v1/imports/preview", json=body).json()["counts"]["new"] == 3

    # Re-import, then the connection sends the older history too: the copies retire.
    client.post("/api/v1/imports", json={**body, "account_id": acct_id, "include": []})
    with db.session() as sess:
        imported = sess.execute(select(Transaction).where(Transaction.name == "STARBUCKS STORE 99",
                                                          Transaction.removed_at.is_(None))).scalar_one()
        imported.user_category = "ENTERTAINMENT"
        sess.add(Transaction(account_id=imported.account_id, source="plaid", plaid_transaction_id="p-late",
                             date=date(2026, 8, 16), amount=Decimal("4.00"), name="STARBUCKS", pending=False,
                             category_primary="FOOD_AND_DRINK"))
        sess.flush()
        assert importer.reconcile(sess, [imported.account_id]) == 1
        assert imported.removed_at is not None
        theirs = sess.execute(select(Transaction).where(Transaction.plaid_transaction_id == "p-late")).scalar_one()
        assert theirs.user_category == "ENTERTAINMENT"  # the person's category moved across
        ledger = sess.execute(select(ImportRow).where(ImportRow.transaction_id == imported.id)).scalar_one()
        assert ledger.status == "superseded" and ledger.matched_transaction_id == theirs.id
        assert datetime.now(UTC)

    # OFX: the bank's own IDs; a second upload adds nothing.
    ofx = ("OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>99994821</BANKACCTFROM>"
           "<BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260610<TRNAMT>-25.00<FITID>A1<NAME>HARDWARE STORE"
           "</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    body3 = {"filename": "export.qfx", "content_b64": base64.b64encode(ofx.encode()).decode(), "account_id": acct_id}
    assert client.post("/api/v1/imports", json={**body3, "include": []}).json()["rows_added"] == 1
    assert client.post("/api/v1/imports/preview", json=body3).json()["counts"]["duplicate"] == 1

    with db.session() as sess:
        brokerage = Account(kind="plaid", name="Brokerage", type="investment", subtype="brokerage")
        sess.add(brokerage)
        sess.flush()
        bid = str(brokerage.id)
    assert client.post("/api/v1/imports/preview", json={**body, "account_id": bid}).status_code == 400
    bad = client.post("/api/v1/imports/preview", json={**body, "content_b64": "not base64!"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "bad_file"


def test_a_401k_statement_fills_in_contributions_prices_and_value_history(client):
    """A Vanguard 401(k) statement into the linked account holding the same trust (no
    public ticker): every entry once though the file repeats it, contributions as new
    money, a buy the connection has matched, the account's value rebuilt from the
    statement's holdings and the trust's own trade prices; re-upload adds nothing,
    undo removes it all."""
    import base64
    from datetime import date
    from decimal import Decimal

    from sqlalchemy import select

    from server.app.models import Account, BalanceSnapshot, Holding, InvestmentTransaction, Security
    from server.app.services import performance
    from server.tests.test_invstatement import POS, TRUST, _buy, _ofx

    with db.session() as sess:
        acct = Account(kind="plaid", name="401(k) Savings Plan", type="investment", subtype="401k", mask="6789",
                       current_balance=Decimal("1320.00"))
        bank = Account(kind="plaid", name="Checking", type="depository", subtype="checking", mask="1111")
        sess.add_all([acct, bank])
        sess.flush()
        trust = Security(plaid_security_id="plaid-sec-trust", name="Vanguard Target Retirement 2045 Trust",
                         type="mutual fund")
        sess.add(trust)
        sess.flush()
        sess.add(Holding(account_id=acct.id, security_id=trust.id, quantity=Decimal("110"),
                         institution_price=Decimal("12.00"), institution_price_as_of=date(2026, 10, 14),
                         institution_value=Decimal("1320.00")))
        # The connection has one buy already (a day later than the statement says).
        sess.add(InvestmentTransaction(account_id=acct.id, plaid_investment_transaction_id="p-inv-1",
                                       security_id=trust.id, date=date(2026, 10, 2), type="buy", subtype="buy",
                                       quantity=Decimal("4"), amount=Decimal("44"), price=Decimal("11")))
        sess.add(BalanceSnapshot(account_id=acct.id, as_of=date(2026, 10, 13), current_balance=Decimal("1320.00"),
                                 source="plaid"))
        acct_id, bank_id, trust_id = str(acct.id), str(bank.id), trust.id

    once = (_buy("A1", "20260901", "5", "10", "50") + _buy("A2", "20260901", "2.5", "10", "25", "MATCH")
            + _buy("A3", "20261001", "4", "11", "44")
            + "<INVEXPENSE><INVTRAN><FITID>F1<DTTRADE>20260915</INVTRAN><SECID><UNIQUEID>VGI0001"
              "<UNIQUEIDTYPE>CUSIP</SECID><TOTAL>-0.50<SUBACCTSEC>CASH<SUBACCTFUND>OTHER</INVEXPENSE>\n"
            + "<TRANSFER><INVTRAN><FITID>T1<DTTRADE>20260920</INVTRAN><SECID><UNIQUEID>VGI0001"
              "<UNIQUEIDTYPE>CUSIP</SECID><SUBACCTSEC>CASH<UNITS>0.1<TFERACTION>IN<POSTYPE>LONG"
              "<UNITPRICE>10.5<INV401KSOURCE>MATCH</TRANSFER>\n")
    raw = _ofx(once * 3, POS, TRUST, "<INV401K><EMPLOYERNAME>ACME 401(K)</INV401K>")
    body = {"filename": "OfxDownload.qfx", "content_b64": base64.b64encode(raw).decode()}

    pv = client.post("/api/v1/imports/preview", json=body)
    assert pv.status_code == 200, pv.text
    pv = pv.json()
    assert pv["format"] == "invofx" and pv["account_id"] == acct_id  # by the account number's last four
    # All older than the connection's first investment transaction (Oct 2): new, not for review.
    assert pv["counts"] == {"total": 5, "new": 4, "review": 0, "matched": 1, "duplicate": 0, "problems": 0}
    assert pv["balances"] == {"days": 73, "from": "2026-08-01", "to": "2026-10-12"}
    assert any("more than once" in n for n in pv["notes"]) and any("contributions" in n for n in pv["notes"])
    assert not any("Not held" in n for n in pv["notes"])  # the trust is the one the account holds
    # A bank account is the wrong place for it.
    wrong = client.post("/api/v1/imports/preview", json={**body, "account_id": bank_id})
    assert wrong.status_code == 400 and "investment account" in wrong.json()["error"]["message"]

    ticks = [r["index"] for r in pv["rows"] if r["status"] == "review"]
    r = client.post("/api/v1/imports", json={**body, "account_id": acct_id, "include": ticks})
    assert r.status_code == 201, r.text
    imp = r.json()
    assert (imp["rows_added"], imp["rows_matched"], imp["format"]) == (4, 1, "invofx")
    assert imp["balances_added"] == 73

    with db.session() as sess:
        rows = sess.execute(select(InvestmentTransaction).where(
            InvestmentTransaction.account_id == acct.id, InvestmentTransaction.source == "import")).scalars().all()
        # The connection's Oct 2 buy says nothing of the paycheck behind it: the statement's contribution joins it.
        assert sorted((t.type, t.subtype) for t in rows) == [
            ("buy", "buy"), ("buy", "buy"), ("cash", "contribution"), ("cash", "contribution"),
            ("cash", "contribution"), ("fee", "account fee"), ("transfer", "transfer")]
        assert {t.security_id for t in rows if t.quantity} == {trust_id}
        days = dict(sess.execute(select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance).where(
            BalanceSnapshot.account_id == acct.id, BalanceSnapshot.source == "derived")).all())
        # 98.4 units before September's buys at the first trade price, plus the fee not yet taken.
        assert days[date(2026, 8, 31)] == Decimal("984.50")
        assert days[date(2026, 9, 1)] == Decimal("1059.50")  # 105.9 units at $10
        # Between trades the trust's price runs straight from $11 (the connection's Oct 2 buy) to $12 (Oct 14).
        assert days[date(2026, 10, 12)] == (Decimal("110") * (Decimal(11) + Decimal(10) / Decimal(12))).quantize(
            Decimal("0.01"))
        assert date(2026, 10, 13) not in days  # tracked from there
        perf = performance.account_series(sess, sess.get(Account, acct.id), date(2026, 8, 1), date(2026, 10, 14),
                                          date(2026, 10, 14))
        assert perf.tracked_since == date(2026, 10, 13)
        assert sum(perf.flows.values()) == Decimal("75") + Decimal("1.05") + Decimal("44")
    hist = client.get("/api/v1/networth/history", params={"range": "1y"}).json()
    sept1 = next(p for p in hist["points"] if p["date"] == "2026-09-01")
    assert Decimal(sept1["assets"]) >= Decimal("1059.50")

    again = client.post("/api/v1/imports/preview", json={**body, "account_id": acct_id}).json()
    assert again["counts"]["duplicate"] == 5  # all in the ledger now, the matched one too

    u = client.delete(f"/api/v1/imports/{imp['id']}")
    assert u.status_code == 200 and u.json()["removed"] == 7
    with db.session() as sess:
        assert not sess.execute(select(InvestmentTransaction).where(InvestmentTransaction.source == "import")).first()
        assert not sess.execute(select(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id,
                                                              BalanceSnapshot.source == "derived")).first()


def test_an_account_counts_where_the_person_puts_it(client):
    """An account the bank calls "other" lands in Other assets until the person puts
    it elsewhere: cash, investments, or a liability group (then it is owed, not
    owned). A sync keeps the choice; null goes back; an offline account takes the
    group's own category when there is one."""
    from decimal import Decimal

    from server.app.models import Account, PlaidItem
    from server.app.services import plaid_sync

    with db.session() as sess:
        item = PlaidItem(item_id="item-groups", institution_name="Odd Bank", access_token_enc=b"x", products=[])
        sess.add(item)
        sess.flush()
        raw = {"account_id": "odd-1", "name": "Cash Reserve", "type": "other", "subtype": None,
               "balances": {"current": 5000, "iso_currency_code": "USD"}}
        (odd,) = plaid_sync.upsert_accounts(sess, item, [raw])
        house = Account(kind="manual", name="Lake lot", manual_category="other_asset", type="manual",
                        subtype="other_asset", current_balance=Decimal("80000"))
        sess.add(house)
        sess.flush()
        odd_id, house_id = str(odd.id), str(house.id)

    def group_of(account_id):
        ov = client.get("/api/v1/overview").json()
        return next(g["key"] for g in ov["groups"] for a in g["accounts"] if a["id"] == account_id)

    assert group_of(odd_id) == "other_assets"
    r = client.patch(f"/api/v1/accounts/{odd_id}", json={"group": "cash"}).json()
    assert (r["group"], r["group_override"], r["is_liability"]) == ("cash", "cash", False)
    assert group_of(odd_id) == "cash"
    before = Decimal(client.get("/api/v1/overview").json()["liabilities"])
    r = client.patch(f"/api/v1/accounts/{odd_id}", json={"group": "loans"}).json()
    assert (r["group"], r["is_liability"]) == ("loans", True)
    assert Decimal(client.get("/api/v1/overview").json()["liabilities"]) == before + Decimal("5000")
    assert any(x["account"]["id"] == odd_id for x in client.get("/api/v1/liabilities").json()["accounts"])
    with db.session() as sess:  # the next sync keeps it a loan
        item = sess.query(PlaidItem).filter_by(item_id="item-groups").one()
        (odd,) = plaid_sync.upsert_accounts(sess, item, [raw])
        assert odd.is_liability and odd.group_override == "loans"
    r = client.patch(f"/api/v1/accounts/{odd_id}", json={"group": None}).json()
    assert (r["group"], r["group_override"], r["is_liability"]) == ("other_assets", None, False)

    r = client.patch(f"/api/v1/accounts/{house_id}", json={"group": "real_estate"}).json()
    assert (r["group"], r["manual_category"], r["group_override"]) == ("real_estate", "real_estate", None)
    r = client.patch(f"/api/v1/accounts/{house_id}", json={"group": "investments"}).json()
    assert (r["group"], r["group_override"], r["is_liability"]) == ("investments", "investments", False)
    assert client.patch(f"/api/v1/accounts/{house_id}", json={"group": "attic"}).status_code == 422


def test_an_offline_bank_takes_its_exports_and_counts_in_insights(client):
    """A bank the connection can't reach, kept as an offline account: its export is
    imported (every row new), its paychecks count as income and its card payment as a
    transfer, its statement balances fill the days nobody typed, a newer statement
    keeps its balance, and undo removes it all."""
    import base64
    import uuid
    from datetime import UTC, date, datetime
    from decimal import Decimal

    from sqlalchemy import delete, select

    from server.app.models import Account, BalanceSnapshot, Transaction

    r = client.post("/api/v1/accounts/manual", json={"name": "Schwab Checking", "manual_category": "other_asset",
                                                     "value": 2500, "iso_currency": "USD"})
    assert r.status_code == 201, r.text
    acct = r.json()
    assert acct["group"] == "other_assets"
    csv_text = ("Date,Description,Amount,Balance\n"
                "09/01/2026,ACME CORP PAYROLL PPD ID: 7,3200.00,4200.00\n"
                "09/03/2026,CHASE CREDIT CRD AUTOPAY,-900.00,3300.00\n"
                "09/15/2026,ACME CORP PAYROLL PPD ID: 7,3200.00,6500.00\n"
                "09/20/2026,LANDLORD LLC RENT,-2400.00,4100.00\n")
    body = {"filename": "Schwab_Checking.csv", "content_b64": base64.b64encode(csv_text.encode()).decode(),
            "account_id": acct["id"]}
    pv = client.post("/api/v1/imports/preview", json=body)
    assert pv.status_code == 200, pv.text
    pv = pv.json()
    assert pv["counts"]["new"] == 4 and pv["connection_from"] is None and pv["balances"]["days"] == 4
    imp = client.post("/api/v1/imports", json=body)
    assert imp.status_code == 201, imp.text
    imp = imp.json()
    assert (imp["rows_added"], imp["balances_added"]) == (4, 4)

    cf = client.get("/api/v1/insights/cashflow", params={"from": "2026-09-01", "to": "2026-09-30"}).json()
    assert cf["totals"]["income"] == "6400.00"  # the paychecks count, like any account's
    assert cf["totals"]["spending"] == "2400.00"  # the rent; the card payment is a transfer
    with db.session() as sess:
        a = sess.get(Account, uuid.UUID(acct["id"]))
        assert a.current_balance == Decimal("2500")  # typed today, newer than the statement
        days = dict(sess.execute(select(BalanceSnapshot.as_of, BalanceSnapshot.source)
                                 .where(BalanceSnapshot.account_id == a.id)).all())
        assert days[date(2026, 9, 20)] == "import"
        assert sess.execute(select(Transaction).where(Transaction.account_id == a.id)).scalars().all()

    # A newer statement than anything typed keeps the balance current.
    with db.session() as sess:
        sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == uuid.UUID(acct["id"]),
                                                   BalanceSnapshot.source == "manual"))
    later = ("Date,Description,Amount,Balance\n"
             f"{datetime.now(UTC).date():%m/%d/%Y},COFFEE,-4.00,4096.00\n")
    r = client.post("/api/v1/imports", json={**body, "filename": "later.csv",
                                             "content_b64": base64.b64encode(later.encode()).decode()})
    assert r.status_code == 201, r.text
    acc = next(x for x in client.get("/api/v1/accounts").json()["accounts"] if x["id"] == acct["id"])
    assert acc["current_balance"] == "4096.00"

    u = client.delete(f"/api/v1/imports/{imp['id']}")
    assert u.status_code == 200 and u.json()["removed"] == 4


def test_homes_and_cars_are_valued_once_a_month_within_budget(client, monkeypatch):
    """Offline homes (RentCast) and cars (MarketCheck: VIN decoded once, priced at
    the garage home's ZIP and the mileage projected at the person's pace) get one
    market value a month: a rerun asks nothing, a new month asks again, a ceiling
    holds requests back, an error changes nothing, and no key is ever stored."""
    import json
    import uuid
    from datetime import UTC, datetime, timedelta

    import httpx
    from sqlalchemy import select

    from server.app.config import settings
    from server.app.models import Account, Valuation
    from server.app.services import valuations

    s = settings().model_copy(update={"rentcast_api_key": "rc-SECRET-key", "marketcheck_api_key": "mc-SECRET-key"})
    calls: list[httpx.Request] = []
    fail = {"rentcast": False}

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "api.rentcast.io":
            if fail["rentcast"]:
                return httpx.Response(500, json={})
            return httpx.Response(200, json={"price": 640000, "priceRangeLow": 601000, "priceRangeHigh": 688000,
                                             "comparables": [{}] * 15})
        if "/decode/" in request.url.path:
            return httpx.Response(200, json={"year": 2020, "make": "Subaru", "model": "Outback", "trim": "Limited"})
        return httpx.Response(200, json={"marketcheck_price": 24350, "msrp": 34895})

    http = httpx.Client(transport=httpx.MockTransport(answer))
    home = client.post("/api/v1/accounts/manual", json={
        "name": "Main house", "manual_category": "real_estate", "value": 600000,
        "asset": {"address_line": "12 Elm St", "city": "Montclair", "state": "nj", "zip": "07042",
                  "property_type": "Single Family"}})
    assert home.status_code == 201, home.text
    home = home.json()
    car = client.post("/api/v1/accounts/manual", json={
        "name": "Outback", "manual_category": "vehicle", "value": 25000,
        "asset": {"vin": "4s4btanc1l3123456", "mileage": 30000, "miles_per_month": 250,
                  "garage_account_id": home["id"]}}).json()
    bare = client.post("/api/v1/accounts/manual", json={"name": "Old truck", "manual_category": "vehicle",
                                                        "value": 3000}).json()
    assert client.get(f"/api/v1/accounts/{bare['id']}/asset").json()["missing"] == ["vin", "mileage", "location"]
    bad = client.put(f"/api/v1/accounts/{car['id']}/asset", json={"vin": "NOTAVIN", "mileage": 1})
    assert bad.status_code == 400 and "VIN" in bad.json()["error"]["message"]
    assert client.put(f"/api/v1/accounts/{car['id']}/asset", json={
        "vin": "4S4BTANC1L3123456", "mileage": 30000, "garage_account_id": car["id"]}).status_code == 400
    assert client.put(f"/api/v1/accounts/{car['id']}/asset", json={"miles_per_month": 333}).status_code == 422

    today = datetime.now(UTC).date()
    later = today + timedelta(days=61)  # two months of driving at 250 a month
    with db.session() as sess:
        assert valuations.run(sess, today=later, client=http, s=s) == {"valued": 2}  # the truck has no details
    rentcast = [r for r in calls if r.url.host == "api.rentcast.io"]
    price = [r for r in calls if r.url.path.endswith("/marketcheck_price")]
    decode = [r for r in calls if "/decode/" in r.url.path]
    assert (len(rentcast), len(price), len(decode)) == (1, 1, 1)
    assert rentcast[0].headers["X-Api-Key"] == "rc-SECRET-key"
    assert rentcast[0].url.params["address"] == "12 Elm St, Montclair, NJ, 07042"
    q = price[0].url.params
    assert (q["vin"], q["zip"], q["miles"], q["dealer_type"]) == ("4S4BTANC1L3123456", "07042", "30501",
                                                                  "independent")
    with db.session() as sess:
        assert sess.get(Account, uuid.UUID(home["id"])).current_balance == 640000
        assert sess.get(Account, uuid.UUID(car["id"])).current_balance == 24350
    info = client.get(f"/api/v1/accounts/{car['id']}/asset").json()
    assert info["details"]["vehicle_label"] == "2020 Subaru Outback Limited" and info["priced_at_zip"] == "07042"
    assert info["valuations"][0]["value"] == "24350.00" and info["valuations"][0]["inputs"]["miles"] == 30501

    calls.clear()
    with db.session() as sess:  # the same month again: nothing is asked
        assert valuations.run(sess, today=later, client=http, s=s) == {"already this month": 2}
    assert calls == []

    next_month = (later.replace(day=1) + timedelta(days=32)).replace(day=3)
    fail["rentcast"] = True
    with db.session() as sess:  # a new month: asked again (no second decode); a failed answer changes nothing
        assert valuations.run(sess, today=next_month, client=http, s=s) == {"valued": 1, "error": 1}
        assert sess.get(Account, uuid.UUID(home["id"])).current_balance == 640000
    assert len([r for r in calls if "/decode/" in r.url.path]) == 0 and len(calls) == 2

    calls.clear()
    monkeypatch.setitem(valuations.MONTHLY_CEILING, "rentcast", 0)
    monkeypatch.setitem(valuations.MONTHLY_CEILING, "marketcheck", 0)
    third = (next_month + timedelta(days=32)).replace(day=1)
    with db.session() as sess:  # over the ceiling: held back, and the month is held
        assert valuations.run(sess, today=third, client=http, s=s) == {"already this month": 2}
        assert {v.status for v in sess.execute(select(Valuation).where(Valuation.month == third)).scalars()} == {
            "skipped"}
        stored = json.dumps([[v.inputs, v.detail, v.error] for v in sess.execute(select(Valuation)).scalars()])
    assert calls == [] and "SECRET" not in stored


def test_categories_are_learned_per_merchant_account_and_direction(client):
    """Filing a merchant's charge teaches its next charges on that account; the
    latest filing wins; a refund (money in) and another account don't follow;
    back to the bank's category forgets; imported rows follow too."""
    import base64
    import uuid
    from datetime import date
    from decimal import Decimal

    from server.app.models import Account, PlaidItem, Transaction
    from server.app.services import category_rules, plaid_sync

    with db.session() as sess:
        item = PlaidItem(item_id="item-rules", institution_name="Card Bank", access_token_enc=b"x", products=[])
        sess.add(item)
        sess.flush()
        card = Account(kind="plaid", item_id=item.id, plaid_account_id="card-a", name="Gold", type="credit",
                       subtype="credit card", is_liability=True)
        other = Account(kind="plaid", item_id=item.id, plaid_account_id="card-b", name="Blue", type="credit",
                        subtype="credit card", is_liability=True)
        bank = Account(kind="plaid", item_id=item.id, plaid_account_id="chk", name="Checking", type="depository",
                       subtype="checking")
        sess.add_all([card, other, bank])
        sess.flush()
        first = Transaction(account_id=card.id, plaid_transaction_id="r-1", date=date(2026, 9, 1),
                            amount=Decimal("6.50"), name="STARBUCKS 123", merchant_name="Starbucks",
                            category_primary="FOOD_AND_DRINK")
        sess.add(first)
        sess.flush()
        first_id, card_id, bank_id = str(first.id), card.id, str(bank.id)

    def arrive(pid, account, amount, merchant="Starbucks"):
        """A new transaction from the connection, the way a sync adds it."""
        with db.session() as sess:
            accounts = {a.plaid_account_id: a for a in sess.query(Account).filter(Account.item_id.isnot(None))}
            rules = category_rules.load(sess, [a.id for a in accounts.values()])
            plaid_sync._upsert_transaction(sess, accounts, {
                "transaction_id": pid, "account_id": account, "date": "2026-10-01", "amount": amount,
                "name": merchant.upper(), "merchant_name": merchant, "pending": False,
                "personal_finance_category": {"primary": "FOOD_AND_DRINK"}}, rules)
            sess.flush()
            return sess.query(Transaction).filter_by(plaid_transaction_id=pid).one().user_category

    assert arrive("r-0", "card-a", 4.00) is None  # nothing learned yet
    client.patch(f"/api/v1/transactions/{first_id}", json={"user_category": "COFFEE"})
    assert arrive("r-2", "card-a", 5.25) == "COFFEE"
    assert arrive("r-3", "card-a", -5.25) is None  # a refund is money in: its own rule
    assert arrive("r-4", "card-b", 5.25) is None  # another card: its own rule
    client.patch("/api/v1/transactions", json={"ids": [first_id], "user_category": "TREATS"})
    assert arrive("r-5", "card-a", 7.00) == "TREATS"  # the latest filing wins
    rules = client.get("/api/v1/transactions/rules").json()["rules"]
    assert [(r["merchant"], r["direction"], r["user_category"], r["times_applied"]) for r in rules] == [
        ("Starbucks", "out", "TREATS", 2)]  # one rule, used twice (as COFFEE, then TREATS)
    client.patch("/api/v1/transactions", json={"ids": [first_id], "user_category": None})
    assert arrive("r-6", "card-a", 3.00) is None and client.get("/api/v1/transactions/rules").json()["rules"] == []

    # An imported export follows the rules too.
    with db.session() as sess:
        sess.add(Transaction(account_id=uuid.UUID(bank_id), plaid_transaction_id="r-7", date=date(2026, 9, 2),
                             amount=Decimal("1200"), name="LANDLORD LLC", category_primary="TRANSFER_OUT"))
    seven = next(t for t in client.get("/api/v1/transactions", params={"q": "LANDLORD"}).json()["transactions"])
    client.patch(f"/api/v1/transactions/{seven['id']}", json={"user_category": "RENT"})
    csv_text = "Date,Description,Amount\n05/02/2026,LANDLORD LLC,-1200.00\n"
    r = client.post("/api/v1/imports", json={"filename": "chk.csv", "account_id": bank_id,
                                            "content_b64": base64.b64encode(csv_text.encode()).decode()})
    assert r.status_code == 201, r.text
    with db.session() as sess:
        imported = sess.query(Transaction).filter_by(source="import", account_id=uuid.UUID(bank_id)).one()
        assert imported.user_category == "RENT"
    rule = client.get("/api/v1/transactions/rules").json()["rules"][0]
    assert client.delete(f"/api/v1/transactions/rules/{rule['id']}").status_code == 204
    assert client.get("/api/v1/transactions/rules").json()["rules"] == []
    assert card_id


def test_cash_and_card_history_is_rebuilt_from_transactions(client):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from sqlalchemy import select

    from server.app.models import Account, BalanceSnapshot, Transaction
    from server.app.services import history

    today = datetime.now(UTC).date()

    def day(n):
        return today - timedelta(days=n)

    with db.session() as sess:
        chk = Account(kind="plaid", name="Hist checking", type="depository", subtype="checking", current_balance=1000)
        card = Account(kind="plaid", name="Hist card", type="credit", subtype="credit card", is_liability=True,
                       current_balance=300)
        brokerage = Account(kind="plaid", name="Hist brokerage", type="investment", subtype="brokerage",
                            current_balance=5000)
        sess.add_all([chk, card, brokerage])
        sess.flush()
        for a in (chk, card, brokerage):  # linked today: the first real snapshot
            sess.add(BalanceSnapshot(account_id=a.id, as_of=today, current_balance=a.current_balance, source="plaid"))
        for acct, n, amt, tid, pending in (  # Plaid sign: + = money out
            (chk, 0, "50", "h1", False),        # spent today
            (chk, 2, "-200", "h2", False),      # paid two days ago
            (chk, 1, "999", "h3", True),        # pending: in no balance yet
            (card, 1, "100", "h4", False),      # a purchase
            (card, 3, "-80", "h5", False),      # a payment
            (brokerage, 2, "10", "h6", False),  # investments are never rebuilt
        ):
            sess.add(Transaction(account_id=acct.id, plaid_transaction_id=tid, date=day(n), amount=Decimal(amt),
                                 name=tid, pending=pending))
        sess.flush()
        assert history.derive_account(sess, chk) == 3
        assert history.derive_account(sess, chk) == 3  # replaces its rows, never duplicates
        assert history.derive_account(sess, card) == 4
        assert history.derive_account(sess, brokerage) == 0
        derived = {(r.account_id, r.as_of): r.current_balance for r in sess.execute(
            select(BalanceSnapshot).where(BalanceSnapshot.source == "derived")).scalars()}
        chk_id, card_id = chk.id, card.id
    # checking: 1000 today; +50 back before today's spend; -200 back before the pay
    assert [derived[(chk_id, day(n))] for n in (1, 2, 3)] == [Decimal("1050"), Decimal("1050"), Decimal("850")]
    # card owed: 300 today; 200 before the purchase; 280 before the payment
    assert [derived[(card_id, day(n))] for n in (1, 2, 3, 4)] == [Decimal(v) for v in ("300", "200", "200", "280")]

    nw = client.get("/api/v1/networth/history", params={"range": "1m"}).json()
    assert nw["points"][0]["date"] == day(4).isoformat() and nw["estimated_before"] == today.isoformat()
    # day 4: checking held at its first rebuilt value (850), card 280, brokerage held at 5000
    assert nw["points"][0]["net"] == "5570.00" and nw["points"][-1]["net"] == "5700.00"
    hist = client.get(f"/api/v1/accounts/{chk_id}/history", params={"range": "1m"}).json()["points"]
    assert [p["source"] for p in hist] == ["derived"] * 3 + ["plaid"]


def test_history_keeps_real_rows_and_never_breaks_a_sync(client, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from sqlalchemy import select

    from server.app.jobs import sync_item as job
    from server.app.models import Account, BalanceSnapshot, PlaidItem, Transaction
    from server.app.services import history

    today = datetime.now(UTC).date()
    with db.session() as sess:
        chk = Account(kind="plaid", name="Gap checking", type="depository", subtype="checking", current_balance=100)
        sess.add(chk)
        sess.flush()
        sess.add_all([  # a day Plaid gave no balance sits below the first usable one
            BalanceSnapshot(account_id=chk.id, as_of=today - timedelta(days=1), current_balance=None, source="plaid"),
            BalanceSnapshot(account_id=chk.id, as_of=today, current_balance=100, source="plaid"),
            Transaction(account_id=chk.id, plaid_transaction_id="g1", date=today - timedelta(days=2),
                        amount=Decimal("10"), name="g1"),
        ])
        sess.flush()
        assert history.derive_account(sess, chk) == 2  # days 2 and 3; day 1 keeps its real row

    def boom(sess, item):
        raise RuntimeError("boom")

    monkeypatch.setattr(job.history, "derive_item", boom)
    with db.session() as sess:
        item = PlaidItem(item_id="item-gap", institution_name="Gap", access_token_enc=b"x", status="active")
        sess.add(item)
        sess.flush()
        job._derive_history(sess, item)  # logged, not raised
        item.institution_name = "Gap Bank"  # the sync's own work still commits
    with db.session() as sess:
        assert sess.execute(select(PlaidItem.institution_name)
                            .where(PlaidItem.item_id == "item-gap")).scalar() == "Gap Bank"


def test_money_into_a_card_or_loan_is_a_payment(client):
    from datetime import date
    from decimal import Decimal

    from server.app.models import Account, Transaction

    with db.session() as sess:
        chk = Account(kind="plaid", name="Pay checking", type="depository", subtype="checking")
        card = Account(kind="plaid", name="Pay card", type="credit", subtype="credit card", is_liability=True)
        sess.add_all([chk, card])
        sess.flush()
        rows = [  # (account, amount: Plaid sign, + = out, primary, detailed)
            (chk, "-1000.00", "INCOME", "INCOME_WAGES"),
            (chk, "500.00", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"),  # the bank side of a card payment
            (card, "-500.00", "INCOME", "INCOME_OTHER_INCOME"),  # the card side, as some issuers report it
            (card, "-45.00", "LOAN_DISBURSEMENTS", "LOAN_DISBURSEMENTS_OTHER_DISBURSEMENT"),  # "PAYMENT-THANK YOU"
            (card, "-20.00", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_OTHER"),  # a refund
            (card, "100.00", "FOOD_AND_DRINK", "FOOD_AND_DRINK_RESTAURANT"),
        ]
        for i, (a, amt, primary, detailed) in enumerate(rows):
            sess.add(Transaction(account_id=a.id, plaid_transaction_id=f"pay-{i}", date=date(2026, 8, 3 + i),
                                 amount=amt, name=f"{primary.lower()}-{i}", pending=False,
                                 category_primary=primary, category_detailed=detailed))
        chk_id, card_id = str(chk.id), str(card.id)

    def cats(**params):
        r = client.get("/api/v1/transactions/summary",
                       params={"group_by": "category", "from": "2026-08-01", "to": "2026-08-31", **params})
        assert r.status_code == 200, r.text
        return {x["label"]: (Decimal(x["inflow"]), Decimal(x["outflow"])) for x in r.json()["rows"]}

    # Household: a card payment is a transfer on both sides, so income is the paycheck alone.
    assert cats() == {"INCOME": (1000, 0), "GENERAL_MERCHANDISE": (20, 0), "FOOD_AND_DRINK": (0, 100)}
    # On the card itself, its money in is its payments (and the refund).
    assert cats(account_id=card_id) == {"PAYMENTS": (545, 0), "GENERAL_MERCHANDISE": (20, 0),
                                        "FOOD_AND_DRINK": (0, 100)}
    # The bank account's own view still leaves the card payment out.
    assert cats(account_id=chk_id) == {"INCOME": (1000, 0)}
    txs = client.get("/api/v1/transactions", params={"account_id": card_id}).json()["transactions"]
    assert {t["name"]: t["category"] for t in txs}["income-2"] == "PAYMENT"


def _seed_insight_rows():
    """Two months of a household's money: paychecks and interest, card spending with a
    refund, a card payment (a transfer), a business account, and last year's coffee."""
    from datetime import date
    from decimal import Decimal

    from server.app.models import Account, Transaction

    with db.session() as sess:
        chk = Account(kind="plaid", name="Ins checking", type="depository", subtype="checking")
        card = Account(kind="plaid", name="Ins card", type="credit", subtype="credit card", is_liability=True)
        biz = Account(kind="plaid", name="Ins business", type="depository", subtype="checking", is_business=True)
        sess.add_all([chk, card, biz])
        sess.flush()
        rows = [  # (account, date, amount: + = out, primary, detailed, merchant_name, name)
            (chk, date(2026, 8, 3), "-3000", "INCOME", "INCOME_WAGES", None, "GOOGLE LLC PAYROLL PPD ID: 991"),
            (chk, date(2026, 9, 3), "-3000", "INCOME", "INCOME_WAGES", None, "GOOGLE LLC PAYROLL PPD ID: 992"),
            (chk, date(2026, 9, 15), "-12.50", "INCOME", "INCOME_INTEREST_EARNED", None, "INTEREST PAYMENT"),
            (card, date(2026, 8, 10), "100", "FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE", "Starbucks", "SBUX 1"),
            (card, date(2026, 9, 12), "50", "FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE", "Starbucks", "SBUX 2"),
            (card, date(2026, 9, 13), "200", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES",
             "Amazon", "AMZN 1"),
            (card, date(2026, 9, 20), "-40", "GENERAL_MERCHANDISE", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES",
             "Amazon", "AMZN refund"),
            (chk, date(2026, 9, 1), "500", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", None, "CARD PMT"),
            (card, date(2026, 9, 1), "-500", "LOAN_PAYMENTS", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", None, "THANK YOU"),
            (biz, date(2026, 9, 5), "-1000", "INCOME", "INCOME_OTHER_INCOME", None, "EBAY PAYOUT"),
            (biz, date(2026, 9, 6), "300", "GENERAL_SERVICES", "GENERAL_SERVICES_OTHER", "Shopify", "SHOPIFY"),
            (card, date(2025, 8, 10), "80", "FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE", "Starbucks", "SBUX 0"),
        ]
        for i, (a, d, amt, primary, detailed, merchant, name) in enumerate(rows):
            sess.add(Transaction(account_id=a.id, plaid_transaction_id=f"ins-{i}", date=d, amount=Decimal(amt),
                                 name=name, merchant_name=merchant, pending=False, category_primary=primary,
                                 category_detailed=detailed))


def test_insights_cash_flow_spending_merchants_and_scope(client):
    from decimal import Decimal

    _seed_insight_rows()

    def get(path, **params):
        r = client.get(f"/api/v1/insights/{path}", params={"from": "2026-08-01", "to": "2026-09-30", **params})
        assert r.status_code == 200, r.text
        return r.json()

    cf = get("cashflow")  # personal by default: no business rows, no card payment on either side
    assert [(p["label"], p["income"], p["spending"], p["net"]) for p in cf["periods"]] == [
        ("Aug 2026", "3000.00", "100.00", "2900.00"), ("Sep 2026", "3012.50", "210.00", "2802.50")]
    assert cf["totals"]["net"] == "5702.50" and round(cf["totals"]["savings_rate"], 4) == 0.9484
    assert cf["averages"] == {"income": "3006.25", "spending": "155.00", "net": "2851.25", "periods": 2}
    assert [(s["kind"], s["label"], s["amount"], s["count"]) for s in cf["income_sources"]] == [
        ("paychecks", "Google Llc", "6000.00", 2), ("interest", "Interest", "12.50", 1)]
    assert cf["spending_categories"] == [{"key": "GENERAL_MERCHANDISE", "amount": "160.00"},
                                         {"key": "FOOD_AND_DRINK", "amount": "150.00"}]
    assert get("cashflow", scope="business")["totals"]["income"] == "1000.00"
    assert get("cashflow", scope="all", grain="quarter")["periods"][0]["label"] == "Q3 2026"

    sp = get("spending")
    assert [(s["key"], s["values"]) for s in sp["series"]] == [
        ("GENERAL_MERCHANDISE", ["0.00", "160.00"]), ("FOOD_AND_DRINK", ["100.00", "50.00"])]
    drill = get("spending", category="GENERAL_MERCHANDISE")
    assert [s["key"] for s in drill["series"]] == ["GENERAL_MERCHANDISE_ONLINE_MARKETPLACES"]

    ms = get("merchants")["merchants"]
    assert [(m["label"], m["total"], m["count"], m["is_new"]) for m in ms] == [
        ("Amazon", "200.00", 1, True), ("Starbucks", "150.00", 2, False)]  # Starbucks first seen in 2025

    cmp = {r["key"]: (r["current"], r["previous"]) for r in get("compare")["rows"]}
    assert cmp == {"FOOD_AND_DRINK": ("150.00", "80.00"), "GENERAL_MERCHANDISE": ("160.00", "0.00")}

    pat = get("patterns")
    assert sum(Decimal(w["total"]) for w in pat["weekdays"]) == Decimal("310")
    assert pat["month_days"][12] == {"day": 13, "total": "200.00", "per_day": "100.00"}  # two 13ths in range
    assert client.get("/api/v1/insights/cashflow", params={"from": "2026-09-30", "to": "2026-08-01"}).status_code == 400


def test_insight_numbers_open_the_transactions_behind_them(client):
    """Every Insights number links to a Transactions list (GET /transactions with `flow`
    and Insights' groupings) that sums to it; several can be recategorized at once."""
    from datetime import date

    _seed_insight_rows()

    def txs(**params):
        r = client.get("/api/v1/transactions", params=params)
        assert r.status_code == 200, r.text
        body = r.json()
        return body["total"], body["sum"], sorted(t["name"] for t in body["transactions"])

    sep = {"from": "2026-09-01", "to": "2026-09-30", "scope": "personal"}
    both = {"from": "2026-08-01", "to": "2026-09-30", "scope": "personal"}
    # Cash flow: September's spending (210, net of the refund) and income (3012.50); no card payment, no business.
    assert txs(flow="spending", **sep) == (3, "210.00", ["AMZN 1", "AMZN refund", "SBUX 2"])
    assert txs(flow="income", **sep)[:2] == (2, "-3012.50")
    assert txs(flow="all", **sep)[1] == "-2802.50"  # the month's net, in Plaid's sign
    assert txs(flow="income", **{**sep, "scope": "business"})[1] == "-1000.00"
    # Income sources: a payer and kind, and "other income" as everything but the named ones.
    assert txs(flow="income", income_kind="paychecks", merchant="Google Llc", **both)[:2] == (2, "-6000.00")
    assert txs(flow="income", not_source="paychecks:Google Llc", **both)[1:] == ("-12.50", ["INTEREST PAYMENT"])
    assert txs(flow="income", income_kind="other income", **both)[0] == 0
    # Spending: a category, a detailed category inside it, and "other" as the categories not shown.
    assert txs(flow="spending", category="GENERAL_MERCHANDISE", **both)[1] == "160.00"
    assert txs(flow="spending", category="GENERAL_MERCHANDISE", detailed="GENERAL_MERCHANDISE_ONLINE_MARKETPLACES",
               **both)[1] == "160.00"
    assert txs(flow="spending", not_category="GENERAL_MERCHANDISE", **both)[1] == "150.00"
    # Merchants count purchases only, so their lists do too.
    assert txs(flow="spending", merchant="Amazon", direction="out", **both)[:2] == (1, "200.00")
    assert txs(flow="spending", merchant="Starbucks", direction="out", **both)[:2] == (2, "150.00")
    # Patterns: a weekday and a day of the month.
    assert txs(flow="spending", weekday=date(2026, 9, 13).weekday(), **both)[1] == "160.00"  # the refund: a Sunday too
    assert txs(flow="spending", day=12, **both)[1] == "50.00"
    # Without `flow` the list is unchanged: transfers and business rows show.
    assert txs(**{"from": "2026-09-01", "to": "2026-09-30"})[0] == 9
    assert client.get("/api/v1/transactions", params={"income_kind": "lottery"}).status_code == 400

    summ = client.get("/api/v1/transactions/summary", params={"flow": "spending", "group_by": "category", **sep}).json()
    assert [(r["key"], r["total"], r["inflow"], r["outflow"]) for r in summ["rows"]] == [
        ("GENERAL_MERCHANDISE", "160.00", "40.00", "200.00"), ("FOOD_AND_DRINK", "50.00", "0.00", "50.00")]
    summ = client.get("/api/v1/transactions/summary",
                      params={"flow": "spending", "merchant": "Amazon", "group_by": "month", **both}).json()
    assert [(r["key"], r["total"], r["count"]) for r in summ["rows"]] == [("2026-09", "160.00", 2)]

    # Select everything a filter matches, then file two of them somewhere new.
    ids = client.get("/api/v1/transactions/ids", params={"flow": "spending", **sep}).json()
    assert ids["total"] == 3
    picked = [t["id"] for t in client.get("/api/v1/transactions", params={"q": "SBUX", **both}).json()["transactions"]]
    r = client.patch("/api/v1/transactions", json={"ids": picked, "user_category": " COFFEE_BEANS "})
    assert r.status_code == 200 and r.json() == {"updated": 2, "user_category": "COFFEE_BEANS"}, r.text
    assert txs(category="COFFEE_BEANS")[0] == 2
    assert "COFFEE_BEANS" in client.get("/api/v1/transactions/categories").json()["categories"]
    assert client.patch("/api/v1/transactions", json={"ids": picked, "user_category": None}).json()[
        "user_category"] is None
    assert txs(category="COFFEE_BEANS")[0] == 0
    gone = client.patch("/api/v1/transactions",
                        json={"ids": [*picked, "00000000-0000-0000-0000-000000000000"], "user_category": "X"})
    assert gone.status_code == 404
    assert client.patch("/api/v1/transactions", json={"ids": []}).status_code == 422
    assert client.patch("/api/v1/transactions", json={"ids": picked}).status_code == 400  # nothing to change

    # Business or personal, one transaction at a time or many: Insights follow the flag, not just the account.
    shopify = [t["id"] for t in client.get("/api/v1/transactions", params={"q": "SHOPIFY"}).json()["transactions"]]
    starbucks = picked[:1]
    r = client.patch("/api/v1/transactions", json={"ids": starbucks, "business": True})
    assert r.status_code == 200 and r.json()["business"] is True
    one = client.patch(f"/api/v1/transactions/{shopify[0]}", json={"business": False}).json()
    assert one["is_business"] is False and one["business"] is False
    biz = client.get("/api/v1/insights/cashflow", params={**both, "scope": "business"}).json()
    personal = client.get("/api/v1/insights/cashflow", params=both).json()
    # The business account's $300 Shopify charge is personal now; a $50 Starbucks (SBUX 2) is business.
    assert biz["totals"]["spending"] == "50.00" and personal["totals"]["spending"] == "560.00"  # 310 - 50 + 300
    flagged = client.get("/api/v1/transactions", params={"q": "SBUX", "from": "2026-08-01"}).json()["transactions"]
    assert sorted((t["name"], t["is_business"], t["business"]) for t in flagged) == [
        ("SBUX 1", False, None), ("SBUX 2", True, True)]
    back = client.patch("/api/v1/transactions", json={"ids": [*starbucks, *shopify], "business": None}).json()
    assert back["business"] is None
    assert client.get("/api/v1/insights/cashflow", params={**both, "scope": "business"}).json()["totals"][
        "spending"] == "300.00"


def test_release_boots_older_code_on_a_newer_schema(client):
    """A newer release migrated past this code; restarting the older one must not fail."""
    from sqlalchemy import text

    from server.tools import release

    with db.engine().begin() as conn:
        head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        conn.execute(text("UPDATE alembic_version SET version_num = 'ffffffffffff'"))
    try:
        assert release.main() == 0
    finally:
        with db.engine().begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = :h"), {"h": head})
    assert release.main() == 0  # at head: the normal path


def test_subscriptions_are_found_flagged_and_alerted(client):
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from server.app.models import Account, Transaction
    from server.app.services.recurring import add_months

    today = datetime.now(UTC).date()

    def ago(n):
        return today - timedelta(days=n)

    def monthly(last, count):
        return [add_months(last, -k) for k in range(count - 1, -1, -1)]

    rows = []  # (date, amount, merchant, primary)
    rows += [(d, a, "Netflix", "ENTERTAINMENT") for d, a in
             zip(monthly(ago(10), 6), ["15.49"] * 4 + ["17.99"] * 2, strict=True)]  # a price rise
    rows += [(d, "11.99", "Spotify", "ENTERTAINMENT") for d in monthly(ago(3), 6)]
    rows += [(d, "2.99", "Apple", "GENERAL_SERVICES") for d in monthly(ago(20), 6)]  # two plans, one merchant
    rows += [(d, "10.99", "Apple", "GENERAL_SERVICES") for d in monthly(ago(7), 6)]
    rows += [(d, a, "Con Edison", "RENT_AND_UTILITIES") for d, a in
             zip(monthly(ago(15), 5), ["96.40", "132.10", "118.75", "88.20", "104.00"], strict=True)]
    rows += [(ago(340 + 365), "139.00", "Amazon Prime", "GENERAL_MERCHANDISE"), (ago(340), "139.00", "Amazon Prime",
                                                                               "GENERAL_MERCHANDISE")]
    rows += [(ago(2 + 7 * k), a, "Whole Foods", "FOOD_AND_DRINK") for k, a in
             enumerate(["80", "120", "95", "150", "110", "190", "70", "135"])]  # weekly, but shopping
    rows += [(ago(n), "45.00", "Shell", "TRANSPORTATION") for n in (100, 80, 45, 30)] + [(ago(5), "180.00", "Shell",
                                                                                         "TRANSPORTATION")]
    rows += [(ago(6), "412.40", "Delta", "TRAVEL"), (ago(5), "412.40", "Delta", "TRAVEL")]  # charged twice
    rows += [(d, a, "Trader Joe's", "FOOD_AND_DRINK") for d, a in
             zip([add_months(ago(9), -3 * k) for k in (2, 1, 0)], ["63.29", "64.10", "62.80"], strict=True)]  # shopping
    rows += [(d, "7.99", "Hulu", "ENTERTAINMENT") for d in monthly(ago(70), 6)]  # stopped: quiet for two months
    with db.session() as sess:
        card = Account(kind="plaid", name="Sub card", type="credit", subtype="credit card", is_liability=True)
        sess.add(card)
        sess.flush()
        for i, (d, amt, merchant, primary) in enumerate(rows):
            sess.add(Transaction(account_id=card.id, plaid_transaction_id=f"sub-{i}", date=d, amount=Decimal(amt),
                                 name=merchant.upper(), merchant_name=merchant, pending=False,
                                 category_primary=primary))

    assert client.post("/api/v1/recurring/detect").json() == {"found": 7}
    streams = {(s["merchant"], s["amount"]): s for s in client.get("/api/v1/recurring").json()["streams"]}
    # Hulu was found, but two months without a charge isn't recurring: not listed, not asked about.
    assert ("Hulu", "7.99") not in streams
    assert ("Hulu", "7.99") in {(s["merchant"], s["amount"]) for s in
                                client.get("/api/v1/recurring", params={"all": "true"}).json()["streams"]}
    assert {(m, a, s["cadence"]) for (m, a), s in streams.items()} == {
        ("Netflix", "17.99", "monthly"), ("Spotify", "11.99", "monthly"), ("Apple", "2.99", "monthly"),
        ("Apple", "10.99", "monthly"), ("Con Edison", "104.00", "monthly"), ("Amazon Prime", "139.00", "annual")}
    netflix = streams[("Netflix", "17.99")]
    assert netflix["previous_amount"] == "15.49" and netflix["price_changed_on"] == monthly(ago(10), 6)[4].isoformat()
    assert netflix["next_date"] == add_months(ago(10), 1).isoformat() and netflix["state"] == "active"

    # The user's verdict and name survive detection.
    r = client.patch(f"/api/v1/recurring/{netflix['id']}", json={"status": "confirmed", "name": "Netflix Premium"})
    assert r.json()["label"] == "Netflix Premium"
    client.patch(f"/api/v1/recurring/{streams[('Con Edison', '104.00')]['id']}", json={"status": "dismissed"})
    client.post("/api/v1/recurring/detect")
    listed = client.get("/api/v1/recurring").json()["streams"]
    after = {s["id"]: s for s in listed}
    assert after[netflix["id"]]["status"] == "confirmed" and after[netflix["id"]]["name"] == "Netflix Premium"
    assert streams[("Con Edison", "104.00")]["id"] not in after  # not recurring: gone from the list
    assert listed[0]["id"] == netflix["id"]  # recurring ones first, then the rest by their next charge
    assert [s["next_date"] for s in listed[1:]] == sorted(s["next_date"] for s in listed[1:])
    assert client.get("/api/v1/recurring").json()["monthly_confirmed"] == "17.99"

    up = client.get("/api/v1/recurring/upcoming", params={"days": 30}).json()
    labels = [i["label"] for i in up["items"]]
    assert "Netflix Premium" in labels and "Amazon Prime" in labels and "Con Edison" not in labels  # dismissed

    found = {a["kind"]: a for a in client.get("/api/v1/alerts").json()["alerts"]}
    assert found["price"]["merchant"] == "Netflix Premium" and found["price"]["previous"] == "15.49"
    assert found["duplicate"]["merchant"] == "Delta" and found["duplicate"]["amount"] == "412.40"
    assert found["large"]["merchant"] == "Shell" and found["large"]["usual"] == "45.00"
    assert client.post("/api/v1/alerts/dismiss", json={"key": found["duplicate"]["key"]}).status_code == 204
    assert "duplicate" not in {a["kind"] for a in client.get("/api/v1/alerts").json()["alerts"]}
    assert client.post("/api/v1/alerts/dismiss-all").json() == {"dismissed": 2}  # the price change and the large one
    assert client.get("/api/v1/alerts").json()["alerts"] == []
    assert client.post("/api/v1/alerts/dismiss-all").json() == {"dismissed": 0}


def test_dashboard_is_per_person_seeded_pinned_and_arranged(client):
    from server.app.models import DashboardWidget, User

    d = client.get("/api/v1/dashboard").json()  # first read: Overview as it always was
    assert d["columns"] == 2 and [w["view"] for w in d["widgets"]] == [
        "networth", "split", "upcoming", "alerts", "calendar", "accounts"]
    pinned = client.post("/api/v1/dashboard/widgets", json={
        "view": "cashflow", "settings": {"range": "12m", "grain": "quarter", "scope": "business"}}).json()
    assert pinned["size"] == "full" and pinned["settings"]["grain"] == "quarter" and pinned["position"] == 6
    assert client.post("/api/v1/dashboard/widgets", json={"view": "nope"}).status_code == 400
    too_big = {"view": "loans", "settings": {"x": "y" * 3000}}
    assert client.post("/api/v1/dashboard/widgets", json=too_big).status_code == 400

    small = client.patch(f"/api/v1/dashboard/widgets/{pinned['id']}", json={"size": "narrow"}).json()
    assert small["size"] == "narrow" and small["settings"]["scope"] == "business"
    ids = [w["id"] for w in client.get("/api/v1/dashboard").json()["widgets"]]
    moved = client.put("/api/v1/dashboard/order", json={"widget_ids": [ids[-1], *ids[:-1]]}).json()
    assert moved["widgets"][0]["view"] == "cashflow"
    assert client.put("/api/v1/dashboard/order", json={"widget_ids": ids[:-1]}).status_code == 400  # every widget, once
    assert client.put("/api/v1/dashboard/columns", json={"columns": 3}).json()["columns"] == 3
    assert client.put("/api/v1/dashboard/columns", json={"columns": 4}).status_code == 422

    for w in client.get("/api/v1/dashboard").json()["widgets"]:  # emptied stays empty...
        assert client.delete(f"/api/v1/dashboard/widgets/{w['id']}").status_code == 204
    assert client.get("/api/v1/dashboard").json()["widgets"] == []
    reset = client.post("/api/v1/dashboard/reset").json()  # ...until reset
    assert len(reset["widgets"]) == 6 and reset["columns"] == 2

    with db.session() as sess:  # someone else's widget is out of reach
        other = User(email="someone@example.com", role="member")
        sess.add(other)
        sess.flush()
        theirs = DashboardWidget(user_id=other.id, view="loans", settings={}, size="narrow", position=0)
        sess.add(theirs)
        sess.flush()
        theirs_id = str(theirs.id)
    assert client.patch(f"/api/v1/dashboard/widgets/{theirs_id}", json={"size": "full"}).status_code == 404
    assert client.delete(f"/api/v1/dashboard/widgets/{theirs_id}").status_code == 404
    assert theirs_id not in {w["id"] for w in client.get("/api/v1/dashboard").json()["widgets"]}
