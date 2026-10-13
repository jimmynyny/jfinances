from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user, dashboard_only
from ..auth.human import Principal
from ..db import get_session
from ..jobs.sync_item import enqueue_item_refresh
from ..models import PlaidItem
from ..plaid_client import PlaidError, plaid
from ..services import plaid_sync
from ._common import ApiError, item_json, parse_uuid

router = APIRouter()


def _get(sess: Session, item_id: str) -> PlaidItem:
    it = sess.execute(select(PlaidItem).options(selectinload(PlaidItem.accounts))
                      .where(PlaidItem.id == parse_uuid(item_id))).scalar_one_or_none()
    if it is None:
        raise ApiError(404, "not_found", "item not found")
    return it


@router.get("/items")
def list_items(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    rows = sess.execute(select(PlaidItem).options(selectinload(PlaidItem.accounts))
                        .order_by(PlaidItem.created_at)).scalars()
    return {"items": [item_json(it) for it in rows]}


@router.post("/items/{item_id}/sync", status_code=202)
def sync(item_id: str, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    it = _get(sess, item_id)
    if it.status == "removed":
        raise ApiError(409, "conflict", "item was unlinked")
    queued = enqueue_item_refresh(sess, it)
    return {"queued": queued is not None, "item": item_json(it)}


@router.post("/items/{item_id}/relink")
def relink(item_id: str, p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    """Link token in update mode, with account selection: re-auth after
    ITEM_LOGIN_REQUIRED or expiring consent, and "Add accounts" on a healthy
    connection. Same Item, same access token, so nothing new is billed."""
    from .link import _new_link_session
    it = _get(sess, item_id)
    if it.status == "removed":
        raise ApiError(409, "conflict", "item was unlinked; link it again instead")
    try:
        data = plaid().link_token_create(user_id=str(p.user_id), access_token=plaid_sync.access_token_for(it))
    except PlaidError as e:
        raise ApiError(502, "plaid_error", f"{e.error_code}: {e.body.get('error_message')}") from e
    ls = _new_link_session(sess, p.user_id, data, item=it)
    return {"link_token": data["link_token"], "expiration": data.get("expiration"),
            "link_session_id": str(ls.id), "mode": "update"}


@router.delete("/items/{item_id}")
def remove(item_id: str, _: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    it = _get(sess, item_id)
    if it.status == "removed":
        return item_json(it)
    try:
        plaid_sync.remove_item(sess, it)
    except PlaidError as e:
        raise ApiError(502, "plaid_error", f"{e.error_code}: {e.body.get('error_message')}") from e
    return item_json(it)
