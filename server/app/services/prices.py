"""Daily closes from public market data: benchmarks, and the securities held.

Two providers, each behind its own key in Railway variables (never in code,
never in logs: logging redacts both and silences httpx's URL lines):

- FRED (St. Louis Fed), FRED_API_KEY: SP500, DJIA, NASDAQ100 (price indexes,
  about ten years), CBBTCUSD (Bitcoin), CPIAUCSL (consumer prices, monthly).
- Tiingo, TIINGO_API_KEY: funds and stocks. "tiingo:CODE" stores the
  dividend-adjusted close (a benchmark's total return); "tiingo_close:CODE"
  the close as traded (to value a holding's past quantity; its dividends
  arrive as cash). "tiingo_crypto:btcusd" for crypto.

Only series codes and dates leave the app. A refresh fetches each series from
the day after its last stored close (from HISTORY_START the first time). A
provider error is logged by series and status only, never by URL; a 429
stops that provider's run until the next one.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..config import Settings, settings
from ..models import Holding, InvestmentTransaction, PricePoint, Security

log = logging.getLogger(__name__)

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
TIINGO_DAILY = "https://api.tiingo.com/tiingo/daily/{code}/prices"
TIINGO_CRYPTO = "https://api.tiingo.com/tiingo/crypto/prices"
HISTORY_START = date(2014, 1, 1)
#: Securities priced from Tiingo's daily feed (Plaid's security types).
PRICED_TYPES = {"equity", "etf", "mutual fund"}


class PriceError(RuntimeError):
    """A provider answered, but not with prices. Carries no URL."""


class RateLimited(PriceError):
    pass


def _check(r: httpx.Response, series: str) -> None:
    if r.status_code == 429:
        raise RateLimited(f"{series}: rate limited")
    if r.status_code != 200:
        raise PriceError(f"{series}: HTTP {r.status_code}")


def _num(v: object) -> Decimal | None:
    if v in (None, "", "."):
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def fetch(series: str, start: date, client: httpx.Client, s: Settings) -> list[tuple[date, Decimal]]:
    provider, code = series.split(":", 1)
    out: list[tuple[date, Decimal]] = []
    if provider == "fred":
        if not s.fred_api_key:
            raise PriceError("FRED_API_KEY is not set")
        r = client.get(FRED_URL, params={"series_id": code, "api_key": s.fred_api_key, "file_type": "json",
                                         "observation_start": start.isoformat()})
        _check(r, series)
        for o in r.json().get("observations", []):
            v = _num(o.get("value"))
            if v is not None:
                out.append((date.fromisoformat(o["date"]), v))
        return out
    if provider in ("tiingo", "tiingo_close", "tiingo_crypto"):
        if not s.tiingo_api_key:
            raise PriceError("TIINGO_API_KEY is not set")
        headers = {"Authorization": f"Token {s.tiingo_api_key}"}
        if provider == "tiingo_crypto":
            r = client.get(TIINGO_CRYPTO, headers=headers,
                           params={"tickers": code, "startDate": start.isoformat(), "resampleFreq": "1day"})
            _check(r, series)
            body = r.json()
            rows = body[0].get("priceData", []) if body else []
            field = "close"
        else:
            r = client.get(TIINGO_DAILY.format(code=code), headers=headers, params={"startDate": start.isoformat()})
            _check(r, series)
            rows = r.json()
            field = "adjClose" if provider == "tiingo" else "close"
        for x in rows:
            v = _num(x.get(field))
            if v is not None:
                out.append((date.fromisoformat(str(x["date"])[:10]), v))
        return out
    raise PriceError(f"{series}: unknown provider")


def store(sess: Session, series: str, points: Iterable[tuple[date, Decimal]]) -> int:
    rows = [{"series": series, "date": d, "close": v} for d, v in points]
    if not rows:
        return 0
    stmt = insert(PricePoint).values(rows)
    sess.execute(stmt.on_conflict_do_update(index_elements=["series", "date"], set_={"close": stmt.excluded.close}))
    return len(rows)


def held_series(sess: Session) -> list[str]:
    """Price series for the securities held now or traded in the last two years."""
    since = datetime.now(UTC).date() - timedelta(days=760)
    ids = set(sess.execute(select(Holding.security_id)).scalars())
    ids |= set(sess.execute(select(InvestmentTransaction.security_id)
                            .where(InvestmentTransaction.date >= since,
                                   InvestmentTransaction.security_id.is_not(None))).scalars())
    out = set()
    for sec in sess.execute(select(Security).where(Security.id.in_(ids))).scalars():
        ticker = (sec.ticker or "").strip()
        if not ticker or sec.is_cash_equivalent:
            continue
        kind = (sec.type or "").lower()
        if kind in PRICED_TYPES:
            out.add(f"tiingo_close:{ticker.upper().replace('.', '-')}")
        elif kind == "cryptocurrency":
            out.add(f"tiingo_crypto:{ticker.lower()}usd")
    return sorted(out)


def wanted_series(sess: Session, s: Settings | None = None) -> list[str]:
    """Benchmarks first (FRED and Tiingo, as their keys allow), then held securities."""
    from .benchmarks import BENCHMARKS
    s = s or settings()
    want: list[str] = []
    for b in BENCHMARKS:
        for series in b.all_series():
            if series not in want and _has_key(series, s):
                want.append(series)
    if s.tiingo_api_key:
        want += [x for x in held_series(sess) if x not in want]
    return want


def _has_key(series: str, s: Settings) -> bool:
    return bool(s.fred_api_key) if series.startswith("fred:") else bool(s.tiingo_api_key)


def refresh(sess: Session, series_keys: list[str] | None = None, *, client: httpx.Client | None = None,
            today: date | None = None) -> dict[str, int]:
    """Bring each series up to date. Returns closes stored per series (-1: failed)."""
    s = settings()
    today = today or datetime.now(UTC).date()
    keys = series_keys if series_keys is not None else wanted_series(sess, s)
    results: dict[str, int] = {}
    limited: set[str] = set()
    own = client is None
    c = client or httpx.Client(timeout=30.0)
    try:
        for key in keys:
            provider = key.split(":", 1)[0].removesuffix("_close").removesuffix("_crypto")
            if provider in limited:
                continue
            last = sess.execute(select(func.max(PricePoint.date)).where(PricePoint.series == key)).scalar()
            start = last + timedelta(days=1) if last else HISTORY_START
            if start > today:
                results[key] = 0
                continue
            try:
                results[key] = store(sess, key, fetch(key, start, c, s))
            except RateLimited as e:
                log.warning("prices: %s; stopping %s until the next run", e, provider)
                limited.add(provider)
                results[key] = -1
            except (PriceError, httpx.HTTPError, ValueError, KeyError) as e:
                log.warning("prices: %s failed (%s)", key, e if isinstance(e, PriceError) else type(e).__name__)
                results[key] = -1
            sess.flush()
    finally:
        if own:
            c.close()
    return results


def series_points(sess: Session, series: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    return [(d, Decimal(v)) for d, v in sess.execute(
        select(PricePoint.date, PricePoint.close).where(PricePoint.series == series, PricePoint.date >= start,
                                                        PricePoint.date <= end).order_by(PricePoint.date))]


def first_date(sess: Session, series: str) -> date | None:
    return sess.execute(select(func.min(PricePoint.date)).where(PricePoint.series == series)).scalar()
