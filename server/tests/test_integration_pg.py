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


def test_insights_cash_flow_spending_merchants_and_scope(client):
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
    with db.session() as sess:
        card = Account(kind="plaid", name="Sub card", type="credit", subtype="credit card", is_liability=True)
        sess.add(card)
        sess.flush()
        for i, (d, amt, merchant, primary) in enumerate(rows):
            sess.add(Transaction(account_id=card.id, plaid_transaction_id=f"sub-{i}", date=d, amount=Decimal(amt),
                                 name=merchant.upper(), merchant_name=merchant, pending=False,
                                 category_primary=primary))

    assert client.post("/api/v1/recurring/detect").json() == {"found": 6}
    streams = {(s["merchant"], s["amount"]): s for s in client.get("/api/v1/recurring").json()["streams"]}
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
    after = {s["id"]: s for s in client.get("/api/v1/recurring").json()["streams"]}
    assert after[netflix["id"]]["status"] == "confirmed" and after[netflix["id"]]["name"] == "Netflix Premium"
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
