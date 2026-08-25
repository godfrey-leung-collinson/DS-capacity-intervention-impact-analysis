from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from capacity_impact.config import (
    AnalysisConfig,
    LoungeIntervention,
    MetricSettings,
    Period,
    SqlTemplates,
)


@pytest.fixture
def settings() -> MetricSettings:
    return MetricSettings(
        slot_minutes=15,
        dwell_time_minutes=30,
        max_allowed_seat_proportion=0.70,
        forward_traffic_hours=3,
        high_utilisation_threshold=0.50,
        traffic_threshold_mode="fixed",
        high_traffic_threshold=15,
    )


@pytest.fixture
def analysis_config(settings) -> AnalysisConfig:
    lounge = LoungeIntervention(
        outlet_code="TEST1",
        intervention_date=datetime(2026, 1, 2),
        pre=Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
        post=Period(datetime(2026, 1, 2), datetime(2026, 1, 3)),
    )
    return AnalysisConfig(
        (lounge,),
        settings,
        {},
        SqlTemplates(Path("SQL/extract_visits.sql"), Path("SQL/extract_flights.sql")),
        Path("output"),
    )


@pytest.fixture
def visits() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "visit_interval": pd.to_datetime(
                [
                    "2026-01-01 10:00",
                    "2026-01-01 10:15",
                    "2026-01-02 10:00",
                    "2026-01-02 10:15",
                ]
            ),
            "outlet_code": ["TEST1"] * 4,
            "airport_code": ["TST"] * 4,
            "number_of_seats": [100] * 4,
            "total_visits": [10, 20, 20, 30],
        }
    )


@pytest.fixture
def flights() -> pd.DataFrame:
    pre_slots = pd.date_range("2026-01-01 10:00", periods=12, freq="15min")
    post_slots = pd.date_range("2026-01-02 10:00", periods=12, freq="15min")
    return pd.DataFrame(
        {
            "flight_interval": pre_slots.append(post_slots),
            "airport_code": ["TST"] * 24,
            "departure_flight_count": [1] * 12 + [2] * 12,
        }
    )
