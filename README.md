# jfinances

Private, read-only personal finance tracker for the Mooney household.
Connects ~25 accounts through [Plaid](https://plaid.com), keeps its own
history in Postgres, and shows net worth, balances, transactions, holdings
and liabilities on a dashboard. No budgeting, no payments, no third parties.

- **Live:** https://jfinances.sellingtcg.com (Cloudflare Access, household only)
- **Sandbox:** https://jfinances-sandbox.sellingtcg.com (Plaid Sandbox data)
- **Privacy / Plaid review page:** https://jimmynyny.github.io/jfinances/

## How it is built

| Layer | Choice |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, `plaid-python` |
| Frontend | Vite + React 19 + TypeScript, design system `@mooney/ui` in `packages/ui` |
| Database | Railway Postgres with daily + weekly backups |
| Services | `web` (SPA + API), `hooks` (Plaid webhooks), `worker` (sync jobs + scheduler) — one image, three Railway services |
| Edge | Cloudflare DNS + Access (one-time PIN, email allowlist); app re-verifies the Access JWT |
| Deploys | Manual: `railway up --service <name> --ci` |
| Phones | Native apps with home-screen widgets, editing and connecting banks as the dashboard does: SwiftUI in `ios/` (docs/85), Jetpack Compose in `android/` (docs/86) |

Full documentation is in [`docs/`](docs/00-overview.md). Start with
[`docs/10-architecture.md`](docs/10-architecture.md).

## Local development

```bash
uv sync                      # python deps into .venv
npm install                  # frontend + design system
cp .env.example .env         # fill in sandbox Plaid keys; DEV_LOGIN_EMAIL bypasses Access locally
npm run dev                  # Vite on :5173 proxying /api to :8000
uv run uvicorn server.app.web:app --reload --port 8000
uv run python -m server.app.worker
```

Tests and lint: `uv run pytest && uv run ruff check server && npm run typecheck && npm run lint`.
