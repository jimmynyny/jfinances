# 30 — Plaid

Products: **Transactions**, **Investments**, **Liabilities**. Country US.
Which ones an Item gets depends on the Connect choice; see "Products" below.
History on link: 730 days (Plaid's maximum). Client: `server/app/plaid_client.py`,
a thin httpx wrapper (see the module docstring for why not the generated SDK).

## Products: why there are two Connect choices

`/link/token/create` takes `products` (every one must be supported or the
institution is hidden from Link) and `required_if_supported_products`
(added only when the institution and the selected accounts support them,
and billed only then). Asking for all three as `products` would hide
Robinhood and the 529 plans (no liabilities) and banks without brokerage.
So the dashboard's Connect button asks what is being connected:

| Choice | `kind` | requires | adds when supported |
|---|---|---|---|
| Bank, card or loan | `banking` | `transactions` | `liabilities`, `investments` |
| Investment or retirement | `investments` | `investments` | `transactions`, `liabilities` |

Chase with checking, cards and a mortgage → `banking` gives transactions +
liabilities (+ investments if a J.P. Morgan brokerage account is selected).
Robinhood or a 529 → `investments`. The plan lives in
`plaid_client.LINK_KINDS`; `GET /api/v1/link/config` prints it.

After linking, `/accounts/get` reports the Item's actual `products`, stored
on `plaid_items.products`. Every job checks it first
(`PlaidItem.has_product`): calling `/investments/*`, `/liabilities/get` or
`/transactions/sync` on an Item without that product makes Plaid try to
add it, which starts a new monthly charge.

Update mode (Add accounts) never adds a product. A card added later to an
Item linked without one gets balances and transactions, but Liabilities
details only if the Item already had Liabilities.

## What to register in the Plaid dashboard

Once per environment. All four values come from Railway variables so they are
also printed by `GET /api/v1/link/config`.

| Dashboard field | Production | Sandbox |
|---|---|---|
| Allowed redirect URIs (Team Settings → API) | `https://jfinances.sellingtcg.com/link/oauth` | `https://jfinances-sandbox.sellingtcg.com/link/oauth` |
| Webhook URL (set per item by us at link time) | `https://jfinances-hooks.sellingtcg.com/plaid/webhook` | `https://jfinances-sandbox-hooks.sellingtcg.com/plaid/webhook` |
| App website / privacy (compliance) | `https://jimmynyny.github.io/jfinances/` (also `/about` on the app) | same |

Redirect URIs must be exact, https, no query string, no `#`. The webhook URL
is not a dashboard setting: it is passed in every `/link/token/create` and
can be changed for an existing item with `/item/webhook/update`
(`PlaidClient.item_webhook_update`).

## Link flow

```
browser                         web (Access)                    Plaid
  │ POST /api/v1/link/token ───────►│ /link/token/create ─────────►│
  │◄──── {link_token, link_session_id}                             │
  │ Plaid.create({token}).open() ───────────────────────────────────►│  (user picks bank, logs in)
  │   OAuth bank? Plaid redirects the tab to                        │
  │   /link/oauth?oauth_state_id=…  (SPA route, still behind Access)│
  │   GET /api/v1/link/session  → same link_token                   │
  │   Plaid.create({token, receivedRedirectUri: location.href})     │
  │ onSuccess(public_token, metadata)                               │
  │ POST /api/v1/link/exchange ─────►│ duplicate guard (metadata)    │
  │◄── 409 link.*: ask, or stop      │   (no exchange, no bill)      │
  │                                  │ /item/public_token/exchange ─►│
  │                                  │ encrypt + COMMIT access_token │
  │                                  │ /accounts/get, enqueue jobs   │
  │◄──── item summary                │                               │
```

## Never paying twice

An Item bills monthly from the moment its public token is exchanged until
`/item/remove`, and only its access token can remove it. Two rules follow.

**Don't create the same Item twice.** `services/link_guard.py` compares the
Link metadata (institution id, each selected account's name and mask, as
Plaid recommends) with the live Items *before* the exchange. A public token
that is never exchanged never becomes a billed Item.

| verdict (409 code) | meaning | way through |
|---|---|---|
| `link.duplicate` | every selected account is already connected, or a connection there is still loading its first accounts | none: use Add accounts / Re-link on the existing connection |
| `link.overlap` | some are already connected (a joint account under both logins); they would show twice | `confirm:"overlap"`, or reconnect with them unticked |
| `link.same_institution` | another login at the same bank, none of these accounts | `confirm:"new_login"` (each person's own login) |

The dashboard turns each 409 into a question (`components/LinkExchange.tsx`);
nothing is exchanged until the answer is yes.

**Never lose a token.** `create_item_from_public_token` commits the encrypted
token on its own, right after the exchange. A later failure (the first
`/accounts/get`, say) leaves a saved Item whose queued `sync_item` retries
and then queues the product refreshes it skipped. If the token cannot be
saved at all, the Item is removed at Plaid on the spot. Beyond the code:
daily backups and a copy of `TOKEN_ENCRYPTION_KEY` (docs/60 §6).

Update mode (Re-link for re-auth and consent renewal, Add accounts on a
healthy connection): `POST /api/v1/items/{id}/relink` returns a link token
created with the item's access token and `update.account_selection_enabled`.
Same Item, same token, nothing new billed. When Link finishes there is **no
new public token**; the SPA calls `POST /api/v1/link/update-complete
{link_session_id}`, which clears the error and the new-accounts flag and
queues a sync. A missed account always goes through Add accounts, never a
second Connect.

## Webhooks

Delivered to the `hooks` service only. Verification is in
`services/plaid_webhooks.py` and is covered in docs/40 §3. Routing table is
`hooks.ROUTES`:

| type / code | action |
|---|---|
| TRANSACTIONS / SYNC_UPDATES_AVAILABLE, INITIAL_UPDATE, HISTORICAL_UPDATE, DEFAULT_UPDATE | enqueue `sync_item` |
| HOLDINGS / DEFAULT_UPDATE, INVESTMENTS_TRANSACTIONS / * | enqueue `refresh_investments` |
| LIABILITIES / DEFAULT_UPDATE | enqueue `refresh_liabilities` |
| ITEM / ERROR | status `error` (or `login_required` if the error is ITEM_LOGIN_REQUIRED) |
| ITEM / LOGIN_REPAIRED | status `active`, error cleared |
| ITEM / PENDING_EXPIRATION, PENDING_DISCONNECT | status `pending_expiration`, `consent_expires_at` set |
| ITEM / USER_PERMISSION_REVOKED, USER_ACCOUNT_REVOKED | status `removed` |
| ITEM / NEW_ACCOUNTS_AVAILABLE | set `new_accounts_at`: Settings shows "new accounts available" and highlights Add accounts. A sync can't add them; the user picks them in update mode |
| anything else | recorded in `webhook_events`, no action |

The payload is a signal only; the worker re-reads from Plaid. Unknown item
ids are recorded and ignored.

## Sync

`services/plaid_sync.py`:

- **`sync_transactions`**: `/transactions/sync` from the stored cursor, page
  until `has_more` is false, then apply added/modified/removed and persist
  the new cursor. On `TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION` it
  restarts from the original cursor (up to three times). If a transaction
  references an account we do not have, accounts are refreshed first.
- **`refresh_accounts`**: `/accounts/get` (the balances Plaid last fetched;
  free) and a snapshot. Also behind the Refresh button, rate limited to once
  per item per 10 minutes. Real-time `/accounts/balance/get` is refused by
  the client (see "Cost model").
- **`refresh_investments`**: holdings replaced wholesale; transactions for
  730 days on the first run, then a 30-day overlap.
- **`refresh_liabilities`**: `/liabilities/get`, one row per liability account.

Errors: `PRODUCTS_NOT_SUPPORTED` / `NO_*_ACCOUNTS` are silently fine (a bank
with no investments). `ITEM_LOGIN_REQUIRED` and friends set
`status=login_required`, which is a state, not a retry. Everything else
raises, the job retries with backoff and ends up in `/sync/status`.

## Schedule (worker, UTC)

| when | job |
|---|---|
| 03:00 daily | `sync_all` → one `sync_item` per active item |
| 06:00 daily | `snapshot_balances` |
| 06:30 daily | `refresh_investments_all` |
| 07:00 Mondays | `refresh_liabilities_all` |
| 22:30 daily | `refresh_prices` (market data, below; also on the worker's first start with none stored) |
| every 10 min | release stale `running` jobs, prune old ones |

Times are settings (`NIGHTLY_SYNC_UTC` etc.) if they ever need to move.

## Cost model (what actually bills)

Contract rates (Plaid dashboard → Contracts & Rates, contract of
2026-10-10), per Item per month. An Item is one login at one institution,
however many accounts it covers.

| product | rate | added to an Item when |
|---|---|---|
| Transactions | $0.30 | `banking` requires it; `investments` adds it if a checking, savings or card account is selected |
| Liabilities | $0.20 | a credit card, mortgage or student loan is selected |
| Investments Holdings | $0.18 | `investments` requires it; `banking` adds it if a brokerage account is selected |
| Investments Transactions | $0.35 | the first `/investments/transactions/get`, which `refresh_investments` makes for every Item with Investments: the activity list, kept on purpose |
| Recurring Transactions | $0.15 | never: `/transactions/recurring/get` is not allowlisted |

- A subscription bills every month while a valid access token exists for
  the Item, even while it is broken (`ITEM_LOGIN_REQUIRED`). Only
  `/item/remove` (Unlink) stops it, and a product cannot be taken off an
  Item on its own.
- Everything the jobs call is inside those prices: `/accounts/get`,
  `/transactions/sync`, `/investments/holdings/get`,
  `/investments/transactions/get`, `/liabilities/get`, `/item/get`,
  `/institutions/get_by_id`.
- Per-call endpoints are refused in code, before any request
  (`plaid_client.ALLOWED_ENDPOINTS`, tested in `test_billing_guard.py`):
  `/accounts/balance/get` (Balance, not in the contract),
  `/transactions/refresh`, `/investments/refresh`. Allowlisting an endpoint
  is a billing decision: record it here.
- Rough size: a bank login is $0.30, plus $0.20 with a card, mortgage or
  student loan; an investment login is $0.53. Ten logins come to about
  $4–5 a month.

## Market data (benchmarks, investment history)

Not Plaid, and nothing about the household leaves: only series codes and dates.
`services/prices.py` fetches daily closes into `price_points`:

| provider | key | series | used for |
|---|---|---|---|
| FRED (St. Louis Fed) | `FRED_API_KEY` | `fred:SP500`, `fred:DJIA`, `fred:NASDAQ100` (price indexes, ~10 years), `fred:CBBTCUSD`, `fred:CPIAUCSL` (monthly) | S&P 500, Dow, Nasdaq-100 without dividends; Bitcoin; inflation |
| Tiingo | `TIINGO_API_KEY` | `tiingo:SPY`, `DIA`, `QQQ`, `VT`, `AGG`, `GLD` (dividend-adjusted close) | total-return benchmarks, 60/40 (VT + AGG, rebalanced daily) |
| Tiingo | same | `tiingo_close:<ticker>` (close as traded), `tiingo_crypto:<coin>usd` | pricing past holdings to rebuild investment history |

Keys are Railway variables only. FRED takes its key in the query string, so
logging silences httpx's request lines and redacts `api_key=`/`Token` values;
provider errors are logged by series and status, never by URL. A refresh
starts at the day after the last stored close (2014-01-01 the first time); a
429 stops that provider until the next run. A benchmark uses its first series
with data covering the range (Tiingo's fund first, FRED's index as the
fallback), and the API says which.

Performance (`services/performance.py`) is a time-weighted return: each day's
return is (value − flows) / previous value − 1, chained, where flows are cash
deposits, contributions, withdrawals and transfers (an account joining the
portfolio counts as a flow too). Values come from balance snapshots; before an
account's first snapshot, holdings are rebuilt by undoing later trades from
today's holdings and priced with `tiingo_close` (no price history: held at
today's price, reported as `coverage`). docs/80 "Investment performance".

## Sandbox testing

The `sandbox` Railway environment points at `sandbox.plaid.com`. In Link, use
institution "First Platypus Bank", user `user_good`, password `pass_good`.
OAuth flow: institution "Platypus OAuth Bank" exercises the redirect.

**Sandbox never sends a real text message.** Link's codes are fixed values:

| Where Link asks for a code | What to enter |
|---|---|
| Phone screen at the start of Link (Plaid's "returning user" / Remember Me step) | Phone `415-555-0011`, then code `123456` (any of `415-555-0011`, `-0012`, `-0013`, `-0136`, `-0137`, `-0138` works) |
| After signing in to a test bank with password `mfa_device` (device MFA) | `1234` |

The phone step is Plaid's own feature, on for every Plaid customer; there is
no dashboard switch. In production it sends real texts to the number you type.

To fire a webhook without waiting:

```bash
railway run --environment sandbox --service worker python - <<'PY'
from server.app.db import session
from server.app.models import PlaidItem
from server.app.plaid_client import plaid
from server.app.services.plaid_sync import access_token_for
with session() as s:
    item = s.query(PlaidItem).filter_by(status="active").first()
    print(plaid().sandbox_item_fire_webhook(access_token_for(item), "SYNC_UPDATES_AVAILABLE"))
PY
```

`/sandbox/item/reset_login` puts an item into ITEM_LOGIN_REQUIRED to test
the relink path.

## Going to production

Plaid's production checklist for an app like this: webhooks implemented (yes),
update mode implemented (yes), `/item/remove` on unlink (yes), redirect URI
registered (do it), privacy page public (yes). Before the first production
link: daily backups on and `TOKEN_ENCRYPTION_KEY` in the password manager;
then follow the linking-day checklist in docs/60 §2. Production secrets go only in
Railway variables; `PLAID_ENV` must equal `production` and `APP_ENV` must
equal `production` on the same service, or boot validation refuses to start.
