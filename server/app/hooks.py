"""The `hooks` service: Plaid posts here, nobody else.

It does three things and returns 200 fast: verify the signature, record the
event, enqueue the right job. The body is only a signal, the worker re-reads
everything from Plaid. No Cloudflare Access on this hostname (Plaid cannot
log in); the signature is the authentication.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select

from .config import settings
from .db import ping, session
from .jobs.queue import enqueue
from .logging import configure, new_request_id, request_id_var
from .models import PlaidItem, WebhookEvent
from .services import plaid_webhooks

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = settings()
    configure(s.log_level, service="hooks")
    problems = s.validate_for_boot("hooks")
    if problems and s.app_env != "local":
        for p in problems:
            log.error("boot check failed: %s", p)
        raise SystemExit(78)
    log.info("hooks up (env=%s plaid=%s)", s.app_env, s.plaid_env)
    yield


app = FastAPI(title="jfinances hooks", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def request_id_mw(request: Request, call_next):
    token = request_id_var.set(new_request_id())
    try:
        resp: Response = await call_next(request)
    finally:
        request_id_var.reset(token)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/healthz")
def healthz():
    try:
        db = "ok" if ping() else "bad"
    except Exception as e:  # noqa: BLE001
        db = f"error: {type(e).__name__}"
    status = 200 if db == "ok" else 503
    return JSONResponse({"ok": db == "ok", "service": "hooks", "env": settings().app_env, "db": db},
                        status_code=status)


# webhook_type/webhook_code -> job kind. Anything not listed is recorded only.
ROUTES: dict[tuple[str, str], str] = {
    ("TRANSACTIONS", "SYNC_UPDATES_AVAILABLE"): "sync_item",
    ("TRANSACTIONS", "INITIAL_UPDATE"): "sync_item",
    ("TRANSACTIONS", "HISTORICAL_UPDATE"): "sync_item",
    ("TRANSACTIONS", "DEFAULT_UPDATE"): "sync_item",
    ("TRANSACTIONS", "RECURRING_TRANSACTIONS_UPDATE"): "sync_item",
    ("HOLDINGS", "DEFAULT_UPDATE"): "refresh_investments",
    ("INVESTMENTS_TRANSACTIONS", "DEFAULT_UPDATE"): "refresh_investments",
    ("INVESTMENTS_TRANSACTIONS", "HISTORICAL_UPDATE"): "refresh_investments",
    ("LIABILITIES", "DEFAULT_UPDATE"): "refresh_liabilities",
    ("ITEM", "NEW_ACCOUNTS_AVAILABLE"): "sync_item",
}

ITEM_STATUS: dict[str, str] = {
    "ERROR": "error",
    "LOGIN_REPAIRED": "active",
    "PENDING_EXPIRATION": "pending_expiration",
    "PENDING_DISCONNECT": "pending_expiration",
    "USER_PERMISSION_REVOKED": "removed",
    "USER_ACCOUNT_REVOKED": "removed",
}


def route_event(sess, body: dict[str, Any]) -> str | None:
    wtype = str(body.get("webhook_type") or "")
    wcode = str(body.get("webhook_code") or "")
    plaid_item_id = body.get("item_id")
    item = None
    if plaid_item_id:
        item = sess.execute(select(PlaidItem).where(PlaidItem.item_id == plaid_item_id)).scalar_one_or_none()
        if item is not None:
            item.last_webhook_at = datetime.now(UTC)

    if wtype == "ITEM":
        if item is not None and wcode in ITEM_STATUS:
            new = ITEM_STATUS[wcode]
            if wcode == "ERROR":
                err = body.get("error") or {}
                item.error_code = err.get("error_code")
                item.error_message = (err.get("error_message") or "")[:1000]
                if item.error_code == "ITEM_LOGIN_REQUIRED":
                    new = "login_required"
            if new == "removed":
                item.removed_at = datetime.now(UTC)
            elif new == "active":
                item.error_code = None
                item.error_message = None
            item.status = new
            if wcode == "PENDING_EXPIRATION" and body.get("consent_expiration_time"):
                item.consent_expires_at = datetime.fromisoformat(
                    str(body["consent_expiration_time"]).replace("Z", "+00:00"))
            return f"item:{new}"
        if wcode == "WEBHOOK_UPDATE_ACKNOWLEDGED":
            return "ack"
        if wcode == "NEW_ACCOUNTS_AVAILABLE" and item is not None:
            enqueue(sess, "sync_item", {"item_id": str(item.id)})
            return "sync_item"
        return None

    kind = ROUTES.get((wtype, wcode))
    if kind and item is not None:
        enqueue(sess, kind, {"item_id": str(item.id)})
        return kind
    return None


@app.post("/plaid/webhook")
async def plaid_webhook(request: Request):
    raw = await request.body()
    header = request.headers.get("plaid-verification")
    try:
        plaid_webhooks.verify(raw, header)
    except plaid_webhooks.WebhookVerificationError as e:
        log.warning("rejected webhook: %s", e)
        return JSONResponse({"error": {"code": "webhook.unverified", "message": "rejected"}}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": {"code": "webhook.bad_json", "message": "rejected"}}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": {"code": "webhook.bad_json", "message": "rejected"}}, status_code=400)

    event = WebhookEvent(item_id=body.get("item_id"), webhook_type=str(body.get("webhook_type") or "?"),
                         webhook_code=str(body.get("webhook_code") or "?"),
                         environment=body.get("environment"), payload=body)
    with session() as sess:
        sess.add(event)
        try:
            routed = route_event(sess, body)
            event.processed_at = datetime.now(UTC)
        except Exception as e:  # noqa: BLE001
            event.error = f"{type(e).__name__}: {e}"[:2000]
            routed = None
            log.exception("webhook routing failed")
    log.info("webhook %s/%s item=%s -> %s", event.webhook_type, event.webhook_code,
             body.get("item_id"), routed, extra={"item_id": body.get("item_id")})
    return {"ok": True}
