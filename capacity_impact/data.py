"""Snowflake extraction and SQL-template helpers."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable

import pandas as pd

from capacity_impact.config import AnalysisConfig
from capacity_impact.exc import InvalidSQL
from capacity_impact.snowflake_manager import SnowflakeManager

TOKEN_PATTERN = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def _sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_sql(
    template: str,
    *,
    start_datetime: datetime,
    end_datetime: datetime,
    outlet_codes: Iterable[str],
) -> str:
    """Render the deliberately small, allow-listed SQL template vocabulary."""
    values = {
        "start_datetime": _sql_string(start_datetime.isoformat(sep=" ")),
        "end_datetime": _sql_string(end_datetime.isoformat(sep=" ")),
        "outlet_codes": ", ".join(
            _sql_string(str(code).strip().upper()) for code in outlet_codes
        ),
    }
    tokens = set(TOKEN_PATTERN.findall(template))
    unknown = tokens.difference(values)
    if unknown:
        raise InvalidSQL(f"Unknown SQL template tokens: {', '.join(sorted(unknown))}")
    rendered = TOKEN_PATTERN.sub(lambda match: values[match.group(1)], template)
    if TOKEN_PATTERN.search(rendered):
        raise InvalidSQL("SQL template contains unresolved tokens")
    return rendered


def extraction_bounds(config: AnalysisConfig) -> tuple[datetime, datetime]:
    starts = [period.start for lounge in config.lounges for period in (lounge.pre, lounge.post)]
    ends = [period.end for lounge in config.lounges for period in (lounge.pre, lounge.post)]
    return min(starts), max(ends)


def query_dataframe(connection, sql: str) -> pd.DataFrame:
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetch_pandas_all().rename(columns=str.lower)
    finally:
        cursor.close()


def extract_inputs(config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Execute the visit and flight extracts for all configured periods."""
    start, end = extraction_bounds(config)
    codes = [lounge.outlet_code for lounge in config.lounges]
    visit_sql = render_sql(
        config.sql_templates.visit_extract.read_text(),
        start_datetime=start,
        end_datetime=end,
        outlet_codes=codes,
    )
    flight_sql = render_sql(
        config.sql_templates.flight_extract.read_text(),
        start_datetime=start,
        end_datetime=end,
        outlet_codes=codes,
    )
    manager = SnowflakeManager.from_settings(config.snowflake)
    connection = manager.connect()
    try:
        return query_dataframe(connection, visit_sql), query_dataframe(connection, flight_sql)
    finally:
        manager.close_connection()
