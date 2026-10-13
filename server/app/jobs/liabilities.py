from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PlaidItem
from ..plaid_client import PlaidError
from ..services import plaid_sync
from .queue import enqueue, handler
from .sync_item import _item


@handler("refresh_liabilities")
def refresh_liabilities(sess: Session, payload: dict) -> None:
    item = _item(sess, payload)
    if item is None or not item.has_product("liabilities"):
        return
    try:
        plaid_sync.refresh_liabilities(sess, item)
    except PlaidError:
        sess.commit()
        if item.status in ("login_required", "removed"):
            return
        raise


@handler("refresh_liabilities_all")
def refresh_liabilities_all(sess: Session, payload: dict) -> None:
    for it in sess.execute(select(PlaidItem).where(PlaidItem.status == "active")).scalars():
        if it.has_product("liabilities"):
            enqueue(sess, "refresh_liabilities", {"item_id": str(it.id)})
