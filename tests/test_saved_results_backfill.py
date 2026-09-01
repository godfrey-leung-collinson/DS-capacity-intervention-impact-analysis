from __future__ import annotations

import pandas as pd

from capacity_impact.analysis import ensure_change_metric_columns
from capacity_impact.config import load_config
from dashboards.data import enrich_saved_results
from dashboards.metrics import available_trackable_metrics


def test_ensure_change_metric_columns_adds_missing_visit_to_flight_ratio() -> None:
    impact = pd.DataFrame(
        {
            "outlet_code": ["A"],
            "pre_pp_visit_volume": [10.0],
            "post_pp_visit_volume": [12.0],
        }
    )

    enriched = ensure_change_metric_columns(impact)

    assert "pre_visit_to_flight_ratio" in enriched.columns
    assert "post_visit_to_flight_ratio" in enriched.columns
    assert "visit_to_flight_ratio_delta" in enriched.columns
    assert pd.isna(enriched.loc[0, "pre_visit_to_flight_ratio"])


def test_enrich_saved_results_handles_stale_csv_outputs() -> None:
    config = load_config("config/analysis.yaml")
    period_metrics = pd.read_csv(config.output_directory / "period_metrics.csv")
    impact = pd.read_csv(config.output_directory / "intervention_impact.csv")

    enriched_periods, enriched_impact = enrich_saved_results(
        period_metrics,
        impact,
        config,
    )

    assert "pre_visit_to_flight_ratio" in enriched_impact.columns
    assert "visit_to_flight_ratio" not in available_trackable_metrics(enriched_impact)
    assert not enriched_periods.empty
