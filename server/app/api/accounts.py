from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user, dashboard_only
from ..auth.human import Principal
from ..config import settings
from ..db import get_session
from ..models import MANUAL_CATEGORIES, Account, BalanceSnapshot, PlaidItem, is_liability_for
from ..plaid_client import PlaidError
from ..services import plaid_sync
from ._common import ApiError, account_json, parse_uuid

router = APIRouter()


def _get(sess: Session, account_id: str) -> Account:
    a = sess.execute(select(Account).options(selectinload(Account.item))
                     .where(Account.id == parse_uuid(account_id))).scalar_one_or_none()
    if a is None:
        raise ApiError(404, "not_found", "account not found")
    return a


@router.get("/accounts")
def list_accounts(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    rows = sess.execute(select(Account).options(selectinload(Account.item))
                        .order_by(Account.display_order, Account.name)).scalars()
    return {"accounts": [account_json(a) for a in rows]}


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    is_hidden: bool | None = None
    display_order: int | None = None


@router.patch("/accounts/{account_id}")
def patch_account(account_id: str, body: AccountPatch, _: Principal = Depends(current_user),
                  sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    if body.name is not None:
        a.name = body.name.strip() or a.name
    if body.is_hidden is not None:
        a.is_hidden = body.is_hidden
    if body.display_order is not None:
        a.display_order = body.display_order
    sess.flush()
    return account_json(a)


class ManualAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    manual_category: Literal["real_estate", "vehicle", "cash", "other_asset", "other_liability"]
    value: Decimal
    iso_currency: str = Field(default="USD", min_length=3, max_length=3)
    note: str | None = None


@router.post("/accounts/manual", status_code=201)
def create_manual(body: ManualAccountIn, _: Principal = Depends(current_user),
                  sess: Session = Depends(get_session)):
    if body.manual_category not in MANUAL_CATEGORIES:
        raise ApiError(400, "bad_request", "unknown manual_category")
    a = Account(kind="manual", name=body.name.strip(), manual_category=body.manual_category,
                type="manual", subtype=body.manual_category, iso_currency=body.iso_currency.upper(),
                current_balance=body.value, balance_updated_at=datetime.now(UTC),
                is_liability=is_liability_for("manual", None, body.manual_category))
    sess.add(a)
    sess.flush()
    plaid_sync.write_snapshots(sess, [a], source="manual")
    return account_json(a, None)


class ValueIn(BaseModel):
    value: Decimal
    as_of: date | None = None
    note: str | None = None


@router.put("/accounts/{account_id}/value")
def set_value(account_id: str, body: ValueIn, _: Principal = Depends(current_user),
              sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    if a.kind != "manual":
        raise ApiError(400, "bad_request", "only manual accounts take a value")
    as_of = body.as_of or datetime.now(UTC).date()
    if as_of > datetime.now(UTC).date():
        raise ApiError(400, "bad_request", "as_of cannot be in the future")
    today = datetime.now(UTC).date()
    if as_of == today or a.balance_updated_at is None or as_of >= a.balance_updated_at.date():
        a.current_balance = body.value
        a.balance_updated_at = datetime.now(UTC)
    snap = sess.execute(select(BalanceSnapshot).where(BalanceSnapshot.account_id == a.id,
                                                      BalanceSnapshot.as_of == as_of)).scalar_one_or_none()
    if snap is None:
        sess.add(BalanceSnapshot(account_id=a.id, as_of=as_of, current_balance=body.value,
                                 source="manual", note=body.note))
    else:
        snap.current_balance, snap.source, snap.note = body.value, "manual", body.note
    sess.flush()
    return account_json(a, None)


@router.delete("/accounts/{account_id}", status_code=204)
def delete_manual(account_id: str, _: Principal = Depends(dashboard_only),
                  sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    if a.kind != "manual":
        raise ApiError(400, "bad_request", "Plaid accounts are removed by unlinking their item")
    sess.delete(a)
    sess.flush()
    return None


@router.post("/accounts/{account_id}/refresh")
def refresh(account_id: str, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Real-time balance via /accounts/balance/get for the whole item. Billed
    per call, so rate limited per item."""
    a = _get(sess, account_id)
    if a.kind != "plaid" or a.item is None:
        raise ApiError(400, "bad_request", "manual accounts have nothing to refresh")
    item: PlaidItem = a.item
    if item.status == "removed":
        raise ApiError(409, "conflict", "item was unlinked")
    s = settings()
    now = datetime.now(UTC)
    last = max((x.last_refresh_requested_at for x in item.accounts if x.last_refresh_requested_at),
               default=None)
    if last and now - last < timedelta(seconds=s.refresh_min_interval_seconds):
        wait = int((last + timedelta(seconds=s.refresh_min_interval_seconds) - now).total_seconds())
        raise ApiError(429, "rate_limited", f"try again in {wait}s")
    for x in item.accounts:
        x.last_refresh_requested_at = now
    try:
        plaid_sync.refresh_accounts(sess, item, realtime=True)
    except PlaidError as e:
        sess.flush()
        raise ApiError(502, "plaid_error", f"{e.error_code}: {e.body.get('error_message')}") from e
    sess.refresh(a)
    return account_json(a)


@router.get("/accounts/{account_id}/history")
def history(account_id: str, range: str = "1y", _: Principal = Depends(current_user),
            sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    days = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "all": 36500}.get(range, 366)
    since = datetime.now(UTC).date() - timedelta(days=days)
    rows = sess.execute(select(BalanceSnapshot).where(BalanceSnapshot.account_id == a.id,
                                                      BalanceSnapshot.as_of >= since)
                        .order_by(BalanceSnapshot.as_of)).scalars()
    from ._common import money
    return {"account_id": str(a.id),
            "points": [{"date": r.as_of.isoformat(), "balance": money(r.current_balance),
                        "source": r.source} for r in rows]}
