"""Investment performance against benchmarks (services/performance.py, services/benchmarks.py).

docs/80 "Investment performance".
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..jobs.queue import enqueue
from ..services import benchmarks, performance
from ._common import parse_uuid, plain

router = APIRouter()

RANGES = {"3m": 92, "6m": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653}


@router.get("/investments/performance")
def get_performance(range: str = "1y", account_id: str | None = None, benchmark: str | None = None,
                    _: Principal = Depends(current_user),
                    sess: Session = Depends(get_session)):
    """Time-weighted return of the portfolio (or one account) and, from the
    same first day, the cumulative return of each benchmark asked for
    (`benchmark=sp500,dow`)."""
    today = datetime.now(UTC).date()
    start = today - timedelta(days=RANGES.get(range, 366))
    acct = parse_uuid(account_id, "account_id") if account_id else None
    data = performance.performance(sess, start, today, today, acct)
    base = data["series"][0]["date"] if data["series"] else start
    out = []
    for key in [k for k in (benchmark or "").split(",") if k in benchmarks.BY_KEY]:
        b = benchmarks.BY_KEY[key]
        g = benchmarks.growth(sess, key, base, today)
        if g is None:
            out.append({"key": key, "label": b.label, "source": None, "points": []})
            continue
        points, source = g
        out.append({"key": key, "label": b.label, "source": source,
                    "points": [{"date": d, "return": r} for d, r in sorted(points.items())]})
    return plain({"range": range, "from": base, "to": today, **data, "benchmarks": out,
                  "available": benchmarks.available(sess)})


@router.post("/prices/refresh", status_code=202)
def refresh_prices(_: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Fetch market data now instead of after tonight's close."""
    return {"queued": enqueue(sess, "refresh_prices", {}) is not None}
