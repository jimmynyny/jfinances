"""Learned categories: what the person filed a merchant's transactions under,
per account and direction, given to that merchant's new transactions there.

A rule's key is (account, merchant, direction): the merchant as Insights names
it (insights.merchant_key), and money out (a charge) apart from money in (a
refund or a payment), so a refund never takes the purchase's category by
accident. Every category the person sets, one transaction or many, writes the
rule for each key it touches; the latest edit wins, and filing one back under
the bank's category forgets the rule. A rule only fills in: a transaction that
already has the person's category (carried from its pending version, say)
keeps it. Applied to transactions a sync or an import adds; never to ones that
already exist.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import CategoryRule, Transaction
from .insights import merchant_key

Key = tuple[uuid.UUID, str, str]


def direction_of(amount: Decimal | float | int | None) -> str:
    """Plaid's sign: positive is money out."""
    return "out" if Decimal(amount or 0) > 0 else "in"


def key_of(t: Transaction) -> Key:
    return t.account_id, merchant_key(t.merchant_name, t.name)[:300], direction_of(t.amount)


def learn(sess: Session, txs: Iterable[Transaction], category: str | None) -> int:
    """After the person files `txs` under `category` (None: back to the bank's)."""
    keys: dict[Key, Transaction] = {}
    for t in txs:
        keys[key_of(t)] = t
    for (account_id, merchant, way), t in keys.items():
        where = (CategoryRule.account_id == account_id, CategoryRule.merchant == merchant,
                 CategoryRule.direction == way)
        if category is None:
            sess.execute(delete(CategoryRule).where(*where))
            continue
        rule = sess.execute(select(CategoryRule).where(*where)).scalar_one_or_none()
        if rule is None:
            rule = CategoryRule(account_id=account_id, merchant=merchant, direction=way, user_category=category)
            sess.add(rule)
        rule.user_category, rule.learned_from = category, t.id
        rule.updated_at = datetime.now(UTC)
    sess.flush()
    return len(keys)


def load(sess: Session, account_ids: Iterable[uuid.UUID]) -> dict[Key, CategoryRule]:
    ids = list(set(account_ids))
    if not ids:
        return {}
    return {(r.account_id, r.merchant, r.direction): r
            for r in sess.execute(select(CategoryRule).where(CategoryRule.account_id.in_(ids))).scalars()}


def apply(rules: dict[Key, CategoryRule], t: Transaction) -> bool:
    """File a new transaction as the person filed its merchant last time here. True if it did."""
    if t.user_category is not None or not rules:
        return False
    rule = rules.get(key_of(t))
    if rule is None:
        return False
    t.user_category = rule.user_category
    rule.times_applied += 1
    rule.last_applied_at = datetime.now(UTC)
    return True
