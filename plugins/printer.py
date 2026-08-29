from __future__ import annotations

import os
import posixpath
from urllib.parse import quote, urljoin, urlparse

import requests

from _shared import TTLCache


PLUGIN_ID = "printer"
PLUGIN_NAME = "3D Printer"
PLUGIN_VERSION = "3.0.2"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/printer.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "custom_routes", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 50
PLUGIN_REFRESH_SECONDS = 3
PLUGIN_ACCENT = "#6fb7ff"
PLUGIN_ICON = "PRINT"
PLUGIN_PUBLIC_ERROR = "3D printer unavailable"

PLUGIN_CONFIG = [
    {
        "key": "KLIPPER_URL",
        "label": "Moonraker URL",
        "type": "text",
        "default": "http://127.0.0.1:7125",
        "required": True,
    },
    {
        "key": "KLIPPER_CAMERA_URL",
        "label": "Camera Stream URL",
        "type": "text",
        "default": "",
        "help": "Optional MJPEG stream or snapshot URL. Mainsail/Crowsnest commonly uses /webcam/?action=stream. Relative URLs are resolved against the Moonraker host.",
    },
    {
        "key": "KLIPPER_CAMERA_ROTATE_180",
        "label": "Rotate Camera 180°",
        "type": "checkbox",
        "default": "false",
        "required": False,
        "help": "Rotate the live camera stream 180 degrees for upside-down camera mounts.",
    },
]

KLIPPER_URL = os.getenv(
    "KLIPPER_URL",
    "http://127.0.0.1:7125",
).rstrip("/")
CAMERA_URL = os.getenv(
    "KLIPPER_CAMERA_URL",
    "",
).strip()

CAMERA_ROTATE_180 = os.getenv(
    "KLIPPER_CAMERA_ROTATE_180",
    "false",
).strip().lower() in ("1", "true", "yes", "on")

_metadata_cache = TTLCache(300)
_machine_cache = TTLCache(300)
_objects_cache = TTLCache(300)


PLUGIN_HTML = r'''
<div class="printer-shell">
  <section class="printer-hero surface">
    <div class="printer-hero-copy">
      <div class="printer-headline">
        <div>
          <span class="eyebrow">KLIPPER / MOONRAKER</span>
          <h1 data-role="title">3D Printer</h1>
          <div class="muted printer-file" data-role="file">Connecting...</div>
        </div>
        <span class="printer-state" data-role="state">--</span>
      </div>

      <div class="printer-progress-wrap">
        <div class="printer-progress-track">
          <div class="printer-progress-bar" data-role="bar"></div>
        </div>
        <div class="printer-progress-meta">
          <strong data-role="pct">0.0%</strong>
          <span data-role="elapsed">-- elapsed</span>
          <span data-role="eta">ETA --</span>
          <span data-role="done"></span>
        </div>
      </div>
    </div>

    <div class="printer-preview" data-role="preview-card">
      <img data-role="preview" alt="Current print preview">
      <div class="printer-preview-empty" data-role="preview-empty">
        <span>G-CODE PREVIEW</span>
        <strong>No thumbnail</strong>
      </div>
    </div>
  </section>

  <section class="printer-metrics">
    <article class="surface printer-metric temp">
      <span>HOTEND</span>
      <strong data-role="hotend">--</strong>
      <small data-role="hotend-target">target off</small>
      <div class="mini-track"><i data-role="hotend-power"></i></div>
    </article>
    <article class="surface printer-metric temp">
      <span>BED</span>
      <strong data-role="bed">--</strong>
      <small data-role="bed-target">target off</small>
      <div class="mini-track"><i data-role="bed-power"></i></div>
    </article>
    <article class="surface printer-metric">
      <span>LAYER</span>
      <strong data-role="layer">--</strong>
      <small data-role="layer-pct">layer progress</small>
    </article>
    <article class="surface printer-metric">
      <span>Z HEIGHT</span>
      <strong data-role="z-height">--</strong>
      <small>toolhead position</small>
    </article>
    <article class="surface printer-metric">
      <span>PART FAN</span>
      <strong data-role="fan">--</strong>
      <small data-role="rpm">--</small>
    </article>
    <article class="surface printer-metric">
      <span>FILAMENT</span>
      <strong data-role="filament">--</strong>
      <small data-role="filament-weight">used this print</small>
    </article>
    <article class="surface printer-metric">
      <span>SPEED</span>
      <strong data-role="speed">--</strong>
      <small>speed factor</small>
    </article>
    <article class="surface printer-metric">
      <span>FLOW</span>
      <strong data-role="flow">--</strong>
      <small>extrusion factor</small>
    </article>
  </section>

  <section class="printer-main-grid">
    <article class="surface printer-camera-card">
      <div class="printer-section-head">
        <div>
          <div class="section-label">LIVE CAMERA</div>
          <div class="muted printer-small">USB camera / Crowsnest / Mainsail</div>
        </div>
        <span class="camera-status" data-role="camera-status">NOT CONFIGURED</span>
      </div>
      <div class="printer-camera-frame" data-role="camera-frame">
        <img data-role="camera" alt="3D printer camera stream">
        <div class="printer-camera-empty" data-role="camera-empty">
          <strong>Camera not configured</strong>
          <span>Add KLIPPER_CAMERA_URL in plugin settings.</span>
        </div>
      </div>
    </article>

    <article class="surface printer-details-card">
      <div class="printer-section-head">
        <div>
          <div class="section-label">PRINT DETAILS</div>
          <div class="muted printer-small">Current job metadata</div>
        </div>
      </div>
      <div class="printer-details" data-role="details"></div>
    </article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-printer{
  --printer:#6fb7ff;
  --printer-soft:rgba(111,183,255,.08);
  --printer-line:rgba(111,183,255,.28);
}
.plugin-printer .printer-shell{display:grid;gap:var(--gap)}
.plugin-printer .printer-hero{
  display:grid;
  grid-template-columns:minmax(0,1fr) minmax(180px,22rem);
  gap:var(--gap);
  align-items:stretch;
  border-left:3px solid var(--printer);
  background:linear-gradient(115deg,rgba(111,183,255,.07),rgba(255,255,255,.008) 45%,rgba(255,255,255,.004));
}
.plugin-printer .printer-hero-copy{display:flex;flex-direction:column;justify-content:space-between;min-width:0}
.plugin-printer .printer-headline{display:flex;justify-content:space-between;align-items:flex-start;gap:.75rem}
.plugin-printer .printer-headline h1{margin:.15rem 0 .12rem;font-size:clamp(1.45rem,3vw,2.5rem);line-height:1}
.plugin-printer .printer-file{font-size:.55rem;max-width:60ch;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-printer .printer-state{
  padding:.3rem .5rem;border-radius:.35rem;border:1px solid var(--border);font-size:.5rem;font-weight:900;letter-spacing:.05em;color:#dce8ee
}
.plugin-printer .printer-state.printing{border-color:rgba(72,210,118,.4);background:rgba(72,210,118,.065);color:#75e599}
.plugin-printer .printer-state.paused{border-color:rgba(229,160,13,.45);background:rgba(229,160,13,.08);color:#f5be50}
.plugin-printer .printer-state.error{border-color:rgba(255,86,96,.45);background:rgba(255,86,96,.08);color:#ff7b85}
.plugin-printer .printer-progress-wrap{margin-top:1rem}
.plugin-printer .printer-progress-track{height:.7rem;border-radius:1rem;overflow:hidden;background:rgba(255,255,255,.075);border:1px solid rgba(255,255,255,.03)}
.plugin-printer .printer-progress-bar{height:100%;width:0;background:linear-gradient(90deg,#397fc1,var(--printer));box-shadow:0 0 15px rgba(111,183,255,.25);transition:width .3s ease}
.plugin-printer .printer-progress-meta{display:grid;grid-template-columns:auto repeat(3,minmax(0,1fr));gap:.55rem;align-items:center;margin-top:.35rem;color:var(--muted);font-size:.48rem}
.plugin-printer .printer-progress-meta strong{font-size:.72rem;color:#fff}

.plugin-printer .printer-preview{
  position:relative;
  width:min(100%,22rem);
  height:13rem;
  max-height:13rem;
  justify-self:end;
  align-self:center;
  border-radius:.55rem;
  overflow:hidden;
  background:#10171c;
  border:1px solid rgba(111,183,255,.12);
}
.plugin-printer .printer-preview img{
  width:100%;
  height:100%;
  max-width:100%;
  max-height:100%;
  object-fit:contain;
  display:none;
  background:radial-gradient(circle at center,rgba(111,183,255,.06),transparent 58%);
}
.plugin-printer .printer-preview.has-image img{display:block}
.plugin-printer .printer-preview-empty{position:absolute;inset:0;display:grid;place-content:center;text-align:center;gap:.22rem;color:var(--muted)}
.plugin-printer .printer-preview.has-image .printer-preview-empty{display:none}
.plugin-printer .printer-preview-empty span{font-size:.43rem;letter-spacing:.06em;font-weight:850}
.plugin-printer .printer-preview-empty strong{font-size:.68rem;color:#cbd6dc}

.plugin-printer .printer-metrics{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:var(--gap)}
.plugin-printer .printer-metric{min-width:0;border-top:1px solid rgba(111,183,255,.15)}
.plugin-printer .printer-metric>span{display:block;color:var(--muted);font-size:.43rem;font-weight:850;letter-spacing:.05em}
.plugin-printer .printer-metric>strong{display:block;margin-top:.1rem;font-size:clamp(.82rem,1.5vw,1.22rem);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-printer .printer-metric>small{display:block;margin-top:.08rem;color:var(--muted);font-size:.42rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-printer .mini-track{height:.2rem;background:rgba(255,255,255,.06);border-radius:1rem;margin-top:.35rem;overflow:hidden}
.plugin-printer .mini-track i{display:block;height:100%;width:0;background:var(--printer);border-radius:inherit;transition:width .25s ease}

.plugin-printer .printer-main-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(300px,.6fr);gap:var(--gap)}
.plugin-printer .printer-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.7rem}
.plugin-printer .printer-small{font-size:.45rem}
.plugin-printer .camera-status{font-size:.44rem;color:var(--muted);border:1px solid var(--border);padding:.22rem .35rem;border-radius:.3rem;font-weight:850}
.plugin-printer .camera-status.live{color:#75e599;border-color:rgba(72,210,118,.35);background:rgba(72,210,118,.055)}
.plugin-printer .printer-camera-frame{
  position:relative;
  height:22rem;
  margin-top:.55rem;
  overflow:hidden;
  border-radius:.55rem;
  background:#0b0f12;
  border:1px solid rgba(111,183,255,.11);
}
.plugin-printer .printer-camera-frame img{width:100%;height:100%;object-fit:contain;display:none;transform-origin:center center}
.plugin-printer .printer-camera-frame.has-camera img{display:block}
.plugin-printer .printer-camera-frame.rotate-180 img{transform:rotate(180deg)}
.plugin-printer .printer-camera-empty{position:absolute;inset:0;display:grid;place-content:center;text-align:center;gap:.25rem;color:var(--muted);padding:1rem}
.plugin-printer .printer-camera-frame.has-camera .printer-camera-empty{display:none}
.plugin-printer .printer-camera-empty strong{font-size:.7rem;color:#d2dde2}
.plugin-printer .printer-camera-empty span{font-size:.48rem}

.plugin-printer .printer-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.42rem;margin-top:.55rem}
.plugin-printer .detail-box{padding:.55rem;border-radius:.43rem;border:1px solid var(--border);background:rgba(255,255,255,.012);min-width:0}
.plugin-printer .detail-box.wide{grid-column:1/-1}
.plugin-printer .detail-box span{display:block;font-size:.42rem;color:var(--muted);font-weight:850;letter-spacing:.04em}
.plugin-printer .detail-box strong{display:block;margin-top:.1rem;font-size:.6rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-printer .printer-message{margin-top:.45rem;padding:.48rem;border-radius:.4rem;border:1px solid rgba(229,160,13,.2);background:rgba(229,160,13,.035);font-size:.49rem;color:#e8c36e}

@media(max-width:1200px){
  .plugin-printer .printer-metrics{grid-template-columns:repeat(4,minmax(0,1fr))}
}
@media(max-width:900px){
  .plugin-printer .printer-main-grid{grid-template-columns:1fr}
  .plugin-printer .printer-camera-frame{height:18rem}
}
@media(max-width:700px){
  .plugin-printer .printer-hero{grid-template-columns:1fr}
  .plugin-printer .printer-preview{width:100%;max-width:22rem;justify-self:start}
  .plugin-printer .printer-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
  .plugin-printer .printer-progress-meta{grid-template-columns:repeat(2,minmax(0,1fr))}
}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.printer={
  stateTitle(state){
    if(state==="printing")return "Printing";
    if(state==="paused")return "Print paused";
    if(state==="complete")return "Print complete";
    if(state==="error")return "Print error";
    if(state==="cancelled")return "Print cancelled";
    return "Printer ready";
  },

  setText(root,role,value){
    const el=root.querySelector(`[data-role="${role}"]`);
    if(el)el.textContent=value;
  },

  renderDetails(data){
    const rows=[
      ["PRINTER",data.hostname||"Klipper"],
      ["KLIPPER",data.klipper_version||"--"],
      ["MOONRAKER",data.moonraker_version||"--"],
      ["G-CODE SIZE",data.file_size_human||"--"],
      ["SLICER",data.slicer||"--"],
      ["EST. PRINT TIME",data.estimated_time?RackDash.duration(data.estimated_time):"--"],
      ["OBJECT HEIGHT",data.object_height!=null?`${Number(data.object_height).toFixed(1)} mm`:"--"],
      ["FILAMENT TOTAL",data.filament_total_mm?`${(data.filament_total_mm/1000).toFixed(2)} m`:"--"],
    ];

    return rows.map(([label,value],index)=>`
      <div class="detail-box ${index===0?"wide":""}">
        <span>${RackDash.escape(label)}</span>
        <strong title="${RackDash.escape(String(value))}">${RackDash.escape(String(value))}</strong>
      </div>
    `).join("")+
    (data.message?`<div class="detail-box wide printer-message">${RackDash.escape(data.message)}</div>`:"");
  },

  render(data,root){
    const state=String(data.state||"standby").toLowerCase();
    const stateNode=root.querySelector('[data-role="state"]');

    this.setText(root,"title",this.stateTitle(state));
    this.setText(root,"file",data.filename||"Klipper connected");
    this.setText(root,"state",state.toUpperCase());

    if(stateNode){
      stateNode.className=`printer-state ${state}`;
    }

    const progress=Math.max(0,Math.min(100,Number(data.progress||0)));
    root.querySelector('[data-role="bar"]').style.width=`${progress}%`;
    this.setText(root,"pct",`${progress.toFixed(1)}%`);
    this.setText(root,"elapsed",`${RackDash.duration(data.duration||0)} elapsed`);
    this.setText(root,"eta",data.eta?`ETA ${RackDash.duration(data.eta)}`:"ETA --");
    this.setText(
      root,
      "done",
      data.eta
        ?`DONE ${new Date(Date.now()+data.eta*1000).toLocaleTimeString([],{hour:"numeric",minute:"2-digit"})}`
        :""
    );

    this.setText(root,"hotend",`${Math.round(data.hotend||0)}°C`);
    this.setText(root,"hotend-target",data.hotend_target?`target ${Math.round(data.hotend_target)}°C`:"target off");
    root.querySelector('[data-role="hotend-power"]').style.width=`${Math.round((data.hotend_power||0)*100)}%`;

    this.setText(root,"bed",`${Math.round(data.bed||0)}°C`);
    this.setText(root,"bed-target",data.bed_target?`target ${Math.round(data.bed_target)}°C`:"target off");
    root.querySelector('[data-role="bed-power"]').style.width=`${Math.round((data.bed_power||0)*100)}%`;

    this.setText(
      root,
      "layer",
      (data.current_layer!=null||data.total_layer!=null)
        ?`${data.current_layer??"?"} / ${data.total_layer??"?"}`
        :"--"
    );
    this.setText(
      root,
      "layer-pct",
      data.total_layer&&data.current_layer!=null
        ?`${Math.round(Number(data.current_layer)/Number(data.total_layer)*100)}% through layers`
        :"layer progress"
    );

    this.setText(root,"z-height",data.z_height!=null?`${Number(data.z_height).toFixed(2)} mm`:"--");
    this.setText(root,"fan",`${Math.round(data.fan_pct||0)}%`);
    this.setText(root,"rpm",data.fan_rpm?`${Math.round(data.fan_rpm)} RPM`:"RPM unavailable");
    this.setText(root,"filament",data.filament_mm?`${(data.filament_mm/1000).toFixed(2)} m`:"--");
    this.setText(root,"filament-weight",data.filament_weight_g?`${Number(data.filament_weight_g).toFixed(1)} g estimated`:"used this print");
    this.setText(root,"speed",`${Math.round((data.speed_factor||1)*100)}%`);
    this.setText(root,"flow",`${Math.round((data.flow_factor||1)*100)}%`);

    root.querySelector('[data-role="details"]').innerHTML=this.renderDetails(data);

    const previewCard=root.querySelector('[data-role="preview-card"]');
    const preview=root.querySelector('[data-role="preview"]');
    if(data.thumbnail_available&&data.filename){
      preview.onload=()=>previewCard.classList.add("has-image");
      preview.onerror=()=>previewCard.classList.remove("has-image");
      preview.src=`/api/plugin/printer/thumbnail?filename=${encodeURIComponent(data.filename)}&v=${encodeURIComponent(data.thumbnail_key||"")}`;
    }else{
      previewCard.classList.remove("has-image");
      preview.removeAttribute("src");
    }

    const cameraFrame=root.querySelector('[data-role="camera-frame"]');
    const camera=root.querySelector('[data-role="camera"]');
    const cameraStatus=root.querySelector('[data-role="camera-status"]');

    cameraFrame.classList.toggle("rotate-180",!!data.camera_rotate_180);

    if(data.camera_configured){
      camera.onload=()=>{
        cameraFrame.classList.add("has-camera");
        cameraStatus.textContent="LIVE";
        cameraStatus.classList.add("live");
      };
      camera.onerror=()=>{
        cameraFrame.classList.remove("has-camera");
        cameraStatus.textContent="UNAVAILABLE";
        cameraStatus.classList.remove("live");
      };
      if(!camera.src.endsWith("/api/plugin/printer/camera")){
        camera.src="/api/plugin/printer/camera";
      }
    }else{
      cameraFrame.classList.remove("has-camera");
      camera.removeAttribute("src");
      cameraStatus.textContent="NOT CONFIGURED";
      cameraStatus.classList.remove("live");
    }
  }
};
'''


def _get(path, params=None, timeout=5, stream=False):
    return requests.get(
        f"{KLIPPER_URL}{path}",
        params=params,
        timeout=timeout,
        stream=stream,
        headers={
            "User-Agent": "RackDash-Printer/3.0.1",
        },
    )


def _available_objects():
    cached = _objects_cache.get()
    if cached is not None:
        return set(cached)

    response = _get(
        "/printer/objects/list",
        timeout=5,
    )
    response.raise_for_status()

    objects = set(
        response.json()
        .get("result", {})
        .get("objects", [])
        or []
    )

    _objects_cache.set(sorted(objects))
    return objects


def _query_status():
    available = _available_objects()

    requested = [
        ("webhooks", ""),
        ("print_stats", ""),
        ("virtual_sdcard", ""),
        ("extruder", "temperature,target,power"),
        ("heater_bed", "temperature,target,power"),
        ("fan", "speed,rpm"),
        ("toolhead", "position"),
        ("gcode_move", "speed_factor,extrude_factor"),
        ("display_status", "progress,message"),
    ]

    parts = []
    for object_name, fields in requested:
        if object_name not in available:
            continue
        parts.append(
            object_name
            if not fields
            else f"{object_name}={fields}"
        )

    if not parts:
        raise RuntimeError(
            "Moonraker returned no queryable printer objects"
        )

    response = _get(
        "/printer/objects/query?"
        + "&".join(parts)
    )
    response.raise_for_status()

    return (
        response.json()
        .get("result", {})
        .get("status", {})
    )


def _metadata(filename):
    if not filename:
        return {}

    cached = _metadata_cache.get()
    if (
        cached
        and cached.get("_filename") == filename
    ):
        return dict(cached)

    try:
        response = _get(
            "/server/files/metadata",
            params={"filename": filename},
            timeout=6,
        )
        response.raise_for_status()
        result = response.json().get("result") or {}
    except Exception:
        result = {}

    result = dict(result)
    result["_filename"] = filename
    _metadata_cache.set(result)
    return dict(result)


def _machine_info():
    cached = _machine_cache.get()
    if cached is not None:
        return dict(cached)

    result = {
        "hostname": "",
        "klipper_version": "",
        "moonraker_version": "",
    }

    try:
        response = _get(
            "/server/info",
            timeout=5,
        )
        response.raise_for_status()
        info = response.json().get("result") or {}
        result["hostname"] = str(
            info.get("hostname")
            or ""
        )
        result["klipper_version"] = str(
            info.get("klippy_version")
            or info.get("klipper_version")
            or ""
        )
        result["moonraker_version"] = str(
            info.get("moonraker_version")
            or ""
        )
    except Exception:
        pass

    _machine_cache.set(result)
    return dict(result)


def _human_bytes(value):
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0

    units = ["B", "KB", "MB", "GB"]
    idx = 0

    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1

    if idx == 0:
        return f"{int(size)} {units[idx]}"
    return f"{size:.1f} {units[idx]}"


def _resolve_camera_url():
    if not CAMERA_URL:
        return ""

    if CAMERA_URL.startswith(
        ("http://", "https://")
    ):
        return CAMERA_URL

    parsed = urlparse(KLIPPER_URL)
    origin = (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme and parsed.netloc
        else KLIPPER_URL
    )

    return urljoin(
        origin.rstrip("/") + "/",
        CAMERA_URL.lstrip("/"),
    )


def _thumbnail_path(filename, metadata):
    thumbnails = (
        metadata.get("thumbnails")
        if isinstance(metadata, dict)
        else None
    ) or []

    if not thumbnails:
        return ""

    ordered = sorted(
        thumbnails,
        key=lambda item: (
            int(item.get("width") or 0)
            * int(item.get("height") or 0)
        ),
        reverse=True,
    )

    relative = str(
        ordered[0].get("relative_path")
        or ""
    ).strip()

    if not relative:
        return ""

    parent = posixpath.dirname(filename)
    return posixpath.normpath(
        posixpath.join(parent, relative)
    ).lstrip("/")


def get_data():
    status = _query_status()

    stats = status.get("print_stats") or {}
    sd = status.get("virtual_sdcard") or {}
    extruder = status.get("extruder") or {}
    bed = status.get("heater_bed") or {}
    fan = status.get("fan") or {}
    toolhead = status.get("toolhead") or {}
    move = status.get("gcode_move") or {}
    display = status.get("display_status") or {}
    info = stats.get("info") or {}

    filename = str(
        stats.get("filename")
        or ""
    )

    progress = float(
        sd.get("progress")
        or display.get("progress")
        or 0
    )

    duration = float(
        stats.get("print_duration")
        or 0
    )

    eta = (
        max(
            0,
            int(
                duration / progress
                - duration
            ),
        )
        if progress > 0.005 and duration > 0
        else 0
    )

    metadata = _metadata(filename)
    machine = _machine_info()

    position = toolhead.get("position") or []
    z_height = (
        position[2]
        if isinstance(position, list)
        and len(position) >= 3
        else None
    )

    filament_mm = float(
        stats.get("filament_used")
        or 0
    )

    filament_weight = metadata.get(
        "filament_weight_total"
    )

    thumbnail = _thumbnail_path(
        filename,
        metadata,
    )

    return {
        "state": stats.get(
            "state",
            "standby",
        ),
        "filename": filename,
        "message": (
            stats.get("message")
            or display.get("message")
            or ""
        ),
        "progress": round(
            progress * 100,
            1,
        ),
        "duration": int(duration),
        "eta": eta,

        "filament_mm": round(
            filament_mm,
            1,
        ),
        "filament_weight_g": (
            round(
                float(filament_weight),
                1,
            )
            if filament_weight is not None
            else None
        ),
        "filament_total_mm": float(
            metadata.get(
                "filament_total",
                0,
            )
            or 0
        ),

        "current_layer": info.get(
            "current_layer"
        ),
        "total_layer": info.get(
            "total_layer"
        ),

        "hotend": round(
            float(
                extruder.get(
                    "temperature",
                    0,
                )
                or 0
            ),
            1,
        ),
        "hotend_target": round(
            float(
                extruder.get(
                    "target",
                    0,
                )
                or 0
            ),
            1,
        ),
        "hotend_power": float(
            extruder.get(
                "power",
                0,
            )
            or 0
        ),

        "bed": round(
            float(
                bed.get(
                    "temperature",
                    0,
                )
                or 0
            ),
            1,
        ),
        "bed_target": round(
            float(
                bed.get(
                    "target",
                    0,
                )
                or 0
            ),
            1,
        ),
        "bed_power": float(
            bed.get(
                "power",
                0,
            )
            or 0
        ),

        "fan_pct": round(
            float(
                fan.get(
                    "speed",
                    0,
                )
                or 0
            )
            * 100
        ),
        "fan_rpm": fan.get("rpm"),

        "z_height": z_height,
        "speed_factor": float(
            move.get(
                "speed_factor",
                1,
            )
            or 1
        ),
        "flow_factor": float(
            move.get(
                "extrude_factor",
                1,
            )
            or 1
        ),

        "hostname": machine.get(
            "hostname",
            "",
        ),
        "klipper_version": machine.get(
            "klipper_version",
            "",
        ),
        "moonraker_version": machine.get(
            "moonraker_version",
            "",
        ),

        "file_size_human": _human_bytes(
            metadata.get("size")
        ),
        "estimated_time": int(
            float(
                metadata.get(
                    "estimated_time",
                    0,
                )
                or 0
            )
        ),
        "object_height": metadata.get(
            "object_height"
        ),
        "slicer": str(
            metadata.get(
                "slicer",
                "",
            )
            or ""
        ),

        "thumbnail_available": bool(
            thumbnail
        ),
        "thumbnail_key": thumbnail,

        "camera_configured": bool(
            _resolve_camera_url()
        ),
        "camera_rotate_180": CAMERA_ROTATE_180,
    }


def register_routes(app):
    @app.get(
        "/api/plugin/printer/thumbnail"
    )
    def printer_thumbnail():
        from flask import request

        filename = str(
            request.args.get(
                "filename",
                "",
            )
        ).strip()

        if (
            not filename
            or filename.startswith("/")
            or ".." in filename.split("/")
        ):
            return app.response_class(
                status=404
            )

        metadata = _metadata(filename)
        thumbnail = _thumbnail_path(
            filename,
            metadata,
        )

        if not thumbnail:
            return app.response_class(
                status=404
            )

        try:
            safe_path = quote(
                thumbnail,
                safe="/",
            )
            response = _get(
                f"/server/files/gcodes/{safe_path}",
                timeout=8,
            )
            response.raise_for_status()

            result = app.response_class(
                response.content,
                content_type=response.headers.get(
                    "Content-Type",
                    "image/png",
                ),
            )
            result.headers[
                "Cache-Control"
            ] = "private, max-age=300"
            return result

        except Exception:
            app.logger.exception(
                "Printer thumbnail fetch failed"
            )
            return app.response_class(
                status=404
            )

    @app.get(
        "/api/plugin/printer/camera"
    )
    def printer_camera():
        camera_url = _resolve_camera_url()

        if not camera_url:
            return app.response_class(
                status=404
            )

        try:
            upstream = requests.get(
                camera_url,
                stream=True,
                timeout=15,
                headers={
                    "User-Agent": (
                        "RackDash-Printer/3.0.1"
                    )
                },
            )
            upstream.raise_for_status()

            content_type = upstream.headers.get(
                "Content-Type",
                "multipart/x-mixed-replace",
            )

            def generate():
                try:
                    for chunk in upstream.iter_content(
                        chunk_size=16384,
                    ):
                        if chunk:
                            yield chunk
                finally:
                    upstream.close()

            result = app.response_class(
                generate(),
                content_type=content_type,
                direct_passthrough=True,
            )
            result.headers["Cache-Control"] = "no-store"
            result.headers["Pragma"] = "no-cache"
            return result

        except Exception:
            app.logger.exception(
                "Printer camera stream failed"
            )
            return app.response_class(
                status=502
            )


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "3D Printer",
            "lines": [
                "Printer unavailable",
            ],
        }

    state = str(
        data.get(
            "state",
            "standby",
        )
    ).upper()

    return {
        "title": "3D Printer",
        "lines": [
            (
                f"{state} "
                f"{float(data.get('progress', 0)):.0f}%"
            ),
            (
                f"E {float(data.get('hotend', 0)):.0f}/"
                f"{float(data.get('hotend_target', 0)):.0f}C "
                f"B {float(data.get('bed', 0)):.0f}/"
                f"{float(data.get('bed_target', 0)):.0f}C"
            ),
            (
                f"L {data.get('current_layer') or '-'}"
                f"/{data.get('total_layer') or '-'} "
                f"Z {float(data.get('z_height') or 0):.1f}"
            ),
        ],
    }
