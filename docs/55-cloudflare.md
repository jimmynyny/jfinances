# 55 — Cloudflare: DNS, TLS and Access

Everything reaches Railway through Cloudflare. Humans are gated by Zero
Trust Access; Plaid's webhook host is not (Plaid cannot log in), and is
protected by signature verification in the app instead.

Zone: `sellingtcg.com`. Zero Trust team: `daedalustcg` →
`https://daedalustcg.cloudflareaccess.com`.

## 1. DNS

Four proxied CNAMEs (orange cloud ON). Targets come from Railway → service
→ Settings → Networking → Custom Domain.

| Name | Type | Target | Proxy |
|---|---|---|---|
| `jfinances` | CNAME | `3b95hhzb.up.railway.app` (`web`, production) | proxied |
| `jfinances-hooks` | CNAME | `3qcl1xl6.up.railway.app` (`hooks`, production) | proxied |
| `jfinances-sandbox` | CNAME | `2rwwyp0l.up.railway.app` (`web`, sandbox) | proxied |
| `jfinances-sandbox-hooks` | CNAME | `z0nl608z.up.railway.app` (`hooks`, sandbox) | proxied |
| `_railway-verify.<each of the above>` | TXT | `railway-verify=…` from Railway | DNS only |

All eight records exist (created 2026-10-13). If a service's custom domain is
ever re-created in Railway, its CNAME target and TXT value change: copy the
new ones from Railway → service → Settings → Networking.

Future: `jfinances-api` / `jfinances-sandbox-api` → the same `web` services,
for the iOS app (see `docs/90-roadmap.md`).

Single-level names only. `api.jfinances.sellingtcg.com` would need Advanced
Certificate Manager; `jfinances-api.sellingtcg.com` is covered by Universal SSL.

## 2. TLS

SSL/TLS mode for the zone: **Full (Strict)**. Railway issues a Let's Encrypt
certificate for each custom domain, so strict works. "Flexible" would send
plaintext to Railway and must never be used.

## 3. Access application (dashboard)

Managed as code by `ops/cloudflare_access.py` (idempotent; dry run by
default, `--apply` to change; prints the AUD tags and the Railway commands).
The token needs **Account → Access: Apps and Policies → Edit** and **Account →
Access: Organizations, Identity Providers, and Groups → Read** on
"Jimmy.mooney@gmail.com's Account" (which owns the zone and the `daedalustcg`
team). Cloudflare returns an *empty list*, not an error, for lists a token
cannot read, so an empty result is not proof that nothing exists.

What the script sets, if you ever do it by hand (Zero Trust → Access →
Applications → Add → Self-hosted):

| Field | Value |
|---|---|
| Name | `jfinances` (and a second app `jfinances-sandbox`) |
| Domain | `jfinances.sellingtcg.com` (path empty — the whole host) |
| Session duration | 24 hours |
| Identity providers | One-time PIN only, with instant auth (auto-redirect) |
| App Launcher | off |
| Cookie | HttpOnly, SameSite=Lax (the Plaid OAuth return is a cross-site GET) |

Policies, in order:

1. **jfinances household** (reusable policy): *Allow*; include *Emails* →
   `jimmy.mooney@gmail.com`, `anna.b.mooney@gmail.com`.

No bypass for `/healthz` is needed: Railway's healthcheck calls the container
directly (Host `healthcheck.railway.app`), never through Cloudflare. Keeping
the whole dashboard host behind Access means nothing on it is public.

After saving, open the application → Overview → copy the **Application
Audience (AUD) Tag** and set it as `CF_ACCESS_AUD` on the `web` service in
Railway for that environment. Each application has its own AUD; the variable
accepts a comma-separated list.

Do **not** put `jfinances-hooks.*` behind Access.

## 4. Why the app verifies the JWT anyway

Access adds `Cf-Access-Jwt-Assertion` to every proxied request. If the
Railway origin were ever reachable without Cloudflare (a leaked
`up.railway.app` domain, a DNS mistake), anyone could hit it. So the app
rejects any `/api/*` request on the dashboard host whose JWT does not
verify against `https://daedalustcg.cloudflareaccess.com/cdn-cgi/access/certs`
with the right `aud` and `iss`. The app also keeps its own `users`
allowlist: Access proves *who*, the app decides *whether*.

## 5. Adding or removing a person

1. Edit `EMAILS` in `ops/cloudflare_access.py` and run it with `--apply`
   (or Zero Trust → Access → Policies → "jfinances household" → edit emails).
2. Railway → `web` → `ALLOWED_USERS` → edit (keep the owner first), redeploy `web` (or run
   `railway run --service web python -m server.tools.seed`).
3. To remove: delete from both places. Disabling in the app alone is enough
   to block access even if Access still lets them through.

## 6. Checklist for a new hostname

- [ ] Custom domain added on the Railway service, status "Valid"
- [ ] Proxied CNAME in Cloudflare
- [ ] Railway shows the deployment SUCCESS (its healthcheck is internal)
- [ ] hooks hosts: `curl -s https://<host>/healthz` returns 200 JSON
- [ ] Access application created (dashboard hosts only), AUD set in Railway
- [ ] `curl -sI https://<host>/api/v1/me` returns a 302 to cloudflareaccess.com
- [ ] Railway-provided `*.up.railway.app` domain deleted from the service
