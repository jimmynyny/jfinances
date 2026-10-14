"""Subscriptions found in transactions, and alerts (services/recurring.py, services/alerts.py).

Detection runs after every transactions sync (jobs/recurring.py); these
endpoints read its results, record the user's verdict on each subscription,
and dismiss alerts. docs/80 "Subscriptions and alerts".
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, DismissedAlert, RecurringStream
from ..services import alerts, recurring
from ._common import ApiError, money, parse_uuid, plain, ts

router = APIRouter()


def _today() -> date:
    return datetime.now(UTC).date()


def _accounts(sess: Session) -> dict[uuid.UUID, Account]:
    return {a.id: a for a in sess.execute(select(Account)).scalars()}


def stream_json(r: RecurringStream, today: date, accounts: dict[uuid.UUID, Account]) -> dict:
    acct = accounts.get(r.account_id) if r.account_id else None
    return {
        "id": str(r.id), "merchant": r.merchant, "name": r.name, "label": r.name or r.merchant,
        "cadence": r.cadence, "interval_days": r.interval_days,
        "amount": money(r.amount), "last_amount": money(r.last_amount),
        "previous_amount": money(r.previous_amount), "price_changed_on": ts(r.price_changed_on),
        "first_date": ts(r.first_date), "last_date": ts(r.last_date), "next_date": ts(r.next_date),
        "charge_count": r.charge_count, "category": r.category,
        "account_id": str(r.account_id) if r.account_id else None,
        "account_name": acct.name if acct else None, "account_mask": acct.mask if acct else None,
        "is_business": bool(acct and acct.is_business),
        "status": r.status, "state": "lapsed" if recurring.is_lapsed(r.next_date, r.cadence, today) else "active",
        "monthly": money(recurring.monthly_cost(r.amount, r.cadence)),
    }


@router.get("/recurring")
def list_streams(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Every stream; `monthly_*` add up the active ones per verdict."""
    today = _today()
    accounts = _accounts(sess)
    rows = sess.execute(select(RecurringStream).order_by(RecurringStream.next_date)).scalars()
    items = [stream_json(r, today, accounts) for r in rows]

    def monthly(status: str) -> str | None:
        return money(sum((Decimal(x["monthly"]) for x in items if x["status"] == status and x["state"] == "active"),
                         Decimal(0)))
    return {"streams": items, "monthly_confirmed": monthly("confirmed"), "monthly_detected": monthly("detected")}


class StreamPatch(BaseModel):
    status: Literal["detected", "confirmed", "dismissed"] | None = None
    #: The user's name for it; empty or null goes back to the merchant's.
    name: str | None = Field(default=None, max_length=200)


@router.patch("/recurring/{stream_id}")
def patch_stream(stream_id: str, body: StreamPatch, _: Principal = Depends(current_user),
                 sess: Session = Depends(get_session)):
    r = sess.get(RecurringStream, parse_uuid(stream_id))
    if r is None:
        raise ApiError(404, "not_found", "subscription not found")
    if body.status is not None:
        r.status = body.status
        r.status_set_at = datetime.now(UTC)
    if "name" in body.model_fields_set:
        r.name = (body.name or "").strip() or None
    sess.flush()
    return stream_json(r, _today(), _accounts(sess))


@router.get("/recurring/upcoming")
def upcoming(days: int = Query(default=30, ge=1, le=120), _: Principal = Depends(current_user),
             sess: Session = Depends(get_session)):
    """Charges expected in the next `days`, from every active stream that isn't
    dismissed; a weekly one appears once per week. Overdue ones (still within
    their tolerance) are listed as due today."""
    today = _today()
    horizon = today + timedelta(days=days)
    accounts = _accounts(sess)
    items = []
    for r in sess.execute(select(RecurringStream).where(RecurringStream.status != "dismissed")).scalars():
        if recurring.is_lapsed(r.next_date, r.cadence, today):
            continue
        cadence = recurring.BY_NAME[r.cadence]
        d = r.next_date
        while d <= horizon:
            acct = accounts.get(r.account_id) if r.account_id else None
            items.append({"stream_id": str(r.id), "label": r.name or r.merchant, "date": max(d, today),
                          "overdue": d < today, "amount": r.amount, "cadence": r.cadence, "status": r.status,
                          "category": r.category, "account_name": acct.name if acct else None,
                          "is_business": bool(acct and acct.is_business)})
            d = recurring.next_after(d, cadence)
    items.sort(key=lambda x: (x["date"], x["label"]))
    return plain({"from": today, "to": horizon, "items": items,
                  "total": sum((x["amount"] for x in items), Decimal(0))})


@router.post("/recurring/detect")
def detect_now(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Run detection now instead of waiting for the next sync."""
    return {"found": recurring.sync_streams(sess)}


@router.get("/alerts")
def list_alerts(days: int = Query(default=60, ge=7, le=365), _: Principal = Depends(current_user),
                sess: Session = Depends(get_session)):
    return {"days": days, "alerts": plain(alerts.find_alerts(sess, _today(), days))}


class DismissIn(BaseModel):
    key: str = Field(min_length=3, max_length=200)


@router.post("/alerts/dismiss", status_code=204)
def dismiss_alert(body: DismissIn, p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    if sess.get(DismissedAlert, body.key) is None:
        sess.add(DismissedAlert(key=body.key, dismissed_by=p.user_id))
    return None
