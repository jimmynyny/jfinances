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
- Never call a Plaid product endpoint for an Item that lacks the product (`PlaidItem.has_product`): Plaid would add and bill it.
- Plaid endpoints go through `plaid_client.ALLOWED_ENDPOINTS`; allowlisting one is a billing decision (docs/30 "Cost model").
- Never exchange a public token the duplicate guard refused, and commit an access token before anything else can fail: a lost token is an Item billed forever.
- Cloudflare Access is managed by `ops/cloudflare_access.py`; change it there, not by hand.
- Keep `web`, `hooks`, `worker` independent: shared code is fine, shared process is not.

## Shipping
```
git push
railway environment sandbox && railway up --service web --ci   # etc.
railway environment production && railway up --service web --ci
```
`railway up` uploads the working tree, uncommitted files included: deploy from a clean tree (stash work in
progress first) so what ships is a commit. A Railway variable change redeploys every service from its last
upload; older code booting on a newer schema logs it and starts (`server.tools.release`).
Every service runs migrations before it starts (`start.sh` → `server.tools.release`, advisory-locked; `web` also in pre-deploy), so there is no required deploy order. Keep migrations backward compatible with the code still running in the other services.

## Code
- Python: `uv run ruff check server && uv run pytest` before pushing.
- Frontend: `npm run typecheck && npm run lint && npm run build`.
- Android: `cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug`. The iPhone and Android apps are
  twins (docs/85, docs/86): a screen or widget changed in one is changed in the other.
- Design system lives in `packages/ui` (`@mooney/ui`). New UI goes through it; do not hand-roll styles in `frontend/`.
- Money is `numeric`, never float. Plaid's sign convention (positive = outflow) is preserved in `transactions.amount`.
- UI copy never names Plaid (or other plumbing): say bank, connection, institution. The public privacy page is the exception (Plaid's terms require the disclosure).

## Docs
If you change behaviour, update the matching `docs/*.md` in the same commit. New env var → `docs/10-architecture.md` §3 and the Railway service.
