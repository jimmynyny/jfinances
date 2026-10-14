"""Net worth and debt insights (services/wealth.py, GET /insights/{networth,homes,loans,cards})."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from server.app import db
from server.app.config import reset_settings_cache
from server.app.services.wealth import amortize
from server.tests.conftest import migrate, pg_url

URL = pg_url()


def test_amortization_matches_the_textbook():
    a = amortize(Decimal("100000"), Decimal("6"), 360, date(2026, 11, 1))
    assert a["payment"] == Decimal("599.55") and a["months"] == 360 and a["payoff"] == date(2056, 10, 31)
    assert abs(a["interest"] - Decimal("115838.19")) < 1  # cent rounding month by month
    assert sum(y["principal"] for y in a["per_year"]) == Decimal("100000")
    more = amortize(Decimal("100000"), Decimal("6"), 0, date(2026, 11, 1), extra=Decimal("100"), payment=a["payment"])
    assert more["months"] < 360 and more["interest"] < a["interest"]


@pytest.fixture
def client(monkeypatch):
    if URL is None:
        pytest.skip("TEST_DATABASE_URL not reachable")
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("DEV_LOGIN_EMAIL", "jimmy@example.com")
    reset_settings_cache()
    db.reset_engine_cache()
    migrate(URL, fresh=True)
    from fastapi.testclient import TestClient

    from server.app.web import app
    with TestClient(app) as c:
        yield c


def test_net_worth_homes_loans_and_cards(client):
    from server.app.models import Account, BalanceSnapshot, Liability, Transaction
    from server.app.services.recurring import add_months

    today = datetime.now(UTC).date()
    with db.session() as sess:
        chk = Account(kind="plaid", name="Checking", type="depository", current_balance=5000)
        brk = Account(kind="plaid", name="Brokerage", type="investment", current_balance=20000)
        house = Account(kind="manual", name="Main house", type="manual", manual_category="real_estate",
                        current_balance=500000)
        card = Account(kind="plaid", name="Card", type="credit", is_liability=True, current_balance=1000,
                       credit_limit=10000)
        sess.add_all([chk, brk, house, card])
        sess.flush()
        mortgage = Account(kind="plaid", name="Mortgage", type="loan", subtype="mortgage", is_liability=True,
                           current_balance=300000, secured_by_id=house.id)
        sess.add(mortgage)
        sess.flush()
        for a in (chk, brk, house, card, mortgage):
            sess.add(BalanceSnapshot(account_id=a.id, as_of=today, current_balance=a.current_balance,
                                     source="manual" if a.kind == "manual" else "plaid"))
        sess.add(Liability(account_id=mortgage.id, kind="mortgage", interest_rate_pct=Decimal("6"),
                           maturity_date=add_months(today, 360), next_payment_amount=Decimal("2400"),
                           raw={"ytd_interest_paid": 12000.5}))
        last_month = add_months(today, -1)
        sess.add_all([
            Transaction(account_id=card.id, plaid_transaction_id="int-1", date=last_month, amount=Decimal("25"),
                        name="INTEREST CHARGE", pending=False, category_primary="BANK_FEES",
                        category_detailed="BANK_FEES_INTEREST_CHARGE"),
            Transaction(account_id=card.id, plaid_transaction_id="fee-1", date=last_month, amount=Decimal("35"),
                        name="LATE FEE", pending=False, category_primary="BANK_FEES",
                        category_detailed="BANK_FEES_LATE_FEES"),
        ])
        mortgage_id, house_id = str(mortgage.id), str(house.id)

    nw = client.get("/api/v1/insights/networth", params={"range": "1y"}).json()
    assert {g["key"] for g in nw["groups"]} == {"cash", "investments", "real_estate", "credit_cards", "loans"}
    assert nw["points"][-1]["net"] == "224000.00" and nw["points"][-1]["date"] == today.isoformat()

    (home,) = client.get("/api/v1/insights/homes").json()["homes"]
    assert home["id"] == house_id and home["equity"] == "200000.00" and home["ltv"] == 0.6
    assert home["loans"][0]["id"] == mortgage_id and home["loans"][0]["rate"] == 6.0

    (loan,) = client.get("/api/v1/insights/loans", params={"extra": "500"}).json()["loans"]
    assert loan["schedule"]["payment"] == "1798.65"  # principal and interest; the 2,400 bill includes escrow
    assert loan["schedule"]["months"] == 360 and loan["ytd_interest"] == "12000.50"
    assert loan["what_if"]["months_saved"] > 0 and float(loan["what_if"]["interest_saved"]) > 50000

    cards = client.get("/api/v1/insights/cards").json()
    assert cards["cards"][0]["utilization"] == 0.1
    assert cards["totals"] == {"interest": "25.00", "fees": "35.00"}
    assert today - timedelta(days=400) < date.fromisoformat(cards["overall"][0]["date"])
