"""Plaid Link: token creation, OAuth resume, public-token exchange."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_user, dashboard_only
from ..auth.human import Principal
from ..config import settings
from ..db import get_session
from ..jobs.queue import enqueue
from ..jobs.sync_item import enqueue_item_refresh
from ..models import LinkSession, PlaidItem
from ..plaid_client import LINK_KINDS, PlaidError, link_product_plan, plaid
from ..services import plaid_sync
from ._common import ApiError, item_json, parse_uuid

router = APIRouter()


def _new_link_session(sess: Session, user_id, data: dict[str, Any], item: PlaidItem | None = None) -> LinkSession:
    exp = data.get("expiration")
    expires_at = (datetime.fromisoformat(exp.replace("Z", "+00:00")) if exp
                  else datetime.now(UTC) + timedelta(hours=4))
    ls = LinkSession(user_id=user_id, link_token=data["link_token"], expires_at=expires_at,
                     item_id=item.id if item else None, mode="update" if item else "create")
    sess.add(ls)
    sess.flush()
    return ls


class TokenIn(BaseModel):
    item_id: str | None = None
    #: Which Connect button was pressed. Ignored in update mode (item_id set).
    kind: Literal["banking", "investments"] = "banking"


@router.post("/link/token")
def create_token(body: TokenIn | None = None, p: Principal = Depends(dashboard_only),
                 sess: Session = Depends(get_session)):
    body = body or TokenIn()
    item = None
    access_token = None
    if body.item_id:
        item = sess.get(PlaidItem, parse_uuid(body.item_id))
        if item is None or item.status == "removed":
            raise ApiError(404, "not_found", "item not found")
        access_token = plaid_sync.access_token_for(item)
    try:
        data = plaid().link_token_create(user_id=str(p.user_id), access_token=access_token, kind=body.kind)
    except ValueError as e:
        raise ApiError(400, "bad_request", str(e)) from e
    except PlaidError as e:
        raise ApiError(502, "plaid_error", f"{e.error_code}: {e.body.get('error_message')}") from e
    ls = _new_link_session(sess, p.user_id, data, item=item)
    return {"link_token": data["link_token"], "expiration": data.get("expiration"),
            "link_session_id": str(ls.id), "mode": ls.mode, "kind": None if item else body.kind,
            "redirect_uri": settings().plaid_redirect_uri}


@router.get("/link/session")
def latest_session(p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    """The OAuth return page needs the same link token it started with."""
    ls = sess.execute(select(LinkSession).where(LinkSession.user_id == p.user_id,
                                                LinkSession.consumed_at.is_(None),
                                                LinkSession.expires_at > datetime.now(UTC))
                      .order_by(LinkSession.created_at.desc()).limit(1)).scalar_one_or_none()
    if ls is None:
        raise ApiError(404, "not_found", "no active link session")
    return {"link_token": ls.link_token, "link_session_id": str(ls.id), "mode": ls.mode,
            "item_id": str(ls.item_id) if ls.item_id else None}


class ExchangeIn(BaseModel):
    public_token: str
    metadata: dict[str, Any] | None = None
    link_session_id: str | None = None


@router.post("/link/exchange", status_code=201)
def exchange(body: ExchangeIn, p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    try:
        item = plaid_sync.create_item_from_public_token(sess, public_token=body.public_token,
                                                        user_id=p.user_id, metadata=body.metadata)
    except PlaidError as e:
        raise ApiError(502, "plaid_error", f"{e.error_code}: {e.body.get('error_message')}") from e
    if body.link_session_id:
        ls = sess.get(LinkSession, parse_uuid(body.link_session_id))
        if ls is not None and ls.user_id == p.user_id:
            ls.consumed_at = datetime.now(UTC)
    enqueue_item_refresh(sess, item)
    return item_json(item)


@router.post("/link/update-complete")
def update_complete(body: ExchangeIn | None = None, p: Principal = Depends(dashboard_only),
                    sess: Session = Depends(get_session)):
    """After update-mode Link finishes there is no new public token; the
    existing access token is simply valid again. Clear the error and resync."""
    body = body or ExchangeIn(public_token="")
    ls = None
    if body.link_session_id:
        ls = sess.get(LinkSession, parse_uuid(body.link_session_id))
    if ls is None or ls.item_id is None:
        raise ApiError(400, "bad_request", "link_session_id of an update-mode session is required")
    item = sess.get(PlaidItem, ls.item_id)
    if item is None:
        raise ApiError(404, "not_found", "item not found")
    ls.consumed_at = datetime.now(UTC)
    plaid_sync.clear_item_error(item)
    item.status = "active"
    enqueue(sess, "sync_item", {"item_id": str(item.id)})
    return item_json(item)


@router.get("/link/config")
def link_config(_: Principal = Depends(current_user)):
    s = settings()
    kinds = {}
    for k in LINK_KINDS:
        try:
            req, extra = link_product_plan(k, s.plaid_products)
        except ValueError:
            continue
        kinds[k] = {"products": req, "required_if_supported_products": extra}
    return {"redirect_uri": s.plaid_redirect_uri, "webhook_url": s.plaid_webhook_url,
            "products": s.plaid_products, "kinds": kinds, "plaid_env": s.plaid_env}
