"""Alerts: findings in recent transactions worth a look, computed on demand.

- price: a subscription's price changed within the window (recurring_streams);
- duplicate: one merchant charged one amount twice within two days on the
  same account: a double charge, or a legitimate repeat; the user decides;
- large: a charge far above what this merchant usually costs (2.5x its
  median over the previous year, at least $50), or, for a merchant with
  little history, far above its category (5x, at least $250).

Each alert has a stable key; a dismissed key (dismissed_alerts) is never
shown again. Read-only apart from dismissals.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DismissedAlert, RecurringStream
from .recurring import Charge, load_charges

DUP_MIN = Decimal("15")
LARGE_MIN = Decimal("50")
CATEGORY_LARGE_MIN = Decimal("250")


def _price(sess: Session, since: date) -> list[dict]:
    rows = sess.execute(select(RecurringStream).where(RecurringStream.status != "dismissed",
                                                      RecurringStream.price_changed_on >= since,
                                                      RecurringStream.previous_amount.is_not(None))).scalars()
    return [{"key": f"price:{r.id}:{r.price_changed_on.isoformat()}", "kind": "price", "date": r.price_changed_on,
             "merchant": r.name or r.merchant, "amount": r.last_amount, "previous": r.previous_amount,
             "stream_id": str(r.id), "transaction_ids": []} for r in rows]


def _duplicates(recent: list[Charge]) -> list[dict]:
    by_key: dict[tuple, list[Charge]] = defaultdict(list)
    for c in recent:
        if c.amount >= DUP_MIN:
            by_key[(c.account_id, c.merchant, c.amount)].append(c)
    out = []
    for group in by_key.values():
        group.sort(key=lambda c: c.date)
        for a, b in zip(group, group[1:], strict=False):
            if (b.date - a.date).days <= 2:
                ids = sorted([str(a.id), str(b.id)])
                out.append({"key": f"dup:{ids[0]}:{ids[1]}", "kind": "duplicate", "date": b.date,
                            "merchant": b.merchant, "amount": b.amount, "transaction_ids": ids})
    return out


def _large(recent: list[Charge], history: list[Charge]) -> list[dict]:
    by_merchant: dict[str, list[Charge]] = defaultdict(list)
    by_category: dict[str | None, list[Charge]] = defaultdict(list)
    for c in history:
        by_merchant[c.merchant].append(c)
        by_category[c.category].append(c)
    out = []
    for c in recent:
        if c.amount < LARGE_MIN:
            continue
        year_before = c.date - timedelta(days=365)
        past = [h.amount for h in by_merchant[c.merchant] if year_before <= h.date < c.date]
        if len(past) >= 3:
            usual = statistics.median(past)
            if c.amount > usual * Decimal("2.5"):
                out.append({"key": f"large:{c.id}", "kind": "large", "date": c.date, "merchant": c.merchant,
                            "amount": c.amount, "usual": usual, "basis": "merchant", "transaction_ids": [str(c.id)]})
            continue
        peers = [h.amount for h in by_category[c.category] if year_before <= h.date < c.date and h.id != c.id]
        if len(peers) >= 10 and c.amount >= CATEGORY_LARGE_MIN:
            usual = statistics.median(peers)
            if c.amount > usual * 5:
                out.append({"key": f"large:{c.id}", "kind": "large", "date": c.date, "merchant": c.merchant,
                            "amount": c.amount, "usual": usual, "basis": "category", "category": c.category,
                            "transaction_ids": [str(c.id)]})
    return out


def find_alerts(sess: Session, today: date, days: int = 60) -> list[dict]:
    since = today - timedelta(days=days)
    charges = load_charges(sess, today)
    recent = [c for c in charges if c.date >= since]
    alerts = _price(sess, since) + _duplicates(recent) + _large(recent, charges)
    dismissed = set(sess.execute(select(DismissedAlert.key)).scalars())
    return sorted((a for a in alerts if a["key"] not in dismissed), key=lambda a: a["date"], reverse=True)
