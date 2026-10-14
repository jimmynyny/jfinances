"""Job: refresh subscriptions found in transactions (services/recurring.py).

Queued after every transactions sync; household-wide, so one queued copy at a
time (jobs.queue.enqueue).
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..services import recurring
from .queue import handler

log = logging.getLogger(__name__)


@handler("detect_recurring")
def detect_recurring(sess: Session, payload: dict) -> None:
    found = recurring.sync_streams(sess)
    log.info("recurring streams found: %d", found)
