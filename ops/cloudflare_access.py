#!/usr/bin/env python3
"""Cloudflare Access for jfinances, as code. Idempotent; stdlib only.

    export CF_API_TOKEN=...                      # never commit it
    python3 ops/cloudflare_access.py             # dry run: print what would change
    python3 ops/cloudflare_access.py --apply     # create/update, then print each app's AUD

What it manages (docs/55-cloudflare.md):
  * one reusable Allow policy, "jfinances household", listing the household's emails
  * one self-hosted Access application per dashboard hostname, using that policy,
    24 h sessions, SameSite=Lax cookies (the Plaid OAuth return is a cross-site
    top-level GET), app launcher hidden, login pinned to One-time PIN when the
    token can read identity providers

It never touches the hooks hostnames: Plaid cannot log in, so they stay outside
Access and the app verifies Plaid's signature instead.

Token permissions (Cloudflare -> My Profile -> API Tokens -> edit the token):
  Account | Access: Apps and Policies | Edit
  Account | Access: Organizations, Identity Providers, and Groups | Read
After --apply, put each AUD into Railway (`CF_ACCESS_AUD` on the web service of
the matching environment). The script prints the exact commands.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.cloudflare.com/client/v4"
ACCOUNT_ID = "0eb8db5528ac0eb4d9ccdf5068bf9c51"          # "Jimmy.mooney@gmail.com's Account", owns sellingtcg.com
TEAM = "daedalustcg"                                     # Zero Trust team -> daedalustcg.cloudflareaccess.com
POLICY_NAME = "jfinances household"
EMAILS = ["jimmy.mooney@gmail.com", "anna.b.mooney@gmail.com"]
SESSION = "24h"
APPS = [  # (name, hostname, railway environment)
    ("jfinances", "jfinances.sellingtcg.com", "production"),
    ("jfinances-sandbox", "jfinances-sandbox.sellingtcg.com", "sandbox"),
]


class CFError(RuntimeError):
    pass


def call(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get("CF_API_TOKEN")
    if not token:
        raise SystemExit("CF_API_TOKEN is not set")
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            data = json.load(e)
        except Exception:  # noqa: BLE001
            raise CFError(f"{method} {path}: HTTP {e.code}") from e
    if not data.get("success"):
        errs = "; ".join(f"{x.get('code')} {x.get('message') or x.get('error')}" for x in data.get("errors", []))
        raise CFError(f"{method} {path}: {errs or 'failed'}")
    return data


def otp_idp_id() -> str | None:
    try:
        idps = call("GET", f"/accounts/{ACCOUNT_ID}/access/identity_providers")["result"]
    except CFError as e:
        print(f"  ! cannot read identity providers ({e}); login page will offer every IdP on the team")
        return None
    for idp in idps:
        if idp.get("type") == "onetimepin":
            return idp["id"]
    # Cloudflare answers a list call the token may not read with an EMPTY list, not an error.
    print("  ! no One-time PIN identity provider visible: either the token lacks 'Access: Organizations,\n"
          "    Identity Providers, and Groups: Read', or One-time PIN is not enabled for the team.\n"
          "    The login page will then offer every IdP on the team.")
    return None


def desired_policy() -> dict:
    return {"name": POLICY_NAME, "decision": "allow", "session_duration": SESSION,
            "include": [{"email": {"email": e}} for e in EMAILS]}


def desired_app(name: str, host: str, policy_id: str | None, otp: str | None) -> dict:
    app = {"name": name, "domain": host, "type": "self_hosted", "session_duration": SESSION,
           "app_launcher_visible": False, "http_only_cookie_attribute": True,
           "same_site_cookie_attribute": "lax", "enable_binding_cookie": False,
           "policies": [{"id": policy_id, "precedence": 1}] if policy_id else []}
    if otp:
        app["allowed_idps"] = [otp]
        app["auto_redirect_to_identity"] = True
    return app


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    args = ap.parse_args()
    verb = "" if args.apply else "(dry run) "

    otp = otp_idp_id()
    policies = call("GET", f"/accounts/{ACCOUNT_ID}/access/policies?per_page=100")["result"]
    policy = next((p for p in policies if p.get("name") == POLICY_NAME), None)
    want = desired_policy()
    if policy is None:
        print(f"{verb}create policy {POLICY_NAME!r} for {', '.join(EMAILS)}")
        policy_id = None
        if args.apply:
            policy_id = call("POST", f"/accounts/{ACCOUNT_ID}/access/policies", want)["result"]["id"]
    else:
        policy_id = policy["id"]
        print(f"{verb}update policy {POLICY_NAME!r} ({policy_id}) -> {', '.join(EMAILS)}")
        if args.apply:
            call("PUT", f"/accounts/{ACCOUNT_ID}/access/policies/{policy_id}", want)

    apps = call("GET", f"/accounts/{ACCOUNT_ID}/access/apps?per_page=100")["result"]
    auds: list[tuple[str, str, str]] = []
    for name, host, env in APPS:
        existing = next((a for a in apps if a.get("domain") == host), None)
        body = desired_app(name, host, policy_id, otp)
        if existing is None:
            print(f"{verb}create Access app {name!r} for https://{host}")
            res = call("POST", f"/accounts/{ACCOUNT_ID}/access/apps", body)["result"] if args.apply else None
        else:
            print(f"{verb}update Access app {name!r} ({existing['id']}) for https://{host}")
            res = call("PUT", f"/accounts/{ACCOUNT_ID}/access/apps/{existing['id']}", body)["result"] \
                if args.apply else existing
        if res:
            auds.append((env, host, res["aud"]))

    if auds:
        print("\nAUD tags (not secret; they are in every Access JWT). Put them in Railway:")
        for env, host, aud in auds:
            print(f"  railway variable set --service web --environment {env} CF_ACCESS_AUD={aud}   # {host}")
        print(f"\nTeam: {TEAM} -> https://{TEAM}.cloudflareaccess.com (CF_ACCESS_TEAM={TEAM})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CFError as e:
        print(f"Cloudflare API error: {e}", file=sys.stderr)
        if "auth.forbidden" in str(e) or "10000" in str(e) or "9109" in str(e):
            print("The token lacks Access permissions; see the docstring at the top of this file.", file=sys.stderr)
        sys.exit(1)
