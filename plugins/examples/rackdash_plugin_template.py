from __future__ import annotations

import os
import time

import requests

from _shared import TTLCache


# ============================================================
# RackDash Plugin Metadata
# ============================================================

PLUGIN_ID = "my_plugin"
PLUGIN_NAME = "My Plugin"
PLUGIN_VERSION = "1.0.0"

# Set True only for plugins that live in the official RackDash repository.
PLUGIN_OFFICIAL = False
PLUGIN_SOURCE_PATH = ""

PLUGIN_MIN_RACKDASH = "3.0.0"
PLUGIN_MAX_RACKDASH = ""

# Common capabilities:
#   network
#   i2c
#   argb
#   custom_routes
PLUGIN_CAPABILITIES = ["network", "i2c", "argb"]

PLUGIN_GITHUB = ""
PLUGIN_ORDER = 100
PLUGIN_REFRESH_SECONDS = 30
PLUGIN_ACCENT = "#6fb7ff"
PLUGIN_ICON = "APP"
PLUGIN_PUBLIC_ERROR = "Plugin unavailable"


# ============================================================
# Plugin Settings
# ============================================================

PLUGIN_CONFIG = [
    {
        "key": "MY_PLUGIN_URL",
        "label": "Service URL",
        "type": "text",
        "default": "http://127.0.0.1:8000",
        "required": True,
        "help": "Base URL for the service this plugin connects to.",
    },
    {
        "key": "MY_PLUGIN_TOKEN",
        "label": "API Token",
        "type": "secret",
        "default": "",
        "required": False,
        "help": "Optional API token. This value stays server-side.",
    },
]

MY_PLUGIN_URL = os.getenv(
    "MY_PLUGIN_URL",
    "http://127.0.0.1:8000",
).rstrip("/")

MY_PLUGIN_TOKEN = os.getenv(
    "MY_PLUGIN_TOKEN",
    "",
).strip()


# ============================================================
# Caches / Runtime State
# ============================================================

_data_cache = TTLCache(15)
_history = []


# ============================================================
# Frontend Markup
# ============================================================

PLUGIN_HTML = r'''
<div class="my-plugin-shell">
  <section class="surface my-plugin-hero">
    <div>
      <span class="eyebrow">MY PLUGIN</span>
      <h1 data-role="title">My Plugin</h1>
      <div class="muted" data-role="subtitle">Waiting for data...</div>
    </div>

    <div class="my-plugin-status-wrap">
      <span class="my-plugin-status" data-role="status">--</span>
      <strong data-role="primary">--</strong>
      <small data-role="primary-label">PRIMARY METRIC</small>
    </div>
  </section>

  <section class="my-plugin-metrics">
    <article class="surface my-plugin-metric">
      <span>METRIC ONE</span>
      <strong data-role="metric-one">--</strong>
      <small data-role="metric-one-sub">details</small>
    </article>

    <article class="surface my-plugin-metric">
      <span>METRIC TWO</span>
      <strong data-role="metric-two">--</strong>
      <small data-role="metric-two-sub">details</small>
    </article>

    <article class="surface my-plugin-metric">
      <span>METRIC THREE</span>
      <strong data-role="metric-three">--</strong>
      <small data-role="metric-three-sub">details</small>
    </article>

    <article class="surface my-plugin-metric">
      <span>UPTIME</span>
      <strong data-role="uptime">--</strong>
      <small>service uptime</small>
    </article>
  </section>

  <section class="my-plugin-main-grid">
    <article class="surface">
      <div class="my-plugin-section-head">
        <div>
          <div class="section-label">ACTIVITY</div>
          <div class="muted my-plugin-small">Recent values</div>
        </div>

        <strong data-role="chart-value">--</strong>
      </div>

      <div class="my-plugin-chart-wrap">
        <canvas data-role="chart" width="1200" height="220"></canvas>
      </div>
    </article>

    <article class="surface">
      <div class="my-plugin-section-head">
        <div>
          <div class="section-label">DETAILS</div>
          <div class="muted my-plugin-small">Service information</div>
        </div>
      </div>

      <div class="my-plugin-details" data-role="details"></div>
    </article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-my_plugin{
  --my-plugin:#6fb7ff;
  --my-plugin-soft:rgba(111,183,255,.07);
  --my-plugin-line:rgba(111,183,255,.25);
}

.plugin-my_plugin .my-plugin-shell{
  display:grid;
  gap:var(--gap);
}

.plugin-my_plugin .my-plugin-hero{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:1rem;
  border-left:3px solid var(--my-plugin);
  background:
    radial-gradient(circle at 10% 35%,rgba(111,183,255,.09),transparent 30%),
    linear-gradient(110deg,rgba(111,183,255,.04),rgba(255,255,255,.006));
}

.plugin-my_plugin .my-plugin-hero h1{
  margin:.12rem 0 .15rem;
  font-size:clamp(1.6rem,3.2vw,2.8rem);
  line-height:1;
}

.plugin-my_plugin .my-plugin-status-wrap{
  text-align:right;
  min-width:10rem;
}

.plugin-my_plugin .my-plugin-status{
  display:inline-block;
  padding:.25rem .42rem;
  border-radius:.32rem;
  border:1px solid rgba(80,210,120,.35);
  background:rgba(80,210,120,.055);
  color:#78e79c;
  font-size:.46rem;
  font-weight:900;
  letter-spacing:.05em;
}

.plugin-my_plugin .my-plugin-status.warning{
  border-color:rgba(246,183,60,.4);
  background:rgba(246,183,60,.06);
  color:#f6c65d;
}

.plugin-my_plugin .my-plugin-status.error{
  border-color:rgba(255,86,96,.4);
  background:rgba(255,86,96,.06);
  color:#ff7b85;
}

.plugin-my_plugin .my-plugin-status-wrap strong{
  display:block;
  margin-top:.25rem;
  font-size:clamp(2rem,5vw,4.5rem);
  line-height:.9;
}

.plugin-my_plugin .my-plugin-status-wrap small{
  display:block;
  margin-top:.2rem;
  color:var(--muted);
  font-size:.42rem;
  font-weight:850;
  letter-spacing:.05em;
}

.plugin-my_plugin .my-plugin-metrics{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:var(--gap);
}

.plugin-my_plugin .my-plugin-metric{
  min-width:0;
  border-top:1px solid var(--my-plugin-line);
}

.plugin-my_plugin .my-plugin-metric>span{
  display:block;
  color:var(--muted);
  font-size:.43rem;
  font-weight:850;
  letter-spacing:.05em;
}

.plugin-my_plugin .my-plugin-metric>strong{
  display:block;
  margin-top:.12rem;
  font-size:clamp(.9rem,1.7vw,1.35rem);
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.plugin-my_plugin .my-plugin-metric>small{
  display:block;
  margin-top:.08rem;
  color:var(--muted);
  font-size:.42rem;
}

.plugin-my_plugin .my-plugin-main-grid{
  display:grid;
  grid-template-columns:minmax(0,1.4fr) minmax(300px,.6fr);
  gap:var(--gap);
}

.plugin-my_plugin .my-plugin-section-head{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:.6rem;
}

.plugin-my_plugin .my-plugin-small{
  font-size:.45rem;
}

.plugin-my_plugin .my-plugin-chart-wrap{
  height:14rem;
  margin-top:.5rem;
  border-radius:.45rem;
  overflow:hidden;
  background:
    linear-gradient(rgba(111,183,255,.025),rgba(111,183,255,.005)),
    repeating-linear-gradient(0deg,transparent,transparent 31px,rgba(255,255,255,.025) 32px);
}

.plugin-my_plugin .my-plugin-chart-wrap canvas{
  width:100%;
  height:100%;
}

.plugin-my_plugin .my-plugin-details{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:.4rem;
  margin-top:.55rem;
}

.plugin-my_plugin .my-plugin-detail{
  min-width:0;
  padding:.5rem;
  border:1px solid var(--border);
  border-radius:.4rem;
  background:rgba(255,255,255,.012);
}

.plugin-my_plugin .my-plugin-detail span{
  display:block;
  color:var(--muted);
  font-size:.4rem;
  font-weight:850;
  letter-spacing:.04em;
}

.plugin-my_plugin .my-plugin-detail strong{
  display:block;
  margin-top:.1rem;
  font-size:.58rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

@media(max-width:950px){
  .plugin-my_plugin .my-plugin-main-grid{
    grid-template-columns:1fr;
  }
}

@media(max-width:720px){
  .plugin-my_plugin .my-plugin-hero{
    flex-direction:column;
    align-items:flex-start;
  }

  .plugin-my_plugin .my-plugin-status-wrap{
    text-align:left;
  }

  .plugin-my_plugin .my-plugin-metrics{
    grid-template-columns:repeat(2,minmax(0,1fr));
  }
}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.my_plugin={
  setText(root,role,value){
    const el=root.querySelector(`[data-role="${role}"]`);
    if(el)el.textContent=value;
  },

  detailRows(rows){
    return rows
      .filter(([,value])=>
        value!==null &&
        value!==undefined &&
        String(value)!==""
      )
      .map(([label,value])=>`
        <div class="my-plugin-detail">
          <span>${RackDash.escape(label)}</span>
          <strong title="${RackDash.escape(String(value))}">
            ${RackDash.escape(String(value))}
          </strong>
        </div>
      `).join("");
  },

  render(data,root){
    const status=String(data.status||"online").toLowerCase();

    this.setText(root,"title",data.title||"My Plugin");
    this.setText(root,"subtitle",data.subtitle||"Connected");

    const statusNode=root.querySelector('[data-role="status"]');
    if(statusNode){
      statusNode.textContent=status.toUpperCase();
      statusNode.className=`my-plugin-status ${status}`;
    }

    this.setText(root,"primary",Number(data.primary||0).toFixed(1));
    this.setText(root,"primary-label",data.primary_label||"PRIMARY METRIC");

    this.setText(root,"metric-one",data.metric_one??"--");
    this.setText(root,"metric-one-sub",data.metric_one_sub||"");

    this.setText(root,"metric-two",data.metric_two??"--");
    this.setText(root,"metric-two-sub",data.metric_two_sub||"");

    this.setText(root,"metric-three",data.metric_three??"--");
    this.setText(root,"metric-three-sub",data.metric_three_sub||"");

    this.setText(root,"uptime",RackDash.uptime(data.uptime||0));

    this.setText(
      root,
      "chart-value",
      data.primary!=null?Number(data.primary).toFixed(1):"--"
    );

    root.querySelector('[data-role="details"]').innerHTML=this.detailRows([
      ["HOST",data.host||""],
      ["VERSION",data.version||""],
      ["LAST UPDATE",data.last_update||""],
      ["EXAMPLE",data.example_detail||""],
    ]);

    RackDash.drawLine(
      root.querySelector('[data-role="chart"]'),
      (data.history||[]).map(item=>Number(item.value||0)),
      "#6fb7ff"
    );
  }
};
'''


def _headers():
    headers = {
        "User-Agent": "RackDash-MyPlugin/1.0.0"
    }

    if MY_PLUGIN_TOKEN:
        headers["Authorization"] = f"Bearer {MY_PLUGIN_TOKEN}"

    return headers


def _request_json(path):
    response = requests.get(
        f"{MY_PLUGIN_URL}{path}",
        timeout=6,
        headers=_headers(),
    )
    response.raise_for_status()
    return response.json()


def get_data():
    cached = _data_cache.get()
    if cached is not None:
        return dict(cached)

    # Replace this example block with your real service request.
    # Example:
    # payload = _request_json("/api/status")

    now = int(time.time())
    primary = 42.0

    _history.append({
        "t": now,
        "value": primary,
    })

    del _history[:-120]

    data = {
        "status": "online",
        "title": "My Plugin",
        "subtitle": "Template data",

        "primary": primary,
        "primary_label": "PRIMARY METRIC",

        "metric_one": "123",
        "metric_one_sub": "example value",

        "metric_two": "45%",
        "metric_two_sub": "example value",

        "metric_three": "67",
        "metric_three_sub": "example value",

        "uptime": 86400,

        "host": MY_PLUGIN_URL,
        "version": PLUGIN_VERSION,
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "example_detail": "Replace me",

        "history": list(_history),
    }

    return _data_cache.set(data)


# Optional custom routes:
#
# If you add register_routes(app):
#   1. Add "custom_routes" to PLUGIN_CAPABILITIES.
#   2. A full RackDash restart is required when routes change.
#
# def register_routes(app):
#     @app.get("/api/plugin/my_plugin/example")
#     def my_plugin_example():
#         return {"ok": True}


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "My Plugin",
            "lines": [
                "Plugin unavailable",
            ],
        }

    return {
        "title": "My Plugin",
        "lines": [
            str(data.get("status","unknown")).upper(),
            f"Value {float(data.get('primary',0)):.1f}",
            f"Up {int(data.get('uptime',0)) // 3600}h",
        ],
    }

# ============================================================
# Optional RackDash ARGB Lighting Hook
# ============================================================
#
# Add "argb" to PLUGIN_CAPABILITIES when using this hook.
#
# RackDash calls get_argb_data() in the background. Return None or {} when the
# plugin does not want control. When multiple plugins request lighting, the
# highest priority wins; ties follow plugin order.
#
# IMPORTANT:
#   Plugins cannot control global brightness. RackDash deliberately ignores
#   "brightness" and "global_brightness" keys. The user always owns brightness
#   from Admin -> Display & Hardware.
#
# Core RackDash status also has higher priority than plugins:
#   failure detected -> red breathe
#   update available -> orange breathe
#   plugin request   -> plugin effect
#   no plugin hook   -> RackDash green breathe
#
# Supported effects:
#   solid
#   breathe
#   pulse
#   chase
#   rainbow
#   pixels
#
# Colors use #RRGGBB strings.
#
# Example:
#
# def get_argb_data():
#     try:
#         data = get_data()
#     except Exception:
#         return None
#
#     if str(data.get("status", "")).lower() != "online":
#         return None
#
#     return {
#         "effect": "chase",
#         "color": "#6fb7ff",
#         "secondary": "#081117",
#         "speed": 2.5,
#         "priority": 50,
#     }
#
# For direct per-pixel control:
#
# def get_argb_data():
#     return {
#         "effect": "pixels",
#         "pixels": [
#             "#ff0000",
#             "#00ff00",
#             "#0000ff",
#         ],
#         "priority": 60,
#     }

