"""Tests for dashboard plot helpers."""

from __future__ import annotations

import pandas as pd

from dashboards.data import load_analysis_config, load_saved_results
from dashboards.plots import quadrant_transition_chart


def test_quadrant_transition_chart_builds_scatter() -> None:
    config = load_analysis_config()
    _, impact = load_saved_results(config)
    fig = quadrant_transition_chart(
        impact,
        high_utilisation_threshold=config.metrics.high_utilisation_threshold,
        high_traffic_threshold=config.metrics.high_traffic_threshold,
    )
    assert len(fig.data) == 2
    assert "Quadrant movement" in fig.layout.title.text
    assert fig.layout.shapes


def test_delta_bar_chart_uses_numeric_zero_centred_axis() -> None:
    from dashboards.plots import delta_bar_chart

    impact = pd.DataFrame(
        {
            "outlet_code": ["EDI4", "MAN4", "STN5", "BRS2"],
            "peak_pp_utilisation_rate_delta": [-0.010582, 0.0, 0.0, 0.10],
        }
    )
    fig = delta_bar_chart(impact, "peak_pp_utilisation_rate")
    assert fig.data
    x_values = list(fig.data[0].x)
    assert any(value < 0 for value in x_values)
    assert any(value > 0 for value in x_values)
    assert all(isinstance(value, (int, float)) for value in x_values)
    assert fig.layout.xaxis.zeroline


def test_quadrant_transition_chart_empty() -> None:
    fig = quadrant_transition_chart(pd.DataFrame())
    assert fig.data == ()
