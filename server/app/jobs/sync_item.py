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
        knew_products = bool(item.products)
        plaid_sync.refresh_accounts(sess, item)
        if not knew_products and item.products:
            # The link-time /accounts/get failed, so the product refreshes the
            # exchange would have queued were skipped. Queue them now.
            enqueue_product_refreshes(sess, item)
        if item.has_product("transactions"):
            plaid_sync.sync_transactions(sess, item)
        else:
            log.info("item %s has no transactions product; balances only", item.id)
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


def enqueue_item_refresh(sess: Session, item: PlaidItem):
    """Queue every refresh this Item's products allow and return the
    sync_item enqueue result (None when one was already queued).

    sync_item always runs: /accounts/get is free and works for every Item.
    Investments and liabilities are queued only when Plaid initialised them.
    """
    from .queue import enqueue
    queued = enqueue(sess, "sync_item", {"item_id": str(item.id)})
    enqueue_product_refreshes(sess, item)
    return queued


def enqueue_product_refreshes(sess: Session, item: PlaidItem) -> None:
    """Investments and liabilities refreshes, only for products Plaid
    initialised on the Item (calling one it lacks would add it to the bill)."""
    from .queue import enqueue
    if item.has_product("investments"):
        enqueue(sess, "refresh_investments", {"item_id": str(item.id)})
    if item.has_product("liabilities"):
        enqueue(sess, "refresh_liabilities", {"item_id": str(item.id)})
