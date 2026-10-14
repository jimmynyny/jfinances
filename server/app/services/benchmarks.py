"""Benchmarks to compare investment returns against (docs/30 "Market data").

Each benchmark lists its series in order of preference: a fund through Tiingo
first (its dividend-adjusted close is a total return, comparable with the
portfolio's time-weighted return, which counts dividends), then FRED's index
(price only, about ten years). The first series with data covering the range
is used, and the response says which. 60/40 is a blend rebalanced daily;
inflation is consumer prices (monthly, held through the month).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from . import prices


@dataclass(frozen=True)
class Benchmark:
    key: str
    label: str
    #: Series in order of preference.
    series: tuple[str, ...] = ()
    #: A blend: (series, weight), rebalanced daily.
    blend: tuple[tuple[str, Decimal], ...] = field(default=())
    note: str = ""

    def all_series(self) -> list[str]:
        return list(self.series) + [s for s, _ in self.blend]


BENCHMARKS = (
    Benchmark("sp500", "S&P 500", ("tiingo:SPY", "fred:SP500")),
    Benchmark("dow", "Dow Jones", ("tiingo:DIA", "fred:DJIA")),
    Benchmark("nasdaq100", "Nasdaq-100", ("tiingo:QQQ", "fred:NASDAQ100")),
    Benchmark("bitcoin", "Bitcoin", ("fred:CBBTCUSD", "tiingo_crypto:btcusd")),
    Benchmark("world", "World stocks", ("tiingo:VT",)),
    Benchmark("bonds", "US bonds", ("tiingo:AGG",)),
    Benchmark("gold", "Gold", ("tiingo:GLD",)),
    Benchmark("sixty_forty", "60/40 world stocks and bonds",
              blend=(("tiingo:VT", Decimal("0.6")), ("tiingo:AGG", Decimal("0.4")))),
    Benchmark("inflation", "Inflation", ("fred:CPIAUCSL",), note="consumer prices"),
)
BY_KEY = {b.key: b for b in BENCHMARKS}
#: How far before the range a series must start to count as covering it (weekends, holidays, monthly CPI).
SLACK = timedelta(days=35)


def daily(points: list[tuple[date, Decimal]], start: date, end: date) -> dict[date, Decimal]:
    """Every day from start to end, each carrying the latest close on or before it."""
    out: dict[date, Decimal] = {}
    last = None
    i = 0
    d = start
    while d <= end:
        while i < len(points) and points[i][0] <= d:
            last = points[i][1]
            i += 1
        if last is not None:
            out[d] = last
        d += timedelta(days=1)
    return out


def _covering(sess: Session, b: Benchmark, start: date) -> str | None:
    for s in b.series:
        first = prices.first_date(sess, s)
        if first is not None and first <= start + timedelta(days=7):
            return s
    return None


def growth(sess: Session, key: str, start: date, end: date) -> tuple[dict[date, float], str] | None:
    """Cumulative return per day from `start` (0.0 on the first day), and the
    series it came from; None when no series covers the range."""
    b = BY_KEY[key]
    if b.blend:
        legs = []
        for s, w in b.blend:
            first = prices.first_date(sess, s)
            if first is None or first > start + timedelta(days=7):
                return None
            legs.append((daily(prices.series_points(sess, s, start - SLACK, end), start, end), w))
        days = sorted(set.intersection(*(set(leg) for leg, _ in legs)))
        out: dict[date, float] = {}
        level = Decimal(1)
        prev = None
        for d in days:
            if prev is not None:
                level *= 1 + sum((w * (leg[d] / leg[prev] - 1) for leg, w in legs), Decimal(0))
            out[d] = float(level - 1)
            prev = d
        return out, "+".join(s for s, _ in b.blend)
    s = _covering(sess, b, start)
    if s is None:
        return None
    filled = daily(prices.series_points(sess, s, start - SLACK, end), start, end)
    if not filled:
        return None
    base = filled[min(filled)]
    return {d: float(v / base - 1) for d, v in filled.items()}, s


def available(sess: Session) -> list[dict]:
    """Every benchmark and whether stored prices can draw it today."""
    out = []
    for b in BENCHMARKS:
        firsts = [prices.first_date(sess, s) for s in b.all_series()]
        have = [f for f in firsts if f is not None]
        ok = bool(have) and (all(f is not None for f in firsts) if b.blend else True)
        out.append({"key": b.key, "label": b.label, "available": ok,
                    "since": min(have).isoformat() if ok and have else None, "note": b.note})
    return out
