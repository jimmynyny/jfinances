"""Net worth and debt insights: by asset class, per home, loan payoff, cards.

- By asset class: every visible account's daily balance (the net worth
  chart's rules: carried over days without a snapshot, held at its first
  value before it), summed per group (services/networth.group_key), one point
  per month end.
- Homes and other property: each real estate (or other securable) asset with
  the loans secured by it (accounts.secured_by_id): value, owed, equity,
  loan-to-value, and their month-end history.
- Loan payoff: a standard amortization of today's balance at the loan's rate,
  ending at its maturity date (or, without one, at the scheduled payment).
  The principal-and-interest payment is computed, so escrow in the bill
  doesn't distort it. Interest per calendar year, payoff date, and what an
  extra monthly payment would save.
- Cards: utilization (balance / limit, today's limit) per card and overall,
  month by month, and interest and fees charged, from transactions.
"""
from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from ..models import SECURABLE_CATEGORIES, Account, BalanceSnapshot, Liability, PlaidItem, Transaction
from .networth import ASSET_GROUPS, GROUPS, AccountRow, group_key

ZERO = Decimal(0)


def _row(a: Account) -> AccountRow:
    return AccountRow(id=str(a.id), name=a.name, kind=a.kind, type=a.type, subtype=a.subtype,
                      manual_category=a.manual_category, is_liability=a.is_liability, is_hidden=a.is_hidden,
                      current_balance=a.current_balance)


def month_ends(start: date, end: date) -> list[date]:
    out = []
    y, m = start.year, start.month
    while True:
        last = date(y, m, calendar.monthrange(y, m)[1])
        out.append(min(last, end))
        if last >= end:
            return out
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def visible_accounts(sess: Session) -> list[Account]:
    return list(sess.execute(select(Account).outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
                             .where(Account.is_hidden.is_(False))
                             .where((PlaidItem.id.is_(None)) | (PlaidItem.status != "removed"))).scalars())


def balances_on(sess: Session, accounts: list[Account], days: list[date]) -> dict[uuid.UUID, dict[date, Decimal]]:
    """Each account's balance on each day: its latest snapshot on or before the
    day, or its first snapshot for days before it (as the net worth chart)."""
    ids = [a.id for a in accounts]
    rows = sess.execute(select(BalanceSnapshot.account_id, BalanceSnapshot.as_of, BalanceSnapshot.current_balance)
                        .where(BalanceSnapshot.account_id.in_(ids), BalanceSnapshot.current_balance.is_not(None),
                               BalanceSnapshot.as_of <= max(days))
                        .order_by(BalanceSnapshot.account_id, BalanceSnapshot.as_of)).all()
    series: dict[uuid.UUID, list[tuple[date, Decimal]]] = defaultdict(list)
    for aid, d, v in rows:
        series[aid].append((d, Decimal(v)))
    out: dict[uuid.UUID, dict[date, Decimal]] = {}
    for a in accounts:
        pts = series.get(a.id)
        if not pts:
            if a.current_balance is not None:
                out[a.id] = {d: Decimal(a.current_balance) for d in days}
            continue
        vals, i, last = {}, 0, pts[0][1]
        for d in sorted(days):
            while i < len(pts) and pts[i][0] <= d:
                last = pts[i][1]
                i += 1
            vals[d] = last
        out[a.id] = vals
    return out


def by_class(sess: Session, start: date, end: date) -> dict:
    accounts = visible_accounts(sess)
    days = month_ends(start, end)
    bal = balances_on(sess, accounts, days)
    keys = [k for k, _ in GROUPS]
    points = []
    for d in days:
        groups: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for a in accounts:
            if a.id in bal:
                groups[group_key(_row(a))] += bal[a.id][d]
        assets = sum((v for k, v in groups.items() if k in ASSET_GROUPS), ZERO)
        debts = sum((v for k, v in groups.items() if k not in ASSET_GROUPS), ZERO)
        points.append({"date": d, **{k: groups.get(k, ZERO) for k in keys}, "assets": assets, "liabilities": debts,
                       "net": assets - debts})
    used = [k for k in keys if any(p[k] != 0 for p in points)]
    return {"groups": [{"key": k, "label": dict(GROUPS)[k], "liability": k not in ASSET_GROUPS} for k in used],
            "points": points}


def homes(sess: Session, today: date, months: int = 24) -> list[dict]:
    accounts = visible_accounts(sess)
    loans_by_asset: dict[uuid.UUID, list[Account]] = defaultdict(list)
    for a in accounts:
        if a.secured_by_id:
            loans_by_asset[a.secured_by_id].append(a)
    props = [a for a in accounts if a.kind == "manual" and a.manual_category in SECURABLE_CATEGORIES
             and (a.manual_category == "real_estate" or loans_by_asset.get(a.id))]
    if not props:
        return []
    start = date(today.year - months // 12, today.month, 1)
    days = month_ends(start, today)
    involved = props + [loan for p in props for loan in loans_by_asset.get(p.id, [])]
    bal = balances_on(sess, involved, days)
    rates = {L.account_id: L.interest_rate_pct for L in sess.execute(
        select(Liability).where(Liability.account_id.in_([a.id for a in involved]))).scalars()}
    out = []
    for p in sorted(props, key=lambda a: -(a.current_balance or 0)):
        loans = loans_by_asset.get(p.id, [])
        value = Decimal(p.current_balance or 0)
        owed = sum((Decimal(x.current_balance or 0) for x in loans), ZERO)
        history = []
        for d in days:
            v = bal.get(p.id, {}).get(d, value)
            o = sum((bal.get(x.id, {}).get(d, Decimal(x.current_balance or 0)) for x in loans), ZERO)
            history.append({"date": d, "value": v, "owed": o, "equity": v - o})
        out.append({"id": str(p.id), "name": p.name, "category": p.manual_category, "value": value, "owed": owed,
                    "equity": value - owed, "ltv": float(owed / value) if value > 0 else None,
                    "loans": [{"id": str(x.id), "name": x.name, "mask": x.mask,
                               "balance": Decimal(x.current_balance or 0),
                               "rate": float(rates[x.id]) if rates.get(x.id) is not None else None} for x in loans],
                    "history": history})
    return out


def _months_between(a: date, b: date) -> int:
    return max(0, (b.year - a.year) * 12 + (b.month - a.month))


def amortize(balance: Decimal, apr_pct: Decimal, months: int, start: date, extra: Decimal = ZERO,
             payment: Decimal | None = None) -> dict:
    """Month-by-month payoff. `payment` is principal and interest; computed
    from `months` when not given. Returns payoff month, interest remaining,
    and interest/principal per calendar year."""
    r = apr_pct / Decimal(1200)
    if payment is None:
        if months <= 0:
            payment = balance
        elif r == 0:
            payment = balance / months
        else:
            payment = balance * r / (1 - (1 + r) ** -months)
    payment = payment.quantize(Decimal("0.01"))
    per_year: dict[int, dict[str, Decimal]] = defaultdict(lambda: {"interest": ZERO, "principal": ZERO})
    b, total_interest, n = balance, ZERO, 0
    y, m = start.year, start.month
    while b > 0 and n < 600:
        interest = (b * r).quantize(Decimal("0.01"))
        principal = min(b, payment + extra - interest)
        if principal <= 0:
            return {"payment": payment, "payoff": None, "months": None, "interest": None, "per_year": []}
        if months and n + 1 >= months:  # the last scheduled payment settles what rounding left over
            principal = b
        b -= principal
        total_interest += interest
        per_year[y]["interest"] += interest
        per_year[y]["principal"] += principal
        n += 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    payoff = date(y, m, 1) - timedelta(days=1)
    return {"payment": payment, "payoff": payoff, "months": n, "interest": total_interest,
            "per_year": [{"year": yr, **v} for yr, v in sorted(per_year.items())]}


def loans_payoff(sess: Session, today: date, extra: Decimal = ZERO) -> list[dict]:
    """Each loan's payoff from today's balance, on the lender's terms with the
    gaps filled from what the person entered (services/terms)."""
    from . import terms
    loans = [a for a in visible_accounts(sess)
             if a.is_liability and a.type != "credit" and (a.current_balance or 0) > 0]
    liabs, entered = terms.load(sess, loans)
    out = []
    for a in loans:
        L, T = liabs.get(a.id), entered.get(a.id)
        kind = terms.kind_of(a, L)
        balance = Decimal(a.current_balance or 0)
        loan = terms.loan_terms(a, L, kind, terms.merge(terms.bank_values(a, L, kind), T, kind), today)
        if loan.rate is None:
            out.append({"id": str(a.id), "name": a.name, "balance": balance, "rate": None, "schedule": None,
                        "note": "no rate reported for this loan: add it in the account's details"})
            continue
        apr = Decimal(loan.rate)
        base = terms.payoff(balance, loan, today)
        if base is None:
            out.append({"id": str(a.id), "name": a.name, "balance": balance, "rate": float(apr), "schedule": None,
                        "note": "no maturity date or payment: add them in the account's details"})
            continue
        what_if = None
        if extra > 0 and base["payoff"]:
            alt = amortize(balance, apr, 0, date(today.year, today.month, 1), extra=extra, payment=base["payment"])
            if alt["payoff"]:
                what_if = {"extra": extra, "payoff": alt["payoff"], "months": alt["months"],
                           "interest": alt["interest"], "months_saved": base["months"] - alt["months"],
                           "interest_saved": base["interest"] - alt["interest"]}
        raw = (L.raw if L is not None else None) or {}
        ytd = raw.get("ytd_interest_paid")
        scheduled = (L.next_payment_amount or L.minimum_payment) if L is not None else None
        out.append({"id": str(a.id), "name": a.name, "kind": L.kind if L is not None else kind, "balance": balance,
                    "rate": float(apr), "rate_source": loan.sources.get("interest_rate_pct"),
                    "scheduled_payment": scheduled or loan.total or loan.payment, "maturity_date": loan.maturity,
                    "ytd_interest": Decimal(str(ytd)) if ytd is not None else None,
                    "schedule": base, "what_if": what_if})
    return sorted(out, key=lambda x: -x["balance"])


FEE_PREFIX = "BANK_FEES_"
INTEREST_DETAILED = "BANK_FEES_INTEREST_CHARGE"


def cards(sess: Session, start: date, end: date) -> dict:
    from . import terms
    accounts = [a for a in visible_accounts(sess) if a.type == "credit"]
    days = month_ends(start, end)
    bal = balances_on(sess, accounts, days)
    _, entered = terms.load(sess, accounts)
    per_card, total_bal, total_limit = [], defaultdict(lambda: ZERO), ZERO
    for a in accounts:
        limit = terms.credit_limit(a, entered.get(a.id)) or ZERO  # the bank's, else the one entered
        hist = []
        for d in days:
            b = bal.get(a.id, {}).get(d, ZERO)
            hist.append({"date": d, "balance": b, "utilization": float(b / limit) if limit > 0 else None})
            if limit > 0:
                total_bal[d] += b
        total_limit += limit
        b_now = Decimal(a.current_balance or 0)
        per_card.append({"id": str(a.id), "name": a.name, "mask": a.mask, "limit": limit or None, "balance": b_now,
                         "utilization": float(b_now / limit) if limit > 0 else None, "history": hist})
    overall = [{"date": d, "utilization": float(total_bal[d] / total_limit) if total_limit > 0 else None} for d in days]
    detailed = func.coalesce(Transaction.category_detailed, "")
    month = func.date_trunc(literal_column("'month'"), Transaction.date).label("month")  # inlined: one GROUP BY key
    rows = sess.execute(select(month, detailed, func.sum(Transaction.amount))
                        .where(Transaction.removed_at.is_(None), Transaction.pending.is_(False),
                               Transaction.date >= start, Transaction.date <= end, detailed.like(f"{FEE_PREFIX}%"))
                        .group_by(month, detailed)).all()
    months: dict[date, dict[str, Decimal]] = defaultdict(lambda: {"interest": ZERO, "fees": ZERO})
    for m, det, amt in rows:
        key = m.date() if hasattr(m, "date") else m
        months[key]["interest" if det == INTEREST_DETAILED else "fees"] += Decimal(amt or 0)
    charges = [{"month": m, **v} for m, v in sorted(months.items())]
    return {"cards": sorted(per_card, key=lambda c: -(c["utilization"] or 0)), "overall": overall,
            "charges": charges, "totals": {"interest": sum((c["interest"] for c in charges), ZERO),
                                           "fees": sum((c["fees"] for c in charges), ZERO)}}
