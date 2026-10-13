"""Job: sync one item's transactions and balances."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PlaidItem
from ..plaid_client import PlaidError
from ..services import plaid_sync
from .queue import handler

log = logging.getLogger(__name__)


def _item(sess: Session, payload: dict) -> PlaidItem | None:
    item = sess.execute(select(PlaidItem).where(PlaidItem.id == payload["item_id"])).scalar_one_or_none()
    if item is None:
        log.warning("job for unknown item %s", payload.get("item_id"))
        return None
    if item.status == "removed":
        return None
    return item


@handler("sync_item")
def sync_item(sess: Session, payload: dict) -> None:
    item = _item(sess, payload)
    if item is None:
        return
    try:
        plaid_sync.refresh_accounts(sess, item)
        plaid_sync.sync_transactions(sess, item)
    except PlaidError as e:
        # Login-required and friends are a state, not a failure to retry.
        sess.commit()
        if item.status in ("login_required", "removed"):
            return
        raise e


@handler("sync_all")
def sync_all(sess: Session, payload: dict) -> None:
    from .queue import enqueue
    items = sess.execute(select(PlaidItem).where(PlaidItem.status.in_(["active", "pending_expiration"]))).scalars()
    for it in items:
        enqueue(sess, "sync_item", {"item_id": str(it.id)})
