#!/usr/bin/env python3
"""The iPhone app's App ID and development profile, from App Store Connect (docs/85 §4).

    ASC_KEY_PATH=~/path/AuthKey_XXXXXXXXXX.p8 uv run python ios/Scripts/asc-profile.py

Makes sure the account has the App ID `com.daedalustcg.jfinances` with
Associated Domains enabled (the OAuth return of a bank link, docs/30 "Link on
the phones"), and an active iOS development profile for it naming every
enabled iPhone and iPad on the account and the development certificate that is
in this Mac's keychain. The profile is saved where `deploy-ota.sh` looks.
Idempotent: run it again when a profile expires (a year), a phone is added, or
the certificate is renewed; a profile that is missing a device or the
certificate is replaced.

The key is an App Store Connect API key with the Developer role (its issuer id
and key id are identifiers, not secrets; the .p8 is the secret and stays out of
the repo). Nothing here prints the key or the token it signs.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt

ISSUER = os.environ.get("ASC_ISSUER_ID", "02a4a13f-af3c-4c34-8e1b-15b40f1b0793")
KEY_PATH = os.path.expanduser(os.environ["ASC_KEY_PATH"])
_m = re.search(r"AuthKey_([A-Z0-9]{10})\.p8$", os.path.basename(KEY_PATH))
KEY_ID = os.environ.get("ASC_KEY_ID") or (_m and _m.group(1)) or sys.exit("set ASC_KEY_ID: it is not in the file name")
BUNDLE = "com.daedalustcg.jfinances"
APP_NAME = "jFinances"
PROFILE_NAME = "jfinances development"
PROFILE_DIR = os.path.expanduser("~/Library/Developer/Xcode/UserData/Provisioning Profiles")
API = "https://api.appstoreconnect.apple.com/v1"

with open(KEY_PATH) as f:
    _key = f.read()
_now = int(time.time())
_token = jwt.encode(
    {"iss": ISSUER, "iat": _now, "exp": _now + 15 * 60, "aud": "appstoreconnect-v1"},
    _key, algorithm="ES256", headers={"kid": KEY_ID},
)


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, method=method, data=data)
    req.add_header("Authorization", "Bearer " + _token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r) if r.status != 204 else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}\n{e.read().decode()}")


def keychain_sha1s():
    cmd = ["security", "find-identity", "-v", "-p", "codesigning"]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    return {line.split()[1] for line in out.splitlines() if ") " in line and '"' in line}


def main():
    # The App ID, with Associated Domains.
    found = [b for b in call("GET", f"/bundleIds?filter[identifier]={BUNDLE}&filter[platform]=IOS")["data"]
             if b["attributes"]["identifier"] == BUNDLE]
    if found:
        bid = found[0]
        print(f"App ID: {bid['attributes']['name']} ({BUNDLE})")
    else:
        bid = call("POST", "/bundleIds", {"data": {"type": "bundleIds", "attributes": {
            "identifier": BUNDLE, "name": APP_NAME, "platform": "IOS"}}})["data"]
        print(f"created App ID {APP_NAME} ({BUNDLE})")
    caps = call("GET", f"/bundleIds/{bid['id']}/bundleIdCapabilities")["data"]
    have = {c["attributes"]["capabilityType"] for c in caps}
    if "ASSOCIATED_DOMAINS" not in have:
        call("POST", "/bundleIdCapabilities", {"data": {"type": "bundleIdCapabilities",
            "attributes": {"capabilityType": "ASSOCIATED_DOMAINS"},
            "relationships": {"bundleId": {"data": {"type": "bundleIds", "id": bid["id"]}}}}})
        print("enabled Associated Domains")
    else:
        print("Associated Domains enabled")

    # The development certificate that is in this keychain.
    local = keychain_sha1s()
    every = call("GET", "/certificates?filter[certificateType]=DEVELOPMENT,IOS_DEVELOPMENT&limit=200")["data"]
    certs = [c for c in every
             if hashlib.sha1(base64.b64decode(c["attributes"]["certificateContent"])).hexdigest().upper() in local]
    if not certs:
        sys.exit("no development certificate from the account is in this keychain")
    for c in certs:
        print(f"certificate: {c['attributes']['name']} (expires {c['attributes']['expirationDate'][:10]})")

    # Every enabled iPhone and iPad.
    devices = call("GET", "/devices?filter[platform]=IOS&filter[status]=ENABLED&limit=200")["data"]
    if not devices:
        sys.exit("no enabled iOS devices on the account")
    for d in devices:
        print(f"device: {d['attributes']['name']} ({d['attributes']['deviceClass']})")

    # The profile: kept if current, else replaced.
    want_devices = {d["id"] for d in devices}
    want_certs = {c["id"] for c in certs}
    profile = None
    q = urllib.parse.quote(PROFILE_NAME)
    for p in call("GET", f"/profiles?filter[name]={q}&include=bundleId,devices,certificates")["data"]:
        a, rel = p["attributes"], p["relationships"]
        current = (a["profileState"] == "ACTIVE" and a["profileType"] == "IOS_APP_DEVELOPMENT"
                   and rel["bundleId"]["data"]["id"] == bid["id"]
                   and {d["id"] for d in rel["devices"]["data"]} >= want_devices
                   and {c["id"] for c in rel["certificates"]["data"]} >= want_certs)
        if current and profile is None:
            profile = p
            print(f"profile is current: {a['name']} (expires {a['expirationDate'][:10]})")
        else:
            call("DELETE", f"/profiles/{p['id']}")
            print(f"replaced profile {a['name']} ({a['profileState'].lower()}, {a['uuid']})")
    if profile is None:
        profile = call("POST", "/profiles", {"data": {"type": "profiles",
            "attributes": {"name": PROFILE_NAME, "profileType": "IOS_APP_DEVELOPMENT"},
            "relationships": {
                "bundleId": {"data": {"type": "bundleIds", "id": bid["id"]}},
                "certificates": {"data": [{"type": "certificates", "id": i} for i in sorted(want_certs)]},
                "devices": {"data": [{"type": "devices", "id": i} for i in sorted(want_devices)]},
            }}})["data"]
        print(f"created profile {PROFILE_NAME} (expires {profile['attributes']['expirationDate'][:10]})")

    content = profile["attributes"].get("profileContent")
    if not content:
        content = call("GET", f"/profiles/{profile['id']}")["data"]["attributes"]["profileContent"]
    os.makedirs(PROFILE_DIR, exist_ok=True)
    path = os.path.join(PROFILE_DIR, profile["attributes"]["uuid"] + ".mobileprovision")
    with open(path, "wb") as f:
        f.write(base64.b64decode(content))
    print("saved", path)


if __name__ == "__main__":
    main()
