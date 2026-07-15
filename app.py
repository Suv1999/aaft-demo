"""
AAFT Executive Admissions & Marketing BI Dashboard
Flask + SQLite backend. All numbers are computed live from real uploaded data
(no hardcoded/fabricated figures) via /home/claude/aaft_dashboard/data/institute.db.

Run:
    pip install -r requirements.txt
    python etl.py        # (re)builds the SQLite DB from the source workbook
    python app.py
Then open http://127.0.0.1:5000
"""
import sqlite3
from pathlib import Path
from flask import Flask, jsonify, render_template, request

BASE = Path(__file__).parent
DB_PATH = BASE / "data" / "institute.db"

app = Flask(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_list(cur):
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------
FILTER_FIELDS = ["school", "state", "lead_source", "status", "team", "admission_manager"]


def build_where(args, table_alias=""):
    clauses, params = [], []
    prefix = f"{table_alias}." if table_alias else ""
    for f in FILTER_FIELDS:
        val = args.get(f)
        if val and val != "All":
            clauses.append(f"{prefix}{f} = ?")
            params.append(val)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------
def compute_payload(args):
    conn = get_conn()
    where, params = build_where(args)

    # ---- KPI headline numbers -------------------------------------------------
    total = conn.execute(f"SELECT COUNT(*) c FROM admissions_master{where}", params).fetchone()["c"]
    confirmed = conn.execute(
        f"SELECT COUNT(*) c FROM admissions_master{where}{' AND ' if where else ' WHERE '}status='Confirmed'",
        params,
    ).fetchone()["c"]
    dropped = conn.execute(
        f"SELECT COUNT(*) c FROM admissions_master{where}{' AND ' if where else ' WHERE '}status='Dropped'",
        params,
    ).fetchone()["c"]
    pipeline = total - confirmed - dropped
    conv_rate = round(100 * confirmed / total, 1) if total else 0
    drop_rate = round(100 * dropped / total, 1) if total else 0

    n_schools = conn.execute(f"SELECT COUNT(DISTINCT school) c FROM admissions_master{where}", params).fetchone()["c"]
    n_states = conn.execute(f"SELECT COUNT(DISTINCT state) c FROM admissions_master{where}", params).fetchone()["c"]
    n_sources = conn.execute(f"SELECT COUNT(DISTINCT lead_source) c FROM admissions_master{where}", params).fetchone()["c"]

    # Guard against a handful of Excel date-serial artifacts in the source sheet
    # (e.g. a stray -45835) by keeping only a plausible 0-730 day pipeline window.
    avg_days = conn.execute(
        f"""SELECT AVG(days_in_pipeline) a FROM admissions_master{where}
            {' AND ' if where else ' WHERE '}days_in_pipeline BETWEEN 0 AND 730""",
        params,
    ).fetchone()["a"]
    avg_days = round(avg_days, 1) if avg_days is not None else None

    # ---- By school --------------------------------------------------------
    by_school = rows_to_list(conn.execute(
        f"""SELECT school,
                   COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed,
                   SUM(CASE WHEN status='Dropped' THEN 1 ELSE 0 END) dropped
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}school IS NOT NULL
            GROUP BY school ORDER BY total DESC""",
        params,
    ))
    for r in by_school:
        r["conv_rate"] = round(100 * r["confirmed"] / r["total"], 1) if r["total"] else 0
        r["pct_of_total"] = round(100 * r["total"] / total, 1) if total else 0

    # ---- By status (funnel) ------------------------------------------------
    by_status = rows_to_list(conn.execute(
        f"""SELECT COALESCE(status,'In Pipeline') status, COUNT(*) total
            FROM admissions_master{where}
            GROUP BY COALESCE(status,'In Pipeline') ORDER BY total DESC""",
        params,
    ))

    # ---- By lead source (with conversion) ----------------------------------
    by_source = rows_to_list(conn.execute(
        f"""SELECT lead_source,
                   COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}lead_source IS NOT NULL
            GROUP BY lead_source ORDER BY total DESC""",
        params,
    ))
    for r in by_source:
        r["conv_rate"] = round(100 * r["confirmed"] / r["total"], 1) if r["total"] else 0

    # ---- By state (for geo module) ------------------------------------------
    by_state = rows_to_list(conn.execute(
        f"""SELECT state, COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed,
                   SUM(CASE WHEN status='Dropped' THEN 1 ELSE 0 END) dropped
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}state IS NOT NULL
            GROUP BY state ORDER BY total DESC""",
        params,
    ))

    # ---- By team / counselor performance ------------------------------------
    by_team = rows_to_list(conn.execute(
        f"""SELECT team,
                   COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed,
                   SUM(CASE WHEN status='Dropped' THEN 1 ELSE 0 END) dropped
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}team IS NOT NULL
            GROUP BY team ORDER BY total DESC""",
        params,
    ))
    for r in by_team:
        r["conv_rate"] = round(100 * r["confirmed"] / r["total"], 1) if r["total"] else 0

    by_manager = rows_to_list(conn.execute(
        f"""SELECT admission_manager,
                   COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed,
                   SUM(CASE WHEN status='Dropped' THEN 1 ELSE 0 END) dropped
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}admission_manager IS NOT NULL
            GROUP BY admission_manager ORDER BY total DESC LIMIT 10""",
        params,
    ))
    for r in by_manager:
        r["conv_rate"] = round(100 * r["confirmed"] / r["total"], 1) if r["total"] else 0

    # ---- Monthly trend -------------------------------------------------------
    monthly = rows_to_list(conn.execute(
        f"""SELECT reg_month, COUNT(*) total,
                   SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) confirmed
            FROM admissions_master{where}{' AND ' if where else ' WHERE '}reg_month IS NOT NULL
            GROUP BY reg_month ORDER BY MIN(registration_date)""",
        params,
    ))

    # ---- Drop reasons (from the detail table - richer reason text) -----------
    dwhere, dparams = build_where(args)
    drop_reasons = rows_to_list(conn.execute(
        f"""SELECT reason, COUNT(*) total FROM admissions_detail
            {dwhere}{' AND ' if dwhere else ' WHERE '}reason IS NOT NULL
            GROUP BY reason ORDER BY total DESC LIMIT 10""",
        dparams,
    ))

    avg_tat = conn.execute(
        f"""SELECT AVG(tat_days) a FROM admissions_detail
            {dwhere}{' AND ' if dwhere else ' WHERE '}tat_days IS NOT NULL AND tat_days > -365 AND tat_days < 365""",
        dparams,
    ).fetchone()["a"]
    avg_tat = round(avg_tat, 1) if avg_tat is not None else None

    conn.close()

    payload = {
        "kpis": {
            "total": total,
            "confirmed": confirmed,
            "dropped": dropped,
            "pipeline": pipeline,
            "conv_rate": conv_rate,
            "drop_rate": drop_rate,
            "n_schools": n_schools,
            "n_states": n_states,
            "n_sources": n_sources,
            "avg_days_in_pipeline": avg_days,
            "avg_tat_days": avg_tat,
        },
        "by_school": by_school,
        "by_status": by_status,
        "by_source": by_source,
        "by_state": by_state,
        "by_team": by_team,
        "by_manager": by_manager,
        "monthly": monthly,
        "drop_reasons": drop_reasons,
        "filters_applied": {f: args.get(f) for f in FILTER_FIELDS if args.get(f)},
    }
    payload["health_score"] = compute_health_score(payload)
    payload["alerts"] = compute_alerts(payload)
    payload["insights"] = compute_insights(payload)
    return payload


# ---------------------------------------------------------------------------
# Executive Health Score  (0-100, computed only from real numbers above)
# ---------------------------------------------------------------------------
def compute_health_score(p):
    k = p["kpis"]

    def clamp(v):
        return max(0.0, min(100.0, v))

    conv = clamp(k["conv_rate"])                                   # weight 40
    diversification = clamp(k["n_schools"] * 8)                     # weight 20
    geo_reach = clamp(k["n_states"] * 6)                            # weight 15
    source_mix = clamp(k["n_sources"] * 8)                          # weight 15
    days = k["avg_days_in_pipeline"]
    speed = 100.0 if not days else clamp(100 - days * 0.5)          # weight 10

    score = round(
        conv * 0.40 + diversification * 0.20 + geo_reach * 0.15 + source_mix * 0.15 + speed * 0.10, 0
    )
    score = max(0, min(100, score))
    contributors = [
        {"label": "Conversion Rate", "value": conv, "weight": 40},
        {"label": "School Diversification", "value": diversification, "weight": 20},
        {"label": "Geographic Reach", "value": geo_reach, "weight": 15},
        {"label": "Lead Source Mix", "value": source_mix, "weight": 15},
        {"label": "Pipeline Speed", "value": round(speed, 0), "weight": 10},
    ]
    return {"score": int(score), "contributors": contributors}


# ---------------------------------------------------------------------------
# Smart alerts - generated only from thresholds against real aggregates
# ---------------------------------------------------------------------------
def compute_alerts(p):
    alerts = []
    k = p["kpis"]
    if k["drop_rate"] >= 15:
        alerts.append({
            "severity": "high", "title": f"Drop rate at {k['drop_rate']}%",
            "detail": "More than 1 in 7 registered leads is being lost before confirmation.",
            "action": "Review counselling follow-up cadence for at-risk leads.",
        })
    if p["by_school"]:
        worst = max(p["by_school"], key=lambda r: (r["total"] - r["confirmed"] - r.get("dropped", 0) >= 0, 100 - r["conv_rate"]))
        low_conv = [r for r in p["by_school"] if r["total"] >= 3 and r["conv_rate"] < 60]
        if low_conv:
            worst2 = min(low_conv, key=lambda r: r["conv_rate"])
            alerts.append({
                "severity": "medium",
                "title": f"{worst2['school']} converting below 60%",
                "detail": f"Conversion rate is {worst2['conv_rate']}% across {worst2['total']} leads.",
                "action": "Audit counselling script and offer timelines for this school.",
            })
    if p["by_source"]:
        big_weak = [r for r in p["by_source"] if r["total"] >= 5 and r["conv_rate"] < 50]
        if big_weak:
            w = min(big_weak, key=lambda r: r["conv_rate"])
            alerts.append({
                "severity": "medium",
                "title": f"Lead source '{w['lead_source']}' underperforming",
                "detail": f"Only {w['conv_rate']}% of {w['total']} leads from this source convert.",
                "action": "Reassess marketing spend allocation to this channel.",
            })
    if k["n_schools"] and p["by_school"]:
        top = p["by_school"][0]
        if top["pct_of_total"] >= 30:
            alerts.append({
                "severity": "low",
                "title": f"{top['school']} drives {top['pct_of_total']}% of volume",
                "detail": "Admissions are concentrated in a single school.",
                "action": "Diversify marketing spend to reduce single-programme dependency.",
            })
    if not alerts:
        alerts.append({
            "severity": "low", "title": "No critical risks detected",
            "detail": "All tracked metrics are within healthy thresholds for the current filter.",
            "action": "Continue monitoring weekly.",
        })
    return alerts


# ---------------------------------------------------------------------------
# Executive narrative text per chart - built only from the numbers computed above
# ---------------------------------------------------------------------------
def compute_insights(p):
    k = p["kpis"]
    insights = {}

    if p["by_school"]:
        top = p["by_school"][0]
        insights["by_school"] = {
            "question": "Which school contributes the most admissions volume?",
            "observation": f"{top['school']} leads with {top['total']} leads ({top['pct_of_total']}% of total), converting at {top['conv_rate']}%.",
            "insight": "Volume leadership does not always mean the best conversion — compare the conversion-rate column across schools before allocating more budget.",
            "recommendation": f"Protect counselling capacity for {top['school']} while checking whether lower-volume, higher-conversion schools deserve more lead flow.",
            "impact": "Rebalancing lead flow toward higher-converting schools can lift overall confirmations without spending more on marketing.",
        }

    if p["by_source"]:
        best = max(p["by_source"], key=lambda r: r["conv_rate"] if r["total"] >= 3 else -1)
        biggest = p["by_source"][0]
        insights["by_source"] = {
            "question": "Which lead source is most efficient?",
            "observation": f"'{biggest['lead_source']}' brings the most leads ({biggest['total']}), while '{best['lead_source']}' converts best at {best['conv_rate']}% (min. 3 leads).",
            "insight": "The highest-volume channel and the highest-converting channel are not the same — a pure volume-based budget misses efficiency.",
            "recommendation": f"Test shifting incremental spend toward '{best['lead_source']}' while keeping '{biggest['lead_source']}' as the volume engine.",
            "impact": "Even a 5-point conversion improvement on the largest channel would add several confirmed admissions at no extra spend.",
        }

    if k["total"]:
        insights["funnel"] = {
            "question": "How healthy is the admissions funnel overall?",
            "observation": f"Of {k['total']} tracked leads, {k['confirmed']} are Confirmed ({k['conv_rate']}%), {k['dropped']} Dropped ({k['drop_rate']}%), {k['pipeline']} still in pipeline.",
            "insight": "A double-digit drop rate combined with leads still sitting in pipeline signals follow-up delay risk, not just lead-quality risk.",
            "recommendation": "Prioritise same-week follow-up for leads that have been in pipeline the longest.",
            "impact": "Cutting the drop rate by a few points converts pipeline leakage directly into enrolment revenue.",
        }

    if p["by_state"]:
        top_state = p["by_state"][0]
        insights["by_state"] = {
            "question": "Where is admissions demand geographically concentrated?",
            "observation": f"{top_state['state']} contributes the most leads ({top_state['total']}), across {k['n_states']} states tracked overall.",
            "insight": "Heavy geographic concentration increases exposure to local demand shocks (economy, competing institutes, local events).",
            "recommendation": "Run a small paid-lead test in 2-3 underrepresented states to diversify the geographic base.",
            "impact": "Geographic diversification reduces revenue volatility tied to any single region.",
        }

    if p["drop_reasons"]:
        top_reason = p["drop_reasons"][0]
        insights["drop_reasons"] = {
            "question": "Why are students dropping out of the admissions process?",
            "observation": f"'{top_reason['reason']}' is the most common reason ({top_reason['total']} cases) among tracked drop-outs.",
            "insight": "If a financial reason dominates, it points to a pricing/financing-options gap rather than a counselling-quality problem.",
            "recommendation": "Promote EMI/loan-partner options earlier in the counselling conversation for at-risk profiles.",
            "impact": "Addressing the top drop reason directly targets the largest lever for recovering lost admissions.",
        }

    return insights


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/overview")
def api_overview():
    return jsonify(compute_payload(request.args))


@app.route("/api/filter-options")
def api_filter_options():
    conn = get_conn()
    out = {}
    for f in FILTER_FIELDS:
        rows = conn.execute(
            f"SELECT DISTINCT {f} v FROM admissions_master WHERE {f} IS NOT NULL ORDER BY {f}"
        ).fetchall()
        out[f] = [r["v"] for r in rows]
    conn.close()
    return jsonify(out)


if __name__ == "__main__":
    if not DB_PATH.exists():
        raise SystemExit("Database not found. Run `python etl.py` first.")
    app.run(debug=True, port=5000)
