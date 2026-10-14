from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, case, cast, extract, func, literal, or_, select, update
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, PlaidItem, Transaction
from ..services import insights
from ..services.flows import PAYMENT, display_category, is_liability_payment_clause, is_transfer_clause
from ._common import ApiError, money, parse_uuid, ts

router = APIRouter()

ZERO = Decimal(0)
#: Most rows one request selects or recategorizes.
MAX_IDS = 5000
INCOME_KINDS = {*insights.INCOME_KINDS.values(), insights.OTHER_INCOME}


def _tx_json(t: Transaction, a: Account | None, inst: str | None) -> dict:
    return {
        "id": str(t.id), "account_id": str(t.account_id), "account_name": a.name if a else None,
        "account_mask": a.mask if a else None, "institution_name": inst,
        # Business by its own flag (`business`: the person's say, null to follow the account), else its account's.
        "is_business": t.business if t.business is not None else bool(a and a.is_business), "business": t.business,
        "date": t.date.isoformat(), "authorized_date": ts(t.authorized_date),
        "amount": money(t.amount), "iso_currency": t.iso_currency, "name": t.name,
        "merchant_name": t.merchant_name, "logo_url": t.logo_url, "pending": t.pending,
        "category_primary": t.category_primary, "category_detailed": t.category_detailed,
        "category": display_category(t, a), "user_category": t.user_category,
        "payment_channel": t.payment_channel, "notes": t.notes, "removed_at": ts(t.removed_at),
    }


def _like(text: str) -> str:
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class TxQuery:
    """The list's filters, shared by the list, its summary and its ids (docs/80 "GET /transactions").

    `flow` shows the rows behind an Insights number: it applies Insights' rules
    (posted, no transfers between your accounts or payments into cards and loans,
    no hidden accounts) and picks income, spending or both. The finer filters
    (`detailed`, `merchant`, `income_kind`, `not_*`, `weekday`, `day`) follow
    Insights' groupings, so a list sums to the number it came from."""

    def __init__(self, from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                 account_id: str | None = None, q: str | None = None, category: str | None = None,
                 pending: bool | None = None,
                 flow: Literal["income", "spending", "all"] | None = None,
                 scope: insights.Scope = "all",
                 detailed: str | None = None,
                 merchant: str | None = Query(default=None, max_length=300),
                 income_kind: str | None = None,
                 direction: Literal["in", "out"] | None = None,
                 not_category: list[str] = Query(default=[]),
                 not_detailed: list[str] = Query(default=[]),
                 not_source: list[str] = Query(default=[]),
                 weekday: int | None = Query(default=None, ge=0, le=6),
                 day: int | None = Query(default=None, ge=1, le=31)):
        if income_kind is not None and income_kind not in INCOME_KINDS:
            raise ApiError(400, "bad_request", f"unknown income_kind {income_kind!r}")
        self.from_, self.to, self.q, self.category, self.pending = from_, to, q, category, pending
        self.account = parse_uuid(account_id, "account_id") if account_id else None
        self.flow, self.scope, self.detailed, self.merchant = flow, scope, detailed, merchant
        self.income_kind, self.direction, self.weekday, self.day = income_kind, direction, weekday, day
        self.not_category, self.not_detailed = not_category, not_detailed
        # "kind:merchant" pairs: Insights' income sources, which the money-flow diagram folds into "other income".
        self.not_source = {tuple(x.split(":", 1)) for x in not_source if ":" in x}

    @property
    def needs_python(self) -> bool:
        """Merchants are named in Python (insights.merchant_key), so those filters run there."""
        return bool(self.merchant or self.not_source)

    def clauses(self, *, include_removed: bool = False) -> list:
        out: list = []
        if not include_removed:
            out.append(Transaction.removed_at.is_(None))
        if self.from_:
            out.append(Transaction.date >= self.from_)
        if self.to:
            out.append(Transaction.date <= self.to)
        if self.account:
            out.append(Transaction.account_id == self.account)
        if self.q:
            like = _like(self.q.strip())
            out.append(or_(Transaction.name.ilike(like), Transaction.merchant_name.ilike(like),
                           Transaction.notes.ilike(like), cast(Transaction.amount, String).ilike(like)))
        if self.category:
            out.append(insights.effective_category() == self.category)
        if self.pending is not None:
            out.append(Transaction.pending.is_(self.pending))
        if (scoped := insights.scope_clause(self.scope)) is not None:
            out.append(scoped)
        if self.flow:
            out += insights.counted_clauses()
            if self.flow == "income":
                out.append(insights.effective_category() == insights.INCOME)
            elif self.flow == "spending":
                out.append(insights.effective_category() != insights.INCOME)
        if self.detailed:
            out.append(insights.detail_key() == self.detailed)
        if self.not_category:
            out.append(insights.effective_category().notin_(self.not_category))
        if self.not_detailed:
            out.append(insights.detail_key().notin_(self.not_detailed))
        if self.income_kind:
            known = list(insights.INCOME_KINDS)
            if self.income_kind == insights.OTHER_INCOME:
                out.append(or_(Transaction.category_detailed.is_(None), Transaction.category_detailed.notin_(known)))
            else:
                out.append(Transaction.category_detailed.in_([k for k, v in insights.INCOME_KINDS.items()
                                                              if v == self.income_kind]))
        if self.direction == "out":
            out.append(Transaction.amount > 0)
        elif self.direction == "in":
            out.append(Transaction.amount < 0)
        if self.weekday is not None:
            out.append(extract("isodow", Transaction.date) == self.weekday + 1)
        if self.day is not None:
            out.append(extract("day", Transaction.date) == self.day)
        if self.merchant and self.merchant != "Unknown":
            # A superset in SQL (the name it came from contains its first word), exact in Python.
            first = self.merchant.split()[0] if self.merchant.split() else self.merchant
            out.append(or_(Transaction.merchant_name.ilike(_like(self.merchant)), Transaction.name.ilike(_like(first))))
        return out

    def keep(self, t: Transaction) -> bool:
        m = insights.merchant_key(t.merchant_name, t.name)
        if self.merchant and m != self.merchant:
            return False
        return not (self.not_source and (insights.income_kind(t.category_detailed), m) in self.not_source)


def _rows_stmt(tq: TxQuery, **kw):
    return (select(Transaction, Account, PlaidItem.institution_name)
            .join(Account, Account.id == Transaction.account_id)
            .outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
            .where(*tq.clauses(**kw)))


NEWEST_FIRST = (Transaction.date.desc(), Transaction.created_at.desc())
#: Biggest money first, either way: what to look at when a total seems too big.
LARGEST_FIRST = (func.abs(Transaction.amount).desc(), *NEWEST_FIRST)


@router.get("/transactions")
def list_transactions(tq: TxQuery = Depends(), page: int = Query(default=1, ge=1),
                      page_size: int = Query(default=50, ge=1, le=500),
                      sort: Literal["newest", "largest"] = "newest",
                      _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    stmt = _rows_stmt(tq)
    order = LARGEST_FIRST if sort == "largest" else NEWEST_FIRST
    if tq.needs_python:
        rows = [r for r in sess.execute(stmt.order_by(*order)).all() if tq.keep(r[0])]
        total, total_sum = len(rows), sum((r[0].amount for r in rows), ZERO)
        rows = rows[(page - 1) * page_size:page * page_size]
    else:
        total, total_sum = sess.execute(
            select(func.count(), func.coalesce(func.sum(Transaction.amount), 0))
            .join(Account, Account.id == Transaction.account_id).where(*tq.clauses())).one()
        rows = sess.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"page": page, "page_size": page_size, "total": total, "sum": money(total_sum),
            "transactions": [_tx_json(t, a, inst) for t, a, inst in rows]}


@router.get("/transactions/ids")
def transaction_ids(tq: TxQuery = Depends(), _: Principal = Depends(current_user),
                    sess: Session = Depends(get_session)):
    """Every id the list's filters match, newest first, to select them all at once."""
    stmt = (select(Transaction).join(Account, Account.id == Transaction.account_id)
            .where(*tq.clauses()).order_by(*NEWEST_FIRST))
    if tq.needs_python:
        ids = [str(t.id) for t in sess.execute(stmt).scalars() if tq.keep(t)]
    else:
        ids = [str(i) for i in sess.execute(stmt.with_only_columns(Transaction.id).limit(MAX_IDS + 1)).scalars()]
    if len(ids) > MAX_IDS:
        raise ApiError(400, "too_many", f"more than {MAX_IDS} transactions match; narrow the filters")
    return {"ids": ids, "total": len(ids)}


class TxPatch(BaseModel):
    user_category: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)
    #: True business, False personal, null: as its account.
    business: bool | None = None


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
    if "business" in body.model_fields_set:
        t.business = body.business
    sess.flush()
    return _tx_json(t, a, inst)


class BulkEdit(BaseModel):
    model_config = {"extra": "forbid"}
    ids: list[str] = Field(min_length=1, max_length=MAX_IDS)
    #: The category to file them under; null or blank goes back to the bank's. Omitted: unchanged.
    user_category: str | None = Field(default=None, max_length=80)
    #: True business, False personal, null as each one's account. Omitted: unchanged.
    business: bool | None = None


@router.patch("/transactions")
def edit_many(body: BulkEdit, _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Several transactions at once: one category (or back to the bank's) and/or
    business or personal (or back to each one's account)."""
    ids = list({parse_uuid(i, "ids") for i in body.ids})
    changes: dict = {}
    if "user_category" in body.model_fields_set:
        changes["user_category"] = (body.user_category or "").strip() or None
    if "business" in body.model_fields_set:
        changes["business"] = body.business
    if not changes:
        raise ApiError(400, "bad_request", "nothing to change: send user_category and/or business")
    found = sess.execute(select(func.count()).select_from(Transaction)
                         .where(Transaction.id.in_(ids), Transaction.removed_at.is_(None))).scalar() or 0
    if found != len(ids):
        raise ApiError(404, "not_found",
                       f"{len(ids) - found} of these transactions no longer exist; reload and try again")
    sess.execute(update(Transaction).where(Transaction.id.in_(ids)).values(**changes)
                 .execution_options(synchronize_session=False))
    sess.flush()
    return {"updated": len(ids), **changes}


def _summary_key(group_by: str, t: Transaction, a: Account) -> str:
    if group_by == "month":
        return t.date.strftime("%Y-%m")
    if group_by == "account":
        return str(t.account_id)
    if display_category(t, a) == PAYMENT:
        return PAYMENT
    return t.user_category or t.category_primary or insights.UNCATEGORIZED


@router.get("/transactions/summary")
def summary(tq: TxQuery = Depends(), group_by: Literal["category", "month", "account"] = "category",
            include_transfers: bool = False,
            _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Totals per category, month or account. Each row has `inflow` (money in,
    positive), `outflow` (money out, positive), and `total` (net, Plaid sign:
    positive = more out than in). Month rows are chronological; the others
    are biggest net outflow first. Takes the list's filters; with `flow`, the
    rows are Insights' (transfers are already out)."""
    pay = is_liability_payment_clause()
    clauses = [*tq.clauses(), Transaction.pending.is_(False)]
    acct = sess.get(Account, tq.account) if tq.account else None
    if not include_transfers and not tq.flow:
        # A card or loan's own view counts its payments as its money in;
        # anywhere else they are the second half of a transfer.
        clauses.append(or_(~is_transfer_clause(), pay) if acct is not None and acct.is_liability
                       else and_(~is_transfer_clause(), ~pay))
    if tq.needs_python:
        agg: dict[str, list] = defaultdict(lambda: [ZERO, ZERO, ZERO, 0])
        for t, a in sess.execute(select(Transaction, Account).join(Account, Account.id == Transaction.account_id)
                                 .where(*clauses)).all():
            if not tq.keep(t):
                continue
            g = agg[_summary_key(group_by, t, a)]
            g[0] += t.amount
            g[1] += -t.amount if t.amount < 0 else ZERO
            g[2] += t.amount if t.amount > 0 else ZERO
            g[3] += 1
        order = sorted(agg) if group_by == "month" else sorted(agg, key=lambda k: agg[k][0], reverse=True)
        rows = [(k, *agg[k]) for k in order]
    else:
        cat = case((pay, literal(PAYMENT)), else_=insights.effective_category())
        key = {"category": cat, "month": func.to_char(Transaction.date, "YYYY-MM"),
               "account": cast(Transaction.account_id, String)}[group_by]
        outflow = func.coalesce(func.sum(case((Transaction.amount > 0, Transaction.amount))), 0)
        inflow = func.coalesce(func.sum(case((Transaction.amount < 0, -Transaction.amount))), 0)
        order = key.asc() if group_by == "month" else func.sum(Transaction.amount).desc()
        rows = sess.execute(select(key.label("key"), func.sum(Transaction.amount).label("total"),
                                   inflow.label("inflow"), outflow.label("outflow"), func.count().label("count"))
                            .join(Account, Account.id == Transaction.account_id)
                            .where(*clauses).group_by(key).order_by(order)).all()
    names = {}
    if group_by == "account":
        names = {str(a.id): a.name for a in sess.execute(select(Account)).scalars()}
    return {"group_by": group_by, "transfers": "included" if include_transfers and not tq.flow else "excluded",
            "rows": [{"key": k, "label": "PAYMENTS" if k == PAYMENT else names.get(k, k), "total": money(t),
                      "inflow": money(i),
                      "outflow": money(o), "count": c} for k, t, i, o, c in rows]}


@router.get("/transactions/categories")
def categories(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    rows = sess.execute(select(func.coalesce(Transaction.user_category, Transaction.category_primary))
                        .where(Transaction.removed_at.is_(None)).distinct()).scalars()
    return {"categories": sorted(c for c in rows if c)}

