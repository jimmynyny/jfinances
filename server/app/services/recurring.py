"""Subscriptions and bills: charges that repeat on a schedule, found in transactions.

Never Plaid's paid Recurring Transactions product (docs/30 "Cost model"): this
reads the transactions already synced. A merchant's charges (posted money
out; not transfers, not card or loan payments) become recurring streams:

1. First the merchant's whole series is tried as one stream, which keeps a
   price change and a bill whose amount moves (electricity) together.
2. If that has no steady rhythm, its charges are split by amount (several
   plans at one merchant, e.g. two Apple subscriptions) and each part is
   tried on its own.
3. A series is recurring when most of its gaps (two thirds) match one
   cadence, weekly to annual, within that cadence's tolerance, and it has
   enough charges (three up to monthly, two beyond). Amounts must be steady
   (within 5% of the median), except monthly-or-longer bills in categories
   that vary by nature (utilities, loans, services, medical). In shopping
   categories (groceries, restaurants, stores, gas, travel) only an exact
   repeat price counts, on a tight rhythm: a weekly grocery run is not a
   subscription, Amazon Prime is.
4. The next charge is the last plus the cadence (same day of the month for
   monthly and longer). A stream overdue by more than its tolerance has
   lapsed, most likely cancelled.

`sync_streams` keeps recurring_streams in step. A found stream updates the
row for the same merchant whose amount is close (same cadence preferred);
otherwise it is added as "detected". A "detected" row that detection no
longer finds is removed; confirmed and dismissed rows (the user's verdicts)
and names are never changed by detection.
"""
from __future__ import annotations

import calendar
import statistics
import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, RecurringStream, Transaction
from .flows import is_liability_payment_clause, is_transfer_clause
from .insights import merchant_key


@dataclass(frozen=True)
class Cadence:
    name: str
    days: float
    tolerance: int
    #: Calendar step in months for monthly and longer (0: step in days).
    months: int = 0
    min_charges: int = 3


CADENCES = (
    Cadence("weekly", 7, 2),
    Cadence("biweekly", 14, 3),
    Cadence("monthly", 30.44, 5, months=1),
    Cadence("quarterly", 91.31, 12, months=3, min_charges=2),
    Cadence("semiannual", 182.62, 18, months=6, min_charges=2),
    Cadence("annual", 365.25, 25, months=12, min_charges=2),
)
BY_NAME = {c.name: c for c in CADENCES}
#: Categories whose bills move from one charge to the next.
VARIABLE_OK = {"RENT_AND_UTILITIES", "LOAN_PAYMENTS", "GENERAL_SERVICES", "MEDICAL", "GOVERNMENT_AND_NON_PROFIT"}
#: Where repeat charges are mostly shopping (a weekly grocery run, a monthly lunch spot): there only an
#: exact repeat price (or a clean step between exact prices), on a tight rhythm, counts.
SHOPPING = {"FOOD_AND_DRINK", "GENERAL_MERCHANDISE", "TRANSPORTATION", "TRAVEL", "HOME_IMPROVEMENT", "PERSONAL_CARE"}
LOOKBACK_DAYS = 800
DAYS_PER_MONTH = Decimal("30.44")


@dataclass(frozen=True)
class Charge:
    id: uuid.UUID
    date: date
    amount: Decimal
    merchant: str
    category: str | None
    account_id: uuid.UUID


@dataclass
class Found:
    merchant: str
    cadence: Cadence
    interval_days: int
    charges: list[Charge]
    amount: Decimal
    previous_amount: Decimal | None
    price_changed_on: date | None
    next_date: date

    @property
    def last(self) -> Charge:
        return self.charges[-1]


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def next_after(d: date, c: Cadence) -> date:
    return add_months(d, c.months) if c.months else d + timedelta(days=round(c.days))


def is_lapsed(next_date: date, cadence: str, today: date) -> bool:
    return today > next_date + timedelta(days=BY_NAME[cadence].tolerance)


def is_stale(last_date: date, cadence: str, today: date) -> bool:
    """Two of its own periods without a charge (a monthly one quiet for two months):
    it isn't recurring any more, so it isn't listed or asked about."""
    return (today - last_date).days >= 2 * BY_NAME[cadence].days


def monthly_cost(amount: Decimal, cadence: str) -> Decimal:
    return amount * DAYS_PER_MONTH / Decimal(str(BY_NAME[cadence].days))


def steady(amounts: list[Decimal], within: Decimal = Decimal("0.05")) -> bool:
    med = statistics.median(amounts)
    return med > 0 and (max(amounts) - min(amounts)) <= med * within * 2


def exact(amounts: list[Decimal]) -> bool:
    med = statistics.median(amounts)
    return med > 0 and (max(amounts) - min(amounts)) <= max(Decimal("0.10"), med * Decimal("0.01"))


def _cadence_of(gaps: list[int]) -> tuple[Cadence, int] | None:
    """The cadence most gaps match, and how many do."""
    best = None
    for c in CADENCES:
        hits = sum(1 for g in gaps if abs(g - c.days) <= c.tolerance)
        if best is None or hits > best[1]:
            best = (c, hits)
    return best if best and best[1] > 0 else None


def _price_change(charges: list[Charge]) -> tuple[Decimal | None, date | None]:
    """The latest step in a steady price: the old price and the date the new one started."""
    amounts = [c.amount for c in charges]
    for i in range(len(amounts) - 1, 0, -1):
        a, b = amounts[i - 1], amounts[i]
        if abs(b - a) > max(Decimal("0.50"), a * Decimal("0.02")):
            before = amounts[max(0, i - 3):i]
            after = amounts[i:]
            if len(before) >= 2 and steady(before, Decimal("0.02")) and steady(after, Decimal("0.02")):
                return a, charges[i].date
            return None, None
    return None, None


def evaluate(charges: list[Charge]) -> Found | None:
    """A recurring stream, if this series has one."""
    series = sorted(charges, key=lambda c: c.date)
    # Two charges within three days are one occurrence for rhythm's sake (a double charge is an alert).
    occurrences: list[Charge] = []
    for c in series:
        if occurrences and (c.date - occurrences[-1].date).days <= 3:
            continue
        occurrences.append(c)
    if len(occurrences) < 2:
        return None
    gaps = [(b.date - a.date).days for a, b in zip(occurrences, occurrences[1:], strict=False)]
    match = _cadence_of(gaps)
    if match is None:
        return None
    cadence, hits = match
    if len(occurrences) < cadence.min_charges or hits < max(1, round(len(gaps) * 2 / 3)):
        return None
    # A clean step in price (old price steady, new price steady) still counts as steady:
    # judge, and quote, the amounts since the step.
    previous, changed_on = _price_change(occurrences)
    recent = [c.amount for c in occurrences if changed_on is None or c.date >= changed_on][-3:]
    category = occurrences[-1].category
    if category in SHOPPING:
        # Exact repeats only: the same price throughout, or a clean step between two exact runs.
        before = [c.amount for c in occurrences if changed_on is not None and c.date < changed_on][-3:]
        stepped = len(before) >= 2 and exact(before) and exact(recent)
        if hits < round(len(gaps) * 0.8) or not (exact([c.amount for c in occurrences][-3:]) or stepped):
            return None
    elif not steady(recent) and not (cadence.months >= 1 and category in VARIABLE_OK):
        return None
    matched = [g for g in gaps if abs(g - cadence.days) <= cadence.tolerance]
    return Found(
        merchant=occurrences[-1].merchant, cadence=cadence, interval_days=round(statistics.median(matched)),
        charges=occurrences, amount=statistics.median(recent), previous_amount=previous,
        price_changed_on=changed_on, next_date=next_after(occurrences[-1].date, cadence),
    )


def _amount_groups(charges: list[Charge]) -> list[list[Charge]]:
    """Split by amount: sorted amounts break where the next is more than 8% (or $1) higher."""
    groups: list[list[Charge]] = []
    for c in sorted(charges, key=lambda c: c.amount):
        if groups and c.amount - groups[-1][-1].amount <= max(Decimal("1.00"), groups[-1][-1].amount * Decimal("0.08")):
            groups[-1].append(c)
        else:
            groups.append([c])
    return groups


def detect(charges: Iterable[Charge]) -> list[Found]:
    by_merchant: dict[str, list[Charge]] = defaultdict(list)
    for c in charges:
        by_merchant[c.merchant].append(c)
    found: list[Found] = []
    for group in by_merchant.values():
        if len(group) < 2:
            continue
        whole = evaluate(group)
        if whole is not None:
            found.append(whole)
            continue
        found.extend(f for part in _amount_groups(group) if (f := evaluate(part)) is not None)
    return found


def load_charges(sess: Session, today: date) -> list[Charge]:
    cat = func.coalesce(Transaction.user_category, Transaction.category_primary)
    stmt = (select(Transaction.id, Transaction.date, Transaction.amount, cat, Transaction.merchant_name,
                   Transaction.name, Transaction.account_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.removed_at.is_(None), Transaction.pending.is_(False), Transaction.amount > 0,
                   ~is_transfer_clause(), ~is_liability_payment_clause(),
                   Transaction.date >= today - timedelta(days=LOOKBACK_DAYS)))
    return [Charge(i, d, Decimal(a), merchant_key(m, n), c, acct) for i, d, a, c, m, n, acct in sess.execute(stmt)]


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= max(Decimal("2.00"), abs(b) * Decimal("0.25"))


def sync_streams(sess: Session, today: date | None = None) -> int:
    """Run detection and keep recurring_streams in step. Returns how many streams were found."""
    today = today or datetime.now(UTC).date()
    found = detect(load_charges(sess, today))
    rows = list(sess.execute(select(RecurringStream)).scalars())
    taken: set[int] = set()
    now = datetime.now(UTC)
    for f in found:
        candidates = [r for r in rows if id(r) not in taken and r.merchant == f.merchant
                      and (_close(f.last.amount, r.last_amount) or _close(f.amount, r.amount))]
        row = min(candidates, key=lambda r: (r.cadence != f.cadence.name, abs(r.last_amount - f.last.amount)),
                  default=None)
        if row is None:
            row = RecurringStream(merchant=f.merchant, status="detected")
            sess.add(row)
            rows.append(row)
        taken.add(id(row))
        row.cadence = f.cadence.name
        row.interval_days = f.interval_days
        row.amount = f.amount
        row.last_amount = f.last.amount
        row.previous_amount = f.previous_amount
        row.price_changed_on = f.price_changed_on
        row.first_date = f.charges[0].date
        row.last_date = f.last.date
        row.next_date = f.next_date
        row.charge_count = len(f.charges)
        row.category = f.last.category
        row.account_id = f.last.account_id
        row.seen_at = now
    # A suggestion detection no longer makes goes away; a verdict the user gave stays.
    for r in rows:
        if id(r) not in taken and r.status == "detected":
            sess.delete(r)
    sess.flush()
    return len(found)
