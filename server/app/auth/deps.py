"""FastAPI dependencies. Routers depend on `current_user` and never parse
headers themselves.

Which prover runs is decided by the Host header: the API hostname
(`API_HOST`) uses app-issued bearer tokens; every other hostname is the
dashboard and must carry a Cloudflare Access JWT.
"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from .errors import AuthError, Code
from .human import Principal, authenticate_human
from .tokens import authenticate_bearer


def _host(request: Request) -> str:
    return (request.headers.get("host") or "").split(":")[0].lower()


def on_api_host(request: Request) -> bool:
    s = settings()
    return bool(s.api_host) and _host(request) == s.api_host.lower()


def client_ip(request: Request) -> str:
    # Cloudflare fronts every hostname, so the connecting address is an edge's;
    # the visitor's is in this header. Throttling the edge would throttle all.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def current_user(request: Request, sess: Session = Depends(get_session)) -> Principal:
    """Either credential resolves to the same `users` row and may do the same
    things: a linked phone edits, connects and unlinks banks as the dashboard
    does (docs/40 §5). What a phone may NOT do is in `dashboard_only`."""
    if on_api_host(request):
        principal = authenticate_bearer(request.headers, sess, client_ip(request))
    else:
        principal = authenticate_human(request.headers, request.cookies, sess)
    request.state.principal = principal
    return principal


def dashboard_only(request: Request, principal: Principal = Depends(current_user)) -> Principal:
    """Managing linked phones (minting a link code, listing and revoking
    tokens) needs an interactive Access session, never a phone's token: a
    stolen phone cannot link another phone, and cannot stop its owner
    unlinking it from the dashboard."""
    if principal.via == "token":
        raise AuthError(Code.FORBIDDEN, "this endpoint requires an interactive session", status=403)
    return principal
