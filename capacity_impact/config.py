"""Load and validate intervention-analysis configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Period:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("Period start must be before period end")


@dataclass(frozen=True)
class LoungeIntervention:
    outlet_code: str
    intervention_date: datetime
    pre: Period
    post: Period
    pre_number_of_seats: float | None = None
    post_number_of_seats: float | None = None


@dataclass(frozen=True)
class MetricSettings:
    slot_minutes: int = 15
    dwell_time_minutes: int = 60
    max_allowed_seat_proportion: float = 0.70
    forward_traffic_hours: int = 3
    high_utilisation_threshold: float = 0.53
    traffic_threshold_mode: str = "pre_percentile"
    high_traffic_threshold: float | None = None
    traffic_percentile: float = 70.0


@dataclass(frozen=True)
class SqlTemplates:
    visit_extract: Path
    flight_extract: Path


@dataclass(frozen=True)
class AnalysisConfig:
    lounges: tuple[LoungeIntervention, ...]
    metrics: MetricSettings
    snowflake: dict[str, Any]
    sql_templates: SqlTemplates
    output_directory: Path


def _project_relative_path(config_path: Path, value: Any, default: str) -> Path:
    path = Path(str(value) if value is not None else default)
    if not path.is_absolute():
        path = config_path.parent.parent / path
    return path


def _datetime(value: Any, field: str) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date or datetime") from exc


def _period(raw: Any, field: str) -> Period:
    if not isinstance(raw, dict):
        raise ValueError(f"{field} must be a mapping")
    return Period(
        start=_datetime(raw.get("start"), f"{field}.start"),
        end=_datetime(raw.get("end"), f"{field}.end"),
    )


def load_config(path: str | Path) -> AnalysisConfig:
    """Return validated settings from a YAML file."""
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text()) or {}

    raw_lounges = raw.get("lounges")
    if not isinstance(raw_lounges, list) or not raw_lounges:
        raise ValueError("Config must define at least one lounge")

    lounges: list[LoungeIntervention] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_lounges):
        if not isinstance(item, dict):
            raise ValueError(f"lounges[{index}] must be a mapping")
        code = str(item.get("outlet_code", "")).strip().upper()
        if not code:
            raise ValueError(f"lounges[{index}].outlet_code cannot be empty")
        if code in seen:
            raise ValueError(f"Duplicate outlet_code: {code}")
        seen.add(code)
        intervention = _datetime(
            item.get("intervention_date"),
            f"lounges[{index}].intervention_date",
        )
        pre = _period(item.get("pre"), f"lounges[{index}].pre")
        post = _period(item.get("post"), f"lounges[{index}].post")
        if pre.end > intervention or post.start < intervention:
            raise ValueError(
                f"{code}: pre must end on/before and post must start on/after intervention"
            )
        pre_seats = item.get("pre_number_of_seats")
        post_seats = item.get("post_number_of_seats")
        for field_name, value in (
            ("pre_number_of_seats", pre_seats),
            ("post_number_of_seats", post_seats),
        ):
            if value is not None and float(value) <= 0:
                raise ValueError(f"{code}: {field_name} must be positive")
        lounges.append(
            LoungeIntervention(
                code,
                intervention,
                pre,
                post,
                None if pre_seats is None else int(pre_seats),
                None if post_seats is None else int(post_seats),
            )
        )

    metric_values = raw.get("metrics", {})
    metrics = MetricSettings(**metric_values)
    if metrics.slot_minutes <= 0 or 60 % metrics.slot_minutes:
        raise ValueError("metrics.slot_minutes must be a positive divisor of 60")
    if metrics.dwell_time_minutes <= 0 or metrics.forward_traffic_hours <= 0:
        raise ValueError("Dwell time and forward traffic hours must be positive")
    if not 0 < metrics.max_allowed_seat_proportion <= 1:
        raise ValueError("max_allowed_seat_proportion must be in (0, 1]")
    if not 0 <= metrics.high_utilisation_threshold:
        raise ValueError("high_utilisation_threshold cannot be negative")
    if metrics.traffic_threshold_mode not in {"fixed", "pre_percentile"}:
        raise ValueError("traffic_threshold_mode must be fixed or pre_percentile")
    if metrics.traffic_threshold_mode == "fixed" and metrics.high_traffic_threshold is None:
        raise ValueError("high_traffic_threshold is required in fixed mode")
    if not 0 < metrics.traffic_percentile < 100:
        raise ValueError("traffic_percentile must be between 0 and 100")

    raw_sql = raw.get("sql", {})
    sql_templates = SqlTemplates(
        visit_extract=_project_relative_path(
            config_path,
            raw_sql.get("visit_extract"),
            "SQL/extract_visits.sql",
        ),
        flight_extract=_project_relative_path(
            config_path,
            raw_sql.get("flight_extract"),
            "SQL/extract_flights.sql",
        ),
    )

    output = _project_relative_path(
        config_path,
        raw.get("output", {}).get("directory"),
        "output",
    )

    return AnalysisConfig(
        lounges=tuple(lounges),
        metrics=metrics,
        snowflake=dict(raw.get("snowflake", {})),
        sql_templates=sql_templates,
        output_directory=output,
    )
