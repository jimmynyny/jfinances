"""Sparkline series: daily, gap-free, carried forward, ending at today."""
from __future__ import annotations

from datetime import date
from decimal import Decimal as D

from server.app.services.trends import fill_daily


def test_carries_value_from_before_the_window_and_fills_gaps():
    pts = [(date(2026, 9, 25), D("100")), (date(2026, 10, 3), D("130"))]
    out = fill_daily(pts, date(2026, 10, 1), date(2026, 10, 5))
    assert out == [D("100"), D("100"), D("130"), D("130"), D("130")]


def test_series_starts_at_first_known_day():
    pts = [(date(2026, 10, 3), D("5"))]
    assert fill_daily(pts, date(2026, 10, 1), date(2026, 10, 4)) == [D("5"), D("5")]


def test_none_values_are_ignored_and_empty_input_gives_empty_series():
    assert fill_daily([(date(2026, 10, 2), None)], date(2026, 10, 1), date(2026, 10, 3)) == []
    assert fill_daily([], date(2026, 10, 1), date(2026, 10, 3)) == []
