from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user, dashboard_only
from ..auth.human import Principal
from ..config import settings
from ..db import get_session
from ..models import (
    MANUAL_CATEGORIES,
    SECURABLE_CATEGORIES,
    Account,
    AccountTerms,
    AssetDetails,
    BalanceSnapshot,
    Liability,
    PlaidItem,
    is_liability_for,
)
from ..plaid_client import PlaidError
from ..services import plaid_sync, terms
from ..services.trends import balance_trends
from ._common import ApiError, account_group, account_json, money, parse_uuid

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
                        .order_by(Account.display_order, Account.name)).scalars().all()
    trends = balance_trends(sess, [a.id for a in rows], current={a.id: a.current_balance for a in rows})
    # An offline home's place ("Montclair, NJ 07042"), so a car can be kept at it.
    places = {d.account_id: d for d in sess.execute(select(AssetDetails)).scalars()}

    def place(a: Account) -> dict:
        d = places.get(a.id)
        if d is None or a.kind != "manual":
            return {}
        where = " ".join(x for x in (", ".join(y for y in (d.city, d.state) if y), d.zip) if x)
        return {"asset_place": where or None, "asset_zip": d.zip}
    return {"accounts": [{**account_json(a), **place(a), "trend": [money(v) for v in trends.get(a.id, [])]}
                         for a in rows]}


GroupKey = Literal["cash", "investments", "real_estate", "vehicles", "other_assets", "credit_cards", "loans",
                   "other_liabilities"]


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    is_hidden: bool | None = None
    is_business: bool | None = None
    display_order: int | None = None
    #: Where the account counts (networth.GROUPS); null goes back to what its type says.
    group: GroupKey | None = None
    #: The offline asset (home, car) this loan is secured by; null unlinks.
    secured_by_id: str | None = None


def _collateral(sess: Session, loan: Account, asset_id: str | None) -> uuid.UUID | None:
    """Validate a loan -> offline asset link (Account.secured_by_id)."""
    if asset_id is None:
        return None
    if not loan.is_liability or loan.type == "credit":
        raise ApiError(400, "bad_request", "only a loan can be secured by an asset")
    asset = sess.get(Account, parse_uuid(asset_id))
    if (asset is None or asset.kind != "manual" or asset.manual_category not in SECURABLE_CATEGORIES
            or asset.closed_at is not None):
        raise ApiError(400, "bad_request", "a loan can be secured only by an offline home, vehicle or other asset")
    return asset.id


@router.patch("/accounts/{account_id}")
def patch_account(account_id: str, body: AccountPatch, _: Principal = Depends(current_user),
                  sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    if body.name is not None:
        a.name = body.name.strip() or a.name
    if body.is_hidden is not None:
        a.is_hidden = body.is_hidden
    if body.is_business is not None:
        a.is_business = body.is_business
    if body.display_order is not None:
        a.display_order = body.display_order
    if "group" in body.model_fields_set:
        _set_group(sess, a, body.group)
    if "secured_by_id" in body.model_fields_set:  # an explicit null unlinks
        a.secured_by_id = _collateral(sess, a, body.secured_by_id)
    sess.flush()
    return account_json(a)


def _set_group(sess: Session, a: Account, group: str | None) -> None:
    """Count the account in `group`. An offline account whose group has a category of
    its own takes that category (so a home is a home everywhere); otherwise the group
    is kept as an override. Liability or asset follows the group, and history is
    rebuilt (cash and card groups rebuild from transactions)."""
    from ..services import history
    from ..services.networth import LIABILITY_GROUPS, MANUAL_CATEGORY_FOR
    a.group_override = None
    a.is_liability = is_liability_for(a.kind, a.type, a.manual_category)  # what its kind alone says
    if group is not None and group != account_group(a, natural=True):
        if a.kind == "manual" and group in MANUAL_CATEGORY_FOR:
            a.manual_category = a.subtype = MANUAL_CATEGORY_FOR[group]
        else:
            a.group_override = group
    effective = account_group(a)
    a.is_liability = effective in LIABILITY_GROUPS
    if not a.is_liability:
        a.secured_by_id = None  # only a debt is secured by something
    sess.flush()
    with sess.begin_nested():
        history.derive_account(sess, a)


class OrderIn(BaseModel):
    #: One group's accounts, top to bottom. Positions are written as 0..n-1.
    account_ids: list[str] = Field(min_length=1, max_length=500)


@router.put("/accounts/order")
def reorder_accounts(body: OrderIn, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Drag-and-drop reorder: set display_order for the listed accounts in one
    transaction. Groups sort independently, so the dashboard sends one group's
    full list (hidden accounts included) after each drop."""
    ids = [parse_uuid(i, "account_ids") for i in body.account_ids]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "bad_request", "account_ids contains duplicates")
    rows = {a.id: a for a in sess.execute(select(Account).where(Account.id.in_(ids))).scalars()}
    missing = [str(i) for i in ids if i not in rows]
    if missing:
        raise ApiError(404, "not_found", f"unknown account ids: {', '.join(missing)}")
    for position, account_id in enumerate(ids):
        rows[account_id].display_order = position
    sess.flush()
    return {"ok": True, "count": len(ids)}


class AssetIn(BaseModel):
    """What a monthly market valuation needs: a home's address (and, optionally, its
    size), or a vehicle's VIN, mileage and ZIP. A new mileage keeps the old reading,
    so the pace between them projects today's."""
    model_config = {"extra": "forbid"}
    valuation_enabled: bool = True
    address_line: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, pattern=r"^[A-Za-z]{2}$")
    zip: str | None = Field(default=None, pattern=r"^\d{5}(-\d{4})?$")
    property_type: Literal["Single Family", "Condo", "Townhouse", "Multi-Family", "Manufactured", "Land"] | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    bathrooms: Decimal | None = Field(default=None, ge=0, le=50)
    square_feet: int | None = Field(default=None, ge=100, le=100_000)
    vin: str | None = Field(default=None, max_length=17)
    mileage: int | None = Field(default=None, ge=0, le=2_000_000)
    miles_per_month: Literal[100, 250, 500, 750, 1000, 1500, 2000] | None = None
    #: The home a vehicle is kept at (an offline home account); its ZIP prices the car.
    garage_account_id: str | None = None


def _asset(sess: Session, a: Account, body: AssetIn, user_id) -> AssetDetails:
    from ..services import valuations
    if valuations.kind_of(a) is None:
        raise ApiError(400, "bad_request", "market values are for offline homes and vehicles")
    det = sess.get(AssetDetails, a.id) or AssetDetails(account_id=a.id)
    vin = (body.vin or "").strip().upper() or None
    if vin is not None and not valuations.VIN.fullmatch(vin):
        raise ApiError(400, "bad_request", "a VIN is 17 letters and digits (no I, O or Q)")
    today = datetime.now(UTC).date()
    if body.mileage != det.mileage:  # a new reading, as of today
        det.mileage, det.mileage_as_of = body.mileage, today if body.mileage is not None else None
    det.miles_per_month = body.miles_per_month
    garage = None
    if body.garage_account_id:
        garage = sess.get(Account, parse_uuid(body.garage_account_id, "garage_account_id"))
        if garage is None or valuations.kind_of(garage) != "home" or garage.id == a.id:
            raise ApiError(400, "bad_request", "a vehicle is kept at one of your offline homes")
    det.garage_account_id = garage.id if garage is not None else None
    det.valuation_enabled = body.valuation_enabled
    det.address_line = (body.address_line or "").strip() or None
    det.city = (body.city or "").strip() or None
    det.state = (body.state or "").upper() or None
    det.zip = body.zip or None
    det.property_type, det.bedrooms, det.bathrooms, det.square_feet = (body.property_type, body.bedrooms,
                                                                       body.bathrooms, body.square_feet)
    if vin != det.vin:
        det.vin, det.vehicle_label, det.decoded_vin = vin, None, None
    det.updated_by = user_id
    sess.add(det)
    sess.flush()
    return det


@router.get("/accounts/{account_id}/asset")
def get_asset(account_id: str, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """An offline home's or vehicle's valuation inputs and its recent monthly values."""
    from ..services import valuations
    a = _get(sess, account_id)
    return valuations.details_json(a, sess.get(AssetDetails, a.id), sess, datetime.now(UTC).date())


@router.put("/accounts/{account_id}/asset")
def put_asset(account_id: str, body: AssetIn, p: Principal = Depends(current_user),
              sess: Session = Depends(get_session)):
    """Set what a valuation needs. Nothing is asked for here: the monthly job does that."""
    from ..services import valuations
    a = _get(sess, account_id)
    det = _asset(sess, a, body, p.user_id)
    return valuations.details_json(a, det, sess, datetime.now(UTC).date())


class ManualAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    manual_category: Literal["real_estate", "vehicle", "cash", "other_asset", "other_liability"]
    value: Decimal
    iso_currency: str = Field(default="USD", min_length=3, max_length=3)
    note: str | None = None
    #: A home's address or a vehicle's VIN and mileage, for its monthly market value.
    asset: AssetIn | None = None


@router.post("/accounts/manual", status_code=201)
def create_manual(body: ManualAccountIn, p: Principal = Depends(current_user),
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
    if body.asset is not None:
        _asset(sess, a, body.asset, p.user_id)
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


@router.get("/accounts/{account_id}/details")
def account_details(account_id: str, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Everything the detail panel shows: the bank's facts, the person's where the
    bank is silent, and what follows (services/terms.py)."""
    return terms.details(sess, _get(sess, account_id), datetime.now(UTC).date())


class TermsIn(BaseModel):
    """What a person can fill in where the bank is silent. Omitted fields keep
    their value; null clears one."""
    model_config = ConfigDict(extra="forbid")
    interest_rate_pct: Decimal | None = Field(default=None, ge=0, le=40)
    rate_type: Literal["fixed", "variable"] | None = None
    original_principal: Decimal | None = Field(default=None, gt=0, le=100_000_000)
    origination_date: date | None = None
    term_months: int | None = Field(default=None, ge=1, le=600)
    payment_amount: Decimal | None = Field(default=None, gt=0, le=10_000_000)
    escrow_amount: Decimal | None = Field(default=None, ge=0, le=1_000_000)
    payment_day: int | None = Field(default=None, ge=1, le=31)
    statement_day: int | None = Field(default=None, ge=1, le=31)
    credit_limit: Decimal | None = Field(default=None, gt=0, le=100_000_000)
    minimum_payment: Decimal | None = Field(default=None, ge=0, le=10_000_000)


def _entered(sess: Session, a: Account, body: TermsIn) -> AccountTerms:
    """The stored terms with `body` applied, as a detached copy (nothing is written)."""
    kind = terms.kind_of(a, sess.execute(select(Liability).where(Liability.account_id == a.id)).scalar_one_or_none())
    allowed = {f.key for f in terms.fields_for(kind)}
    extra = sorted(body.model_fields_set - allowed)
    if extra:
        raise ApiError(400, "bad_request", f"not something to enter for this account: {', '.join(extra)}")
    if body.origination_date and body.origination_date > datetime.now(UTC).date():
        raise ApiError(400, "bad_request", "the start date can't be in the future")
    stored = sess.get(AccountTerms, a.id)
    out = AccountTerms(account_id=a.id)
    for key in terms.TERM_KEYS:
        setattr(out, key, getattr(stored, key) if stored is not None else None)
    for key in body.model_fields_set:
        setattr(out, key, getattr(body, key))
    return out


@router.put("/accounts/{account_id}/terms")
def put_terms(account_id: str, body: TermsIn, p: Principal = Depends(current_user),
              sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    entered = _entered(sess, a, body)
    row = sess.get(AccountTerms, a.id)
    if all(getattr(entered, k) is None for k in terms.TERM_KEYS):
        if row is not None:
            sess.delete(row)
    else:
        if row is None:
            row = AccountTerms(account_id=a.id)
            sess.add(row)
        for key in terms.TERM_KEYS:
            setattr(row, key, getattr(entered, key))
        row.updated_by = p.user_id
    sess.flush()
    return terms.details(sess, a, datetime.now(UTC).date())


@router.post("/accounts/{account_id}/terms/preview")
def preview_terms(account_id: str, body: TermsIn, _: Principal = Depends(current_user),
                  sess: Session = Depends(get_session)):
    """The panel as it would read with these terms, saving nothing (the form's live preview)."""
    a = _get(sess, account_id)
    return terms.details(sess, a, datetime.now(UTC).date(), entered=_entered(sess, a, body))


@router.delete("/accounts/{account_id}", status_code=204)
def delete_manual(account_id: str, _: Principal = Depends(dashboard_only),
                  sess: Session = Depends(get_session)):
    a = _get(sess, account_id)
    if a.kind != "manual":
        raise ApiError(400, "bad_request", "connected accounts are removed by unlinking their connection in Settings")
    sess.delete(a)
    sess.flush()
    return None


@router.post("/accounts/{account_id}/refresh")
def refresh(account_id: str, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """The latest balances Plaid has for the whole item, via /accounts/get
    (free; Plaid refreshes them several times a day). Rate limited per item so
    a busy finger can't hammer Plaid."""
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
        plaid_sync.refresh_accounts(sess, item)
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
