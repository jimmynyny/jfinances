from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, BalanceSnapshot, PlaidItem
from ..services import networth
from ._common import account_json, money, ts

router = APIRouter()


def _rows(sess: Session) -> list[tuple[Account, networth.AccountRow]]:
    accts = sess.execute(select(Account).options(selectinload(Account.item))
                         .where(Account.closed_at.is_(None))).scalars().all()
    out = []
    for a in accts:
        if a.item is not None and a.item.status == "removed":
            continue
        out.append((a, networth.AccountRow(
            id=str(a.id), name=a.name, kind=a.kind, type=a.type, subtype=a.subtype,
            manual_category=a.manual_category, is_liability=a.is_liability, is_hidden=a.is_hidden,
            current_balance=a.current_balance, institution_name=a.item.institution_name if a.item else None,
            mask=a.mask, balance_updated_at=a.balance_updated_at,
            item_status=a.item.status if a.item else None, display_order=a.display_order)))
    return out


def _net_on(sess: Session, day) -> tuple[Decimal, Decimal, Decimal] | None:
    """Net worth as of a date from snapshots (latest snapshot on or before day
    per account)."""
    sub = (select(BalanceSnapshot.account_id, func.max(BalanceSnapshot.as_of).label("d"))
           .where(BalanceSnapshot.as_of <= day).group_by(BalanceSnapshot.account_id).subquery())
    q = (select(Account.is_liability, Account.is_hidden, BalanceSnapshot.current_balance)
         .join(sub, sub.c.account_id == BalanceSnapshot.account_id)
         .where(BalanceSnapshot.as_of == sub.c.d)
         .join(Account, Account.id == BalanceSnapshot.account_id)
         .outerjoin(PlaidItem, PlaidItem.id == Account.item_id)
         .where((PlaidItem.id.is_(None)) | (PlaidItem.status != "removed")))
    rows = sess.execute(q).all()
    if not rows:
        return None
    assets = liabilities = Decimal("0")
    for is_liab, hidden, bal in rows:
        if hidden or bal is None:
            continue
        if is_liab:
            liabilities += Decimal(bal)
        else:
            assets += Decimal(bal)
    return assets, liabilities, assets - liabilities


@router.get("/overview")
def overview(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    pairs = _rows(sess)
    rows = [r for _, r in pairs]
    by_id = {str(a.id): a for a, _ in pairs}
    assets, liabilities, net = networth.totals(rows)
    month_ago = (datetime.now(UTC) - timedelta(days=30)).date()
    then = _net_on(sess, month_ago)
    change = None
    if then is not None:
        change = {"amount": money(net - then[2]), "pct": (
            str(networth.pct_change(net, then[2])) if networth.pct_change(net, then[2]) is not None else None),
            "since": month_ago.isoformat()}

    groups = []
    for g in networth.grouped(rows):
        g_then = None
        groups.append({
            "key": g["key"], "label": g["label"], "is_liability": g["is_liability"],
            "total": money(g["total"]), "change_1m": g_then,
            "accounts": [account_json(by_id[r.id]) for r in g["accounts"]],
        })
    # Per-group month change from snapshots.
    sub = (select(BalanceSnapshot.account_id, func.max(BalanceSnapshot.as_of).label("d"))
           .where(BalanceSnapshot.as_of <= month_ago).group_by(BalanceSnapshot.account_id).subquery())
    q = (select(BalanceSnapshot.account_id, BalanceSnapshot.current_balance)
         .join(sub, (sub.c.account_id == BalanceSnapshot.account_id) & (sub.c.d == BalanceSnapshot.as_of)))
    then_by_acct = {str(aid): Decimal(bal or 0) for aid, bal in sess.execute(q).all()}
    for g in groups:
        visible = [a for a in g["accounts"] if not a["is_hidden"]]
        if not visible or not any(a["id"] in then_by_acct for a in visible):
            continue
        then_total = sum((then_by_acct.get(a["id"], Decimal(0)) for a in visible), Decimal(0))
        now_total = Decimal(g["total"])
        g["change_1m"] = {"amount": money(now_total - then_total),
                          "pct": str(networth.pct_change(now_total, then_total))
                          if networth.pct_change(now_total, then_total) is not None else None}

    latest = max((a.balance_updated_at for a, _ in pairs if a.balance_updated_at), default=None)
    items = sess.execute(select(PlaidItem).where(PlaidItem.status != "removed")).scalars().all()
    attention = [{"id": str(i.id), "institution_name": i.institution_name, "status": i.status,
                  "error_code": i.error_code} for i in items if i.status != "active"]
    return {
        "net_worth": money(net), "assets": money(assets), "liabilities": money(liabilities),
        "change_1m": change, "groups": groups, "as_of": ts(latest),
        "account_count": len([r for r in rows if not r.is_hidden]),
        "items_needing_attention": attention,
    }
