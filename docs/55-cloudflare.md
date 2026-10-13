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
| `jfinances` | CNAME | Railway target for `web` (production) | proxied |
| `jfinances-hooks` | CNAME | Railway target for `hooks` (production) | proxied |
| `jfinances-sandbox` | CNAME | Railway target for `web` (sandbox) | proxied |
| `jfinances-sandbox-hooks` | CNAME | Railway target for `hooks` (sandbox) | proxied |

Future: `jfinances-api` / `jfinances-sandbox-api` → the same `web` services,
for the iOS app (see `docs/90-roadmap.md`).

Single-level names only. `api.jfinances.sellingtcg.com` would need Advanced
Certificate Manager; `jfinances-api.sellingtcg.com` is covered by Universal SSL.

## 2. TLS

SSL/TLS mode for the zone: **Full (Strict)**. Railway issues a Let's Encrypt
certificate for each custom domain, so strict works. "Flexible" would send
plaintext to Railway and must never be used.

## 3. Access application (dashboard)

Zero Trust → Access → Applications → Add → Self-hosted.

| Field | Value |
|---|---|
| Name | `jfinances` (and a second app `jfinances-sandbox`) |
| Domain | `jfinances.sellingtcg.com` (path empty — the whole host) |
| Session duration | 24 hours |
| Identity providers | One-time PIN (and Google if/when added to the team) |
| App Launcher | off |

Policies, in order:

1. **Allow — household**: action *Allow*; include *Emails* →
   `jimmy.mooney@gmail.com`, `<wife's gmail>`.
2. **Bypass — health**: action *Bypass*; include *Everyone*; path `/healthz`.
   Add this as a separate application scoped to `jfinances.sellingtcg.com/healthz`
   if the UI does not let you scope a policy by path — Railway's healthcheck
   must get a 200 from the app, not a Cloudflare login page.

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

1. Zero Trust → the Access application → policy "household" → edit emails.
2. Railway → `web` → `ALLOWED_USERS` → edit, redeploy `web` (or run
   `railway run --service web python -m server.tools.seed`).
3. To remove: delete from both places. Disabling in the app alone is enough
   to block access even if Access still lets them through.

## 6. Checklist for a new hostname

- [ ] Custom domain added on the Railway service, status "Valid"
- [ ] Proxied CNAME in Cloudflare
- [ ] `curl -sI https://<host>/healthz` returns 200 from the app
- [ ] Access application created (dashboard hosts only), AUD set in Railway
- [ ] `curl -sI https://<host>/api/v1/me` returns a 302 to cloudflareaccess.com
- [ ] Railway-provided `*.up.railway.app` domain deleted from the service
