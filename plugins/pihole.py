from __future__ import annotations
import os
import time
import requests

PLUGIN_ID = "pihole"
PLUGIN_NAME = "Pi-hole"
PLUGIN_VERSION = "1.0.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/pihole.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ['network']
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 10
PLUGIN_REFRESH_SECONDS = 2
PLUGIN_ACCENT = "#52d273"
PLUGIN_ICON = "DNS"
PLUGIN_PUBLIC_ERROR = "Pi-hole unavailable"

PLUGIN_CONFIG = [{'key': 'PIHOLE_URL', 'label': 'Pi-hole URL', 'type': 'text', 'default': 'http://127.0.0.1', 'required': True}, {'key': 'PIHOLE_PASSWORD', 'label': 'Application Password', 'type': 'password', 'default': '', 'help': 'Use a Pi-hole application password.'}]

PIHOLE_URL = os.getenv("PIHOLE_URL", "http://127.0.0.1").rstrip("/")
PIHOLE_PASSWORD = os.getenv("PIHOLE_PASSWORD", "")
_session = {"sid": None, "expires": 0}


def _sid():
    if not PIHOLE_PASSWORD:
        return None
    now = time.time()
    if _session["sid"] and now < _session["expires"] - 30:
        return _session["sid"]
    r = requests.post(f"{PIHOLE_URL}/api/auth", json={"password": PIHOLE_PASSWORD}, timeout=3)
    r.raise_for_status()
    session = r.json()["session"]
    _session["sid"] = session["sid"]
    _session["expires"] = now + int(session.get("validity", 300))
    return _session["sid"]


def _get(path):
    sid = _sid()
    headers = {"X-FTL-SID": sid} if sid else {}
    r = requests.get(f"{PIHOLE_URL}{path}", headers=headers, timeout=3)
    if r.status_code == 401 and PIHOLE_PASSWORD:
        _session["sid"] = None
        headers = {"X-FTL-SID": _sid()}
        r = requests.get(f"{PIHOLE_URL}{path}", headers=headers, timeout=3)
    r.raise_for_status()
    return r.json()


def get_data():
    summary = _get("/api/stats/summary")
    queries = summary.get("queries", {})
    clients = summary.get("clients", {})
    history = []
    try:
        history = _get("/api/history").get("history", [])[-72:]
    except Exception:
        pass
    return {
        "queries": queries.get("total", 0),
        "blocked": queries.get("blocked", 0),
        "percent": queries.get("percent_blocked", 0),
        "clients": clients.get("active", clients.get("total", 0)),
        "history": history,
    }


PLUGIN_HTML = r'''
<div class="plugin-head">
  <div><span class="eyebrow">PI-HOLE</span><h1>DNS Overview</h1></div>
  <span class="status-chip">LIVE</span>
</div>
<div class="metric-grid">
  <article class="metric"><label>DNS QUERIES</label><strong data-role="queries">—</strong><small>last 24 hours</small></article>
  <article class="metric"><label>BLOCKED</label><strong data-role="blocked">—</strong><small>queries blocked</small></article>
  <article class="metric"><label>BLOCK RATE</label><strong data-role="percent">—</strong><small>of all queries</small></article>
  <article class="metric"><label>CLIENTS</label><strong data-role="clients">—</strong><small>active clients</small></article>
</div>
<section class="chart-card">
  <div class="section-label">DNS ACTIVITY</div>
  <canvas data-role="chart" width="1180" height="150"></canvas>
</section>
'''

PLUGIN_CSS = r'''
.plugin-pihole .metric{border-left:2px solid rgba(82,223,119,.6)}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.pihole={
  render(data,root){
    root.querySelector('[data-role="queries"]').textContent=RackDash.formatNumber(data.queries);
    root.querySelector('[data-role="blocked"]').textContent=RackDash.formatNumber(data.blocked);
    root.querySelector('[data-role="percent"]').textContent=`${Number(data.percent||0).toFixed(1)}%`;
    root.querySelector('[data-role="clients"]').textContent=RackDash.formatNumber(data.clients);
    RackDash.drawLine(root.querySelector('[data-role="chart"]'),(data.history||[]).map(x=>Number(x.total||0)),"#52d273");
  },
  onResize(root){ this.renderLast && this.renderLast(root); }
};
'''
