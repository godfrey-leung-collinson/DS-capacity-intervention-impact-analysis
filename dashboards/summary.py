"""Executive summary helpers for the intervention dashboard."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from capacity_impact.analysis import CHANGE_METRICS
from dashboards.metrics import format_pct_change, metric_label


@dataclass(frozen=True)
class ExecutiveSummary:
    """
    Portfolio-level pre/post intervention headline metrics.

    Attributes
    ----------
    outlet_count : int
        Number of lounges in the impact table.
    outlets_with_visit_increase : int
        Lounges whose PP visit volume increased post intervention.
    outlets_with_quadrant_change : int
        Lounges that changed capacity quadrant.
    pre_capacity_risk_count : int
        Lounges in the Capacity risk quadrant pre intervention.
    post_capacity_risk_count : int
        Lounges in the Capacity risk quadrant post intervention.
    median_visit_volume_pct_change : float or None
        Median percentage change in PP visit volume.
    median_avg_monthly_visits_pct_change : float or None
        Median percentage change in average monthly visits.
    median_estimated_pp_market_share_pct_change : float or None
        Median percentage change in estimated PP market share proxy.
    headline : str
        One-line portfolio summary.
    bullets : tuple of str
        Supporting bullet points for the executive summary panel.
    """

    outlet_count: int
    outlets_with_visit_increase: int
    outlets_with_quadrant_change: int
    pre_capacity_risk_count: int
    post_capacity_risk_count: int
    median_visit_volume_pct_change: float | None
    median_avg_monthly_visits_pct_change: float | None
    median_estimated_pp_market_share_pct_change: float | None
    headline: str
    bullets: tuple[str, ...]


def _median_pct_change(impact: pd.DataFrame, metric: str) -> float | None:
    """
    Compute the median percentage change for one metric across outlets.

    Parameters
    ----------
    impact : pandas.DataFrame
        Intervention impact table.
    metric : str
        Base metric name without ``_pct_change`` suffix.

    Returns
    -------
    float or None
        Median percentage change, or ``None`` when no valid values exist.
    """
    column = f"{metric}_pct_change"
    if column not in impact.columns:
        return None
    values = pd.to_numeric(impact[column], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.median())


def build_executive_summary(impact: pd.DataFrame) -> ExecutiveSummary:
    """
    Summarise portfolio-level pre/post intervention movement.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.

    Returns
    -------
    ExecutiveSummary
        Headline metrics and narrative bullets for the dashboard.
    """
    if impact.empty:
        return ExecutiveSummary(
            outlet_count=0,
            outlets_with_visit_increase=0,
            outlets_with_quadrant_change=0,
            pre_capacity_risk_count=0,
            post_capacity_risk_count=0,
            median_visit_volume_pct_change=None,
            median_avg_monthly_visits_pct_change=None,
            median_estimated_pp_market_share_pct_change=None,
            headline="No intervention results available.",
            bullets=("Run the analysis or load saved CSV outputs.",),
        )

    visit_delta = pd.to_numeric(impact.get("pp_visit_volume_delta"), errors="coerce")
    quadrant_changed = impact.get("quadrant_changed", pd.Series(dtype=bool)).fillna(False)
    pre_risk = (impact.get("pre_quadrant_label") == "Capacity risk").sum()
    post_risk = (impact.get("post_quadrant_label") == "Capacity risk").sum()
    median_visit_pct = _median_pct_change(impact, "pp_visit_volume")
    median_monthly_pct = _median_pct_change(impact, "avg_monthly_visits")
    median_share_pct = _median_pct_change(impact, "estimated_pp_market_share")

    increased = int((visit_delta > 0).sum())
    changed_quadrant = int(quadrant_changed.sum())
    outlet_count = len(impact)

    if median_visit_pct is not None and median_visit_pct > 0:
        headline = (
            f"Portfolio PP demand rose in {increased}/{outlet_count} lounges "
            f"(median visit volume {format_pct_change(median_visit_pct)})."
        )
    elif median_visit_pct is not None and median_visit_pct < 0:
        headline = (
            f"Portfolio PP demand fell in {outlet_count - increased}/{outlet_count} lounges "
            f"(median visit volume {format_pct_change(median_visit_pct)})."
        )
    else:
        headline = f"Pre/post comparison across {outlet_count} intervention lounges."

    bullets = [
        f"{changed_quadrant} lounge(s) changed capacity quadrant after intervention.",
        (
            f"Capacity risk quadrant: {pre_risk} pre → {post_risk} post "
            f"(peak PP utilisation vs airport traffic thresholds)."
        ),
    ]
    if median_monthly_pct is not None:
        bullets.append(
            f"Median avg monthly visits change: {format_pct_change(median_monthly_pct)}."
        )
    if median_share_pct is not None:
        bullets.append(
            f"Median est. PP market share change: {format_pct_change(median_share_pct)}."
        )

    return ExecutiveSummary(
        outlet_count=outlet_count,
        outlets_with_visit_increase=increased,
        outlets_with_quadrant_change=changed_quadrant,
        pre_capacity_risk_count=int(pre_risk),
        post_capacity_risk_count=int(post_risk),
        median_visit_volume_pct_change=median_visit_pct,
        median_avg_monthly_visits_pct_change=median_monthly_pct,
        median_estimated_pp_market_share_pct_change=median_share_pct,
        headline=headline,
        bullets=tuple(bullets),
    )


def metric_change_table(impact: pd.DataFrame, metrics: tuple[str, ...] = CHANGE_METRICS) -> pd.DataFrame:
    """
    Return a display-friendly long table of pre/post/delta values.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    metrics : tuple of str, optional
        Metric keys to include. Defaults to :data:`capacity_impact.analysis.CHANGE_METRICS`.

    Returns
    -------
    pandas.DataFrame
        Long-form table with one row per outlet and metric.
    """
    rows: list[dict[str, object]] = []
    for _, record in impact.iterrows():
        for metric in metrics:
            rows.append(
                {
                    "outlet_code": record["outlet_code"],
                    "metric_key": metric,
                    "metric": metric_label(metric),
                    "pre": record.get(f"pre_{metric}"),
                    "post": record.get(f"post_{metric}"),
                    "delta": record.get(f"{metric}_delta"),
                    "pct_change": record.get(f"{metric}_pct_change"),
                }
            )
    return pd.DataFrame(rows)
