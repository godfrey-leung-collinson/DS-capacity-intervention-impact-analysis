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
    """
    Validate that a DataFrame contains required columns.

    Parameters
    ----------
    df : pandas.DataFrame
        Input frame to validate.
    required : set of str
        Required column names.
    name : str
        Dataset name used in error messages.

    Raises
    ------
    DataMissing
        If any required columns are missing.
    """
    missing = required.difference(df.columns)
    if missing:
        raise DataMissing(f"{name} is missing columns: {', '.join(sorted(missing))}")


def _in_period(values: pd.Series, period: Period) -> pd.Series:
    """
    Return a boolean mask for timestamps within a half-open period.

    Parameters
    ----------
    values : pandas.Series
        Timestamp series.
    period : Period
        Half-open analysis window.

    Returns
    -------
    pandas.Series
        Boolean mask where ``period.start <= timestamp < period.end``.
    """
    timestamps = pd.to_datetime(values)
    return timestamps.ge(period.start) & timestamps.lt(period.end)


def build_outlet_slot_frame(
    visits: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    outlet_code: str,
    number_of_seats: float | None = None,
) -> pd.DataFrame:
    """
    Build slot-level visits, occupancy and utilisation for one outlet.

    Parameters
    ----------
    visits : pandas.DataFrame
        Visit extract.
    period : Period
        Half-open analysis window.
    settings : MetricSettings
        Metric calculation settings.
    outlet_code : str
        Outlet identifier.
    number_of_seats : float or None, optional
        Seat-count override for effective capacity.

    Returns
    -------
    pandas.DataFrame
        Slot-level frame with occupancy and utilisation columns. Empty when
        no visits exist for the outlet in the period.

    Raises
    ------
    DataInvalid
        If seat capacity cannot be resolved or is non-positive.
    """
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
        return pd.DataFrame(
            columns=[
                "visit_interval",
                "outlet_code",
                "total_visits",
                "number_of_seats",
                "estimated_occupancy",
                "pp_utilisation_rate",
            ]
        )

    work["visit_interval"] = pd.to_datetime(work["visit_interval"])
    work["total_visits"] = pd.to_numeric(work["total_visits"], errors="coerce").fillna(0)
    work = (
        work.groupby(["outlet_code", "visit_interval"], as_index=False)
        .agg(total_visits=("total_visits", "sum"), number_of_seats=("number_of_seats", "last"))
        .sort_values("visit_interval")
    )

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
    return work


def compute_visit_metrics(
    visits: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    outlet_code: str,
    number_of_seats: float | None = None,
) -> dict[str, float]:
    """
    Compute PP volume, occupancy, utilisation and weekly-peak proxy.

    Parameters
    ----------
    visits : pandas.DataFrame
        Visit extract.
    period : Period
        Half-open analysis window.
    settings : MetricSettings
        Metric calculation settings.
    outlet_code : str
        Outlet identifier.
    number_of_seats : float or None, optional
        Seat-count override for effective capacity.

    Returns
    -------
    dict
        Period-level visit, occupancy, utilisation and market-share proxy metrics.
    """
    code = outlet_code.strip().upper()
    work = build_outlet_slot_frame(
        visits,
        period,
        settings,
        outlet_code=code,
        number_of_seats=number_of_seats,
    )
    if work.empty:
        return {
            "pp_visit_volume": 0.0,
            "avg_monthly_visits": 0.0,
            "peak_pp_estimated_occupancy": np.nan,
            "peak_pp_utilisation_rate": np.nan,
            "average_pp_estimated_occupancy": np.nan,
            "average_pp_utilisation_rate": np.nan,
            "estimated_pp_market_share": np.nan,
            "number_of_seats": np.nan,
            "effective_seat_capacity": np.nan,
        }

    available_seats = pd.to_numeric(work["number_of_seats"], errors="coerce").dropna()
    seats = (
        float(number_of_seats)
        if number_of_seats is not None
        else float(available_seats.iloc[-1])
    )
    effective_capacity = seats * settings.max_allowed_seat_proportion

    observed_mondays = (
        work["visit_interval"]
        - pd.to_timedelta(work["visit_interval"].dt.weekday, unit="D")
    ).dt.normalize().unique()
    observed_months = work["visit_interval"].dt.to_period("M").unique()
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


def _airport_forward_traffic(
    flights: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    airport_code: str,
) -> pd.Series:
    """Return forward-window departure counts for an airport and period."""
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
        return pd.Series(dtype=float)

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
    return counts.iloc[::-1].rolling(forward_slots, min_periods=1).sum().iloc[::-1]


def compute_airport_traffic_peak(
    flights: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    airport_code: str,
) -> float:
    """
    Compute peak forward departures in the configured traffic window.

    Parameters
    ----------
    flights : pandas.DataFrame
        Flight extract.
    period : Period
        Half-open analysis window.
    settings : MetricSettings
        Metric calculation settings.
    airport_code : str
        Airport identifier.

    Returns
    -------
    float
        Peak forward departure count, or ``NaN`` when no flight data exist.
    """
    forward = _airport_forward_traffic(
        flights,
        period,
        settings,
        airport_code=airport_code,
    )
    if forward.empty:
        return np.nan
    return float(forward.max())


def compute_airport_traffic_average(
    flights: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    airport_code: str,
) -> float:
    """Compute mean forward departures in the configured traffic window."""
    forward = _airport_forward_traffic(
        flights,
        period,
        settings,
        airport_code=airport_code,
    )
    if forward.empty:
        return np.nan
    return float(forward.mean())


def compute_visit_to_flight_ratio(
    visits: pd.DataFrame,
    flights: pd.DataFrame,
    period: Period,
    settings: MetricSettings,
    *,
    outlet_code: str,
    airport_code: str,
    number_of_seats: float | None = None,
) -> float:
    """
    Compute the period visit-to-flight ratio.

    For each slot, forward departures in the configured window are matched to
    outlet visit totals. The period ratio is total visits divided by the sum of
    those forward departure counts across the period.
    """
    slot_frame = build_outlet_slot_frame(
        visits,
        period,
        settings,
        outlet_code=outlet_code,
        number_of_seats=number_of_seats,
    )
    forward = _airport_forward_traffic(
        flights,
        period,
        settings,
        airport_code=airport_code,
    )
    if slot_frame.empty or forward.empty:
        return np.nan

    visits_by_slot = slot_frame.set_index("visit_interval")["total_visits"]
    forward_by_slot = forward.reindex(visits_by_slot.index, fill_value=0)
    total_forward = float(forward_by_slot.sum())
    if total_forward <= 0:
        return np.nan
    return float(visits_by_slot.sum() / total_forward)


def compute_traffic_threshold(
    pre_traffic_peaks: pd.Series,
    settings: MetricSettings,
) -> float:
    """
    Derive one traffic threshold reused for pre and post quadrant assignment.

    Parameters
    ----------
    pre_traffic_peaks : pandas.Series
        Pre-period airport traffic peaks across outlets.
    settings : MetricSettings
        Threshold mode and percentile settings.

    Returns
    -------
    float
        Traffic threshold value.

    Raises
    ------
    DataMissing
        If percentile mode is selected but no valid pre-period peaks exist.
    """
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
    """
    Assign a capacity quadrant from utilisation and traffic values.

    Parameters
    ----------
    utilisation : float
        Peak PP utilisation rate.
    traffic : float
        Airport traffic index.
    utilisation_threshold : float
        High-utilisation threshold (inclusive).
    traffic_threshold : float
        High-traffic threshold (inclusive).

    Returns
    -------
    category : str or None
        Canonical quadrant category key.
    label : str or None
        Human-readable quadrant label.
    """
    if pd.isna(utilisation) or pd.isna(traffic):
        return None, None
    util_group = "high" if utilisation >= utilisation_threshold else "low"
    traffic_group = "high" if traffic >= traffic_threshold else "low"
    category = f"{util_group} util, {traffic_group} air traffic"
    return category, QUADRANT_LABELS[category]


def period_days(period: Period) -> float:
    """
    Return period length in days for visit-volume normalisation.

    Parameters
    ----------
    period : Period
        Half-open analysis window.

    Returns
    -------
    float
        Period duration in days.
    """
    return (period.end - period.start).total_seconds() / 86_400
