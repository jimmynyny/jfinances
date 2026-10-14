# 80 — HTTP API

Base: `https://jfinances.sellingtcg.com/api/v1`. JSON in, JSON out. Every
route needs a principal (Cloudflare Access session on the dashboard
hostname, or `Authorization: Bearer` on the API hostname) except `/healthz`.
Money fields are strings with two decimals (`"1234.56"`); quantities are
strings; dates are ISO 8601.

Errors:

```json
{"error": {"code": "auth.not_allowed", "message": "…"}}
```

Codes you will see: `auth.missing_credential` 401, `auth.bad_access_jwt` 401,
`auth.bad_token` 401/429, `auth.bad_link_code` 400, `auth.not_allowed` 403,
`auth.forbidden` 403, `auth.read_only` 403,
`not_found` 404, `bad_request` 400, `validation` 422, `conflict` 409,
`rate_limited` 429, `plaid_error` 502, `internal` 500.

`dashboard_only` below means a device token is refused (interactive session required).

## Identity

### GET /me
```json
{"email":"jimmy@…","display_name":null,"role":"owner","via":"access",
 "session_expires_at":"2026-10-14T16:00:00+00:00","env":"production","plaid_env":"production"}
```

## Overview and net worth

### GET /overview
```json
{"net_worth":"687041.79","assets":"929008.67","liabilities":"241966.88",
 "change_1m":{"amount":"23542.96","pct":"3.5","since":"2026-09-13"},
 "as_of":"2026-10-13T06:00:12+00:00","account_count":23,
 "items_needing_attention":[{"id":"…","institution_name":"Chase","status":"login_required","error_code":"ITEM_LOGIN_REQUIRED"}],
 "groups":[
   {"key":"cash","label":"Cash","is_liability":false,"total":"65342.30",
    "change_1m":{"amount":"1826.10","pct":"2.9"},
    "accounts":[{"id":"…","name":"Checking","mask":"4821","type":"depository","subtype":"checking",
                 "current_balance":"15234.75","available_balance":"15100.00","institution_name":"Citi",
                 "balance_updated_at":"…","is_hidden":false,"is_liability":false,"kind":"plaid","item_status":"active", "…":"…"}]},
   {"key":"investments","label":"Investments","…":"…"},
   {"key":"real_estate","…":"…"},{"key":"vehicles","…":"…"},{"key":"other_assets","…":"…"},
   {"key":"credit_cards","is_liability":true,"…":"…"},{"key":"loans","…":"…"},{"key":"other_liabilities","…":"…"}
 ]}
```
Group keys are fixed and always present (possibly empty).

### GET /networth/history?range=1m|3m|6m|1y|all
```json
{"range":"6m","points":[{"date":"2026-04-13","assets":"…","liabilities":"…","net":"…"}, "…"],
 "estimated_before":"2026-10-13|null"}
```
One point per day; each account contributes its latest snapshot on or before that day, and its
first snapshot's value on days before it (held flat, so linking an account doesn't make the line
jump). Cash and card accounts reach back past linking through `derived` snapshots
(docs/20 "Derived history"). `estimated_before` is the first day with a real snapshot when the
range starts earlier: the line before it is an estimate.

## Accounts

### GET /accounts
`{"accounts":[account, …]}` — every account including hidden and closed.

Account object:
```json
{"id":"…","item_id":"…|null","kind":"plaid|manual","name":"…","official_name":"…","mask":"4821",
 "type":"depository|credit|loan|investment|other|manual","subtype":"checking","manual_category":null,
 "iso_currency":"USD","current_balance":"…","available_balance":"…","credit_limit":"…",
 "balance_updated_at":"…","is_liability":false,"is_hidden":false,"is_business":false,"display_order":0,"closed_at":null,
 "secured_by_id":"…|null","institution_name":"Citi","institution_id":"ins_5","item_status":"active"}
```


Every account row here and in `GET /overview` carries `trend`: up to 90 daily
balances, oldest to newest, as decimal strings with the same sign as
`current_balance`. Gaps carry the previous value forward and the last point
is the live balance, so a sparkline ends at the number printed beside it
(`server/app/services/trends.py`).

### PUT /accounts/order
Drag-and-drop reorder. Body `{"account_ids":["…","…"]}`: one group's accounts,
top to bottom, hidden ones included; each gets `display_order` = its index.
→ `{"ok":true,"count":3}`. `400` on duplicates, `404` naming unknown ids.
Groups sort independently, so sending one group never disturbs another.

### PATCH /accounts/{id}
Body: `{"name"?: str, "is_hidden"?: bool, "is_business"?: bool, "display_order"?: int, "secured_by_id"?: uuid|null}` → account.
`secured_by_id` links a loan (any liability but a credit card) to the offline asset it is secured
by: a manual `real_estate`, `vehicle` or `other_asset` account. `null` unlinks; leaving the field
out keeps the link. 400 for a card, or a target that isn't such an asset.

### POST /accounts/manual → 201
Body: `{"name":"2019 4Runner","manual_category":"vehicle","value":"28500","iso_currency":"USD"}`.
`manual_category` ∈ `real_estate | vehicle | cash | other_asset | other_liability`.
Creates the account and today's snapshot.

### PUT /accounts/{id}/value
Body: `{"value":"29000","as_of":"2026-10-01","note":"KBB"}` (manual accounts only). Writes/overwrites the snapshot for that date; updates the current balance if the date is the latest.

### DELETE /accounts/{id} → 204 (manual only, dashboard_only)

### POST /accounts/{id}/refresh
The latest balances Plaid has for the whole item (`/accounts/get`, free). 429 if the item was refreshed within 10 minutes. → account.

### GET /accounts/{id}/history?range=1y
`{"account_id":"…","points":[{"date":"…","balance":"…","source":"plaid|manual|carry|derived"}]}`
(`derived`: rebuilt from transactions for the days before the account was linked)

## Items (Plaid connections)

### GET /items
`{"items":[item, …]}`
```json
{"id":"…","plaid_item_id":"…","institution_id":"ins_3","institution_name":"Chase",
 "status":"active|login_required|error|pending_expiration|removed","error_code":null,"error_message":null,
 "consent_expires_at":null,"transactions_status":"HISTORICAL_UPDATE_COMPLETE",
 "last_synced_at":"…","last_webhook_at":"…","new_accounts_at":null,"investments_synced_at":"…","liabilities_synced_at":"…",
 "products":["transactions","liabilities"],"account_count":3,"created_at":"…","removed_at":null}
```

### POST /items/{id}/sync → 202
Queues `sync_item`, `refresh_investments`, `refresh_liabilities`. `{"queued":true,"item":item}`

### POST /items/{id}/relink (dashboard_only)
Update mode with account selection: Re-link (re-auth, consent) and Add accounts. Same Item, nothing new billed.
`{"link_token":"link-…","expiration":"…","link_session_id":"…","mode":"update"}`

### DELETE /items/{id} (dashboard_only)
Calls `/item/remove`; returns the item with `status:"removed"`.

## Link

### POST /link/token (dashboard_only)
Body: `{"kind"?: "banking"|"investments", "item_id"?: "…"}`. `kind` (default `banking`)
picks the product plan (docs/30 "Products"); `item_id` present = update mode, `kind` ignored.
```json
{"link_token":"link-production-…","expiration":"…","link_session_id":"…","mode":"create",
 "kind":"banking","redirect_uri":"https://jfinances.sellingtcg.com/link/oauth"}
```
`400 bad_request` for an unknown kind or one whose required product `PLAID_PRODUCTS` disables.

### GET /link/session (dashboard_only)
The newest unconsumed, unexpired link session for this user, for the OAuth return page:
`{"link_token":"…","link_session_id":"…","mode":"create|update","item_id":null}`

### POST /link/exchange → 201 (dashboard_only)
Body: `{"public_token":"public-…","metadata":{…from Link onSuccess…},"link_session_id":"…","confirm"?:"new_login"|"overlap"}` → item. Queues `sync_item`, plus `refresh_investments` / `refresh_liabilities` only if the Item has those products.

The duplicate guard runs first (docs/30 "Never paying twice"). `409` with
`code` `link.duplicate` (no override), `link.overlap` (retry with
`confirm:"overlap"`) or `link.same_institution` (retry with
`confirm:"new_login"`); the body adds `institution`, `accounts` (the
already-connected ones, as "Name ··1234") and `confirm` (the value that lets
it through, or null). Nothing was exchanged, so nothing is billed.
```json
{"error":{"code":"link.overlap","message":"Chase Total Checking ··4821 is already connected…",
 "institution":"Chase","accounts":["Chase Total Checking ··4821"],"confirm":"overlap"}}
```
If the first `/accounts/get` fails after the exchange, the item is still
saved and returned (its queued sync retries).

### POST /link/update-complete (dashboard_only)
Body: `{"link_session_id":"…"}` after update-mode Link finishes → item (status `active`, `new_accounts_at` cleared).

### GET /link/config
`{"redirect_uri":"…","webhook_url":"…","products":[…],"kinds":{"banking":{"products":["transactions"],"required_if_supported_products":["liabilities","investments"]},"investments":{…}},"plaid_env":"production"}`

## Transactions

### GET /transactions
Query: `from`, `to` (dates), `account_id`, `q` (name/merchant/notes/amount contains), `category`, `pending` (bool), `page` (1-based), `page_size` (≤500, default 50).
```json
{"page":1,"page_size":50,"total":1234,"transactions":[
 {"id":"…","account_id":"…","account_name":"Checking","account_mask":"4821","institution_name":"Citi",
  "date":"2026-10-12","authorized_date":"2026-10-11","amount":"64.00","iso_currency":"USD",
  "name":"THE GOOD TABLE","merchant_name":"The Good Table","logo_url":"…","pending":false,
  "category_primary":"FOOD_AND_DRINK","category_detailed":"FOOD_AND_DRINK_RESTAURANT",
  "category":"FOOD_AND_DRINK","user_category":null,"payment_channel":"in store","notes":null,"removed_at":null}]}
```
`amount` keeps Plaid's sign: positive is money out, negative is money in. `category` is `user_category` if set, else Plaid's primary.

### PATCH /transactions/{id}
Body: `{"user_category"?: str|null, "notes"?: str|null}` → transaction.

### GET /transactions/summary
Query: `group_by=category|month|account`, optional `from`, `to`, `account_id`,
`include_transfers` (default `false`). Pending transactions are never counted.
```json
{"group_by":"month","transfers":"excluded","rows":[
 {"key":"2026-09","label":"2026-09","inflow":"8421.10","outflow":"6776.14","total":"-1644.96","count":131}]}
```
`inflow` is money in and `outflow` money out, both positive; `total` is the net
with Plaid's sign (positive = more out than in). Month rows are chronological;
category and account rows are biggest net outflow first.

Internal transfers are excluded unless `include_transfers=true`: categories
`TRANSFER_IN` / `TRANSFER_OUT` (the user's category wins when set) and card
payments (`LOAN_PAYMENTS_CREDIT_CARD_PAYMENT`). Counting them would double
count: a transfer is out of one account and into another, and a card payment
repays purchases already counted on the card.

Money into a card or loan (`is_liability`, negative amount) whose category is
`INCOME`, `TRANSFER_IN`, `LOAN_PAYMENTS` or `LOAN_DISBURSEMENTS` is a payment
from another account, whatever the issuer called it (card payments arrive as
`INCOME` or `LOAN_DISBURSEMENTS` too). It is
grouped under the key `PAYMENT` (label `PAYMENTS`); with `account_id` set to
that card or loan it counts as money in, and everywhere else it is excluded
with the other transfers. Transactions show it as `category: "PAYMENT"`.

### GET /transactions/categories
`{"categories":["FOOD_AND_DRINK","GENERAL_MERCHANDISE", "…"]}`

## Investments

### GET /holdings
```json
{"total_value":"542301.55","accounts":[
 {"account":account,"holdings_value":"180336.73","holdings":[
   {"id":"…","security_id":"…","ticker":"VTI","name":"Vanguard Total Stock Market ETF","type":"etf",
    "is_cash_equivalent":false,"quantity":"120.5","cost_basis":"20000.00","price":"281.12",
    "price_as_of":"2026-10-10","value":"33875.00","iso_currency":"USD","close_price":"281.12","close_price_as_of":"2026-10-10"}]}]}
```

### GET /holdings/transactions?account_id&limit=200
`{"transactions":[{"id":"…","account_id":"…","account_name":"…","institution_name":"…","date":"…","name":"BUY VTI","type":"buy","subtype":"buy","ticker":"VTI","security_name":"…","quantity":"10","amount":"2811.20","price":"281.12","fees":"0.00"}]}`

## Investment performance

### GET /investments/performance?range=3m|6m|1y|2y|5y&account_id=…&benchmark=sp500,dow
Time-weighted return of every investment account together (or one), and each
benchmark asked for from the same first day:
`{range, from, to, series[{date, value, flows, return}], estimated_before,
accounts[{id, name, rebuilt, coverage, tracked_since}], benchmarks[{key, label,
source, points[{date, return}]}], available[{key, label, available, since, note}]}`.
`return` is a ratio (0.12 = +12%); `flows` is money moved in (+) or out (−);
`estimated_before` is the first real snapshot when the line starts earlier
(rebuilt before it). Benchmarks: `sp500`, `dow`, `nasdaq100`, `bitcoin`, `world`,
`bonds`, `gold`, `sixty_forty`, `inflation`; `source` is null when no stored
prices cover the range.

### POST /prices/refresh → 202 (dashboard_only)
Queues `refresh_prices` now: `{"queued": bool}` (false when one is already queued).

## Liabilities

### GET /liabilities
```json
{"total_owed":"241966.88","accounts":[
 {"account":account,"detail":{"kind":"mortgage","interest_rate_pct":"6.125","interest_rate_type":"fixed",
   "next_payment_due_date":"2026-11-01","minimum_payment":"2412.00","next_payment_amount":"2412.00",
   "last_payment_amount":"2412.00","last_payment_date":"2026-10-01","last_statement_balance":null,
   "last_statement_date":null,"is_overdue":false,"origination_date":"2021-03-15","origination_principal":"320000.00",
   "loan_term":"30 year","maturity_date":"2051-03-15","updated_at":"…"}}]}
```
`detail` is null until the liabilities refresh has run for that item.

## Insights
Read-only slices of transactions (`services/insights.py`). Every endpoint takes
`from`, `to` (default: the current month and the eleven before it), `scope`
(`personal` default, `business`, `all`, by `accounts.is_business`) and
repeatable `account_id`, and echoes `from`/`to`/`scope`. Same rules as the
Transactions summary: no pending or removed rows, no transfers between your
own accounts, no payments into cards and loans, no hidden accounts. Income is
the `INCOME` category; spending is every other category, net of refunds.

### GET /insights/cashflow?grain=month|quarter|year
`periods[{period, label, income, spending, net, savings_rate}]`, `totals`,
`averages` (whole periods only, with `periods` = how many), `income_sources[{kind,
label, amount, count}]` (`kind`: paychecks, dividends, interest, retirement, tax
refunds, unemployment, other income; `label`: the payer, ACH noise removed) and
`spending_categories[{key, amount}]` (top 8 + `OTHER`, for the money-flow diagram).

### GET /insights/spending?grain=…&group=category|merchant&category=…&top=7
`periods[{period, label}]`, `series[{key, total, values[]}]` (top N + `OTHER`),
`total`. With `category`, drills into it: series are its detailed categories (or
merchants).

### GET /insights/compare?category=…
`previous{from, to}` (the same range a year earlier) and `rows[{key, current,
previous, change, pct}]` per category (or detailed category within `category`).

### GET /insights/merchants?category=…&top=25
`merchants[{label, total, count, average, category, first_seen, last_seen,
is_new, trend[]}]`: purchases only (refunds don't count as visits); `is_new`
when the first transaction ever with the merchant falls in the range; `trend`
is one value per month of the range.

### GET /insights/patterns?category=…
`weekdays[{weekday 0=Mon, total, per_day}]` and `month_days[{day, total,
per_day}]`; `per_day` divides by how many of that day the range holds.

### GET /insights/networth?range=1y|2y|5y|10y
Month-end totals per account group (the net worth chart's rules): `{groups[{key, label,
liability}], points[{date, assets, liabilities, net, <group key>…}]}`; debts are positive.

### GET /insights/homes
`{"homes":[{id, name, category, value, owed, equity, ltv, loans[{id, name, mask, balance,
rate}], history[{date, value, owed, equity}]}]}`: real estate (and other property with a
loan linked by `secured_by_id`), month ends for two years.

### GET /insights/loans?extra=0
`{"extra", "loans":[{id, name, kind, balance, rate, scheduled_payment, maturity_date,
ytd_interest, schedule{payment, payoff, months, interest, per_year[{year, interest,
principal}]}, what_if{extra, payoff, months, interest, months_saved, interest_saved}}]}`.
`payment` is principal and interest from an amortization to the maturity date (the bill
may include escrow); `ytd_interest` is the lender's figure when reported.

### GET /insights/cards?range=1y
`{cards[{id, name, mask, limit, balance, utilization, history[…]}], overall[{date,
utilization}], charges[{month, interest, fees}], totals{interest, fees}}`: utilization
against today's limits; interest and fees from `BANK_FEES_*` transactions.

## Subscriptions and alerts
Found in transactions after every sync (docs/20 `recurring_streams`).

### GET /recurring
`{"streams":[{id, merchant, name, label, cadence, interval_days, amount, last_amount,
previous_amount, price_changed_on, first_date, last_date, next_date, charge_count,
category, account_id, account_name, account_mask, is_business, status, state, monthly}],
"monthly_confirmed", "monthly_detected"}`. `state` is `active` or `lapsed`;
`monthly` is the amount per month; the totals add up active streams per status.

### PATCH /recurring/{id}
Body: `{"status"?: "detected"|"confirmed"|"dismissed", "name"?: str|null}` → stream.
The verdict and name survive detection.

### GET /recurring/upcoming?days=30
Expected charges from active, non-dismissed streams: `{from, to, items[{stream_id,
label, date, overdue, amount, cadence, status, category, account_name, is_business}],
total}`. A weekly stream appears once per week.

### POST /recurring/detect
Runs detection now: `{"found": n}`.

### GET /alerts?days=60
`{"days", "alerts":[{key, kind, date, merchant, amount, ...}]}`: `price` (with
`previous`, `stream_id`), `duplicate` (same merchant and amount within two days
on one account, `transaction_ids`), `large` (with `usual` and `basis`: merchant,
or category for a merchant with little history). Dismissed keys never return.

### POST /alerts/dismiss → 204
Body: `{"key": "…"}`.

### POST /alerts/dismiss-all?days=60
Dismisses every alert showing in that window (what GET /alerts returns now): `{"dismissed": n}`.
The panel shows alerts ten to a page.

## Dashboard (each person's Overview)

### GET /dashboard
`{"columns": 1|2|3, "widgets":[{id, view, settings, size, position}]}` for the
signed-in person only. The first read seeds Overview's sections (`networth`,
`split`, `upcoming`, `alerts`, `calendar`, `accounts`); after that an emptied
dashboard stays empty until reset.

### POST /dashboard/widgets → 201
Body: `{"view": "<key>", "settings"?: {…}, "size"?: "narrow"|"wide"|"full"}` → widget,
appended. `view` is one of `api/dashboard.py` VIEWS: the sections above plus
`cashflow`, `money_flow`, `income_sources`, `spending`, `merchants`, `patterns`,
`compare`, `subscriptions`, `networth_classes`, `homes`, `loans`, `cards`,
`performance`. `settings` (≤ 2 KB JSON) is what the view showed when pinned:
for Insights views `{range, grain, scope, accountId?, category?}` (ranges are
presets, so a pinned "12m" keeps rolling); for performance `{range, benchmarks,
accountId?}`. 40 widgets at most.

### PATCH /dashboard/widgets/{id} · DELETE /dashboard/widgets/{id} → 204
Body: `{"size"?: …, "settings"?: {…}}`. 404 for another person's widget.

### PUT /dashboard/order
Body: `{"widget_ids": [...]}`: every widget on the dashboard, each once, in the
new order → dashboard.

### PUT /dashboard/columns · POST /dashboard/reset
`{"columns": 1|2|3}` → dashboard. Reset deletes every widget and seeds the
default sections again.

## Sync

### GET /sync/status
```json
{"items":[item, …],
 "jobs":[{"id":"…","kind":"sync_item","status":"queued|running|failed","item_id":"…","attempts":1,
          "run_after":"…","last_error":null,"created_at":"…","finished_at":null}],
 "webhooks":[{"id":"…","item_id":"…","type":"TRANSACTIONS","code":"SYNC_UPDATES_AVAILABLE",
              "received_at":"…","processed_at":"…","error":null}]}
```

### POST /sync/all → 202 (dashboard_only) — queue sync/investments/liabilities for every item.
### POST /sync/snapshot → 202 (dashboard_only) — queue today's balance snapshot.

## Phones

A token is read-only: anything but GET/HEAD/OPTIONS with a token is 403
`auth.read_only`. docs/40 §5 has the whole flow.

### GET /mobile/link?nonce=N&name=… (dashboard hostname, dashboard_only)
Opened by the app in a system web sheet. Mints a one-time code (120 s) and
answers 302 `jfinances://linked?code=…&nonce=N`. `nonce`: 8–64 of
`[A-Za-z0-9_-]`, else 400.

### POST /mobile/redeem (API hostname only, no auth)
`{"code","nonce","name"?}` → `{"token":"<shown once>","id","name","email","display_name"}`.
400 `auth.bad_link_code` for an unknown, used, expired or mismatched code; 429
after 20 bad attempts a minute from one address.

### POST /mobile/unlink (API hostname only, bearer)
Revokes the presenting token → `{"revoked":true,"id"}`.

### GET /tokens (dashboard_only) → `{"tokens":[{"id","name","created_at","last_used_at","revoked_at"}]}`
### DELETE /tokens/{id} (dashboard_only) → 204: unlinks that phone.

## Public

### GET /healthz → `{"ok":true,"service":"web","env":"production","db":"ok"}` (503 if the DB is down)
### GET /about → the privacy page (`index.html`)

## Hooks service (separate hostname)

### POST /plaid/webhook — Plaid only. 401 unless the `Plaid-Verification` signature checks out.
### GET /healthz
