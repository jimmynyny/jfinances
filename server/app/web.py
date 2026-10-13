"""The `web` service: the dashboard SPA and the JSON API, behind Cloudflare
Access on the dashboard hostname and behind app-issued bearer tokens on the
API hostname (docs/10-architecture.md §4).
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import router as api_router
from .auth.errors import AuthError
from .auth.human import seed_allowed_users
from .config import settings
from .db import ping, session
from .logging import configure, new_request_id, request_id_var

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    configure(s.log_level, service="web")
    problems = s.validate_for_boot("web")
    if problems and s.app_env != "local":
        for p in problems:
            log.error("boot check failed: %s", p)
        raise SystemExit(78)
    try:
        with session() as sess:
            n = seed_allowed_users(sess)
        log.info("allowed users seeded: %d", n)
    except Exception:  # noqa: BLE001
        log.exception("could not seed allowed users (database down?)")
        if s.app_env != "local":
            raise
    log.info("web up (env=%s plaid=%s spa=%s)", s.app_env, s.plaid_env, _spa_dir() is not None)
    yield


app = FastAPI(title="jfinances", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(api_router)


# --- middleware --------------------------------------------------------------
@app.middleware("http")
async def request_mw(request: Request, call_next):
    token = request_id_var.set(new_request_id())
    started = time.perf_counter()
    try:
        resp: Response = await call_next(request)
    finally:
        request_id_var.reset(token)
    resp.headers["X-Request-Id"] = request_id_var.get() or ""
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if settings().app_env != "local":
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
        log.info("%s %s -> %d", request.method, request.url.path, resp.status_code,
                 extra={"path": request.url.path, "status": resp.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1)})
    return resp


# --- errors ------------------------------------------------------------------
@app.exception_handler(AuthError)
async def auth_error(_: Request, e: AuthError):
    return JSONResponse({"error": {"code": str(e.code), "message": e.message}}, status_code=e.status)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, e: StarletteHTTPException):
    detail = e.detail if isinstance(e.detail, dict) else {"code": "http_error", "message": str(e.detail)}
    return JSONResponse({"error": detail}, status_code=e.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    return JSONResponse({"error": {"code": "validation", "message": "invalid request",
                                   "details": e.errors()}}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(_: Request, e: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "internal", "message": "internal error"}}, status_code=500)


# --- public routes -----------------------------------------------------------
@app.get("/healthz")
def healthz():
    try:
        db = "ok" if ping() else "bad"
    except Exception as e:  # noqa: BLE001
        db = f"error: {type(e).__name__}"
    return JSONResponse({"ok": db == "ok", "service": "web", "env": settings().app_env, "db": db},
                        status_code=200 if db == "ok" else 503)


@app.get("/about")
def about():
    page = ROOT / settings().about_page
    if page.exists():
        return FileResponse(page, media_type="text/html")
    return HTMLResponse("<h1>Mooney Household Ledger</h1>", status_code=200)


# --- SPA ---------------------------------------------------------------------
def _spa_dir() -> Path | None:
    p = Path(settings().spa_dir)
    if not p.is_absolute():
        p = ROOT / p
    return p if (p / "index.html").exists() else None


_NOT_BUILT = """<!doctype html><meta charset=utf-8><title>jfinances</title>
<body style="font:14px ui-monospace,monospace;padding:2rem">
<h1>jfinances</h1><p>The API is up but the frontend bundle is not in this image.</p>
<p>Build it with <code>npm run build</code> (see docs/50-deploy-railway.md) or check <code>SPA_DIR</code>.</p>
<p><a href="/healthz">/healthz</a> · <a href="/api/v1/me">/api/v1/me</a></p></body>"""


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse({"error": {"code": "not_found", "message": "no such route"}}, status_code=404)
    d = _spa_dir()
    if d is None:
        return HTMLResponse(_NOT_BUILT, status_code=200)
    candidate = (d / path).resolve() if path else d / "index.html"
    if path and candidate.is_file() and str(candidate).startswith(str(d.resolve()) + os.sep):
        headers = {"Cache-Control": "public, max-age=31536000, immutable"} if "/assets/" in str(candidate) \
            else {"Cache-Control": "no-cache"}
        return FileResponse(candidate, headers=headers)
    return FileResponse(d / "index.html", media_type="text/html", headers={"Cache-Control": "no-cache"})
