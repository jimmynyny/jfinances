"""Investment performance: time-weighted return, for the portfolio and each account.

Value per day, per investment account:
- From its first snapshot on: balance_snapshots (the balance Plaid reports,
  carried over days without one).
- Before that, as far back as investment transactions reach (about two
  years): holdings are rebuilt by undoing every later trade and cash movement
  from today's holdings, and priced at each security's close as traded
  ("tiingo_close:" series). A security without price history keeps today's
  price; `coverage` is the share of the rebuilt value that had real prices.
  A rebuild that goes negative (missing transactions) is dropped.

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
EXTERNAL_CASH = {"deposit", "contribution", "withdrawal"}
EXTERNAL_TRANSFER = {"transfer", "send", "request", "deposit", "withdrawal"}


def is_external(t: InvestmentTransaction) -> bool:
    kind, sub = (t.type or "").lower(), (t.subtype or "").lower()
    return (kind == "cash" and sub in EXTERNAL_CASH) or (kind == "transfer" and sub in EXTERNAL_TRANSFER)


def flow_of(t: InvestmentTransaction) -> Decimal:
    """Money into the account (+) or out (-). Plaid's amount is positive when cash leaves."""
    if t.amount:
        return -Decimal(t.amount)
    if t.quantity and t.price:
        return Decimal(t.quantity) * Decimal(t.price)
    return ZERO


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
    for sid, sec in securities.items():
        if sec.is_cash_equivalent:
            continue
        ticker = (sec.ticker or "").strip()
        if ticker and (sec.type or "").lower() in prices.PRICED_TYPES:
            pts = prices.series_points(sess, f"tiingo_close:{ticker.upper().replace('.', '-')}",
                                       start - timedelta(days=10), today)
            if pts:
                curves[sid] = daily(pts, start, today)
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
                total += q * (p if p is not None else flat.get(sid, ZERO))
                if d == last_day:
                    if p is not None:
                        priced += abs(q * p)
                    else:
                        unpriced += abs(q * flat.get(sid, ZERO))
            values[d] = total
        for t in by_day.get(d, []):  # undo day d: what it was at the end of the day before
            sec = securities.get(t.security_id) if t.security_id else None
            if t.security_id and t.quantity and not (sec is not None and sec.is_cash_equivalent):
                qty[t.security_id] -= Decimal(t.quantity)
            if t.amount:
                cash += Decimal(t.amount)
        d -= timedelta(days=1)
    if values and min(values.values()) < 0:
        return {}, None
    share = float(priced / (priced + unpriced)) if priced + unpriced > 0 else None
    return values, share


def account_series(sess: Session, acct: Account, start: date, end: date, today: date) -> AccountSeries:
    out = AccountSeries(acct.id, acct.name)
    snaps = list(sess.execute(select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance)
                              .where(BalanceSnapshot.account_id == acct.id,
                                     BalanceSnapshot.current_balance.is_not(None),
                                     BalanceSnapshot.as_of <= end).order_by(BalanceSnapshot.as_of)))
    txs = list(sess.execute(select(InvestmentTransaction).where(InvestmentTransaction.account_id == acct.id,
                                                                InvestmentTransaction.date >= start)).scalars())
    for t in txs:
        if is_external(t) and t.date <= end:
            out.flows[t.date] = out.flows.get(t.date, ZERO) + flow_of(t)
    if snaps:
        out.tracked_since = snaps[0][0]
        out.values.update(daily([(d, Decimal(v)) for d, v in snaps], max(start, snaps[0][0]), end))
    if out.tracked_since is None or out.tracked_since > start:
        last_day = min(end, (out.tracked_since or today + timedelta(days=1)) - timedelta(days=1))
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
    stmt = (select(Account).outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
            .where(Account.type == "investment", Account.is_hidden.is_(False), Account.closed_at.is_(None))
            .where((PlaidItem.id.is_(None)) | (PlaidItem.status != "removed")))
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)
    return list(sess.execute(stmt.order_by(Account.display_order, Account.name)).scalars())


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
