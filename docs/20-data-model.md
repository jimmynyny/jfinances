# 20 — Data model

Postgres, managed by Alembic (`server/alembic/`). The ORM is
`server/app/models.py`; this page explains *why* each table and column
exists. If you add a column, add it here.

Conventions: uuid4 primary keys named `id`; money is `numeric(18,2)`; share
quantities and prices are `numeric(24,8)`; interest rates `numeric(9,4)`;
timestamps are `timestamptz` in UTC; every row that came from Plaid keeps
the full payload in a `raw jsonb` column so a new field can be backfilled
from what we already stored instead of another billable call.

```
users ──< api_tokens
users ──< mobile_link_codes
users ──< link_sessions >── plaid_items
users ──< plaid_items ──< accounts ──< transactions >── imports ──< import_rows
                                  ├──< balance_snapshots
                                  ├──< holdings >── securities
                                  ├──< investment_transactions >── securities
                                  ├──1 liabilities
                                  └──1 account_terms
jobs                 (queue)
webhook_events       (audit)
```

## users
Who may use the app. Seeded from `ALLOWED_USERS` at every `web` boot
(`auth/human.py::seed_allowed_users`). The first address in the list is
`owner` and the rest are `member`, re-applied to existing rows at every boot,
so the variable's order is the source of truth. Seeding takes a Postgres
advisory lock because every uvicorn worker seeds at startup. Removing an address from the variable does not
delete the row (history references it); it sets `disabled_at`, and the person
is refused on their next request.

| column | why |
|---|---|
| `email` (unique) | the one fact we take from Cloudflare Access, lowercased |
| `display_name` | optional, for the nav |
| `role` | `owner` / `member`. Today both can do everything; the column exists so a future read-only member is a one-line change |
| `disabled_at` | soft delete |
| `last_seen_at` | written on each authenticated request |

## api_tokens
Phone credentials for the API hostname (docs/40 §5). **Only the SHA-256 of
the token is stored.** The plaintext is returned once, to the phone, by
`POST /api/v1/mobile/redeem`. `name` is what the phone called itself;
`revoked_at` is a soft revoke; `last_used_at` (written at most every 5
minutes) tells you which phone is in use.

## mobile_link_codes
The two-minute codes `GET /api/v1/mobile/link` mints behind Access: `user_id`,
the app's `nonce`, SHA-256 `code_hash`, `expires_at`, `used_at` (set by the
one redeem that wins). Rows more than a day past expiry are deleted whenever
a new code is minted.

## plaid_items
One row per Plaid Item (one login at one institution). The row outlives an
unlink: `status=removed`, `removed_at` set, accounts kept for history.

| column | why |
|---|---|
| `item_id` (unique) | Plaid's id; what webhooks name |
| `institution_id`, `institution_name` | from Link metadata or `/institutions/get_by_id` |
| `access_token_enc` | AES-256-GCM ciphertext of the access token (docs/40 §4). Never leaves the server |
| `status` | `active`, `login_required`, `error`, `pending_expiration`, `removed`. Drives the "needs attention" list |
| `error_code`, `error_message` | last Plaid error, cleared on the next success |
| `consent_expires_at` | from `PENDING_EXPIRATION` or item metadata; relink before it |
| `transactions_cursor` | the `/transactions/sync` cursor; persisted only after a full successful page set |
| `transactions_status` | `NOT_READY` → `INITIAL_UPDATE_COMPLETE` → `HISTORICAL_UPDATE_COMPLETE` |
| `investments_synced_at`, `liabilities_synced_at`, `last_synced_at`, `last_webhook_at` | shown on /sync/status |
| `new_accounts_at` | set by `ITEM/NEW_ACCOUNTS_AVAILABLE`, cleared when update mode finishes; Settings highlights Add accounts while it is set |
| `products` | what Plaid says the item has; used to decide which refresh jobs apply |
| `created_by` | who linked it |

## accounts
Every account we show, Plaid or manual, in one table so the overview is one
query.

| column | why |
|---|---|
| `item_id` | null for manual accounts |
| `plaid_account_id` (unique) | null for manual |
| `kind` | `plaid` / `manual` |
| `name` | follows Plaid until the user renames it via `PATCH /accounts/{id}` |
| `official_name`, `mask`, `type`, `subtype` | Plaid's; `type` is `depository`, `credit`, `loan`, `investment`, `other`; manual accounts use `type=manual` |
| `manual_category` | `real_estate`, `vehicle`, `cash`, `other_asset`, `other_liability` — the "offline assets" bucket |
| `iso_currency` | default USD |
| `current_balance`, `available_balance`, `credit_limit` | as Plaid gives them: liabilities are positive amounts owed |
| `balance_updated_at` | when we last wrote the balance (used by the snapshot job to decide `plaid` vs `carry`) |
| `is_liability` | derived at write time from `type` / `manual_category` (or `group_override`) so the overview never recomputes it |
| `is_hidden` | excluded from totals and charts, still listed |
| `is_business` | a business account (Daedalus TCG), set in the account's Edit form; Insights keep business and personal apart (a transaction's own `business` flag wins) |
| `group_override` | where the account counts when its type alone would put it elsewhere ("Counts as" in the Edit form): a `networth.GROUPS` key (`cash`, `investments`, `real_estate`, `vehicles`, `other_assets`, `credit_cards`, `loans`, `other_liabilities`). It also decides `is_liability`, which a sync keeps; an account counted as cash or a card rebuilds its history from transactions. An offline account moved to a group with a category of its own takes the category instead (null override) |
| `display_order` | user sort |
| `closed_at` | Plaid stopped returning it, or the item was unlinked |
| `last_refresh_requested_at` | rate limit for the Refresh button |
| `secured_by_id` | a loan's collateral: the offline asset (`real_estate`, `vehicle`, `other_asset`) a mortgage, HELOC or car loan is secured by. Set by hand on the Liabilities page via `PATCH /accounts/{id}`; several loans can share one asset; deleting the asset clears it (`ON DELETE SET NULL`). The account drawer shows an asset's loans and its equity (value − what they owe) |

## balance_snapshots
One row per account per day, the source of every history chart.
`source` is `plaid` (balance refreshed that day), `manual` (user entered a
value for that date), `carry` (worker copied the last known value) or
`derived` (rebuilt from transactions, below). A manual value on a date is
never overwritten by a carry. Unique on `(account_id, as_of)`.

**Derived history.** Snapshots start the day an account is linked, but Plaid
hands over up to two years of transactions. For cash (`depository`) and card
(`credit`) accounts, `services/history.py` walks back from the account's
first real snapshot, undoing each day's posted transactions, and writes one
`derived` row per day back to the day before its earliest transaction. It
runs after every transactions sync (`sync_item`), in a savepoint so a failure
is logged and never undoes the sync, and replaces only `derived` rows, which
all fall before the first real one (a day that already has a real row keeps
it). Loans and offline assets are never derived: their value moves with
interest and prices, which transactions don't record. An investment account
is derived only over the window an imported statement covers
(`history.derive_investment`): the statement's holdings on its last day
(kept in the import's `mapping`), walked back through every trade in the
window, each fund priced that day (`performance.price_curve`: market closes
when the fund's ticker agrees with its trade prices, else the trade prices,
interpolated). Elsewhere the net worth chart holds an account at its first
recorded value on earlier days and says the stretch is estimated
(`estimated_before` on `GET /networth/history`); derived days count as
estimated too, and investment performance treats them as values, not
tracking.

## transactions
From `/transactions/sync` (`source = 'plaid'`), or from a bank export (`source = 'import'`,
`import_id` set, `plaid_transaction_id` null; see imports below). `amount` keeps Plaid's sign (positive = money
leaving the account). `category_primary` / `category_detailed` are Plaid's
personal finance categories; `user_category` overrides the primary for
display and summaries. `notes` is free text. `business` is the person's say on
one transaction (true business, false personal, null as its account's
`is_business`): a personal buy on the business card counts as personal in
Insights, and the other way round. `removed_at` is set when Plaid
reports a removal (a pending transaction that posted under a new id) instead
of deleting, so audit is possible. When a pending transaction posts, user
edits are carried to the new row via `pending_transaction_id`.

## securities, holdings, investment_transactions
From `/investments/holdings/get` and `/investments/transactions/get`.
`securities` is global (one row per Plaid security). `holdings` is unique on
`(account_id, security_id)` and is replaced wholesale on each refresh;
positions Plaid stops reporting are deleted. `investment_transactions` are
append/upsert by Plaid id (`source = 'plaid'`), or come from an investment
statement (`source = 'import'`, `import_id` set, `plaid_investment_transaction_id`
null): a 401(k) payroll buy is two rows, a `cash`/`contribution` and the `buy`,
so walking history back finds no cash that never was and performance counts the
contribution as money in, not growth. A fund an account doesn't hold becomes a
`securities` row of its own (`plaid_security_id` = `import:<id type>:<id>`),
removed with the import if nothing else uses it.

## liabilities
One row per liability account (unique `account_id`). `kind` is `credit`,
`mortgage` or `student`. Columns are the useful subset of Plaid's three
shapes (APR, minimum payment, due dates, origination, maturity); `raw` has the
rest.

## account_terms
One row per account (primary key `account_id`, deleted when every field is
cleared) holding what the person entered where the bank is silent: a loan's
`interest_rate_pct`, `rate_type`, `original_principal`, `origination_date`,
`term_months`, `payment_amount` (principal and interest; a mortgage's escrow is
`escrow_amount`) and `payment_day`; a card's purchase APR (`interest_rate_pct`),
`credit_limit`, `statement_day`, `payment_day` and `minimum_payment`; a savings
account's APY (`interest_rate_pct`). `updated_by` is the person. A value the
bank reports always wins, so an entered one only ever fills a gap; the rest
(payment, rate, term or original amount from the other three; payoff; schedule)
is worked out on read by `services/terms.py` and `services/loanmath.py`, never
stored.

## imports, import_rows, import_profiles
A bank export imported into a linked account (services/importer.py), or an investment statement
into a linked investment account (`format = 'invofx'`, services/invimport.py: `mapping` holds the
statement's holdings on its last day, which anchor derived history). `imports` is one per
file: its name and SHA-256 (never its contents), how its columns were read (`mapping`), the
date range, counts, and `status` (`applied`, or `undone` with `undone_at`). `import_rows` is
the ledger, unique on (`account_id`, `fingerprint`): every row an import added (`added`,
`transaction_id`) or found already there (`matched`, `matched_transaction_id`), so the same row
in a later or overlapping export is never added again; `superseded` marks an added row the
connection later sent too. A fingerprint is the bank's FITID for OFX, else date, amount,
normalized description and which of the identical same-day rows it is. `import_profiles`
remembers a confirmed CSV layout by its header signature, and the account it last went into.
Imported transactions have `source = 'import'`, `import_id`, and no `plaid_transaction_id`;
everything else reads them like any other. Their running balances are `balance_snapshots`
with `source = 'import'` (and `note = 'import:<id>'`), only on days before tracking began; for
an offline account (no tracking: kept by hand), on every day without a typed (`manual`) value,
and the daily carry-forward never overwrites one.

## jobs
The work queue (docs/10 §5, `jobs/queue.py`). `kind` is a registered handler
name; `payload` is small JSON (usually `{"item_id": ...}`); `status` is
`queued` → `running` → `done` | `failed`; `run_after` schedules retries with
backoff; `attempts`/`max_attempts` bound them. The expression index on
`(kind, payload->>'item_id')` makes dedupe cheap; a household-wide job (no
payload: `sync_all`, `detect_recurring`) has at most one queued copy.
Done/failed rows are pruned after 30 days.

## recurring_streams
Subscriptions and bills found in transactions (`services/recurring.py`),
never Plaid's paid Recurring product. Detection runs after every
transactions sync (`detect_recurring` job) and refreshes the numbers:
`merchant`, `cadence` (weekly, biweekly, monthly, quarterly, semiannual,
annual), `interval_days`, `amount` (typical: median of the latest three
since any price step), `last_amount`, `previous_amount` + `price_changed_on`
(the latest step in a steady price), `first_date`, `last_date`, `next_date`,
`charge_count`, `category`, `account_id`, `seen_at`. The user's verdict
`status` (`detected` → `confirmed` | `dismissed`) and `name` are never
changed by detection; a found stream updates the row for the same merchant
whose amount is close (same cadence preferred). Overdue by more than the
cadence's tolerance = lapsed (computed, not stored).

## dashboard_widgets
Each person's Overview (`api/dashboard.py`): `user_id`, `view` (a key in VIEWS),
`settings` JSONB (what the view showed when pinned), `size` (`narrow`, `wide`,
`full`), `position`. `users.dashboard_columns` (1-3) is null until the first read,
which seeds the default widgets, so an emptied dashboard stays empty.

## price_points
Daily closes from public market data (docs/30 "Market data"): `(series, date)`
primary key, `close`. `series` is `provider:CODE`: `fred:SP500`, `tiingo:SPY`
(dividend-adjusted), `tiingo_close:AAPL` (as traded), `tiingo_crypto:btcusd`.

## dismissed_alerts
Alerts the user waved off (`services/alerts.py`), by stable key:
`dup:<txn>:<txn>`, `large:<txn>`, `price:<stream>:<date>`.

## webhook_events
Every verified webhook, as received, with `processed_at` or `error`. This is
the audit trail when a sync did not happen.

## link_sessions
Link tokens we created, per user, so the OAuth return page can re-initialise
Link with the same token. `mode` is `create` or `update`; `consumed_at` is
set after exchange.

## Net worth
assets = Σ `current_balance` of visible, open, non-liability accounts;
liabilities = Σ of visible, open liability accounts; net = assets − liabilities.
History uses, for each day, each account's most recent snapshot on or before
that day, so a missed snapshot carries forward rather than dropping to zero.
