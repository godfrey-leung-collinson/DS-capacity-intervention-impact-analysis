"""Plotly charts for intervention impact analysis."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from dashboards.metrics import TRACKABLE_METRICS, metric_label
from dashboards.outlet_series import OUTLET_SERIES_METRICS, outlet_series_metric_label

COLORS = {
    "pre": "#003865",
    "post": "#ce0058",
    "positive": "#16a34a",
    "negative": "#dc2626",
    "neutral": "#64748b",
    "arrow_changed": "#ce0058",
    "arrow_unchanged": "#94a3b8",
}

QUADRANT_BG: dict[str, str] = {
    "high util, high air traffic": "rgba(220,38,38,0.15)",
    "low util, high air traffic": "rgba(245,158,11,0.15)",
    "high util, low air traffic": "rgba(59,130,246,0.15)",
    "low util, low air traffic": "rgba(156,163,175,0.15)",
}


def pre_post_grouped_bar(impact: pd.DataFrame, metric: str) -> go.Figure:
    """
    Build grouped pre/post bars for one metric across outlets.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    metric : str
        Metric key to plot.

    Returns
    -------
    plotly.graph_objects.Figure
        Grouped bar chart figure.
    """
    labels = impact["outlet_code"].astype(str)
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Pre",
            x=labels,
            y=pd.to_numeric(impact[f"pre_{metric}"], errors="coerce"),
            marker_color=COLORS["pre"],
        )
    )
    fig.add_trace(
        go.Bar(
            name="Post",
            x=labels,
            y=pd.to_numeric(impact[f"post_{metric}"], errors="coerce"),
            marker_color=COLORS["post"],
        )
    )
    fig.update_layout(
        barmode="group",
        title=metric_label(metric),
        xaxis_title="Outlet",
        yaxis_title=metric_label(metric),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        height=420,
        margin=dict(t=70, b=40),
    )

    if ("utilisation" in metric) or ("market_share" in metric):
        fig.layout.yaxis.tickformat = ',.0%'
    
    return fig


def delta_bar_chart(impact: pd.DataFrame, metric: str) -> go.Figure:
    """
    Build horizontal delta bars coloured by direction of change.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    metric : str
        Metric key whose ``{metric}_delta`` column is plotted.

    Returns
    -------
    plotly.graph_objects.Figure
        Horizontal bar chart of absolute changes.
    """
    work = impact[["outlet_code", f"{metric}_delta"]].copy()
    work["delta"] = pd.to_numeric(work[f"{metric}_delta"], errors="coerce")
    work = work.dropna(subset=["delta"]).sort_values("delta")
    colors = [
        COLORS["positive"] if value >= 0 else COLORS["negative"]
        for value in work["delta"]
    ]

    if ("utilisation" in metric) or ("market_share" in metric):
        work["delta"] = work["delta"].map(lambda v: f"{100 * v:+.1f}%" if abs(v) < 1 else f"{v:+,.0f}%")
    else:
        work["delta"] = work["delta"].map(lambda v: f"{v:+.2f}" if abs(v) < 1 else f"{v:+,.0f}")

    fig = go.Figure(
        go.Bar(
            x=work["delta"],
            y=work["outlet_code"],
            orientation="h",
            marker_color=colors,
            text=work["delta"],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"{metric_label(metric)} change (post − pre)",
        xaxis_title="Change",
        yaxis_title="Outlet",
        height=max(320, 48 * len(work) + 80),
        margin=dict(t=60, l=80, r=40),
    )

    if ("utilisation" in metric) or ("market share" in metric):
        fig.layout.xaxis.tickformat = ',.0%'

    return fig


def metric_heatmap(impact: pd.DataFrame, metrics: tuple[str, ...] = TRACKABLE_METRICS) -> go.Figure:
    """
    Build a heatmap of percentage change by outlet and metric.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    metrics : tuple of str, optional
        Metric keys to include in the heatmap.

    Returns
    -------
    plotly.graph_objects.Figure
        Heatmap figure, or an empty figure when no metrics are available.
    """
    matrix = []
    labels = []
    for metric in metrics:
        pct_col = f"{metric}_pct_change"
        if pct_col not in impact.columns:
            continue
        values = pd.to_numeric(impact[pct_col], errors="coerce")
        matrix.append(values.tolist())
        labels.append(metric_label(metric))
    if not matrix:
        return go.Figure()
    fig = go.Figure(
        data=go.Heatmap(
            z=matrix,
            x=impact["outlet_code"].astype(str).tolist(),
            y=labels,
            colorscale="RdYlGn",
            zmid=0,
            text=[
                [f"{v:+.0%}" if pd.notna(v) else "—" for v in row]
                for row in matrix
            ],
            texttemplate="%{text}",
            hovertemplate="Outlet: %{x}<br>Metric: %{y}<br>Change: %{text}<extra></extra>",
        )
    )
    fig.update_layout(
        title="Percentage change by outlet and metric",
        xaxis_title="Outlet",
        yaxis_title="Metric",
        height=max(360, 36 * len(labels) + 120),
        margin=dict(t=60, l=180),
    )
    return fig


def _resolve_traffic_threshold(
    impact: pd.DataFrame,
    high_traffic_threshold: float | None,
) -> float:
    """
    Resolve the airport traffic threshold for quadrant backgrounds.

    Parameters
    ----------
    impact : pandas.DataFrame
        Intervention impact table.
    high_traffic_threshold : float or None
        Configured fixed threshold. When ``None``, values are read from impact.

    Returns
    -------
    float
        Traffic threshold used to draw quadrant lines.
    """
    if high_traffic_threshold is not None:
        return float(high_traffic_threshold)
    for column in ("pre_traffic_threshold", "post_traffic_threshold"):
        if column in impact.columns:
            values = pd.to_numeric(impact[column], errors="coerce").dropna()
            if not values.empty:
                return float(values.iloc[0])
    return 30.0


def _quadrant_background_shapes(
    x_lo: float,
    x_upper: float,
    y_upper: float,
    traffic_threshold: float,
    util_threshold_pct: float,
) -> list[dict]:
    """
    Build Plotly layout shapes for quadrant background shading.

    Parameters
    ----------
    x_lo : float
        Lower x-axis bound.
    x_upper : float
        Upper x-axis bound.
    y_upper : float
        Upper y-axis bound in percent utilisation.
    traffic_threshold : float
        Vertical traffic threshold.
    util_threshold_pct : float
        Horizontal utilisation threshold in percent.

    Returns
    -------
    list of dict
        Plotly shape dictionaries.
    """
    return [
        dict(
            type="rect",
            x0=x_lo,
            x1=traffic_threshold,
            y0=0,
            y1=util_threshold_pct,
            fillcolor=QUADRANT_BG["low util, low air traffic"],
            layer="below",
            line_width=0,
        ),
        dict(
            type="rect",
            x0=x_lo,
            x1=traffic_threshold,
            y0=util_threshold_pct,
            y1=y_upper,
            fillcolor=QUADRANT_BG["high util, low air traffic"],
            layer="below",
            line_width=0,
        ),
        dict(
            type="rect",
            x0=traffic_threshold,
            x1=x_upper,
            y0=0,
            y1=util_threshold_pct,
            fillcolor=QUADRANT_BG["low util, high air traffic"],
            layer="below",
            line_width=0,
        ),
        dict(
            type="rect",
            x0=traffic_threshold,
            x1=x_upper,
            y0=util_threshold_pct,
            y1=y_upper,
            fillcolor=QUADRANT_BG["high util, high air traffic"],
            layer="below",
            line_width=0,
        ),
        dict(
            type="line",
            x0=traffic_threshold,
            x1=traffic_threshold,
            y0=0,
            y1=y_upper,
            line=dict(color="#222", width=2, dash="dash"),
        ),
        dict(
            type="line",
            x0=x_lo,
            x1=x_upper,
            y0=util_threshold_pct,
            y1=util_threshold_pct,
            line=dict(color="#222", width=2, dash="dash"),
        ),
    ]


def quadrant_transition_chart(
    impact: pd.DataFrame,
    *,
    high_utilisation_threshold: float = 0.53,
    high_traffic_threshold: float | None = None,
) -> go.Figure:
    """
    Build a quadrant scatter showing pre/post lounge movement.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    high_utilisation_threshold : float, default 0.53
        Utilisation threshold for quadrant backgrounds.
    high_traffic_threshold : float or None, optional
        Traffic threshold for quadrant backgrounds.

    Returns
    -------
    plotly.graph_objects.Figure
        Scatter plot with pre/post markers and movement arrows.
    """
    fig = go.Figure()
    if impact.empty:
        return fig

    work = impact.copy()
    work["outlet_code"] = work["outlet_code"].astype(str)
    work["pre_x"] = pd.to_numeric(work["pre_airport_traffic_peak"], errors="coerce")
    work["post_x"] = pd.to_numeric(work["post_airport_traffic_peak"], errors="coerce")
    work["pre_y"] = 100.0 * pd.to_numeric(work["pre_peak_pp_utilisation_rate"], errors="coerce")
    work["post_y"] = 100.0 * pd.to_numeric(work["post_peak_pp_utilisation_rate"], errors="coerce")
    work = work.dropna(subset=["pre_x", "post_x", "pre_y", "post_y"])
    if work.empty:
        return fig

    traffic_threshold = _resolve_traffic_threshold(work, high_traffic_threshold)
    util_threshold_pct = 100.0 * high_utilisation_threshold

    x_values = pd.concat([work["pre_x"], work["post_x"]])
    y_values = pd.concat([work["pre_y"], work["post_y"]])
    x_max = float(x_values.max())
    y_max = float(y_values.max())
    x_lo = min(float(x_values.min()) * 0.85, -0.5) if x_max > 0 else -0.5
    x_upper = max(x_max * 1.15, traffic_threshold * 1.3, traffic_threshold + 15)
    y_upper = max(y_max * 1.15, util_threshold_pct * 1.3, 100)

    hover_cols = [
        "outlet_code",
        "pre_quadrant_label",
        "post_quadrant_label",
        "quadrant_transition",
    ]
    for column in hover_cols:
        if column not in work.columns:
            work[column] = "—"

    pre_hover = (
        "<b>%{customdata[0]}</b> (pre)<br>"
        "PP utilisation: %{y:.1f}%<br>"
        "Airport traffic index: %{x:.1f}<br>"
        "Quadrant: %{customdata[1]}<extra></extra>"
    )
    post_hover = (
        "<b>%{customdata[0]}</b> (post)<br>"
        "PP utilisation: %{y:.1f}%<br>"
        "Airport traffic index: %{x:.1f}<br>"
        "Quadrant: %{customdata[2]}<br>"
        "Transition: %{customdata[3]}<extra></extra>"
    )

    fig.add_trace(
        go.Scatter(
            x=work["pre_x"],
            y=work["pre_y"],
            mode="markers+text",
            name="Pre intervention",
            text=work["outlet_code"],
            textposition="bottom center",
            textfont=dict(size=9, color=COLORS["pre"]),
            marker=dict(size=11, color=COLORS["pre"], opacity=0.9, line=dict(width=1, color="white")),
            customdata=work[hover_cols].values,
            hovertemplate=pre_hover,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=work["post_x"],
            y=work["post_y"],
            mode="markers+text",
            name="Post intervention",
            text=work["outlet_code"],
            textposition="top center",
            textfont=dict(size=9, color=COLORS["post"]),
            marker=dict(size=13, color=COLORS["post"], opacity=0.95, line=dict(width=1.2, color="white")),
            customdata=work[hover_cols].values,
            hovertemplate=post_hover,
        )
    )

    annotations: list[dict] = []
    for _, row in work.iterrows():
        changed = bool(row.get("quadrant_changed", False))
        annotations.append(
            dict(
                x=float(row["post_x"]),
                y=float(row["post_y"]),
                ax=float(row["pre_x"]),
                ay=float(row["pre_y"]),
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=1.5,
                arrowcolor=COLORS["arrow_changed"] if changed else COLORS["arrow_unchanged"],
                opacity=0.85 if changed else 0.55,
            )
        )

    n_changed = int(work.get("quadrant_changed", pd.Series(dtype=bool)).fillna(False).sum())
    fig.update_layout(
        title=(
            "Quadrant movement: PP utilisation vs airport traffic "
            f"({len(work)} lounges, {n_changed} quadrant change(s))"
        ),
        xaxis_title="Airport traffic index (peak departures, next 3h)",
        yaxis_title="Peak PP utilisation rate",
        height=max(460, 56 * len(work) + 180),
        margin=dict(t=70, l=60, r=30, b=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
        shapes=_quadrant_background_shapes(
            x_lo, x_upper, y_upper, traffic_threshold, util_threshold_pct
        ),
        annotations=[
            dict(
                x=max(x_lo + 0.5, 0.5),
                y=y_upper - 4,
                text="Usage anomaly",
                showarrow=False,
                xanchor="left",
                font=dict(size=9, color="#555"),
            ),
            dict(
                x=max(x_lo + 0.5, 0.5),
                y=util_threshold_pct - 4,
                text="Low priority",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=9, color="#555"),
            ),
            dict(
                x=traffic_threshold + 5,
                y=y_upper - 4,
                text="Capacity risk",
                showarrow=False,
                xanchor="left",
                font=dict(size=9, color="#555"),
            ),
            dict(
                x=traffic_threshold + 5,
                y=util_threshold_pct - 4,
                text="Capacity/Opportunity gap",
                showarrow=False,
                xanchor="left",
                yanchor="top",
                font=dict(size=9, color="#555"),
            ),
            dict(
                x=x_upper - 50,
                y=util_threshold_pct + 5,
                text=f"{util_threshold_pct:.0f}% utilisation",
                showarrow=False,
                xanchor="left",
                font=dict(size=11, color="#333"),
            ),
            dict(
                x=traffic_threshold + 1,
                y=1,
                text=f"Traffic threshold ({traffic_threshold:.0f})",
                showarrow=False,
                xanchor="left",
                yanchor="bottom",
                font=dict(size=11, color="#333"),
            ),
            *annotations,
        ],
    )
    fig.update_xaxes(range=[x_lo, x_upper], gridcolor="#d8d8d8")
    fig.update_yaxes(range=[0, y_upper], ticksuffix="%", gridcolor="#d8d8d8")
    return fig


def outlet_metric_timeseries_chart(
    series: pd.DataFrame,
    *,
    metric_key: str,
    outlet_code: str,
    intervention_date,
    utilisation_threshold: float | None = None,
) -> go.Figure:
    """
    Build a (PP) utilisation time-series chart split by pre/post period.

    Parameters
    ----------
    series : pandas.DataFrame
        Time series with ``timestamp``, ``period`` and metric value columns.
    metric_key : str
        Key from :data:`dashboards.outlet_series.OUTLET_SERIES_METRICS`.
    outlet_code : str
        Outlet identifier for the chart title.
    intervention_date
        Intervention timestamp used for a vertical marker line.
    utilisation_threshold : float or None, optional
        Optional utilisation threshold line for percent metrics.

    Returns
    -------
    plotly.graph_objects.Figure
        Line chart figure.
    """
    fig = go.Figure()
    if series.empty:
        return fig

    spec = OUTLET_SERIES_METRICS.get(metric_key, {})
    value_col = spec.get("column", metric_key)
    y_title = outlet_series_metric_label(metric_key)
    is_percent = spec.get("format") == "percent"

    for period_name, color, label in (
        ("post", COLORS["post"], "Post intervention"),
        ("pre", COLORS["pre"], "Pre intervention"),
    ):
        subset = series[series["period"].eq(period_name)].copy()
        if subset.empty:
            continue
        y_values = pd.to_numeric(subset[value_col], errors="coerce")
        if is_percent:
            y_values = 100.0 * y_values

        # NOTE: for "joining" the pre and post period lines in the time-series plot
        if period_name == "post":
            intercept_point = dict(
                x=subset["timestamp"].iloc[0],
                y=y_values.iloc[0],
                xref="x",
                yref="y",
            )

        if period_name == "pre":
            x_values = [*subset["timestamp"].values, intercept_point["x"]]
            y_values = [*y_values.values, intercept_point["y"]]
        else:
            x_values = subset["timestamp"]
            y_values = y_values

        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines+markers",
                name=label,
                line=dict(color=color, width=2),
                marker=dict(size=6, color=color),
                hovertemplate=(
                    "Date: %{x|%Y-%m-%d}<br>"
                    f"{y_title}: "
                    + ("%{y:.1f}%<extra></extra>" if is_percent else "%{y:,.1f}<extra></extra>")
                ),
            )
        )

    shapes: list[dict] = []
    annotations: list[dict] = []
    if intervention_date is not None:
        intervention = pd.to_datetime(intervention_date)
        shapes.append(
            dict(
                type="line",
                x0=intervention,
                x1=intervention,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="#64748b", width=2, dash="dot"),
            )
        )
        annotations.append(
            dict(
                x=intervention,
                y=1.02,
                yref="paper",
                text="Intervention",
                showarrow=False,
                font=dict(size=11, color="#64748b"),
            )
        )

    if utilisation_threshold is not None and is_percent:
        threshold_pct = 100.0 * utilisation_threshold
        shapes.append(
            dict(
                type="line",
                x0=series["timestamp"].min(),
                x1=series["timestamp"].max(),
                y0=threshold_pct,
                y1=threshold_pct,
                line=dict(color="#222", width=1.5, dash="dash"),
            )
        )
        annotations.append(
            dict(
                x=series["timestamp"].max(),
                y=threshold_pct,
                text=f"{threshold_pct:.0f}% threshold",
                showarrow=False,
                xanchor="right",
                yanchor="bottom",
                font=dict(size=10, color="#333"),
            )
        )

    fig.update_layout(
        title=f"{outlet_code}: {y_title} over time",
        xaxis_title="Date",
        yaxis_title=y_title + (" (%)" if is_percent else ""),
        height=460,
        margin=dict(t=70, l=60, r=30, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
        shapes=shapes,
        annotations=annotations,
    )
    if is_percent:
        fig.update_yaxes(ticksuffix="%")
    fig.update_xaxes(gridcolor="#d8d8d8")
    fig.update_yaxes(gridcolor="#d8d8d8")
    return fig


def daily_visit_volume_distribution_chart(
    daily_visits: pd.DataFrame,
    *,
    outlet_code: str,
) -> go.Figure:
    """
    Compare pre vs post distributions of daily visit volume.

    Parameters
    ----------
    daily_visits : pandas.DataFrame
        Daily visit totals with ``period`` and ``daily_visit_volume`` columns.
    outlet_code : str
        Outlet identifier for the chart title.

    Returns
    -------
    plotly.graph_objects.Figure
        Overlaid histogram figure.
    """
    fig = go.Figure()
    if daily_visits.empty:
        return fig

    for period_name, color, label in (
        ("pre", COLORS["pre"], "Pre intervention"),
        ("post", COLORS["post"], "Post intervention"),
    ):
        subset = daily_visits[daily_visits["period"].eq(period_name)].copy()
        values = pd.to_numeric(subset["daily_visit_volume"], errors="coerce").dropna()
        if values.empty:
            continue
        fig.add_trace(
            go.Histogram(
                x=values,
                name=label,
                marker_color=color,
                opacity=0.55,
                histnorm="probability density",
                nbinsx=min(20, max(5, len(values))),
                hovertemplate="Daily visits: %{x:,.0f}<br>Density: %{y:.3f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=f"{outlet_code}: daily visit volume distribution (pre vs post)",
        xaxis_title="Daily visit volume",
        yaxis_title="Density",
        barmode="overlay",
        height=460,
        margin=dict(t=70, l=60, r=30, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#d8d8d8")
    fig.update_yaxes(gridcolor="#d8d8d8")
    return fig


def daily_visit_volume_timeseries_chart(
    daily_visits: pd.DataFrame,
    *,
    outlet_code: str,
    intervention_date,
) -> go.Figure:
    """
    Plot daily visit totals over time with an intervention marker.

    Parameters
    ----------
    daily_visits : pandas.DataFrame
        Daily visit totals with ``date``, ``period`` and ``daily_visit_volume``.
    outlet_code : str
        Outlet identifier for the chart title.
    intervention_date
        Intervention timestamp used for a vertical marker line.

    Returns
    -------
    plotly.graph_objects.Figure
        Grouped daily bar chart.
    """
    fig = go.Figure()
    if daily_visits.empty:
        return fig

    for period_name, color, label in (
        ("pre", COLORS["pre"], "Pre intervention"),
        ("post", COLORS["post"], "Post intervention"),
    ):
        subset = daily_visits[daily_visits["period"].eq(period_name)].copy()
        if subset.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=subset["date"],
                y=pd.to_numeric(subset["daily_visit_volume"], errors="coerce"),
                name=label,
                marker_color=color,
                opacity=0.85,
                hovertemplate="Date: %{x|%Y-%m-%d}<br>Visits: %{y:,.0f}<extra></extra>",
            )
        )

    shapes: list[dict] = []
    if intervention_date is not None:
        intervention = pd.to_datetime(intervention_date)
        shapes.append(
            dict(
                type="line",
                x0=intervention,
                x1=intervention,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="#64748b", width=2, dash="dot"),
            )
        )

    fig.update_layout(
        title=f"{outlet_code}: daily visit volume over time",
        xaxis_title="Date",
        yaxis_title="Daily visit volume",
        barmode="group",
        height=420,
        margin=dict(t=70, l=60, r=30, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        plot_bgcolor="white",
        paper_bgcolor="white",
        shapes=shapes,
    )
    fig.update_xaxes(gridcolor="#d8d8d8")
    fig.update_yaxes(gridcolor="#d8d8d8")
    return fig


def outlet_metric_radar(impact: pd.DataFrame, outlet_code: str, metrics: tuple[str, ...]) -> go.Figure:
    """
    Build a normalised pre/post radar chart for one outlet.

    Parameters
    ----------
    impact : pandas.DataFrame
        Paired intervention impact table.
    outlet_code : str
        Outlet identifier to plot.
    metrics : tuple of str
        Metric keys to include on the radar axes.

    Returns
    -------
    plotly.graph_objects.Figure
        Radar chart comparing normalised pre and post values.
    """
    row = impact.loc[impact["outlet_code"].astype(str).eq(outlet_code)]
    if row.empty:
        return go.Figure()
    row = row.iloc[0]
    categories = [metric_label(metric) for metric in metrics]
    pre_values = []
    post_values = []
    for metric in metrics:
        pre = pd.to_numeric(row.get(f"pre_{metric}"), errors="coerce")
        post = pd.to_numeric(row.get(f"post_{metric}"), errors="coerce")
        scale = max(pre, post) if pd.notna(pre) and pd.notna(post) else 1
        scale = float(scale) if scale not in (0, None) and scale == scale else 1.0
        pre_values.append(float(pre / scale) if pd.notna(pre) else 0)
        post_values.append(float(post / scale) if pd.notna(post) else 0)

    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=pre_values + [pre_values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name="Pre",
            line_color=COLORS["pre"],
        )
    )
    fig.add_trace(
        go.Scatterpolar(
            r=post_values + [post_values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name="Post",
            line_color=COLORS["post"],
        )
    )
    fig.update_layout(
        title=f"{outlet_code}: normalised pre vs post",
        polar=dict(radialaxis=dict(visible=True, range=[0, 1.05])),
        height=460,
        margin=dict(t=80),
    )
    return fig
