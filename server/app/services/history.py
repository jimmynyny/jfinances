"""Balance history rebuilt from transactions, for the days before tracking began.

Plaid hands over up to two years of transactions at link time, but balance
snapshots only start the day an account is linked. For cash (depository) and
credit card accounts the gap follows from the transactions: walk back from
the earliest real snapshot, undoing each day's posted transactions. Plaid's
sign is positive = money out, so a checking balance was higher before a
debit, and a card's balance owed was lower before a purchase.

Rows go to balance_snapshots with source="derived" and are replaced on every
run. Real snapshots (plaid, carry, manual) are never touched, and every
derived day falls before the first real one. Investments, loans and offline
assets are left alone: their value moves with prices and interest, which
transactions don't record (docs/20-data-model.md, balance_snapshots).
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import Account, BalanceSnapshot, PlaidItem, Transaction

#: Account types whose past balances follow from their transactions.
DERIVABLE_TYPES = ("depository", "credit")
DERIVED = "derived"


def derive_account(sess: Session, acct: Account) -> int:
    """Replace `acct`'s derived snapshots. Returns how many days were written."""
    if acct.kind != "plaid" or acct.type not in DERIVABLE_TYPES:
        return 0
    sess.execute(delete(BalanceSnapshot).where(BalanceSnapshot.account_id == acct.id,
                                               BalanceSnapshot.source == DERIVED))
    anchor = sess.execute(
        select(BalanceSnapshot.as_of, BalanceSnapshot.current_balance)
        .where(BalanceSnapshot.account_id == acct.id, BalanceSnapshot.current_balance.is_not(None))
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
    # Stepping back over a day undoes its transactions: money out (+) returns
    # to a cash account, and comes off what a card owes.
    sign = Decimal(-1) if acct.is_liability else Decimal(1)
    earliest = min(flows)
    bal = Decimal(balance)
    rows = []
    while day >= earliest:  # the last row is the balance before the first known transaction
        bal += sign * Decimal(flows.get(day, 0))
        day -= timedelta(days=1)
        if day not in taken:
            rows.append(BalanceSnapshot(account_id=acct.id, as_of=day, current_balance=bal, source=DERIVED))
    sess.add_all(rows)
    sess.flush()
    return len(rows)


def derive_item(sess: Session, item: PlaidItem) -> int:
    """Rebuild every cash and card account on `item` (after a transactions sync)."""
    return sum(derive_account(sess, a) for a in item.accounts)
