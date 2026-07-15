// ============================================================================
// AAFT Executive Admissions Command Center — frontend logic
// All data is fetched live from /api/overview (SQLite-backed). No fabricated values.
// ============================================================================

const FILTER_FIELDS = ["school", "state", "lead_source", "status", "team"];
let currentFilters = {};
let charts = {};
let lastPayload = null;

const FIELD_LABEL = {
  school: "School", state: "State", lead_source: "Lead Source",
  status: "Status", team: "Team",
};

// Approx centroids for Indian states/UTs appearing in this dataset
const STATE_COORDS = {
  "Uttar Pradesh": [27.0, 80.5], "Delhi": [28.66, 77.1], "Haryana": [29.2, 76.3],
  "Punjab": [31.0, 75.5], "Bihar": [25.7, 85.6], "Maharashtra": [19.5, 75.7],
  "Madhya Pradesh": [23.6, 78.4], "Assam": [26.4, 92.9], "Andhra Pradesh": [15.9, 79.7],
  "Jharkhand": [23.6, 85.3], "West Bengal": [22.9, 87.8], "Karnataka": [15.3, 75.7],
  "Kerala": [10.4, 76.5], "Tamil Nadu": [11.1, 78.7], "Odisha": [20.5, 84.7],
  "Gujarat": [22.6, 71.6], "Rajasthan": [26.9, 73.8], "Uttarakhand": [30.1, 79.2],
  "Chhattisgarh": [21.3, 81.9], "Telangana": [17.9, 79.6], "Goa": [15.4, 74.1],
  "Himachal Pradesh": [31.9, 77.2], "Jammu and Kashmir": [33.8, 76.5],
};

const COLORS = { gold: "#e3ac47", coral: "#ef7161", teal: "#5fc8b8", violet: "#9d8bf0", muted: "#9ba1c9" };
Chart.defaults.color = "#c9cdea";
Chart.defaults.font.family = "Inter";
Chart.defaults.borderColor = "rgba(255,255,255,.06)";

function qs(obj) {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => { if (v) p.set(k, v); });
  return p.toString();
}

async function loadFilterOptions() {
  const res = await fetch("/api/filter-options");
  const data = await res.json();
  FILTER_FIELDS.forEach((f) => {
    const sel = document.getElementById("f_" + f);
    if (!sel) return;
    (data[f] || []).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v; opt.textContent = v;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", () => {
      if (sel.value) currentFilters[f] = sel.value; else delete currentFilters[f];
      refresh();
    });
  });
}

function setFilter(field, value) {
  if (currentFilters[field] === value) { delete currentFilters[field]; }
  else { currentFilters[field] = value; }
  document.getElementById("f_" + field).value = currentFilters[field] || "";
  refresh();
}

function renderBreadcrumb() {
  const el = document.getElementById("breadcrumb");
  const entries = Object.entries(currentFilters);
  if (!entries.length) { el.innerHTML = "<span>No filters applied — showing all real records</span>"; return; }
  el.innerHTML = "<span>Filters:</span>" + entries.map(([k, v]) =>
    `<span class="chip">${FIELD_LABEL[k] || k}: ${v}<button onclick="setFilter('${k}', '${v.replace(/'/g, "\\'")}')">✕</button></span>`
  ).join("");
}

async function refresh() {
  renderBreadcrumb();
  const res = await fetch("/api/overview?" + qs(currentFilters));
  const data = await res.json();
  lastPayload = data;
  renderKpis(data.kpis);
  renderSchoolChart(data.by_school);
  renderStatusChart(data.by_status);
  renderSourceChart(data.by_source);
  renderMap(data.by_state);
  renderTable("tblTeam", data.by_team, "team");
  renderTable("tblManager", data.by_manager, "admission_manager");
  renderDropReasons(data.drop_reasons);
  renderTrend(data.monthly);
  renderHealth(data.health_score);
  renderAlerts(data.alerts);
  renderInsights(data.insights);
}

// ---------------------------------------------------------------------------
function renderKpis(k) {
  const cards = [
    { label: "Total Leads Tracked", value: k.total, sub: `${k.n_schools} schools · ${k.n_states} states` },
    { label: "Confirmed", value: k.confirmed, sub: `${k.conv_rate}% conversion`, cls: "" },
    { label: "Dropped", value: k.dropped, sub: `${k.drop_rate}% drop rate`, cls: k.drop_rate >= 15 ? "bad" : "" },
    { label: "In Pipeline", value: k.pipeline, sub: "awaiting outcome" },
    { label: "Lead Sources Active", value: k.n_sources, sub: "channel diversity" },
    { label: "Avg. Days in Pipeline", value: k.avg_days_in_pipeline ?? "–", sub: "speed to decision" },
  ];
  document.getElementById("kpiRow").innerHTML = cards.map(c => `
    <div class="kpi">
      <div class="label">${c.label}</div>
      <div class="value">${c.value}</div>
      <div class="sub ${c.cls || ""}">${c.sub}</div>
    </div>`).join("");
}

// ---------------------------------------------------------------------------
function destroy(id) { if (charts[id]) { charts[id].destroy(); delete charts[id]; } }

function richTooltip(totalKey = "total") {
  return {
    backgroundColor: "#242a55", borderColor: "#e3ac47", borderWidth: 1,
    padding: 10, titleColor: "#f2f0e8", bodyColor: "#c9cdea", displayColors: false,
  };
}

function renderSchoolChart(rows) {
  destroy("chartSchool");
  const ctx = document.getElementById("chartSchool");
  const grandTotal = rows.reduce((s, r) => s + r.total, 0);
  charts.chartSchool = new Chart(ctx, {
    type: "bar",
    data: {
      labels: rows.map(r => r.school),
      datasets: [
        { label: "Confirmed", data: rows.map(r => r.confirmed), backgroundColor: COLORS.teal, stack: "s" },
        { label: "Dropped", data: rows.map(r => r.dropped), backgroundColor: COLORS.coral, stack: "s" },
        { label: "Other", data: rows.map(r => r.total - r.confirmed - r.dropped), backgroundColor: "#3a4080", stack: "s" },
      ],
    },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      onClick: (e, els) => { if (els.length) setFilter("school", rows[els[0].index].school); },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } },
        tooltip: {
          ...richTooltip(),
          callbacks: {
            afterBody: (items) => {
              const r = rows[items[0].dataIndex];
              const pct = grandTotal ? Math.round(1000 * r.total / grandTotal) / 10 : 0;
              return [`${pct}% of total leads`, `Conversion: ${r.conv_rate}%`, "Click to filter dashboard"];
            },
          },
        },
      },
      scales: { x: { stacked: true, grid: { color: "rgba(255,255,255,.05)" } }, y: { stacked: true, grid: { display: false } } },
    },
  });
}

function renderStatusChart(rows) {
  destroy("chartStatus");
  const ctx = document.getElementById("chartStatus");
  const palette = { Confirmed: COLORS.teal, Dropped: COLORS.coral, "In Pipeline": COLORS.gold };
  charts.chartStatus = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: rows.map(r => r.status),
      datasets: [{ data: rows.map(r => r.total), backgroundColor: rows.map(r => palette[r.status] || COLORS.violet), borderColor: "#181b38", borderWidth: 2 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "62%",
      onClick: (e, els) => { if (els.length) setFilter("status", rows[els[0].index].status); },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } },
        tooltip: richTooltip(),
      },
    },
  });
}

function renderSourceChart(rows) {
  destroy("chartSource");
  const ctx = document.getElementById("chartSource");
  charts.chartSource = new Chart(ctx, {
    type: "bar",
    data: {
      labels: rows.map(r => r.lead_source),
      datasets: [
        { label: "Total Leads", data: rows.map(r => r.total), backgroundColor: "#3a4080", yAxisID: "y" },
        { label: "Conversion %", data: rows.map(r => r.conv_rate), type: "line", borderColor: COLORS.gold, backgroundColor: COLORS.gold, yAxisID: "y1", tension: .3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      onClick: (e, els) => { if (els.length) setFilter("lead_source", rows[els[0].index].lead_source); },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } }, tooltip: richTooltip() },
      scales: {
        x: { ticks: { autoSkip: false, maxRotation: 40, minRotation: 30, font: { size: 10 } }, grid: { display: false } },
        y: { position: "left", grid: { color: "rgba(255,255,255,.05)" } },
        y1: { position: "right", grid: { display: false }, suggestedMax: 100 },
      },
    },
  });
}

function renderDropReasons(rows) {
  destroy("chartDropReasons");
  const ctx = document.getElementById("chartDropReasons");
  charts.chartDropReasons = new Chart(ctx, {
    type: "bar",
    data: { labels: rows.map(r => r.reason), datasets: [{ data: rows.map(r => r.total), backgroundColor: COLORS.coral }] },
    options: {
      indexAxis: "y", responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: richTooltip() },
      scales: { x: { grid: { color: "rgba(255,255,255,.05)" } }, y: { grid: { display: false }, ticks: { font: { size: 10.5 } } } },
    },
  });
}

function renderTrend(rows) {
  destroy("chartTrend");
  const ctx = document.getElementById("chartTrend");
  charts.chartTrend = new Chart(ctx, {
    type: "line",
    data: {
      labels: rows.map(r => r.reg_month),
      datasets: [
        { label: "Total Registrations", data: rows.map(r => r.total), borderColor: COLORS.violet, backgroundColor: "rgba(157,139,240,.15)", fill: true, tension: .35 },
        { label: "Confirmed", data: rows.map(r => r.confirmed), borderColor: COLORS.teal, backgroundColor: "rgba(95,200,184,.12)", fill: true, tension: .35 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } }, tooltip: richTooltip() },
      scales: { x: { grid: { display: false } }, y: { grid: { color: "rgba(255,255,255,.05)" } } },
    },
  });
}

function renderMap(rows) {
  const lats = [], lons = [], texts = [], sizes = [], colors = [];
  rows.forEach(r => {
    const c = STATE_COORDS[r.state];
    if (!c) return;
    lats.push(c[0]); lons.push(c[1]);
    const conv = r.total ? Math.round(1000 * r.confirmed / r.total) / 10 : 0;
    texts.push(`${r.state}<br>${r.total} leads · ${conv}% confirmed`);
    sizes.push(10 + Math.sqrt(r.total) * 6);
    colors.push(conv);
  });
  const trace = {
    type: "scattergeo", lat: lats, lon: lons, text: texts, mode: "markers",
    marker: { size: sizes, color: colors, colorscale: [[0, "#ef7161"], [0.5, "#e3ac47"], [1, "#5fc8b8"]], cmin: 0, cmax: 100, line: { color: "#181b38", width: 1 }, opacity: .88 },
    hovertemplate: "%{text}<extra></extra>",
  };
  const layout = {
    geo: {
      scope: "asia", lataxis: { range: [6, 36] }, lonaxis: { range: [66, 98] },
      showland: true, landcolor: "#1d2144", showcountries: true, countrycolor: "#3a4080",
      showcoastlines: false, bgcolor: "rgba(0,0,0,0)",
    },
    paper_bgcolor: "rgba(0,0,0,0)", margin: { t: 0, b: 0, l: 0, r: 0 },
    font: { color: "#c9cdea", family: "Inter" },
  };
  Plotly.newPlot("mapWrap", [trace], layout, { displayModeBar: false, responsive: true });
  document.getElementById("mapWrap").on("plotly_click", (d) => {
    const idx = d.points[0].pointIndex;
    const st = rows[idx] ? rows[idx].state : null;
    if (st) setFilter("state", st);
  });
}

function renderTable(id, rows, keyField) {
  const tbody = document.querySelector(`#${id} tbody`);
  tbody.innerHTML = rows.map(r => `
    <tr style="cursor:pointer" onclick="setFilter('${keyField === 'admission_manager' ? 'admission_manager' : 'team'}', '${String(r[keyField]).replace(/'/g, "\\'")}')">
      <td>${r[keyField]}</td>
      <td>${r.total}</td>
      <td>${r.confirmed}</td>
      <td><span class="pill ${r.conv_rate >= 60 ? "good" : "bad"}">${r.conv_rate}%</span></td>
    </tr>`).join("");
}

function renderHealth(h) {
  const circumference = 2 * Math.PI * 52;
  const offset = circumference - (h.score / 100) * circumference;
  const arc = document.getElementById("healthArc");
  arc.style.strokeDasharray = circumference;
  arc.style.strokeDashoffset = offset;
  arc.style.stroke = h.score >= 70 ? COLORS.teal : h.score >= 45 ? COLORS.gold : COLORS.coral;
  document.getElementById("healthScoreNum").textContent = h.score;
  document.getElementById("healthContrib").innerHTML = h.contributors.map(c => `
    <div class="contrib-row">
      <div class="lbl">${c.label}</div>
      <div class="contrib-bar"><span style="width:${c.value}%"></span></div>
      <div class="val">${Math.round(c.value)}</div>
    </div>`).join("");
}

function renderAlerts(alerts) {
  document.getElementById("alertsWrap").innerHTML = alerts.map(a => `
    <div class="alert ${a.severity}">
      <div class="dot"></div>
      <div>
        <div class="title">${a.title}</div>
        <div class="detail">${a.detail}</div>
        <div class="action">→ ${a.action}</div>
      </div>
    </div>`).join("");
}

function insightBlock(o) {
  if (!o) return "";
  return `
    <div class="row"><span class="tag">Observation</span>${o.observation}</div>
    <div class="row"><span class="tag">Insight</span>${o.insight}</div>
    <div class="row"><span class="tag">Recommendation</span><b>${o.recommendation}</b></div>
    <div class="row"><span class="tag">Impact</span>${o.impact}</div>`;
}

function renderInsights(ins) {
  ["by_school", "funnel", "by_source", "by_state", "drop_reasons"].forEach(k => {
    const el = document.getElementById("insight_" + k);
    if (el) el.innerHTML = insightBlock(ins[k]);
  });
}

// ---------------------------------------------------------------------------
// Presentation mode
// ---------------------------------------------------------------------------
let slideIdx = 0, slides = [];

function buildSlides() {
  if (!lastPayload) return [];
  const k = lastPayload.kpis, h = lastPayload.health_score, ins = lastPayload.insights;
  const s = [];
  s.push({ eyebrow: "Business Health", title: "Overall Admissions Health Score", kpi: h.score + "/100", body: "Composite of conversion rate, school diversification, geographic reach, lead-source mix and pipeline speed — computed from real tracked leads." });
  s.push({ eyebrow: "Admissions", title: "Funnel Snapshot", kpi: k.confirmed + " Confirmed", body: `${k.total} leads tracked · ${k.conv_rate}% conversion · ${k.drop_rate}% drop rate · ${k.pipeline} still in pipeline.` });
  if (ins.by_school) s.push({ eyebrow: "Schools", title: ins.by_school.question, kpi: "", body: ins.by_school.observation + " " + ins.by_school.recommendation });
  if (ins.by_source) s.push({ eyebrow: "Marketing", title: ins.by_source.question, kpi: "", body: ins.by_source.observation + " " + ins.by_source.recommendation });
  if (ins.by_state) s.push({ eyebrow: "Geography", title: ins.by_state.question, kpi: k.n_states + " States", body: ins.by_state.observation + " " + ins.by_state.recommendation });
  if (ins.drop_reasons) s.push({ eyebrow: "Risk", title: ins.drop_reasons.question, kpi: "", body: ins.drop_reasons.observation + " " + ins.drop_reasons.recommendation });
  const topAlert = lastPayload.alerts[0];
  s.push({ eyebrow: "Decision Center", title: "Top Priority Right Now", kpi: "", body: `${topAlert.title}. ${topAlert.detail} Recommended action: ${topAlert.action}` });
  s.push({ eyebrow: "Summary", title: "Where Management Should Focus This Week", kpi: "", body: "Protect volume in top-performing schools, shift incremental spend toward the highest-converting lead source, and follow up fastest with leads that have sat longest in pipeline." });
  return s;
}

function showSlide(i) {
  if (!slides.length) return;
  slideIdx = (i + slides.length) % slides.length;
  const s = slides[slideIdx];
  document.getElementById("p-eyebrow").textContent = s.eyebrow;
  document.getElementById("p-title").textContent = s.title;
  document.getElementById("p-kpi").textContent = s.kpi || "";
  document.getElementById("p-kpi").style.display = s.kpi ? "block" : "none";
  document.getElementById("p-body").textContent = s.body;
  document.getElementById("p-progress").textContent = `Slide ${slideIdx + 1} / ${slides.length}`;
}

function enterPresent() {
  slides = buildSlides();
  slideIdx = 0;
  document.body.classList.add("present-mode");
  showSlide(0);
}
function exitPresent() { document.body.classList.remove("present-mode"); }

document.getElementById("presentBtn").addEventListener("click", enterPresent);
document.getElementById("presentExit").addEventListener("click", exitPresent);
document.getElementById("p-next").addEventListener("click", () => showSlide(slideIdx + 1));
document.getElementById("p-prev").addEventListener("click", () => showSlide(slideIdx - 1));
document.addEventListener("keydown", (e) => {
  if (!document.body.classList.contains("present-mode")) return;
  if (e.key === "Escape") exitPresent();
  if (e.key === "ArrowRight") showSlide(slideIdx + 1);
  if (e.key === "ArrowLeft") showSlide(slideIdx - 1);
});
document.getElementById("resetBtn").addEventListener("click", () => {
  currentFilters = {};
  FILTER_FIELDS.forEach(f => { const el = document.getElementById("f_" + f); if (el) el.value = ""; });
  refresh();
});

// ---------------------------------------------------------------------------
(async function init() {
  await loadFilterOptions();
  await refresh();
})();
