"""Insights: household cash flow and spending, sliced by time, category and merchant.

Every number follows the Transactions summary's rules (services/flows.py):
pending and removed transactions never count, transfers between the
household's own accounts and payments into cards and loans are left out
(they would double count), and hidden accounts are left out as they are
everywhere else. `scope` keeps business accounts (accounts.is_business) and
personal ones apart.

Income is the INCOME category (paychecks, interest, dividends, refunds of
tax...); spending is every other category, net of refunds (a refund is money
in under a spending category and reduces that category). A deposit the bank
filed as a transfer (a marketplace payout, say) only counts once the user
recategorises it as income.

One query loads the filtered rows; the aggregation is plain Python over
them, which keeps each view a small, testable function. A household's two
years of transactions is a few tens of thousands of rows at most.
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, Transaction
from .flows import is_liability_payment_clause, is_transfer_clause

Scope = Literal["personal", "business", "all"]
Grain = Literal["month", "quarter", "year"]

INCOME = "INCOME"
ZERO = Decimal(0)

#: What kind of income a detailed category is; anything else is "other income".
INCOME_KINDS = {
    "INCOME_WAGES": "paychecks",
    "INCOME_DIVIDENDS": "dividends",
    "INCOME_INTEREST_EARNED": "interest",
    "INCOME_RETIREMENT_PENSION": "retirement",
    "INCOME_TAX_REFUND": "tax refunds",
    "INCOME_UNEMPLOYMENT": "unemployment",
}


@dataclass(frozen=True)
class Filters:
    start: date
    end: date
    scope: Scope = "personal"
    account_ids: tuple[uuid.UUID, ...] = ()


@dataclass(frozen=True)
class Row:
    date: date
    #: Plaid sign: positive = money out.
    amount: Decimal
    category: str
    detailed: str | None
    merchant: str
    account_id: uuid.UUID


# --- loading ---------------------------------------------------------------------------------

_NOISE = re.compile(r"^(PPD|CCD|WEB|ID|DES|INDN|CO|ACH|DEP|DEPOSIT|PAYROLL|DIRECT|DIR|POS|DEBIT|CREDIT|"
                    r"PURCHASE|ONLINE|TRANSFER|XFER|REF|TRN|PMT|PAYMENT|RECURRING|CHECKCARD|VISA)$", re.I)


def merchant_key(merchant_name: str | None, name: str) -> str:
    """A stable merchant label: the bank's merchant name when it has one,
    otherwise the description without card numbers, ids and ACH noise
    ("GOOGLE LLC PAYROLL PPD ID: 123" -> "Google Llc")."""
    if merchant_name and merchant_name.strip():
        return merchant_name.strip()
    s = re.sub(r"[0-9#*]+", " ", name or "")
    s = re.sub(r"[^A-Za-z&' ]+", " ", s)
    words = [w for w in s.split() if not _NOISE.match(w)]
    return " ".join(words[:4]).title() or (name or "").strip() or "Unknown"


UNCATEGORIZED = "UNCATEGORIZED"
OTHER_INCOME = "other income"


def effective_category():
    """The category Insights group by: the user's, else the bank's, else UNCATEGORIZED."""
    return func.coalesce(Transaction.user_category, Transaction.category_primary, UNCATEGORIZED)


def detail_key():
    """What a drilled-in category splits by: the detailed category, else the category itself."""
    return func.coalesce(func.nullif(Transaction.category_detailed, ""), effective_category())


def counted_clauses() -> list:
    """The rows Insights count (the module docstring), for a select joined to Account. The
    Transactions list uses the same clauses to show the rows behind a number."""
    return [Transaction.removed_at.is_(None), Transaction.pending.is_(False), Account.is_hidden.is_(False),
            ~is_transfer_clause(), ~is_liability_payment_clause()]


def scope_clause(scope: Scope):
    return None if scope == "all" else Account.is_business.is_(scope == "business")


def income_kind(detailed: str | None) -> str:
    return INCOME_KINDS.get(detailed or "", OTHER_INCOME)


def load_rows(sess: Session, f: Filters) -> list[Row]:
    stmt = (select(Transaction.date, Transaction.amount, effective_category(), Transaction.category_detailed,
                   Transaction.merchant_name, Transaction.name, Transaction.account_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(*counted_clauses(), Transaction.date >= f.start, Transaction.date <= f.end))
    if (scoped := scope_clause(f.scope)) is not None:
        stmt = stmt.where(scoped)
    if f.account_ids:
        stmt = stmt.where(Transaction.account_id.in_(f.account_ids))
    return [Row(d, Decimal(a), c, det, merchant_key(m, n), acct)
            for d, a, c, det, m, n, acct in sess.execute(stmt)]


def first_seen(sess: Session, f: Filters) -> dict[str, date]:
    """Each merchant's first transaction ever (in scope), to tell new merchants apart."""
    whole = Filters(date(1900, 1, 1), f.end, f.scope, f.account_ids)
    out: dict[str, date] = {}
    for r in load_rows(sess, whole):
        if r.merchant not in out or r.date < out[r.merchant]:
            out[r.merchant] = r.date
    return out


# --- periods -----------------------------------------------------------------------------------

def period_start(d: date, grain: Grain) -> date:
    if grain == "year":
        return date(d.year, 1, 1)
    if grain == "quarter":
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    return date(d.year, d.month, 1)


def next_period(d: date, grain: Grain) -> date:
    months = {"month": 1, "quarter": 3, "year": 12}[grain]
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


def periods(start: date, end: date, grain: Grain) -> list[date]:
    out, p = [], period_start(start, grain)
    while p <= end:
        out.append(p)
        p = next_period(p, grain)
    return out


def period_label(p: date, grain: Grain) -> str:
    if grain == "year":
        return str(p.year)
    if grain == "quarter":
        return f"Q{(p.month - 1) // 3 + 1} {p.year}"
    return p.strftime("%b %Y")


def is_income(r: Row) -> bool:
    return r.category == INCOME


# --- cash flow ---------------------------------------------------------------------------------

def rate(net: Decimal, income: Decimal) -> float | None:
    return float(net / income) if income > 0 else None


def cashflow(rows: Iterable[Row], f: Filters, grain: Grain, top: int = 8) -> dict:
    rows = list(rows)
    keys = periods(f.start, f.end, grain)
    inc: dict[date, Decimal] = defaultdict(lambda: ZERO)
    spend: dict[date, Decimal] = defaultdict(lambda: ZERO)
    sources: dict[tuple[str, str], list] = {}
    cats: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        p = period_start(r.date, grain)
        if is_income(r):
            inc[p] -= r.amount
            kind = income_kind(r.detailed)
            src = sources.setdefault((kind, r.merchant), [ZERO, 0])
            src[0] -= r.amount
            src[1] += 1
        else:
            spend[p] += r.amount
            cats[r.category] += r.amount
    out_periods = []
    for p in keys:
        i, s = inc[p], spend[p]
        out_periods.append({"period": p, "label": period_label(p, grain), "income": i, "spending": s,
                            "net": i - s, "savings_rate": rate(i - s, i)})
    total_i, total_s = sum(inc.values(), ZERO), sum(spend.values(), ZERO)
    # Averages count whole periods only, so a half-finished month doesn't drag them down.
    whole = [x for x in out_periods if next_period(x["period"], grain) - timedelta(days=1) <= f.end
             and x["period"] >= period_start(f.start, grain) and x["period"] >= f.start]
    n = len(whole) or 1
    ranked = sorted(sources.items(), key=lambda kv: kv[1][0], reverse=True)
    spending_cats = sorted(((k, v) for k, v in cats.items() if v > 0), key=lambda kv: kv[1], reverse=True)
    head, tail = spending_cats[:top], spending_cats[top:]
    return {
        "periods": out_periods,
        "totals": {"income": total_i, "spending": total_s, "net": total_i - total_s,
                   "savings_rate": rate(total_i - total_s, total_i)},
        "averages": {"income": sum((x["income"] for x in whole), ZERO) / n,
                     "spending": sum((x["spending"] for x in whole), ZERO) / n,
                     "net": sum((x["net"] for x in whole), ZERO) / n, "periods": len(whole)},
        "income_sources": [{"kind": k, "label": label, "amount": amt, "count": c}
                           for (k, label), (amt, c) in ranked],
        "spending_categories": [{"key": k, "amount": v} for k, v in head]
        + ([{"key": "OTHER", "amount": sum((v for _, v in tail), ZERO)}] if tail else []),
    }


# --- spending ----------------------------------------------------------------------------------

def spending(rows: Iterable[Row], f: Filters, grain: Grain, *, category: str | None = None,
             group: Literal["category", "merchant"] = "category", top: int = 7) -> dict:
    """Spending per period, one series per group (top N + "OTHER"). With
    `category`, drills into that category: groups are its detailed categories
    (or merchants)."""
    keys = periods(f.start, f.end, grain)
    rows = [r for r in rows if not is_income(r) and (category is None or r.category == category)]

    def key(r: Row) -> str:
        if group == "merchant":
            return r.merchant
        return (r.detailed or r.category) if category else r.category

    per: dict[str, dict[date, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        k = key(r)
        per[k][period_start(r.date, grain)] += r.amount
        totals[k] += r.amount
    ranked = sorted(totals, key=lambda k: totals[k], reverse=True)
    head, tail = ranked[:top], ranked[top:]
    series = [{"key": k, "total": totals[k], "values": [per[k][p] for p in keys]} for k in head]
    if tail:
        series.append({"key": "OTHER", "total": sum((totals[k] for k in tail), ZERO),
                       "values": [sum((per[k][p] for k in tail), ZERO) for p in keys]})
    return {"periods": [{"period": p, "label": period_label(p, grain)} for p in keys],
            "series": series, "total": sum(totals.values(), ZERO)}


def compare(current: Iterable[Row], previous: Iterable[Row], *, category: str | None = None) -> list[dict]:
    """Spending per category (or detailed category) this period vs the same period a year earlier."""
    def by_key(rows: Iterable[Row]) -> dict[str, Decimal]:
        out: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for r in rows:
            if not is_income(r) and (category is None or r.category == category):
                out[(r.detailed or r.category) if category else r.category] += r.amount
        return out
    now, then = by_key(current), by_key(previous)
    rows = []
    for k in set(now) | set(then):
        a, b = now.get(k, ZERO), then.get(k, ZERO)
        rows.append({"key": k, "current": a, "previous": b, "change": a - b,
                     "pct": float((a - b) / b) if b > 0 else None})
    return sorted(rows, key=lambda x: max(x["current"], x["previous"]), reverse=True)


def merchants(rows: Iterable[Row], f: Filters, seen: dict[str, date], *, category: str | None = None,
              top: int = 25) -> list[dict]:
    """Top merchants by spending: total, visits, average ticket, a monthly trend, and whether the
    first transaction ever with them falls in the range ("new")."""
    months = periods(f.start, f.end, "month")
    agg: dict[str, dict] = {}
    for r in rows:
        if is_income(r) or (category is not None and r.category != category) or r.amount <= 0:
            continue
        m = agg.setdefault(r.merchant, {"total": ZERO, "count": 0, "last": r.date, "cats": defaultdict(int),
                                        "trend": defaultdict(lambda: ZERO)})
        m["total"] += r.amount
        m["count"] += 1
        m["last"] = max(m["last"], r.date)
        m["cats"][r.category] += 1
        m["trend"][period_start(r.date, "month")] += r.amount
    out = []
    for label, m in sorted(agg.items(), key=lambda kv: kv[1]["total"], reverse=True)[:top]:
        first = seen.get(label)
        out.append({"label": label, "total": m["total"], "count": m["count"], "average": m["total"] / m["count"],
                    "category": max(m["cats"], key=m["cats"].get), "last_seen": m["last"], "first_seen": first,
                    "is_new": first is not None and first >= f.start,
                    "trend": [m["trend"][p] for p in months]})
    return out


def patterns(rows: Iterable[Row], f: Filters, *, category: str | None = None) -> dict:
    """When the money goes: spending per weekday and per day of the month,
    with how many of each day the range holds so averages are fair."""
    by_dow: dict[int, Decimal] = defaultdict(lambda: ZERO)
    by_dom: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for r in rows:
        if is_income(r) or (category is not None and r.category != category):
            continue
        by_dow[r.date.weekday()] += r.amount
        by_dom[r.date.day] += r.amount
    days_dow: dict[int, int] = defaultdict(int)
    days_dom: dict[int, int] = defaultdict(int)
    d = f.start
    while d <= f.end:
        days_dow[d.weekday()] += 1
        days_dom[d.day] += 1
        d += timedelta(days=1)
    return {
        "weekdays": [{"weekday": i, "total": by_dow[i],
                      "per_day": by_dow[i] / days_dow[i] if days_dow[i] else ZERO} for i in range(7)],
        "month_days": [{"day": i, "total": by_dom[i],
                        "per_day": by_dom[i] / days_dom[i] if days_dom[i] else ZERO} for i in range(1, 32)],
    }
