# jfinances — working rules for Claude Code

Private household finance tracker (Plaid → Postgres → dashboard). Two users.
Read `docs/00-overview.md` then `docs/10-architecture.md` before changing
anything structural.

## Non-negotiables
- **Never** commit secrets. All secrets are Railway variables. `.env` is ignored.
- **Never** log, return, or print Plaid access tokens, Cloudflare JWTs, or API tokens.
- **Never** add anything that writes to a financial institution. Read-only app.
- **Never** auto-deploy from GitHub. Deploys are `railway up --service <name> --ci`, per service, sandbox first.
- `worker` runs **one** replica. Do not scale it.
- Keep `web`, `hooks`, `worker` independent: shared code is fine, shared process is not.

## Shipping
```
git push
railway environment sandbox && railway up --service web --ci   # etc.
railway environment production && railway up --service web --ci
```
`web` runs migrations in its pre-deploy step. Ship `web` before `worker` when a migration matters.

## Code
- Python: `uv run ruff check server && uv run pytest` before pushing.
- Frontend: `npm run typecheck && npm run lint && npm run build`.
- Design system lives in `packages/ui` (`@mooney/ui`). New UI goes through it; do not hand-roll styles in `frontend/`.
- Money is `numeric`, never float. Plaid's sign convention (positive = outflow) is preserved in `transactions.amount`.

## Docs
If you change behaviour, update the matching `docs/*.md` in the same commit. New env var → `docs/10-architecture.md` §3 and the Railway service.
