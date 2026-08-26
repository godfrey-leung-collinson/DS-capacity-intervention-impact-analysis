"""Tests for dashboard summary helpers."""

from __future__ import annotations

import pandas as pd

from dashboards.summary import build_executive_summary, metric_change_table


def test_build_executive_summary_empty() -> None:
    summary = build_executive_summary(pd.DataFrame())
    assert summary.outlet_count == 0
    assert "No intervention results" in summary.headline


def test_build_executive_summary_with_impact() -> None:
    impact = pd.DataFrame(
        [
            {
                "outlet_code": "BRS2",
                "pp_visit_volume_delta": 100.0,
                "pp_visit_volume_pct_change": 0.1,
                "avg_monthly_visits_pct_change": 0.1,
                "estimated_pp_market_share_pct_change": 0.05,
                "quadrant_changed": False,
                "pre_quadrant_label": "Capacity risk",
                "post_quadrant_label": "Capacity risk",
            },
            {
                "outlet_code": "MAN4",
                "pp_visit_volume_delta": -50.0,
                "pp_visit_volume_pct_change": -0.05,
                "avg_monthly_visits_pct_change": -0.05,
                "estimated_pp_market_share_pct_change": -0.02,
                "quadrant_changed": True,
                "pre_quadrant_label": "Capacity/Opportunity gap",
                "post_quadrant_label": "Low priority",
            },
        ]
    )
    summary = build_executive_summary(impact)
    assert summary.outlet_count == 2
    assert summary.outlets_with_visit_increase == 1
    assert summary.outlets_with_quadrant_change == 1
    assert summary.pre_capacity_risk_count == 1
    assert summary.post_capacity_risk_count == 1
    assert len(summary.bullets) >= 2


def test_metric_change_table_shape() -> None:
    impact = pd.DataFrame(
        [
            {
                "outlet_code": "BRS2",
                "pre_pp_visit_volume": 100.0,
                "post_pp_visit_volume": 120.0,
                "pp_visit_volume_delta": 20.0,
                "pp_visit_volume_pct_change": 0.2,
            }
        ]
    )
    table = metric_change_table(impact, metrics=("pp_visit_volume",))
    assert len(table) == 1
    assert table.iloc[0]["metric_key"] == "pp_visit_volume"
    assert table.iloc[0]["pre"] == 100.0
