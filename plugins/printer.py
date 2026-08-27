from __future__ import annotations
import os
import requests

PLUGIN_ID = "printer"
PLUGIN_NAME = "3D Printer"
PLUGIN_VERSION = "1.0.0"
PLUGIN_GITHUB = "https://github.com/YOUR_GITHUB_USERNAME/RackDash"
PLUGIN_ORDER = 50
PLUGIN_REFRESH_SECONDS = 2
PLUGIN_ACCENT = "#6fb7ff"
PLUGIN_ICON = "PRINT"
PLUGIN_PUBLIC_ERROR = "3D printer unavailable"

PLUGIN_CONFIG = [{'key': 'KLIPPER_URL', 'label': 'Moonraker URL', 'type': 'text', 'default': 'http://127.0.0.1:7125', 'required': True}]

KLIPPER_URL = os.getenv("KLIPPER_URL", "http://127.0.0.1:7125").rstrip("/")


def get_data():
    query = (
        "/printer/objects/query?"
        "webhooks&print_stats&virtual_sdcard&extruder=temperature,target,power"
        "&heater_bed=temperature,target,power&fan=speed,rpm"
    )
    response = requests.get(f"{KLIPPER_URL}{query}", timeout=4)
    response.raise_for_status()
    status = response.json().get("result", {}).get("status", {})
    stats = status.get("print_stats", {})
    sd = status.get("virtual_sdcard", {})
    extruder = status.get("extruder", {})
    bed = status.get("heater_bed", {})
    fan = status.get("fan", {})
    info = stats.get("info", {}) or {}

    progress = float(sd.get("progress", 0) or 0)
    duration = float(stats.get("print_duration", 0) or 0)
    eta = max(0, int(duration / progress - duration)) if progress > .005 and duration > 0 else 0

    return {
        "state": stats.get("state", "standby"),
        "filename": stats.get("filename", ""),
        "progress": round(progress * 100, 1),
        "duration": int(duration),
        "eta": eta,
        "filament_mm": round(float(stats.get("filament_used", 0) or 0), 1),
        "current_layer": info.get("current_layer"),
        "total_layer": info.get("total_layer"),
        "hotend": round(float(extruder.get("temperature", 0) or 0), 1),
        "hotend_target": round(float(extruder.get("target", 0) or 0), 1),
        "bed": round(float(bed.get("temperature", 0) or 0), 1),
        "bed_target": round(float(bed.get("target", 0) or 0), 1),
        "fan_pct": round(float(fan.get("speed", 0) or 0) * 100),
        "fan_rpm": fan.get("rpm"),
    }


PLUGIN_HTML = r'''
<div class="plugin-head">
 <div><span class="eyebrow">KLIPPER / MOONRAKER</span><h1 data-role="title">Printer</h1><div class="muted" data-role="file"></div></div>
 <span class="status-chip" data-role="state">--</span>
</div>
<div class="progress-xl"><div data-role="bar"></div></div>
<div class="split meta-row"><span data-role="pct">0%</span><span data-role="elapsed"></span><span data-role="eta"></span><span data-role="done"></span></div>
<div class="metric-grid printer-metrics">
 <article class="metric"><label>HOTEND</label><strong data-role="hotend">--</strong><small data-role="hotend-target"></small></article>
 <article class="metric"><label>BED</label><strong data-role="bed">--</strong><small data-role="bed-target"></small></article>
 <article class="metric"><label>LAYER</label><strong data-role="layer">--</strong><small>current / total</small></article>
 <article class="metric"><label>FAN</label><strong data-role="fan">--</strong><small data-role="rpm"></small></article>
 <article class="metric"><label>FILAMENT</label><strong data-role="filament">--</strong><small>used</small></article>
</div>
'''

PLUGIN_CSS = r'''
.plugin-printer .printer-metrics{grid-template-columns:repeat(5,1fr)}
.plugin-printer .metric{border-top:2px solid rgba(111,183,255,.35)}
@media(max-width:760px){.plugin-printer .printer-metrics{grid-template-columns:repeat(2,1fr)}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.printer={
 render(data,root){
  const state=String(data.state||"standby").toUpperCase();
  root.querySelector('[data-role="state"]').textContent=state;
  root.querySelector('[data-role="title"]').textContent=state==="PRINTING"?"Printing":state==="PAUSED"?"Print paused":state==="COMPLETE"?"Print complete":"Printer ready";
  root.querySelector('[data-role="file"]').textContent=data.filename||"Klipper connected";
  root.querySelector('[data-role="bar"]').style.width=`${Math.max(0,Math.min(100,data.progress||0))}%`;
  root.querySelector('[data-role="pct"]').textContent=`${Number(data.progress||0).toFixed(1)}%`;
  root.querySelector('[data-role="elapsed"]').textContent=`${RackDash.duration(data.duration)} elapsed`;
  root.querySelector('[data-role="eta"]').textContent=data.eta?`ETA ${RackDash.duration(data.eta)}`:"ETA --";
  root.querySelector('[data-role="done"]').textContent=data.eta?`DONE ${new Date(Date.now()+data.eta*1000).toLocaleTimeString([],{hour:"numeric",minute:"2-digit"})}`:"";
  root.querySelector('[data-role="hotend"]').textContent=`${Math.round(data.hotend||0)}°C`;
  root.querySelector('[data-role="hotend-target"]').textContent=data.hotend_target?`target ${Math.round(data.hotend_target)}°C`:"target off";
  root.querySelector('[data-role="bed"]').textContent=`${Math.round(data.bed||0)}°C`;
  root.querySelector('[data-role="bed-target"]').textContent=data.bed_target?`target ${Math.round(data.bed_target)}°C`:"target off";
  root.querySelector('[data-role="layer"]').textContent=(data.current_layer!=null||data.total_layer!=null)?`${data.current_layer??"?"} / ${data.total_layer??"?"}`:"--";
  root.querySelector('[data-role="fan"]').textContent=`${data.fan_pct??0}%`;
  root.querySelector('[data-role="rpm"]').textContent=data.fan_rpm?`${data.fan_rpm} RPM`:"";
  root.querySelector('[data-role="filament"]').textContent=data.filament_mm?`${(data.filament_mm/1000).toFixed(2)} m`:"--";
 }
};
'''
