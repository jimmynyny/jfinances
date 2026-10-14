"""ORM models. The schema contract is docs/20-data-model.md; keep them in step.

Conventions
- `id` is a uuid4 primary key everywhere.
- Money is numeric(18,2). Quantities (shares) are numeric(24,8).
- Timestamps are timestamptz, UTC.
- Plaid payloads are kept whole in `raw` jsonb so fields can be backfilled
  later without another API call.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

MONEY = Numeric(18, 2)
QTY = Numeric(24, 8)
RATE = Numeric(9, 4)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")  # owner | member
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Overview's grid: 1, 2 or 3 columns. Null until the dashboard is first
    #: read, which seeds the default widgets (so an emptied one stays empty).
    dashboard_columns: Mapped[int | None] = mapped_column(Integer)


class ApiToken(TimestampMixin, Base):
    """A phone's credential, minted by the link flow (auth/mobile.py). Only the
    SHA-256 is stored."""

    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class MobileLinkCode(TimestampMixin, Base):
    """A two-minute code minted behind Access and traded once by the phone
    for an `api_tokens` row (auth/mobile.py). Only the SHA-256 is stored."""

    __tablename__ = "mobile_link_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_name: Mapped[str | None] = mapped_column(String(120))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------------------------------------------------------------------------
# Plaid items and accounts
# ---------------------------------------------------------------------------
ITEM_STATUSES = ("active", "login_required", "error", "pending_expiration", "removed")


class PlaidItem(TimestampMixin, Base):
    __tablename__ = "plaid_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    institution_id: Mapped[str | None] = mapped_column(String(40))
    institution_name: Mapped[str | None] = mapped_column(String(200))
    access_token_enc: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    transactions_cursor: Mapped[str | None] = mapped_column(Text)
    # NOT_READY | INITIAL_UPDATE_COMPLETE | HISTORICAL_UPDATE_COMPLETE
    transactions_status: Mapped[str | None] = mapped_column(String(40))
    investments_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    liabilities_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set by ITEM/NEW_ACCOUNTS_AVAILABLE; cleared when update mode finishes.
    new_accounts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    products: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    accounts: Mapped[list[Account]] = relationship(back_populates="item")

    def has_product(self, product: str) -> bool:
        """True when Plaid initialised `product` on this Item. Calling a
        product endpoint for an Item without it makes Plaid try to add the
        product, which starts billing for it, so every job checks first."""
        return product in (self.products or [])


ACCOUNT_KINDS = ("plaid", "manual")
MANUAL_CATEGORIES = ("real_estate", "vehicle", "cash", "other_asset", "other_liability")
#: Manual categories a loan can be secured by (Account.secured_by_id).
SECURABLE_CATEGORIES = ("real_estate", "vehicle", "other_asset")
LIABILITY_TYPES = {"credit", "loan"}


def is_liability_for(kind: str, type_: str | None, manual_category: str | None) -> bool:
    if kind == "manual":
        return manual_category == "other_liability"
    return (type_ or "") in LIABILITY_TYPES


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (Index("ix_accounts_item", "item_id"), Index("ix_accounts_secured_by", "secured_by_id"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plaid_items.id", ondelete="CASCADE"))
    plaid_account_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(10), nullable=False, default="plaid")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    official_name: Mapped[str | None] = mapped_column(String(300))
    mask: Mapped[str | None] = mapped_column(String(8))
    type: Mapped[str | None] = mapped_column(String(40))      # depository | credit | loan | investment | other
    subtype: Mapped[str | None] = mapped_column(String(60))
    manual_category: Mapped[str | None] = mapped_column(String(24))
    iso_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    current_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    available_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_liability: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: A business account (Daedalus TCG): Insights keep it out of personal numbers.
    is_business: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Where the account counts when its type alone would put it elsewhere (a
    #: networth.GROUPS key, set by the person); it also decides is_liability.
    group_override: Mapped[str | None] = mapped_column(String(24))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONB)
    #: The offline asset a loan is secured by (a mortgage's home, a car loan's
    #: car), set by hand. Several loans can share one asset (mortgage + HELOC).
    secured_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))

    item: Mapped[PlaidItem | None] = relationship(back_populates="accounts")


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"
    __table_args__ = (
        UniqueConstraint("account_id", "as_of", name="uq_balance_snapshots_account_day"),
        Index("ix_balance_snapshots_as_of", "as_of"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    current_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    available_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # plaid | manual | carry
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_account_date", "account_id", "date"),
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_category", "category_primary"),
        Index("ix_transactions_import", "import_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    #: None for a row imported from a bank export (`source` "import").
    plaid_transaction_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="plaid", server_default="plaid")
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    authorized_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)  # Plaid sign: positive = money out
    iso_currency: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(300))
    logo_url: Mapped[str | None] = mapped_column(Text)
    pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_transaction_id: Mapped[str | None] = mapped_column(String(80))
    category_primary: Mapped[str | None] = mapped_column(String(80))
    category_detailed: Mapped[str | None] = mapped_column(String(120))
    payment_channel: Mapped[str | None] = mapped_column(String(40))
    user_category: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)
    #: The person's say: True business, False personal, None as its account (accounts.is_business).
    business: Mapped[bool | None] = mapped_column(Boolean)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONB)


class Import(TimestampMixin, Base):
    """One uploaded bank export (services/importer.py): the account, the file
    (its name and hash, never its contents), how its columns were read, and what
    came of its rows. Undoing it removes what it added."""
    __tablename__ = "imports"
    __table_args__ = (Index("ix_imports_account", "account_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)  # csv | ofx | venmo | invofx
    mapping: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    date_from: Mapped[date | None] = mapped_column(Date)
    date_to: Mapped[date | None] = mapped_column(Date)
    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    balances_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="applied")  # applied | undone
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportRow(Base):
    """The ledger: every row an import added or matched, by its permanent
    fingerprint (statement.fingerprint), so the same row in a later or
    overlapping export is never added twice. `status`: added (it is in
    transactions), matched (the connection already had it), superseded (added,
    then the connection sent it too, so the imported copy was retired)."""
    __tablename__ = "import_rows"
    __table_args__ = (UniqueConstraint("account_id", "fingerprint", name="uq_import_rows_account_fingerprint"),
                      Index("ix_import_rows_import", "import_id"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("imports.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transactions.id", ondelete="SET NULL"))
    matched_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ImportProfile(TimestampMixin, Base):
    """A bank's export layout, recognized by its header (statement.signature):
    the confirmed column mapping, and the account it was last imported into."""
    __tablename__ = "import_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    signature: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Investments
# ---------------------------------------------------------------------------
class Security(TimestampMixin, Base):
    __tablename__ = "securities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    plaid_security_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[str | None] = mapped_column(String(300))
    type: Mapped[str | None] = mapped_column(String(40))
    is_cash_equivalent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    close_price: Mapped[Decimal | None] = mapped_column(QTY)
    close_price_as_of: Mapped[date | None] = mapped_column(Date)
    iso_currency: Mapped[str | None] = mapped_column(String(3))
    raw: Mapped[dict | None] = mapped_column(JSONB)


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (UniqueConstraint("account_id", "security_id", name="uq_holdings_account_security"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    security_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(QTY)
    cost_basis: Mapped[Decimal | None] = mapped_column(MONEY)
    institution_price: Mapped[Decimal | None] = mapped_column(QTY)
    institution_price_as_of: Mapped[date | None] = mapped_column(Date)
    institution_value: Mapped[Decimal | None] = mapped_column(MONEY)
    iso_currency: Mapped[str | None] = mapped_column(String(3))
    raw: Mapped[dict | None] = mapped_column(JSONB)

    security: Mapped[Security] = relationship()


class InvestmentTransaction(TimestampMixin, Base):
    __tablename__ = "investment_transactions"
    __table_args__ = (Index("ix_invtx_account_date", "account_id", "date"), Index("ix_invtx_import", "import_id"))

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    #: None for a row imported from an investment statement (`source` "import").
    plaid_investment_transaction_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="plaid", server_default="plaid")
    import_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"))
    security_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("securities.id", ondelete="SET NULL"))
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str | None] = mapped_column(String(300))
    type: Mapped[str | None] = mapped_column(String(40))
    subtype: Mapped[str | None] = mapped_column(String(60))
    quantity: Mapped[Decimal | None] = mapped_column(QTY)
    amount: Mapped[Decimal | None] = mapped_column(MONEY)
    price: Mapped[Decimal | None] = mapped_column(QTY)
    fees: Mapped[Decimal | None] = mapped_column(MONEY)
    iso_currency: Mapped[str | None] = mapped_column(String(3))
    raw: Mapped[dict | None] = mapped_column(JSONB)


# ---------------------------------------------------------------------------
# Liabilities
# ---------------------------------------------------------------------------
class Liability(TimestampMixin, Base):
    __tablename__ = "liabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # credit | mortgage | student
    interest_rate_pct: Mapped[Decimal | None] = mapped_column(RATE)
    interest_rate_type: Mapped[str | None] = mapped_column(String(20))
    next_payment_due_date: Mapped[date | None] = mapped_column(Date)
    minimum_payment: Mapped[Decimal | None] = mapped_column(MONEY)
    next_payment_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    last_payment_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    last_payment_date: Mapped[date | None] = mapped_column(Date)
    last_statement_balance: Mapped[Decimal | None] = mapped_column(MONEY)
    last_statement_date: Mapped[date | None] = mapped_column(Date)
    is_overdue: Mapped[bool | None] = mapped_column(Boolean)
    origination_date: Mapped[date | None] = mapped_column(Date)
    origination_principal: Mapped[Decimal | None] = mapped_column(MONEY)
    loan_term: Mapped[str | None] = mapped_column(String(40))
    maturity_date: Mapped[date | None] = mapped_column(Date)
    raw: Mapped[dict | None] = mapped_column(JSONB)


class AccountTerms(TimestampMixin, Base):
    """What the person told us about an account that its bank doesn't report:
    a loan's rate, original amount, start, term and monthly payment (principal
    and interest; escrow apart), a card's APR, limit and statement day, a
    savings rate. Bank-reported values win wherever both exist; these fill the
    gaps, and the rest follows from them (services/terms.py)."""
    __tablename__ = "account_terms"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    #: A loan's rate, a card's purchase APR, a savings account's APY.
    interest_rate_pct: Mapped[Decimal | None] = mapped_column(RATE)
    rate_type: Mapped[str | None] = mapped_column(String(20))  # fixed | variable
    original_principal: Mapped[Decimal | None] = mapped_column(MONEY)
    origination_date: Mapped[date | None] = mapped_column(Date)
    term_months: Mapped[int | None] = mapped_column(Integer)
    payment_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    escrow_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    payment_day: Mapped[int | None] = mapped_column(Integer)
    statement_day: Mapped[int | None] = mapped_column(Integer)
    credit_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    minimum_payment: Mapped[Decimal | None] = mapped_column(MONEY)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Subscriptions and alerts (services/recurring.py, services/alerts.py)
# ---------------------------------------------------------------------------
RECURRING_STATUSES = ("detected", "confirmed", "dismissed")


class RecurringStream(TimestampMixin, Base):
    """A charge that repeats on a schedule, found in transactions (never Plaid's
    paid Recurring product). Detection refreshes the numbers; the user's
    verdict (`status`: detected, confirmed, dismissed) and `name` survive it."""
    __tablename__ = "recurring_streams"
    __table_args__ = (Index("ix_recurring_merchant", "merchant"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    merchant: Mapped[str] = mapped_column(String(300), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200))
    cadence: Mapped[str] = mapped_column(String(12), nullable=False)
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Typical charge: the median of the latest three.
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    last_amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    #: The price before the latest increase or cut, and when it changed.
    previous_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    price_changed_on: Mapped[date | None] = mapped_column(Date)
    first_date: Mapped[date] = mapped_column(Date, nullable=False)
    last_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_date: Mapped[date] = mapped_column(Date, nullable=False)
    charge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str | None] = mapped_column(String(80))
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="detected")
    status_set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The last detection run that still found it.
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DismissedAlert(Base):
    """An alert the user waved off, never shown again. Keys are stable per
    finding: "dup:<txn>:<txn>", "large:<txn>", "price:<stream>:<date>"."""
    __tablename__ = "dismissed_alerts"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    dismissed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    dismissed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class PricePoint(Base):
    """A daily close from public market data (services/prices.py): benchmarks and
    the securities the household holds. `series` is "provider:CODE", e.g.
    "fred:SP500", "tiingo:SPY" (dividend-adjusted), "tiingo_close:AAPL" (as traded)."""
    __tablename__ = "price_points"

    series: Mapped[str] = mapped_column(String(48), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(QTY, nullable=False)


class DashboardWidget(TimestampMixin, Base):
    """One card on a person's Overview: a built-in section or an Insights view
    pinned with the settings it had (api/dashboard.py VIEWS). Each person
    arranges their own; `size` spans narrow (one column), wide (two) or full."""
    __tablename__ = "dashboard_widgets"
    __table_args__ = (Index("ix_dashboard_widgets_user", "user_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    view: Mapped[str] = mapped_column(String(40), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    size: Mapped[str] = mapped_column(String(8), nullable=False, default="wide")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# ---------------------------------------------------------------------------
# Plumbing: jobs, webhooks, link sessions
# ---------------------------------------------------------------------------
JOB_STATUSES = ("queued", "running", "done", "failed")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_run_after", "status", "run_after"),
        Index("ix_jobs_kind_item", "kind", text("(payload->>'item_id')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (Index("ix_webhook_events_received", "received_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    item_id: Mapped[str | None] = mapped_column(String(80))
    webhook_type: Mapped[str] = mapped_column(String(60), nullable=False)
    webhook_code: Mapped[str] = mapped_column(String(80), nullable=False)
    environment: Mapped[str | None] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class LinkSession(Base):
    __tablename__ = "link_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    link_token: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("plaid_items.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="create")  # create | update
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
