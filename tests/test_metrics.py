from dataclasses import replace
from datetime import datetime

import pandas as pd
import pytest

from capacity_impact.config import Period
from capacity_impact.metrics import (
    assign_quadrant,
    compute_airport_traffic_average,
    compute_airport_traffic_peak,
    compute_visit_metrics,
    compute_visit_to_flight_ratio,
)


def test_visit_metrics_follow_dashboard_formula(visits, settings):
    metrics = compute_visit_metrics(
        visits,
        Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
        settings,
        outlet_code="test1",
    )

    assert metrics["pp_visit_volume"] == 30
    assert metrics["avg_monthly_visits"] == 30
    assert metrics["peak_pp_estimated_occupancy"] == 30
    assert metrics["effective_seat_capacity"] == 70
    assert metrics["peak_pp_utilisation_rate"] == pytest.approx(30 / 70)
    assert metrics["estimated_pp_market_share"] == pytest.approx(30 / 70)


def test_market_share_is_mean_of_weekly_peaks(settings):
    visits = pd.DataFrame(
        {
            "visit_interval": pd.to_datetime(["2026-01-01", "2026-01-08"]),
            "outlet_code": ["A", "A"],
            "number_of_seats": [100, 100],
            "total_visits": [35, 70],
        }
    )
    metrics = compute_visit_metrics(
        visits,
        Period(datetime(2026, 1, 1), datetime(2026, 1, 9)),
        replace(settings, dwell_time_minutes=15),
        outlet_code="A",
    )
    assert metrics["estimated_pp_market_share"] == pytest.approx((0.5 + 1.0) / 2)


def test_forward_airport_traffic_peak(flights, settings):
    peak = compute_airport_traffic_peak(
        flights,
        Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
        settings,
        airport_code="TST",
    )
    assert peak == 12


def test_forward_airport_traffic_average(flights, settings):
    average = compute_airport_traffic_average(
        flights,
        Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
        settings,
        airport_code="TST",
    )
    assert average == pytest.approx(1.5)


def test_visit_to_flight_ratio_uses_period_totals(visits, flights, settings):
    period = Period(datetime(2026, 1, 1), datetime(2026, 1, 2))
    ratio = compute_visit_to_flight_ratio(
        visits,
        flights,
        period,
        settings,
        outlet_code="TEST1",
        airport_code="TST",
    )
    assert ratio == pytest.approx(30 / 144)


def test_visit_to_flight_ratio_empty_without_flight_data(visits, settings):
    period = Period(datetime(2026, 1, 1), datetime(2026, 1, 2))
    empty_flights = pd.DataFrame(
        columns=["flight_interval", "airport_code", "departure_flight_count"]
    )
    ratio = compute_visit_to_flight_ratio(
        visits,
        empty_flights,
        period,
        settings,
        outlet_code="TEST1",
        airport_code="TST",
    )
    assert ratio != ratio


@pytest.mark.parametrize(
    ("utilisation", "traffic", "expected"),
    [
        (0.53, 30, "Capacity risk"),
        (0.52, 30, "Capacity/Opportunity gap"),
        (0.53, 29, "Usage anomaly"),
        (0.52, 29, "Low priority"),
    ],
)
def test_quadrant_boundaries_are_inclusive(utilisation, traffic, expected):
    _, label = assign_quadrant(utilisation, traffic, 0.53, 30)
    assert label == expected
