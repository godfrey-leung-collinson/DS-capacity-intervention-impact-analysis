from datetime import datetime

import pytest

from capacity_impact.config import load_config
from capacity_impact.data import render_sql
from capacity_impact.exc import InvalidSQL


def test_example_config_loads():
    config = load_config("config/analysis.yaml")
    assert config.lounges[0].outlet_code
    assert config.snowflake["is_run_locally"] is True
    assert config.metrics.high_utilisation_threshold == 0.53
    assert config.sql_templates.visit_extract.name == "extract_visits.sql"
    assert config.sql_templates.flight_extract.name == "extract_flights.sql"


def test_render_sql_quotes_values():
    rendered = render_sql(
        "SELECT {{ start_datetime }}, {{ end_datetime }} "
        "WHERE code IN ({{ outlet_codes }})",
        start_datetime=datetime(2026, 1, 1),
        end_datetime=datetime(2026, 2, 1),
        outlet_codes=["atl10", "O'Hare"],
    )
    assert "'2026-01-01 00:00:00'" in rendered
    assert "'ATL10', 'O''HARE'" in rendered


def test_render_sql_rejects_unknown_token():
    with pytest.raises(InvalidSQL, match="Unknown SQL template tokens"):
        render_sql(
            "SELECT {{ unsafe_identifier }}",
            start_datetime=datetime(2026, 1, 1),
            end_datetime=datetime(2026, 2, 1),
            outlet_codes=["A"],
        )
