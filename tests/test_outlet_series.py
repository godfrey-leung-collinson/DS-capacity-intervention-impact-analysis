"""Tests for outlet-level time-series helpers."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from capacity_impact.config import LoungeIntervention, Period
from dashboards.outlet_series import (
    build_outlet_slot_series,
    daily_utilisation_series,
    daily_visit_volume_series,
    outlet_metric_timeseries,
    weekly_peak_utilisation_series,
)


def _lounge() -> LoungeIntervention:
    return LoungeIntervention(
        outlet_code="TEST1",
        intervention_date=datetime(2026, 1, 16),
        pre=Period(datetime(2026, 1, 1), datetime(2026, 1, 16)),
        post=Period(datetime(2026, 1, 16), datetime(2026, 1, 31)),
    )


def _visits() -> pd.DataFrame:
    pre_days = pd.date_range("2026-01-01 10:00", "2026-01-15 10:00", freq="D")
    post_days = pd.date_range("2026-01-16 10:00", "2026-01-30 10:00", freq="D")
    timestamps = pre_days.append(post_days)
    return pd.DataFrame(
        {
            "visit_interval": timestamps,
            "outlet_code": ["TEST1"] * len(timestamps),
            "airport_code": ["TST"] * len(timestamps),
            "number_of_seats": [100] * len(timestamps),
            "total_visits": [10] * len(pre_days) + [20] * len(post_days),
        }
    )


def test_build_outlet_slot_series_labels_periods(settings) -> None:
    slots = build_outlet_slot_series(_visits(), _lounge(), settings)
    assert not slots.empty
    assert set(slots["period"]) == {"pre", "post"}


def test_weekly_and_daily_series(settings) -> None:
    slots = build_outlet_slot_series(_visits(), _lounge(), settings)
    weekly = weekly_peak_utilisation_series(slots)
    daily = daily_utilisation_series(slots)
    visits = daily_visit_volume_series(slots)
    assert not weekly.empty
    assert not daily.empty
    assert not visits.empty
    assert "daily_visit_volume" in visits.columns


def test_outlet_metric_timeseries(settings) -> None:
    slots = build_outlet_slot_series(_visits(), _lounge(), settings)
    series = outlet_metric_timeseries("weekly_peak_pp_utilisation", slots)
    assert "weekly_peak_pp_utilisation" in series.columns
    assert set(series["period"]) <= {"pre", "post"}
