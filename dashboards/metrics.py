"""Metric labels and formatting for the intervention dashboard."""

from __future__ import annotations

import pandas as pd

from capacity_impact.analysis import CHANGE_METRICS

METRIC_SPECS: dict[str, dict[str, str]] = {
    "pp_visit_volume": {
        "label": "PP visit volume",
        "format": "count",
        "help": "Total PP/LK arrivals in the analysis window.",
    },
    "pp_visits_per_day": {
        "label": "PP visits per day",
        "format": "count",
        "help": "Visit volume (PP & LK) normalised by period length.",
    },
    "avg_monthly_visits": {
        "label": "Avg monthly visits",
        "format": "count",
        "help": "Mean of calendar-month (PP & LK) visit totals.",
    },
    "estimated_pp_market_share": {
        "label": "Est. PP market share",
        "format": "percent",
        "help": "Mean of weekly peak PP utilisation (dashboard proxy).",
    },
    "peak_pp_utilisation_rate": {
        "label": "Peak PP utilisation",
        "format": "percent",
        "help": "Maximum estimated occupancy divided by effective seat capacity.",
    },
    "peak_pp_estimated_occupancy": {
        "label": "Peak PP est. occupancy",
        "format": "count",
        "help": "Highest rolling estimated concurrent PP guests.",
    },
    "average_pp_utilisation_rate": {
        "label": "Average PP utilisation",
        "format": "percent",
        "help": "Mean slot-level PP utilisation across the period.",
    },
    "average_pp_estimated_occupancy": {
        "label": "Average PP est. occupancy",
        "format": "count",
        "help": "Mean rolling estimated concurrent PP guests.",
    },
    "airport_traffic_peak": {
        "label": "Airport traffic peak",
        "format": "count",
        "help": "Peak forward departure count in the configured window.",
    },
    "visit_to_flight_ratio": {
        "label": "Visit-to-flight ratio",
        "format": "ratio",
        "help": (
            "Total PP visits divided by the sum of forward departure counts "
            "in the configured window across the period."
        ),
    },
}

TRACKABLE_METRICS = tuple(metric for metric in CHANGE_METRICS if metric in METRIC_SPECS)


def available_trackable_metrics(impact: pd.DataFrame) -> tuple[str, ...]:
    """Return dashboard metrics that have both pre and post values available."""
    return tuple(
        metric
        for metric in TRACKABLE_METRICS
        if f"pre_{metric}" in impact.columns
        and f"post_{metric}" in impact.columns
        and impact[[f"pre_{metric}", f"post_{metric}"]].notna().any().any()
    )


def metric_label(metric: str) -> str:
    """
    Return the display label for a metric key.

    Parameters
    ----------
    metric : str
        Internal metric identifier.

    Returns
    -------
    str
        Human-readable metric label.
    """
    return METRIC_SPECS.get(metric, {}).get("label", metric.replace("_", " ").title())


def format_metric_value(value: float | None, metric: str) -> str:
    """
    Format a metric value for display in tables and KPIs.

    Parameters
    ----------
    value : float or None
        Raw metric value.
    metric : str
        Internal metric identifier controlling number formatting.

    Returns
    -------
    str
        Formatted display string, or an em dash for missing values.
    """
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    spec = METRIC_SPECS.get(metric, {})
    fmt = spec.get("format", "number")
    if fmt == "percent":
        return f"{float(value):.1%}"
    if fmt == "count":
        return f"{float(value):,.0f}"
    if fmt == "ratio":
        return f"{float(value):,.3f}"
    return f"{float(value):,.2f}"


def format_delta(value: float | None, metric: str) -> str:
    """
    Format an absolute metric delta for display.

    Parameters
    ----------
    value : float or None
        Absolute change value.
    metric : str
        Internal metric identifier controlling number formatting.

    Returns
    -------
    str
        Signed formatted delta, or an em dash for missing values.
    """
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    spec = METRIC_SPECS.get(metric, {})
    fmt = spec.get("format", "number")
    sign = "+" if float(value) > 0 else ""
    if fmt == "percent":
        return f"{sign}{float(value):.1%}"
    if fmt == "count":
        return f"{sign}{float(value):,.0f}"
    if fmt == "ratio":
        return f"{sign}{float(value):,.3f}"
    return f"{sign}{float(value):,.2f}"


def format_pct_change(value: float | None) -> str:
    """
    Format a percentage change for display.

    Parameters
    ----------
    value : float or None
        Fractional percentage change.

    Returns
    -------
    str
        Signed percentage string, or an em dash for missing values.
    """
    if value is None or (isinstance(value, float) and value != value):
        return "—"
    sign = "+" if float(value) > 0 else ""
    return f"{sign}{float(value):.1%}"
