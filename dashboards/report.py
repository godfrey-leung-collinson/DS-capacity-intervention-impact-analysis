"""Shared helpers for building dashboard tables and report figures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import yaml

from capacity_impact.config import AnalysisConfig, LoungeIntervention
from dashboards.data import load_analysis_config, load_raw_inputs, load_saved_results
from dashboards.metrics import (
    TRACKABLE_METRICS,
    format_delta,
    format_metric_value,
    format_pct_change,
    metric_label,
)
from dashboards.outlet_series import (
    OUTLET_SERIES_METRICS,
    build_outlet_slot_series,
    daily_visit_volume_series,
    intervention_timestamp,
    lounge_for_outlet,
    outlet_metric_timeseries,
    outlet_series_metric_label,
)
from dashboards.plots import (
    daily_visit_volume_distribution_chart,
    daily_visit_volume_timeseries_chart,
    delta_bar_chart,
    metric_heatmap,
    outlet_metric_timeseries_chart,
    pre_post_grouped_bar,
    quadrant_transition_chart,
)
from dashboards.summary import ExecutiveSummary, build_executive_summary

DASHBOARD_CONFIG_PATH = Path(__file__).parent / "config" / "dashboard_config.yaml"


def load_dashboard_config(path: Path | None = None) -> dict:
    """
    Load dashboard YAML settings.

    Parameters
    ----------
    path : pathlib.Path or None, optional
        Dashboard config path. Defaults to ``dashboards/config/dashboard_config.yaml``.

    Returns
    -------
    dict
        Parsed dashboard configuration, or an empty dict when missing.
    """
    config_path = path or DASHBOARD_CONFIG_PATH
    if config_path.exists():
        return yaml.safe_load(config_path.read_text()) or {}
    return {}


def styled_impact_table(impact: pd.DataFrame) -> pd.DataFrame:
    """
    Format the intervention impact table for display or HTML export.

    Parameters
    ----------
    impact : pandas.DataFrame
        Raw paired intervention impact table.

    Returns
    -------
    pandas.DataFrame
        Display-ready table with formatted values and readable column names.
    """
    display = impact.copy()
    for metric in TRACKABLE_METRICS:
        display[f"pre_{metric}"] = display[f"pre_{metric}"].map(
            lambda value, m=metric: format_metric_value(value, m)
        )
        display[f"post_{metric}"] = display[f"post_{metric}"].map(
            lambda value, m=metric: format_metric_value(value, m)
        )
        display[f"{metric}_delta"] = display[f"{metric}_delta"].map(
            lambda value, m=metric: format_delta(value, m)
        )
        display[f"{metric}_pct_change"] = display[f"{metric}_pct_change"].map(format_pct_change)
    rename = {
        "outlet_code": "Outlet",
        "pre_quadrant_label": "Pre quadrant",
        "post_quadrant_label": "Post quadrant",
        "quadrant_transition": "Quadrant transition",
        "quadrant_changed": "Quadrant changed",
    }
    for metric in TRACKABLE_METRICS:
        rename[f"pre_{metric}"] = f"Pre {metric_label(metric)}"
        rename[f"post_{metric}"] = f"Post {metric_label(metric)}"
        rename[f"{metric}_delta"] = f"Δ {metric_label(metric)}"
        rename[f"{metric}_pct_change"] = f"% Δ {metric_label(metric)}"
    keep = [column for column in rename if column in display.columns]
    return display[keep].rename(columns=rename)


@dataclass(frozen=True)
class ReportContext:
    """
    Loaded inputs shared by the Streamlit app and HTML export.

    Attributes
    ----------
    dashboard_config : dict
        Dashboard YAML settings.
    analysis_config : AnalysisConfig
        Analysis configuration.
    period_metrics : pandas.DataFrame
        Period-level metrics table.
    impact : pandas.DataFrame
        Paired intervention impact table.
    visits : pandas.DataFrame
        Visit extract, possibly empty when unavailable.
    summary : ExecutiveSummary
        Portfolio executive summary.
    selected_metrics : tuple of str
        Metrics to include in portfolio charts.
    """

    dashboard_config: dict
    analysis_config: AnalysisConfig
    period_metrics: pd.DataFrame
    impact: pd.DataFrame
    visits: pd.DataFrame
    summary: ExecutiveSummary
    selected_metrics: tuple[str, ...]


def load_report_context(
    *,
    analysis_config_path: Path,
    dashboard_config_path: Path | None = None,
    refresh_from_snowflake: bool = False,
    outlet_filter: tuple[str, ...] | None = None,
) -> ReportContext:
    """
    Load all data required to render the dashboard or HTML report.

    Parameters
    ----------
    analysis_config_path : pathlib.Path
        Path to the analysis YAML config.
    dashboard_config_path : pathlib.Path or None, optional
        Path to dashboard YAML settings.
    refresh_from_snowflake : bool, default False
        When ``True``, re-query Snowflake and recompute analysis outputs.
    outlet_filter : tuple of str or None, optional
        Optional outlet codes to restrict the loaded tables.

    Returns
    -------
    ReportContext
        Loaded dashboard/report context.
    """
    dashboard_config = load_dashboard_config(dashboard_config_path)
    analysis_config = load_analysis_config(analysis_config_path)
    if refresh_from_snowflake:
        from capacity_impact.analysis import run_analysis
        from capacity_impact.data import extract_inputs

        visits, flights = extract_inputs(analysis_config)
        period_metrics, impact = run_analysis(visits, flights, analysis_config)
    else:
        period_metrics, impact = load_saved_results(analysis_config)
        try:
            visits, _flights = load_raw_inputs(analysis_config)
        except Exception:
            visits = pd.DataFrame()

    if outlet_filter:
        codes = {code.strip().upper() for code in outlet_filter}
        impact = impact[impact["outlet_code"].astype(str).str.upper().isin(codes)].copy()
        period_metrics = period_metrics[
            period_metrics["outlet_code"].astype(str).str.upper().isin(codes)
        ].copy()

    default_metrics = dashboard_config.get("default_metrics", list(TRACKABLE_METRICS))
    selected_metrics = tuple(
        metric for metric in default_metrics if metric in TRACKABLE_METRICS
    ) or TRACKABLE_METRICS

    return ReportContext(
        dashboard_config=dashboard_config,
        analysis_config=analysis_config,
        period_metrics=period_metrics,
        impact=impact,
        visits=visits,
        summary=build_executive_summary(impact),
        selected_metrics=selected_metrics,
    )


def quadrant_table(impact: pd.DataFrame) -> pd.DataFrame:
    """
    Build a display-friendly quadrant summary table.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.

    Returns
    -------
    pandas.DataFrame
        Quadrant-focused subset with readable column names.
    """
    columns = [
        "outlet_code",
        "pre_quadrant_label",
        "post_quadrant_label",
        "quadrant_transition",
        "quadrant_changed",
        "pre_peak_pp_utilisation_rate",
        "post_peak_pp_utilisation_rate",
        "pre_airport_traffic_peak",
        "post_airport_traffic_peak",
    ]
    present = [column for column in columns if column in impact.columns]
    view = impact[present].copy()
    rename = {
        "outlet_code": "Outlet",
        "pre_quadrant_label": "Pre quadrant",
        "post_quadrant_label": "Post quadrant",
        "quadrant_transition": "Transition",
        "quadrant_changed": "Changed",
        "pre_peak_pp_utilisation_rate": "Pre peak util",
        "post_peak_pp_utilisation_rate": "Post peak util",
        "pre_airport_traffic_peak": "Pre traffic peak",
        "post_airport_traffic_peak": "Post traffic peak",
    }
    return view.rename(columns=rename)


def build_portfolio_figures(context: ReportContext) -> dict[str, go.Figure | list[tuple[str, go.Figure]]]:
    """
    Build portfolio-level Plotly figures for overview and metric tabs.

    Parameters
    ----------
    context : ReportContext
        Loaded dashboard/report context.

    Returns
    -------
    dict
        Named portfolio figures including heatmap, quadrant scatter, bars and
        per-metric comparison sections.
    """
    impact = context.impact
    metrics = context.selected_metrics
    quadrant_kwargs = {
        "high_utilisation_threshold": context.analysis_config.metrics.high_utilisation_threshold,
        "high_traffic_threshold": context.analysis_config.metrics.high_traffic_threshold,
    }
    primary_metric = metrics[0]
    metric_figures = [
        (
            metric_label(metric),
            pre_post_grouped_bar(impact, metric),
            delta_bar_chart(impact, metric),
        )
        for metric in metrics
    ]
    return {
        "overview_heatmap": metric_heatmap(impact, metrics),
        "overview_quadrant": quadrant_transition_chart(impact, **quadrant_kwargs),
        "overview_primary_bar": pre_post_grouped_bar(impact, primary_metric),
        "metric_sections": metric_figures,
        "quadrants_scatter": quadrant_transition_chart(impact, **quadrant_kwargs),
    }


def build_outlet_figures(
    context: ReportContext,
    lounge: LoungeIntervention,
) -> dict[str, go.Figure | list[go.Figure]] | None:
    """
    Build outlet-level Plotly figures for one lounge.

    Parameters
    ----------
    context : ReportContext
        Loaded dashboard/report context.
    lounge : LoungeIntervention
        Lounge configuration.

    Returns
    -------
    dict or None
        Outlet figures and daily visit table when visit data are available;
        otherwise ``None``.
    """
    if context.visits.empty:
        # TODO: add logging warning to indicate the lounge have no visits (e.g. cases of closed or newly opened lounges)
        return None
    slots = build_outlet_slot_series(
        context.visits,
        lounge,
        context.analysis_config.metrics,
    )
    if slots.empty:
        # TODO: add logging warning to indicate the lounge have no pre/post period (e.g. cases of closed or newly opened lounges)
        return None
    daily_visits = daily_visit_volume_series(slots)
    intervention = intervention_timestamp(lounge)
    util_threshold = context.analysis_config.metrics.high_utilisation_threshold
    series_figures = []
    for metric_key in OUTLET_SERIES_METRICS:
        series = outlet_metric_timeseries(metric_key, slots)
        series_figures.append(
            (
                outlet_series_metric_label(metric_key),
                outlet_metric_timeseries_chart(
                    series,
                    metric_key=metric_key,
                    outlet_code=lounge.outlet_code,
                    intervention_date=intervention,
                    utilisation_threshold=util_threshold,
                ),
            )
        )
    return {
        "series": series_figures,
        "daily_visits_ts": daily_visit_volume_timeseries_chart(
            daily_visits,
            outlet_code=lounge.outlet_code,
            intervention_date=intervention,
        ),
        "daily_visits_dist": daily_visit_volume_distribution_chart(
            daily_visits,
            outlet_code=lounge.outlet_code,
        ),
        "daily_visits_table": daily_visits,
    }
