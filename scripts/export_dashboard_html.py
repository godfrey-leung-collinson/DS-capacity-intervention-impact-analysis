#!/usr/bin/env python3
"""Export the capacity intervention Streamlit dashboard as standalone HTML.

Includes the same portfolio metrics as the Streamlit app (including
visit-to-flight ratio), peak/average quadrant toggles, and outlet-level
pre/post KPI cards.

Usage (from project root):
    python scripts/export_dashboard_html.py
    python scripts/export_dashboard_html.py --output reports/intervention_report.html --open
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboards.html_report import build_html_report  # noqa: E402
from dashboards.report import load_dashboard_config  # noqa: E402


def _parse_outlets(value: str) -> tuple[str, ...]:
    """
    Parse a comma-separated outlet list from CLI input.

    Parameters
    ----------
    value : str
        Comma-separated outlet codes.

    Returns
    -------
    tuple of str
        Normalised uppercase outlet codes.
    """
    return tuple(item.strip().upper() for item in value.split(",") if item.strip())


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments for the HTML export script.

    Returns
    -------
    argparse.Namespace
        Parsed CLI arguments.
    """
    dashboard_config = load_dashboard_config()
    default_analysis = dashboard_config.get("paths", {}).get("analysis_config", "config/analysis.yaml")
    parser = argparse.ArgumentParser(
        description="Export the capacity intervention dashboard to interactive HTML."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / default_analysis,
        help="Analysis YAML config path.",
    )
    parser.add_argument(
        "--dashboard-config",
        type=Path,
        default=PROJECT_ROOT / "dashboards" / "config" / "dashboard_config.yaml",
        help="Dashboard YAML config path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "capacity_intervention_dashboard.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--plotly-js",
        choices=("inline", "cdn"),
        default="inline",
        help="Inline embeds Plotly.js for offline use; CDN produces a smaller file.",
    )
    parser.add_argument(
        "--refresh-from-snowflake",
        action="store_true",
        help="Re-query Snowflake instead of using saved CSV outputs.",
    )
    parser.add_argument(
        "--outlets",
        type=_parse_outlets,
        default=(),
        help="Optional comma-separated outlet codes to include.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_report",
        help="Open the generated report in the default browser.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Export the dashboard to standalone HTML and optionally open it.

    Writes the report using :func:`dashboards.html_report.build_html_report`
    and prints the output path.
    """
    args = parse_args()
    report_path = build_html_report(
        args.output,
        analysis_config_path=args.config,
        dashboard_config_path=args.dashboard_config,
        plotly_js=args.plotly_js,
        refresh_from_snowflake=args.refresh_from_snowflake,
        outlet_filter=args.outlets or None,
    )
    print(f"Dashboard HTML report written to: {report_path}")
    if args.open_report:
        webbrowser.open(report_path.as_uri())


if __name__ == "__main__":
    main()
