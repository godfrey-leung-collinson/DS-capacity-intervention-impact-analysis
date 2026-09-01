"""Build standalone HTML reports from dashboard figures."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from dashboards.report import (
    build_outlet_figures,
    build_portfolio_figures,
    load_report_context,
    quadrant_table,
    styled_impact_table,
)
from dashboards.metrics import format_metric_value, metric_label

PLOTLY_CONFIG = {
    "responsive": True,
    "displaylogo": False,
    "scrollZoom": True,
}


def _figure_fragment(figure: go.Figure, *, include_plotlyjs: str | bool) -> str:
    figure.update_layout(width=None, autosize=True)
    return pio.to_html(
        figure,
        full_html=False,
        include_plotlyjs=include_plotlyjs,
        config=PLOTLY_CONFIG,
    )


def _card(label: str, value: Any) -> str:
    return (
        '<div class="metric-card">'
        f'<div class="card-label">{html.escape(label)}</div>'
        f'<div class="card-value">{html.escape(str(value))}</div>'
        "</div>"
    )


def _metric_grid(items: list[tuple[str, Any]]) -> str:
    return '<div class="metric-grid">' + "".join(_card(label, value) for label, value in items) + "</div>"


def _table(frame: pd.DataFrame, table_id: str, title: str) -> str:
    table_html = frame.to_html(
        index=False,
        border=0,
        classes="report-table",
        table_id=table_id,
        escape=True,
        na_rep="—",
    )
    return (
        f'<details class="table-panel" open><summary>{html.escape(title)}</summary>'
        f'<input class="table-search" type="search" '
        f'oninput="filterTable(\'{table_id}\', this.value)" '
        f'placeholder="Filter rows…">'
        f"{table_html}</details>"
    )


def _section(title: str, body: str, *, section_id: str | None = None) -> str:
    section_attr = f' id="{section_id}"' if section_id else ""
    return f'<section class="report-section"{section_attr}><h2>{html.escape(title)}</h2>{body}</section>'


def _chart_block(title: str, fragment: str) -> str:
    return (
        f'<div class="chart-block"><h3>{html.escape(title)}</h3>'
        f'<div class="chart-shell">{fragment}</div></div>'
    )


def _tab_button(tab_id: str, label: str, *, active: bool = False) -> str:
    active_class = " active" if active else ""
    return (
        f'<button type="button" class="tab-button{active_class}" '
        f'data-tab="{html.escape(tab_id)}" onclick="showTab(\'{tab_id}\')">'
        f"{html.escape(label)}</button>"
    )


def _quadrant_measure_control(control_id: str) -> str:
    return (
        f'<div class="control-row">'
        f'<label for="{control_id}">Quadrant measure '
        f'<select id="{control_id}" onchange="selectQuadrantMeasure(\'{control_id}\', this.value)">'
        f'<option value="peak" selected>Peak</option>'
        f'<option value="average">Average</option>'
        f"</select></label></div>"
    )


def _quadrant_chart_panels(
    peak_fragment: str,
    average_fragment: str,
    *,
    panel_prefix: str,
) -> str:
    return (
        '<div class="chart-column">'
        + _quadrant_measure_control(f"{panel_prefix}-quadrant-measure")
        + f'<div class="quadrant-chart-panel" data-quadrant-group="{panel_prefix}" data-measure="peak">'
        + f'{_chart_block("Quadrant movement (peak)", peak_fragment)}'
        + "</div>"
        + f'<div class="quadrant-chart-panel" data-quadrant-group="{panel_prefix}" data-measure="average" hidden>'
        + f'{_chart_block("Quadrant movement (average)", average_fragment)}'
        + "</div>"
        + "</div>"
    )


def build_html_report(
    output_path: Path,
    *,
    analysis_config_path: Path,
    dashboard_config_path: Path | None = None,
    plotly_js: str = "inline",
    refresh_from_snowflake: bool = False,
    outlet_filter: tuple[str, ...] | None = None,
) -> Path:
    context = load_report_context(
        analysis_config_path=analysis_config_path,
        dashboard_config_path=dashboard_config_path,
        refresh_from_snowflake=refresh_from_snowflake,
        outlet_filter=outlet_filter,
    )
    if context.impact.empty:
        raise ValueError("No intervention impact rows available to export.")

    dashboard_config = context.dashboard_config
    title = dashboard_config.get("title", "Capacity Intervention Impact")
    subtitle = dashboard_config.get("subtitle", "Pre- vs post-intervention lounge performance")
    summary = context.summary
    portfolio = build_portfolio_figures(context)

    unavailable_notice = ""
    if context.unavailable_metrics:
        labels = ", ".join(metric_label(metric) for metric in context.unavailable_metrics)
        unavailable_notice = (
            f'<p class="notice">{html.escape(labels)} unavailable in saved results. '
            "Re-run <code>python -m capacity_impact.cli</code> or export with "
            "<code>--refresh-from-snowflake</code>.</p>"
        )

    include_first: str | bool = "inline" if plotly_js == "inline" else "cdn"
    figure_count = 0

    def next_figure(figure: go.Figure) -> str:
        nonlocal figure_count
        fragment = _figure_fragment(
            figure,
            include_plotlyjs=include_first if figure_count == 0 else False,
        )
        figure_count += 1
        return fragment

    executive_bullets = "".join(f"<li>{html.escape(bullet)}</li>" for bullet in summary.bullets)
    executive_html = (
        '<div class="takeaway">'
        f'<div class="takeaway-headline">{html.escape(summary.headline)}</div>'
        f"<ul>{executive_bullets}</ul></div>"
        + _metric_grid(
            [
                ("Lounges analysed", summary.outlet_count),
                ("Visit volume up", summary.outlets_with_visit_increase),
                ("Quadrant changes", summary.outlets_with_quadrant_change),
                ("Pre capacity risk", summary.pre_capacity_risk_count),
                ("Post capacity risk", summary.post_capacity_risk_count),
            ]
        )
    )

    overview_html = (
        unavailable_notice
        + '<div class="chart-grid two-up">'
        + _chart_block("Percentage change heatmap", next_figure(portfolio["overview_heatmap"]))
        + _quadrant_chart_panels(
            next_figure(portfolio["overview_quadrant_peak"]),
            next_figure(portfolio["overview_quadrant_average"]),
            panel_prefix="overview",
        )
        + "</div>"
        + _chart_block(
            f'Pre/post comparison — {portfolio["overview_primary_metric_label"]}',
            next_figure(portfolio["overview_primary_bar"]),
        )
    )

    metric_sections: list[str] = []
    for metric_label_text, pre_post_fig, delta_fig in portfolio["metric_sections"]:
        metric_sections.append(
            f'<div class="metric-panel">'
            f"<h3>{html.escape(metric_label_text)}</h3>"
            f'<div class="chart-grid two-up">'
            f'{_chart_block("Pre vs post", next_figure(pre_post_fig))}'
            f'<div class="chart-block"><div class="chart-shell">{next_figure(delta_fig)}</div></div>'
            f"</div></div>"
        )
    metrics_html = "".join(metric_sections)

    quadrants_html = (
        _table(quadrant_table(context.impact), "quadrant-table", "Quadrant summary")
        + _quadrant_chart_panels(
            next_figure(portfolio["quadrants_scatter_peak"]),
            next_figure(portfolio["quadrants_scatter_average"]),
            panel_prefix="quadrants",
        )
    )

    outlet_options = sorted(context.impact["outlet_code"].astype(str).unique().tolist())
    outlet_panels: list[str] = []
    for index, outlet_code in enumerate(outlet_options):
        lounge = next(
            (item for item in context.analysis_config.lounges if item.outlet_code == outlet_code),
            None,
        )
        hidden = "" if index == 0 else " hidden"
        if lounge is None:
            outlet_panels.append(
                f'<div class="outlet-panel"{hidden} data-outlet="{html.escape(outlet_code)}">'
                f"<p>No configured intervention periods for {html.escape(outlet_code)}.</p></div>"
            )
            continue

        outlet_figures = build_outlet_figures(context, lounge)
        row = context.impact[context.impact["outlet_code"].astype(str).eq(outlet_code)]
        cards = ""
        if not row.empty:
            record = row.iloc[0]
            cards = _metric_grid(
                [
                    ("Pre quadrant", record.get("pre_quadrant_label", "—")),
                    ("Post quadrant", record.get("post_quadrant_label", "—")),
                    (
                        "Pre visit volume",
                        format_metric_value(
                            record.get("pre_pp_visit_volume"),
                            "pp_visit_volume",
                        ),
                    ),
                    (
                        "Post visit volume",
                        format_metric_value(
                            record.get("post_pp_visit_volume"),
                            "pp_visit_volume",
                        ),
                    ),
                    (
                        "Pre visit-to-flight ratio",
                        format_metric_value(
                            record.get("pre_visit_to_flight_ratio"),
                            "visit_to_flight_ratio",
                        ),
                    ),
                    (
                        "Post visit-to-flight ratio",
                        format_metric_value(
                            record.get("post_visit_to_flight_ratio"),
                            "visit_to_flight_ratio",
                        ),
                    ),
                ]
            )

        if outlet_figures is None:
            outlet_panels.append(
                f'<div class="outlet-panel"{hidden} data-outlet="{html.escape(outlet_code)}">'
                f"<h3>{html.escape(outlet_code)}</h3>{cards}"
                "<p class='caption'>Visit extracts unavailable. Re-run the CLI to write "
                "<code>output/visits_extract.csv</code> or export with "
                "<code>--refresh-from-snowflake</code>.</p></div>"
            )
            continue

        series_blocks = "".join(
            _chart_block(label, next_figure(figure))
            for label, figure in outlet_figures["series"]
        )
        daily_table = outlet_figures["daily_visits_table"].copy()
        daily_table["date"] = pd.to_datetime(daily_table["date"]).dt.date
        outlet_panels.append(
            f'<div class="outlet-panel"{hidden} data-outlet="{html.escape(outlet_code)}">'
            f"<h3>{html.escape(outlet_code)}</h3>{cards}"
            f"{series_blocks}"
            f'<div class="chart-grid two-up">'
            f'{_chart_block("Daily visit volume over time", next_figure(outlet_figures["daily_visits_ts"]))}'
            f'{_chart_block("Daily visit volume distribution", next_figure(outlet_figures["daily_visits_dist"]))}'
            f"</div>"
            f'{_table(daily_table, f"daily-visits-{outlet_code}", "Daily visit volume table")}'
            f"</div>"
        )

    outlet_options_html = "".join(
        f'<option value="{html.escape(code)}"{" selected" if index == 0 else ""}>'
        f"{html.escape(code)}</option>"
        for index, code in enumerate(outlet_options)
    )
    outlet_html = (
        '<div class="control-row">'
        '<label for="outlet-select">Outlet '
        f'<select id="outlet-select" onchange="selectOutlet(this.value)">{outlet_options_html}</select>'
        "</label></div>"
        + "".join(outlet_panels)
    )

    detail_html = (
        _table(styled_impact_table(context.impact), "impact-detail-table", "Intervention impact detail")
        + _table(
            context.period_metrics,
            "period-metrics-table",
            "Period-level metrics",
        )
    )

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    tab_bar = (
        _tab_button("overview", "Overview", active=True)
        + _tab_button("metrics", "Metric changes")
        + _tab_button("quadrants", "Quadrants")
        + _tab_button("outlet", "Outlet view")
        + _tab_button("detail", "Detail table")
    )
    body = f"""
    <header>
      <h1>{html.escape(title)}</h1>
      <p>{html.escape(subtitle)}</p>
      <p class="caption">Static interactive export generated {html.escape(generated_at)}.
      Charts retain hover, zoom, pan, legend toggles, and scroll zoom.</p>
    </header>

    {_section("Executive summary", executive_html, section_id="executive-summary")}

    <nav class="tab-bar">{tab_bar}</nav>

    <div id="tab-overview" class="tab-panel active">
      {_section("Overview", overview_html)}
    </div>
    <div id="tab-metrics" class="tab-panel">
      {_section("Metric changes", metrics_html)}
    </div>
    <div id="tab-quadrants" class="tab-panel">
      {_section("Quadrants", quadrants_html)}
    </div>
    <div id="tab-outlet" class="tab-panel">
      {_section("Outlet view", outlet_html)}
    </div>
    <div id="tab-detail" class="tab-panel">
      {_section("Detail table", detail_html)}
    </div>
    """

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root {{ --navy:#003865; --pink:#ce0058; --ink:#172033; --muted:#5f6b7a; --line:#d9e0e8; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f7fa; color:var(--ink); font:15px/1.5 Arial,sans-serif; }}
header {{ padding:24px 32px; color:white; background:linear-gradient(120deg,var(--navy),#15658c); }}
header h1 {{ margin:0 0 8px; font-size:30px; }}
header p {{ margin:0 0 6px; }}
.report-section {{ margin:20px 16px 0; padding:24px 32px; background:white; border:1px solid var(--line); border-radius:12px; }}
.report-section h2 {{ margin-top:0; color:var(--navy); }}
.report-section h3 {{ color:var(--navy); margin-bottom:10px; }}
.takeaway {{ margin-bottom:16px; padding:14px 16px; border-left:4px solid var(--pink); border-radius:6px; background:#f9eef3; }}
.takeaway-headline {{ font-size:1.05rem; font-weight:600; color:var(--navy); margin-bottom:8px; }}
.takeaway ul {{ margin:0; padding-left:1.2rem; color:#334155; }}
.metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; }}
.metric-card {{ min-height:84px; padding:14px; border:1px solid var(--line); border-radius:9px; background:#fbfcfe; }}
.card-label {{ color:var(--muted); font-size:12px; font-weight:bold; text-transform:uppercase; }}
.card-value {{ margin-top:7px; color:var(--navy); font-size:20px; font-weight:bold; }}
.caption {{ color:var(--muted); font-size:12px; }}
.notice {{ margin:0 0 16px; padding:12px 14px; border-left:4px solid #f59e0b; border-radius:6px; background:#fffbeb; color:#7c2d12; }}
.quadrant-chart-panel {{ width:100%; }}
.tab-bar {{ display:flex; flex-wrap:wrap; gap:8px; margin:20px 16px 0; }}
.tab-button {{ border:1px solid var(--line); background:white; color:var(--navy); border-radius:999px; padding:10px 16px; cursor:pointer; font-weight:bold; }}
.tab-button.active {{ background:var(--pink); border-color:var(--pink); color:white; }}
.tab-panel {{ display:none; }}
.tab-panel.active {{ display:block; }}
.chart-grid.two-up {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:16px; }}
.chart-column {{ display:flex; flex-direction:column; gap:8px; min-width:0; }}
.chart-block {{ margin-top:16px; }}
.chart-shell {{ width:100%; overflow:hidden; }}
.chart-shell .plotly-graph-div {{ width:100% !important; max-width:100%; }}
.metric-panel {{ margin-top:24px; padding-top:8px; border-top:1px solid var(--line); }}
.control-row {{ margin-bottom:16px; }}
.control-row label {{ color:var(--muted); font-size:13px; font-weight:bold; }}
.control-row select {{ display:block; min-width:220px; margin-top:6px; padding:8px; border:1px solid var(--line); border-radius:5px; }}
.table-panel {{ margin-top:16px; border:1px solid var(--line); border-radius:8px; padding:12px; }}
.table-panel summary {{ cursor:pointer; color:var(--navy); font-weight:bold; }}
.table-search {{ width:min(420px,100%); margin:12px 0; padding:8px; border:1px solid var(--line); border-radius:5px; }}
.report-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
.report-table th {{ position:sticky; top:0; cursor:pointer; background:var(--navy); color:white; }}
.report-table th,.report-table td {{ padding:7px; border:1px solid var(--line); text-align:left; }}
.report-table tr:nth-child(even) {{ background:#f7f9fb; }}
@media (max-width:900px) {{
  header {{ padding:18px; }}
  .report-section {{ margin:12px 8px 0; padding:18px; }}
}}
</style>
</head>
<body>{body}
<script>
function showTab(tabId) {{
  document.querySelectorAll('.tab-panel').forEach(panel => {{
    panel.classList.toggle('active', panel.id === 'tab-' + tabId);
  }});
  document.querySelectorAll('.tab-button').forEach(button => {{
    button.classList.toggle('active', button.dataset.tab === tabId);
  }});
  if (tabId === 'outlet') {{
    resizeVisiblePlots(document.querySelector('.outlet-panel:not([hidden])'));
  }} else {{
    resizeVisiblePlots(document.getElementById('tab-' + tabId));
  }}
}}
function selectQuadrantMeasure(controlId, measure) {{
  const group = controlId.startsWith('overview') ? 'overview' : 'quadrants';
  document.querySelectorAll(`.quadrant-chart-panel[data-quadrant-group="${{group}}"]`).forEach(panel => {{
    panel.hidden = panel.dataset.measure !== measure;
  }});
  resizeVisiblePlots(document.getElementById(`tab-${{group === 'overview' ? 'overview' : 'quadrants'}}`));
}}
function selectOutlet(outletCode) {{
  document.querySelectorAll('.outlet-panel').forEach(panel => {{
    panel.hidden = panel.dataset.outlet !== outletCode;
  }});
  resizeVisiblePlots(document.querySelector('.outlet-panel:not([hidden])'));
}}
function resizeVisiblePlots(container) {{
  if (!container || !window.Plotly) return;
  container.querySelectorAll('.plotly-graph-div').forEach(plot => {{
    requestAnimationFrame(() => Plotly.Plots.resize(plot));
  }});
}}
function filterTable(id, query) {{
  const q = query.toLowerCase();
  document.querySelectorAll('#' + id + ' tbody tr').forEach(row => {{
    row.hidden = !row.innerText.toLowerCase().includes(q);
  }});
}}
document.querySelectorAll('.report-table th').forEach(th => th.addEventListener('click', () => {{
  const table = th.closest('table');
  const body = table.tBodies[0];
  const index = th.cellIndex;
  const ascending = th.dataset.order !== 'asc';
  [...body.rows].sort((a, b) => {{
    const av = a.cells[index].innerText.trim();
    const bv = b.cells[index].innerText.trim();
    const an = Number(av.replace(/[%,$]/g, ''));
    const bn = Number(bv.replace(/[%,$]/g, ''));
    const comparison = Number.isNaN(an) || Number.isNaN(bn) ? av.localeCompare(bv) : an - bn;
    return ascending ? comparison : -comparison;
  }}).forEach(row => body.appendChild(row));
  th.dataset.order = ascending ? 'asc' : 'desc';
}}));
window.addEventListener('load', () => resizeVisiblePlots(document.getElementById('tab-overview')));
window.addEventListener('resize', () => {{
  const activePanel = document.querySelector('.tab-panel.active');
  if (activePanel) resizeVisiblePlots(activePanel);
}});
</script>
</body></html>"""

    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path
