from dataclasses import replace
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from capacity_impact.analysis import _airport_for_outlet, run_analysis
from capacity_impact.config import Period
from capacity_impact.data import render_sql
from capacity_impact.exc import DataError, DataInconsistent, DataInvalid, DataMissing, InvalidSQL
from capacity_impact.metrics import compute_traffic_threshold, compute_visit_metrics


def test_invalid_sql_raises_for_unknown_token():
    with pytest.raises(InvalidSQL, match="Unknown SQL template tokens: unsafe_identifier"):
        render_sql(
            "SELECT {{ unsafe_identifier }}",
            start_datetime=datetime(2026, 1, 1),
            end_datetime=datetime(2026, 2, 1),
            outlet_codes=["A"],
        )


def test_invalid_sql_raises_for_unresolved_tokens(monkeypatch):
    class FakePattern:
        def findall(self, _template):
            return ["start_datetime"]

        def sub(self, _repl, _template):
            return "SELECT {{ start_datetime }}"

        def search(self, _rendered):
            return object()

    monkeypatch.setattr("capacity_impact.data.TOKEN_PATTERN", FakePattern())

    with pytest.raises(InvalidSQL, match="SQL template contains unresolved tokens"):
        render_sql(
            "SELECT {{ start_datetime }}",
            start_datetime=datetime(2026, 1, 1),
            end_datetime=datetime(2026, 2, 1),
            outlet_codes=["A"],
        )


def test_data_missing_raises_for_missing_visit_columns():
    visits = pd.DataFrame({"outlet_code": ["TEST1"]})

    with pytest.raises(DataMissing, match="visits is missing columns: airport_code"):
        _airport_for_outlet(visits, "TEST1")


def test_data_missing_raises_when_outlet_has_no_airport_mapping():
    visits = pd.DataFrame(
        {
            "outlet_code": ["OTHER"],
            "airport_code": ["TST"],
        }
    )

    with pytest.raises(DataMissing, match="No airport mapping found for TEST1"):
        _airport_for_outlet(visits, "TEST1")


def test_data_inconsistent_raises_for_multiple_airports_per_outlet():
    visits = pd.DataFrame(
        {
            "outlet_code": ["TEST1", "TEST1"],
            "airport_code": ["TST", "LHR"],
        }
    )

    with pytest.raises(DataInconsistent, match="TEST1 maps to 2 airports"):
        _airport_for_outlet(visits, "TEST1")


def test_data_invalid_raises_when_seats_are_missing(settings):
    visits = pd.DataFrame(
        {
            "visit_interval": pd.to_datetime(["2026-01-01 10:00"]),
            "outlet_code": ["TEST1"],
            "number_of_seats": [np.nan],
            "total_visits": [10],
        }
    )

    with pytest.raises(
        DataInvalid,
        match="TEST1: no valid number_of_seats value or override",
    ):
        compute_visit_metrics(
            visits,
            Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
            settings,
            outlet_code="TEST1",
        )


def test_data_invalid_raises_when_effective_capacity_is_not_positive(settings):
    visits = pd.DataFrame(
        {
            "visit_interval": pd.to_datetime(["2026-01-01 10:00"]),
            "outlet_code": ["TEST1"],
            "number_of_seats": [100],
            "total_visits": [10],
        }
    )

    with pytest.raises(
        DataInvalid,
        match="TEST1: effective seat capacity must be positive",
    ):
        compute_visit_metrics(
            visits,
            Period(datetime(2026, 1, 1), datetime(2026, 1, 2)),
            settings,
            outlet_code="TEST1",
            number_of_seats=0,
        )


def test_data_missing_raises_when_traffic_threshold_cannot_be_derived(settings):
    percentile_settings = replace(settings, traffic_threshold_mode="pre_percentile")

    with pytest.raises(
        DataMissing,
        match="Cannot derive a pre-period traffic threshold from empty data",
    ):
        compute_traffic_threshold(pd.Series([0, np.nan]), percentile_settings)


def test_data_missing_raises_from_run_analysis_for_missing_columns(
    flights,
    analysis_config,
):
    visits = pd.DataFrame(
        {
            "visit_interval": pd.to_datetime(["2026-01-01 10:00"]),
            "outlet_code": ["TEST1"],
            "number_of_seats": [100],
            "total_visits": [10],
        }
    )

    with pytest.raises(DataMissing, match="visits is missing columns: airport_code"):
        run_analysis(visits, flights, analysis_config)


@pytest.mark.parametrize(
    ("exc_type", "base_type"),
    [
        (DataMissing, DataError),
        (DataInvalid, DataError),
        (DataInconsistent, DataError),
    ],
)
def test_data_exceptions_inherit_from_data_error(exc_type, base_type):
    assert issubclass(exc_type, base_type)
