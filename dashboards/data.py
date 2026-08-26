"""Load intervention analysis results for the dashboard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from capacity_impact.analysis import run_analysis
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
    return period_metrics, impact


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
