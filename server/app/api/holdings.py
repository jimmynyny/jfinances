from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, Holding, InvestmentTransaction, PlaidItem, Security
from ._common import account_json, money, num, parse_uuid, ts

router = APIRouter()


@router.get("/holdings")
def holdings(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    accts = sess.execute(select(Account).options(selectinload(Account.item))
                         .where(Account.type == "investment", Account.closed_at.is_(None))
                         .order_by(Account.display_order, Account.name)).scalars().all()
    accts = [a for a in accts if a.item is None or a.item.status != "removed"]
    rows = sess.execute(select(Holding, Security).join(Security, Security.id == Holding.security_id)
                        .where(Holding.account_id.in_([a.id for a in accts]))).all()
    by_acct: dict = {}
    for h, s in rows:
        by_acct.setdefault(h.account_id, []).append({
            "id": str(h.id), "security_id": str(s.id), "ticker": s.ticker, "name": s.name,
            "type": s.type, "is_cash_equivalent": s.is_cash_equivalent,
            "quantity": num(h.quantity), "cost_basis": money(h.cost_basis),
            "price": num(h.institution_price), "price_as_of": ts(h.institution_price_as_of),
            "value": money(h.institution_value), "iso_currency": h.iso_currency,
            "close_price": num(s.close_price), "close_price_as_of": ts(s.close_price_as_of),
        })
    total = Decimal(0)
    out = []
    for a in accts:
        hs = sorted(by_acct.get(a.id, []), key=lambda x: Decimal(x["value"] or 0), reverse=True)
        value = sum((Decimal(h["value"] or 0) for h in hs), Decimal(0))
        total += Decimal(a.current_balance or 0)
        out.append({"account": account_json(a), "holdings_value": money(value), "holdings": hs})
    return {"total_value": money(total), "accounts": out}


@router.get("/holdings/transactions")
def investment_transactions(account_id: str | None = None, limit: int = 200,
                            _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    stmt = (select(InvestmentTransaction, Security, Account, PlaidItem.institution_name)
            .outerjoin(Security, Security.id == InvestmentTransaction.security_id)
            .join(Account, Account.id == InvestmentTransaction.account_id)
            .outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
            .order_by(InvestmentTransaction.date.desc()).limit(min(limit, 1000)))
    if account_id:
        stmt = stmt.where(InvestmentTransaction.account_id == parse_uuid(account_id, "account_id"))
    rows = sess.execute(stmt).all()
    return {"transactions": [{
        "id": str(t.id), "account_id": str(t.account_id), "account_name": a.name, "institution_name": inst,
        "date": t.date.isoformat(), "name": t.name, "type": t.type, "subtype": t.subtype,
        "ticker": s.ticker if s else None, "security_name": s.name if s else None,
        "quantity": num(t.quantity), "amount": money(t.amount), "price": num(t.price), "fees": money(t.fees),
    } for t, s, a, inst in rows]}
