"""Tests for static HTML dashboard export."""

from __future__ import annotations

from pathlib import Path

from dashboards.report import load_report_context


def test_export_dashboard_html_builds(tmp_path: Path) -> None:
    from dashboards.html_report import build_html_report

    project_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "report.html"
    report_path = build_html_report(
        output_path,
        analysis_config_path=project_root / "config" / "analysis.yaml",
        dashboard_config_path=project_root / "dashboards" / "config" / "dashboard_config.yaml",
    )
    content = report_path.read_text(encoding="utf-8")
    assert report_path.exists()
    assert "Capacity Intervention Impact" in content
    assert "plotly-graph-div" in content
    assert "Executive summary" in content
    assert "Outlet view" in content
    assert "Visit-to-flight ratio" in content
    assert "Quadrant measure" in content
    assert "Pre visit-to-flight ratio" in content


def test_load_report_context_from_saved_outputs() -> None:
    project_root = Path(__file__).resolve().parents[1]
    context = load_report_context(
        analysis_config_path=project_root / "config" / "analysis.yaml",
        dashboard_config_path=project_root / "dashboards" / "config" / "dashboard_config.yaml",
    )
    assert not context.impact.empty
    assert context.summary.outlet_count == len(context.impact)
    assert "visit_to_flight_ratio" in context.selected_metrics
