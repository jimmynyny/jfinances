from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..jobs.queue import enqueue
from ..models import Job, PlaidItem, WebhookEvent
from ._common import item_json, ts

router = APIRouter()


@router.get("/sync/status")
def status(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    items = sess.execute(select(PlaidItem).options(selectinload(PlaidItem.accounts))
                         .where(PlaidItem.status != "removed").order_by(PlaidItem.institution_name)).scalars()
    jobs = sess.execute(select(Job).where(Job.status.in_(["queued", "running", "failed"]))
                        .order_by(Job.created_at.desc()).limit(50)).scalars()
    hooks = sess.execute(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(20)).scalars()
    return {
        "items": [item_json(i) for i in items],
        "jobs": [{"id": str(j.id), "kind": j.kind, "status": j.status, "item_id": j.payload.get("item_id"),
                  "attempts": j.attempts, "run_after": ts(j.run_after), "last_error": j.last_error,
                  "created_at": ts(j.created_at), "finished_at": ts(j.finished_at)} for j in jobs],
        "webhooks": [{"id": str(w.id), "item_id": w.item_id, "type": w.webhook_type, "code": w.webhook_code,
                      "received_at": ts(w.received_at), "processed_at": ts(w.processed_at), "error": w.error}
                     for w in hooks],
    }


@router.post("/sync/all", status_code=202)
def sync_all(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    enqueue(sess, "sync_all", {})
    enqueue(sess, "refresh_investments_all", {})
    enqueue(sess, "refresh_liabilities_all", {})
    return {"queued": True}


@router.post("/sync/snapshot", status_code=202)
def snapshot(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    enqueue(sess, "snapshot_balances", {})
    return {"queued": True}
