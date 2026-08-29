from __future__ import annotations

import os
import time

import requests

from _shared import TTLCache


PLUGIN_ID = "pihole"
PLUGIN_NAME = "Pi-hole"
PLUGIN_VERSION = "3.0.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/pihole.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 10
PLUGIN_REFRESH_SECONDS = 15
PLUGIN_ACCENT = "#52d273"
PLUGIN_ICON = "DNS"
PLUGIN_PUBLIC_ERROR = "Pi-hole unavailable"

PLUGIN_CONFIG = [
    {
        "key": "PIHOLE_URL",
        "label": "Pi-hole URL",
        "type": "text",
        "default": "http://127.0.0.1",
        "required": True,
    },
    {
        "key": "PIHOLE_PASSWORD",
        "label": "Application Password",
        "type": "password",
        "default": "",
        "help": "Use a Pi-hole application password.",
    },
]

PIHOLE_URL = os.getenv("PIHOLE_URL", "http://127.0.0.1").rstrip("/")
PIHOLE_PASSWORD = os.getenv("PIHOLE_PASSWORD", "")

_session = {"sid": None, "expires": 0}
_detail_cache = TTLCache(60)
_system_cache = TTLCache(300)


PLUGIN_HTML = r'''
<div class="pihole-shell">
  <section class="pihole-hero surface">
    <div>
      <span class="eyebrow">PI-HOLE</span>
      <h1>DNS Command Center</h1>
      <div class="muted" data-role="hero-subtitle">Network-wide DNS filtering</div>
    </div>
    <div class="pihole-state" data-role="blocking-state">--</div>
  </section>

  <section class="pihole-metrics">
    <article class="surface metric-card primary"><span>DNS QUERIES</span><strong data-role="queries">--</strong><small>last 24 hours</small></article>
    <article class="surface metric-card blocked"><span>BLOCKED</span><strong data-role="blocked">--</strong><small data-role="blocked-sub">queries blocked</small></article>
    <article class="surface metric-card"><span>BLOCK RATE</span><strong data-role="percent">--</strong><small>of all DNS queries</small></article>
    <article class="surface metric-card"><span>ACTIVE CLIENTS</span><strong data-role="clients">--</strong><small data-role="clients-sub">currently active</small></article>
    <article class="surface metric-card"><span>DOMAINS ON LIST</span><strong data-role="gravity">--</strong><small>gravity database</small></article>
    <article class="surface metric-card"><span>CACHED</span><strong data-role="cached">--</strong><small>queries answered locally</small></article>
  </section>

  <section class="surface pihole-chart-card">
    <div class="pihole-section-head">
      <div><div class="section-label">DNS ACTIVITY · LAST 24 HOURS</div><div class="muted tiny">Query volume over time</div></div>
      <div class="chart-legend"><span><i class="legend-dot query"></i>Queries</span><span><i class="legend-dot blocked"></i>Blocked</span></div>
    </div>
    <div class="chart-wrap"><canvas data-role="chart" width="1500" height="250"></canvas></div>
  </section>

  <section class="pihole-detail-grid">
    <article class="surface"><div class="pihole-section-head"><div class="section-label">TOP REQUESTED DOMAINS</div><span class="detail-note">24h</span></div><div class="rank-list" data-role="top-domains"></div></article>
    <article class="surface"><div class="pihole-section-head"><div class="section-label">TOP BLOCKED DOMAINS</div><span class="detail-note">24h</span></div><div class="rank-list" data-role="top-blocked"></div></article>
    <article class="surface"><div class="pihole-section-head"><div class="section-label">TOP CLIENTS</div><span class="detail-note">DNS activity</span></div><div class="rank-list" data-role="top-clients"></div></article>
    <article class="surface"><div class="pihole-section-head"><div class="section-label">QUERY TYPES</div><span class="detail-note">record mix</span></div><div class="type-grid" data-role="query-types"></div></article>
    <article class="surface"><div class="pihole-section-head"><div class="section-label">UPSTREAM RESOLVERS</div><span class="detail-note">forwarded DNS</span></div><div class="rank-list" data-role="upstreams"></div></article>
    <article class="surface pihole-system-card"><div class="pihole-section-head"><div class="section-label">PI-HOLE STATUS</div><span class="detail-note" data-role="version-label"></span></div><div class="system-grid" data-role="system-info"></div></article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-pihole .pihole-shell{display:grid;gap:var(--gap)}
.plugin-pihole .pihole-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;border-left:2px solid rgba(82,210,115,.72);background:linear-gradient(110deg,rgba(82,210,115,.045),rgba(255,255,255,.008) 36%,rgba(255,255,255,.006))}
.plugin-pihole .pihole-hero h1{margin:.2rem 0 .15rem;font-size:clamp(1.45rem,3vw,2.65rem);line-height:1}
.plugin-pihole .pihole-state{padding:.45rem .72rem;border-radius:.45rem;border:1px solid var(--border);font-size:.62rem;font-weight:950;letter-spacing:.05em}
.plugin-pihole .pihole-state.enabled{color:#6eea8f;border-color:rgba(110,234,143,.5);background:rgba(110,234,143,.055)}
.plugin-pihole .pihole-state.disabled{color:#ff7c84;border-color:rgba(255,124,132,.5);background:rgba(255,124,132,.05)}
.plugin-pihole .pihole-metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:var(--gap)}
.plugin-pihole .metric-card{min-width:0;border-top:1px solid rgba(82,210,115,.13)}
.plugin-pihole .metric-card.primary{border-left:2px solid rgba(82,210,115,.72)}
.plugin-pihole .metric-card.blocked{border-left:2px solid rgba(244,173,72,.65)}
.plugin-pihole .metric-card span{display:block;font-size:.47rem;color:var(--muted);font-weight:850;letter-spacing:.055em}
.plugin-pihole .metric-card strong{display:block;margin-top:.1rem;font-size:clamp(1rem,2vw,1.65rem);line-height:1.05;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-pihole .metric-card small{display:block;margin-top:.08rem;font-size:.46rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-pihole .pihole-chart-card{min-height:17rem}
.plugin-pihole .pihole-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.8rem}
.plugin-pihole .tiny,.plugin-pihole .detail-note{font-size:.46rem;color:var(--muted)}
.plugin-pihole .chart-wrap{height:13.5rem;margin-top:.55rem;position:relative}
.plugin-pihole .chart-wrap canvas{width:100%!important;height:100%!important}
.plugin-pihole .chart-legend{display:flex;gap:.75rem;color:var(--muted);font-size:.48rem;font-weight:800}
.plugin-pihole .chart-legend span{display:flex;align-items:center;gap:.25rem}
.plugin-pihole .legend-dot{width:.42rem;height:.42rem;border-radius:50%;display:inline-block}
.plugin-pihole .legend-dot.query{background:#52d273;box-shadow:0 0 7px rgba(82,210,115,.6)}
.plugin-pihole .legend-dot.blocked{background:#f3aa49;box-shadow:0 0 7px rgba(243,170,73,.5)}
.plugin-pihole .pihole-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:var(--gap);align-items:start}
.plugin-pihole .rank-list{display:grid;gap:.26rem;margin-top:.52rem}
.plugin-pihole .rank-row{display:grid;grid-template-columns:1.6rem minmax(0,1fr) auto;gap:.45rem;align-items:center;min-height:1.72rem;padding:.26rem .36rem;border-radius:.34rem;border:1px solid rgba(255,255,255,.025);background:rgba(255,255,255,.012)}
.plugin-pihole .rank-num{display:grid;place-items:center;width:1.35rem;height:1.35rem;border:1px solid var(--border);border-radius:.3rem;font-size:.5rem;font-weight:900;color:var(--muted)}
.plugin-pihole .rank-name{min-width:0;font-size:.57rem;font-weight:780;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-pihole .rank-value{font-size:.55rem;font-weight:900;color:#8fe5a6;text-align:right}
.plugin-pihole .rank-row.blocked .rank-value{color:#f3b45b}
.plugin-pihole .type-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.32rem;margin-top:.52rem}
.plugin-pihole .type-card{padding:.45rem;border:1px solid var(--border);border-radius:.38rem;background:rgba(255,255,255,.012)}
.plugin-pihole .type-card span{display:block;color:var(--muted);font-size:.47rem;font-weight:800}
.plugin-pihole .type-card strong{display:block;margin-top:.1rem;font-size:.74rem}
.plugin-pihole .type-bar{height:.18rem;margin-top:.28rem;background:rgba(255,255,255,.055);border-radius:1rem;overflow:hidden}
.plugin-pihole .type-bar i{display:block;height:100%;background:#52d273;border-radius:1rem}
.plugin-pihole .system-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.34rem;margin-top:.52rem}
.plugin-pihole .system-item{padding:.42rem .46rem;border:1px solid var(--border);border-radius:.38rem;background:rgba(255,255,255,.012);min-width:0}
.plugin-pihole .system-item span{display:block;color:var(--muted);font-size:.45rem;font-weight:800}
.plugin-pihole .system-item strong{display:block;margin-top:.1rem;font-size:.58rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-pihole .empty-detail{display:grid;place-items:center;min-height:6rem;margin-top:.5rem;border:1px dashed var(--border);border-radius:.4rem;color:var(--muted);font-size:.52rem;text-align:center;padding:.6rem}
@media(max-width:1100px){.plugin-pihole .pihole-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}.plugin-pihole .pihole-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.plugin-pihole .pihole-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.plugin-pihole .pihole-detail-grid{grid-template-columns:1fr}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.pihole={
  number(value){return RackDash.formatNumber(Number(value||0));},
  percent(value){return `${Number(value||0).toFixed(1)}%`;},
  list(rows,blocked=false){
    if(!rows?.length)return `<div class="empty-detail">No data returned by Pi-hole.</div>`;
    return rows.slice(0,6).map((row,index)=>`<div class="rank-row ${blocked?"blocked":""}"><div class="rank-num">${index+1}</div><div class="rank-name" title="${RackDash.escape(row.name||"")}">${RackDash.escape(row.name||"Unknown")}</div><div class="rank-value">${this.number(row.count)}</div></div>`).join("");
  },
  queryTypes(rows){
    if(!rows?.length)return `<div class="empty-detail">Query-type statistics unavailable.</div>`;
    const max=Math.max(...rows.map(row=>Number(row.count||0)),1);
    return rows.slice(0,8).map(row=>`<div class="type-card"><span>${RackDash.escape(row.name||"OTHER")}</span><strong>${this.number(row.count)}</strong><div class="type-bar"><i style="width:${Math.max(2,Number(row.count||0)/max*100)}%"></i></div></div>`).join("");
  },
  systemInfo(data){
    const rows=[["HOST",data.host],["PI-HOLE",data.pihole_version],["FTL",data.ftl_version],["WEB",data.web_version],["API",data.api_version],["TOTAL CLIENTS",data.clients_total],["UPSTREAMS",data.upstream_count],["STATUS",data.blocking===true?"Blocking enabled":data.blocking===false?"Blocking disabled":""]].filter(row=>row[1]!==null&&row[1]!==undefined&&String(row[1])!=="");
    if(!rows.length)return `<div class="empty-detail">System details unavailable.</div>`;
    return rows.map(([label,value])=>`<div class="system-item"><span>${RackDash.escape(label)}</span><strong title="${RackDash.escape(String(value))}">${RackDash.escape(String(value))}</strong></div>`).join("");
  },
  drawActivity(canvas,history){
    if(!canvas)return;
    const rows=history||[];
    const queryValues=rows.map(row=>Number(row.total||0));
    RackDash.drawLine(canvas,queryValues,"#52d273");
    if(!rows.some(row=>Number(row.blocked||0)>0))return;
    const ctx=canvas.getContext("2d");if(!ctx)return;
    const blockedValues=rows.map(row=>Number(row.blocked||0));
    const allMax=Math.max(...queryValues,1),w=canvas.width,h=canvas.height,pad=10;
    ctx.save();ctx.strokeStyle="#f3aa49";ctx.lineWidth=2;ctx.beginPath();
    blockedValues.forEach((value,index)=>{const x=pad+(w-pad*2)*(index/Math.max(1,blockedValues.length-1));const y=h-pad-(h-pad*2)*(value/allMax);if(index===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});
    ctx.stroke();ctx.restore();
  },
  render(data,root){
    root.querySelector('[data-role="queries"]').textContent=this.number(data.queries);
    root.querySelector('[data-role="blocked"]').textContent=this.number(data.blocked);
    root.querySelector('[data-role="percent"]').textContent=this.percent(data.percent);
    root.querySelector('[data-role="clients"]').textContent=this.number(data.clients);
    root.querySelector('[data-role="gravity"]').textContent=this.number(data.gravity);
    root.querySelector('[data-role="cached"]').textContent=this.number(data.cached);
    root.querySelector('[data-role="blocked-sub"]').textContent=`${this.percent(data.percent)} of DNS traffic`;
    root.querySelector('[data-role="clients-sub"]').textContent=data.clients_total!=null?`${this.number(data.clients_total)} known clients`:"currently active";
    const state=root.querySelector('[data-role="blocking-state"]');
    if(data.blocking===true){state.textContent="BLOCKING ACTIVE";state.className="pihole-state enabled";}else if(data.blocking===false){state.textContent="BLOCKING DISABLED";state.className="pihole-state disabled";}else{state.textContent="LIVE";state.className="pihole-state enabled";}
    root.querySelector('[data-role="hero-subtitle"]').textContent=[data.host,data.pihole_version?`Pi-hole ${data.pihole_version}`:""].filter(Boolean).join(" · ")||"Network-wide DNS filtering";
    root.querySelector('[data-role="top-domains"]').innerHTML=this.list(data.top_domains);
    root.querySelector('[data-role="top-blocked"]').innerHTML=this.list(data.top_blocked,true);
    root.querySelector('[data-role="top-clients"]').innerHTML=this.list(data.top_clients);
    root.querySelector('[data-role="upstreams"]').innerHTML=this.list(data.upstreams);
    root.querySelector('[data-role="query-types"]').innerHTML=this.queryTypes(data.query_types);
    root.querySelector('[data-role="system-info"]').innerHTML=this.systemInfo(data);
    root.querySelector('[data-role="version-label"]').textContent=data.ftl_version?`FTL ${data.ftl_version}`:"";
    this.drawActivity(root.querySelector('[data-role="chart"]'),data.history||[]);
  }
};
'''


def _sid():
    if not PIHOLE_PASSWORD:
        return None
    now = time.time()
    if _session["sid"] and now < _session["expires"] - 30:
        return _session["sid"]
    response = requests.post(f"{PIHOLE_URL}/api/auth", json={"password": PIHOLE_PASSWORD}, timeout=3)
    response.raise_for_status()
    session = response.json()["session"]
    _session["sid"] = session["sid"]
    _session["expires"] = now + int(session.get("validity", 300))
    return _session["sid"]


def _get(path):
    sid = _sid()
    headers = {"X-FTL-SID": sid} if sid else {}
    response = requests.get(f"{PIHOLE_URL}{path}", headers=headers, timeout=3)
    if response.status_code == 401 and PIHOLE_PASSWORD:
        _session["sid"] = None
        headers = {"X-FTL-SID": _sid()}
        response = requests.get(f"{PIHOLE_URL}{path}", headers=headers, timeout=3)
    response.raise_for_status()
    return response.json()


def _safe_get(path, default=None):
    try:
        return _get(path)
    except Exception:
        return default


def _first_number(mapping, keys, default=0):
    if not isinstance(mapping, dict):
        return default
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, (int, float)):
            return value
    return default


def _normalize_rank_rows(payload, section_names=()):
    if payload is None:
        return []
    value = payload
    if isinstance(payload, dict):
        for key in section_names:
            if key in payload:
                value = payload[key]
                break
        if value is payload:
            for key in ("domains", "clients", "upstreams", "data"):
                if key in payload:
                    value = payload[key]
                    break
    rows = []
    if isinstance(value, dict):
        for name, count in value.items():
            amount = _first_number(count, ("count", "queries", "total"), 0) if isinstance(count, dict) else count
            if isinstance(amount, (int, float)):
                rows.append({"name": str(name), "count": amount})
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("domain") or item.get("name") or item.get("client") or item.get("ip") or item.get("address") or item.get("upstream") or item.get("destination") or item.get("host")
            count = _first_number(item, ("count", "queries", "total", "frequency"), 0)
            if name is not None:
                rows.append({"name": str(name), "count": count})
    rows.sort(key=lambda row: float(row["count"] or 0), reverse=True)
    return rows


def _normalize_top_domains(payload):
    if not isinstance(payload, dict):
        return [], []
    requested = _normalize_rank_rows(payload, ("domains", "top_domains", "top"))
    blocked = _normalize_rank_rows(payload, ("blocked", "top_blocked", "blocked_domains", "ads"))
    if not requested:
        requested = _normalize_rank_rows(payload, ("top_queries",))
    if not blocked:
        blocked = _normalize_rank_rows(payload, ("top_ads",))
    return requested, blocked


def _normalize_query_types(payload):
    if payload is None:
        return []
    value = payload
    if isinstance(payload, dict):
        for key in ("types", "query_types", "queries"):
            if key in payload:
                value = payload[key]
                break
    rows = []
    if isinstance(value, dict):
        for name, count in value.items():
            if isinstance(count, (int, float)):
                rows.append({"name": str(name).upper(), "count": count})
            elif isinstance(count, dict):
                amount = _first_number(count, ("count", "queries", "total"), None)
                if amount is not None:
                    rows.append({"name": str(name).upper(), "count": amount})
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("type") or item.get("name") or item.get("query_type")
            count = _first_number(item, ("count", "queries", "total"), None)
            if name is not None and count is not None:
                rows.append({"name": str(name).upper(), "count": count})
    rows.sort(key=lambda row: float(row["count"] or 0), reverse=True)
    return rows


def _normalize_history(payload):
    if not isinstance(payload, dict):
        return []
    rows = payload.get("history", [])
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[-144:]:
        if not isinstance(row, dict):
            continue
        result.append({
            "timestamp": row.get("timestamp") or row.get("time") or row.get("start"),
            "total": _first_number(row, ("total", "queries"), 0),
            "blocked": _first_number(row, ("blocked", "blocked_queries"), 0),
        })
    return result


def _detail_data():
    cached = _detail_cache.get()
    if cached is not None:
        return dict(cached)
    top_domains, top_blocked = _normalize_top_domains(_safe_get("/api/stats/top_domains", {}))
    top_clients = _normalize_rank_rows(_safe_get("/api/stats/top_clients", {}), ("clients", "top_clients"))
    upstreams = _normalize_rank_rows(_safe_get("/api/stats/upstreams", {}), ("upstreams", "destinations"))
    query_types = _normalize_query_types(_safe_get("/api/stats/query_types", {}))
    result = {
        "top_domains": top_domains[:8],
        "top_blocked": top_blocked[:8],
        "top_clients": top_clients[:8],
        "upstreams": upstreams[:8],
        "query_types": query_types[:10],
    }
    _detail_cache.set(result)
    return dict(result)


def _scalar_text(value):
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return str(value)

    return ""


def _version_from_object(value):
    """
    Pi-hole v6 /api/info/version returns nested objects whose values may
    themselves be dictionaries such as local/remote version metadata.
    Extract a human-readable version string without ever stringifying the
    entire Python object into the dashboard.
    """
    if isinstance(value, (str, int, float)):
        return str(value)

    if not isinstance(value, dict):
        return ""

    # Prefer direct version-ish fields.
    for key in ("version", "local_version", "current", "tag"):
        candidate = _scalar_text(value.get(key))
        if candidate:
            return candidate

    # Pi-hole v6 commonly nests version info under local/remote.
    local = value.get("local")
    if isinstance(local, dict):
        for key in ("version", "tag"):
            candidate = _scalar_text(local.get(key))
            if candidate:
                return candidate

    remote = value.get("remote")
    if isinstance(remote, dict):
        for key in ("version", "tag"):
            candidate = _scalar_text(remote.get(key))
            if candidate:
                return candidate

    return ""


def _host_from_object(payload):
    if not isinstance(payload, dict):
        return ""

    # v6 may return host metadata as a nested object.
    for key in ("hostname", "host", "name"):
        candidate = _scalar_text(payload.get(key))
        if candidate:
            return candidate

    for key in ("system", "host"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            for subkey in ("hostname", "host", "name"):
                candidate = _scalar_text(nested.get(subkey))
                if candidate:
                    return candidate

    return ""


def _system_data():
    cached = _system_cache.get()
    if cached is not None:
        return dict(cached)

    blocking_payload = _safe_get(
        "/api/dns/blocking",
        {},
    )
    version_payload = _safe_get(
        "/api/info/version",
        {},
    )
    host_payload = _safe_get(
        "/api/info/host",
        {},
    )

    blocking = None
    if isinstance(blocking_payload, dict):
        value = blocking_payload.get("blocking")

        if isinstance(value, bool):
            blocking = value
        elif isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("enabled", "true", "on"):
                blocking = True
            elif lowered in ("disabled", "false", "off"):
                blocking = False

    host = _host_from_object(host_payload)

    pihole_version = ""
    ftl_version = ""
    web_version = ""
    api_version = ""

    if isinstance(version_payload, dict):
        # Pi-hole v6 can expose these as rich nested dictionaries.
        pihole_version = _version_from_object(
            version_payload.get("core")
            or version_payload.get("pihole")
        )

        ftl_version = _version_from_object(
            version_payload.get("ftl")
        )

        web_version = _version_from_object(
            version_payload.get("web")
        )

        api_version = _version_from_object(
            version_payload.get("api")
        )

        # Flat-field fallbacks for other v6 revisions.
        if not pihole_version:
            pihole_version = _scalar_text(
                version_payload.get("core_version")
                or version_payload.get("version")
            )

        if not ftl_version:
            ftl_version = _scalar_text(
                version_payload.get("ftl_version")
            )

        if not web_version:
            web_version = _scalar_text(
                version_payload.get("web_version")
            )

        if not api_version:
            api_version = _scalar_text(
                version_payload.get("api_version")
            )

    result = {
        "blocking": blocking,
        "host": host,
        "pihole_version": pihole_version,
        "ftl_version": ftl_version,
        "web_version": web_version,
        "api_version": api_version,
    }

    _system_cache.set(result)
    return dict(result)


def get_data():
    summary = _get("/api/stats/summary")
    queries = summary.get("queries", {}) if isinstance(summary, dict) else {}
    clients = summary.get("clients", {}) if isinstance(summary, dict) else {}
    history = _normalize_history(_safe_get("/api/history", {}))
    details = _detail_data()
    system = _system_data()
    gravity = 0
    if isinstance(summary, dict):
        gravity = _first_number(summary, ("gravity", "domains_being_blocked"), 0)
        gravity_data = summary.get("gravity")
        if isinstance(gravity_data, dict):
            gravity = _first_number(gravity_data, ("domains_being_blocked", "total", "count"), gravity)
    data = {
        "queries": _first_number(queries, ("total", "queries"), 0),
        "blocked": _first_number(queries, ("blocked", "blocked_queries"), 0),
        "percent": _first_number(queries, ("percent_blocked", "percentage_blocked", "blocked_percent"), 0),
        "cached": _first_number(queries, ("cached", "cache", "cached_queries"), 0),
        "clients": _first_number(clients, ("active", "active_clients"), _first_number(clients, ("total", "clients"), 0)),
        "clients_total": _first_number(clients, ("total", "clients"), 0),
        "gravity": gravity,
        "history": history,
    }
    data.update(details)
    data.update(system)
    data["upstream_count"] = len(data.get("upstreams") or [])
    return data


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {"title": "Pi-hole", "lines": ["DNS unavailable"]}
    state = "ON" if data.get("blocking") is not False else "OFF"
    return {
        "title": "Pi-hole",
        "lines": [
            f"DNS {state}  Q {int(data.get('queries', 0)):,}",
            f"Blocked {int(data.get('blocked', 0)):,} {float(data.get('percent', 0)):.1f}%",
            f"Clients {int(data.get('clients', 0))} List {int(data.get('gravity', 0)):,}",
        ],
    }
