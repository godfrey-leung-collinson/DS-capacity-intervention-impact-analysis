"""
Capacity intervention impact dashboard.

Usage (from project root):
    streamlit run dashboards/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboards.data import (
    load_analysis_config,
    load_raw_inputs,
    load_saved_results,
    run_live_analysis,
)
from dashboards.metrics import (
    TRACKABLE_METRICS,
    format_metric_value,
    metric_label,
)
from dashboards.outlet_series import (
    OUTLET_SERIES_METRICS,
    build_outlet_slot_series,
    daily_visit_volume_series,
    intervention_timestamp,
    lounge_for_outlet,
    outlet_metric_timeseries,
    outlet_series_metric_label,
)
from dashboards.plots import (
    daily_visit_volume_distribution_chart,
    daily_visit_volume_timeseries_chart,
    delta_bar_chart,
    metric_heatmap,
    outlet_metric_radar,
    outlet_metric_timeseries_chart,
    pre_post_grouped_bar,
    quadrant_transition_chart,
)
from dashboards.report import styled_impact_table
from dashboards.summary import build_executive_summary

DASHBOARD_CONFIG_PATH = Path(__file__).parent / "config" / "dashboard_config.yaml"


@st.cache_data(show_spinner=False)
def load_dashboard_config() -> dict:
    """
    Load dashboard YAML settings with Streamlit caching.

    Returns
    -------
    dict
        Parsed dashboard configuration.
    """
    if DASHBOARD_CONFIG_PATH.exists():
        return yaml.safe_load(DASHBOARD_CONFIG_PATH.read_text()) or {}
    return {}


@st.cache_data(show_spinner="Loading saved analysis outputs...")
def cached_saved_results(config_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load saved CSV analysis outputs with Streamlit caching.

    Parameters
    ----------
    config_path : str
        Path to the analysis YAML config.

    Returns
    -------
    period_metrics : pandas.DataFrame
        Period-level metrics table.
    impact : pandas.DataFrame
        Paired intervention impact table.
    """
    config = load_analysis_config(Path(config_path))
    return load_saved_results(config)


@st.cache_data(show_spinner="Running Snowflake analysis...")
def cached_live_results(config_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run live Snowflake analysis with Streamlit caching.

    Parameters
    ----------
    config_path : str
        Path to the analysis YAML config.

    Returns
    -------
    period_metrics : pandas.DataFrame
        Period-level metrics table.
    impact : pandas.DataFrame
        Paired intervention impact table.
    """
    config = load_analysis_config(Path(config_path))
    return run_live_analysis(config)


@st.cache_data(show_spinner="Loading visit extracts...")
def cached_raw_inputs(config_path: str, refresh_from_snowflake: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load visit and flight extracts with Streamlit caching.

    Parameters
    ----------
    config_path : str
        Path to the analysis YAML config.
    refresh_from_snowflake : bool
        When ``True``, query Snowflake directly.

    Returns
    -------
    visits : pandas.DataFrame
        Visit extract.
    flights : pandas.DataFrame
        Flight extract.
    """
    config = load_analysis_config(Path(config_path))
    if refresh_from_snowflake:
        from capacity_impact.data import extract_inputs

        return extract_inputs(config)
    return load_raw_inputs(config)


def render_executive_summary(summary) -> None:
    """
    Render the executive summary panel and KPI metrics.

    Parameters
    ----------
    summary : ExecutiveSummary
        Portfolio summary object from :func:`dashboards.summary.build_executive_summary`.
    """
    st.markdown("### Executive summary")
    st.markdown(
        f"""
<div style="background:#f8f9fb;border-left:4px solid #ce0058;padding:1rem 1.25rem;border-radius:6px;margin-bottom:1rem;">
  <div style="font-size:1.05rem;font-weight:600;color:#003865;margin-bottom:0.5rem;">{summary.headline}</div>
  <ul style="margin:0;padding-left:1.2rem;color:#334155;">
    {''.join(f'<li>{bullet}</li>' for bullet in summary.bullets)}
  </ul>
</div>
""",
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Lounges analysed", summary.outlet_count)
    c2.metric("Visit volume up", summary.outlets_with_visit_increase)
    c3.metric("Quadrant changes", summary.outlets_with_quadrant_change)
    c4.metric("Pre capacity risk", summary.pre_capacity_risk_count)
    c5.metric("Post capacity risk", summary.post_capacity_risk_count)


def main() -> None:
    """
    Run the Streamlit capacity intervention impact dashboard.

    Loads analysis outputs, renders the executive summary, and displays tabbed
    portfolio and outlet-level visualisations.
    """
    dashboard_config = load_dashboard_config()
    st.set_page_config(
        page_title=dashboard_config.get("title", "Capacity Intervention Impact"),
        page_icon="📊",
        layout="wide",
    )

    st.markdown(
        f"""
<style>
  .main-title {{
    font-size: 2rem;
    font-weight: 700;
    color: #ce0058;
    margin-bottom: 0.25rem;
  }}
  .main-subtitle {{
    color: #003865;
    margin-bottom: 1.25rem;
  }}
</style>
<div class="main-title">{dashboard_config.get("title", "Capacity Intervention Impact")}</div>
<div class="main-subtitle">{dashboard_config.get("subtitle", "Pre- vs post-intervention lounge performance")}</div>
""",
        unsafe_allow_html=True,
    )

    config_path = PROJECT_ROOT / dashboard_config.get("paths", {}).get(
        "analysis_config", "config/analysis.yaml"
    )
    default_metrics = dashboard_config.get("default_metrics", list(TRACKABLE_METRICS))

    with st.sidebar:
        st.header("Controls")
        data_source = st.radio(
            "Data source",
            ["Saved CSV outputs", "Refresh from Snowflake"],
            index=0,
        )
        selected_metrics = st.multiselect(
            "Metrics to compare",
            options=list(TRACKABLE_METRICS),
            default=[metric for metric in default_metrics if metric in TRACKABLE_METRICS],
            format_func=metric_label,
        )
        if not selected_metrics:
            selected_metrics = list(TRACKABLE_METRICS)

    try:
        if data_source == "Refresh from Snowflake":
            period_metrics, impact = cached_live_results(str(config_path))
        else:
            period_metrics, impact = cached_saved_results(str(config_path))
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()
    except Exception as exc:
        st.error(f"Failed to load analysis results: {exc}")
        st.stop()

    analysis_config = load_analysis_config(config_path)
    quadrant_plot_kwargs = {
        "high_utilisation_threshold": analysis_config.metrics.high_utilisation_threshold,
        "high_traffic_threshold": analysis_config.metrics.high_traffic_threshold,
    }

    summary = build_executive_summary(impact)
    render_executive_summary(summary)

    outlet_options = sorted(impact["outlet_code"].astype(str).unique().tolist())
    selected_outlets = st.multiselect(
        "Filter outlets",
        options=outlet_options,
        default=outlet_options,
    )
    filtered = impact[impact["outlet_code"].astype(str).isin(selected_outlets)].copy()
    if filtered.empty:
        st.warning("No outlets selected.")
        st.stop()

    tab_overview, tab_metrics, tab_quadrants, tab_outlet, tab_detail = st.tabs(
        ["Overview", "Metric changes", "Quadrants", "Outlet view", "Detail table"]
    )

    with tab_overview:
        left, right = st.columns([1.2, 1])
        with left:
            st.plotly_chart(
                metric_heatmap(filtered, tuple(selected_metrics)),
                use_container_width=True,
                key="overview_metric_heatmap",
            )
        with right:
            st.plotly_chart(
                quadrant_transition_chart(filtered, **quadrant_plot_kwargs),
                use_container_width=True,
                key="overview_quadrant_transition",
            )
        primary_metric = selected_metrics[0]
        st.plotly_chart(
            pre_post_grouped_bar(filtered, primary_metric),
            use_container_width=True,
            key=f"overview_pre_post_{primary_metric}",
        )

    with tab_metrics:
        metric_choice = st.selectbox(
            "Focus metric",
            options=selected_metrics,
            format_func=metric_label,
        )
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                pre_post_grouped_bar(filtered, metric_choice),
                use_container_width=True,
                key=f"metrics_pre_post_{metric_choice}",
            )
        with col2:
            st.plotly_chart(
                delta_bar_chart(filtered, metric_choice),
                use_container_width=True,
                key=f"metrics_delta_{metric_choice}",
            )
        if len(selected_outlets) == 1:
            st.plotly_chart(
                outlet_metric_radar(filtered, selected_outlets[0], tuple(selected_metrics)),
                use_container_width=True,
                key=f"metrics_radar_{selected_outlets[0]}",
            )

    with tab_quadrants:
        quadrant_cols = [
            "outlet_code",
            "pre_quadrant_label",
            "post_quadrant_label",
            "quadrant_transition",
            "quadrant_changed",
            "pre_peak_pp_utilisation_rate",
            "post_peak_pp_utilisation_rate",
            "pre_airport_traffic_peak",
            "post_airport_traffic_peak",
        ]
        quadrant_view = filtered[quadrant_cols].rename(
            columns={
                "outlet_code": "Outlet",
                "pre_quadrant_label": "Pre quadrant",
                "post_quadrant_label": "Post quadrant",
                "quadrant_transition": "Transition",
                "quadrant_changed": "Changed",
                "pre_peak_pp_utilisation_rate": "Pre peak util",
                "post_peak_pp_utilisation_rate": "Post peak util",
                "pre_airport_traffic_peak": "Pre traffic peak",
                "post_airport_traffic_peak": "Post traffic peak",
            }
        )
        st.dataframe(quadrant_view, use_container_width=True, hide_index=True)
        st.plotly_chart(
            quadrant_transition_chart(filtered, **quadrant_plot_kwargs),
            use_container_width=True,
            key="quadrants_transition",
        )

    with tab_outlet:
        outlet_choice = st.selectbox(
            "Outlet",
            options=outlet_options if outlet_options else selected_outlets,
            key="outlet_view_select",
        )
        lounge = lounge_for_outlet(analysis_config, outlet_choice)
        if lounge is None:
            st.warning(f"No configured intervention periods for {outlet_choice}.")
        else:
            refresh_visits = data_source == "Refresh from Snowflake"
            try:
                visits, _flights = cached_raw_inputs(str(config_path), refresh_visits)
            except Exception as exc:
                st.error(
                    "Could not load visit extracts for outlet time-series plots. "
                    f"Re-run the CLI to cache `output/visits_extract.csv`, or refresh from Snowflake. ({exc})"
                )
                visits = pd.DataFrame()

            if not visits.empty:
                slots = build_outlet_slot_series(
                    visits,
                    lounge,
                    analysis_config.metrics,
                )
                daily_visits = daily_visit_volume_series(slots)
                intervention = intervention_timestamp(lounge)
                outlet_row = filtered[filtered["outlet_code"].astype(str).eq(outlet_choice)]
                if not outlet_row.empty:
                    row = outlet_row.iloc[0]
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Pre quadrant", row.get("pre_quadrant_label", "—"))
                    c2.metric("Post quadrant", row.get("post_quadrant_label", "—"))
                    c3.metric(
                        "Pre visit volume",
                        format_metric_value(row.get("pre_pp_visit_volume"), "pp_visit_volume"),
                    )
                    c4.metric(
                        "Post visit volume",
                        format_metric_value(row.get("post_pp_visit_volume"), "pp_visit_volume"),
                    )

                series_metric = st.selectbox(
                    "Utilisation time series",
                    options=list(OUTLET_SERIES_METRICS),
                    format_func=outlet_series_metric_label,
                    key="outlet_series_metric",
                )
                series = outlet_metric_timeseries(series_metric, slots)
                st.plotly_chart(
                    outlet_metric_timeseries_chart(
                        series,
                        metric_key=series_metric,
                        outlet_code=outlet_choice,
                        intervention_date=intervention,
                        utilisation_threshold=analysis_config.metrics.high_utilisation_threshold,
                    ),
                    use_container_width=True,
                    key=f"outlet_series_{outlet_choice}_{series_metric}",
                )

                left, right = st.columns(2)
                with left:
                    st.plotly_chart(
                        daily_visit_volume_timeseries_chart(
                            daily_visits,
                            outlet_code=outlet_choice,
                            intervention_date=intervention,
                        ),
                        use_container_width=True,
                        key=f"outlet_daily_visits_ts_{outlet_choice}",
                    )
                with right:
                    st.plotly_chart(
                        daily_visit_volume_distribution_chart(
                            daily_visits,
                            outlet_code=outlet_choice,
                        ),
                        use_container_width=True,
                        key=f"outlet_daily_visits_dist_{outlet_choice}",
                    )

                with st.expander("Daily visit volume table"):
                    display_daily = daily_visits.copy()
                    display_daily["date"] = pd.to_datetime(display_daily["date"]).dt.date
                    st.dataframe(display_daily, use_container_width=True, hide_index=True)

    with tab_detail:
        st.dataframe(styled_impact_table(filtered), use_container_width=True, hide_index=True)
        with st.expander("Period-level metrics"):
            period_view = period_metrics[
                period_metrics["outlet_code"].astype(str).isin(selected_outlets)
            ].copy()
            st.dataframe(period_view, use_container_width=True, hide_index=True)

        csv_bytes = filtered.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download filtered impact CSV",
            data=csv_bytes,
            file_name="intervention_impact_filtered.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
