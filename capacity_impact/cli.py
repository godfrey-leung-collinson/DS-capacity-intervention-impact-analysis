"""Command-line entry point for the intervention analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from capacity_impact.analysis import run_analysis
from capacity_impact.config import load_config
from capacity_impact.data import extract_inputs


def build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Parser configured with config and optional local CSV paths.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/analysis.yaml")
    parser.add_argument("--visits-csv", help="Use a local extract instead of Snowflake")
    parser.add_argument("--flights-csv", help="Use a local extract instead of Snowflake")
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Run the intervention analysis and write CSV outputs.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments. Defaults to ``sys.argv`` when omitted.

    Returns
    -------
    int
        Process exit code (0 on success).

    Raises
    ------
    ValueError
        If only one of ``--visits-csv`` or ``--flights-csv`` is supplied.
    """
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config = load_config(config_path)

    if bool(args.visits_csv) != bool(args.flights_csv):
        raise ValueError("--visits-csv and --flights-csv must be supplied together")
    if args.visits_csv:
        visits = pd.read_csv(args.visits_csv, parse_dates=["visit_interval"])
        flights = pd.read_csv(args.flights_csv, parse_dates=["flight_interval"])
    else:
        visits, flights = extract_inputs(config)

    period_metrics, impact = run_analysis(visits, flights, config)
    config.output_directory.mkdir(parents=True, exist_ok=True)
    period_metrics.to_csv(config.output_directory / "period_metrics.csv", index=False)
    impact.to_csv(config.output_directory / "intervention_impact.csv", index=False)
    visits.to_csv(config.output_directory / "visits_extract.csv", index=False)
    flights.to_csv(config.output_directory / "flights_extract.csv", index=False)
    print(f"Wrote results to {config.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
