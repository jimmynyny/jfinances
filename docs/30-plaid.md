# 30 — Plaid

Products: **Transactions**, **Investments**, **Liabilities**. Country US.
History on link: 730 days (Plaid's maximum). Client: `server/app/plaid_client.py`,
a thin httpx wrapper (see the module docstring for why not the generated SDK).

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
  │ POST /api/v1/link/exchange ─────►│ /item/public_token/exchange ─►│
  │                                  │ encrypt+store access_token    │
  │                                  │ /accounts/get, enqueue jobs   │
  │◄──── item summary                │                               │
```

Update mode (re-auth, consent renewal, adding accounts):
`POST /api/v1/items/{id}/relink` returns a link token created with the item's
access token. When Link finishes there is **no new public token**; the SPA
calls `POST /api/v1/link/update-complete {link_session_id}` which clears the
error and queues a sync.

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
| ITEM / NEW_ACCOUNTS_AVAILABLE | enqueue `sync_item` (accounts upsert picks them up) |
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
- **`refresh_accounts`**: `/accounts/get` (cached balances, cheap) and a
  snapshot. `realtime=True` uses `/accounts/balance/get`, which is billed per
  call, and is only reachable from the Refresh button, rate limited to once
  per item per 10 minutes.
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
| every 10 min | release stale `running` jobs, prune old ones |

Times are settings (`NIGHTLY_SYNC_UTC` etc.) if they ever need to move.

## Cost model (what actually bills)

- Transactions, Investments, Liabilities: each is a per-Item monthly charge
  while the product is enabled on that Item. With ~25 items this is the bill.
  Investments and Liabilities are only requested for items that have those
  account types; Plaid still bills per product per item that was *initialised*
  with the product, so link with only the products you need. Today Link asks
  for all three; narrowing that per institution is a one-line change in
  `PlaidClient.link_token_create`.
- `/accounts/balance/get` (real-time) is per call. Never scheduled.
- `/accounts/get`, `/transactions/sync`, `/investments/*`, `/liabilities/get`
  are included in the product price.

## Sandbox testing

The `sandbox` Railway environment points at `sandbox.plaid.com`. In Link, use
institution "First Platypus Bank", user `user_good`, password `pass_good`.
OAuth flow: institution "Platypus OAuth Bank" exercises the redirect.

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
registered (do it), privacy page public (yes). Production secrets go only in
Railway variables; `PLAID_ENV` must equal `production` and `APP_ENV` must
equal `production` on the same service, or boot validation refuses to start.
