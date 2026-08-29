from __future__ import annotations

import os
import re

import requests

from _shared import TTLCache


PLUGIN_ID = "uptime_kuma"
PLUGIN_NAME = "Uptime Kuma"
PLUGIN_VERSION = "3.0.1"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/uptime_kuma.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 80
PLUGIN_REFRESH_SECONDS = 30
PLUGIN_ACCENT = "#5cdd8b"
PLUGIN_ICON = "UK"
PLUGIN_PUBLIC_ERROR = "Uptime Kuma data unavailable"

PLUGIN_CONFIG = [
    {
        "key": "UPTIME_KUMA_URL",
        "label": "Uptime Kuma URL",
        "type": "text",
        "default": "http://127.0.0.1:3001",
        "required": True,
        "help": "Base URL of your Uptime Kuma server.",
    },
    {
        "key": "UPTIME_KUMA_STATUS_PAGE",
        "label": "Status Page Slug",
        "type": "text",
        "default": "",
        "required": False,
        "help": "Recommended. Published status page slug, for example homelab. Enables groups, 24h uptime, and last-check timestamps.",
    },
    {
        "key": "UPTIME_KUMA_API_KEY",
        "label": "API Key",
        "type": "secret",
        "default": "",
        "required": False,
        "help": "Optional. Used for /metrics when no Status Page Slug is configured.",
    },
    {
        "key": "UPTIME_KUMA_USERNAME",
        "label": "Username",
        "type": "text",
        "default": "",
        "required": False,
        "help": "Optional fallback for /metrics when not using an API key.",
    },
    {
        "key": "UPTIME_KUMA_PASSWORD",
        "label": "Password",
        "type": "secret",
        "default": "",
        "required": False,
        "help": "Optional fallback for /metrics when not using an API key.",
    },
    {
        "key": "UPTIME_KUMA_FILTER",
        "label": "Monitor Filter",
        "type": "text",
        "default": "",
        "required": False,
        "help": "Optional comma-separated monitor name fragments. Leave blank for all.",
    },
    {
        "key": "UPTIME_KUMA_SHOW_ONLY_PROBLEMS",
        "label": "Show Only Problems",
        "type": "checkbox",
        "default": "false",
        "required": False,
        "help": "Show only DOWN, PENDING, or MAINTENANCE monitors.",
    },
]

PLUGIN_HTML = r'''
<div class="kuma-shell">
  <div class="kuma-summary">
    <div>
      <span class="eyebrow">UPTIME KUMA</span>
      <h1 data-role="headline">Checking monitors...</h1>
      <div class="muted" data-role="subhead"></div>
    </div>
    <div class="kuma-overall" data-role="overall">--</div>
  </div>

  <div class="kuma-stats">
    <div><span>UP</span><strong data-role="up-count">--</strong></div>
    <div><span>DOWN</span><strong data-role="down-count">--</strong></div>
    <div><span>PENDING</span><strong data-role="pending-count">--</strong></div>
    <div><span>MAINT</span><strong data-role="maintenance-count">--</strong></div>
    <div><span>AVG RESPONSE</span><strong data-role="avg-ping">--</strong></div>
  </div>

  <div class="kuma-groups" data-role="groups"></div>
</div>
'''

PLUGIN_CSS = r'''
.plugin-uptime_kuma .kuma-shell{height:100%;display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:var(--gap)}
.plugin-uptime_kuma .kuma-summary{display:flex;align-items:center;justify-content:space-between;gap:1rem}
.plugin-uptime_kuma .kuma-summary h1{margin:.18rem 0 0;font-size:clamp(1rem,2.3vw,1.8rem)}
.plugin-uptime_kuma .kuma-overall{min-width:6.2rem;padding:.42rem .7rem;text-align:center;border:1px solid var(--border);border-radius:.5rem;font-size:.68rem;font-weight:900;background:rgba(255,255,255,.015)}
.plugin-uptime_kuma .kuma-overall.ok{color:#66e28a;border-color:rgba(102,226,138,.45)}
.plugin-uptime_kuma .kuma-overall.bad{color:#ff7d86;border-color:rgba(255,125,134,.48)}
.plugin-uptime_kuma .kuma-overall.warn{color:#f6b73c;border-color:rgba(246,183,60,.48)}
.plugin-uptime_kuma .kuma-stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.45rem}
.plugin-uptime_kuma .kuma-stats>div{padding:.42rem .55rem;border:1px solid var(--border);border-radius:.45rem;background:rgba(255,255,255,.012)}
.plugin-uptime_kuma .kuma-stats span{display:block;font-size:.5rem;color:var(--muted);font-weight:850;letter-spacing:.05em}
.plugin-uptime_kuma .kuma-stats strong{display:block;margin-top:.08rem;font-size:.83rem}
.plugin-uptime_kuma .kuma-groups{overflow:auto;display:grid;gap:.55rem;align-content:start;padding-bottom:.2rem}
.plugin-uptime_kuma .kuma-group{border:1px solid var(--border);border-radius:.55rem;overflow:hidden;background:rgba(255,255,255,.01)}
.plugin-uptime_kuma .kuma-group-head{display:flex;justify-content:space-between;align-items:center;padding:.38rem .55rem;border-bottom:1px solid var(--border);font-size:.58rem;font-weight:900;color:#aab7bd}
.plugin-uptime_kuma .kuma-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.plugin-uptime_kuma .kuma-monitor{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:.45rem;align-items:center;padding:.48rem .55rem;border-right:1px solid rgba(255,255,255,.04);border-bottom:1px solid rgba(255,255,255,.04);min-width:0}
.plugin-uptime_kuma .kuma-dot{width:9px;height:9px;border-radius:50%;background:#6d7b82}
.plugin-uptime_kuma .kuma-monitor.up .kuma-dot{background:#54df77}
.plugin-uptime_kuma .kuma-monitor.down .kuma-dot{background:#ff5d68;box-shadow:0 0 8px rgba(255,93,104,.38)}
.plugin-uptime_kuma .kuma-monitor.pending .kuma-dot{background:#f6b73c}
.plugin-uptime_kuma .kuma-monitor.maintenance .kuma-dot{background:#6fb7ff}
.plugin-uptime_kuma .kuma-copy{min-width:0}
.plugin-uptime_kuma .kuma-name{font-size:.68rem;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-uptime_kuma .kuma-detail{margin-top:.12rem;font-size:.52rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-uptime_kuma .kuma-right{text-align:right;min-width:68px}
.plugin-uptime_kuma .kuma-right strong{display:block;font-size:.68rem}
.plugin-uptime_kuma .kuma-right small{display:block;font-size:.48rem;color:var(--muted)}
.plugin-uptime_kuma .kuma-empty{display:grid;place-items:center;min-height:120px;border:1px dashed var(--border);border-radius:.55rem;color:var(--muted)}
@media(min-width:1000px) and (max-height:500px){
  .plugin-uptime_kuma .kuma-list{grid-template-columns:repeat(3,minmax(0,1fr))}
  .plugin-uptime_kuma .kuma-monitor{padding:.38rem .45rem}
}
@media(max-width:700px){
  .plugin-uptime_kuma .kuma-stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .plugin-uptime_kuma .kuma-list{grid-template-columns:1fr}
}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.uptime_kuma={
  statusName(status){
    return ({0:"down",1:"up",2:"pending",3:"maintenance"})[Number(status)]||"unknown";
  },

  ago(timestamp){
    if(!timestamp)return "No check time";
    const t=Date.parse(timestamp);
    if(Number.isNaN(t))return timestamp;
    const seconds=Math.max(0,Math.floor((Date.now()-t)/1000));
    if(seconds<60)return `${seconds}s ago`;
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    return `${Math.floor(seconds/86400)}d ago`;
  },

  monitor(m){
    const state=this.statusName(m.status);
    const uptime=m.uptime_24h==null?"--":`${(Number(m.uptime_24h)*100).toFixed(Number(m.uptime_24h)>=.999?2:1)}%`;
    const ping=m.ping==null?"--":`${Math.round(Number(m.ping))}ms`;
    const detail=[m.type||"",this.ago(m.last_check)].filter(Boolean).join(" · ");
    return `<div class="kuma-monitor ${state}">
      <span class="kuma-dot"></span>
      <div class="kuma-copy">
        <div class="kuma-name">${RackDash.escape(m.name||"Monitor")}</div>
        <div class="kuma-detail">${RackDash.escape(detail)}</div>
      </div>
      <div class="kuma-right">
        <strong>${RackDash.escape(ping)}</strong>
        <small>${RackDash.escape(uptime)} uptime</small>
      </div>
    </div>`;
  },

  render(data,root){
    const counts=data.counts||{};
    root.querySelector('[data-role="up-count"]').textContent=counts.up??0;
    root.querySelector('[data-role="down-count"]').textContent=counts.down??0;
    root.querySelector('[data-role="pending-count"]').textContent=counts.pending??0;
    root.querySelector('[data-role="maintenance-count"]').textContent=counts.maintenance??0;
    root.querySelector('[data-role="avg-ping"]').textContent=data.avg_ping==null?"--":`${Math.round(data.avg_ping)}ms`;

    const overall=root.querySelector('[data-role="overall"]');
    if(counts.down){
      overall.textContent="DEGRADED";
      overall.className="kuma-overall bad";
    }else if(counts.pending){
      overall.textContent="PENDING";
      overall.className="kuma-overall warn";
    }else{
      overall.textContent="ALL SYSTEMS UP";
      overall.className="kuma-overall ok";
    }

    root.querySelector('[data-role="headline"]').textContent=
      counts.down?`${counts.down} monitor${counts.down===1?"":"s"} down`:
      counts.pending?`${counts.pending} monitor${counts.pending===1?"":"s"} pending`:
      "All monitored services are healthy";

    root.querySelector('[data-role="subhead"]').textContent=
      `${data.visible_count??0} shown · ${data.total_count||0} total · ${data.mode==="status_page"?"Status Page API":"Prometheus metrics"}`;

    const groups=root.querySelector('[data-role="groups"]');
    const rows=data.groups||[];
    if(!rows.length){
      groups.innerHTML=`<div class="kuma-empty">No monitors match the current filter.</div>`;
      return;
    }

    groups.innerHTML=rows.map(group=>`
      <section class="kuma-group">
        <div class="kuma-group-head">
          <span>${RackDash.escape(group.name||"Monitors")}</span>
          <span>${group.monitors.length}</span>
        </div>
        <div class="kuma-list">${group.monitors.map(m=>this.monitor(m)).join("")}</div>
      </section>
    `).join("");
  }
};
'''

_cache = TTLCache(20)
_METRIC_RE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+([-+0-9.eE]+)$')
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')


def _bool(name: str, default="false"):
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _base_url():
    return os.getenv(
        "UPTIME_KUMA_URL",
        "http://127.0.0.1:3001",
    ).strip().rstrip("/")


def _filters():
    raw = os.getenv("UPTIME_KUMA_FILTER", "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _matches(name: str):
    filters = _filters()
    if not filters:
        return True
    lowered = (name or "").lower()
    return any(part in lowered for part in filters)


def _status_page_data():
    slug = os.getenv("UPTIME_KUMA_STATUS_PAGE", "").strip().strip("/")
    if not slug:
        return None

    base = _base_url()
    page = requests.get(
        f"{base}/api/status-page/{slug}",
        timeout=8,
    )
    page.raise_for_status()
    heartbeat = requests.get(
        f"{base}/api/status-page/heartbeat/{slug}",
        timeout=8,
    )
    heartbeat.raise_for_status()

    page_data = page.json()
    heartbeat_data = heartbeat.json()
    heartbeat_list = heartbeat_data.get("heartbeatList") or {}
    uptime_list = heartbeat_data.get("uptimeList") or {}

    groups = []
    all_monitors = []

    for group in page_data.get("publicGroupList") or []:
        visible = []
        for monitor in group.get("monitorList") or []:
            monitor_id = str(monitor.get("id"))
            beats = heartbeat_list.get(monitor_id)
            if beats is None and monitor_id.isdigit():
                beats = heartbeat_list.get(int(monitor_id), [])
            if not isinstance(beats, list):
                beats = []

            latest = beats[-1] if beats else {}
            status = int(latest.get("status", 2))
            row = {
                "id": monitor.get("id"),
                "name": monitor.get("name") or f"Monitor {monitor_id}",
                "type": monitor.get("type") or "",
                "status": status,
                "ping": latest.get("ping"),
                "last_check": latest.get("time"),
                "message": latest.get("msg") or "",
                "uptime_24h": uptime_list.get(f"{monitor_id}_24"),
            }
            all_monitors.append(row)

            if not _matches(row["name"]):
                continue
            if (
                _bool("UPTIME_KUMA_SHOW_ONLY_PROBLEMS")
                and status == 1
            ):
                continue
            visible.append(row)

        if visible:
            groups.append({
                "name": group.get("name") or "Monitors",
                "monitors": visible,
            })

    return _finalize("status_page", groups, all_monitors)


def _decode_label(value):
    return (
        value
        .replace(r'\"', '"')
        .replace(r'\\', '\\')
        .replace(r'\n', '\n')
    )


def _parse_metrics(text: str):
    metrics = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        match = _METRIC_RE.match(line)
        if not match:
            continue

        metric_name, label_text, value_text = match.groups()
        if metric_name not in {
            "monitor_status",
            "monitor_response_time",
        }:
            continue

        labels = {
            key: _decode_label(value)
            for key, value in _LABEL_RE.findall(label_text or "")
        }

        try:
            value = float(value_text)
        except ValueError:
            continue

        metrics.append((metric_name, labels, value))

    return metrics


def _metrics_data():
    base = _base_url()
    api_key = os.getenv("UPTIME_KUMA_API_KEY", "").strip()
    username = os.getenv("UPTIME_KUMA_USERNAME", "").strip()
    password = os.getenv("UPTIME_KUMA_PASSWORD", "").strip()

    auth = None
    if api_key:
        auth = ("", api_key)
    elif username or password:
        auth = (username, password)

    response = requests.get(
        f"{base}/metrics",
        auth=auth,
        timeout=8,
    )
    response.raise_for_status()

    rows = {}
    for metric, labels, value in _parse_metrics(response.text):
        name = labels.get("monitor_name")
        if not name:
            continue

        identity = (
            name,
            labels.get("monitor_type", ""),
            labels.get("monitor_url", ""),
            labels.get("monitor_hostname", ""),
            labels.get("monitor_port", ""),
        )

        row = rows.setdefault(identity, {
            "name": name,
            "type": labels.get("monitor_type", ""),
            "status": 2,
            "ping": None,
            "last_check": None,
            "uptime_24h": None,
        })

        if metric == "monitor_status":
            row["status"] = int(value)
        elif metric == "monitor_response_time":
            row["ping"] = value

    all_monitors = list(rows.values())
    visible = []
    for row in all_monitors:
        if not _matches(row["name"]):
            continue
        if (
            _bool("UPTIME_KUMA_SHOW_ONLY_PROBLEMS")
            and row["status"] == 1
        ):
            continue
        visible.append(row)

    groups = (
        [{"name": "Monitors", "monitors": visible}]
        if visible else []
    )
    return _finalize("metrics", groups, all_monitors)


def _finalize(mode, groups, all_monitors):
    counts = {
        "up": 0,
        "down": 0,
        "pending": 0,
        "maintenance": 0,
    }
    status_names = {
        0: "down",
        1: "up",
        2: "pending",
        3: "maintenance",
    }
    pings = []

    for monitor in all_monitors:
        state = status_names.get(
            int(monitor.get("status", 2)),
            "pending",
        )
        counts[state] += 1

        if monitor.get("ping") is not None:
            try:
                pings.append(float(monitor["ping"]))
            except Exception:
                pass

    return {
        "mode": mode,
        "counts": counts,
        "total_count": len(all_monitors),
        "visible_count": sum(
            len(group["monitors"]) for group in groups
        ),
        "avg_ping": (
            sum(pings) / len(pings)
            if pings else None
        ),
        "groups": groups,
    }


def get_data():
    cached = _cache.get()
    if cached:
        return cached

    status_page = _status_page_data()
    data = (
        status_page
        if status_page is not None
        else _metrics_data()
    )
    return _cache.set(data)


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "Uptime Kuma",
            "lines": ["Data unavailable"],
        }

    counts = data.get("counts") or {}
    lines = [
        f"{counts.get('up', 0)} UP / {counts.get('down', 0)} DOWN"
    ]

    problems = []
    healthy = []
    for group in data.get("groups") or []:
        for monitor in group.get("monitors") or []:
            if monitor.get("status") != 1:
                problems.append(monitor)
            else:
                healthy.append(monitor)

    for monitor in problems[:3]:
        state = {
            0: "DOWN",
            2: "WAIT",
            3: "MAINT",
        }.get(monitor.get("status"), "?")
        lines.append(
            f"{monitor.get('name', '')[:12]} {state}"
        )

    if not problems:
        for monitor in healthy[:3]:
            ping = monitor.get("ping")
            ping_text = (
                "--"
                if ping is None
                else f"{int(round(float(ping)))}ms"
            )
            lines.append(
                f"{monitor.get('name', '')[:12]} {ping_text}"
            )

    return {
        "title": "Uptime Kuma",
        "lines": lines,
    }
