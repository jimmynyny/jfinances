"""Linked phones (api_tokens), listed and revoked from the dashboard only.

Tokens are minted by the link flow (api/mobile.py), never by hand.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import tokens as tok
from ..auth.deps import dashboard_only
from ..auth.human import Principal
from ..db import get_session
from ..models import ApiToken
from ._common import ApiError, parse_uuid, ts

router = APIRouter()


@router.get("/tokens")
def list_tokens(p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    rows = sess.execute(select(ApiToken).where(ApiToken.user_id == p.user_id)
                        .order_by(ApiToken.created_at.desc())).scalars()
    return {"tokens": [{"id": str(t.id), "name": t.name, "created_at": ts(t.created_at),
                        "last_used_at": ts(t.last_used_at), "revoked_at": ts(t.revoked_at)} for t in rows]}


@router.delete("/tokens/{token_id}", status_code=204)
def revoke(token_id: str, p: Principal = Depends(dashboard_only), sess: Session = Depends(get_session)):
    if not tok.revoke_token(sess, token_id=parse_uuid(token_id), user_id=p.user_id):
        raise ApiError(404, "not_found", "token not found")
    return None
