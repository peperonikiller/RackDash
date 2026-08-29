from __future__ import annotations

import os
import time
from collections import deque

import requests


PLUGIN_ID = "bitaxe"
PLUGIN_NAME = "Bitaxe"
PLUGIN_VERSION = "3.0.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/bitaxe.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 60
PLUGIN_REFRESH_SECONDS = 3
PLUGIN_ACCENT = "#f6b73c"
PLUGIN_ICON = "ASIC"
PLUGIN_PUBLIC_ERROR = "Bitaxe unavailable"

PLUGIN_CONFIG = [
    {
        "key": "BITAXE_URL",
        "label": "Bitaxe URL",
        "type": "text",
        "default": "http://127.0.0.1",
        "required": True,
    }
]

BITAXE_URL = os.getenv(
    "BITAXE_URL",
    "http://127.0.0.1",
).rstrip("/")

_history = deque(maxlen=180)


PLUGIN_HTML = r'''
<div class="bitaxe-shell">
  <section class="surface bitaxe-hero">
    <div class="bitaxe-watermark" aria-hidden="true"></div>

    <div class="bitaxe-hero-copy">
      <span class="eyebrow">OPEN SOURCE BITCOIN MINING</span>
      <h1 data-role="title">Bitaxe</h1>
      <div class="bitaxe-subline">
        <span data-role="asic">ASIC</span>
        <span data-role="version"></span>
        <span data-role="hostname"></span>
      </div>
    </div>

    <div class="bitaxe-state-block">
      <span class="bitaxe-state" data-role="state">--</span>
      <strong data-role="hashrate">--</strong>
      <small>GH/s HASHRATE</small>
    </div>
  </section>

  <section class="bitaxe-metrics">
    <article class="surface bitaxe-metric">
      <span>POWER</span>
      <strong><b data-role="power">--</b> W</strong>
      <small data-role="voltage-current">--</small>
    </article>

    <article class="surface bitaxe-metric">
      <span>EFFICIENCY</span>
      <strong><b data-role="efficiency">--</b> J/TH</strong>
      <small data-role="efficiency-label">--</small>
    </article>

    <article class="surface bitaxe-metric thermal">
      <span>ASIC TEMP</span>
      <strong><b data-role="temp">--</b> °C</strong>
      <small data-role="temp-label">--</small>
    </article>

    <article class="surface bitaxe-metric thermal">
      <span>VR TEMP</span>
      <strong><b data-role="vr-temp">--</b> °C</strong>
      <small>voltage regulator</small>
    </article>

    <article class="surface bitaxe-metric">
      <span>FAN</span>
      <strong data-role="fan">--</strong>
      <small data-role="fan-sub">cooling</small>
    </article>

    <article class="surface bitaxe-metric">
      <span>WIFI</span>
      <strong data-role="rssi">--</strong>
      <small data-role="wifi-label">signal</small>
    </article>
  </section>

  <section class="bitaxe-main-grid">
    <article class="surface bitaxe-chart-card">
      <div class="bitaxe-section-head">
        <div>
          <div class="section-label">MINING PERFORMANCE</div>
          <div class="muted bitaxe-small">Recent hashrate history</div>
        </div>
        <div class="bitaxe-chart-current">
          <strong data-role="chart-hashrate">--</strong>
          <span>GH/s</span>
        </div>
      </div>

      <div class="bitaxe-chart-wrap">
        <canvas data-role="chart" width="1200" height="210"></canvas>
      </div>

      <div class="bitaxe-chart-footer">
        <span data-role="frequency">-- MHz</span>
        <span data-role="core-voltage">Core -- mV</span>
        <span data-role="uptime">Uptime --</span>
      </div>
    </article>

    <article class="surface bitaxe-pool-card">
      <div class="bitaxe-section-head">
        <div>
          <div class="section-label">MINING POOL</div>
          <div class="muted bitaxe-small">Current stratum connection</div>
        </div>
        <span class="pool-chip" data-role="pool-status">CONNECTED</span>
      </div>

      <div class="bitaxe-pool-name" data-role="pool">--</div>
      <div class="bitaxe-worker" data-role="worker">--</div>

      <div class="bitaxe-share-grid">
        <div>
          <span>ACCEPTED</span>
          <strong data-role="accepted">0</strong>
        </div>
        <div>
          <span>REJECTED</span>
          <strong data-role="rejected">0</strong>
        </div>
        <div>
          <span>ACCEPT RATE</span>
          <strong data-role="accept-rate">--</strong>
        </div>
        <div>
          <span>BEST DIFF</span>
          <strong data-role="best">--</strong>
        </div>
      </div>
    </article>
  </section>

  <section class="bitaxe-bottom-grid">
    <article class="surface">
      <div class="bitaxe-section-head">
        <div>
          <div class="section-label">HARDWARE</div>
          <div class="muted bitaxe-small">ASIC operating parameters</div>
        </div>
      </div>
      <div class="bitaxe-detail-grid" data-role="hardware"></div>
    </article>

    <article class="surface">
      <div class="bitaxe-section-head">
        <div>
          <div class="section-label">SYSTEM HEALTH</div>
          <div class="muted bitaxe-small">Network and runtime information</div>
        </div>
      </div>
      <div class="bitaxe-detail-grid" data-role="system"></div>
    </article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-bitaxe{
  --axe:#f6b73c;
  --axe-soft:rgba(246,183,60,.075);
  --axe-line:rgba(246,183,60,.28);
}
.plugin-bitaxe .bitaxe-shell{display:grid;gap:var(--gap)}
.plugin-bitaxe .bitaxe-hero{
  position:relative;
  overflow:hidden;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:1rem;
  min-height:8.5rem;
  border-left:3px solid var(--axe);
  background:
    radial-gradient(circle at 10% 35%,rgba(246,183,60,.10),transparent 28%),
    linear-gradient(110deg,rgba(246,183,60,.045),rgba(255,255,255,.008) 50%,rgba(255,255,255,.004));
}
.plugin-bitaxe .bitaxe-watermark{
  position:absolute;
  right:10rem;
  top:50%;
  width:28rem;
  height:10rem;
  transform:translateY(-50%);
  opacity:.055;
  pointer-events:none;
  display:grid;
  place-items:center;
  filter:none;
}
.plugin-bitaxe .bitaxe-watermark::before{
  content:"BITAXE";
  font-size:clamp(3rem,8vw,7rem);
  font-weight:1000;
  font-style:italic;
  letter-spacing:-.07em;
  color:var(--axe);
  transform:skew(-8deg);
}
.plugin-bitaxe .bitaxe-hero-copy{position:relative;z-index:1;min-width:0}
.plugin-bitaxe .bitaxe-hero h1{
  margin:.12rem 0 .18rem;
  font-size:clamp(1.7rem,3.4vw,3rem);
  line-height:1;
  letter-spacing:-.035em;
}
.plugin-bitaxe .bitaxe-subline{
  display:flex;
  gap:.4rem;
  flex-wrap:wrap;
  color:var(--muted);
  font-size:.5rem;
}
.plugin-bitaxe .bitaxe-subline span:not(:empty)+span:not(:empty)::before{content:"·";margin-right:.4rem}
.plugin-bitaxe .bitaxe-state-block{
  position:relative;
  z-index:1;
  min-width:11rem;
  text-align:right;
}
.plugin-bitaxe .bitaxe-state{
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
.plugin-bitaxe .bitaxe-state.paused{
  border-color:rgba(246,183,60,.42);
  background:rgba(246,183,60,.07);
  color:#f8c75f;
}
.plugin-bitaxe .bitaxe-state-block strong{
  display:block;
  margin-top:.25rem;
  font-size:clamp(2.5rem,6vw,5.6rem);
  line-height:.88;
  letter-spacing:-.065em;
}
.plugin-bitaxe .bitaxe-state-block small{
  display:block;
  margin-top:.22rem;
  color:var(--muted);
  font-size:.43rem;
  font-weight:850;
  letter-spacing:.05em;
}

.plugin-bitaxe .bitaxe-metrics{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:var(--gap);
}
.plugin-bitaxe .bitaxe-metric{
  min-width:0;
  border-top:1px solid rgba(246,183,60,.16);
}
.plugin-bitaxe .bitaxe-metric>span{
  display:block;
  color:var(--muted);
  font-size:.43rem;
  font-weight:850;
  letter-spacing:.05em;
}
.plugin-bitaxe .bitaxe-metric>strong{
  display:block;
  margin-top:.12rem;
  font-size:clamp(.9rem,1.7vw,1.35rem);
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-bitaxe .bitaxe-metric>strong b{font:inherit}
.plugin-bitaxe .bitaxe-metric>small{
  display:block;
  margin-top:.08rem;
  color:var(--muted);
  font-size:.42rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.plugin-bitaxe .bitaxe-main-grid{
  display:grid;
  grid-template-columns:minmax(0,1.4fr) minmax(320px,.6fr);
  gap:var(--gap);
}
.plugin-bitaxe .bitaxe-section-head{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:.7rem;
}
.plugin-bitaxe .bitaxe-small{font-size:.45rem}
.plugin-bitaxe .bitaxe-chart-current{text-align:right}
.plugin-bitaxe .bitaxe-chart-current strong{font-size:.9rem}
.plugin-bitaxe .bitaxe-chart-current span{font-size:.45rem;color:var(--muted)}
.plugin-bitaxe .bitaxe-chart-wrap{
  position:relative;
  height:13rem;
  margin-top:.45rem;
  border-radius:.45rem;
  overflow:hidden;
  background:
    linear-gradient(rgba(246,183,60,.025),rgba(246,183,60,.005)),
    repeating-linear-gradient(0deg,transparent,transparent 31px,rgba(255,255,255,.025) 32px);
}
.plugin-bitaxe .bitaxe-chart-wrap canvas{width:100%;height:100%}
.plugin-bitaxe .bitaxe-chart-footer{
  display:flex;
  justify-content:space-between;
  gap:.6rem;
  flex-wrap:wrap;
  margin-top:.4rem;
  color:var(--muted);
  font-size:.46rem;
}

.plugin-bitaxe .pool-chip{
  padding:.22rem .36rem;
  border-radius:.3rem;
  border:1px solid rgba(80,210,120,.32);
  background:rgba(80,210,120,.045);
  color:#78e79c;
  font-size:.44rem;
  font-weight:900;
}
.plugin-bitaxe .bitaxe-pool-name{
  margin-top:.7rem;
  font-size:clamp(.85rem,1.5vw,1.2rem);
  font-weight:850;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-bitaxe .bitaxe-worker{
  margin-top:.12rem;
  color:var(--muted);
  font-size:.48rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-bitaxe .bitaxe-share-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:.4rem;
  margin-top:.7rem;
}
.plugin-bitaxe .bitaxe-share-grid>div{
  padding:.52rem;
  border-radius:.42rem;
  border:1px solid var(--border);
  background:rgba(255,255,255,.012);
}
.plugin-bitaxe .bitaxe-share-grid span{
  display:block;
  color:var(--muted);
  font-size:.41rem;
  font-weight:850;
}
.plugin-bitaxe .bitaxe-share-grid strong{
  display:block;
  margin-top:.1rem;
  font-size:.72rem;
}

.plugin-bitaxe .bitaxe-bottom-grid{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:var(--gap);
}
.plugin-bitaxe .bitaxe-detail-grid{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:.4rem;
  margin-top:.55rem;
}
.plugin-bitaxe .axe-detail{
  padding:.5rem;
  min-width:0;
  border-radius:.42rem;
  border:1px solid var(--border);
  background:rgba(255,255,255,.012);
}
.plugin-bitaxe .axe-detail span{
  display:block;
  color:var(--muted);
  font-size:.4rem;
  font-weight:850;
  letter-spacing:.04em;
}
.plugin-bitaxe .axe-detail strong{
  display:block;
  margin-top:.1rem;
  font-size:.58rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

@media(max-width:1100px){
  .plugin-bitaxe .bitaxe-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}
  .plugin-bitaxe .bitaxe-main-grid{grid-template-columns:1fr}
}
@media(max-width:760px){
  .plugin-bitaxe .bitaxe-hero{align-items:flex-start;flex-direction:column}
  .plugin-bitaxe .bitaxe-state-block{text-align:left}
  .plugin-bitaxe .bitaxe-watermark{right:-8rem}
  .plugin-bitaxe .bitaxe-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
  .plugin-bitaxe .bitaxe-bottom-grid{grid-template-columns:1fr}
  .plugin-bitaxe .bitaxe-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.bitaxe={
  tempLabel(temp){
    const value=Number(temp||0);
    if(value>=80)return "Hot";
    if(value>=70)return "Warm";
    if(value>0)return "Healthy";
    return "--";
  },

  wifiLabel(rssi){
    const value=Number(rssi||-100);
    if(value>=-50)return "Excellent signal";
    if(value>=-60)return "Good signal";
    if(value>=-70)return "Fair signal";
    return "Weak signal";
  },

  efficiencyLabel(value){
    const v=Number(value||0);
    if(!v)return "--";
    if(v<=15)return "Excellent";
    if(v<=20)return "Efficient";
    if(v<=25)return "Normal";
    return "High power / TH";
  },

  detailRows(rows){
    return rows
      .filter(([,value])=>value!==null&&value!==undefined&&String(value)!=="")
      .map(([label,value])=>`
        <div class="axe-detail">
          <span>${RackDash.escape(label)}</span>
          <strong title="${RackDash.escape(String(value))}">${RackDash.escape(String(value))}</strong>
        </div>
      `).join("");
  },

  render(data,root){
    const paused=!!data.paused;
    const state=root.querySelector('[data-role="state"]');

    root.querySelector('[data-role="title"]').textContent=data.model||"Bitaxe";
    root.querySelector('[data-role="asic"]').textContent=data.asic_model||data.model||"ASIC";
    root.querySelector('[data-role="version"]').textContent=data.version?`AxeOS ${data.version}`:"";
    root.querySelector('[data-role="hostname"]').textContent=data.hostname||"";

    state.textContent=paused?"PAUSED":"MINING";
    state.className=`bitaxe-state ${paused?"paused":""}`;

    root.querySelector('[data-role="hashrate"]').textContent=Number(data.hashrate||0).toFixed(0);
    root.querySelector('[data-role="chart-hashrate"]').textContent=Number(data.hashrate||0).toFixed(0);
    root.querySelector('[data-role="power"]').textContent=Number(data.power||0).toFixed(1);
    root.querySelector('[data-role="efficiency"]').textContent=Number(data.efficiency||0).toFixed(1);
    root.querySelector('[data-role="efficiency-label"]').textContent=this.efficiencyLabel(data.efficiency);

    root.querySelector('[data-role="temp"]').textContent=Number(data.temp||0).toFixed(1);
    root.querySelector('[data-role="temp-label"]').textContent=this.tempLabel(data.temp);
    root.querySelector('[data-role="vr-temp"]').textContent=Number(data.vr_temp||0).toFixed(1);

    root.querySelector('[data-role="voltage-current"]').textContent=
      data.voltage?`${Number(data.voltage).toFixed(1)} V · ${Number(data.current||0).toFixed(1)} A`:"";

    root.querySelector('[data-role="fan"]').textContent=
      data.fan_rpm?`${Math.round(data.fan_rpm)} RPM`:`${Math.round(data.fan_pct||0)}%`;
    root.querySelector('[data-role="fan-sub"]').textContent=
      data.fan_rpm&&data.fan_pct!=null?`${Math.round(data.fan_pct)}% command`:"cooling";

    root.querySelector('[data-role="rssi"]').textContent=`${data.wifi_rssi??"--"} dBm`;
    root.querySelector('[data-role="wifi-label"]').textContent=this.wifiLabel(data.wifi_rssi);

    root.querySelector('[data-role="frequency"]').textContent=`${data.frequency||"--"} MHz`;
    root.querySelector('[data-role="core-voltage"]').textContent=
      data.core_voltage?`Core ${data.core_voltage} mV`:"Core --";
    root.querySelector('[data-role="uptime"]').textContent=`Uptime ${RackDash.uptime(data.uptime||0)}`;

    root.querySelector('[data-role="pool"]').textContent=
      data.pool_url?`${data.pool_url}${data.pool_port?`:${data.pool_port}`:""}`:"Pool unavailable";
    root.querySelector('[data-role="worker"]').textContent=data.pool_user||"";

    root.querySelector('[data-role="accepted"]').textContent=RackDash.compact(data.shares_accepted||0);
    root.querySelector('[data-role="rejected"]').textContent=RackDash.compact(data.shares_rejected||0);
    root.querySelector('[data-role="accept-rate"]').textContent=
      data.accept_rate!=null?`${Number(data.accept_rate).toFixed(2)}%`:"--";
    root.querySelector('[data-role="best"]').textContent=RackDash.compact(data.best_diff||0);

    root.querySelector('[data-role="hardware"]').innerHTML=this.detailRows([
      ["ASIC",data.asic_model||data.model],
      ["FREQUENCY",data.frequency?`${data.frequency} MHz`:""],
      ["CORE VOLTAGE",data.core_voltage?`${data.core_voltage} mV`:""],
      ["INPUT VOLTAGE",data.voltage?`${Number(data.voltage).toFixed(2)} V`:""],
      ["CURRENT",data.current?`${Number(data.current).toFixed(2)} A`:""],
      ["BOARD",data.board_version||""],
      ["ASIC TEMP",`${Number(data.temp||0).toFixed(1)} °C`],
      ["VR TEMP",`${Number(data.vr_temp||0).toFixed(1)} °C`],
      ["FAN",data.fan_rpm?`${Math.round(data.fan_rpm)} RPM`:`${Math.round(data.fan_pct||0)}%`],
    ]);

    root.querySelector('[data-role="system"]').innerHTML=this.detailRows([
      ["HOSTNAME",data.hostname||""],
      ["AXEOS",data.version||""],
      ["IP",data.ip||""],
      ["WIFI",data.wifi_ssid||""],
      ["SIGNAL",data.wifi_rssi!=null?`${data.wifi_rssi} dBm`:""],
      ["UPTIME",RackDash.uptime(data.uptime||0)],
      ["FREE HEAP",data.free_heap?`${Math.round(data.free_heap/1024)} KB`:""],
      ["BLOCK HEIGHT",data.block_height?RackDash.compact(data.block_height):""],
      ["BEST SESSION",data.best_session_diff?RackDash.compact(data.best_session_diff):""],
    ]);

    RackDash.drawLine(
      root.querySelector('[data-role="chart"]'),
      (data.history||[]).map(x=>Number(x.hashrate||0)),
      "#f6b73c"
    );
  }
};
'''


def _number(item, *keys, default=0):
    for key in keys:
        value = item.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return default


def _integer(item, *keys, default=0):
    return int(_number(item, *keys, default=default))


def _text(item, *keys, default=""):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return default


def get_data():
    response = requests.get(
        f"{BITAXE_URL}/api/system/info",
        timeout=5,
        headers={
            "User-Agent": "RackDash-\1/3.0.0",
        },
    )
    response.raise_for_status()
    item = response.json()

    hashrate = _number(
        item,
        "hashRate_1m",
        "hashRate",
        "hashrate",
    )

    power = _number(
        item,
        "power",
        "powerWatts",
    )

    temp = _number(
        item,
        "temp",
        "asicTemp",
        "temperature",
    )

    vr_temp = _number(
        item,
        "vrTemp",
        "vrmTemp",
    )

    accepted = _integer(
        item,
        "sharesAccepted",
        "acceptedShares",
    )

    rejected = _integer(
        item,
        "sharesRejected",
        "rejectedShares",
    )

    total_shares = accepted + rejected
    accept_rate = (
        round(
            accepted / total_shares * 100,
            2,
        )
        if total_shares
        else None
    )

    _history.append({
        "t": int(time.time()),
        "hashrate": hashrate,
        "temp": temp,
        "power": power,
    })

    voltage = _number(
        item,
        "voltage",
        "inputVoltage",
    )

    current = _number(
        item,
        "current",
        "currentA",
    )

    # Some AxeOS builds expose millivolts, others volts.
    if voltage > 100:
        voltage = voltage / 1000

    if not current and voltage:
        current = power / voltage if voltage else 0

    core_voltage = _number(
        item,
        "coreVoltage",
        "coreVoltageActual",
        "voltageCore",
    )

    if 0 < core_voltage < 10:
        core_voltage *= 1000

    return {
        "model": _text(
            item,
            "deviceModel",
            "boardVersion",
            default="Bitaxe",
        ),
        "asic_model": _text(
            item,
            "ASICModel",
            "asicModel",
        ),
        "board_version": _text(
            item,
            "boardVersion",
            "hardwareVersion",
        ),
        "version": _text(
            item,
            "axeOSVersion",
            "version",
        ),
        "hostname": _text(
            item,
            "hostname",
            "hostName",
        ),
        "ip": _text(
            item,
            "ip",
            "ipAddress",
        ),

        "hashrate": hashrate,
        "power": power,
        "efficiency": (
            round(
                power / (hashrate / 1000),
                2,
            )
            if hashrate
            else 0
        ),

        "temp": temp,
        "vr_temp": vr_temp,
        "fan_rpm": _integer(
            item,
            "fanRpm",
            "fanRPM",
        ),
        "fan_pct": _number(
            item,
            "fanspeed",
            "fanSpeed",
            "fanPercent",
        ),

        "frequency": _number(
            item,
            "frequency",
            "asicFrequency",
        ),
        "core_voltage": round(
            core_voltage,
            0,
        ),
        "voltage": voltage,
        "current": current,

        "shares_accepted": accepted,
        "shares_rejected": rejected,
        "accept_rate": accept_rate,
        "best_diff": _number(
            item,
            "bestDiff",
            "bestDifficulty",
        ),
        "best_session_diff": _number(
            item,
            "bestSessionDiff",
            "bestSessionDifficulty",
        ),

        "pool_url": _text(
            item,
            "stratumURL",
            "poolURL",
            "pool",
        ),
        "pool_port": _text(
            item,
            "stratumPort",
            "poolPort",
        ),
        "pool_user": _text(
            item,
            "stratumUser",
            "poolUser",
            "worker",
        ),

        "wifi_rssi": _integer(
            item,
            "wifiRSSI",
            "wifiRssi",
            default=-100,
        ),
        "wifi_ssid": _text(
            item,
            "ssid",
            "wifiSSID",
        ),

        "uptime": _integer(
            item,
            "uptimeSeconds",
            "uptime",
        ),
        "free_heap": _integer(
            item,
            "freeHeap",
            "free_heap",
        ),
        "block_height": _integer(
            item,
            "blockHeight",
            "block_height",
        ),
        "paused": bool(
            item.get(
                "miningPaused",
                False,
            )
        ),
        "history": list(_history),
    }


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "Bitaxe",
            "lines": [
                "Miner unavailable",
            ],
        }

    state = (
        "PAUSED"
        if data.get("paused")
        else "MINING"
    )

    return {
        "title": "Bitaxe",
        "lines": [
            (
                f"{state} "
                f"{float(data.get('hashrate', 0)):.0f} GH/s"
            ),
            (
                f"{float(data.get('power', 0)):.1f}W "
                f"{float(data.get('efficiency', 0)):.1f} J/TH"
            ),
            (
                f"ASIC {float(data.get('temp', 0)):.0f}C "
                f"Fan {int(data.get('fan_pct') or 0)}%"
            ),
        ],
    }
