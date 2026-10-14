"""Balance history rebuilt from transactions, for the days before tracking began.

Plaid hands over up to two years of transactions at link time, but balance
snapshots only start the day an account is linked. For cash (depository) and
credit card accounts the gap follows from the transactions: walk back from
the earliest real snapshot, undoing each day's posted transactions. Plaid's
sign is positive = money out, so a checking balance was higher before a
debit, and a card's balance owed was lower before a purchase.

Rows go to balance_snapshots with source="derived" and are replaced on every
run. Real snapshots (plaid, carry, manual) are never touched, and every
derived day falls before the first real one. An imported bank export's
end-of-day balances (source="import", services/importer.py) are exact: the walk
back resets to each one it reaches, so years of history don't drift. Loans and
offline assets are left alone: their value moves with interest and prices,
which transactions don't record (docs/20-data-model.md, balance_snapshots).

An investment account is valued only where an imported statement vouches for
its holdings (derive_investment): the statement's own holdings on its last
day, walked back through every trade in its window, each fund priced that day
(performance.price_curve). Elsewhere it is held flat as before.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Account, BalanceSnapshot, Import, InvestmentTransaction, PlaidItem, Security, Transaction

#: Account types whose past balances follow from their transactions.
DERIVABLE_TYPES = ("depository", "credit")
DERIVED = "derived"
IMPORTED = "import"


def derive_account(sess: Session, acct: Account) -> int:
    """Replace `acct`'s derived snapshots. Returns how many days were written."""
    if acct.kind == "plaid" and acct.type == "investment":
        return derive_investment(sess, acct)
    # Balances follow transactions for cash and card accounts, and for an account the
    # bank calls something else that the person counts as cash or a card.
    derivable = acct.type in DERIVABLE_TYPES or acct.group_override in ("cash", "credit_cards")
    if acct.kind != "plaid" or not derivable:
        sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id,
                                                   BalanceSnapshot.source == DERIVED))
        return 0
    sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id,
                                               BalanceSnapshot.source == DERIVED))
    anchor = sess.execute(
        select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance)
        .where(BalanceSnapshot.account_id == acct.id, BalanceSnapshot.current_balance.is_not(None),
               BalanceSnapshot.source != IMPORTED)
        .order_by(BalanceSnapshot.as_of).limit(1)).first()
    if anchor is None:
        return 0
    day, balance = anchor
    flows: dict = dict(sess.execute(
        select(Transaction.date, func.sum(Transaction.amount))
        .where(Transaction.account_id == acct.id, Transaction.pending.is_(False),
               Transaction.removed_at.is_(None), Transaction.date <= day)
        .group_by(Transaction.date)).all())
    if not flows:
        return 0
    # Days that already have a real row (one with no balance sits below the anchor) stay as they are.
    taken = set(sess.execute(select(BalanceSnapshot.as_of).where(BalanceSnapshot.account_id == acct.id)).scalars())
    exact = dict(sess.execute(select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance).where(
        BalanceSnapshot.account_id == acct.id, BalanceSnapshot.source == IMPORTED,
        BalanceSnapshot.current_balance.is_not(None))).all())
    # Stepping back over a day undoes its transactions: money out (+) returns
    # to a cash account, and comes off what a card owes.
    sign = Decimal(-1) if acct.is_liability else Decimal(1)
    earliest = min(flows)
    bal = Decimal(balance)
    rows = []
    while day >= earliest:  # the last row is the balance before the first known transaction
        bal += sign * Decimal(flows.get(day, 0))
        day -= timedelta(days=1)
        if day in exact:  # an imported closing balance is the truth for its day: carry on from it
            bal = Decimal(exact[day])
        elif day not in taken:
            rows.append(BalanceSnapshot(account_id=acct.id, as_of=day, current_balance=bal, source=DERIVED))
    sess.add_all(rows)
    sess.flush()
    return len(rows)


def derive_investment(sess: Session, acct: Account) -> int:
    """An investment account's value on the days its imported statements cover,
    before tracking began. Each statement (newest first; a day an earlier one
    already set keeps that value) starts from the holdings it lists on its last
    day and steps back a day at a time: value the day, then undo its trades (a
    buy's shares come off, its cash comes back). A statement whose walk goes
    negative disagrees with itself and sets nothing."""
    from .performance import price_curve
    sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id,
                                               BalanceSnapshot.source == DERIVED))
    imports = sess.execute(select(Import).where(Import.account_id == acct.id, Import.format == "invofx",
                                                Import.status == "applied", Import.date_from.is_not(None))
                           .order_by(Import.date_to.desc())).scalars().all()
    if not imports:
        return 0
    live = sess.execute(select(func.min(BalanceSnapshot.as_of)).where(
        BalanceSnapshot.account_id == acct.id, BalanceSnapshot.source.in_(("plaid", "carry", "manual")),
        BalanceSnapshot.current_balance.is_not(None))).scalar_one_or_none()
    taken = set(sess.execute(select(BalanceSnapshot.as_of).where(BalanceSnapshot.account_id == acct.id)).scalars())
    filled: dict[date, Decimal] = {}
    for imp in imports:
        anchor = imp.mapping or {}
        if anchor.get("kind") != "investment" or not anchor.get("as_of") or not anchor.get("positions"):
            continue
        end, start = date.fromisoformat(anchor["as_of"]), imp.date_from
        units: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal(0))
        for x in anchor["positions"]:
            units[uuid.UUID(x["security_id"])] += Decimal(x["units"])
        cash = Decimal(anchor["cash"]) if anchor.get("cash") else Decimal(0)
        trades: dict[date, list[InvestmentTransaction]] = defaultdict(list)
        for t in sess.execute(select(InvestmentTransaction).where(
                InvestmentTransaction.account_id == acct.id, InvestmentTransaction.date > start,
                InvestmentTransaction.date <= end)).scalars():
            trades[t.date].append(t)
        ids = set(units) | {t.security_id for day in trades.values() for t in day if t.security_id}
        securities = {s.id: s for s in sess.execute(select(Security).where(Security.id.in_(ids))).scalars()}
        curves = {sid: price_curve(sess, sec, start, end)[0] for sid, sec in securities.items()
                  if not sec.is_cash_equivalent}
        values: dict[date, Decimal] = {}
        day = end
        while day >= start:
            total = cash
            for sid, q in units.items():
                sec = securities.get(sid)
                if q and sec is not None:
                    total += q * (Decimal(1) if sec.is_cash_equivalent else curves.get(sid, {}).get(day, Decimal(0)))
            values[day] = total
            for t in trades.get(day, []):
                sec = securities.get(t.security_id) if t.security_id else None
                if t.quantity and sec is not None:
                    units[sec.id] -= Decimal(t.quantity)
                if t.amount and not (t.type == "buy" and t.subtype == "contribution"):
                    cash += Decimal(t.amount)
            day -= timedelta(days=1)
        if not values or min(values.values()) < 0:
            continue
        for d, v in values.items():
            if d not in filled and d not in taken and (live is None or d < live):
                filled[d] = v
    sess.add_all([BalanceSnapshot(account_id=acct.id, as_of=d, current_balance=v.quantize(Decimal("0.01")),
                                  source=DERIVED) for d, v in filled.items()])
    sess.flush()
    return len(filled)


def derive_item(sess: Session, item: PlaidItem) -> int:
    """Rebuild every cash and card account on `item` (after a transactions sync), and
    every investment account with imported statements."""
    return sum(derive_account(sess, a) for a in item.accounts)
