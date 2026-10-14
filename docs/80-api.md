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
`auth.bad_token` 401/429, `auth.not_allowed` 403, `auth.forbidden` 403,
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
 "balance_updated_at":"…","is_liability":false,"is_hidden":false,"display_order":0,"closed_at":null,
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
Body: `{"name"?: str, "is_hidden"?: bool, "display_order"?: int, "secured_by_id"?: uuid|null}` → account.
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

## Device tokens (dashboard_only)

### GET /tokens → `{"tokens":[{"id","name","created_at","last_used_at","revoked_at"}]}`
### POST /tokens `{"name":"Jimmy's iPhone"}` → 201 `{"id","name","token":"<shown once>","note"}`
### DELETE /tokens/{id} → 204

## Public

### GET /healthz → `{"ok":true,"service":"web","env":"production","db":"ok"}` (503 if the DB is down)
### GET /about → the privacy page (`index.html`)

## Hooks service (separate hostname)

### POST /plaid/webhook — Plaid only. 401 unless the `Plaid-Verification` signature checks out.
### GET /healthz
