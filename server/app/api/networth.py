from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, BalanceSnapshot, PlaidItem
from ._common import money

router = APIRouter()

RANGES = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "all": 36500}


@router.get("/networth/history")
def history(range: str = "6m", _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """One point per day. Each account contributes its latest snapshot on or
    before that day, so a missed snapshot carries forward rather than
    dropping the line to zero. Before an account's first snapshot it counts
    at that first value, so the line doesn't jump on the day it was linked.

    Cash and card accounts reach back past linking through snapshots rebuilt
    from transactions (source="derived", services/history.py); everything
    else is held flat there. `estimated_before` is the first day with a real
    snapshot when the range starts earlier, so the chart can say so."""
    days = RANGES.get(range, 183)
    since = datetime.now(UTC).date() - timedelta(days=days)
    q = (select(BalanceSnapshot.account_id, BalanceSnapshot.as_of, BalanceSnapshot.current_balance,
                Account.is_liability, BalanceSnapshot.source)
         .join(Account, Account.id == BalanceSnapshot.account_id)
         .outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
         .where(Account.is_hidden.is_(False))
         .where((PlaidItem.id.is_(None)) | (PlaidItem.status != "removed"))
         .order_by(BalanceSnapshot.as_of))
    rows = sess.execute(q).all()
    if not rows:
        return {"range": range, "points": [], "estimated_before": None}

    # Seed each account with its last value before `since`, then walk days.
    last: dict[object, tuple[Decimal, bool]] = {}
    first: dict[object, tuple[Decimal, bool]] = {}  # stands in before an account's first snapshot
    by_day: dict[object, list] = {}
    real_since = None
    for aid, d, bal, liab, source in rows:
        first.setdefault(aid, (Decimal(bal or 0), liab))
        if source != "derived" and (real_since is None or d < real_since):
            real_since = d
        if d < since:
            last[aid] = (Decimal(bal or 0), liab)
        else:
            by_day.setdefault(d, []).append((aid, Decimal(bal or 0), liab))
    start = max(since, min(by_day) if by_day else since)
    today = datetime.now(UTC).date()
    points = []
    d = start
    while d <= today:
        for aid, bal, liab in by_day.get(d, []):
            last[aid] = (bal, liab)
        values = [last.get(aid, v) for aid, v in first.items()]
        assets = sum((b for b, L in values if not L), Decimal(0))
        liabs = sum((b for b, L in values if L), Decimal(0))
        points.append({"date": d.isoformat(), "assets": money(assets), "liabilities": money(liabs),
                       "net": money(assets - liabs)})
        d += timedelta(days=1)
    estimated = real_since.isoformat() if real_since and points and points[0]["date"] < real_since.isoformat() else None
    return {"range": range, "points": points, "estimated_before": estimated}
