"""Job: market values for offline homes and vehicles. It runs daily, but each
asset is asked about at most once a calendar month (services/valuations.py
records every request first, and the table refuses a second one)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..services import valuations
from .queue import handler


@handler("value_assets")
def value_assets(sess: Session, payload: dict) -> None:
    valuations.run(sess)
