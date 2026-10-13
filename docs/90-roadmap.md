# 90 — Roadmap and reserved decisions

Things deliberately *not* built yet, with the hooks left in place so they
do not require a redesign.

## iOS app (future)

Modelled on vending's mobile flow (`vending.sellingtcg.com/server/app/auth/mobile.py`).

- Hostname `jfinances-api.sellingtcg.com` → the same `web` service, **not**
  behind Access. `API_HOST` is already a variable; `auth/deps.py` already
  switches to bearer-token auth when `Host == API_HOST`.
- Link flow: the phone opens `https://jfinances.sellingtcg.com/settings/devices/link?nonce=N`
  in `ASWebAuthenticationSession` (Access login happens there), the server
  302s to `jfinances://linked?code=C&nonce=N`, the app POSTs
  `/v1/devices/link {code, nonce, name}` on the API host and receives a
  token stored in the Keychain.
- `api_tokens` table exists now (sha256 of token, `revoked_at`). Revoking the
  user revokes every device on its next request.
- Rate limit unknown tokens per IP in-process, and rely on Cloudflare WAF
  rate rules on the API host as the outer wall.
- Read-only scope first. Any write endpoint on the API host must be a
  deliberate decision.

## Google login in Access

The Zero Trust team currently uses Google Workspace for `webuytcg.com` and
One-time PIN. Both household accounts are Gmail, so PIN is used. Adding a
generic Google IdP later is a Zero Trust setting; no app change.

## Tailoring (Jimmy's list, to be discussed)

- Custom groupings beyond Plaid's type/subtype (e.g. "529s", "Kids").
- Rules for recategorising recurring merchants.
- Offline assets with scheduled depreciation (vehicles) or an external
  valuation source (houses).
- Alerts (large transaction, item needs re-link) via email/push.
- Exports (CSV, yearly summaries for taxes).

## Hardening backlog

- **Content-Security-Policy on `web`.** Security headers are set except CSP.
  A correct policy must allow Plaid Link (`cdn.plaid.com` scripts, `*.plaid.com`
  frames and connections), the Google Fonts the SPA uses, and the inline
  pre-paint theme script (by hash). Ship it only after testing Link in a real
  browser in sandbox, including an OAuth bank, or it will silently break
  connecting accounts.
- **Cloudflare rate limit on the hooks hostnames.** Plaid sends a handful of
  webhooks a day; a WAF rate rule caps abuse before it reaches Railway.

## Explicitly out of scope

Budgets, bill pay, transfers, investment trading, anything that writes to an
institution. The Plaid review page says read-only; keep it true.
