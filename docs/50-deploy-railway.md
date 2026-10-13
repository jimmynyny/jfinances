# 50 — Deploying on Railway

Deploys are **manual and per service**. GitHub is the source of truth for
code; Railway only ever receives what you push from this directory with the
CLI. Nothing auto-deploys on `git push`.

## Identifiers

| Thing | Value |
|---|---|
| Workspace | DaedalusTCG |
| Project | `jfinances` — `eb936bf8-51f3-4c47-88fe-a29ae508213a` |
| Environment `production` | `442cb7a9-4019-4de3-a562-aadaa1db284d` |
| Environment `sandbox` | `eef4e965-23bf-453d-821b-54c3d5782f07` |
| Service `web` | `c8de032f-daeb-458d-881e-cc013fb3a66d` |
| Service `hooks` | `04497853-6286-460e-8776-be1bfb0d4cfe` |
| Service `worker` | `a2a00ab2-28fc-465d-a083-e370027f378d` |
| Service `Postgres` (production) | `9f79573f-b04a-4de6-9ebe-d5365c95f28a` |

Dashboard: https://railway.com/project/eb936bf8-51f3-4c47-88fe-a29ae508213a

## One-time setup on a machine

```bash
brew install railway          # or: npm i -g @railway/cli
railway login                 # opens a browser; use `--browserless` on a headless box
cd jfinances
railway link --project eb936bf8-51f3-4c47-88fe-a29ae508213a --environment production --service web
railway status                # confirm project / environment / service
```

`railway link` writes to `~/.railway`, not to the repo. The repo has no
`railway.json`: Railway deprecated config-as-code, so service settings
(start command, healthcheck, pre-deploy, restart policy) live in the service
settings and are recorded in the table below. If you ever recreate a
service, set these by hand.

| Setting | web | hooks | worker |
|---|---|---|---|
| Builder | Dockerfile | Dockerfile | Dockerfile |
| Start command | `./start.sh` | `./start.sh` | `./start.sh` |
| Pre-deploy | `python -m server.tools.release` | same | same |
| `PORT` variable | `8080` | `8080` | — |
| Custom domain target port | 8080 | 8080 | — |
| Healthcheck | `/healthz`, 120 s | `/healthz`, 120 s | — |
| Restart policy | ON_FAILURE ×5 | ON_FAILURE ×5 | ALWAYS |
| Replicas | 1 | 1 | **1 — never more** (the scheduler would double-fire) |

Variables per service are listed in `docs/10-architecture.md` §3.

## Shipping a change

```bash
# 1. commit and push to GitHub as usual
git push

# 2. choose the environment (sandbox first, then production)
railway environment sandbox

# 3. deploy the services you changed. Each one is an independent build of
#    the same image; the dashboard stays up while the worker ships.
railway up --service worker --ci
railway up --service hooks  --ci
railway up --service web    --ci     # every service migrates in pre-deploy, then swaps

# 4. verify
railway deployment list --service web --json | head -40
curl -s https://jfinances-sandbox-hooks.sellingtcg.com/healthz
curl -sI https://jfinances-sandbox.sellingtcg.com/          # 302 to daedalustcg.cloudflareaccess.com = Access is on

# 5. repeat for production
railway environment production
railway up --service worker --ci && railway up --service hooks --ci && railway up --service web --ci
```

`--ci` streams the build and exits non-zero on failure, which is what you
want from a script. `--detach` returns at "queued" and tells you nothing.

Every service runs `python -m server.tools.release` as its pre-deploy step:
boot checks for that service's role, then `alembic upgrade head` under a
Postgres advisory lock. Whichever service deploys first migrates; the rest
find the schema at head. So there is no required deploy order, as long as
migrations stay backward compatible with the code still running elsewhere
(add tables/columns now, drop them in a later release).

### Rollback

Railway → service → Deployments → pick the previous SUCCESS → "Redeploy".
Migrations are forward-only; write a new migration rather than downgrading.

## Postgres

Railway's Postgres template with a volume. `DATABASE_URL` is injected into
the three app services as a reference variable `${{Postgres.DATABASE_URL}}`,
so rotating the DB password in Railway propagates automatically.

### Backups (required — this is personal financial data)

Railway → `Postgres` service → **Backups** tab. As of 2026-10-13 **Weekly**
(kept 27 days) and **Monthly** (kept 89 days) are on. Adding **Daily** (kept
6 days) is recommended: transactions can be re-pulled from Plaid, but daily
balance snapshots (the net-worth history) and your edits cannot. Do this in
**both** environments. Backups are incremental copy-on-write and cost cents.

Restore: same tab → pick a backup → Restore → review the staged change →
Deploy. The old volume stays attached-but-unmounted so nothing is lost.

### Manual dump

```bash
railway environment production
railway connect Postgres          # psql shell
# or
railway run --service web pg_dump "$DATABASE_URL" > backup.sql   # from inside the Railway network
```

## Environments

`sandbox` is a full copy: its own Postgres, its own hostnames, `PLAID_ENV=sandbox`
and the Plaid **sandbox** secret. Use it to test Link, webhooks
(`/sandbox/item/fire_webhook`) and migrations before production. Jimmy
develops remotely, so this stands in for a local environment.

## Removing the Railway-provided domain

A `*.up.railway.app` domain bypasses Cloudflare and therefore Access.
Delete any Railway-provided domain from each service's Settings →
Networking (the CLI cannot delete domains). `hooks` in production has
`hooks-production-3bcd.up.railway.app` from initial testing; delete it.

## Sandbox end-to-end check

Proves Plaid credentials, exchange + encryption, the worker, and the signed
Plaid → Cloudflare → hooks path, without a browser. Sandbox only (it refuses
production):

```bash
railway ssh --service worker --environment sandbox -- \
    python -m server.tools.sandbox_smoke --email jimmy.mooney@gmail.com
```

It leaves a First Platypus Bank item linked so the sandbox dashboard has
data; unlink it in Settings when you are done with it.
