"""Net worth arithmetic. Pure functions over simple rows so they are testable
without a database; the API layer feeds them ORM rows.

Rules (docs/10-architecture.md §6):
- a liability account's balance is what is owed (positive), and is subtracted
- hidden accounts are excluded from totals
- removed items' accounts are excluded from totals but kept for history
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0.00")

GROUPS: list[tuple[str, str]] = [
    ("cash", "Cash"),
    ("investments", "Investments"),
    ("real_estate", "Real estate"),
    ("vehicles", "Vehicles"),
    ("other_assets", "Other assets"),
    ("credit_cards", "Credit cards"),
    ("loans", "Loans"),
    ("other_liabilities", "Other liabilities"),
]
GROUP_LABEL = dict(GROUPS)
ASSET_GROUPS = {"cash", "investments", "real_estate", "vehicles", "other_assets"}


@dataclass(frozen=True)
class AccountRow:
    id: str
    name: str
    kind: str                     # plaid | manual
    type: str | None
    subtype: str | None
    manual_category: str | None
    is_liability: bool
    is_hidden: bool
    current_balance: Decimal | None
    institution_name: str | None = None
    mask: str | None = None
    balance_updated_at: object = None
    item_status: str | None = None
    display_order: int = 0


def group_key(row: AccountRow) -> str:
    if row.kind == "manual":
        return {
            "real_estate": "real_estate",
            "vehicle": "vehicles",
            "cash": "cash",
            "other_asset": "other_assets",
            "other_liability": "other_liabilities",
        }.get(row.manual_category or "", "other_assets")
    t = (row.type or "").lower()
    if t == "depository":
        return "cash"
    if t == "investment" or t == "brokerage":
        return "investments"
    if t == "credit":
        return "credit_cards"
    if t == "loan":
        return "loans"
    return "other_liabilities" if row.is_liability else "other_assets"


def _bal(row: AccountRow) -> Decimal:
    return Decimal(row.current_balance or 0).quantize(Decimal("0.01"))


def totals(rows: Iterable[AccountRow]) -> tuple[Decimal, Decimal, Decimal]:
    """(assets, liabilities, net) over visible rows."""
    assets = ZERO
    liabilities = ZERO
    for r in rows:
        if r.is_hidden:
            continue
        if r.is_liability:
            liabilities += _bal(r)
        else:
            assets += _bal(r)
    return assets, liabilities, assets - liabilities


def grouped(rows: Iterable[AccountRow]) -> list[dict]:
    buckets: dict[str, list[AccountRow]] = {k: [] for k, _ in GROUPS}
    for r in rows:
        buckets[group_key(r)].append(r)
    out = []
    for key, label in GROUPS:
        members = sorted(buckets[key], key=lambda r: (r.display_order, r.name.lower()))
        visible = [r for r in members if not r.is_hidden]
        total = sum((_bal(r) for r in visible), ZERO)
        out.append({
            "key": key,
            "label": label,
            "is_liability": key not in ASSET_GROUPS,
            "total": total,
            "accounts": members,
        })
    return out


def pct_change(now: Decimal, then: Decimal | None) -> Decimal | None:
    if then is None or then == 0:
        return None
    return ((now - then) / abs(then) * 100).quantize(Decimal("0.1"))
