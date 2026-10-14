"""One read for the phone's widgets and its Home screen (docs/80 "Phones").

A widget refresh is a single request: net worth with its 30-day line, this
month's money in and out with the biggest spending categories, the next two
weeks of expected charges, every visible account's balance, and how many
alerts are waiting. Each part is the same computation the dashboard's own
endpoint makes; nothing here is new arithmetic.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..services import alerts, insights
from . import networth, overview, recurring
from ._common import plain

router = APIRouter()

#: The widget lists show at most this many upcoming charges.
UPCOMING_MAX = 12


@router.get("/glance")
def glance(p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    now = datetime.now(UTC)
    today = now.date()
    ov = overview.overview(p, sess)
    hist = networth.history("1m", p, sess)
    month = insights.Filters(today.replace(day=1), today, "personal", ())
    flow = insights.cashflow(insights.load_rows(sess, month), month, "month")
    up = recurring.upcoming(14, p, sess)
    accounts = [{**{k: a[k] for k in ("id", "name", "mask", "institution_name", "type", "subtype", "kind",
                                      "manual_category", "is_liability", "current_balance", "available_balance",
                                      "credit_limit", "iso_currency", "balance_updated_at", "is_business")},
                 "group": g["key"], "group_label": g["label"], "trend": a.get("trend", [])}
                for g in ov["groups"] for a in g["accounts"] if not a["is_hidden"]]
    return plain({
        "as_of": now.isoformat(),
        "net_worth": {"net": ov["net_worth"], "assets": ov["assets"], "liabilities": ov["liabilities"],
                      "change_1m": ov["change_1m"], "as_of": ov["as_of"],
                      "points": [{"date": x["date"], "net": x["net"]} for x in hist["points"]]},
        "month": {"from": month.start, "to": month.end, **flow["totals"],
                  "categories": flow["spending_categories"]},
        "upcoming": {"from": up["from"], "to": up["to"], "total": up["total"],
                     "count": len(up["items"]), "items": up["items"][:UPCOMING_MAX]},
        "accounts": accounts,
        "groups": [{"key": g["key"], "label": g["label"], "is_liability": g["is_liability"], "total": g["total"]}
                   for g in ov["groups"]],
        "alerts": {"count": len(alerts.find_alerts(sess, today, 60))},
        "attention": ov["items_needing_attention"],
    })
