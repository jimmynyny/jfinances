# 10 — Architecture

jfinances is a private, tracking-only finance dashboard for one household.
It aggregates ~25 accounts through Plaid, keeps its own history, and shows
net worth, balances, transactions, holdings and liabilities. It does not
budget, pay, move money, or write to any institution.

This document is the **contract** every part of the system is built against.
If code and this doc disagree, fix one of them the same day.

## 1. Topology

```
                 Cloudflare (DNS proxy, WAF, Access)
                              │
     ┌────────────────────────┼─────────────────────────────┐
     │ jfinances.sellingtcg.com│ jfinances-hooks.sellingtcg.com│ jfinances-api.sellingtcg.com (iOS app)
     │   behind Access         │   NO Access (Plaid posts here)│   NO Access (app-issued bearer tokens)
     ▼                         ▼                               ▼
 ┌────────┐              ┌─────────┐                     (same `web` service, second hostname)
 │  web   │              │  hooks  │
 │FastAPI │              │ FastAPI │
 │SPA+API │              │ verify, │
 └───┬────┘              │ enqueue │
     │                   └────┬────┘
     │        ┌───────────────┘
     ▼        ▼
 ┌──────────────┐      ┌──────────┐
 │   Postgres   │◄─────│  worker  │  job queue consumer + scheduler
 │ (Railway)    │      │ (Plaid   │  (one replica, no HTTP)
 └──────────────┘      │  sync)   │
                       └──────────┘
```

One repo, one Docker image, three Railway services selected by `SERVICE_ROLE`
(`web`, `hooks`, `worker`). They share nothing but Postgres. Any one can be
redeployed without touching the others: the dashboard stays up while the
worker ships, and Plaid webhooks keep landing while the dashboard ships.

Why three and not one: a scheduler inside the web process means every web
replica runs every job, memory spikes take the dashboard down, and every
worker change forces a dashboard deploy. Those are all problems we have had
before on other projects.

## 2. Railway layout

| Project | `jfinances` (workspace DaedalusTCG), id `eb936bf8-51f3-4c47-88fe-a29ae508213a` |
|---|---|
| Environments | `production` (`442cb7a9-…`), `sandbox` (`eef4e965-…`, Plaid Sandbox) |
| Services | `Postgres`, `web`, `hooks`, `worker` — in both environments |
| Builder | Dockerfile at repo root (multi-stage: node builds the SPA, python runs) |
| Start | `./start.sh` dispatches on `SERVICE_ROLE` |
| Migrations | `python -m server.tools.release` (boot checks for that `SERVICE_ROLE`, then Alembic `upgrade head` under a Postgres advisory lock) runs at the start of `start.sh` for every role; `web` also runs it as its Railway pre-deploy command |
| Healthcheck | `web` and `hooks`: `GET /healthz` → 200 JSON, called by Railway directly (not through Cloudflare). `worker`: none (no HTTP) |
| Port | `web` and `hooks` listen on `PORT=8080`, the target port of their custom domains |
| Deploys | **Manual**: `railway up --service <web|hooks|worker> --ci`. Not linked to GitHub. |
| Backups | Postgres volume: weekly + monthly schedules today; daily recommended (Railway → Postgres → Backups, per environment) |

Hostnames (Cloudflare proxied CNAME → Railway, SSL Full (Strict)):

| Env | Dashboard (Access) | Webhooks (no Access) | Device API (no Access, future) |
|---|---|---|---|
| production | `jfinances.sellingtcg.com` | `jfinances-hooks.sellingtcg.com` | `jfinances-api.sellingtcg.com` |
| sandbox | `jfinances-sandbox.sellingtcg.com` | `jfinances-sandbox-hooks.sellingtcg.com` | `jfinances-sandbox-api.sellingtcg.com` |

Single-level subdomains only: Cloudflare Universal SSL does not cover
`a.b.sellingtcg.com`. The `*.up.railway.app` domains are deleted once
Cloudflare is in front, because they bypass Access.

## 3. Environment variables

Set per service in Railway. Never in the repo. `.env` is git-ignored.

| Name | web | hooks | worker | Meaning |
|---|---|---|---|---|
| `SERVICE_ROLE` | web | hooks | worker | Which process `start.sh` launches |
| `APP_ENV` | ✓ | ✓ | ✓ | `production` or `sandbox`; gates boot validation |
| `LOG_LEVEL` | ✓ | ✓ | ✓ | `info` / `debug` |
| `DATABASE_URL` | ✓ | ✓ | ✓ | `${{Postgres.DATABASE_URL}}` reference |
| `PLAID_ENV` | ✓ | ✓ | ✓ | `production` or `sandbox` |
| `PLAID_CLIENT_ID` | ✓ | ✓ | ✓ | From Plaid dashboard |
| `PLAID_SECRET` | ✓ | ✓ | ✓ | Production **or** sandbox secret, matching `PLAID_ENV` |
| `TOKEN_ENCRYPTION_KEY` | ✓ |  | ✓ | 32 random bytes, urlsafe-base64. Encrypts Plaid access tokens at rest |
| `SESSION_SECRET` | ✓ |  |  | Signs short-lived state cookies (Link OAuth) |
| `CF_ACCESS_TEAM` | ✓ |  |  | `daedalustcg` — the Zero Trust team name |
| `CF_ACCESS_AUD` | ✓ |  |  | Comma-separated AUD tags of the Access application(s) |
| `ALLOWED_USERS` | ✓ |  |  | Comma-separated emails that may use the app, **in order**: the first is `owner`, the rest `member`. Reconciled into `users` at every web boot (lock-serialised across uvicorn workers) |
| `PUBLIC_BASE_URL` | ✓ |  |  | `https://jfinances.sellingtcg.com` — builds the OAuth redirect URI |
| `HOOKS_BASE_URL` | ✓ | ✓ | ✓ | `https://jfinances-hooks.sellingtcg.com` — Plaid webhook base |
| `API_HOST` | ✓ |  |  | `jfinances-api.sellingtcg.com` (sandbox: `jfinances-sandbox-api.sellingtcg.com`). The hostname where phones use bearer tokens instead of Access; it serves `/api/*` only. Unset = no phone access |
| `PORT` | ✓ | ✓ |  | `8080`, set explicitly to match the custom domains' target port |
| `FRED_API_KEY` | ✓ | ✓ | ✓ | St. Louis Fed market data (benchmark indexes, Bitcoin, CPI); only the worker calls it. Optional: without it those benchmarks are off. docs/30 "Market data" |
| `TIINGO_API_KEY` | ✓ | ✓ | ✓ | Tiingo daily prices (dividend-adjusted fund benchmarks, holdings history); only the worker calls it. Optional |
| `DAILY_PRICES_UTC` | | | ✓ | Default `22:30`, after US markets close |

Boot validation (`config.validate_for_boot()`): in `APP_ENV=production` the
web service refuses to start if `CF_ACCESS_AUD`, `CF_ACCESS_TEAM`,
`TOKEN_ENCRYPTION_KEY`, `PLAID_SECRET` are missing or still `REPLACE_ME`, or
if `DEV_LOGIN_EMAIL` is set.

## 4. Authentication and authorization

**Humans (dashboard hostname).** Cloudflare Access with One-time PIN
(Google login can be added later) and an email allowlist. The app never
trusts the fact that a request arrived. Every `/api/*` request on the
dashboard hostname must carry `Cf-Access-Jwt-Assertion` (or the
`CF_Authorization` cookie). The app verifies it with PyJWT against
`https://{CF_ACCESS_TEAM}.cloudflareaccess.com/cdn-cgi/access/certs`,
requiring `exp`, `iat`, `aud ∈ CF_ACCESS_AUD`, `iss == https://{team}.cloudflareaccess.com`.
The `email` claim is lowercased and looked up in `users`; unknown or disabled
→ 403. Access proves *who*, our `users` table decides *whether*.

**Machines (hooks hostname).** No Access. Plaid signs every webhook with an
ES256 JWT in `Plaid-Verification`. We fetch the JWK by `kid` from
`/webhook_verification_key/get` (cached), verify the signature, require
`iat` within 5 minutes, and compare `request_body_sha256` to the raw body
with a constant-time compare. Anything else → 401 and the body is dropped.

**Phones (API hostname).** Modelled on vending's `mobile.py`. A phone links
once through Access (`GET /api/v1/mobile/link` on the dashboard hostname),
trades the two-minute code it is handed for an app-issued 256-bit token, and
sends `Authorization: Bearer` on the API hostname. Only SHA-256 hashes are
stored (`mobile_link_codes`, `api_tokens`). The token resolves to a `users`
row, so disabling the user stops the phone, and it is **read-only**:
`current_user` refuses anything but GET/HEAD/OPTIONS from a token. Details in
docs/40 §5.

**Principals.** `auth/deps.py` exposes `current_user()` which resolves a
`Principal(email, user_id, via="access"|"token")`. Routers depend on it and
never parse headers themselves.

## 5. Plaid integration

Products: `transactions`, `investments`, `liabilities` (`PLAID_PRODUCTS`).
Plaid hides any institution that lacks one of the *required* products, so
each Connect choice requires exactly one and asks for the rest only where
supported (`required_if_supported_products`, billed only when added):

| Connect choice (`kind`) | `products` | `required_if_supported_products` |
|---|---|---|
| `banking` — bank, card or loan | `transactions` | `liabilities`, `investments` |
| `investments` — brokerage, 401(k), IRA, 529 | `investments` | `transactions`, `liabilities` |

Jobs only call a product's endpoints when the Item reports that product
(`PlaidItem.has_product`), because calling them on an Item without the
product makes Plaid add it and start billing.

Link requests `days_requested=730`. `webhook` on every link token is
`{HOOKS_BASE_URL}/plaid/webhook`. `redirect_uri` is
`{PUBLIC_BASE_URL}/link/oauth` and must be registered in the Plaid dashboard
(Team Settings → API → Allowed redirect URIs) for both hostnames.

Flow:
1. `POST /api/v1/link/token` → server creates a link token (update mode when
   `item_id` is given), stores it in `link_sessions`, returns it.
2. Browser runs Plaid Link. For OAuth banks the browser is redirected back to
   `/link/oauth?oauth_state_id=…`; the SPA re-initialises Link with the same
   token (from `link_sessions`) and `receivedRedirectUri=window.location.href`.
3. `POST /api/v1/link/exchange {public_token, metadata}` → the duplicate
   guard checks the metadata against live items (409 = nothing exchanged,
   nothing billed), then `/item/public_token/exchange`; the access token is
   encrypted (AES-GCM via `cryptography`, key from `TOKEN_ENCRYPTION_KEY`)
   and committed to `plaid_items` before anything else runs. Accounts are
   fetched and upserted. A `sync_item` job is enqueued. (docs/30 "Never
   paying twice".)
4. Webhooks: `TRANSACTIONS.SYNC_UPDATES_AVAILABLE` → enqueue `sync_item`.
   `HOLDINGS.DEFAULT_UPDATE` / `INVESTMENTS_TRANSACTIONS.DEFAULT_UPDATE` →
   enqueue `refresh_investments`. `LIABILITIES.DEFAULT_UPDATE` → enqueue
   `refresh_liabilities`. `ITEM.ERROR` / `ITEM.LOGIN_REQUIRED` /
   `PENDING_EXPIRATION` / `USER_PERMISSION_REVOKED` → set `plaid_items.status`.
   The webhook body is **only a signal**; the worker always re-reads from Plaid.
5. `sync_item` job: `/transactions/sync` with the stored cursor, paginate
   while `has_more`, apply added/modified/removed, store the new cursor only
   after the whole page set succeeds. Then `/accounts/get` for balances.
   Last, cash and card balances before the account was linked are rebuilt
   from its transactions (`services/history.py`, docs/20 "Derived history").
6. Scheduler (worker): 03:00 UTC nightly `sync_item` for every active item;
   06:00 UTC daily `snapshot_balances` (one `balance_snapshots` row per
   account per day, manual accounts carried forward); daily
   `refresh_investments`; weekly `refresh_liabilities`.
7. Unlink: `DELETE /api/v1/items/{id}` calls `/item/remove`, marks the item
   `removed`, keeps history (accounts/transactions stay, flagged).
8. Re-link / Add accounts: `POST /api/v1/items/{id}/relink` → link token in
   update mode with account selection. Same Item, nothing new billed.

The Plaid client refuses every endpoint outside
`plaid_client.ALLOWED_ENDPOINTS`, so per-call billing (`/accounts/balance/get`,
the refresh endpoints) cannot happen by accident. The "Refresh" button reads
`/accounts/get` (free), rate limited to once per item per 10 minutes.

## 6. Data model (Postgres, Alembic-managed)

All ids are UUIDv7-ish (`uuid.uuid4()` is fine). Money is `numeric(18,2)`.
Timestamps are `timestamptz`. Plaid raw payloads are kept in `jsonb` columns
named `raw` so we can backfill fields without re-fetching.

| Table | Key columns |
|---|---|
| `users` | `email` unique, `display_name`, `role` (`owner`/`member`), `disabled_at` |
| `plaid_items` | `item_id` unique, `institution_id`, `institution_name`, `access_token_enc` bytea, `status` (`active`,`login_required`,`error`,`pending_expiration`,`removed`), `error_code`, `consent_expires_at`, `transactions_cursor`, `last_synced_at`, `products` text[], `created_by` → users |
| `accounts` | `item_id` → plaid_items (null for manual), `plaid_account_id` unique nullable, `kind` (`plaid`/`manual`), `name`, `official_name`, `mask`, `type`, `subtype`, `manual_category` (`real_estate`,`vehicle`,`cash`,`other_asset`,`other_liability`), `iso_currency`, `current_balance`, `available_balance`, `credit_limit`, `balance_updated_at`, `is_hidden`, `display_order`, `is_liability` (derived at write time from type/manual_category) |
| `balance_snapshots` | `account_id`, `as_of` date, `current_balance`, `available_balance`, `source` (`plaid`/`manual`/`carry`), unique(`account_id`,`as_of`) |
| `transactions` | `account_id`, `plaid_transaction_id` unique, `date`, `authorized_date`, `amount` (Plaid sign: positive = money out), `iso_currency`, `name`, `merchant_name`, `pending`, `pending_transaction_id`, `category_primary`, `category_detailed`, `payment_channel`, `user_category`, `notes`, `removed_at`, `raw` |
| `securities` | `plaid_security_id` unique, `ticker`, `name`, `type`, `close_price`, `close_price_as_of`, `iso_currency`, `raw` |
| `holdings` | `account_id`, `security_id`, `quantity`, `cost_basis`, `institution_price`, `institution_price_as_of`, `institution_value`, unique(`account_id`,`security_id`) |
| `investment_transactions` | `account_id`, `plaid_investment_transaction_id` unique, `date`, `name`, `type`, `subtype`, `quantity`, `amount`, `price`, `fees`, `security_id`, `raw` |
| `liabilities` | `account_id` unique, `kind` (`credit`/`mortgage`/`student`), `interest_rate_pct`, `next_payment_due_date`, `minimum_payment`, `last_payment_amount`, `last_payment_date`, `origination_date`, `origination_principal`, `raw` |
| `jobs` | `kind`, `payload` jsonb, `status` (`queued`,`running`,`done`,`failed`), `run_after`, `attempts`, `max_attempts`, `last_error`, `locked_at`, `finished_at` |
| `webhook_events` | `item_id`, `webhook_type`, `webhook_code`, `payload`, `received_at`, `processed_at`, `error` |
| `link_sessions` | `user_id`, `link_token`, `item_id` nullable, `expires_at` |
| `api_tokens` | `user_id`, `name`, `token_hash`, `last_used_at`, `revoked_at` |

Net worth = Σ assets − Σ liabilities, where liability accounts are `type in
(credit, loan)` or manual `other_liability`; their balances are stored as
Plaid gives them (positive owed) and subtracted.

## 7. HTTP API (web service, prefix `/api/v1`, JSON)

All routes require a principal except `/healthz`. Errors are
`{"error": {"code": "...", "message": "..."}}`.

| Method & path | Purpose |
|---|---|
| `GET /me` | `{email, display_name, role}` |
| `GET /overview` | `{net_worth, assets, liabilities, change_1m:{amount,pct}, groups:[{key,label,total,change_1m,accounts:[…]}], as_of}` |
| `GET /networth/history?range=1m|3m|6m|1y|all` | `[{date, assets, liabilities, net}]` from `balance_snapshots` |
| `GET /accounts` | all accounts incl. hidden, with item status and `last_updated` |
| `PATCH /accounts/{id}` | `{name?, is_hidden?, display_order?}` |
| `PUT /accounts/order` | `{account_ids}`: one group, top to bottom → drag-and-drop reorder |
| `POST /accounts/manual` | `{name, manual_category, value, iso_currency?}` → account + snapshot |
| `PUT /accounts/{id}/value` | `{value, as_of?, note?}` manual accounts only |
| `POST /accounts/{id}/refresh` | latest balances Plaid has (`/accounts/get`), rate limited |
| `GET /items` | items with status, institution, account count, last sync |
| `POST /items/{id}/sync` | enqueue `sync_item` |
| `POST /items/{id}/relink` | `{link_token}` in update mode (Re-link, Add accounts) |
| `DELETE /items/{id}` | `/item/remove` and mark removed |
| `POST /link/token` | `{kind?: banking|investments, item_id?}` → `{link_token, expiration, link_session_id, mode, kind}` |
| `POST /link/exchange` | `{public_token, metadata?}` → item summary |
| `GET /transactions?from&to&account_id&q&category&pending&page&page_size` | paged list, newest first, with `sum`; `flow` and Insights' groupings list the rows behind an Insights number (docs/80) |
| `PATCH /transactions/{id}` | `{user_category?, notes?, business?}` |
| `GET /transactions/ids`, `PATCH /transactions` | every id a filter matches; several transactions at once (category, business or personal) |
| `GET /transactions/summary?from&to&group_by=category|month|account` | `[{key,label,total,count}]` |
| `GET /holdings` | accounts → holdings with security and value |
| `GET /liabilities` | liability details per account |
| `GET /insights/{cashflow,spending,compare,merchants,patterns}` | Insights slices of transactions (docs/80 "Insights") |
| `GET /insights/{networth,homes,loans,cards}` | net worth by kind, home equity, loan payoff, card costs |
| `GET/POST/PATCH/DELETE /dashboard…` | each person's Overview widgets (docs/80 "Dashboard") |
| `GET/PATCH /recurring…`, `GET /alerts`, `POST /alerts/dismiss` | subscriptions found in transactions, alerts (docs/80) |
| `GET /sync/status` | items with last sync, queued/running jobs, last webhook |
| `GET /healthz` | `{ok:true, service, env, db:"ok"}` (public) |

Hooks service: `POST /plaid/webhook` (verified), `GET /healthz`.

## 8. Frontend

Vite + React 19 + TypeScript. Lives in `frontend/`. Consumes the design
system in `packages/ui` (workspace package `@mooney/ui`). Routes:
`/` overview (each person's dashboard: widgets in `frontend/src/dashboard/`, pinned from Insights), `/accounts`, `/transactions`, `/insights` (cash flow, money flow,
income sources, spending by category with drill-down, merchants, patterns,
a year-earlier comparison, subscriptions, upcoming charges and alerts; views in
`frontend/src/insights/`), `/investments`, `/liabilities`,
`/settings` (items, manual assets, subscriptions, sync status), `/link/oauth` (Plaid OAuth
return). Data via `fetch` to `/api/v1` with `credentials: "include"`; the
browser already carries the Access cookie.

The SPA is built in the Docker image and served by FastAPI at `/` with an
SPA fallback. `/about` serves `index.html` from the repo root (the Plaid
review page) so the privacy statement also lives on the app domain.

## 9. Repo layout

```
Dockerfile            multi-stage build (node → python)
start.sh              SERVICE_ROLE dispatch
pyproject.toml        python deps (uv)
server/app/           FastAPI apps, auth, plaid, jobs, models
server/alembic/       migrations
server/tools/         release.py (migrate + checks), seed.py, sandbox_smoke.py
ops/                  cloudflare_access.py (Access policy + apps as code)
frontend/             Vite SPA
packages/ui/          design system (@mooney/ui)
docs/                 you are here
index.html            Plaid review / privacy page (also GitHub Pages)
```
