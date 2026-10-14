from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import Account, BalanceSnapshot, PlaidItem
from ..services import networth
from ..services.trends import balance_trends
from ..services.wealth import balances_on
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


def _balances_then(sess: Session, accounts: list[Account], day) -> tuple[dict[str, Decimal], set[str]]:
    """Each account's balance on `day` as the net worth chart draws it (the latest
    snapshot on or before the day, else its first one, held flat before tracking
    began), and the accounts that were tracked by then. Comparing today's full net
    worth with only the tracked accounts' month-ago total made a month's change
    out of every account linked since."""
    ids = [a.id for a in accounts]
    tracked = {str(aid) for aid in sess.execute(
        select(BalanceSnapshot.account_id).where(BalanceSnapshot.account_id.in_(ids), BalanceSnapshot.as_of <= day)
        .distinct()).scalars()}
    if not tracked:
        return {}, tracked
    return {str(aid): v[day] for aid, v in balances_on(sess, accounts, [day]).items()}, tracked


@router.get("/overview")
def overview(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    pairs = _rows(sess)
    rows = [r for _, r in pairs]
    by_id = {str(a.id): a for a, _ in pairs}
    assets, liabilities, net = networth.totals(rows)
    month_ago = (datetime.now(UTC) - timedelta(days=30)).date()
    then_by_acct, tracked = _balances_then(sess, [a for a, _ in pairs], month_ago)
    change = None
    if tracked:
        _, _, then = networth.totals(replace(r, current_balance=then_by_acct.get(r.id)) for r in rows)
        pct = networth.pct_change(net, then)
        change = {"amount": money(net - then), "pct": str(pct) if pct is not None else None,
                  "since": month_ago.isoformat()}

    trends = balance_trends(sess, [a.id for a, _ in pairs], current={a.id: a.current_balance for a, _ in pairs})
    groups = []
    for g in networth.grouped(rows):
        g_then = None
        groups.append({
            "key": g["key"], "label": g["label"], "is_liability": g["is_liability"],
            "total": money(g["total"]), "change_1m": g_then,
            "accounts": [{**account_json(by_id[r.id]),
                          "trend": [money(v) for v in trends.get(by_id[r.id].id, [])]} for r in g["accounts"]],
        })
    # Per-group month change, on the same month-ago balances.
    for g in groups:
        visible = [a for a in g["accounts"] if not a["is_hidden"]]
        if not any(a["id"] in tracked for a in visible):
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
