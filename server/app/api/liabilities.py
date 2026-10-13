from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, Liability
from ._common import account_json, money, num, ts

router = APIRouter()


@router.get("/liabilities")
def liabilities(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    accts = sess.execute(select(Account).options(selectinload(Account.item))
                         .where(Account.is_liability.is_(True), Account.closed_at.is_(None))
                         .order_by(Account.display_order, Account.name)).scalars().all()
    accts = [a for a in accts if a.item is None or a.item.status != "removed"]
    detail = {L.account_id: L for L in sess.execute(
        select(Liability).where(Liability.account_id.in_([a.id for a in accts]))).scalars()}
    out = []
    for a in accts:
        L = detail.get(a.id)
        out.append({"account": account_json(a), "detail": None if L is None else {
            "kind": L.kind, "interest_rate_pct": num(L.interest_rate_pct),
            "interest_rate_type": L.interest_rate_type,
            "next_payment_due_date": ts(L.next_payment_due_date),
            "minimum_payment": money(L.minimum_payment), "next_payment_amount": money(L.next_payment_amount),
            "last_payment_amount": money(L.last_payment_amount), "last_payment_date": ts(L.last_payment_date),
            "last_statement_balance": money(L.last_statement_balance),
            "last_statement_date": ts(L.last_statement_date), "is_overdue": L.is_overdue,
            "origination_date": ts(L.origination_date), "origination_principal": money(L.origination_principal),
            "loan_term": L.loan_term, "maturity_date": ts(L.maturity_date), "updated_at": ts(L.updated_at),
        }})
    return {"total_owed": money(sum((a.current_balance or 0) for a in accts if not a.is_hidden)),
            "accounts": out}
