"""Stop a Plaid login from being connected twice.

Plaid bills every Item monthly from the moment its public token is exchanged
(docs/30-plaid.md, "Cost model"), so this check runs before the exchange, on
the metadata Link hands the browser. A public token that is never exchanged
never becomes a billed Item.

Plaid's recommendation (https://plaid.com/docs/link/duplicate-items/): compare
the institution id and each selected account's name and mask with the Items
already linked.

Verdicts, from the selected accounts' point of view:

- `new`               nothing live at this institution: exchange.
- `same_institution`  a live connection there, none of these accounts on it:
                      a second login (each person's own), billed separately.
                      Exchanged only with `confirm="new_login"`.
- `overlap`           some of these accounts are already connected (a joint
                      account under both logins): they would show up twice.
                      Exchanged only with `confirm="overlap"`.
- `duplicate`         every selected account is already connected, or a
                      connection there is still fetching its first accounts.
                      Never exchanged: the existing connection is the way in
                      (Add accounts, Re-link).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import Account, PlaidItem

Verdict = Literal["new", "same_institution", "overlap", "duplicate"]

#: The `confirm` value that lets each verdict through. `duplicate` has none.
CONFIRMS: dict[str, str] = {"same_institution": "new_login", "overlap": "overlap"}


@dataclass
class LinkCheck:
    verdict: Verdict
    institution: str | None = None
    #: Live (not unlinked) connections at the same institution.
    items: list[PlaidItem] = field(default_factory=list)
    #: Already-connected accounts that were selected again.
    overlapping: list[Account] = field(default_factory=list)
    #: A connection there has no accounts yet: its first fetch is still pending.
    pending: bool = False

    def allows(self, confirm: str | None) -> bool:
        return self.verdict == "new" or (confirm is not None and CONFIRMS.get(self.verdict) == confirm)


def _norm(v: Any) -> str:
    return " ".join(str(v or "").lower().split())


def same_account(acct: Account, picked: dict[str, Any]) -> bool:
    """Plaid's name (not a rename in jfinances) and mask; subtype stands in
    for the name when the institution renamed the account."""
    plaid_name = _norm((acct.raw or {}).get("name") or acct.name)
    name, mask = _norm(picked.get("name")), picked.get("mask") or None
    same_subtype = _norm(acct.subtype) == _norm(picked.get("subtype"))
    if acct.mask and mask:
        return acct.mask == mask and (plaid_name == name or same_subtype)
    return bool(name) and plaid_name == name and same_subtype


def check_new_link(sess: Session, metadata: dict[str, Any] | None) -> LinkCheck:
    meta = metadata or {}
    inst = meta.get("institution") or {}
    inst_id = inst.get("institution_id")
    if not inst_id:
        return LinkCheck("new")
    items = list(sess.execute(
        select(PlaidItem).options(selectinload(PlaidItem.accounts))
        .where(PlaidItem.institution_id == inst_id, PlaidItem.status != "removed")
        .order_by(PlaidItem.created_at)).scalars())
    if not items:
        return LinkCheck("new")
    name = inst.get("name") or items[0].institution_name
    live = [a for it in items for a in it.accounts if a.closed_at is None]
    picked = [p for p in meta.get("accounts") or [] if isinstance(p, dict)]
    already = [p for p in picked if any(same_account(a, p) for a in live)]
    overlapping = [a for a in live if any(same_account(a, p) for p in picked)]
    pending = any(not it.accounts for it in items)
    if pending or (picked and len(already) == len(picked)):
        verdict: Verdict = "duplicate"
    elif already:
        verdict = "overlap"
    else:
        verdict = "same_institution"
    return LinkCheck(verdict, name, items, overlapping, pending)


def label(a: Account) -> str:
    return f"{a.name} ··{a.mask}" if a.mask else a.name


def message(check: LinkCheck) -> str:
    inst = check.institution or "this institution"
    names = ", ".join(label(a) for a in check.overlapping)
    one = len(check.overlapping) == 1
    are, they, them = ("is", "it", "it") if one else ("are", "they", "them")
    if check.verdict == "duplicate" and check.pending:
        return (f"Your {inst} connection is still loading its accounts. Give it a minute and check "
                "Settings before connecting again. Nothing was added, and this attempt isn't billed.")
    if check.verdict == "duplicate":
        return (f"{names} {are} already connected through your {inst} connection. Nothing was added, and "
                "this attempt isn't billed. To bring in another account from that login, use "
                "Add accounts on it in Settings.")
    if check.verdict == "overlap":
        return (f"{names} {are} already connected through your {inst} connection. Connecting this login "
                f"anyway adds a second {inst} connection, billed separately, and {they} would show up twice. "
                f"Better: connect again and leave {them} unticked.")
    n = sum(len([a for a in it.accounts if a.closed_at is None]) for it in check.items)
    return (f"You already have a {inst} connection ({n} account{'' if n == 1 else 's'}). If this is a "
            f"different person's login, connect it as a second {inst} connection, billed separately. If "
            "it's the same login, cancel and use Add accounts on the existing connection instead.")
