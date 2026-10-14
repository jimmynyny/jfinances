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
"""
from __future__ import annotations

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


def mint_link_code(sess: Session, principal: Principal, *, nonce: str, device_name: str) -> str:
    """Inside an Access session: a code the phone can trade once."""
    now = datetime.now(UTC)
    # Housekeeping: codes are worthless a minute after they expire.
    sess.execute(delete(MobileLinkCode).where(MobileLinkCode.expires_at < now - timedelta(days=1)))
    code = random_token(32)
    sess.add(MobileLinkCode(user_id=principal.user_id, nonce=nonce[:64], code_hash=sha256_hex(code),
                            device_name=(device_name or "").strip()[:120] or None,
                            expires_at=now + LINK_CODE_TTL))
    sess.flush()
    return code


def redeem_link_code(sess: Session, *, code: str, nonce: str, name: str,
                     client_ip: str = "?") -> tuple[str, ApiToken, User]:
    """The phone's half. Returns the plaintext token exactly once.

    The burn is a conditional UPDATE, so two requests racing on one code
    cannot both win.
    """
    tok.throttle(client_ip)
    now = datetime.now(UTC)
    row = sess.execute(select(MobileLinkCode).where(MobileLinkCode.code_hash == sha256_hex(code))).scalar_one_or_none()
    if row is None or not hmac.compare_digest(row.nonce, nonce[:64]) or row.used_at is not None:
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
    label = (name or "").strip() or row.device_name or "iPhone"
    token_row, token = tok.issue_token(sess, user_id=user.id, name=label)
    log.info("phone linked: user=%s token=%s", user.id, token_row.id)
    return token, token_row, user
