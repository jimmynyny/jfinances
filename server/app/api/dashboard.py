"""Each person's Overview: an ordered grid of widgets (docs/80 "Dashboard").

A widget is a built-in Overview section or an Insights view pinned with the
settings it had. Each person arranges their own; nobody sees or changes
another's. The first read seeds DEFAULTS (Overview as it always was); after
that an emptied dashboard stays empty until "reset".
"""
from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import current_user
from ..auth.human import Principal
from ..db import get_session
from ..models import DashboardWidget, User
from ._common import ApiError, parse_uuid

router = APIRouter()

Size = Literal["narrow", "wide", "full"]
#: Every view a widget can show, with the size it starts at.
VIEWS: dict[str, Size] = {
    # Overview's own sections
    "networth": "full", "split": "full", "upcoming": "narrow", "alerts": "narrow", "calendar": "full",
    "accounts": "full",
    # Insights
    "cashflow": "full", "money_flow": "wide", "income_sources": "narrow", "spending": "full", "merchants": "full",
    "patterns": "wide", "compare": "narrow", "subscriptions": "wide", "recurring": "wide", "networth_classes": "full",
    "homes": "narrow", "loans": "narrow", "cards": "wide", "performance": "full",
}
DEFAULTS = ["networth", "split", "upcoming", "alerts", "calendar", "accounts"]
MAX_WIDGETS = 40
MAX_SETTINGS = 2000  # bytes of JSON


def widget_json(w: DashboardWidget) -> dict:
    return {"id": str(w.id), "view": w.view, "settings": w.settings or {}, "size": w.size, "position": w.position}


def _mine(sess: Session, p: Principal) -> list[DashboardWidget]:
    return list(sess.execute(select(DashboardWidget).where(DashboardWidget.user_id == p.user_id)
                             .order_by(DashboardWidget.position, DashboardWidget.created_at)).scalars())


def _seed(sess: Session, user: User) -> None:
    for i, view in enumerate(DEFAULTS):
        sess.add(DashboardWidget(user_id=user.id, view=view, settings={}, size=VIEWS[view], position=i))
    user.dashboard_columns = user.dashboard_columns or 2
    sess.flush()


def _user(sess: Session, p: Principal) -> User:
    user = sess.get(User, p.user_id)
    if user is None:
        raise ApiError(404, "not_found", "user not found")
    return user


def _dashboard(sess: Session, p: Principal) -> dict:
    user = _user(sess, p)
    if user.dashboard_columns is None:
        _seed(sess, user)
    return {"columns": user.dashboard_columns, "widgets": [widget_json(w) for w in _mine(sess, p)]}


def _settings(v: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(v)) > MAX_SETTINGS:
        raise ApiError(400, "bad_request", "settings too large")
    return v


@router.get("/dashboard")
def get_dashboard(p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    return _dashboard(sess, p)


class WidgetIn(BaseModel):
    view: str
    settings: dict[str, Any] = Field(default_factory=dict)
    size: Size | None = None


@router.post("/dashboard/widgets", status_code=201)
def add_widget(body: WidgetIn, p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Pin a view, with the settings it has now, at the end of the dashboard."""
    if body.view not in VIEWS:
        raise ApiError(400, "bad_request", f"unknown view {body.view!r}")
    _dashboard(sess, p)  # a first pin keeps the defaults above it
    if len(_mine(sess, p)) >= MAX_WIDGETS:
        raise ApiError(400, "bad_request", f"a dashboard holds {MAX_WIDGETS} widgets at most")
    last = sess.execute(select(func.max(DashboardWidget.position)).where(DashboardWidget.user_id == p.user_id)).scalar()
    w = DashboardWidget(user_id=p.user_id, view=body.view, settings=_settings(body.settings),
                        size=body.size or VIEWS[body.view], position=(last if last is not None else -1) + 1)
    sess.add(w)
    sess.flush()
    return widget_json(w)


class WidgetPatch(BaseModel):
    size: Size | None = None
    settings: dict[str, Any] | None = None


def _get(sess: Session, p: Principal, widget_id: str) -> DashboardWidget:
    w = sess.get(DashboardWidget, parse_uuid(widget_id))
    if w is None or w.user_id != p.user_id:
        raise ApiError(404, "not_found", "widget not found")
    return w


@router.patch("/dashboard/widgets/{widget_id}")
def patch_widget(widget_id: str, body: WidgetPatch, p: Principal = Depends(current_user),
                 sess: Session = Depends(get_session)):
    w = _get(sess, p, widget_id)
    if body.size is not None:
        w.size = body.size
    if body.settings is not None:
        w.settings = _settings(body.settings)
    sess.flush()
    return widget_json(w)


@router.delete("/dashboard/widgets/{widget_id}", status_code=204)
def delete_widget(widget_id: str, p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    sess.delete(_get(sess, p, widget_id))
    sess.flush()
    return None


class OrderIn(BaseModel):
    widget_ids: list[str]


@router.put("/dashboard/order")
def reorder(body: OrderIn, p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """The whole dashboard in its new order: every widget, each once."""
    mine = {str(w.id): w for w in _mine(sess, p)}
    if sorted(body.widget_ids) != sorted(mine):
        raise ApiError(400, "bad_request", "widget_ids must list every widget on the dashboard once")
    for i, wid in enumerate(body.widget_ids):
        mine[wid].position = i
    sess.flush()
    return _dashboard(sess, p)


class ColumnsIn(BaseModel):
    columns: Literal[1, 2, 3]


@router.put("/dashboard/columns")
def set_columns(body: ColumnsIn, p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    _dashboard(sess, p)
    _user(sess, p).dashboard_columns = body.columns
    sess.flush()
    return _dashboard(sess, p)


@router.post("/dashboard/reset")
def reset(p: Principal = Depends(current_user), sess: Session = Depends(get_session)):
    """Back to the default Overview."""
    for w in _mine(sess, p):
        sess.delete(w)
    sess.flush()
    user = _user(sess, p)
    user.dashboard_columns = None
    _seed(sess, user)
    return _dashboard(sess, p)
