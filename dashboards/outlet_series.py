"""Time-series and distribution helpers for outlet-level dashboard views."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from capacity_impact.config import AnalysisConfig, LoungeIntervention, MetricSettings
from capacity_impact.metrics import build_outlet_slot_frame

OUTLET_SERIES_METRICS: dict[str, dict[str, str]] = {
    "weekly_peak_pp_utilisation": {
        "label": "Weekly peak PP utilisation",
        "format": "percent",
        "column": "weekly_peak_pp_utilisation",
    },
    "daily_average_pp_utilisation": {
        "label": "Daily average PP utilisation",
        "format": "percent",
        "column": "daily_average_pp_utilisation",
    },
    "daily_peak_pp_utilisation": {
        "label": "Daily peak PP utilisation",
        "format": "percent",
        "column": "daily_peak_pp_utilisation",
    },
    "daily_average_pp_occupancy": {
        "label": "Daily average PP occupancy",
        "format": "count",
        "column": "daily_average_pp_occupancy",
    },
}


def lounge_for_outlet(config: AnalysisConfig, outlet_code: str) -> LoungeIntervention | None:
    """
    Look up the configured lounge intervention for an outlet code.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration.
    outlet_code : str
        Outlet identifier.

    Returns
    -------
    LoungeIntervention or None
        Matching lounge config, or ``None`` if not configured.
    """
    code = outlet_code.strip().upper()
    for lounge in config.lounges:
        if lounge.outlet_code == code:
            return lounge
    return None


def build_outlet_slot_series(
    visits: pd.DataFrame,
    lounge: LoungeIntervention,
    settings: MetricSettings,
) -> pd.DataFrame:
    """
    Concatenate pre/post slot-level frames with a period label.

    Parameters
    ----------
    visits : pandas.DataFrame
        Visit extract.
    lounge : LoungeIntervention
        Lounge configuration including pre/post windows.
    settings : MetricSettings
        Metric calculation settings.

    Returns
    -------
    pandas.DataFrame
        Combined slot-level series sorted by ``visit_interval``.
    """
    frames: list[pd.DataFrame] = []
    for period_name, period, seat_override in (
        ("pre", lounge.pre, lounge.pre_number_of_seats),
        ("post", lounge.post, lounge.post_number_of_seats),
    ):
        slots = build_outlet_slot_frame(
            visits,
            period,
            settings,
            outlet_code=lounge.outlet_code,
            number_of_seats=seat_override,
        )
        if slots.empty:
            # TODO: add logging warning to indicate the lounge have no pre/post period (e.g. cases of closed or newly opened lounges)
            continue

        slots = slots.copy()
        slots["period"] = period_name
        frames.append(slots)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("visit_interval")


def weekly_peak_utilisation_series(slots: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate weekly peak PP utilisation by period.

    Parameters
    ----------
    slots : pandas.DataFrame
        Slot-level outlet series from :func:`build_outlet_slot_series`.

    Returns
    -------
    pandas.DataFrame
        One row per week and period with peak slot utilisation. Week labels
        use the Monday of each ISO week.
    """
    if slots.empty:
        return pd.DataFrame(columns=["week_start", "period", "weekly_peak_pp_utilisation"])
    work = slots.copy()
    work["week_start"] = (
        work["visit_interval"]
        - pd.to_timedelta(work["visit_interval"].dt.weekday, unit="D")
    ).dt.normalize()
    return (
        work.groupby(["period", "week_start"], as_index=False)["pp_utilisation_rate"]
        .max()
        .rename(columns={"pp_utilisation_rate": "weekly_peak_pp_utilisation"})
        .sort_values(["week_start", "period"])
    )


def daily_utilisation_series(slots: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily average and peak PP utilisation by period.

    Parameters
    ----------
    slots : pandas.DataFrame
        Slot-level outlet series.

    Returns
    -------
    pandas.DataFrame
        Daily utilisation and occupancy aggregates by period.
    """
    if slots.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "period",
                "daily_average_pp_utilisation",
                "daily_peak_pp_utilisation",
                "daily_average_pp_occupancy",
            ]
        )
    work = slots.copy()
    work["date"] = work["visit_interval"].dt.normalize()
    grouped = work.groupby(["period", "date"], as_index=False).agg(
        daily_average_pp_utilisation=("pp_utilisation_rate", "mean"),
        daily_peak_pp_utilisation=("pp_utilisation_rate", "max"),
        daily_average_pp_occupancy=("estimated_occupancy", "mean"),
    )
    return grouped.sort_values(["date", "period"])


def daily_visit_volume_series(slots: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate daily total visit volume by period.

    Parameters
    ----------
    slots : pandas.DataFrame
        Slot-level outlet series.

    Returns
    -------
    pandas.DataFrame
        Daily visit totals by period.
    """
    if slots.empty:
        return pd.DataFrame(columns=["date", "period", "daily_visit_volume"])
    work = slots.copy()
    work["date"] = work["visit_interval"].dt.normalize()
    return (
        work.groupby(["period", "date"], as_index=False)["total_visits"]
        .sum()
        .rename(columns={"total_visits": "daily_visit_volume"})
        .sort_values(["date", "period"])
    )


def outlet_metric_timeseries(
    metric_key: str,
    slots: pd.DataFrame,
) -> pd.DataFrame:
    """
    Return a long time-series frame for the selected outlet metric.

    Parameters
    ----------
    metric_key : str
        Key from :data:`OUTLET_SERIES_METRICS`.
    slots : pandas.DataFrame
        Slot-level outlet series.

    Returns
    -------
    pandas.DataFrame
        Time series with ``timestamp``, ``period`` and metric value columns.

    Raises
    ------
    KeyError
        If ``metric_key`` is not recognised.
    """
    weekly = weekly_peak_utilisation_series(slots)
    daily_util = daily_utilisation_series(slots)
    if metric_key == "weekly_peak_pp_utilisation":
        frame = weekly.rename(columns={"week_start": "timestamp"})
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        return frame[["timestamp", "period", "weekly_peak_pp_utilisation"]]
    if metric_key == "daily_average_pp_utilisation":
        frame = daily_util.rename(columns={"date": "timestamp"})
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        return frame[["timestamp", "period", "daily_average_pp_utilisation"]]
    if metric_key == "daily_peak_pp_utilisation":
        frame = daily_util.rename(columns={"date": "timestamp"})
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        return frame[["timestamp", "period", "daily_peak_pp_utilisation"]]
    if metric_key == "daily_average_pp_occupancy":
        frame = daily_util.rename(columns={"date": "timestamp"})
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        return frame[["timestamp", "period", "daily_average_pp_occupancy"]]
    raise KeyError(f"Unknown outlet series metric: {metric_key}")


def outlet_series_metric_label(metric_key: str) -> str:
    """
    Return the display label for an outlet time-series metric.

    Parameters
    ----------
    metric_key : str
        Key from :data:`OUTLET_SERIES_METRICS`.

    Returns
    -------
    str
        Human-readable metric label.
    """
    return OUTLET_SERIES_METRICS.get(metric_key, {}).get("label", metric_key)


def intervention_timestamp(lounge: LoungeIntervention) -> datetime:
    """
    Return the configured intervention timestamp for a lounge.

    Parameters
    ----------
    lounge : LoungeIntervention
        Lounge configuration.

    Returns
    -------
    datetime
        Intervention date separating pre and post windows.
    """
    return lounge.intervention_date
