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


def current_user(request: Request, sess: Session = Depends(get_session)) -> Principal:
    s = settings()
    if s.api_host and _host(request) == s.api_host.lower():
        client_ip = request.client.host if request.client else "?"
        principal = authenticate_bearer(request.headers, sess, client_ip)
    else:
        principal = authenticate_human(request.headers, request.cookies, sess)
    request.state.principal = principal
    return principal


def dashboard_only(request: Request, principal: Principal = Depends(current_user)) -> Principal:
    """Some endpoints (token issuing, unlinking) must not be reachable with a
    device token, only through an interactive Access session."""
    if principal.via == "token":
        raise AuthError(Code.FORBIDDEN, "this endpoint requires an interactive session", status=403)
    return principal
