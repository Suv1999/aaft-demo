# AAFT Executive Admissions & Marketing Command Center
# https://aaft-demo.onrender.com/

A Flask + SQLite executive BI dashboard built from your real uploaded workbook
(`Data_for_Assignment.xlsx`). No numbers on this dashboard are fabricated —
every KPI, chart, insight sentence and alert is computed live from the SQLite
database at query time.

## What data is used, and why

The workbook has 13 sheets. Two were chosen as the analytical source because
they are the only sheets with **complete, real, non-blank records**:

| Table (SQLite)      | Source sheet(s)      | Rows | Used for |
|---|---|---|---|
| `admissions_master`  | `Master file`         | 98   | Primary funnel: lead source → school → course → Confirmed/Dropped, geography, team & counselor performance, pipeline aging |
| `admissions_detail`  | `Diploma` + `Degree`  | 582  | Drop-reason analysis, turnaround-time (TAT), counselling detail |

Other sheets (`Dashboard`, `Sheet19`, `Target`, `aging Report`, etc.) are raw
pivot/staging tabs in the original file with no clean tabular structure and
were not used, to avoid guessing at ambiguous or empty fields. `Assignment.xlsx`
is a CRM lead export where almost every fee/payment column is empty (0 of 110
rows populated) — it wasn't reliable enough to build KPIs on, so it was left out.

A handful of Excel date-serial artifacts in the `Days`/`TAT` columns (e.g. a
stray `-45835`) are filtered out of averages — see `app.py` comments.

## Run it

```bash
cd aaft_dashboard
pip install -r requirements.txt

python etl.py     # builds data/institute.db from the source workbook
python app.py     # starts the dashboard at http://127.0.0.1:5000
```

If you move or update the source workbook, just point `SRC` in `etl.py` at
the new file and re-run `python etl.py` — the dashboard reads live from
`data/institute.db`, so no other code changes are needed.

## What's in the dashboard

- **KPI row** — total leads, confirmed, dropped, pipeline, source diversity, pipeline speed
- **Admissions by School** — stacked bar (Confirmed/Dropped/Other), click a bar to cross-filter everything else
- **Funnel Status** — donut of Confirmed/Dropped/Pipeline
- **Lead Source Performance** — volume bars + conversion-rate line, click to filter
- **Geographic Demand map** — India bubble map (state-level), color = conversion rate, size = volume, click to filter
- **Team & Admission Manager performance tables** — click a row to filter
- **Top Drop Reasons** — from the detail table's real `Reason` field
- **Executive Business Health Score** — weighted composite (conversion 40%, school diversification 20%, geographic reach 15%, lead-source mix 15%, pipeline speed 10%), recalculated per filter
- **Smart Business Alerts** — threshold-based (drop rate ≥ 15%, any school converting < 60% on ≥3 leads, any lead source converting < 50% on ≥5 leads, single-school concentration ≥ 30%)
- **Executive insight panels** — Business Question → Observation → Insight → Recommendation → Impact, generated from the *currently filtered* data, under each chart
- **Presentation Mode** (top-right button, or press it and use ← → / Esc) — full-screen slide view built from the live KPIs/insights, one idea per screen

## Extending it

- Add more filters by adding fields to `FILTER_FIELDS` in `app.py` (they must
  exist as columns in `admissions_master`).
- To wire in real fee/revenue figures once your CRM export has them populated,
  add a `revenue` table in `etl.py` and a matching card in `dashboard.html` /
  `dashboard.js` — the insight-panel and alert patterns are reusable.
