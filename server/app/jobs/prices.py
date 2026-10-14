"""Job: bring market data up to date (services/prices.py).

Daily after US markets close (worker schedule), on the worker's first start
when no prices are stored yet, and on demand (POST /prices/refresh).
Household-wide, so one queued copy at a time.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..services import prices
from .queue import handler

log = logging.getLogger(__name__)


@handler("refresh_prices")
def refresh_prices(sess: Session, payload: dict) -> None:
    results = prices.refresh(sess)
    stored = sum(n for n in results.values() if n > 0)
    failed = sorted(k for k, n in results.items() if n < 0)
    log.info("prices: %d series, %d closes stored%s", len(results), stored,
             f", failed: {', '.join(failed)}" if failed else "")
