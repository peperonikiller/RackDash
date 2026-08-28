from __future__ import annotations
import os
import re
from datetime import datetime, timezone

import requests
from flask import Response
from _shared import TTLCache

PLUGIN_ID = "f1"
PLUGIN_NAME = "Formula 1"
PLUGIN_VERSION = "1.0.0"
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 40
PLUGIN_REFRESH_SECONDS = 300
PLUGIN_ACCENT = "#e5a00d"
PLUGIN_ICON = "F1"
PLUGIN_PUBLIC_ERROR = "Formula 1 data unavailable"

PLUGIN_CONFIG = [{'key': 'F1_API', 'label': 'Formula 1 API', 'type': 'text', 'default': 'https://api.jolpi.ca/ergast/f1', 'required': True}]

F1_API = os.getenv("F1_API", "https://api.jolpi.ca/ergast/f1").rstrip("/")
_cache = TTLCache(1800)


def _driver_standings():
    response = requests.get(f"{F1_API}/current/driverstandings.json", timeout=6)
    response.raise_for_status()
    lists = response.json().get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    rows = lists[0].get("DriverStandings", []) if lists else []
    result = []
    for row in rows[:5]:
        driver = row.get("Driver", {})
        constructors = row.get("Constructors", [])
        result.append({
            "position": row.get("position", ""),
            "points": row.get("points", "0"),
            "wins": row.get("wins", "0"),
            "code": driver.get("code", ""),
            "name": " ".join(x for x in (driver.get("givenName"), driver.get("familyName")) if x),
            "team": constructors[0].get("name", "") if constructors else "",
        })
    return result


def _constructor_standings():
    response = requests.get(f"{F1_API}/current/constructorstandings.json", timeout=6)
    response.raise_for_status()
    lists = response.json().get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
    rows = lists[0].get("ConstructorStandings", []) if lists else []
    result = []
    for row in rows[:11]:
        constructor = row.get("Constructor", {})
        result.append({
            "position": row.get("position", ""),
            "points": row.get("points", "0"),
            "wins": row.get("wins", "0"),
            "name": constructor.get("name", ""),
        })
    return result


def get_data():
    cached = _cache.get()
    if cached:
        cached = dict(cached)
        cached["countdown"] = max(
            0, int(cached["race_epoch"] - datetime.now(timezone.utc).timestamp())
        )
        return cached

    response = requests.get(f"{F1_API}/current/next.json", timeout=6)
    response.raise_for_status()
    races = response.json().get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return {
            "available": False,
            "drivers": _driver_standings(),
            "constructors": _constructor_standings(),
        }

    race = races[0]
    circuit = race.get("Circuit", {})
    loc = circuit.get("Location", {})
    iso = (race.get("date", "") + "T" + race.get("time", "00:00:00Z")).replace("Z", "+00:00")
    race_dt = datetime.fromisoformat(iso)
    circuit_id = circuit.get("circuitId", "")

    data = {
        "available": True,
        "name": race.get("raceName", ""),
        "round": race.get("round", ""),
        "date": race.get("date", ""),
        "time": race.get("time", ""),
        "circuit": circuit.get("circuitName", ""),
        "city": loc.get("locality", ""),
        "country": loc.get("country", ""),
        "track_key": circuit_id,
        "race_epoch": race_dt.timestamp(),
        "countdown": max(0, int((race_dt - datetime.now(timezone.utc)).total_seconds())),
        "drivers": _driver_standings(),
        "constructors": _constructor_standings(),
    }
    return _cache.set(data)


def register_routes(app):
    @app.get("/api/plugin/f1/track/<track>.svg")
    def f1_track(track):
        safe = re.sub(r"[^a-z0-9_-]", "", track.lower())
        url = f"https://raw.githubusercontent.com/MasterPlay007/F1-Track-Layouts-SVG/main/{safe}.svg"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return Response(response.content, content_type="image/svg+xml")
        except Exception:
            return Response(status=404)


PLUGIN_HTML = r'''
<div class="f1-layout">
  <section class="track-surface surface">
    <div data-role="track" class="track-host"></div>
  </section>
  <section class="f1-copy">
    <span class="eyebrow">NEXT GRAND PRIX</span>
    <h1 data-role="name">Loading...</h1>
    <div class="muted" data-role="circuit"></div>
    <div class="countdown" data-role="countdown">--d --h --m</div>
    <div class="chip-row">
      <span data-role="round"></span>
      <span data-role="date"></span>
      <span data-role="time"></span>
    </div>
  </section>
  <section class="surface f1-standings driver-standings">
    <div class="section-label">DRIVER CHAMPIONSHIP · TOP 5</div>
    <div class="standings-list" data-role="drivers"></div>
  </section>
  <section class="surface f1-standings constructor-standings">
    <div class="section-label">CONSTRUCTORS CHAMPIONSHIP · ALL TEAMS</div>
    <div class="standings-list" data-role="constructors"></div>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-f1 .f1-layout{display:grid;grid-template-columns:minmax(0,1.08fr) minmax(0,.92fr);grid-template-areas:"track race" "drivers constructors";gap:calc(var(--gap)*1.15);align-items:stretch}
.plugin-f1 .track-surface{grid-area:track;display:flex;align-items:center;justify-content:center;overflow:hidden;min-height:220px}
.plugin-f1 .track-host{width:100%;height:100%;display:flex;align-items:center;justify-content:center}
.plugin-f1 .track-host svg{width:100%!important;height:100%!important;max-height:55vh;display:block}
.plugin-f1 .track-host path,.plugin-f1 .track-host polyline,.plugin-f1 .track-host line{stroke:#eef7ff!important;fill:none!important;stroke-width:5!important;stroke-linecap:round;stroke-linejoin:round;filter:drop-shadow(0 0 5px rgba(89,200,255,.8));stroke-dasharray:18 10;animation:rackdash-lap 2.2s linear infinite}
@keyframes rackdash-lap{to{stroke-dashoffset:-56}}
.plugin-f1 .f1-copy{grid-area:race;align-self:center;border-left:2px solid rgba(229,160,13,.55);padding-left:clamp(1rem,3vw,2rem)}
.plugin-f1 .f1-copy h1{font-size:clamp(1.6rem,4.5vw,4rem);margin:.25rem 0}
.plugin-f1 .countdown{font-size:clamp(1.8rem,5.2vw,4.6rem);font-weight:900;letter-spacing:-.05em;margin:clamp(.7rem,2vh,1.2rem) 0}
.plugin-f1 .driver-standings{grid-area:drivers}.plugin-f1 .constructor-standings{grid-area:constructors}
.plugin-f1 .standings-list{display:grid;gap:.28rem;margin-top:.5rem}
.plugin-f1 .standing-row{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;align-items:center;gap:.5rem;min-height:1.65rem;padding:.18rem .35rem;border-radius:.35rem;background:rgba(255,255,255,.018)}
.plugin-f1 .standing-pos{display:grid;place-items:center;width:1.55rem;height:1.55rem;border:1px solid var(--border);border-radius:.32rem;font-weight:900;font-size:.7rem;color:#fff}
.plugin-f1 .standing-main{min-width:0}.plugin-f1 .standing-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.72rem;font-weight:820}
.plugin-f1 .standing-sub{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted);font-size:.56rem}
.plugin-f1 .standing-points{text-align:right;font-size:.72rem;font-weight:900;color:#f4c45c}.plugin-f1 .standing-points small{display:block;font-size:.5rem;font-weight:600;color:var(--muted)}
@media(min-width:1000px) and (max-height:500px){.plugin-f1 .f1-layout{grid-template-columns:1.05fr .72fr .62fr;grid-template-areas:"track race drivers" "track race constructors"}.plugin-f1 .track-surface{min-height:260px}.plugin-f1 .standing-row{min-height:1.42rem}.plugin-f1 .standing-name{font-size:.66rem}.plugin-f1 .standing-sub{font-size:.52rem}}
@media(max-width:720px){.plugin-f1 .f1-layout{grid-template-columns:1fr;grid-template-areas:"race" "track" "drivers" "constructors"}.plugin-f1 .f1-copy{border-left:0;padding-left:0}}
@media(prefers-reduced-motion:reduce){.plugin-f1 .track-host path{animation:none;stroke-dasharray:none}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.f1={
  standings(rows,type){
    return (rows||[]).map(row=>`
      <div class="standing-row">
        <div class="standing-pos">${RackDash.escape(row.position||"-")}</div>
        <div class="standing-main">
          <div class="standing-name">${RackDash.escape(row.code||row.name||"")}</div>
          <div class="standing-sub">${RackDash.escape(type==="driver"?(row.team||row.name||""):(row.name||""))}</div>
        </div>
        <div class="standing-points">${RackDash.escape(row.points||"0")}<small>PTS${row.wins&&Number(row.wins)>0?` · ${RackDash.escape(row.wins)}W`:""}</small></div>
      </div>`).join("");
  },
  async render(data,root){
    root.querySelector('[data-role="drivers"]').innerHTML=this.standings(data.drivers,"driver")||`<div class="empty-state">Driver standings unavailable.</div>`;
    root.querySelector('[data-role="constructors"]').innerHTML=this.standings(data.constructors,"constructor")||`<div class="empty-state">Constructor standings unavailable.</div>`;
    if(!data.available){root.querySelector('[data-role="name"]').textContent="No upcoming race";return;}
    root.querySelector('[data-role="name"]').textContent=data.name;
    root.querySelector('[data-role="circuit"]').textContent=[data.circuit,data.city,data.country].filter(Boolean).join(" • ");
    root.querySelector('[data-role="round"]').textContent=`ROUND ${data.round}`;
    root.querySelector('[data-role="date"]').textContent=data.date;
    root.querySelector('[data-role="time"]').textContent=data.time;
    const s=Number(data.countdown||0);
    root.querySelector('[data-role="countdown"]').textContent=`${Math.floor(s/86400)}d ${Math.floor((s%86400)/3600)}h ${Math.floor((s%3600)/60)}m`;
    const host=root.querySelector('[data-role="track"]');
    if(!data.track_key)return;
    try{
      const response=await fetch(`/api/plugin/f1/track/${encodeURIComponent(data.track_key)}.svg`);
      if(!response.ok)return;
      host.innerHTML=await response.text();
      const svg=host.querySelector("svg");
      if(svg){
        svg.removeAttribute("width");svg.removeAttribute("height");
        svg.setAttribute("preserveAspectRatio","xMidYMid meet");
        requestAnimationFrame(()=>{
          try{
            const box=(svg.querySelector("g")||svg).getBBox();
            const pad=Math.max(box.width,box.height)*.08;
            svg.setAttribute("viewBox",`${box.x-pad} ${box.y-pad} ${box.width+pad*2} ${box.height+pad*2}`);
          }catch(e){}
        });
      }
    }catch(e){}
  }
};
'''
