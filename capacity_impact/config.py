"""Load and validate intervention-analysis configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from capacity_impact.exc import InvalidParameter, MissingParameter


@dataclass(frozen=True)
class Period:
    """
    Half-open analysis window ``[start, end)``.

    Attributes
    ----------
    start : datetime
        Inclusive period start.
    end : datetime
        Exclusive period end.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        """
        Validate that the period bounds are ordered.

        Raises
        ------
        ValueError
            If ``start`` is not strictly before ``end``.
        """
        if self.start >= self.end:
            raise ValueError("Period start must be before period end")


@dataclass(frozen=True)
class LoungeIntervention:
    """
    Pre/post windows and optional seat overrides for one lounge.

    Attributes
    ----------
    outlet_code : str
        Normalised outlet identifier.
    intervention_date : datetime
        Intervention date separating pre and post windows.
    pre : Period
        Pre-intervention comparison window.
    post : Period
        Post-intervention comparison window.
    pre_number_of_seats : float or None, optional
        Seat override for the pre period.
    post_number_of_seats : float or None, optional
        Seat override for the post period.
    """

    outlet_code: str
    intervention_date: datetime
    pre: Period
    post: Period
    pre_number_of_seats: float | None = None
    post_number_of_seats: float | None = None


@dataclass(frozen=True)
class MetricSettings:
    """
    Metric calculation and quadrant-threshold settings.

    Attributes
    ----------
    slot_minutes : int, default 15
        Time-slot width in minutes.
    dwell_time_minutes : int, default 60
        Rolling occupancy dwell window in minutes.
    max_allowed_seat_proportion : float, default 0.70
        Effective capacity multiplier applied to seat count.
    forward_traffic_hours : int, default 3
        Forward-looking airport traffic window in hours.   # TODO: make this dwell time dependent
    high_utilisation_threshold : float, default 0.53
        PP utilisation threshold for quadrant assignment.
    traffic_threshold_mode : str, default "pre_percentile"
        Either ``"fixed"`` or ``"pre_percentile"``.
    high_traffic_threshold : float or None, optional
        Fixed airport-traffic threshold when mode is ``"fixed"``.
    traffic_percentile : float, default 70.0
        Percentile used to derive a traffic threshold from pre-period peaks.
    """

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
    """
    Paths to SQL extraction templates.

    Attributes
    ----------
    visit_extract : pathlib.Path
        Visit extract SQL template path.
    flight_extract : pathlib.Path
        Flight extract SQL template path.
    """

    visit_extract: Path
    flight_extract: Path


@dataclass(frozen=True)
class AnalysisConfig:
    """
    Validated analysis configuration loaded from YAML.

    Attributes
    ----------
    lounges : tuple of LoungeIntervention
        Lounges included in the analysis.
    metrics : MetricSettings
        Metric and threshold settings.
    snowflake : dict
        Snowflake connection settings block from YAML.
    sql_templates : SqlTemplates
        SQL template paths.
    output_directory : pathlib.Path
        Directory for CSV outputs.
    """

    lounges: tuple[LoungeIntervention, ...]
    metrics: MetricSettings
    snowflake: dict[str, Any]
    sql_templates: SqlTemplates
    output_directory: Path


def _project_relative_path(config_path: Path, value: Any, default: str) -> Path:
    """
    Resolve a config path relative to the project root when not absolute.

    Parameters
    ----------
    config_path : pathlib.Path
        Path to the YAML config file.
    value : Any
        Raw path value from YAML.
    default : str
        Default relative path when ``value`` is missing.

    Returns
    -------
    pathlib.Path
        Resolved absolute or project-relative path.
    """
    path = Path(str(value) if value is not None else default)
    if not path.is_absolute():
        path = config_path.parent.parent / path
    return path


def _datetime(value: Any, field: str) -> datetime:
    """
    Parse an ISO date or datetime string from config.

    Parameters
    ----------
    value : Any
        Raw config value.
    field : str
        Field name used in error messages.

    Returns
    -------
    datetime
        Parsed datetime.

    Raises
    ------
    InvalidParameter
        If the value cannot be parsed as ISO format.
    """
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise InvalidParameter(f"{field} must be an ISO date or datetime") from exc


def _period(raw: Any, field: str) -> Period:
    """
    Parse a pre/post period mapping from config.

    Parameters
    ----------
    raw : Any
        Raw YAML mapping with ``start`` and ``end`` keys.
    field : str
        Field name used in error messages.

    Returns
    -------
    Period
        Validated half-open period.

    Raises
    ------
    InvalidParameter
        If the mapping is invalid or bounds are unordered.
    """
    if not isinstance(raw, dict):
        raise InvalidParameter(f"{field} must be a mapping")
    return Period(
        start=_datetime(raw.get("start"), f"{field}.start"),
        end=_datetime(raw.get("end"), f"{field}.end"),
    )


def load_config(path: str | Path) -> AnalysisConfig:
    """
    Load and validate analysis settings from a YAML file.

    Parameters
    ----------
    path : str or pathlib.Path
        Path to the analysis YAML config.

    Returns
    -------
    AnalysisConfig
        Validated configuration object.

    Raises
    ------
    MissingParameter
        If a required parameter is missing.
    InvalidParameter
        If a parameter is invalid.
    """
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text()) or {}

    raw_lounges = raw.get("lounges")
    if not isinstance(raw_lounges, list) or not raw_lounges:
        raise MissingParameter("Config must define at least one lounge")

    lounges: list[LoungeIntervention] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_lounges):
        if not isinstance(item, dict):
            raise InvalidParameter(f"lounges[{index}] must be a mapping")
        code = str(item.get("outlet_code", "")).strip().upper()
        if not code:
            raise MissingParameter(f"lounges[{index}].outlet_code cannot be empty")
        if code in seen:
            raise InvalidParameter(f"Duplicate outlet_code: {code}")
        seen.add(code)
        intervention = _datetime(
            item.get("intervention_date"),
            f"lounges[{index}].intervention_date",
        )
        pre = _period(item.get("pre"), f"lounges[{index}].pre")
        post = _period(item.get("post"), f"lounges[{index}].post")
        if pre.end > intervention or post.start < intervention:
            raise InvalidParameter(
                f"{code}: pre must end on/before and post must start on/after intervention"
            )
        pre_seats = item.get("pre_number_of_seats")
        post_seats = item.get("post_number_of_seats")
        for field_name, value in (
            ("pre_number_of_seats", pre_seats),
            ("post_number_of_seats", post_seats),
        ):
            if value is not None and float(value) <= 0:
                raise InvalidParameter(f"{code}: {field_name} must be positive")
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
        raise InvalidParameter("metrics.slot_minutes must be a positive divisor of 60")
    if metrics.dwell_time_minutes <= 0 or metrics.forward_traffic_hours <= 0:
        raise InvalidParameter("Dwell time and forward traffic hours must be positive")
    if not 0 < metrics.max_allowed_seat_proportion <= 1:
        raise InvalidParameter("max_allowed_seat_proportion must be in (0, 1]")
    if not 0 <= metrics.high_utilisation_threshold:
        raise InvalidParameter("high_utilisation_threshold cannot be negative")
    if metrics.traffic_threshold_mode not in {"fixed", "pre_percentile"}:
        raise InvalidParameter("traffic_threshold_mode must be fixed or pre_percentile")
    if metrics.traffic_threshold_mode == "fixed" and metrics.high_traffic_threshold is None:
        raise InvalidParameter("high_traffic_threshold is required in fixed mode")
    if not 0 < metrics.traffic_percentile < 100:
        raise InvalidParameter("traffic_percentile must be between 0 and 100")

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
