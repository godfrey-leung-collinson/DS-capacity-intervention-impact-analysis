import pytest

from capacity_impact.analysis import run_analysis


def test_run_analysis_computes_deltas_and_quadrant_change(
    visits,
    flights,
    analysis_config,
):
    periods, impact = run_analysis(visits, flights, analysis_config)

    assert len(periods) == 2
    assert periods["traffic_threshold"].unique().tolist() == [15.0]

    row = impact.iloc[0]
    assert row["pre_pp_visit_volume"] == 30
    assert row["post_pp_visit_volume"] == 50
    assert row["pp_visit_volume_delta"] == 20
    assert row["pp_visit_volume_pct_change"] == pytest.approx(2 / 3)
    assert row["avg_monthly_visits_delta"] == 20
    assert row["estimated_pp_market_share_delta"] == pytest.approx(20 / 70)
    assert bool(row["quadrant_changed"])
    assert row["quadrant_transition"] == "Low priority -> Capacity risk"


def test_seat_overrides_capture_capacity_change(
    visits,
    flights,
    analysis_config,
):
    lounge = analysis_config.lounges[0]
    changed_lounge = type(lounge)(
        lounge.outlet_code,
        lounge.intervention_date,
        lounge.pre,
        lounge.post,
        50,
        100,
    )
    changed_config = type(analysis_config)(
        (changed_lounge,),
        analysis_config.metrics,
        analysis_config.snowflake,
        analysis_config.sql_templates,
        analysis_config.output_directory,
    )

    periods, _ = run_analysis(visits, flights, changed_config)
    assert periods.loc[periods["period"].eq("pre"), "effective_seat_capacity"].iloc[0] == 35
    assert periods.loc[periods["period"].eq("post"), "effective_seat_capacity"].iloc[0] == 70
