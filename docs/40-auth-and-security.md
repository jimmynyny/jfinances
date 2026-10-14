# 40 — Auth and security

This app holds every balance and transaction a household has. The design
goal is that no single mistake exposes it: the perimeter, the app, and the
database each refuse on their own.

## 1. Threat model, briefly

| Threat | Mitigation |
|---|---|
| Someone on the internet reaches the dashboard | Cloudflare Access in front; the app also verifies the Access JWT on every API call, so a direct hit on the Railway origin fails |
| Railway origin reachable without Cloudflare | `*.up.railway.app` domains deleted; only Cloudflare-proxied hostnames exist |
| Forged Plaid webhook | ES256 signature + body hash + 5-minute freshness, before anything is read |
| Database dump leaks | Plaid access tokens are AES-256-GCM encrypted with a key that lives only in `web`/`worker` env |
| Token in logs | redaction regexes in the log formatter; tokens are never in log calls to begin with |
| Device token stolen | only the hash is stored; tokens are read-only; unlink from Settings by name; a disabled user disables all their tokens |
| Config mistake ships | boot validation refuses placeholders, env mismatches and dev bypasses in deployed environments |
| Browser-side attacks | same-origin only (no CORS), `X-Frame-Options: DENY`, `nosniff`, HSTS, `Cache-Control: no-store` on API responses |

## 2. Humans: Cloudflare Access

Hostnames `jfinances.sellingtcg.com` and `jfinances-sandbox.sellingtcg.com`
are self-hosted Access applications on team `daedalustcg`. Login method is
One-time PIN to the allowlisted emails (Google can be added as an identity
provider later without touching the app). Session 24 h.

The app (`auth/human.py`) then, on every request:
1. takes the JWT from `Cf-Access-Jwt-Assertion` (header, preferred) or the
   `CF_Authorization` cookie,
2. verifies the signature against the team's JWKS
   (`/cdn-cgi/access/certs`, cached 1 h),
3. requires `exp`, `iat`, `aud`, `iss`; `aud` must be one of `CF_ACCESS_AUD`
   (comma-separated, one per Access application); `iss` must be the team URL,
4. lowercases the `email` claim and looks it up in `users`; unknown or
   disabled → 403.

It never reads `Cf-Access-Authenticated-User-Email`; that header is just
text. Access proves *who*; `users` decides *whether*.

Bypass policies on the Access application: `/healthz` only (Railway's health
check must not get a login page). Everything else, including `/about`, can be
behind Access; the public privacy page is on GitHub Pages.

`DEV_LOGIN_EMAIL` lets a laptop skip Access. It only works when
`APP_ENV=local`, and `validate_for_boot` refuses to start a deployed
environment with it set.

## 3. Machines: Plaid webhooks

`services/plaid_webhooks.py::verify`:

1. `Plaid-Verification` header must be a JWT with `alg=ES256` and a `kid`.
2. The key is fetched by `kid` from `/webhook_verification_key/get` and
   cached 24 h; a key Plaid marks `expired_at` is rejected.
3. Signature verified with PyJWT.
4. `iat` must be within 5 minutes.
5. `request_body_sha256` must equal SHA-256 of the **raw** bytes, compared
   with `hmac.compare_digest`.

Only then is the body parsed. Failures are 401 with no detail. The hooks
hostname has no Cloudflare Access (Plaid cannot log in) but is still proxied
by Cloudflare, so the WAF and rate limiting apply.

## 4. Encryption at rest

`crypto.py`. AES-256-GCM via `cryptography`, random 96-bit nonce per value,
stored as `version(1) || nonce(12) || ciphertext+tag`. Key is
`TOKEN_ENCRYPTION_KEY` (32 bytes, urlsafe-base64). Only `web` (exchange,
relink, unlink, refresh button) and `worker` (sync) have the key; `hooks`
does not. The version byte allows a second key during rotation
(docs/60 §4).

## 5. Phones: the API hostname

Design follows vending's `mobile.py` (`auth/mobile.py`, `api/mobile.py`).
`API_HOST` names a hostname with no Access; it serves `/api/*` and nothing
else (the dashboard bundle stays behind Access), and every request there must
carry `Authorization: Bearer <token>`.

Linking, once per phone:

```
app  --ASWebAuthenticationSession-->  GET https://jfinances.sellingtcg.com/api/v1/mobile/link?nonce=N&name=…
                                      (Access login: one-time PIN; dashboard_only)
web  --302-->  jfinances://linked?code=C&nonce=N      (C: 256 bits, 120 s, one use; only its hash is stored)
app  --POST https://jfinances-api.sellingtcg.com/api/v1/mobile/redeem {code, nonce, name}-->
web  --> {token, id, name, email}                    (a new api_tokens row; only its hash is stored)
```

- The nonce is made by the app for each attempt and must come back with the
  code, so a code lifted from a redirect is useless to anyone else.
- **Android uses PKCE** (RFC 7636). An iOS web-auth session hands the redirect
  to the app that opened it; on Android any app can claim the `jfinances`
  scheme and read the redirect, nonce included. So the Android app adds
  `method=S256` and sends, as the nonce, `BASE64URL(SHA-256(verifier))` of a
  secret it keeps; it redeems with `{code, verifier, name}`. A code minted
  with `S256` is refused with the nonce alone, and the verifier never travels
  in a URL (`mobile_link_codes.challenge_method`).
- The burn is a conditional UPDATE; two redeems of one code cannot both win.
- `mobile/link` needs an Access session (`dashboard_only`): a phone cannot
  mint codes for another phone.
- `mobile/redeem` and `mobile/unlink` answer on the API hostname only.

Requests: `auth/tokens.py` hashes the token, finds the `api_tokens` row,
rejects revoked ones, throttles an address (`CF-Connecting-IP`) after 20 bad
tokens or codes a minute, and resolves the user through the same
`principal_for_email` as Access. `last_used_at` is written at most every 5
minutes (widgets poll).

**Read-only.** `current_user` refuses any method but GET/HEAD/OPTIONS from a
token with 403 `auth.read_only`, for every route, including ones added later.
Endpoints marked `dashboard_only` refuse a token even for GET. The only write
a phone makes is `POST /mobile/unlink`, which revokes its own token.

Settings → phones lists each person's linked phones by name with last-seen,
and unlinks one (it stops on its next request). Tokens are never minted by
hand.

## 6. Secrets hygiene

- Secrets live in Railway variables only; the repo has `.env` ignored and no
  `.env.example` with real values.
- Logs: JSON lines through `logging.py`; a formatter-level redaction catches
  Plaid token shapes, JWTs and bearer strings. Do not log request bodies.
- `GET /api/v1/tokens` never returns token plaintext; `POST /mobile/redeem`
  returns it once, to the phone.
- Access tokens never appear in any API response.
- Rotation procedures are in docs/60-runbook.md.

## 7. What is deliberately not here

- No CORS. The SPA is same-origin. The iOS app talks to the API hostname
  with bearer auth; CORS is a browser concept and does not apply.
- No sessions or cookies of our own. Access owns the session.
- No role matrix. Two people, both can do everything; `users.role` exists
  for when that changes.
