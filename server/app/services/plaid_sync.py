"""Everything that moves data from Plaid into our tables.

Each function takes an open session and a PlaidItem and is safe to re-run:
every write is an upsert keyed on the Plaid id. Handlers in `jobs/` are thin
wrappers that look up the item and call these.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..crypto import decrypt, encrypt
from ..models import (
    Account,
    BalanceSnapshot,
    Holding,
    InvestmentTransaction,
    Liability,
    PlaidItem,
    Security,
    Transaction,
    is_liability_for,
)
from ..plaid_client import PlaidClient, PlaidError, plaid

log = logging.getLogger(__name__)

LOGIN_REQUIRED_CODES = {"ITEM_LOGIN_REQUIRED", "INVALID_CREDENTIALS", "INVALID_MFA",
                        "USER_SETUP_REQUIRED", "ACCESS_NOT_GRANTED", "INSUFFICIENT_CREDENTIALS"}


def _d(v: Any) -> Decimal | None:
    if v is None:
        return None
    return Decimal(str(v))


def _date(v: Any) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def access_token_for(item: PlaidItem) -> str:
    return decrypt(item.access_token_enc, settings().encryption_key_bytes)


def store_access_token(item: PlaidItem, token: str) -> None:
    item.access_token_enc = encrypt(token, settings().encryption_key_bytes)


def mark_item_error(item: PlaidItem, err: PlaidError) -> None:
    item.error_code = err.error_code
    item.error_message = (err.body.get("error_message") or "")[:1000]
    if err.error_code in LOGIN_REQUIRED_CODES:
        item.status = "login_required"
    elif err.error_code == "ITEM_NOT_FOUND":
        item.status = "removed"
        item.removed_at = item.removed_at or datetime.now(UTC)
    else:
        item.status = "error"
    log.warning("item %s -> %s (%s)", item.item_id, item.status, err.error_code,
                extra={"item_id": item.item_id})


def clear_item_error(item: PlaidItem) -> None:
    if item.status in ("login_required", "error", "pending_expiration"):
        item.status = "active"
    item.error_code = None
    item.error_message = None


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def upsert_accounts(sess: Session, item: PlaidItem, accounts: list[dict[str, Any]],
                    *, snapshot: bool = True) -> list[Account]:
    existing = {a.plaid_account_id: a for a in item.accounts}
    seen: set[str] = set()
    out: list[Account] = []
    now = datetime.now(UTC)
    for raw in accounts:
        pid = raw["account_id"]
        seen.add(pid)
        acct = existing.get(pid)
        if acct is None:
            acct = Account(item_id=item.id, plaid_account_id=pid, kind="plaid",
                           name=raw.get("name") or raw.get("official_name") or "Account")
            sess.add(acct)
            item.accounts.append(acct)
        bal = raw.get("balances") or {}
        acct.name = acct.name or raw.get("name") or "Account"
        if acct.raw is None or acct.name == (acct.raw.get("name") if acct.raw else None):
            acct.name = raw.get("name") or acct.name     # follow Plaid until the user renames
        acct.official_name = raw.get("official_name")
        acct.mask = raw.get("mask")
        acct.type = raw.get("type")
        acct.subtype = raw.get("subtype")
        acct.iso_currency = bal.get("iso_currency_code") or bal.get("unofficial_currency_code") or "USD"
        acct.current_balance = _d(bal.get("current"))
        acct.available_balance = _d(bal.get("available"))
        acct.credit_limit = _d(bal.get("limit"))
        acct.balance_updated_at = now
        acct.is_liability = is_liability_for("plaid", acct.type, None)
        acct.raw = raw
        if acct.closed_at is not None:
            acct.closed_at = None
        out.append(acct)
    for pid, acct in existing.items():
        if pid not in seen and acct.closed_at is None:
            acct.closed_at = now
            log.info("account %s no longer returned by Plaid; marked closed", acct.id)
    sess.flush()
    if snapshot:
        write_snapshots(sess, out, source="plaid")
    return out


def write_snapshots(sess: Session, accounts: list[Account], *, source: str,
                    as_of: date | None = None) -> int:
    as_of = as_of or datetime.now(UTC).date()
    n = 0
    for acct in accounts:
        row = sess.execute(select(BalanceSnapshot).where(
            BalanceSnapshot.account_id == acct.id, BalanceSnapshot.as_of == as_of)).scalar_one_or_none()
        if row is None:
            sess.add(BalanceSnapshot(account_id=acct.id, as_of=as_of, source=source,
                                     current_balance=acct.current_balance,
                                     available_balance=acct.available_balance))
        else:
            # Same day, fresher number: overwrite unless a manual entry is being
            # replaced by a mere carry-forward.
            if not (row.source == "manual" and source == "carry"):
                row.current_balance = acct.current_balance
                row.available_balance = acct.available_balance
                row.source = source
        n += 1
    sess.flush()
    return n


def refresh_accounts(sess: Session, item: PlaidItem, client: PlaidClient | None = None,
                     *, realtime: bool = False) -> list[Account]:
    client = client or plaid()
    token = access_token_for(item)
    try:
        data = client.accounts_balance_get(token) if realtime else client.accounts_get(token)
    except PlaidError as e:
        mark_item_error(item, e)
        raise
    clear_item_error(item)
    _absorb_item_meta(item, data.get("item"))
    return upsert_accounts(sess, item, data.get("accounts", []))


def _absorb_item_meta(item: PlaidItem, meta: dict[str, Any] | None) -> None:
    if not meta:
        return
    if meta.get("institution_id") and not item.institution_id:
        item.institution_id = meta["institution_id"]
    if meta.get("institution_name"):
        item.institution_name = meta["institution_name"]
    if meta.get("consent_expiration_time"):
        item.consent_expires_at = datetime.fromisoformat(
            meta["consent_expiration_time"].replace("Z", "+00:00"))
    if meta.get("products"):
        item.products = list(meta["products"])


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def sync_transactions(sess: Session, item: PlaidItem, client: PlaidClient | None = None,
                      *, max_pages: int = 200) -> dict[str, int]:
    """Cursor-based sync. The cursor is persisted only after every page of
    this round has been applied, as Plaid recommends. On
    TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION we restart from the original
    cursor."""
    client = client or plaid()
    token = access_token_for(item)
    original_cursor = item.transactions_cursor
    counts = {"added": 0, "modified": 0, "removed": 0, "pages": 0}

    for attempt in range(3):
        cursor = original_cursor
        added: list[dict] = []
        modified: list[dict] = []
        removed: list[dict] = []
        status = None
        try:
            for _ in range(max_pages):
                data = client.transactions_sync(token, cursor)
                counts["pages"] += 1
                added += data.get("added", [])
                modified += data.get("modified", [])
                removed += data.get("removed", [])
                status = data.get("transactions_update_status") or status
                cursor = data.get("next_cursor") or cursor
                if not data.get("has_more"):
                    break
        except PlaidError as e:
            if e.error_code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" and attempt < 2:
                log.info("sync mutation during pagination; restarting", extra={"item_id": item.item_id})
                continue
            mark_item_error(item, e)
            raise
        break

    accounts = {a.plaid_account_id: a for a in item.accounts}
    missing = {t["account_id"] for t in added + modified} - set(accounts)
    if missing:
        # New accounts appeared (update mode added one). Pull accounts first.
        refresh_accounts(sess, item, client)
        accounts = {a.plaid_account_id: a for a in item.accounts}

    for raw in added + modified:
        _upsert_transaction(sess, accounts, raw)
    counts["added"] = len(added)
    counts["modified"] = len(modified)
    if removed:
        ids = [r["transaction_id"] for r in removed]
        rows = sess.execute(select(Transaction).where(Transaction.plaid_transaction_id.in_(ids))).scalars()
        now = datetime.now(UTC)
        for row in rows:
            row.removed_at = now
            counts["removed"] += 1

    item.transactions_cursor = cursor
    item.transactions_status = status
    item.last_synced_at = datetime.now(UTC)
    clear_item_error(item)
    sess.flush()
    log.info("synced %s: +%d ~%d -%d in %d pages", item.item_id, counts["added"],
             counts["modified"], counts["removed"], counts["pages"], extra={"item_id": item.item_id})
    return counts


def _upsert_transaction(sess: Session, accounts: dict[str, Account], raw: dict[str, Any]) -> None:
    acct = accounts.get(raw["account_id"])
    if acct is None:
        log.warning("transaction for unknown account %s skipped", raw["account_id"])
        return
    pid = raw["transaction_id"]
    row = sess.execute(select(Transaction).where(Transaction.plaid_transaction_id == pid)).scalar_one_or_none()
    if row is None:
        row = Transaction(account_id=acct.id, plaid_transaction_id=pid, date=_date(raw["date"]),
                          amount=_d(raw["amount"]) or Decimal("0"), name=raw.get("name") or "")
        sess.add(row)
    pfc = raw.get("personal_finance_category") or {}
    row.account_id = acct.id
    row.date = _date(raw["date"])
    row.authorized_date = _date(raw.get("authorized_date"))
    row.amount = _d(raw["amount"]) or Decimal("0")
    row.iso_currency = raw.get("iso_currency_code") or raw.get("unofficial_currency_code")
    row.name = raw.get("name") or row.name
    row.merchant_name = raw.get("merchant_name")
    row.logo_url = raw.get("logo_url")
    row.pending = bool(raw.get("pending"))
    row.pending_transaction_id = raw.get("pending_transaction_id")
    row.category_primary = pfc.get("primary")
    row.category_detailed = pfc.get("detailed")
    row.payment_channel = raw.get("payment_channel")
    row.removed_at = None
    row.raw = raw
    # When a pending transaction posts, Plaid removes the pending one and adds
    # a new one carrying pending_transaction_id. Carry user edits across.
    if row.pending_transaction_id and (row.user_category is None and row.notes is None):
        prev = sess.execute(select(Transaction).where(
            Transaction.plaid_transaction_id == row.pending_transaction_id)).scalar_one_or_none()
        if prev is not None:
            row.user_category, row.notes = prev.user_category, prev.notes


# ---------------------------------------------------------------------------
# Investments
# ---------------------------------------------------------------------------
def _upsert_securities(sess: Session, securities: list[dict[str, Any]]) -> dict[str, Security]:
    out: dict[str, Security] = {}
    for raw in securities:
        pid = raw["security_id"]
        row = sess.execute(select(Security).where(Security.plaid_security_id == pid)).scalar_one_or_none()
        if row is None:
            row = Security(plaid_security_id=pid)
            sess.add(row)
        row.ticker = raw.get("ticker_symbol")
        row.name = raw.get("name")
        row.type = raw.get("type")
        row.is_cash_equivalent = bool(raw.get("is_cash_equivalent"))
        row.close_price = _d(raw.get("close_price"))
        row.close_price_as_of = _date(raw.get("close_price_as_of"))
        row.iso_currency = raw.get("iso_currency_code")
        row.raw = raw
        out[pid] = row
    sess.flush()
    return out


def refresh_investments(sess: Session, item: PlaidItem, client: PlaidClient | None = None) -> dict[str, int]:
    client = client or plaid()
    token = access_token_for(item)
    try:
        hold = client.investments_holdings_get(token)
    except PlaidError as e:
        if e.error_code in ("PRODUCTS_NOT_SUPPORTED", "PRODUCT_NOT_READY", "NO_INVESTMENT_ACCOUNTS"):
            log.info("no investments for %s (%s)", item.item_id, e.error_code)
            return {"holdings": 0, "transactions": 0}
        mark_item_error(item, e)
        raise
    _absorb_item_meta(item, hold.get("item"))
    accounts = {a.plaid_account_id: a for a in upsert_accounts(sess, item, hold.get("accounts", []))}
    securities = _upsert_securities(sess, hold.get("securities", []))

    n_hold = 0
    seen: set[tuple] = set()
    for raw in hold.get("holdings", []):
        acct = accounts.get(raw["account_id"])
        sec = securities.get(raw["security_id"])
        if acct is None or sec is None:
            continue
        key = (acct.id, sec.id)
        seen.add(key)
        row = sess.execute(select(Holding).where(Holding.account_id == acct.id,
                                                 Holding.security_id == sec.id)).scalar_one_or_none()
        if row is None:
            row = Holding(account_id=acct.id, security_id=sec.id)
            sess.add(row)
        row.quantity = _d(raw.get("quantity"))
        row.cost_basis = _d(raw.get("cost_basis"))
        row.institution_price = _d(raw.get("institution_price"))
        row.institution_price_as_of = _date(raw.get("institution_price_as_of"))
        row.institution_value = _d(raw.get("institution_value"))
        row.iso_currency = raw.get("iso_currency_code")
        row.raw = raw
        n_hold += 1
    # Holdings Plaid no longer reports were sold; drop them.
    for row in sess.execute(select(Holding).where(Holding.account_id.in_([a.id for a in accounts.values()]))).scalars():
        if (row.account_id, row.security_id) not in seen:
            sess.delete(row)
    sess.flush()

    # Transactions: 730 days the first time, then a 30-day overlap.
    end = datetime.now(UTC).date()
    start = end - timedelta(days=settings().plaid_days_requested if item.investments_synced_at is None else 30)
    n_tx = 0
    offset = 0
    while True:
        try:
            data = client.investments_transactions_get(token, start.isoformat(), end.isoformat(), offset=offset)
        except PlaidError as e:
            if e.error_code in ("PRODUCTS_NOT_SUPPORTED", "PRODUCT_NOT_READY"):
                break
            mark_item_error(item, e)
            raise
        securities.update(_upsert_securities(sess, data.get("securities", [])))
        batch = data.get("investment_transactions", [])
        for raw in batch:
            acct = accounts.get(raw["account_id"])
            if acct is None:
                continue
            pid = raw["investment_transaction_id"]
            row = sess.execute(select(InvestmentTransaction).where(
                InvestmentTransaction.plaid_investment_transaction_id == pid)).scalar_one_or_none()
            if row is None:
                row = InvestmentTransaction(account_id=acct.id, plaid_investment_transaction_id=pid,
                                            date=_date(raw["date"]))
                sess.add(row)
            sec = securities.get(raw.get("security_id") or "")
            row.security_id = sec.id if sec else None
            row.date = _date(raw["date"])
            row.name = raw.get("name")
            row.type = raw.get("type")
            row.subtype = raw.get("subtype")
            row.quantity = _d(raw.get("quantity"))
            row.amount = _d(raw.get("amount"))
            row.price = _d(raw.get("price"))
            row.fees = _d(raw.get("fees"))
            row.iso_currency = raw.get("iso_currency_code")
            row.raw = raw
            n_tx += 1
        offset += len(batch)
        if offset >= int(data.get("total_investment_transactions") or 0) or not batch:
            break
    item.investments_synced_at = datetime.now(UTC)
    clear_item_error(item)
    sess.flush()
    return {"holdings": n_hold, "transactions": n_tx}


# ---------------------------------------------------------------------------
# Liabilities
# ---------------------------------------------------------------------------
def refresh_liabilities(sess: Session, item: PlaidItem, client: PlaidClient | None = None) -> int:
    client = client or plaid()
    token = access_token_for(item)
    try:
        data = client.liabilities_get(token)
    except PlaidError as e:
        if e.error_code in ("PRODUCTS_NOT_SUPPORTED", "PRODUCT_NOT_READY", "NO_LIABILITY_ACCOUNTS"):
            log.info("no liabilities for %s (%s)", item.item_id, e.error_code)
            return 0
        mark_item_error(item, e)
        raise
    _absorb_item_meta(item, data.get("item"))
    accounts = {a.plaid_account_id: a for a in upsert_accounts(sess, item, data.get("accounts", []))}
    liab = data.get("liabilities") or {}
    n = 0
    for kind, rows in (("credit", liab.get("credit") or []),
                       ("mortgage", liab.get("mortgage") or []),
                       ("student", liab.get("student") or [])):
        for raw in rows:
            acct = accounts.get(raw.get("account_id") or "")
            if acct is None:
                continue
            row = sess.execute(select(Liability).where(Liability.account_id == acct.id)).scalar_one_or_none()
            if row is None:
                row = Liability(account_id=acct.id, kind=kind)
                sess.add(row)
            row.kind = kind
            row.raw = raw
            if kind == "credit":
                aprs = raw.get("aprs") or []
                purchase = next((a for a in aprs if a.get("apr_type") == "purchase_apr"), aprs[0] if aprs else None)
                row.interest_rate_pct = _d(purchase.get("apr_percentage")) if purchase else None
                row.interest_rate_type = purchase.get("apr_type") if purchase else None
                row.minimum_payment = _d(raw.get("minimum_payment_amount"))
                row.last_statement_balance = _d(raw.get("last_statement_balance"))
                row.last_statement_date = _date(raw.get("last_statement_issue_date"))
                row.is_overdue = raw.get("is_overdue")
            else:
                rate = raw.get("interest_rate") or {}
                row.interest_rate_pct = _d(rate.get("percentage"))
                row.interest_rate_type = rate.get("type")
                row.next_payment_amount = _d(raw.get("next_monthly_payment") or raw.get("minimum_payment_amount"))
                row.minimum_payment = _d(raw.get("minimum_payment_amount") or raw.get("next_monthly_payment"))
                row.origination_date = _date(raw.get("origination_date"))
                row.origination_principal = _d(raw.get("origination_principal_amount"))
                row.loan_term = raw.get("loan_term")
                row.maturity_date = _date(raw.get("maturity_date"))
                row.is_overdue = raw.get("is_overdue")
            row.next_payment_due_date = _date(raw.get("next_payment_due_date"))
            row.last_payment_amount = _d(raw.get("last_payment_amount"))
            row.last_payment_date = _date(raw.get("last_payment_date"))
            n += 1
    item.liabilities_synced_at = datetime.now(UTC)
    clear_item_error(item)
    sess.flush()
    return n


# ---------------------------------------------------------------------------
# Link / exchange / remove
# ---------------------------------------------------------------------------
def create_item_from_public_token(sess: Session, *, public_token: str, user_id,
                                  metadata: dict[str, Any] | None = None,
                                  client: PlaidClient | None = None) -> PlaidItem:
    client = client or plaid()
    ex = client.item_public_token_exchange(public_token)
    access_token = ex["access_token"]
    item_id = ex["item_id"]
    item = sess.execute(select(PlaidItem).where(PlaidItem.item_id == item_id)).scalar_one_or_none()
    inst = (metadata or {}).get("institution") or {}
    if item is None:
        item = PlaidItem(item_id=item_id, created_by=user_id, products=[],  # filled from /accounts/get item meta
                         access_token_enc=b"", institution_id=inst.get("institution_id"),
                         institution_name=inst.get("name"))
        sess.add(item)
    store_access_token(item, access_token)
    item.status = "active"
    item.removed_at = None
    item.error_code = None
    item.error_message = None
    sess.flush()
    refresh_accounts(sess, item, client)
    if not item.institution_name and item.institution_id:
        try:
            item.institution_name = client.institutions_get_by_id(item.institution_id)["institution"]["name"]
        except PlaidError:
            pass
    return item


def remove_item(sess: Session, item: PlaidItem, client: PlaidClient | None = None) -> None:
    client = client or plaid()
    try:
        client.item_remove(access_token_for(item))
    except PlaidError as e:
        if e.error_code != "ITEM_NOT_FOUND":
            raise
    item.status = "removed"
    item.removed_at = datetime.now(UTC)
    # Keep the ciphertext column non-null but useless.
    item.access_token_enc = encrypt("removed", settings().encryption_key_bytes)
    for a in item.accounts:
        a.closed_at = a.closed_at or datetime.now(UTC)
    sess.flush()
