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


def test_quadrant_transition_chart_empty() -> None:
    fig = quadrant_transition_chart(pd.DataFrame())
    assert fig.data == ()
