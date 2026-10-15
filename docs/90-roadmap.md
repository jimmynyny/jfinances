# 90 — Roadmap and reserved decisions

Things deliberately *not* built yet, with the hooks left in place so they
do not require a redesign.

## Phone apps: next steps

The link flow and phone tokens are built for iPhone and Android (docs/40 §5,
docs/85, docs/86), and since 2026-10-15 a phone edits as the dashboard does.
Reserved:

- Push notifications for alerts (needs APNs keys, FCM for Android, and a sender in `worker`).
- Statement imports from the phone (the API allows them; the apps have no file picker for them yet).

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
