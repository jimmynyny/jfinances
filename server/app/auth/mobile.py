"""Linking a phone (docs/40 §5). Modelled on vending's auth/mobile.py.

Cloudflare Access proves a person in a browser for a day. A home-screen
widget refreshes in the background, on a locked phone, for months. So the
phone gets a token WE issue, after Access has done its job once:

    app  --ASWebAuthenticationSession-->  GET /api/v1/mobile/link?nonce=N
                                          (dashboard hostname, behind Access)
    us   --302-->  jfinances://linked?code=C&nonce=N
    app  --POST /api/v1/mobile/redeem {code, nonce, name}-->  API hostname
    us   --> {token}   ...kept in the Keychain, shared with the widgets

Every request after that carries `Authorization: Bearer <token>` on the API
hostname and resolves through `auth/tokens.py` like any `api_tokens` row.

⚠ Only hashes are stored. The code and the token are 256 random bits each.
⚠ A code lives two minutes, works once, and only with the nonce the app made.
⚠ A phone cannot link another phone: minting needs an Access session.

On Android any app can claim the `jfinances` scheme, so the redirect (code and
nonce both) could be read by another app. The Android app therefore links with
PKCE (RFC 7636): it sends `method=S256` and, as the nonce, the SHA-256 of a
secret it keeps; it redeems with the secret ("verifier"), which never travels
in a URL. A code minted that way cannot be redeemed with the nonce alone.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..crypto import random_token, sha256_hex
from ..models import ApiToken, MobileLinkCode, User
from . import tokens as tok
from .errors import AuthError, Code
from .human import Principal

log = logging.getLogger(__name__)

#: The app's URL scheme; `GET /mobile/link` bounces to `jfinances://linked?...`.
APP_SCHEME = "jfinances"
#: Long enough for the redirect, useless afterwards.
LINK_CODE_TTL = timedelta(seconds=120)
#: The one challenge method there is: the nonce is base64url(SHA-256(verifier)).
S256 = "S256"


def s256_challenge(verifier: str) -> str:
    """RFC 7636 §4.2: BASE64URL(SHA256(verifier)), no padding."""
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")


def mint_link_code(sess: Session, principal: Principal, *, nonce: str, device_name: str,
                   challenge_method: str | None = None) -> str:
    """Inside an Access session: a code the phone can trade once. With
    `challenge_method=S256` the nonce is a challenge and only its verifier redeems."""
    now = datetime.now(UTC)
    # Housekeeping: codes are worthless a minute after they expire.
    sess.execute(delete(MobileLinkCode).where(MobileLinkCode.expires_at < now - timedelta(days=1)))
    code = random_token(32)
    sess.add(MobileLinkCode(user_id=principal.user_id, nonce=nonce[:64], challenge_method=challenge_method,
                            code_hash=sha256_hex(code), device_name=(device_name or "").strip()[:120] or None,
                            expires_at=now + LINK_CODE_TTL))
    sess.flush()
    return code


def _proves(row: MobileLinkCode, nonce: str | None, verifier: str | None) -> bool:
    """Whether the phone holds what the code was minted for: its verifier for
    an S256 code (the nonce alone is in the redirect, so it proves nothing),
    else the nonce."""
    if row.challenge_method == S256:
        return verifier is not None and hmac.compare_digest(row.nonce, s256_challenge(verifier))
    return nonce is not None and hmac.compare_digest(row.nonce, nonce[:64])


def redeem_link_code(sess: Session, *, code: str, nonce: str | None, name: str, verifier: str | None = None,
                     client_ip: str = "?") -> tuple[str, ApiToken, User]:
    """The phone's half. Returns the plaintext token exactly once.

    The burn is a conditional UPDATE, so two requests racing on one code
    cannot both win.
    """
    tok.throttle(client_ip)
    now = datetime.now(UTC)
    row = sess.execute(select(MobileLinkCode).where(MobileLinkCode.code_hash == sha256_hex(code))).scalar_one_or_none()
    if row is None or not _proves(row, nonce, verifier) or row.used_at is not None:
        tok.record_bad(client_ip)
        raise AuthError(Code.BAD_LINK_CODE, "that link code is not valid; start again from the app", status=400)
    if row.expires_at < now:
        raise AuthError(Code.BAD_LINK_CODE, "that link code has expired; start again from the app", status=400)
    burned = sess.execute(update(MobileLinkCode).where(MobileLinkCode.id == row.id, MobileLinkCode.used_at.is_(None))
                          .values(used_at=now)).rowcount
    if burned != 1:
        raise AuthError(Code.BAD_LINK_CODE, "that link code was already used", status=400)
    user = sess.get(User, row.user_id)
    if user is None or user.disabled_at is not None:
        raise AuthError(Code.NOT_ALLOWED, "this person is not allowed", status=403)
    label = (name or "").strip() or row.device_name or "phone"
    token_row, token = tok.issue_token(sess, user_id=user.id, name=label)
    log.info("phone linked: user=%s token=%s", user.id, token_row.id)
    return token, token_row, user
