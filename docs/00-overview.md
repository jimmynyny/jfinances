# 00 — Overview and reading order

jfinances is the Mooney household's private finance tracker: one place to
see every account, every transaction, holdings, loans, and net worth over
time. Two users. Read-only against the banks. Powered by Plaid, hosted on
Railway, gated by Cloudflare Access.

Read in this order:

| Doc | What it answers |
|---|---|
| `10-architecture.md` | The contract: services, hostnames, env vars, auth, Plaid flow, data model, API. **Start here.** |
| `20-data-model.md` | Every table and column, and why. |
| `30-plaid.md` | Link, OAuth, webhooks, sync, costs, dashboard settings, sandbox testing. |
| `40-auth-and-security.md` | Threat model, Access JWT, webhook verification, encryption at rest, token hygiene. |
| `50-deploy-railway.md` | IDs, service settings, how to ship, backups, rollback. |
| `55-cloudflare.md` | DNS, TLS, Access application and policies. |
| `60-runbook.md` | Operations: secrets rotation, re-link, restore, logs, common failures. |
| `70-design-system.md` | `@mooney/ui`: tokens, components, charts, reuse in other dashboards. |
| `80-api.md` | Every endpoint with examples. |
| `90-roadmap.md` | Phone writes, Google login, tailoring ideas, out-of-scope list. |

Principles that every change should respect:

1. **Read-only.** Nothing here moves money. Ever.
2. **Secrets live in Railway.** Never in git, never in logs, never in a
   response body. Plaid access tokens are encrypted at rest.
3. **Cloudflare proves who; the app decides whether.** Every request is
   verified in code, not just assumed to have come through Access.
4. **Services are independent.** `web`, `hooks`, `worker` deploy separately
   and share only Postgres.
5. **Webhooks are signals.** The worker always re-reads from Plaid.
6. **Document as you go.** If you change behaviour, change the doc in the
   same commit.
