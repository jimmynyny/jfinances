"""What counts as money in and out: the rules every summary shares.

Transfers between the household's own accounts and payments into cards and
loans move money without earning or spending it, so the Transactions summary
and Insights leave them out of In/Out (docs/80 "GET /transactions/summary").
"""
from __future__ import annotations

from sqlalchemy import and_, func, or_

from ..models import Account, Transaction

#: Money moving between the household's own accounts. Counting it would double
#: count: a transfer is an outflow here and an inflow there, and a card payment
#: repays purchases already counted on the card. Excluded from In/Out unless
#: include_transfers=true (docs/80 "GET /transactions/summary").
TRANSFER_PRIMARY = ("TRANSFER_IN", "TRANSFER_OUT")
CARD_PAYMENT_DETAILED = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"

#: Money into a card or loan is a payment from another account, whatever the
#: issuer called it (card payments arrive as INCOME or LOAN_DISBURSEMENTS too). It is the second
#: half of a transfer: left out of household In/Out like card payments, and
#: shown as PAYMENT on the card or loan itself.
PAYMENT_PRIMARY = ("INCOME", "TRANSFER_IN", "LOAN_PAYMENTS", "LOAN_DISBURSEMENTS")
PAYMENT = "PAYMENT"


def is_liability_payment_clause():
    effective = func.coalesce(Transaction.user_category, Transaction.category_primary)
    return and_(Account.is_liability.is_(True), Transaction.amount < 0, effective.in_(PAYMENT_PRIMARY))


def display_category(t: Transaction, a: Account | None) -> str | None:
    """The category a transaction shows: its own, except a payment into a card or loan."""
    cat = t.user_category or t.category_primary
    if a is not None and a.is_liability and t.amount < 0 and cat in PAYMENT_PRIMARY:
        return PAYMENT
    return cat


def is_transfer_clause():
    """SQL predicate for internal transfers, honouring the user's category."""
    effective = func.coalesce(Transaction.user_category, Transaction.category_primary)
    return or_(effective.in_(TRANSFER_PRIMARY),
               and_(Transaction.user_category.is_(None), Transaction.category_detailed == CARD_PAYMENT_DETAILED))
