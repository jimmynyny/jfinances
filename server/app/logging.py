"""JSON-lines logging with a per-request id and token redaction.

Railway shows one line per log record; JSON lets us filter by field. Anything
that looks like a Plaid token, a JWT, or a bearer credential is replaced
before it is written, as a last line of defence behind "never log it".
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import uuid

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_REDACT = [
    re.compile(r"access-(?:sandbox|production|development)-[0-9a-f-]{20,}"),
    re.compile(r"public-(?:sandbox|production|development)-[0-9a-f-]{20,}"),
    re.compile(r"link-(?:sandbox|production|development)-[0-9a-f-]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)\btoken\s+[A-Za-z0-9]{20,}"),  # Tiingo's Authorization header
    re.compile(r"(?i)(?:api_key|token)=[A-Za-z0-9]{16,}"),  # FRED takes its key in the query string
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),  # OpenAI
]


def redact(text: str) -> str:
    for rx in _REDACT:
        text = rx.sub("[redacted]", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        rid = request_id_var.get()
        if rid:
            payload["request_id"] = rid
        for key in ("service", "item_id", "job_id", "job_kind", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure(level: str = "info", service: str = "web") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # httpx logs every request URL at INFO, and FRED's key travels in the URL: never let those through.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    old_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.service = service
        return record

    logging.setLogRecordFactory(factory)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]
