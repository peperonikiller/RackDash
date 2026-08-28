from __future__ import annotations
import os
import time
from collections import deque
import requests

PLUGIN_ID = "bitaxe"
PLUGIN_NAME = "Bitaxe"
PLUGIN_VERSION = "1.0.0"
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 60
PLUGIN_REFRESH_SECONDS = 2
PLUGIN_ACCENT = "#f6b73c"
PLUGIN_ICON = "ASIC"
PLUGIN_PUBLIC_ERROR = "Bitaxe unavailable"

PLUGIN_CONFIG = [{'key': 'BITAXE_URL', 'label': 'Bitaxe URL', 'type': 'text', 'default': 'http://127.0.0.1', 'required': True}]

BITAXE_URL = os.getenv("BITAXE_URL", "http://127.0.0.1").rstrip("/")
_history = deque(maxlen=120)


def get_data():
    response = requests.get(f"{BITAXE_URL}/api/system/info", timeout=4)
    response.raise_for_status()
    item = response.json()

    hashrate = float(item.get("hashRate_1m", item.get("hashRate", item.get("hashrate", 0))) or 0)
    power = float(item.get("power", 0) or 0)
    _history.append({"t": int(time.time()), "hashrate": hashrate})

    return {
        "model": item.get("ASICModel", item.get("deviceModel", "Bitaxe")),
        "version": item.get("axeOSVersion", item.get("version", "")),
        "hashrate": hashrate,
        "power": power,
        "efficiency": round(power / (hashrate / 1000), 2) if hashrate else 0,
        "temp": float(item.get("temp", item.get("asicTemp", 0)) or 0),
        "vr_temp": float(item.get("vrTemp", 0) or 0),
        "fan_rpm": item.get("fanRpm", 0),
        "fan_pct": item.get("fanspeed", item.get("fanSpeed", 0)),
        "frequency": item.get("frequency", 0),
        "shares_accepted": item.get("sharesAccepted", 0),
        "shares_rejected": item.get("sharesRejected", 0),
        "best_diff": item.get("bestDiff", 0),
        "wifi_rssi": item.get("wifiRSSI", item.get("wifiRssi", 0)),
        "uptime": item.get("uptimeSeconds", 0),
        "paused": bool(item.get("miningPaused", False)),
        "history": list(_history),
    }


PLUGIN_HTML = r'''
<div class="plugin-head">
 <div><span class="eyebrow">BITAXE</span><h1 data-role="title">ASIC Miner</h1><div class="muted" data-role="version"></div></div>
 <span class="status-chip" data-role="state">--</span>
</div>
<div class="metric-grid bitaxe-metrics">
 <article class="metric"><label>HASHRATE</label><strong><span data-role="hashrate">--</span><small> GH/s</small></strong></article>
 <article class="metric"><label>POWER</label><strong><span data-role="power">--</span><small> W</small></strong></article>
 <article class="metric"><label>EFFICIENCY</label><strong><span data-role="efficiency">--</span><small> J/TH</small></strong></article>
 <article class="metric"><label>ASIC TEMP</label><strong><span data-role="temp">--</span><small> °C</small></strong></article>
</div>
<section class="chart-card"><div class="section-label">HASHRATE TREND</div><canvas data-role="chart" width="1180" height="120"></canvas></section>
<div class="chip-row">
 <span data-role="shares"></span><span data-role="best"></span><span data-role="freq"></span><span data-role="fan"></span><span data-role="rssi"></span><span data-role="uptime"></span>
</div>
'''

PLUGIN_CSS = r'''
.plugin-bitaxe .bitaxe-metrics{grid-template-columns:repeat(4,1fr)}
.plugin-bitaxe .metric{border-top:2px solid rgba(246,183,60,.35)}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.bitaxe={
 render(data,root){
  root.querySelector('[data-role="title"]').textContent=data.model||"Bitaxe";
  root.querySelector('[data-role="version"]').textContent=data.version?`AxeOS ${data.version}`:"";
  root.querySelector('[data-role="state"]').textContent=data.paused?"PAUSED":"MINING";
  root.querySelector('[data-role="hashrate"]').textContent=Number(data.hashrate||0).toFixed(0);
  root.querySelector('[data-role="power"]').textContent=Number(data.power||0).toFixed(1);
  root.querySelector('[data-role="efficiency"]').textContent=Number(data.efficiency||0).toFixed(1);
  root.querySelector('[data-role="temp"]').textContent=Number(data.temp||0).toFixed(1);
  root.querySelector('[data-role="shares"]').textContent=`Shares ${data.shares_accepted||0} ✓ / ${data.shares_rejected||0} ✕`;
  root.querySelector('[data-role="best"]').textContent=`Best ${RackDash.compact(data.best_diff)}`;
  root.querySelector('[data-role="freq"]').textContent=`${data.frequency||"--"} MHz`;
  root.querySelector('[data-role="fan"]').textContent=data.fan_rpm?`Fan ${data.fan_rpm} RPM`:`Fan ${data.fan_pct||"--"}%`;
  root.querySelector('[data-role="rssi"]').textContent=`RSSI ${data.wifi_rssi||"--"} dBm`;
  root.querySelector('[data-role="uptime"]').textContent=`Uptime ${RackDash.uptime(data.uptime)}`;
  RackDash.drawLine(root.querySelector('[data-role="chart"]'),(data.history||[]).map(x=>Number(x.hashrate||0)),"#f6b73c");
 }
};
'''
