"""Market data, benchmarks and time-weighted returns (services/prices.py, benchmarks.py, performance.py)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest

from server.app import db
from server.app.config import reset_settings_cache
from server.tests.conftest import migrate, pg_url

URL = pg_url()
pytestmark = pytest.mark.skipif(URL is None, reason="TEST_DATABASE_URL not reachable")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    monkeypatch.setenv("DEV_LOGIN_EMAIL", "jimmy@example.com")
    monkeypatch.setenv("FRED_API_KEY", "fredkey0123456789abcdef0123456789")
    monkeypatch.setenv("TIINGO_API_KEY", "tiingokey0123456789abcdef0123456789abcd")
    reset_settings_cache()
    db.reset_engine_cache()
    migrate(URL, fresh=True)
    from fastapi.testclient import TestClient

    from server.app.web import app
    with TestClient(app) as c:
        yield c
    reset_settings_cache()


def _mock(seen: list[httpx.Request], *, limited: bool = False) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "api.stlouisfed.org":
            return httpx.Response(200, json={"observations": [
                {"date": "2026-01-02", "value": "5000.5"}, {"date": "2026-01-05", "value": "."},
                {"date": "2026-01-06", "value": "5100"}]})
        if limited:
            return httpx.Response(429, json={"detail": "slow down"})
        return httpx.Response(200, json=[{"date": "2026-01-02T00:00:00.000Z", "close": 100, "adjClose": 98.5},
                                         {"date": "2026-01-05T00:00:00.000Z", "close": 101, "adjClose": 99.4}])
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_prices_are_fetched_stored_and_resumed(client):
    from sqlalchemy import select

    from server.app.models import PricePoint
    from server.app.services import prices

    seen: list[httpx.Request] = []
    with db.session() as sess:
        out = prices.refresh(sess, ["fred:SP500", "tiingo:SPY", "tiingo_close:SPY"], client=_mock(seen),
                             today=date(2026, 1, 7))
        assert out == {"fred:SP500": 2, "tiingo:SPY": 2, "tiingo_close:SPY": 2}  # FRED's "." day skipped
        stored = {(p.series, p.date): p.close for p in sess.execute(select(PricePoint)).scalars()}
    assert stored[("tiingo:SPY", date(2026, 1, 5))] == Decimal("99.4")  # adjusted for benchmarks
    assert stored[("tiingo_close:SPY", date(2026, 1, 5))] == Decimal("101")  # as traded for holdings
    fred = next(r for r in seen if r.url.host == "api.stlouisfed.org")
    assert fred.url.params["observation_start"] == prices.HISTORY_START.isoformat()
    tiingo = next(r for r in seen if r.url.host == "api.tiingo.com")
    assert tiingo.headers["Authorization"].startswith("Token ") and "token" not in tiingo.url.params  # key in a header

    seen.clear()
    with db.session() as sess:  # the next run starts after the last stored close, and a 429 stops Tiingo
        out = prices.refresh(sess, ["fred:SP500", "tiingo:SPY", "tiingo:DIA"], client=_mock(seen, limited=True),
                             today=date(2026, 1, 9))
    assert seen[0].url.params["observation_start"] == "2026-01-07"
    assert out["tiingo:SPY"] == -1 and "tiingo:DIA" not in out  # stopped after the first 429


def test_portfolio_time_weighted_return_against_a_benchmark(client):
    from server.app.models import (
        Account,
        BalanceSnapshot,
        Holding,
        InvestmentTransaction,
        PricePoint,
        Security,
    )

    today = datetime.now(UTC).date()

    def ago(n):
        return today - timedelta(days=n)

    with db.session() as sess:
        acct = Account(kind="plaid", name="Brokerage", type="investment", subtype="brokerage",
                       current_balance=Decimal("1200"))
        acme = Security(plaid_security_id="sec-acme", ticker="ACME", name="Acme", type="equity", close_price=120)
        sess.add_all([acct, acme])
        sess.flush()
        sess.add(Holding(account_id=acct.id, security_id=acme.id, quantity=10, institution_price=120,
                         institution_value=1200))
        sess.add(BalanceSnapshot(account_id=acct.id, as_of=today, current_balance=1200, source="plaid"))
        for i, (n, kind, sub, qty, amount, price) in enumerate([  # Plaid: amount + = cash out
            (20, "cash", "deposit", None, "-500", None), (20, "buy", "buy", "5", "500", "100"),
            (10, "cash", "deposit", None, "-550", None), (10, "buy", "buy", "5", "550", "110"),
        ]):
            sess.add(InvestmentTransaction(account_id=acct.id, plaid_investment_transaction_id=f"it-{i}", date=ago(n),
                                           type=kind, subtype=sub, quantity=qty, amount=amount, price=price,
                                           security_id=acme.id if kind == "buy" else None))
        for n in range(30, -1, -1):  # ACME: 100, then 110 from 15 days ago, 120 from 5 days ago
            close = 100 if n > 15 else 110 if n > 5 else 120
            sess.add(PricePoint(series="tiingo_close:ACME", date=ago(n), close=close))
            sess.add(PricePoint(series="fred:SP500", date=ago(n), close=1000 + (30 - n) * 10))
        acct_id = str(acct.id)

    r = client.get("/api/v1/investments/performance", params={"range": "3m", "benchmark": "sp500,world"}).json()
    s = r["series"]
    assert s[0]["date"] == ago(20).isoformat() and s[0]["value"] == "500.00"  # rebuilt from the first deposit
    assert [x["value"] for x in s if x["date"] in (ago(16).isoformat(), ago(15).isoformat(), ago(10).isoformat())] == [
        "500.00", "550.00", "1100.00"]
    assert round(s[-1]["return"], 6) == 0.2  # ACME 100 -> 120; the deposits are not gains
    assert r["estimated_before"] == today.isoformat()
    assert r["accounts"][0]["rebuilt"] is True and r["accounts"][0]["coverage"] == 1.0
    sp, world = r["benchmarks"]
    assert sp["source"] == "fred:SP500" and sp["points"][0]["date"] == ago(20).isoformat()
    assert sp["points"][0]["return"] == 0.0 and round(sp["points"][-1]["return"], 6) == round(1300 / 1100 - 1, 6)
    assert world["source"] is None and world["points"] == []  # no VT prices stored
    avail = {b["key"]: b["available"] for b in r["available"]}
    assert avail["sp500"] is True and avail["world"] is False and avail["sixty_forty"] is False
    one = client.get("/api/v1/investments/performance", params={"range": "3m", "account_id": acct_id}).json()
    assert round(one["series"][-1]["return"], 6) == 0.2
