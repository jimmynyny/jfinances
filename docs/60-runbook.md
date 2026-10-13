# 60 — Runbook

Day-two operations. Railway project `jfinances`, workspace DaedalusTCG.
Environments `production` and `sandbox`; services `web`, `hooks`, `worker`,
`Postgres`.

## 1. Deploy

Deploys are manual. Nothing ships on `git push`.

```bash
cd ~/Dropbox/Documents/__SCRIPTS/jfinances
railway environment production          # or: sandbox
railway up --service web --ci           # runs server/tools/release.py first (migrations)
railway up --service hooks --ci
railway up --service worker --ci
```

All three build the same Dockerfile; deploy `web` first because it runs the
migration. Watch a deploy with `railway logs --service web`. The newest
deployment must reach **SUCCESS** before you call it done; `--ci` streams
and exits non-zero on failure.

Verify:

```bash
curl -sI https://jfinances.sellingtcg.com/              # 302 to daedalustcg.cloudflareaccess.com: Access is on
curl -s https://jfinances-hooks.sellingtcg.com/healthz  # 200 JSON (hooks is outside Access)
railway logs --service worker | grep "worker started"
```

Rollback: Railway → service → Deployments → previous → Redeploy. Migrations
are forward-only; write a new migration rather than downgrading.

## 2. First-time setup checklist

1. Set the real values on each service where it says `REPLACE_ME`:
   `PLAID_CLIENT_ID`, `PLAID_SECRET` (web, hooks, worker), `CF_ACCESS_AUD`
   (web). `TOKEN_ENCRYPTION_KEY` and `SESSION_SECRET` are already set.
2. Deploy web → hooks → worker.
3. Register the redirect URI in the Plaid dashboard (docs/30 §1).
4. Open the dashboard, log in via Access, Settings → Link an account.
5. Check Settings → Sync status: the item should go `active`, jobs `done`,
   a webhook should arrive within a minute.

### Linking day (production: every Item bills monthly, docs/30 "Cost model")

Before the first link:
- Railway → production Postgres → Backups: **Daily** on (§6).
- `TOKEN_ENCRYPTION_KEY` (production web → Variables) copied into the
  password manager. Without it every stored token is unreadable.

While linking:
- One connection per **login**. In Plaid's account picker, tick every
  account you want from that login in one go.
- Banks, cards, loans → "Bank, card or loan". Brokerages, 401(k)s, IRAs,
  529s → "Investment or retirement".
- A joint account visible under both people's logins: tick it under one
  login only. The duplicate guard asks if it sees it twice (docs/30).
- Missed an account? Settings → that connection → **Add accounts**. Never
  Connect the same login again.

After:
- Settings: each connection's product badges are what Plaid bills.
- Take a manual backup (§6).

## 3. Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `boot check failed: PLAID_SECRET is unset or a placeholder` and the service exits 78 | variable still `REPLACE_ME` | set it, redeploy |
| `/healthz` on the dashboard host returns a login page | expected: the whole dashboard host is behind Access | check health in Railway (internal healthcheck) or on the hooks host |
| Link does not list Robinhood / a 529 plan | used "Bank, card or loan" | choose "Investment or retirement" (requires only the investments product) |
| Deploy fails in pre-deploy with exit 78 | that service's boot check failed | `railway logs --service <svc>`; the `config:` lines name the variable |
| API returns `auth.bad_access_jwt` | `CF_ACCESS_AUD` does not match the app's AUD tag, or `CF_ACCESS_TEAM` wrong | copy the AUD from Zero Trust → Applications → the app → Overview |
| API returns `auth.not_allowed` (403) | email passed Access but is not in `ALLOWED_USERS` | add it, redeploy web (seeding runs at boot) or `railway run --service web python -m server.tools.seed` |
| Item shows `login_required` | bank asked for re-auth / MFA | Settings → Relink; Plaid Link opens in update mode |
| Item shows `pending_expiration` | OAuth consent (e.g. Chase) expiring | Relink before `consent_expires_at` |
| Webhooks all 401 in hooks logs | `PLAID_CLIENT_ID`/`PLAID_SECRET` on **hooks** wrong (key fetch fails) or clock skew | fix variables; check `iat` window |
| No webhooks at all | item was linked while `HOOKS_BASE_URL` was wrong | `PlaidClient.item_webhook_update(token, settings().plaid_webhook_url)` from a `railway run` shell, or relink |
| Job `failed` in Sync status | see `last_error` | fix the cause; re-queue with `POST /api/v1/items/{id}/sync` |
| Net worth chart has a flat gap | worker was down at 06:00 UTC | `POST /api/v1/sync/snapshot`, or just wait a day; history carries forward |
| Memory climbs on worker | a huge initial sync | it's one process; Railway restarts it (policy ALWAYS). Jobs resume from the cursor |

## 4. Rotating secrets

- **Plaid secret**: rotate in the Plaid dashboard, update `PLAID_SECRET` on
  web, hooks, worker. Items are unaffected.
- **TOKEN_ENCRYPTION_KEY**: every stored access token must be re-encrypted.
  Procedure: set `TOKEN_ENCRYPTION_KEY_NEXT` on worker, run a one-off
  `railway run --service worker python -m server.tools.rekey` (to be written
  when first needed: decrypt with old, encrypt with new, swap variables).
  Until then, the simpler path is to relink every item after changing the
  key. Do not lose the key: without it every item must be relinked.
- **SESSION_SECRET**: just change it.
- **Cloudflare Access**: rotating the application AUD means updating
  `CF_ACCESS_AUD`.

## 5. Relinking / unlinking

Relink: Settings → the item → Re-link (shown when it needs attention).
Add accounts: Settings → the item → Add accounts (always there for an active
item; highlighted with "new accounts available" after Plaid's
NEW_ACCOUNTS_AVAILABLE webhook). Both: `POST /items/{id}/relink` → Link in
update mode → `POST /link/update-complete`. Same Item, nothing new billed.
Unlink: Settings → the item → Unlink. Backend: `/item/remove` at Plaid, item
`removed`, accounts `closed_at`, history kept. Plaid stops billing that item;
connecting it again later is a new Item, billed again.

A billed Item with no token on our side should not happen (the exchange
commits the token first, and removes the Item at Plaid if it cannot). If it
ever does, the logs name its `item_id`; ask Plaid support to remove it.

## 6. Backups and restore

Railway → Postgres service → Backups: Weekly (kept 27 days) and Monthly
(kept 89 days) are on. In production, Daily (kept 6 days) is required: the
access tokens live only in this database, so a restore from an older backup
loses the token of every Item linked since, and those Items keep billing
with no way to unlink them. Manual backup after a linking session and
before anything scary.
Restore: pick the backup → Restore → Railway stages a new volume → Deploy.
Restores land in the same project and environment only. After a restore,
run `POST /api/v1/sync/all` to catch up; cursors in the restored rows make
that incremental.

A logical dump for off-platform safekeeping:

```bash
railway connect Postgres   # or: railway variables --service Postgres to get DATABASE_URL
pg_dump "$DATABASE_URL" --no-owner -Fc > jfinances-$(date +%F).dump
```

The dump contains encrypted tokens only; it is useless without
`TOKEN_ENCRYPTION_KEY`, which is the point.

## 7. Reading logs

JSON lines. Useful filters:

```bash
railway logs --service worker | grep '"job_kind"'
railway logs --service hooks  | grep rejected
railway logs --service web    | grep '"status": 5'
```

Every web request has `request_id`; it is also returned as `X-Request-Id`.

## 8. Local development

```bash
uv sync --extra dev
createdb jfinances_dev
export DATABASE_URL=postgresql://localhost/jfinances_dev APP_ENV=local DEV_LOGIN_EMAIL=you@example.com \
       ALLOWED_USERS=you@example.com PLAID_ENV=sandbox PLAID_CLIENT_ID=… PLAID_SECRET=… \
       TOKEN_ENCRYPTION_KEY=$(python -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')
uv run alembic -c server/alembic.ini upgrade head
SERVICE_ROLE=web   ./start.sh                 # :8080
SERVICE_ROLE=worker ./start.sh                # another shell
uv run pytest                                 # TEST_DATABASE_URL=… to include integration tests
```

For design and debugging, load a realistic household, never real data: 20
accounts in every group, two years of daily balances, transactions, holdings,
liability details, and PNC in `login_required`. It refuses to run unless
`APP_ENV=local` and the database is on localhost. Do not run the worker
against it: the demo items have fake tokens, so every Plaid call fails and the
items flip to an error state.

```bash
uv run python -m server.tools.demo_seed --reset
```

Webhooks cannot reach a laptop; use the sandbox Railway environment for that.
