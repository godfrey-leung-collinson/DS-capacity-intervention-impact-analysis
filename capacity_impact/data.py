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
    """
    Escape a Python string for safe inclusion in SQL literals.

    Parameters
    ----------
    value : str
        Raw string value.

    Returns
    -------
    str
        Single-quoted SQL string literal.
    """
    return "'" + value.replace("'", "''") + "'"


def render_sql(
    template: str,
    *,
    start_datetime: datetime,
    end_datetime: datetime,
    outlet_codes: Iterable[str],
) -> str:
    """
    Render the allow-listed SQL template vocabulary.

    Parameters
    ----------
    template : str
        SQL template containing ``{{ token }}`` placeholders.
    start_datetime : datetime
        Inclusive extraction start timestamp.
    end_datetime : datetime
        Exclusive extraction end timestamp.
    outlet_codes : iterable of str
        Outlet codes to inject into the template.

    Returns
    -------
    str
        Rendered SQL string.

    Raises
    ------
    InvalidSQL
        If unknown or unresolved template tokens remain.
    """
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
    """
    Return the overall min/max bounds across all configured lounge periods.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration.

    Returns
    -------
    start : datetime
        Earliest configured period start.
    end : datetime
        Latest configured period end.
    """
    starts = [period.start for lounge in config.lounges for period in (lounge.pre, lounge.post)]
    ends = [period.end for lounge in config.lounges for period in (lounge.pre, lounge.post)]
    return min(starts), max(ends)


def query_dataframe(connection, sql: str) -> pd.DataFrame:
    """
    Execute SQL and return a lower-case column DataFrame.

    Parameters
    ----------
    connection
        Open Snowflake connection.
    sql : str
        SQL statement to execute.

    Returns
    -------
    pandas.DataFrame
        Query result with lower-cased column names.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(sql)
        return cursor.fetch_pandas_all().rename(columns=str.lower)
    finally:
        cursor.close()


def extract_inputs(config: AnalysisConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Execute visit and flight extracts for all configured periods.

    Parameters
    ----------
    config : AnalysisConfig
        Analysis configuration including SQL templates and Snowflake settings.

    Returns
    -------
    visits : pandas.DataFrame
        Visit extract.
    flights : pandas.DataFrame
        Flight extract.
    """
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
