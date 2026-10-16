"""Jobs: refresh recurring charges found in transactions (services/recurring.py),
then sort subscriptions from the rest (services/subscriptions.py).

Queued after every transactions sync; household-wide, so one queued copy at a
time (jobs.queue.enqueue). `sort_subscriptions` alone follows "Look for new
ones", which detects in the request but leaves the model's call to the worker.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..services import recurring, subscriptions
from .queue import handler

log = logging.getLogger(__name__)


@handler("detect_recurring")
def detect_recurring(sess: Session, payload: dict) -> None:
    found = recurring.sync_streams(sess)
    log.info("recurring streams found: %d", found)
    sort_subscriptions(sess, payload)


@handler("sort_subscriptions")
def sort_subscriptions(sess: Session, payload: dict) -> None:
    log.info("recurring streams sorted: %d", subscriptions.sort_streams(sess))
