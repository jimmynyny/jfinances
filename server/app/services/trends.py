"""Per-account balance trends for sparklines (`trend` on account rows).

One query covers every requested account. Each series is daily and gap-free:
missing days carry the previous value forward (manual assets are updated
monthly; Plaid items can miss a day), it starts at the first day with a known
value inside the window, and its last point is today. When the caller knows
the live balance, today's point is that balance, so a sparkline always ends at
the number printed next to it.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BalanceSnapshot

#: Points per sparkline. 90 days reads as "this quarter" and stays tiny on the wire.
TREND_DAYS = 90
#: How far before the window to look for a value to carry in (manual assets
#: are typically updated monthly).
LOOKBACK_DAYS = 45


def fill_daily(points: Iterable[tuple[date, Decimal | None]], start: date, end: date) -> list[Decimal]:
    """Daily series from `start` to `end` inclusive. Values before `start`
    seed the carry; days before the first known value are omitted."""
    by_day: dict[date, Decimal] = {}
    for d, v in points:
        if v is not None:
            by_day[d] = Decimal(v)
    carry: Decimal | None = None
    for d in sorted(k for k in by_day if k < start):
        carry = by_day[d]
    out: list[Decimal] = []
    day = start
    while day <= end:
        if day in by_day:
            carry = by_day[day]
        if carry is not None:
            out.append(carry)
        day += timedelta(days=1)
    return out


def balance_trends(sess: Session, account_ids: Iterable[uuid.UUID], *,
                   current: Mapping[uuid.UUID, Decimal | None] | None = None,
                   days: int = TREND_DAYS, today: date | None = None) -> dict[uuid.UUID, list[Decimal]]:
    ids = list(account_ids)
    if not ids:
        return {}
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=days - 1)
    rows = sess.execute(
        select(BalanceSnapshot.account_id, BalanceSnapshot.as_of, BalanceSnapshot.current_balance)
        .where(BalanceSnapshot.account_id.in_(ids),
               BalanceSnapshot.as_of >= start - timedelta(days=LOOKBACK_DAYS),
               BalanceSnapshot.as_of <= end)).all()
    points: dict[uuid.UUID, list[tuple[date, Decimal | None]]] = defaultdict(list)
    for account_id, as_of, bal in rows:
        points[account_id].append((as_of, bal))
    live = current or {}
    out: dict[uuid.UUID, list[Decimal]] = {}
    for account_id in ids:
        series_points = list(points.get(account_id, []))
        if live.get(account_id) is not None:
            series_points = [p for p in series_points if p[0] != end] + [(end, live[account_id])]
        out[account_id] = fill_daily(series_points, start, end)
    return out
