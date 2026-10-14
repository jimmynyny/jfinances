"""Linking a phone (auth/mobile.py, docs/40 §5).

`GET /mobile/link` is opened by the app in a system web sheet on the
dashboard hostname, where Access proves the person. `POST /mobile/redeem` and
`POST /mobile/unlink` are called by the app on the API hostname: the first
before it has a token, the second to give its token back.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import mobile
from ..auth import tokens as tok
from ..auth.deps import client_ip, dashboard_only, on_api_host
from ..auth.human import Principal
from ..db import get_session
from ._common import ApiError

router = APIRouter()

_NONCE = re.compile(r"[A-Za-z0-9_\-]{8,64}")
#: An S256 challenge: base64url of 32 bytes, unpadded.
_CHALLENGE = re.compile(r"[A-Za-z0-9_\-]{43}")


@router.get("/mobile/link")
def link(nonce: str = "", name: str = "", method: str = "", p: Principal = Depends(dashboard_only),
         sess: Session = Depends(get_session)):
    """Mint a one-time code and bounce to the app. `method=S256`: the nonce is
    a PKCE challenge, and only its verifier will redeem the code (Android).

    ⚠ A GET that writes, deliberately: it is where Access's login redirect
    lands, and that can only be a GET. What it writes is a two-minute code.
    """
    if method not in ("", mobile.S256):
        raise ApiError(400, "bad_request", "bad method")
    if not (_CHALLENGE if method else _NONCE).fullmatch(nonce):
        raise ApiError(400, "bad_request", "bad nonce")
    code = mobile.mint_link_code(sess, p, nonce=nonce, device_name=name, challenge_method=method or None)
    # The app redeems the code the moment the redirect arrives: commit first.
    sess.commit()
    return RedirectResponse(f"{mobile.APP_SCHEME}://linked?code={quote(code, safe='')}&nonce={quote(nonce, safe='')}",
                            status_code=302)


class RedeemIn(BaseModel):
    model_config = {"extra": "forbid"}

    code: str = Field(min_length=16, max_length=128)
    #: The nonce the app made (iOS), or, for a code minted with method=S256,
    #: nothing: the verifier redeems it.
    nonce: str | None = Field(default=None, min_length=8, max_length=64)
    #: RFC 7636 §4.1: 43–128 unreserved characters.
    verifier: str | None = Field(default=None, min_length=43, max_length=128, pattern=r"^[A-Za-z0-9\-._~]+$")
    #: Names the row in Settings so a lost phone can be revoked by name.
    name: str = Field(default="", max_length=120)


def _api_host_only(request: Request) -> None:
    if not on_api_host(request):
        raise ApiError(404, "not_found", "no such route")


@router.post("/mobile/redeem")
def redeem(body: RedeemIn, request: Request, sess: Session = Depends(get_session)):
    """Trade the code for this phone's token. Unauthenticated: the code is the credential."""
    _api_host_only(request)
    token, row, user = mobile.redeem_link_code(sess, code=body.code, nonce=body.nonce, verifier=body.verifier,
                                               name=body.name, client_ip=client_ip(request))
    sess.commit()  # the token must exist before the phone holds it
    return {"token": token, "id": str(row.id), "name": row.name, "email": user.email,
            "display_name": user.display_name}


@router.post("/mobile/unlink")
def unlink(request: Request, sess: Session = Depends(get_session)):
    """The phone revoking its own token, from its Settings screen."""
    _api_host_only(request)
    row = tok.revoke_presented(request.headers, sess, client_ip(request))
    return {"revoked": True, "id": str(row.id)}
