"""Insights: cash flow and spending over time (services/insights.py, docs/80 "Insights").

Every endpoint takes the same slice: `from`/`to` (default: the current month
and the eleven before it), `scope` (personal, business or all, by
accounts.is_business) and repeatable `account_id`. Read-only.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..services import insights
from ..services.insights import Filters, Grain, Scope
from ._common import ApiError, parse_uuid
from ._common import plain as _json

router = APIRouter()


def _year_earlier(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # Feb 29
        return d.replace(year=d.year - 1, day=28)


class Slice:
    """The shared query parameters, as a dependency."""

    def __init__(self, from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                 scope: Scope = "personal", account_id: list[str] | None = Query(default=None)):
        end = to or datetime.now(UTC).date()
        start = from_ or date(end.year - (1 if end.month < 12 else 0), end.month % 12 + 1, 1)
        if start > end:
            raise ApiError(400, "bad_request", "`from` is after `to`")
        self.filters = Filters(start, end, scope, tuple(parse_uuid(x, "account_id") for x in account_id or []))

    def echo(self) -> dict:
        f = self.filters
        return {"from": f.start.isoformat(), "to": f.end.isoformat(), "scope": f.scope}


@router.get("/insights/cashflow")
def cashflow(grain: Grain = "month", s: Slice = Depends(), _: Principal = Depends(current_user),
             sess: Session = Depends(get_session)):
    f = s.filters
    return _json({**s.echo(), "grain": grain, **insights.cashflow(insights.load_rows(sess, f), f, grain)})


@router.get("/insights/spending")
def spending(grain: Grain = "month", group: Literal["category", "merchant"] = "category",
             category: str | None = None, top: int = Query(default=7, ge=1, le=20), s: Slice = Depends(),
             _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    f = s.filters
    data = insights.spending(insights.load_rows(sess, f), f, grain, category=category, group=group, top=top)
    return _json({**s.echo(), "grain": grain, "group": group, "category": category, **data})


@router.get("/insights/compare")
def compare(category: str | None = None, s: Slice = Depends(), _: Principal = Depends(current_user),
            sess: Session = Depends(get_session)):
    """This range against the same range a year earlier."""
    f = s.filters
    prev = Filters(_year_earlier(f.start), _year_earlier(f.end), f.scope, f.account_ids)
    rows = insights.compare(insights.load_rows(sess, f), insights.load_rows(sess, prev), category=category)
    return _json({**s.echo(), "previous": {"from": prev.start, "to": prev.end}, "category": category, "rows": rows})


@router.get("/insights/merchants")
def merchants(category: str | None = None, top: int = Query(default=25, ge=1, le=100), s: Slice = Depends(),
              _: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    f = s.filters
    rows = insights.merchants(insights.load_rows(sess, f), f, insights.first_seen(sess, f), category=category, top=top)
    return _json({**s.echo(), "category": category, "merchants": rows})


@router.get("/insights/patterns")
def patterns(category: str | None = None, s: Slice = Depends(), _: Principal = Depends(current_user),
             sess: Session = Depends(get_session)):
    f = s.filters
    data = insights.patterns(insights.load_rows(sess, f), f, category=category)
    return _json({**s.echo(), "category": category, **data})
