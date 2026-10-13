"""Job: one balance_snapshots row per open account per day.

Plaid accounts get `source=plaid` when the nightly sync touched them today,
otherwise their last known balance is carried forward (`source=carry`).
Manual accounts (cars, houses) are always carried forward from their last
manual valuation. This is what the net worth chart reads, so a day without
a snapshot is a gap in the line.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, PlaidItem
from ..services.plaid_sync import write_snapshots
from .queue import handler


@handler("snapshot_balances")
def snapshot_balances(sess: Session, payload: dict) -> None:
    today = datetime.now(UTC).date()
    q = (select(Account).outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
         .where(Account.closed_at.is_(None))
         .where((Account.kind == "manual") | (PlaidItem.status != "removed")))
    accounts = list(sess.execute(q).scalars())
    fresh = [a for a in accounts if a.kind == "plaid" and a.balance_updated_at
             and a.balance_updated_at.date() == today]
    stale = [a for a in accounts if a not in fresh]
    write_snapshots(sess, fresh, source="plaid", as_of=today)
    write_snapshots(sess, stale, source="carry", as_of=today)
