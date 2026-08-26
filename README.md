# Capacity intervention impact analysis

Modular, configuration-driven analysis of capacity-constrained lounges before
and after an intervention. It can query Snowflake directly or analyse saved CSV
extracts, and writes both period metrics and paired changes.

## Metrics

The calculations follow `MLP-Outlet-Capacity-UI`:

- **PP visit volume**: sum of `TOTAL_VISITS`; `avg_monthly_visits` reproduces
  the source dashboard's mean of calendar-month totals, and
  `pp_visits_per_day` keeps periods of unequal length comparable.
- **Estimated PP occupancy**: rolling PP arrivals over the configured dwell
  time (60 minutes by default).
- **Peak PP utilisation**: peak estimated occupancy divided by
  `NUMBER_OF_SEATS * max_allowed_seat_proportion`.
- **Estimated PP market share**: mean of weekly peak PP utilisation. This keeps
  the source dashboard's field name but is a utilisation proxy, not conventional
  passenger market share.
- **Airport traffic peak**: maximum departures in the configured forward window
  (three hours by default), using actual 15-minute departure data.
- **Capacity quadrant**: the source dashboard's inclusive utilisation/traffic
  threshold rules, with labels Capacity risk, Opportunity gap, Usage anomaly,
  Capacity/Opportunity gap, Usage anomaly, and Low priority.

One traffic threshold is applied to both periods so a quadrant transition is not
caused solely by moving the decision boundary. Use a configured fixed value or
derive it from pre-period airport peaks.

## Structure

- `capacity_impact/config.py`: typed, validated YAML configuration
- `capacity_impact/metrics.py`: occupancy, utilisation, market-share proxy,
  traffic and quadrant calculations
- `capacity_impact/analysis.py`: paired pre/post orchestration and deltas
- `capacity_impact/data.py`: safe SQL rendering and Snowflake extraction
- `capacity_impact/snowflake_manager.py`: local user-profile SSO or AWS-secret
  non-human key-pair authentication
- `SQL/`: visit and actual-flight extraction templates
- `config/analysis.yaml`: lounge periods, capacity overrides and thresholds
- `tests/`: unit and integration-style tests with synthetic data

## Run

```bash
python -m pip install -e ".[test]"
pytest
capacity-impact --config config/analysis.yaml
```

Snowflake authentication is selected in `config/analysis.yaml`:

- `is_run_locally: true` uses browser SSO with `SNOWFLAKE_USER` and the
  configured warehouse (local user profile).
- `is_run_locally: false` loads the non-human user from AWS Secrets Manager
  (`secret_name`) and connects with a private key. Set `ENVIRONMENT` to force
  this path even if `is_run_locally` is true.

To run against saved extracts:

```bash
capacity-impact \
  --config config/analysis.yaml \
  --visits-csv data/visits.csv \
  --flights-csv data/flights.csv
```

The command writes:

- `output/period_metrics.csv`: one row per lounge and period
- `output/intervention_impact.csv`: pre/post values, absolute and percentage
  changes, `quadrant_changed`, and `quadrant_transition`
- `output/visits_extract.csv` and `output/flights_extract.csv`: cached raw
  extracts used by the dashboard outlet view

If seat capacity changed during the intervention, set
`pre_number_of_seats` and `post_number_of_seats` for that lounge. Without
overrides, the latest Partnership seat count is used for both periods.

## Dashboard

Interactive Streamlit dashboard for pre/post intervention comparison:

```bash
python -m pip install -e ".[dashboard]"
streamlit run dashboards/app.py
```

By default the dashboard reads saved CSV outputs from `output/`. Use the sidebar
to refresh from Snowflake (requires the same auth as the CLI). Tabs include an
executive summary, metric heatmaps, pre/post bar charts, quadrant transitions,
outlet-level utilisation time series and daily visit distributions, and a
downloadable detail table.

### Static HTML export

Generate a standalone interactive HTML report (no Streamlit server required):

```bash
python scripts/export_dashboard_html.py
python scripts/export_dashboard_html.py --output reports/my_report.html --open
```

The export embeds the same Plotly charts and searchable tables as the dashboard.
Use `--plotly-js cdn` for a smaller file, or `--refresh-from-snowflake` to
rebuild from live extracts. Outlet time-series panels require
`output/visits_extract.csv` unless refreshing from Snowflake.
