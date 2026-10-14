from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account
from ..services import terms
from ._common import account_json, money, num, ts

router = APIRouter()


@router.get("/liabilities")
def liabilities(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Every open liability with its lender's record, gaps filled from what the
    person entered and what follows from it (services/terms.liability_json)."""
    accts = sess.execute(select(Account).options(selectinload(Account.item))
                         .where(Account.is_liability.is_(True), Account.closed_at.is_(None))
                         .order_by(Account.display_order, Account.name)).scalars().all()
    accts = [a for a in accts if a.item is None or a.item.status != "removed"]
    liabs, entered = terms.load(sess, accts)
    today = datetime.now(UTC).date()
    out = []
    for a in accts:
        d = terms.liability_json(a, liabs.get(a.id), entered.get(a.id), today)
        if d is not None:
            d = {**d, "interest_rate_pct": num(d["interest_rate_pct"]), "sources": d["sources"]}
            d = {k: (money(v) if isinstance(v, Decimal) else ts(v) if isinstance(v, (date, datetime)) else v)
                 for k, v in d.items()}
        out.append({"account": account_json(a), "detail": d})
    return {"total_owed": money(sum((a.current_balance or 0) for a in accts if not a.is_hidden)),
            "accounts": out}
