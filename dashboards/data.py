"""Load intervention analysis results for the dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from capacity_impact.analysis import (
    CHANGE_METRICS,
    compare_periods,
    ensure_change_metric_columns,
    run_analysis,
)
from capacity_impact.config import AnalysisConfig, load_config
from capacity_impact.data import extract_inputs


def project_root() -> Path:
    """
    Return the project root directory.

    Returns
    -------
    pathlib.Path
        Absolute path to the repository root.
    """
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    """
    Return the default analysis YAML path.

    Returns
    -------
    pathlib.Path
        Path to ``config/analysis.yaml`` under the project root.
    """
    return project_root() / "config" / "analysis.yaml"


def load_analysis_config(config_path: Path | None = None) -> AnalysisConfig:
    """
    Load the analysis configuration for dashboard use.

    Parameters
    ----------
    config_path : pathlib.Path or None, optional
        Config file path. Defaults to :func:`default_config_path`.

    Returns
    -------
    AnalysisConfig
        Validated analysis configuration.
    """
    return load_config(config_path or default_config_path())


def load_saved_results(config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Read CSV outputs written by the CLI.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration with output directory.

    Returns
    -------
    period_metrics : pandas.DataFrame
        Period-level metrics CSV.
    impact : pandas.DataFrame
        Paired intervention impact CSV.

    Raises
    ------
    FileNotFoundError
        If expected output CSVs are missing.
    """
    period_path = config.output_directory / "period_metrics.csv"
    impact_path = config.output_directory / "intervention_impact.csv"
    if not period_path.exists() or not impact_path.exists():
        raise FileNotFoundError(
            "Saved results not found. Run `python -m capacity_impact.cli` first "
            f"or refresh from Snowflake. Expected: {period_path} and {impact_path}"
        )
    period_metrics = pd.read_csv(period_path, parse_dates=["period_start", "period_end"])
    impact = pd.read_csv(
        impact_path,
        parse_dates=["pre_period_start", "pre_period_end", "post_period_start", "post_period_end"],
    )
    return enrich_saved_results(period_metrics, impact, config)


def _missing_change_metrics(impact: pd.DataFrame) -> tuple[str, ...]:
    return tuple(
        metric for metric in CHANGE_METRICS if f"pre_{metric}" not in impact.columns
    )


def _merge_impact_columns(
    impact: pd.DataFrame,
    refreshed: pd.DataFrame,
    metrics: tuple[str, ...],
) -> pd.DataFrame:
    columns = ["outlet_code"]
    for metric in metrics:
        columns.extend(
            [
                f"pre_{metric}",
                f"post_{metric}",
                f"{metric}_delta",
                f"{metric}_pct_change",
            ]
        )
    columns = [column for column in columns if column in refreshed.columns]
    if len(columns) <= 1:
        return impact

    work = impact.drop(
        columns=[column for column in columns if column != "outlet_code" and column in impact.columns],
        errors="ignore",
    )
    return work.merge(refreshed[columns], on="outlet_code", how="left")


def enrich_saved_results(
    period_metrics: pd.DataFrame,
    impact: pd.DataFrame,
    config: AnalysisConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Backfill newer change metrics into saved CSV outputs when possible.

    When cached visit/flight extracts exist, the analysis is recomputed. When
    only period metrics contain the new fields, paired impact columns are
    merged from a fresh :func:`compare_periods` pass. Otherwise missing columns
    are added as ``NaN`` so dashboards fail gracefully.
    """
    missing = _missing_change_metrics(impact)
    if not missing:
        return period_metrics, ensure_change_metric_columns(impact)

    period_missing = tuple(metric for metric in missing if metric not in period_metrics.columns)
    if not period_missing:
        refreshed = compare_periods(period_metrics)
        impact = _merge_impact_columns(impact, refreshed, missing)
        return period_metrics, ensure_change_metric_columns(impact)

    visits_path = config.output_directory / "visits_extract.csv"
    flights_path = config.output_directory / "flights_extract.csv"
    if visits_path.exists() and flights_path.exists():
        visits = pd.read_csv(visits_path, parse_dates=["visit_interval"])
        flights = pd.read_csv(flights_path, parse_dates=["flight_interval"])
        if not visits.empty and not flights.empty:
            return run_analysis(visits, flights, config)

    return period_metrics, ensure_change_metric_columns(impact)


def load_raw_inputs(config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load visit and flight extracts from cached CSVs or Snowflake.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration.

    Returns
    -------
    visits : pandas.DataFrame
        Visit extract.
    flights : pandas.DataFrame
        Flight extract.
    """
    visits_path = config.output_directory / "visits_extract.csv"
    flights_path = config.output_directory / "flights_extract.csv"
    if visits_path.exists() and flights_path.exists():
        visits = pd.read_csv(visits_path, parse_dates=["visit_interval"])
        flights = pd.read_csv(flights_path, parse_dates=["flight_interval"])
        return visits, flights
    return extract_inputs(config)


def run_live_analysis(config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Query Snowflake and run the intervention analysis.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration.

    Returns
    -------
    period_metrics : pandas.DataFrame
        Period-level metrics.
    impact : pandas.DataFrame
        Paired intervention impact table.
    """
    visits, flights = extract_inputs(config)
    return run_analysis(visits, flights, config)
