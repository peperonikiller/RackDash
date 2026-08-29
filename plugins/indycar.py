from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import requests
from _shared import TTLCache

PLUGIN_ID = "indycar"
PLUGIN_NAME = "IndyCar"
PLUGIN_VERSION = "3.0.5"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/indycar.py"
PLUGIN_MIN_RACKDASH = "3.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 42
PLUGIN_REFRESH_SECONDS = 300
PLUGIN_ACCENT = "#e2231a"
PLUGIN_ICON = "INDY"
PLUGIN_PUBLIC_ERROR = "IndyCar data unavailable"

PLUGIN_CONFIG = [{
    "key": "INDYCAR_NEWS_RSS",
    "label": "IndyCar Headlines RSS",
    "type": "text",
    "default": "https://news.google.com/rss/search?q=NTT+INDYCAR+Series&hl=en-US&gl=US&ceid=US:en",
    "required": False,
    "help": "RSS feed used by the Headlines section.",
}]

INDYCAR_NEWS_RSS = os.getenv("INDYCAR_NEWS_RSS", PLUGIN_CONFIG[0]["default"]).strip()
BASE = "https://www.indycar.com"
_data_cache = TTLCache(600)
_standings_cache = TTLCache(900)
_news_cache = TTLCache(600)
_weather_cache = TTLCache(1800)

# Normalized local SVG paths (viewBox 0 0 1000 650). Keeping them local avoids
# CDN failures and lets RackDash render the 3D circuit view instantly.
CALENDAR_2026 = [
    (1,"2026-03-01","12:00 PM","Firestone Grand Prix of St. Petersburg","Streets of St. Petersburg","St. Petersburg","Florida","Street Circuit",27.7676,-82.6403,"M180 510 L130 465 L145 390 L220 335 L270 270 L330 245 L355 160 L455 120 L560 140 L620 205 L705 180 L805 220 L850 310 L800 390 L710 425 L640 505 L540 535 L430 505 L330 545 Z"),
    (2,"2026-03-07","3:00 PM","Good Ranchers 250","Phoenix Raceway","Avondale","Arizona","Oval",33.3749,-112.3101,"M215 330 C215 165 375 115 505 125 C705 140 815 205 815 330 C815 455 705 520 505 535 C365 545 215 495 215 330 Z"),
    (3,"2026-03-15","12:30 PM","Java House Grand Prix of Arlington","Streets of Arlington","Arlington","Texas","Street Circuit",32.7479,-97.0925,"M125 455 L165 250 L260 170 L395 195 L440 115 L540 165 L665 145 L760 245 L835 260 L855 370 L760 435 L650 410 L585 505 L440 535 L345 465 L235 500 Z"),
    (4,"2026-03-29","1:00 PM","Children's of Alabama Indy Grand Prix","Barber Motorsports Park","Birmingham","Alabama","Road Course",33.5311,-86.6195,"M180 420 C120 330 165 205 295 185 C375 175 420 235 475 205 C535 170 525 105 625 125 C735 145 790 235 760 320 C735 390 665 395 620 445 C560 515 455 550 350 520 C280 500 235 465 180 420 Z"),
    (5,"2026-04-19","5:30 PM","Acura Grand Prix of Long Beach","Streets of Long Beach","Long Beach","California","Street Circuit",33.7648,-118.1924,"M155 470 L145 355 L205 255 L330 235 L420 165 L530 195 L625 140 L740 185 L830 250 L800 350 L700 375 L640 455 L545 495 L430 455 L335 515 L245 505 Z"),
    (6,"2026-05-09","4:30 PM","Sonsio Grand Prix","Indianapolis Motor Speedway Road Course","Indianapolis","Indiana","Road Course",39.795,-86.2347,"M180 500 L145 305 L225 170 L390 145 L520 180 L650 145 L805 210 L840 330 L785 455 L650 490 L565 430 L465 480 L350 445 L280 520 Z"),
    (7,"2026-05-24","12:30 PM","110th Running of the Indianapolis 500","Indianapolis Motor Speedway","Indianapolis","Indiana","Oval",39.795,-86.2347,"M210 325 C210 170 345 130 500 130 C655 130 790 170 790 325 C790 480 655 520 500 520 C345 520 210 480 210 325 Z"),
    (8,"2026-05-31","12:30 PM","Chevrolet Detroit Grand Prix","Streets of Detroit","Detroit","Michigan","Street Circuit",42.3314,-83.0458,"M145 470 L130 330 L205 220 L300 245 L360 155 L485 125 L565 185 L660 155 L790 225 L845 330 L805 440 L695 420 L620 505 L505 470 L415 525 L295 490 L225 525 Z"),
    (9,"2026-06-07","9:00 PM","Bommarito Automotive Group 500","World Wide Technology Raceway","Madison","Illinois","Oval",38.6506,-90.1353,"M220 330 C220 185 355 140 500 150 C655 160 790 215 790 330 C790 445 655 500 500 510 C355 520 220 475 220 330 Z"),
    (10,"2026-06-21","2:00 PM","XPEL Grand Prix at Road America","Road America","Elkhart Lake","Wisconsin","Road Course",43.7976,-87.9897,"M160 420 C110 325 155 230 255 210 L335 155 L445 175 L535 120 L650 160 L740 255 L825 300 L780 390 L690 415 L635 500 L525 535 L445 480 L350 520 L245 475 Z"),
    (11,"2026-07-05","12:30 PM","Honda Indy 200 at Mid-Ohio","Mid-Ohio Sports Car Course","Lexington","Ohio","Road Course",40.6892,-82.6366,"M180 460 C110 385 145 260 245 235 C330 215 355 155 445 155 C535 155 555 215 635 205 C745 190 815 260 810 350 C805 430 725 445 675 495 C615 550 520 525 455 485 C385 445 315 540 245 505 Z"),
    (12,"2026-07-19","3:00 PM","Borchetta Bourbon Music City Grand Prix","Nashville Superspeedway","Lebanon","Tennessee","Oval",36.0464,-86.4084,"M215 325 C215 175 355 130 500 140 C660 150 800 205 800 325 C800 445 660 500 500 510 C355 520 215 475 215 325 Z"),
    (13,"2026-08-09","4:00 PM","Grand Prix of Portland","Portland International Raceway","Portland","Oregon","Road Course",45.5978,-122.6961,"M170 470 L145 335 L205 245 L320 210 L410 145 L535 155 L610 215 L715 200 L825 275 L815 390 L725 445 L625 430 L535 505 L420 490 L335 535 L250 500 Z"),
    (14,"2026-08-16","12:00 PM","Ontario Honda Dealers Indy at Markham","Streets of Markham","Markham","Ontario","Street Circuit",43.8561,-79.337,"M155 490 L140 350 L220 300 L185 205 L305 160 L390 210 L475 140 L595 165 L675 230 L790 210 L845 315 L800 430 L690 465 L585 440 L505 520 L385 485 L275 525 Z"),
    (15,"2026-08-29","2:30 PM","Snap-on Makers and Fixers 250","Milwaukee Mile","West Allis","Wisconsin","Oval",43.0219,-88.0107,"M220 325 C220 180 360 135 500 145 C650 155 785 210 785 325 C785 440 650 495 500 505 C360 515 220 470 220 325 Z"),
    (16,"2026-08-30","1:00 PM","Milwaukee Mile Race 2","Milwaukee Mile","West Allis","Wisconsin","Oval",43.0219,-88.0107,"M220 325 C220 180 360 135 500 145 C650 155 785 210 785 325 C785 440 650 495 500 505 C360 515 220 470 220 325 Z"),
    (17,"2026-09-06","2:30 PM","INDYCAR Grand Prix of Monterey","WeatherTech Raceway Laguna Seca","Monterey","California","Road Course",36.584,-121.7532,"M175 455 C125 370 155 265 250 245 C335 225 370 165 455 155 C540 145 585 205 650 190 C745 170 815 235 825 325 C835 410 760 440 690 455 C620 470 590 535 495 520 C405 505 365 455 290 500 C235 530 205 495 175 455 Z"),
]

CALENDAR_2026 = [dict(zip(("round","date","time_et","name","circuit","city","region","type","lat","lon","track_path"), row)) for row in CALENDAR_2026]

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag=="table": self.table=[]
        elif tag=="tr" and self.table is not None: self.row=[]
        elif tag in ("td","th") and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:
            value=re.sub(r"\s+"," ",data).strip()
            if value: self.cell.append(value)
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join(self.cell).strip()); self.cell=None
        elif tag=="tr" and self.row is not None:
            if any(self.row): self.table.append(self.row)
            self.row=None
        elif tag=="table" and self.table is not None:
            if self.table: self.tables.append(self.table)
            self.table=None

def _fetch(url):
    r=requests.get(url,timeout=9,headers={"User-Agent":"RackDash-IndyCar/3.0.5","Accept":"text/html,application/xhtml+xml"}); r.raise_for_status(); return r.text

def _tables(url):
    p=TableParser(); p.feed(_fetch(url)); return p.tables

def _standings():
    cached=_standings_cache.get()
    if cached is not None: return cached
    drivers=[]; manufacturers=[]
    try:
        for table in _tables(f"{BASE}/standings"):
            if not table or "driver" not in " | ".join(table[0]).lower(): continue
            for c in table[1:]:
                if len(c)<6: continue
                drivers.append({"position":c[0],"number":c[1],"name":c[2],"team":c[3],"engine":c[4],"points":c[5],"behind":c[6] if len(c)>6 else "","wins":c[8] if len(c)>8 else "0","poles":c[9] if len(c)>9 else "0"})
                if len(drivers)>=10: break
            if drivers: break
    except Exception: pass
    try:
        for table in _tables(f"{BASE}/standings?standings=enginemanufacturer"):
            if not table or "manufacturer" not in " | ".join(table[0]).lower(): continue
            for c in table[1:]:
                if len(c)<3: continue
                manufacturers.append({"position":c[0],"name":c[1],"wins":c[2],"points":c[-1]})
            if manufacturers: break
    except Exception: pass
    return _standings_cache.set({"drivers":drivers,"manufacturers":manufacturers})

def _race_dt(e):
    return datetime.strptime(f'{e["date"]} {e["time_et"]}',"%Y-%m-%d %I:%M %p").replace(tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)

def _next_event():
    now=datetime.now(timezone.utc)
    for e in CALENDAR_2026:
        dt=_race_dt(e)
        if dt.timestamp() >= now.timestamp()-5*3600:
            row=dict(e); row["race_epoch"]=dt.timestamp(); row["countdown"]=max(0,int(dt.timestamp()-now.timestamp()))
            row["sessions"]=[{"name":"Race","detail":f'{e["date"]} · {e["time_et"]} ET'},{"name":"Circuit Type","detail":e["type"]},{"name":"Broadcast","detail":"FOX"}]
            return row
    return None

def _headlines():
    cached=_news_cache.get()
    if cached is not None: return cached
    if not INDYCAR_NEWS_RSS: return []
    try:
        r=requests.get(INDYCAR_NEWS_RSS,timeout=7,headers={"User-Agent":"RackDash-IndyCar/3.0.5"}); r.raise_for_status(); root=ET.fromstring(r.content); rows=[]
        for item in root.findall(".//item")[:12]:
            title=(item.findtext("title") or "").strip()
            if not title: continue
            src=item.find("source"); source=(src.text or "").strip() if src is not None else ""; epoch=None
            try:
                dt=parsedate_to_datetime(item.findtext("pubDate") or ""); epoch=(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
            except Exception: pass
            rows.append({"title":title,"source":source,"url":(item.findtext("link") or "").strip(),"published_epoch":epoch})
        return _news_cache.set(rows[:6])
    except Exception: return _news_cache.set([])

def _weather(e):
    if not e: return None
    key=f'{e["lat"]},{e["lon"]},{e["date"]}'; cached=_weather_cache.get()
    if cached and cached.get("_key")==key: return dict(cached)
    labels={0:"Clear",1:"Mostly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",61:"Light rain",63:"Rain",65:"Heavy rain",80:"Showers",81:"Showers",82:"Heavy showers",95:"Thunderstorms",99:"Severe storms"}
    try:
        r=requests.get("https://api.open-meteo.com/v1/forecast",params={"latitude":e["lat"],"longitude":e["lon"],"daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max","temperature_unit":"fahrenheit","wind_speed_unit":"mph","timezone":"auto","start_date":e["date"],"end_date":e["date"]},timeout=7,headers={"User-Agent":"RackDash-IndyCar/3.0.5"}); r.raise_for_status(); d=r.json().get("daily") or {}
        if not d.get("time"): raise RuntimeError("forecast unavailable")
        first=lambda k:(d.get(k) or [None])[0]
        result={"_key":key,"available":True,"condition":labels.get(int(first("weather_code") or -1),"Forecast"),"temp_high_f":first("temperature_2m_max"),"temp_low_f":first("temperature_2m_min"),"rain_chance":first("precipitation_probability_max"),"wind_mph":first("wind_speed_10m_max")}
    except Exception: result={"_key":key,"available":False}
    _weather_cache.set(result); return dict(result)

def _dynamic(data):
    now=datetime.now(timezone.utc).timestamp(); result=dict(data)
    if result.get("event"):
        e=dict(result["event"]); e["countdown"]=max(0,int(e.get("race_epoch",now)-now)); result["event"]=e
    result["headlines"]=[{**h,"age_seconds":max(0,int(now-h["published_epoch"])) if h.get("published_epoch") else None} for h in result.get("headlines",[])]
    return result

def get_data():
    cached=_data_cache.get()
    if cached is not None:
        cached=dict(cached); cached["headlines"]=_headlines(); return _dynamic(cached)
    e=_next_event(); s=_standings(); data={"year":2026,"event":e,"drivers":s["drivers"],"manufacturers":s["manufacturers"],"headlines":_headlines(),"weather":_weather(e),"total_rounds":17}
    return _data_cache.set(_dynamic(data))

def get_i2c_data():
    try: data=get_data()
    except Exception: return {"title":"IndyCar","lines":["Data unavailable"]}
    e=data.get("event") or {}; lines=[]
    if e: lines.extend([str(e.get("name",""))[:18],f'R{e.get("round","?")} {e.get("time_et","")}'])
    if data.get("drivers"): lines.append(f'P1 {data["drivers"][0].get("name","")[:9]} {data["drivers"][0].get("points","0")}pt')
    return {"title":"IndyCar","lines":lines[:4]}

PLUGIN_HTML = r'''
<div class="indy-layout">
<section class="surface indy-track"><div class="track-topline"><span class="section-label">CIRCUIT</span><span class="track-location" data-role="location"></span></div><div class="indy-track-stage"><div class="indy-floor"></div><svg class="indy-track-svg" viewBox="0 0 1000 650" preserveAspectRatio="xMidYMid meet"><defs><filter id="indyGlow"><feGaussianBlur stdDeviation="8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter><linearGradient id="indyGradient"><stop offset="0" stop-color="#fff"/><stop offset=".45" stop-color="#80d4ff"/><stop offset="1" stop-color="#e2231a"/></linearGradient></defs><path class="indy-track-shadow" data-role="track-shadow"/><path class="indy-track-road" data-role="track-road"/><path class="indy-track-light" data-role="track-light"/><circle class="indy-start-dot" data-role="start-dot" r="9"/></svg><div class="indy-track-caption"><span data-role="track-type"></span><strong data-role="circuit"></strong></div></div><div class="track-legend"><span><i class="track-glow"></i> RACING LINE</span><span>NTT INDYCAR SERIES</span></div></section>
<section class="surface indy-race"><div class="indy-race-hero"><span class="eyebrow">NEXT INDYCAR EVENT</span><h1 data-role="name">Loading...</h1><div class="muted" data-role="event-location"></div><div class="countdown" data-role="countdown">--</div><div class="chip-row"><span data-role="round"></span><span data-role="season-progress"></span><span data-role="date"></span><span data-role="race-time"></span></div></div><div class="indy-weekend"><div><div class="section-label">RACE WEEKEND</div><div class="session-list" data-role="sessions"></div></div><div class="indy-weather"><div class="section-label">EXPECTED RACE-DAY WEATHER</div><div class="weather-card" data-role="weather"></div></div></div></section>
<section class="surface indy-standings"><div class="section-label">DRIVER CHAMPIONSHIP · TOP 10</div><div class="standings-list" data-role="drivers"></div></section>
<section class="surface indy-engine"><div class="section-label">ENGINE MANUFACTURERS</div><div class="engine-list" data-role="manufacturers"></div></section>
<section class="surface indy-headlines"><div class="section-label">INDYCAR HEADLINES</div><div class="headline-list" data-role="headlines"></div></section>
</div>'''

PLUGIN_CSS = r'''
.plugin-indycar{--indy:#e2231a;--indy-blue:#80d4ff}.plugin-indycar .indy-layout{display:grid;grid-template-columns:minmax(420px,.83fr) minmax(520px,1.17fr);grid-template-areas:"track race" "drivers engine" "headlines headlines";gap:calc(var(--gap)*1.15)}.plugin-indycar .indy-track{grid-area:track;display:grid;grid-template-rows:auto minmax(300px,1fr) auto;min-height:420px;overflow:hidden}.plugin-indycar .indy-race{grid-area:race;display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,.88fr);gap:var(--gap);border-left:3px solid var(--indy)}.plugin-indycar .indy-standings{grid-area:drivers}.plugin-indycar .indy-engine{grid-area:engine}.plugin-indycar .indy-headlines{grid-area:headlines}.plugin-indycar .track-topline,.plugin-indycar .track-legend{display:flex;justify-content:space-between;gap:.6rem}.plugin-indycar .track-location,.plugin-indycar .track-legend{font-size:.46rem;color:var(--muted)}
.plugin-indycar .indy-track-stage{position:relative;display:grid;place-items:center;min-height:300px;overflow:hidden;perspective:1000px;background:radial-gradient(circle at 50% 43%,rgba(50,135,175,.10),transparent 37%)}.plugin-indycar .indy-floor{position:absolute;width:80%;height:56%;left:10%;bottom:8%;transform:rotateX(72deg);transform-origin:center bottom;background:radial-gradient(ellipse at center,rgba(226,35,26,.06),rgba(33,101,133,.025) 44%,transparent 72%);border:1px solid rgba(128,212,255,.035);border-radius:50%}.plugin-indycar .indy-track-svg{position:relative;z-index:2;width:min(92%,720px);height:88%;min-height:280px;overflow:visible;transform:rotateX(54deg) rotateZ(-2deg) translateY(-2%);transform-origin:center;filter:drop-shadow(0 28px 18px rgba(0,0,0,.55))}.plugin-indycar .indy-track-shadow,.plugin-indycar .indy-track-road,.plugin-indycar .indy-track-light{fill:none;stroke-linejoin:round;stroke-linecap:round}.plugin-indycar .indy-track-shadow{stroke:#000;stroke-width:42;opacity:.62;transform:translateY(14px)}.plugin-indycar .indy-track-road{stroke:#15222a;stroke-width:32}.plugin-indycar .indy-track-light{stroke:url(#indyGradient);stroke-width:11;filter:url(#indyGlow);stroke-dasharray:19 11;animation:indyDash 2.3s linear infinite}.plugin-indycar .indy-start-dot{fill:#fff;stroke:var(--indy);stroke-width:5}.plugin-indycar .indy-track-caption{position:absolute;z-index:5;bottom:.45rem;left:50%;transform:translateX(-50%);width:92%;text-align:center;text-shadow:0 2px 12px #000}.plugin-indycar .indy-track-caption span{display:block;font-size:.42rem;letter-spacing:.12em;color:var(--indy);font-weight:900}.plugin-indycar .indy-track-caption strong{display:block;font-size:.65rem}.plugin-indycar .track-glow{display:inline-block;width:.6rem;height:.18rem;border-radius:1rem;background:var(--indy-blue);box-shadow:0 0 10px rgba(128,212,255,.6)}
.plugin-indycar .indy-race-hero h1{font-size:clamp(1.5rem,3vw,2.6rem);line-height:1;margin:.18rem 0}.plugin-indycar .countdown{font-size:clamp(1.5rem,3vw,2.55rem);font-weight:950;margin:.65rem 0}.plugin-indycar .indy-weather{margin-top:.8rem;padding-top:.7rem;border-top:1px solid var(--border)}.plugin-indycar .session-list{display:grid;gap:.3rem;margin-top:.45rem}.plugin-indycar .session-row{display:grid;grid-template-columns:1fr auto;gap:.5rem;padding:.35rem .45rem;border:1px solid var(--border);border-radius:.35rem;font-size:.5rem}.plugin-indycar .weather-card{display:grid;grid-template-columns:1.3fr 1fr 1fr;gap:.35rem;margin-top:.45rem}.plugin-indycar .weather-primary,.plugin-indycar .weather-metric{padding:.45rem;border:1px solid var(--border);border-radius:.4rem}.plugin-indycar .weather-temp{font-size:.86rem;font-weight:900}.plugin-indycar .weather-temp small,.plugin-indycar .weather-metric span{display:block;font-size:.4rem;color:var(--muted)}
.plugin-indycar .standings-list{display:grid;gap:.2rem;margin-top:.48rem}.plugin-indycar .standing-row{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;gap:.45rem;align-items:center;min-height:1.7rem;padding:.2rem .35rem;border-bottom:1px solid rgba(255,255,255,.035)}.plugin-indycar .standing-pos{font-size:.52rem;font-weight:950;color:var(--indy)}.plugin-indycar .standing-name{font-size:.59rem;font-weight:850}.plugin-indycar .standing-sub{font-size:.43rem;color:var(--muted)}.plugin-indycar .standing-points{text-align:right;font-size:.59rem;font-weight:900}.plugin-indycar .standing-points small{display:block;font-size:.39rem;color:var(--muted)}.plugin-indycar .engine-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.4rem;margin-top:.48rem}.plugin-indycar .engine-card{padding:.62rem;border:1px solid var(--border);border-radius:.45rem}.plugin-indycar .headline-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.3rem;margin-top:.45rem}.plugin-indycar .headline-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.6rem;padding:.4rem .45rem;border:1px solid rgba(255,255,255,.04);border-radius:.38rem;text-decoration:none;color:inherit}.plugin-indycar .headline-title{font-size:.53rem;font-weight:780}.plugin-indycar .headline-meta{font-size:.4rem;color:var(--muted);text-align:right}
@keyframes indyDash{to{stroke-dashoffset:-60}}@media(max-width:1050px){.plugin-indycar .indy-layout{grid-template-columns:minmax(340px,.9fr) minmax(430px,1.1fr)}.plugin-indycar .indy-race{grid-template-columns:1fr}.plugin-indycar .weather-card{grid-template-columns:1fr 1fr}}@media(max-width:720px){.plugin-indycar .indy-layout{grid-template-columns:1fr;grid-template-areas:"race" "track" "drivers" "engine" "headlines"}.plugin-indycar .indy-race{border-left:0}.plugin-indycar .headline-list{grid-template-columns:1fr}.plugin-indycar .indy-track-svg{width:96%;height:82%}}@media(prefers-reduced-motion:reduce){.plugin-indycar .indy-track-light{animation:none!important}}

/* RackDash 3.0.4 enhanced 3D circuit animation */
.plugin-indycar .indy-track-svg{
  animation:indyTrackFloat 6s ease-in-out infinite;
}
.plugin-indycar .indy-floor::after{
  animation:indyGridDrift 9s linear infinite;
}
.plugin-indycar .indy-start-dot{
  animation:indyStartPulse 1.45s ease-in-out infinite;
}
@keyframes indyTrackFloat{
  0%,100%{transform:rotateX(54deg) rotateZ(-2deg) translateY(-2%) scale(.99)}
  50%{transform:rotateX(50deg) rotateZ(-1deg) translateY(-4%) scale(1.015)}
}
@keyframes indyGridDrift{to{background-position:0 28px,28px 0}}
@keyframes indyStartPulse{
  0%,100%{opacity:.55;filter:drop-shadow(0 0 5px rgba(226,35,26,.5))}
  50%{opacity:1;filter:drop-shadow(0 0 14px rgba(128,212,255,.95))}
}
@media(prefers-reduced-motion:reduce){
  .plugin-indycar .indy-track-svg,
  .plugin-indycar .indy-floor::after,
  .plugin-indycar .indy-start-dot,
  }

'''

PLUGIN_JS = r'''
window.RackDashPlugins.indycar={
 duration(s){s=Math.max(0,Number(s||0));const d=Math.floor(s/86400),h=Math.floor((s%86400)/3600),m=Math.floor((s%3600)/60);return d?`${d}d ${h}h ${m}m`:h?`${h}h ${m}m`:`${m}m`},
 age(s){if(s==null)return"";s=Number(s);return s<3600?`${Math.max(1,Math.floor(s/60))}m ago`:s<86400?`${Math.floor(s/3600)}h ago`:`${Math.floor(s/86400)}d ago`},
 standings(rows){return(rows||[]).map(r=>`<div class="standing-row"><div class="standing-pos">${RackDash.escape(r.position||"-")}</div><div><div class="standing-name">${r.number?`#${RackDash.escape(r.number)} · `:""}${RackDash.escape(r.name||"")}</div><div class="standing-sub">${RackDash.escape(r.team||"")}${r.engine?` · ${RackDash.escape(r.engine)}`:""}${Number(r.position)>1&&r.behind?` · ${RackDash.escape(r.behind)} PTS`:""}</div></div><div class="standing-points">${RackDash.escape(r.points||"0")}<small>PTS${Number(r.wins||0)>0?` · ${RackDash.escape(r.wins)}W`:""}</small></div></div>`).join("")},
 manufacturers(rows){return(rows||[]).map(r=>`<div class="engine-card"><span>P${RackDash.escape(r.position||"-")} · ENGINE</span><strong>${RackDash.escape(r.name||"")}</strong><small>${RackDash.escape(r.points||"0")} PTS</small></div>`).join("")},
 sessions(rows){return(rows||[]).map(r=>`<div class="session-row"><span>${RackDash.escape(r.name||"")}</span><span>${RackDash.escape(r.detail||"")}</span></div>`).join("")},
 weather(w){if(!w?.available)return`<div class="empty-state">Forecast not available yet.</div>`;return`<div class="weather-primary"><strong>${RackDash.escape(w.condition||"Forecast")}</strong><div class="weather-temp">${Math.round(Number(w.temp_high_f||0))}°<small>HIGH · ${Math.round(Number(w.temp_low_f||0))}° LOW</small></div></div><div class="weather-metric"><span>RAIN</span><strong>${Math.round(Number(w.rain_chance||0))}%</strong></div><div class="weather-metric"><span>WIND</span><strong>${Math.round(Number(w.wind_mph||0))} mph</strong></div>`},
 headlines(rows){return(rows||[]).map(r=>`<a class="headline-row" href="${RackDash.escape(r.url||"#")}" target="_blank" rel="noopener"><span class="headline-title">${RackDash.escape(r.title||"")}</span><span class="headline-meta">${RackDash.escape(r.source||"")}${r.age_seconds!=null?`<br>${this.age(r.age_seconds)}`:""}</span></a>`).join("")},
 renderTrack(e,root){const p=String(e?.track_path||"");["track-shadow","track-road","track-light"].forEach(role=>root.querySelector(`[data-role="${role}"]`)?.setAttribute("d",p));const path=root.querySelector('[data-role="track-light"]'),dot=root.querySelector('[data-role="start-dot"]');if(path&&dot&&p){try{const pt=path.getPointAtLength(Math.min(18,path.getTotalLength()*.03));dot.setAttribute("cx",pt.x);dot.setAttribute("cy",pt.y)}catch(_){dot.setAttribute("cx",0);dot.setAttribute("cy",0)}}},
 render(data,root){root.querySelector('[data-role="drivers"]').innerHTML=this.standings(data.drivers)||`<div class="empty-state">Driver standings unavailable.</div>`;root.querySelector('[data-role="manufacturers"]').innerHTML=this.manufacturers(data.manufacturers)||`<div class="empty-state">Manufacturer standings unavailable.</div>`;root.querySelector('[data-role="headlines"]').innerHTML=this.headlines(data.headlines)||`<div class="empty-state">IndyCar headlines unavailable.</div>`;const e=data.event;if(!e){root.querySelector('[data-role="name"]').textContent="Season complete";return}root.querySelector('[data-role="name"]').textContent=e.name;root.querySelector('[data-role="circuit"]').textContent=e.circuit;root.querySelector('[data-role="location"]').textContent=[e.city,e.region].join(", ");root.querySelector('[data-role="event-location"]').textContent=[e.circuit,e.city,e.region].join(" • ");root.querySelector('[data-role="track-type"]').textContent=e.type.toUpperCase();root.querySelector('[data-role="round"]').textContent=`ROUND ${e.round}`;root.querySelector('[data-role="season-progress"]').textContent=`${e.round}/${data.total_rounds} ROUNDS`;root.querySelector('[data-role="date"]').textContent=e.date;root.querySelector('[data-role="race-time"]').textContent=`${e.time_et} ET`;root.querySelector('[data-role="countdown"]').textContent=this.duration(e.countdown);root.querySelector('[data-role="sessions"]').innerHTML=this.sessions(e.sessions);root.querySelector('[data-role="weather"]').innerHTML=this.weather(data.weather);this.renderTrack(e,root)}
};
'''
