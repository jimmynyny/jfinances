"""Fixed-rate loan arithmetic: any three of principal, rate, term and payment
give the fourth, and with a start date the balance a loan should have today.

Payments are monthly and cover principal and interest only (a mortgage's
escrow rides on top). Rates are annual percentages (6.125 for 6.125%). Money
in and out is Decimal, rounded to the cent; the solving is done in floats,
which is plenty for cents on loans up to the hundreds of millions.
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

CENT = Decimal("0.01")
MAX_MONTHS = 600


def _q(x: float) -> Decimal:
    return Decimal(str(round(x, 2))).quantize(CENT)


def _i(apr_pct: Decimal | float) -> float:
    return float(apr_pct) / 1200


def payment(principal: Decimal, apr_pct: Decimal, months: int) -> Decimal | None:
    """The monthly payment that repays `principal` in `months`."""
    p, i, n = float(principal), _i(apr_pct), int(months)
    if p <= 0 or n <= 0:
        return None
    return _q(p / n if i == 0 else p * i / (1 - (1 + i) ** -n))


def months_to_repay(principal: Decimal, apr_pct: Decimal, pmt: Decimal) -> int | None:
    """How many payments of `pmt` repay `principal`; None when a payment
    doesn't even cover a month's interest (or it would take over 50 years)."""
    p, i, a = float(principal), _i(apr_pct), float(pmt)
    if p <= 0:
        return 0
    if a <= 0:
        return None
    if i == 0:
        n = math.ceil(p / a - 1e-9)
    elif a <= p * i:
        return None
    else:
        n = math.ceil(-math.log(1 - p * i / a) / math.log(1 + i) - 1e-9)
    return n if n <= MAX_MONTHS else None


def principal_for(apr_pct: Decimal, months: int, pmt: Decimal) -> Decimal | None:
    """The amount `months` payments of `pmt` repay at `apr_pct`."""
    i, n, a = _i(apr_pct), int(months), float(pmt)
    if n <= 0 or a <= 0:
        return None
    return _q(a * n if i == 0 else a * (1 - (1 + i) ** -n) / i)


def balance_after(principal: Decimal, apr_pct: Decimal, pmt: Decimal, k: int) -> Decimal:
    """What is still owed after `k` payments."""
    p, i, a = float(principal), _i(apr_pct), float(pmt)
    if k <= 0:
        return _q(p)
    b = p - a * k if i == 0 else p * (1 + i) ** k - a * ((1 + i) ** k - 1) / i
    return _q(max(0.0, b))


def solve_rate(principal: Decimal, months: int, pmt: Decimal) -> Decimal | None:
    """The annual rate at which `months` payments of `pmt` repay `principal`,
    to three decimals; None when no rate between 0% and 40% does."""
    p, n, a = float(principal), int(months), float(pmt)
    if p <= 0 or n <= 0 or a <= 0 or a * n < p - 0.005:
        return None
    if a * n - p < 0.01:
        return Decimal("0.000")

    def pay(i: float) -> float:
        return p * i / (1 - (1 + i) ** -n)

    lo, hi = 1e-12, 40 / 1200
    if pay(hi) < a:
        return None
    for _ in range(200):  # payment rises with the rate: bisect
        mid = (lo + hi) / 2
        if pay(mid) < a:
            lo = mid
        else:
            hi = mid
    return Decimal(str(round((lo + hi) / 2 * 1200, 3))).quantize(Decimal("0.001"))


def months_between(start: date, end: date) -> int:
    """Whole months from `start` to `end` (a loan opened Jun 15 has made its
    fourth monthly payment by Oct 15)."""
    n = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        n -= 1
    return max(0, n)


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    last = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    return date(year, month, min(d.day, last))


def term_months(loan_term: str | None) -> int | None:
    """A lender's term text ("30 year", "360 months", "15 yr", "72 mo") in months."""
    if not loan_term:
        return None
    text = loan_term.strip().lower()
    num = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    if not num:
        return None
    try:
        value = float(num)
    except ValueError:
        return None
    if "month" in text or text.endswith("mo") or " mo" in text:
        return round(value) or None
    if "year" in text or "yr" in text or text.endswith("y"):
        return round(value * 12) or None
    return None
