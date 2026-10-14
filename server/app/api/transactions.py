from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, func, literal, or_, select
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, PlaidItem, Transaction
from ..services.flows import PAYMENT, display_category, is_liability_payment_clause, is_transfer_clause
from ._common import ApiError, money, parse_uuid, ts

router = APIRouter()


def _tx_json(t: Transaction, a: Account | None, inst: str | None) -> dict:
    return {
        "id": str(t.id), "account_id": str(t.account_id), "account_name": a.name if a else None,
        "account_mask": a.mask if a else None, "institution_name": inst,
        "date": t.date.isoformat(), "authorized_date": ts(t.authorized_date),
        "amount": money(t.amount), "iso_currency": t.iso_currency, "name": t.name,
        "merchant_name": t.merchant_name, "logo_url": t.logo_url, "pending": t.pending,
        "category_primary": t.category_primary, "category_detailed": t.category_detailed,
        "category": display_category(t, a), "user_category": t.user_category,
        "payment_channel": t.payment_channel, "notes": t.notes, "removed_at": ts(t.removed_at),
    }


def _base(sess: Session, *, from_: date | None, to: date | None, account_id: str | None,
          q: str | None, category: str | None, pending: bool | None, include_removed: bool = False):
    stmt = (select(Transaction, Account, PlaidItem.institution_name)
            .join(Account, Account.id == Transaction.account_id)
            .outerjoin(PlaidItem, PlaidItem.id == Account.item_id))
    if not include_removed:
        stmt = stmt.where(Transaction.removed_at.is_(None))
    if from_:
        stmt = stmt.where(Transaction.date >= from_)
    if to:
        stmt = stmt.where(Transaction.date <= to)
    if account_id:
        stmt = stmt.where(Transaction.account_id == parse_uuid(account_id, "account_id"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Transaction.name.ilike(like), Transaction.merchant_name.ilike(like),
                              Transaction.notes.ilike(like), cast(Transaction.amount, String).ilike(like)))
    if category:
        stmt = stmt.where(func.coalesce(Transaction.user_category, Transaction.category_primary) == category)
    if pending is not None:
        stmt = stmt.where(Transaction.pending.is_(pending))
    return stmt


@router.get("/transactions")
def list_transactions(from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                      account_id: str | None = None, q: str | None = None, category: str | None = None,
                      pending: bool | None = None, page: int = Query(default=1, ge=1),
                      page_size: int = Query(default=50, ge=1, le=500),
                      _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    stmt = _base(sess, from_=from_, to=to, account_id=account_id, q=q, category=category, pending=pending)
    total = sess.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    rows = sess.execute(stmt.order_by(Transaction.date.desc(), Transaction.created_at.desc())
                        .offset((page - 1) * page_size).limit(page_size)).all()
    return {"page": page, "page_size": page_size, "total": total,
            "transactions": [_tx_json(t, a, inst) for t, a, inst in rows]}


class TxPatch(BaseModel):
    user_category: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)


@router.patch("/transactions/{tx_id}")
def patch_transaction(tx_id: str, body: TxPatch, _: Principal = Depends(current_user),
                      sess: Session = Depends(get_session)):
    row = sess.execute(select(Transaction, Account, PlaidItem.institution_name)
                       .join(Account, Account.id == Transaction.account_id)
                       .outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
                       .where(Transaction.id == parse_uuid(tx_id))).first()
    if row is None:
        raise ApiError(404, "not_found", "transaction not found")
    t, a, inst = row
    if "user_category" in body.model_fields_set:
        t.user_category = (body.user_category or "").strip() or None
    if "notes" in body.model_fields_set:
        t.notes = (body.notes or "").strip() or None
    sess.flush()
    return _tx_json(t, a, inst)


@router.get("/transactions/summary")
def summary(from_: date | None = Query(default=None, alias="from"), to: date | None = None,
            account_id: str | None = None, group_by: Literal["category", "month", "account"] = "category",
            include_transfers: bool = False,
            _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Totals per category, month or account. Each row has `inflow` (money in,
    positive), `outflow` (money out, positive), and `total` (net, Plaid sign:
    positive = more out than in). Month rows are chronological; the others
    are biggest net outflow first."""
    pay = is_liability_payment_clause()
    cat = case((pay, literal(PAYMENT)),
               else_=func.coalesce(Transaction.user_category, Transaction.category_primary, "UNCATEGORIZED"))
    key = {"category": cat, "month": func.to_char(Transaction.date, "YYYY-MM"),
           "account": cast(Transaction.account_id, String)}[group_by]
    outflow = func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount))), 0)
    inflow = func.coalesce(func.sum(case((Transaction.amount < 0, -Transaction.amount))), 0)
    stmt = (select(key.label("key"), func.sum(Transaction.amount).label("total"), inflow.label("inflow"),
                   outflow.label("outflow"), func.count().label("count"))
            .join(Account, Account.id == Transaction.account_id)
            .where(Transaction.removed_at.is_(None), Transaction.pending.is_(False)))
    acct = sess.get(Account, parse_uuid(account_id, "account_id")) if account_id else None
    if not include_transfers:
        # A card or loan's own view counts its payments as its money in;
        # anywhere else they are the second half of a transfer.
        stmt = (stmt.where(or_(~is_transfer_clause(), pay)) if acct is not None and acct.is_liability
                else stmt.where(~is_transfer_clause(), ~pay))
    if from_:
        stmt = stmt.where(Transaction.date >= from_)
    if to:
        stmt = stmt.where(Transaction.date <= to)
    if account_id:
        stmt = stmt.where(Transaction.account_id == parse_uuid(account_id, "account_id"))
    order = key.asc() if group_by == "month" else func.sum(Transaction.amount).desc()
    rows = sess.execute(stmt.group_by(key).order_by(order)).all()
    names = {}
    if group_by == "account":
        names = {str(a.id): a.name for a in sess.execute(select(Account)).scalars()}
    return {"group_by": group_by, "transfers": "included" if include_transfers else "excluded",
            "rows": [{"key": k, "label": "PAYMENTS" if k == PAYMENT else names.get(k, k), "total": money(t),
                      "inflow": money(i),
                      "outflow": money(o), "count": c} for k, t, i, o, c in rows]}


@router.get("/transactions/categories")
def categories(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    rows = sess.execute(select(func.coalesce(Transaction.user_category, Transaction.category_primary))
                        .where(Transaction.removed_at.is_(None)).distinct()).scalars()
    return {"categories": sorted(c for c in rows if c)}
