"""Subscriptions, told apart from other recurring charges by a language model.

A subscription is a service the household pays for and subscribes to: streaming,
news, software and apps, Uber One. A mortgage, a loan, rent, utilities,
insurance, membership dues and bank fees repeat too, but are "recurring".

Only merchant names leave the app (OpenAI, OPENAI_API_KEY; the privacy page says
so): never amounts, dates, accounts or people. Each stream is sorted once. A
merchant already sorted (by the user above all) answers for its new streams
without asking, and the user's choice (`kind_source = "user"`, PATCH
/recurring/{id}) is never redone. Without a key nothing is sorted and every
stream reads "recurring". A failed call is logged by status only and retried on
the next detection run.
"""
from __future__ import annotations

import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import RecurringStream

log = logging.getLogger(__name__)

URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT = httpx.Timeout(60.0, connect=10.0)
#: Merchants per request.
BATCH = 80

PROMPT = """You sort a household's recurring bank charges. Each name is a merchant as \
it appears on a bank or card statement, sometimes abbreviated or truncated.

A subscription is a service the household chose to pay for and subscribes to: \
streaming video or music, news and magazines, software, apps and cloud storage, \
online services, meal kits, and paid tiers of consumer services (Uber One, \
Amazon Prime, DashPass, YouTube Premium, The New York Times, Spotify, iCloud).

Not a subscription: mortgages, loans, rent and property payments, utilities \
(power, gas, water, phone, internet), insurance, taxes, membership fees and \
dues, bank and account fees, transfers, payroll, charity, and payments to a \
person or a business's bill-pay processor.

When unsure, answer false. Answer for every name, spelled exactly as given."""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {"results": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["name", "subscription"],
        "properties": {"name": {"type": "string"}, "subscription": {"type": "boolean"}},
    }}},
}


class ProviderError(RuntimeError):
    """The model gave no usable answer. The message is safe to keep (no key, no names)."""


def ask(client: httpx.Client, names: list[str], key: str, model: str) -> dict[str, bool]:
    """{name: is a subscription} for the names the model answered."""
    body = {
        "model": model,
        "messages": [{"role": "system", "content": PROMPT},
                     {"role": "user", "content": json.dumps(names)}],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "sorted", "strict": True, "schema": SCHEMA}},
    }
    try:
        r = client.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise ProviderError(f"no answer ({type(e).__name__})") from None
    if r.status_code != 200:
        raise ProviderError(f"HTTP {r.status_code}")
    try:
        content = r.json()["choices"][0]["message"]["content"]
        results = json.loads(content)["results"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise ProviderError("unexpected answer") from None
    asked = set(names)
    return {x["name"]: bool(x["subscription"]) for x in results
            if isinstance(x, dict) and x.get("name") in asked}


def sort_streams(sess: Session, client: httpx.Client | None = None) -> int:
    """Sort every stream not yet sorted (dismissed ones wait). Returns how many were."""
    todo = sess.execute(select(RecurringStream).where(RecurringStream.kind_source.is_(None),
                                                      RecurringStream.status != "dismissed")).scalars().all()
    if not todo:
        return 0
    # A merchant sorted before answers for its new streams; the user's choice over the model's.
    known: dict[str, tuple[str, str]] = {}
    for r in sess.execute(select(RecurringStream).where(RecurringStream.kind_source.is_not(None))).scalars():
        k = r.merchant.lower()
        if k not in known or r.kind_source == "user":
            known[k] = (r.kind or "recurring", r.kind_source or "model")
    done = 0
    left: list[RecurringStream] = []
    for r in todo:
        if (hit := known.get(r.merchant.lower())) is not None:
            r.kind, r.kind_source = hit
            done += 1
        else:
            left.append(r)
    s = settings()
    if not left or not s.openai_api_key:
        sess.flush()
        return done
    names = sorted({r.merchant for r in left})
    answers: dict[str, bool] = {}
    own = client is None
    client = client or httpx.Client()
    try:
        for i in range(0, len(names), BATCH):
            answers |= ask(client, names[i:i + BATCH], s.openai_api_key, s.openai_model)
    except ProviderError as e:
        log.warning("subscriptions not sorted: %s", e)
    finally:
        if own:
            client.close()
    for r in left:
        if r.merchant in answers:
            r.kind = "subscription" if answers[r.merchant] else "recurring"
            r.kind_source = "model"
            done += 1
    sess.flush()
    return done
