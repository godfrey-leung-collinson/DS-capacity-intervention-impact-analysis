"""Capacity metrics aligned with MLP-Outlet-Capacity-UI definitions."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from capacity_impact.config import MetricSettings, Period
from capacity_impact.exc import DataInvalid, DataMissing, DataInconsistent

QUADRANT_LABELS = {
    "high util, high air traffic": "Capacity risk",
    "low util, high air traffic": "Capacity/Opportunity gap",
    "high util, low air traffic": "Usage anomaly",
    "low util, low air traffic": "Low priority",
}


def _require_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {', '.join(sorted(missing))}")


def _in_period(values: pd.Series, period: Period) -> pd.Series:
    timestamps = pd.to_datetime(values)
    return timestamps.ge(period.start) & timestamps.lt(period.end)


def compute_visit_metrics(
    visits: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    outlet_code: str,
    number_of_seats: float | None = None,
) -> dict[str, float]:
    """Compute PP volume, occupancy, (PP) utilisation and weekly-peak proxy."""
    _require_columns(
        visits,
        {"visit_interval", "outlet_code", "total_visits", "number_of_seats"},
        "visits",
    )
    code = outlet_code.strip().upper()
    work = visits.copy()
    work["outlet_code"] = work["outlet_code"].astype(str).str.strip().str.upper()
    work = work[
        work["outlet_code"].eq(code)
        & _in_period(work["visit_interval"], period)
    ].copy()
    if work.empty:
        return {
            "pp_visit_volume": 0.0,
            "avg_monthly_visits": 0.0,
            "peak_pp_estimated_occupancy": np.nan,
            "peak_pp_utilisation_rate": np.nan,
            "estimated_pp_market_share": np.nan,
            "number_of_seats": np.nan,
            "effective_seat_capacity": np.nan,
        }

    work["visit_interval"] = pd.to_datetime(work["visit_interval"])
    work["total_visits"] = pd.to_numeric(work["total_visits"], errors="coerce").fillna(0)
    work = (
        work.groupby(["outlet_code", "visit_interval"], as_index=False)
        .agg(total_visits=("total_visits", "sum"), number_of_seats=("number_of_seats", "last"))
        .sort_values("visit_interval")
    )
    observed_mondays = (
        work["visit_interval"]
        - pd.to_timedelta(work["visit_interval"].dt.weekday, unit="D")
    ).dt.normalize().unique()
    observed_months = work["visit_interval"].dt.to_period("M").unique()

    available_seats = pd.to_numeric(work["number_of_seats"], errors="coerce").dropna()
    if number_of_seats is None and available_seats.empty:
        raise DataInvalid(f"{code}: no valid number_of_seats value or override")
    seats = (
        float(number_of_seats)
        if number_of_seats is not None
        else float(available_seats.iloc[-1])
    )
    effective_capacity = seats * settings.max_allowed_seat_proportion
    if effective_capacity <= 0:
        raise DataInvalid(f"{code}: effective seat capacity must be positive")

    full_index = pd.date_range(
        period.start,
        period.end,
        freq=f"{settings.slot_minutes}min",
        inclusive="left",
    )
    work = (
        work.set_index("visit_interval")
        .reindex(full_index)
        .rename_axis("visit_interval")
        .reset_index()
    )
    work["outlet_code"] = code
    work["total_visits"] = work["total_visits"].fillna(0)

    # TODO: NOT NECESSARILY CORRECT imputation - historical records of number of seats data are not currently retained. Need to look into this in future
    work["number_of_seats"] = work["number_of_seats"].ffill().bfill().fillna(seats)

    rolling_slots = max(1, math.ceil(settings.dwell_time_minutes / settings.slot_minutes))
    work["estimated_occupancy"] = (
        work["total_visits"].rolling(rolling_slots, min_periods=1).sum()
    )
    work["pp_utilisation_rate"] = work["estimated_occupancy"] / effective_capacity
    monday = (
        work["visit_interval"]
        - pd.to_timedelta(work["visit_interval"].dt.weekday, unit="D")
    ).dt.normalize()
    weekly_peaks = work.loc[monday.isin(observed_mondays)].groupby(
        monday[monday.isin(observed_mondays)]
    )["pp_utilisation_rate"].max()
    month = work["visit_interval"].dt.to_period("M")
    monthly_visits = work.loc[month.isin(observed_months)].groupby(
        month[month.isin(observed_months)]
    )["total_visits"].sum()

    return {
        "pp_visit_volume": float(work["total_visits"].sum()),
        "avg_monthly_visits": float(monthly_visits.mean()),
        "peak_pp_estimated_occupancy": float(work["estimated_occupancy"].max()),
        "peak_pp_utilisation_rate": float(work["pp_utilisation_rate"].max()),
        "average_pp_estimated_occupancy": float(work["estimated_occupancy"].mean()),
        "average_pp_utilisation_rate": float(work["pp_utilisation_rate"].mean()),
        # This reproduces the source dashboard's label. It is an average weekly
        # peak utilisation proxy, not conventional passenger market share.
        "estimated_pp_market_share": float(weekly_peaks.mean()),
        "number_of_seats": seats,
        "effective_seat_capacity": effective_capacity,
    }


def compute_airport_traffic_peak(
    flights: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    airport_code: str,
) -> float:
    """Compute peak departures in the configured forward-looking window."""
    _require_columns(
        flights,
        {"flight_interval", "airport_code", "departure_flight_count"},
        "flights",
    )
    code = airport_code.strip().upper()
    work = flights.copy()
    work["airport_code"] = work["airport_code"].astype(str).str.strip().str.upper()
    work = work[
        work["airport_code"].eq(code)
        & _in_period(work["flight_interval"], period)
    ].copy()
    if work.empty:
        return np.nan

    work["flight_interval"] = pd.to_datetime(work["flight_interval"])
    work["departure_flight_count"] = pd.to_numeric(
        work["departure_flight_count"], errors="coerce"
    ).fillna(0)
    counts = work.groupby("flight_interval")["departure_flight_count"].sum()
    full_index = pd.date_range(
        period.start,
        period.end,
        freq=f"{settings.slot_minutes}min",
        inclusive="left",
    )
    counts = counts.reindex(full_index, fill_value=0)
    forward_slots = max(
        1,
        math.ceil(settings.forward_traffic_hours * 60 / settings.slot_minutes),
    )
    forward = counts.iloc[::-1].rolling(forward_slots, min_periods=1).sum().iloc[::-1]
    return float(forward.max())


def compute_traffic_threshold(
    pre_traffic_peaks: pd.Series,
    settings: MetricSettings,
) -> float:
    """Use one fixed baseline threshold for both pre and post classifications."""
    if settings.traffic_threshold_mode == "fixed":
        return float(settings.high_traffic_threshold)
    valid = pd.to_numeric(pre_traffic_peaks, errors="coerce")
    valid = valid[valid.gt(0)]
    if valid.empty:
        raise DataMissing("Cannot derive a pre-period traffic threshold from empty data")
    return float(round(np.percentile(valid, settings.traffic_percentile)))


def assign_quadrant(
    utilisation: float,
    traffic: float,
    utilisation_threshold: float,
    traffic_threshold: float,
) -> tuple[str | None, str | None]:
    """Return canonical category and display label, inclusive at thresholds."""
    if pd.isna(utilisation) or pd.isna(traffic):
        return None, None
    util_group = "high" if utilisation >= utilisation_threshold else "low"
    traffic_group = "high" if traffic >= traffic_threshold else "low"
    category = f"{util_group} util, {traffic_group} air traffic"
    return category, QUADRANT_LABELS[category]


def period_days(period: Period) -> float:
    """Duration used to normalise visit volume across unequal periods."""
    return (period.end - period.start).total_seconds() / 86_400
