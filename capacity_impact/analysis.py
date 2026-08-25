"""Orchestrate paired pre/post lounge impact analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from capacity_impact.config import AnalysisConfig, LoungeIntervention
from capacity_impact.exc import DataMissing, DataInvalid, DataInconsistent
from capacity_impact.metrics import (
    assign_quadrant,
    compute_airport_traffic_peak,
    compute_traffic_threshold,
    compute_visit_metrics,
    period_days,
)

CHANGE_METRICS = (
    "pp_visit_volume",
    "pp_visits_per_day",
    "avg_monthly_visits",
    "estimated_pp_market_share",
    "peak_pp_utilisation_rate",
    "peak_pp_estimated_occupancy",
    "mean_pp_utilisation_rate",
    "mean_pp_estimated_occupancy",
    "airport_traffic_peak",
)


def _airport_for_outlet(visits: pd.DataFrame, outlet_code: str) -> str:
    required = {"outlet_code", "airport_code"}
    missing = required.difference(visits.columns)
    if missing:
        raise DataMissing(f"visits is missing columns: {', '.join(sorted(missing))}")
    codes = visits["outlet_code"].astype(str).str.strip().str.upper()
    airports = (
        visits.loc[codes.eq(outlet_code), "airport_code"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
    )
    if airports.empty:
        raise DataMissing(f"No airport mapping found for {outlet_code}")
    unique = airports[airports.ne("")].unique()
    if len(unique) != 1:
        raise DataInconsistent(f"{outlet_code} maps to {len(unique)} airports")
    return str(unique[0])


def _period_row(
    visits: pd.DataFrame,
    flights: pd.DataFrame,
    lounge: LoungeIntervention,
    config: AnalysisConfig,
    period_name: str,
) -> dict[str, object]:
    period = lounge.pre if period_name == "pre" else lounge.post
    seat_override = (
        lounge.pre_number_of_seats
        if period_name == "pre"
        else lounge.post_number_of_seats
    )
    airport_code = _airport_for_outlet(visits, lounge.outlet_code)
    metrics = compute_visit_metrics(
        visits,
        period,
        config.metrics,
        outlet_code=lounge.outlet_code,
        number_of_seats=seat_override,
    )
    metrics["pp_visits_per_day"] = metrics["pp_visit_volume"] / period_days(period)
    metrics["airport_traffic_peak"] = compute_airport_traffic_peak(
        flights,
        period,
        config.metrics,
        airport_code=airport_code,
    )
    return {
        "outlet_code": lounge.outlet_code,
        "airport_code": airport_code,
        "period": period_name,
        "period_start": period.start,
        "period_end": period.end,
        **metrics,
    }


def compute_period_metrics(
    visits: pd.DataFrame,
    flights: pd.DataFrame,
    config: AnalysisConfig,
) -> pd.DataFrame:
    """Compute one row for each configured lounge and comparison period."""
    rows = [
        _period_row(visits, flights, lounge, config, period_name)
        for lounge in config.lounges
        for period_name in ("pre", "post")
    ]
    result = pd.DataFrame(rows)
    pre = result[result["period"].eq("pre")]
    threshold = compute_traffic_threshold(pre["airport_traffic_peak"], config.metrics)
    result["traffic_threshold"] = threshold
    assigned = result.apply(
        lambda row: assign_quadrant(
            float(row["peak_pp_utilisation_rate"]),
            float(row["airport_traffic_peak"]),
            config.metrics.high_utilisation_threshold,
            threshold,
        ),
        axis=1,
        result_type="expand",
    )
    result[["quadrant_category", "quadrant_label"]] = assigned
    return result


def compare_periods(period_metrics: pd.DataFrame) -> pd.DataFrame:
    """Create paired metric deltas and quadrant transitions per lounge."""
    pre = (
        period_metrics[period_metrics["period"].eq("pre")]
        .drop(columns="period")
        .set_index("outlet_code")
        .add_prefix("pre_")
    )
    post = (
        period_metrics[period_metrics["period"].eq("post")]
        .drop(columns="period")
        .set_index("outlet_code")
        .add_prefix("post_")
    )
    result = pre.join(post, how="outer", validate="one_to_one").reset_index()
    for metric in CHANGE_METRICS:
        before = pd.to_numeric(result[f"pre_{metric}"], errors="coerce")
        after = pd.to_numeric(result[f"post_{metric}"], errors="coerce")
        result[f"{metric}_delta"] = after - before
        result[f"{metric}_pct_change"] = np.where(
            before.ne(0) & before.notna(),
            (after - before) / before,
            np.nan,
        )

    result["quadrant_changed"] = (
        result["pre_quadrant_category"].notna()
        & result["post_quadrant_category"].notna()
        & result["pre_quadrant_category"].ne(result["post_quadrant_category"])
    )
    result["quadrant_transition"] = (
        result["pre_quadrant_label"].fillna("NaN")  # TODO: impute for potential new outlets added (to check/revisit)
        + " -> "
        + result["post_quadrant_label"].fillna("NaN")  # TODO: impute for potential new outlets added (to check/revisit)
    )
    return result


def run_analysis(
    visits: pd.DataFrame,
    flights: pd.DataFrame,
    config: AnalysisConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return period-level metrics and the paired intervention impact table."""
    period_metrics = compute_period_metrics(visits, flights, config)
    return period_metrics, compare_periods(period_metrics)
