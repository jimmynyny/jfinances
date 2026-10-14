"""Investment performance: time-weighted return, for the portfolio and each account.

Value per day, per investment account:
- From its first snapshot on: balance_snapshots (the balance Plaid reports,
  carried over days without one).
- Before that, as far back as investment transactions reach (about two
  years): holdings are rebuilt by undoing every later trade and cash movement
  from today's holdings, and priced day by day (price_curve: the security's
  close as traded, "tiingo_close:" series, when its prices agree with the
  trades; else the prices it traded at, interpolated, which is how a 401(k)
  trust with no public ticker gets a history). A security with neither keeps
  today's price; `coverage` is the share of the rebuilt value that had real
  prices. A rebuild that goes negative (missing transactions) is dropped.
- Days an imported statement covers have derived snapshots (history.py); they
  value the account but don't count as tracked.

Flows are money moved in or out, not earned: cash deposits, contributions and
withdrawals, and transfers. A day's return is (value - flows) / previous
value - 1, and the time-weighted return chains them, so a deposit is never a
gain. For the portfolio, an account's first day also counts as a flow (it
joined; it didn't grow).
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, BalanceSnapshot, Holding, InvestmentTransaction, PlaidItem, Security
from . import prices
from .benchmarks import daily

ZERO = Decimal(0)
#: Snapshots the connection or the person recorded (not rebuilt): "tracked".
LIVE = ("plaid", "carry", "manual")
EXTERNAL_CASH = {"deposit", "contribution", "withdrawal"}
EXTERNAL_TRANSFER = {"transfer", "send", "request", "deposit", "withdrawal"}


def _bought_with_new_money(t: InvestmentTransaction) -> bool:
    """A buy the connection files as a contribution (a 401(k) payroll buy in one row):
    new money in, spent at once, so no cash moves inside the account."""
    return (t.type or "").lower() == "buy" and (t.subtype or "").lower() == "contribution"


def is_external(t: InvestmentTransaction) -> bool:
    kind, sub = (t.type or "").lower(), (t.subtype or "").lower()
    return (kind == "cash" and sub in EXTERNAL_CASH) or (kind == "transfer" and sub in EXTERNAL_TRANSFER) \
        or _bought_with_new_money(t)


def flow_of(t: InvestmentTransaction) -> Decimal:
    """Money into the account (+) or out (-). Plaid's amount is positive when cash leaves."""
    if _bought_with_new_money(t):
        return abs(Decimal(t.amount)) if t.amount else Decimal(t.quantity or 0) * Decimal(t.price or 0)
    if t.amount:
        return -Decimal(t.amount)
    if t.quantity and t.price:
        return Decimal(t.quantity) * Decimal(t.price)
    return ZERO


def _trade_points(sess: Session, sec: Security) -> list[tuple[date, Decimal]]:
    """The prices a security actually traded or was valued at: every trade's price
    (any account), the connection's latest holding price and its close."""
    pts: dict[date, list[Decimal]] = defaultdict(list)
    for d, price in sess.execute(select(InvestmentTransaction.date, InvestmentTransaction.price).where(
            InvestmentTransaction.security_id == sec.id, InvestmentTransaction.price > 0,
            InvestmentTransaction.quantity != 0)):
        pts[d].append(Decimal(price))
    for d, price in sess.execute(select(Holding.institution_price_as_of, Holding.institution_price).where(
            Holding.security_id == sec.id, Holding.institution_price > 0,
            Holding.institution_price_as_of.is_not(None))):
        pts[d].append(Decimal(price))
    if sec.close_price and sec.close_price_as_of:
        pts[sec.close_price_as_of].append(Decimal(sec.close_price))
    return sorted((d, sum(v, ZERO) / len(v)) for d, v in pts.items())


def interpolate(points: list[tuple[date, Decimal]], start: date, end: date) -> dict[date, Decimal]:
    """Every day from start to end: straight lines between known prices, flat beyond them."""
    if not points:
        return {}
    out: dict[date, Decimal] = {}
    j = 0
    d = start
    while d <= end:
        while j < len(points) - 1 and points[j + 1][0] <= d:
            j += 1
        (d0, p0) = points[j]
        if d <= d0 or j == len(points) - 1:
            out[d] = p0
        else:
            d1, p1 = points[j + 1]
            out[d] = p0 + (p1 - p0) * Decimal((d - d0).days) / Decimal((d1 - d0).days)
        d += timedelta(days=1)
    return out


def _agrees(market: list[tuple[date, Decimal]], trades: list[tuple[date, Decimal]]) -> bool:
    """Whether a ticker's closes are this security's prices: a 401(k) trust can carry
    its retail fund's ticker, whose price is a different number."""
    closes = dict(market)
    ratios = []
    for d, price in trades:
        near = next((closes[d - timedelta(days=k)] for k in range(5) if d - timedelta(days=k) in closes), None)
        if near:
            ratios.append(price / near)
    if not ratios:
        return True
    ratios.sort()
    return Decimal("0.98") <= ratios[len(ratios) // 2] <= Decimal("1.02")


def price_curve(sess: Session, sec: Security, start: date, end: date) -> tuple[dict[date, Decimal], bool]:
    """The security's price every day from start to end, and whether that is observed
    (market closes, or prices it traded at) rather than one price held flat."""
    trades = _trade_points(sess, sec)
    ticker = (sec.ticker or "").strip()
    if ticker and (sec.type or "").lower() in prices.PRICED_TYPES:
        pts = prices.series_points(sess, f"tiingo_close:{ticker.upper().replace('.', '-')}",
                                   start - timedelta(days=10), end)
        if pts and _agrees(pts, trades):
            curve = daily(pts, start, end)
            first = min(curve) if curve else None
            if first is not None:  # before the first close: that close
                d = start
                while d < first:
                    curve[d] = curve[first]
                    d += timedelta(days=1)
            return curve, True
    return interpolate(trades, start, end), len({d for d, _ in trades}) >= 2


@dataclass
class AccountSeries:
    account_id: uuid.UUID
    name: str
    values: dict[date, Decimal] = field(default_factory=dict)
    flows: dict[date, Decimal] = field(default_factory=dict)
    #: First day backed by a real snapshot; days before it were rebuilt.
    tracked_since: date | None = None
    rebuilt: bool = False
    coverage: float | None = None


def _rebuild(sess: Session, acct: Account, txs: list[InvestmentTransaction], start: date, last_day: date,
             today: date) -> tuple[dict[date, Decimal], float | None]:
    holdings = list(sess.execute(select(Holding, Security).join(Security, Security.id == Holding.security_id)
                                 .where(Holding.account_id == acct.id)))
    if not holdings and not txs:
        return {}, None
    qty: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
    flat: dict[uuid.UUID, Decimal] = {}
    cash = ZERO
    securities: dict[uuid.UUID, Security] = {}
    for h, sec in holdings:
        securities[sec.id] = sec
        if sec.is_cash_equivalent:
            cash += Decimal(h.institution_value or 0)
            continue
        qty[sec.id] += Decimal(h.quantity or 0)
        if h.institution_price is not None:
            flat[sec.id] = Decimal(h.institution_price)
    for t in txs:
        if t.security_id and t.security_id not in securities:
            sec = sess.get(Security, t.security_id)
            if sec is not None:
                securities[sec.id] = sec
    curves: dict[uuid.UUID, dict[date, Decimal]] = {}
    observed: set[uuid.UUID] = set()
    for sid, sec in securities.items():
        if sec.is_cash_equivalent:
            continue
        curve, real = price_curve(sess, sec, start, today)
        if curve:
            curves[sid] = curve
        if real:
            observed.add(sid)
        if sid not in flat and sec.close_price is not None:
            flat[sid] = Decimal(sec.close_price)
    by_day: dict[date, list[InvestmentTransaction]] = defaultdict(list)
    for t in txs:
        by_day[t.date].append(t)

    values: dict[date, Decimal] = {}
    priced = unpriced = ZERO
    d = today
    while d >= start:
        if d <= last_day:
            total = cash
            for sid, q in qty.items():
                if q == 0:
                    continue
                p = curves.get(sid, {}).get(d)
                price = p if p is not None else flat.get(sid, ZERO)
                total += q * price
                if d == last_day:
                    if sid in observed:
                        priced += abs(q * price)
                    else:
                        unpriced += abs(q * price)
            values[d] = total
        for t in by_day.get(d, []):  # undo day d: what it was at the end of the day before
            sec = securities.get(t.security_id) if t.security_id else None
            if t.security_id and t.quantity and not (sec is not None and sec.is_cash_equivalent):
                qty[t.security_id] -= Decimal(t.quantity)
            if t.amount and not _bought_with_new_money(t):
                cash += Decimal(t.amount)
        d -= timedelta(days=1)
    if values and min(values.values()) < 0:
        return {}, None
    share = float(priced / (priced + unpriced)) if priced + unpriced > 0 else None
    return values, share


def account_series(sess: Session, acct: Account, start: date, end: date, today: date) -> AccountSeries:
    out = AccountSeries(acct.id, acct.name)
    snaps = list(sess.execute(select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance, BalanceSnapshot.source)
                              .where(BalanceSnapshot.account_id == acct.id,
                                     BalanceSnapshot.current_balance.is_not(None),
                                     BalanceSnapshot.as_of <= end).order_by(BalanceSnapshot.as_of)))
    txs = list(sess.execute(select(InvestmentTransaction).where(InvestmentTransaction.account_id == acct.id,
                                                                InvestmentTransaction.date >= start)).scalars())
    for t in txs:
        if is_external(t) and t.date <= end:
            out.flows[t.date] = out.flows.get(t.date, ZERO) + flow_of(t)
    # Derived days (an imported statement's window, history.py) value the account; only live ones are tracked.
    out.tracked_since = next((d for d, _, source in snaps if source in LIVE), None)
    first = snaps[0][0] if snaps else None
    if first is not None:
        out.values.update(daily([(d, Decimal(v)) for d, v, _ in snaps], max(start, first), end))
    if first is None or first > start:
        last_day = min(end, (first or today + timedelta(days=1)) - timedelta(days=1))
        rebuilt, share = _rebuild(sess, acct, txs, start, last_day, today)
        if rebuilt:
            out.values.update({d: v for d, v in rebuilt.items() if start <= d <= end})
            out.rebuilt, out.coverage = True, share
    # The series starts when there is money in it (a rebuilt account is empty before its first deposit).
    first = next((d for d in sorted(out.values) if out.values[d] > 0), None)
    out.values = {d: v for d, v in out.values.items() if first is not None and d >= first}
    return out


def chain(values: dict[date, Decimal], flows: dict[date, Decimal]) -> list[dict]:
    """Time-weighted return, chained day by day from the first value."""
    out = []
    level = Decimal(1)
    prev = None
    for d in sorted(values):
        v = values[d]
        f = flows.get(d, ZERO)
        if prev is not None and prev > 0:
            level *= (v - f) / prev
        out.append({"date": d, "value": v, "flows": f, "return": float(level - 1)})
        prev = v
    return out


def investment_accounts(sess: Session, account_id: uuid.UUID | None = None) -> list[Account]:
    """Every account counted as an investment (networth.account_group): connected, or kept
    by hand (its values are its snapshots; with no trades recorded, a change is growth)."""
    from .networth import account_group
    stmt = (select(Account).outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
            .where(Account.is_hidden.is_(False), Account.closed_at.is_(None))
            .where((PlaidItem.id.is_(None)) | (PlaidItem.status != "removed")))
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)
    return [a for a in sess.execute(stmt.order_by(Account.display_order, Account.name)).scalars()
            if account_group(a) == "investments"]


def performance(sess: Session, start: date, end: date, today: date, account_id: uuid.UUID | None = None) -> dict:
    accounts = investment_accounts(sess, account_id)
    per = [account_series(sess, a, start, end, today) for a in accounts]
    values: dict[date, Decimal] = defaultdict(lambda: ZERO)
    flows: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for s in per:
        if not s.values:
            continue
        joined = min(s.values)
        for d, v in s.values.items():
            values[d] += v
        for d, f in s.flows.items():
            if d in s.values and d != joined:
                flows[d] += f
        if joined > min(min(x.values) for x in per if x.values):
            flows[joined] += s.values[joined]  # joined the portfolio that day: not growth
    series = chain(dict(values), dict(flows))
    tracked = [s.tracked_since for s in per if s.tracked_since]
    first_real = min(tracked) if tracked else None
    return {
        "series": series,
        "estimated_before": first_real if series and first_real and series[0]["date"] < first_real else None,
        "accounts": [{"id": str(s.account_id), "name": s.name, "rebuilt": s.rebuilt, "coverage": s.coverage,
                      "tracked_since": s.tracked_since} for s in per],
    }
