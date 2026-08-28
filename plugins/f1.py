from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from flask import Response
from _shared import TTLCache

PLUGIN_ID = "f1"
PLUGIN_NAME = "Formula 1"
PLUGIN_VERSION = "1.1.3"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/f1.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "custom_routes", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 40
PLUGIN_REFRESH_SECONDS = 60
PLUGIN_ACCENT = "#e5a00d"
PLUGIN_ICON = "F1"
PLUGIN_PUBLIC_ERROR = "Formula 1 data unavailable"

PLUGIN_CONFIG = [
    {
        "key": "F1_API",
        "label": "Formula 1 API",
        "type": "text",
        "default": "https://api.jolpi.ca/ergast/f1",
        "required": True,
    },
    {
        "key": "F1_NEWS_RSS",
        "label": "F1 Headlines RSS",
        "type": "text",
        "default": "https://news.google.com/rss/search?q=Formula+1+F1&hl=en-US&gl=US&ceid=US:en",
        "required": False,
        "help": "RSS feed used by the Headlines section. Leave the default for broad Formula 1 headlines.",
    },
]

F1_API = os.getenv("F1_API", "https://api.jolpi.ca/ergast/f1").rstrip("/")
F1_NEWS_RSS = os.getenv(
    "F1_NEWS_RSS",
    "https://news.google.com/rss/search?q=Formula+1+F1&hl=en-US&gl=US&ceid=US:en",
).strip()

_race_cache = TTLCache(900)
_news_cache = TTLCache(600)
_weather_cache = TTLCache(1800)


def _get_json(path: str):
    response = requests.get(
        f"{F1_API}/{path.lstrip('/')}",
        timeout=7,
        headers={"User-Agent": "RackDash-F1/1.1"},
    )
    response.raise_for_status()
    return response.json()


def _driver_standings():
    payload = _get_json("current/driverstandings.json")
    lists = payload.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
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
    payload = _get_json("current/constructorstandings.json")
    lists = payload.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
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


def _recent_race():
    try:
        payload = _get_json("current/last/results.json")
        races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        if not races:
            return None
        race = races[0]
        podium = []
        fastest = None
        for result in race.get("Results", []):
            driver = result.get("Driver", {})
            constructor = result.get("Constructor", {})
            name = driver.get("code") or " ".join(
                x for x in (driver.get("givenName"), driver.get("familyName")) if x
            )
            if len(podium) < 3:
                podium.append({
                    "position": result.get("position", ""),
                    "driver": name,
                    "team": constructor.get("name", ""),
                })
            fastest_lap = result.get("FastestLap") or {}
            if fastest_lap.get("rank") == "1":
                fastest = {
                    "driver": name,
                    "lap": fastest_lap.get("lap", ""),
                    "time": fastest_lap.get("Time", {}).get("time", ""),
                    "speed": fastest_lap.get("AverageSpeed", {}).get("speed", ""),
                    "speed_units": fastest_lap.get("AverageSpeed", {}).get("units", ""),
                }
        return {
            "name": race.get("raceName", ""),
            "round": race.get("round", ""),
            "podium": podium,
            "fastest_lap": fastest,
        }
    except Exception:
        return None


def _session(label, value):
    if not isinstance(value, dict) or not value.get("date"):
        return None
    iso = f"{value.get('date')}T{value.get('time') or '00:00:00Z'}".replace("Z", "+00:00")
    try:
        epoch = datetime.fromisoformat(iso).timestamp()
    except Exception:
        epoch = None
    return {
        "name": label,
        "date": value.get("date", ""),
        "time": value.get("time", ""),
        "epoch": epoch,
    }


def _weekend_sessions(race):
    fields = [
        ("Practice 1", "FirstPractice"),
        ("Practice 2", "SecondPractice"),
        ("Practice 3", "ThirdPractice"),
        ("Sprint Qualifying", "SprintQualifying"),
        ("Sprint", "Sprint"),
        ("Qualifying", "Qualifying"),
    ]
    rows = []
    for label, key in fields:
        row = _session(label, race.get(key))
        if row:
            rows.append(row)
    race_row = _session("Race", {"date": race.get("date", ""), "time": race.get("time", "")})
    if race_row:
        rows.append(race_row)
    rows.sort(key=lambda row: (row["epoch"] is None, row["epoch"] or 0))
    return rows


def _headlines():
    cached = _news_cache.get()
    if cached is not None:
        return cached
    if not F1_NEWS_RSS:
        return []
    try:
        response = requests.get(
            F1_NEWS_RSS,
            timeout=7,
            headers={"User-Agent": "RackDash-F1/1.1"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
        rows = []
        for item in root.findall(".//item")[:10]:
            source_node = item.find("source")
            source = (source_node.text or "").strip() if source_node is not None else ""
            title = (item.findtext("title") or "").strip()
            if source and title.lower().endswith((" - " + source).lower()):
                title = title[: -(len(source) + 3)].rstrip()
            if not title:
                continue
            raw_date = item.findtext("pubDate") or ""
            epoch = None
            try:
                dt = parsedate_to_datetime(raw_date)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                epoch = dt.timestamp()
            except Exception:
                pass
            rows.append({
                "title": title,
                "source": source,
                "url": (item.findtext("link") or "").strip(),
                "published_epoch": epoch,
            })
        return _news_cache.set(rows[:6])
    except Exception:
        return _news_cache.set([])



def _weather_code_label(code):
    labels = {
        0: "Clear",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Rime fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        56: "Freezing drizzle",
        57: "Heavy freezing drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        66: "Freezing rain",
        67: "Heavy freezing rain",
        71: "Light snow",
        73: "Snow",
        75: "Heavy snow",
        77: "Snow grains",
        80: "Rain showers",
        81: "Rain showers",
        82: "Heavy showers",
        85: "Snow showers",
        86: "Heavy snow showers",
        95: "Thunderstorms",
        96: "Thunderstorms + hail",
        99: "Severe storms + hail",
    }
    try:
        return labels.get(int(code), "Unknown")
    except Exception:
        return "Unknown"


def _race_day_weather(lat, lon, race_date):
    if not lat or not lon or not race_date:
        return None

    cache_key = f"{lat},{lon},{race_date}"
    cached = _weather_cache.get()
    if cached and cached.get("_key") == cache_key:
        return dict(cached)

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": (
                    "weather_code,"
                    "temperature_2m_max,"
                    "temperature_2m_min,"
                    "precipitation_probability_max,"
                    "precipitation_sum,"
                    "wind_speed_10m_max,"
                    "wind_gusts_10m_max"
                ),
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "inch",
                "timezone": "auto",
                "start_date": race_date,
                "end_date": race_date,
            },
            timeout=7,
            headers={"User-Agent": "RackDash-F1/1.1.2"},
        )
        response.raise_for_status()
        payload = response.json()
        daily = payload.get("daily") or {}
        dates = daily.get("time") or []

        if not dates:
            result = {
                "_key": cache_key,
                "available": False,
                "reason": "Forecast not available yet",
            }
            _weather_cache.set(result)
            return dict(result)

        def first(name, default=None):
            values = daily.get(name) or []
            return values[0] if values else default

        result = {
            "_key": cache_key,
            "available": True,
            "date": dates[0],
            "condition": _weather_code_label(first("weather_code")),
            "weather_code": first("weather_code"),
            "temp_high_f": first("temperature_2m_max"),
            "temp_low_f": first("temperature_2m_min"),
            "rain_chance": first("precipitation_probability_max"),
            "precipitation_in": first("precipitation_sum"),
            "wind_mph": first("wind_speed_10m_max"),
            "gust_mph": first("wind_gusts_10m_max"),
            "timezone": payload.get("timezone", ""),
        }
        _weather_cache.set(result)
        return dict(result)
    except Exception:
        result = {
            "_key": cache_key,
            "available": False,
            "reason": "Forecast not available yet",
        }
        _weather_cache.set(result)
        return dict(result)



def _dynamic(data):
    now = datetime.now(timezone.utc).timestamp()
    result = dict(data)
    if result.get("race_epoch"):
        result["countdown"] = max(0, int(result["race_epoch"] - now))

    sessions = []
    next_session = None
    for session in result.get("sessions", []):
        row = dict(session)
        if row.get("epoch"):
            row["countdown"] = int(row["epoch"] - now)
        sessions.append(row)
        if next_session is None and row.get("epoch") and row["epoch"] >= now - 7200:
            next_session = row
    result["sessions"] = sessions
    result["next_session"] = next_session

    headlines = []
    for headline in result.get("headlines", []):
        row = dict(headline)
        epoch = row.get("published_epoch")
        row["age_seconds"] = max(0, int(now - epoch)) if epoch else None
        headlines.append(row)
    result["headlines"] = headlines
    return result


def get_data():
    cached = _race_cache.get()
    if cached:
        cached = dict(cached)
        cached["headlines"] = _headlines()
        return _dynamic(cached)

    payload = _get_json("current/next.json")
    races = payload.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    drivers = _driver_standings()
    constructors = _constructor_standings()
    recent = _recent_race()
    headlines = _headlines()

    if not races:
        return _race_cache.set({
            "available": False,
            "drivers": drivers,
            "constructors": constructors,
            "recent_race": recent,
            "headlines": headlines,
            "sessions": [],
            "race_weather": None,
        })

    race = races[0]
    circuit = race.get("Circuit", {})
    loc = circuit.get("Location", {})
    iso = f"{race.get('date', '')}T{race.get('time') or '00:00:00Z'}".replace("Z", "+00:00")
    race_dt = datetime.fromisoformat(iso)

    data = {
        "available": True,
        "name": race.get("raceName", ""),
        "round": race.get("round", ""),
        "date": race.get("date", ""),
        "time": race.get("time", ""),
        "circuit": circuit.get("circuitName", ""),
        "city": loc.get("locality", ""),
        "country": loc.get("country", ""),
        "lat": loc.get("lat", ""),
        "long": loc.get("long", ""),
        "track_key": circuit.get("circuitId", ""),
        "race_epoch": race_dt.timestamp(),
        "sessions": _weekend_sessions(race),
        "drivers": drivers,
        "constructors": constructors,
        "recent_race": recent,
        "headlines": headlines,
        "race_weather": _race_day_weather(
            loc.get("lat", ""),
            loc.get("long", ""),
            race.get("date", ""),
        ),
    }
    return _race_cache.set(_dynamic(data))


def register_routes(app):
    @app.get("/api/plugin/f1/track/<track>.svg")
    def f1_track(track):
        safe = re.sub(r"[^a-z0-9_-]", "", track.lower())
        url = f"https://raw.githubusercontent.com/MasterPlay007/F1-Track-Layouts-SVG/main/{safe}.svg"
        try:
            response = requests.get(url, timeout=5, headers={"User-Agent": "RackDash-F1/1.1"})
            response.raise_for_status()
            return Response(response.content, content_type="image/svg+xml")
        except Exception:
            return Response(status=404)


def _short_countdown(seconds):
    seconds = max(0, int(seconds or 0))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {"title": "Formula 1", "lines": ["Data unavailable"]}

    lines = []
    if data.get("available"):
        race_name = (data.get("name", "") or "").replace("Grand Prix", "GP")
        lines.append(race_name[:18])
        lines.append(f"R{data.get('round', '?')} {_short_countdown(data.get('countdown', 0))}")
        next_session = data.get("next_session")
        if (
            next_session
            and next_session.get("name") != "Race"
            and -7200 <= (next_session.get("countdown") or 0) <= 345600
        ):
            lines.append(
                f"{next_session.get('name', '')[:12]} {_short_countdown(max(0, next_session.get('countdown') or 0))}"
            )
    else:
        lines.append("No upcoming race")

    drivers = data.get("drivers") or []
    constructors = data.get("constructors") or []
    if drivers and len(lines) < 4:
        leader = drivers[0]
        lines.append(
            f"P1 {leader.get('code') or leader.get('name', '')[:8]} {leader.get('points', '0')}pt"
        )
    if constructors and len(lines) < 4:
        leader = constructors[0]
        lines.append(f"P1 {leader.get('name', '')[:10]} {leader.get('points', '0')}pt")

    return {"title": "Formula 1", "lines": lines[:4]}


PLUGIN_HTML = r'''
<div class="f1-layout">
  <section class="track-surface surface">
    <div class="track-topline">
      <span class="section-label">CIRCUIT</span>
      <span class="track-location" data-role="track-location"></span>
    </div>
    <div data-role="track" class="track-host"></div>
    <div class="track-legend">
      <span><i class="track-glow"></i> RACING LINE</span>
      <span data-role="circuit"></span>
    </div>
  </section>

  <section class="f1-copy surface">
    <div class="f1-race-hero">
      <span class="eyebrow">NEXT GRAND PRIX</span>
      <h1 data-role="name">Loading...</h1>
      <div class="muted" data-role="race-location"></div>
      <div class="countdown" data-role="countdown">--d --h --m</div>
      <div class="chip-row">
        <span data-role="round"></span>
        <span data-role="date"></span>
        <span data-role="time"></span>
      </div>
    </div>
    <div class="f1-weekend-column">
      <div class="f1-session-block">
        <div class="section-label">RACE WEEKEND</div>
        <div class="session-list" data-role="sessions"></div>
      </div>
      <div class="f1-weather-block">
        <div class="section-label">EXPECTED RACE DAY WEATHER</div>
        <div class="weather-card" data-role="race-weather"></div>
      </div>
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

  <section class="surface recent-race">
    <div class="section-label">LAST RACE</div>
    <div class="recent-race-name" data-role="recent-name">--</div>
    <div class="podium-list" data-role="podium"></div>
    <div class="fastest-lap" data-role="fastest"></div>
  </section>

  <section class="surface f1-headlines">
    <div class="section-label">HEADLINES</div>
    <div class="headline-list" data-role="headlines"></div>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-f1 .f1-layout{display:grid;grid-template-columns:minmax(360px,.82fr) minmax(520px,1.18fr);grid-template-areas:"track race" "drivers constructors" "recent headlines";gap:calc(var(--gap)*1.15);align-items:stretch}
.plugin-f1 .track-surface{grid-area:track;display:grid;grid-template-rows:auto minmax(380px,54vh) auto;overflow:hidden;min-height:470px;position:relative}
.plugin-f1 .track-topline,.plugin-f1 .track-legend{display:flex;align-items:center;justify-content:space-between;gap:.7rem;position:relative;z-index:3}.plugin-f1 .track-location{font-size:.55rem;color:var(--muted);font-weight:750}
.plugin-f1 .track-host{width:100%;height:100%;min-height:380px;display:flex;align-items:center;justify-content:center;position:relative}.plugin-f1 .track-host::before{content:"";position:absolute;inset:12% 14%;border-radius:50%;background:radial-gradient(circle,rgba(89,200,255,.09),transparent 68%);filter:blur(22px);animation:f1-track-breathe 4s ease-in-out infinite}
.plugin-f1 .track-host svg{width:100%!important;height:100%!important;max-height:70vh;display:block;overflow:visible;position:relative;z-index:2;filter:drop-shadow(0 0 10px rgba(89,200,255,.12))}.plugin-f1 .track-host path,.plugin-f1 .track-host polyline,.plugin-f1 .track-host line{stroke:#d9e7ee!important;fill:none!important;stroke-width:6!important;stroke-linecap:round;stroke-linejoin:round;opacity:.92;filter:drop-shadow(0 0 4px rgba(89,200,255,.72))}.plugin-f1 .track-host .rackdash-racing-line{stroke:#62d5ff!important;stroke-width:2.4!important;stroke-dasharray:8 14;opacity:.95;filter:drop-shadow(0 0 5px rgba(89,200,255,.9));animation:f1-dash-flow 1.35s linear infinite}.plugin-f1 .track-host .rackdash-tracer{fill:#fff!important;stroke:#62d5ff!important;stroke-width:2!important;filter:drop-shadow(0 0 5px #62d5ff) drop-shadow(0 0 12px #62d5ff)}.plugin-f1 .track-host .rackdash-tracer-halo{fill:rgba(98,213,255,.18)!important;stroke:none!important;filter:drop-shadow(0 0 10px rgba(98,213,255,.75))}
.plugin-f1 .track-legend{color:var(--muted);font-size:.5rem;font-weight:750}.plugin-f1 .track-glow{display:inline-block;width:.5rem;height:.5rem;border-radius:50%;background:#62d5ff;box-shadow:0 0 8px #62d5ff;vertical-align:-.05rem;margin-right:.25rem}@keyframes f1-dash-flow{to{stroke-dashoffset:-44}}@keyframes f1-track-breathe{0%,100%{opacity:.45;transform:scale(.96)}50%{opacity:1;transform:scale(1.04)}}
.plugin-f1 .f1-copy{grid-area:race;align-self:stretch;border-left:2px solid rgba(229,160,13,.55);padding-left:clamp(1rem,2vw,1.6rem);display:grid;grid-template-columns:minmax(0,.92fr) minmax(290px,1.08fr);gap:clamp(1rem,2vw,1.7rem);align-items:start}.plugin-f1 .f1-race-hero{min-width:0}.plugin-f1 .f1-copy h1{font-size:clamp(1.8rem,3.2vw,3.25rem);line-height:.98;margin:.3rem 0 .35rem}.plugin-f1 .countdown{font-size:clamp(2rem,3.7vw,3.6rem);font-weight:900;letter-spacing:-.05em;margin:clamp(.7rem,2vh,1.2rem) 0}
.plugin-f1 .f1-weekend-column{display:grid;grid-template-rows:auto 1fr;gap:.9rem;min-width:0}.plugin-f1 .f1-session-block{margin-top:0;padding-top:0;border-top:0;min-width:0}.plugin-f1 .session-list{margin-top:.45rem;display:grid;gap:.26rem}.plugin-f1 .session-row{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:.7rem;align-items:center;min-height:2rem;padding:.34rem .5rem;border-radius:.38rem;background:rgba(255,255,255,.018);font-size:.64rem;border:1px solid rgba(255,255,255,.025)}.plugin-f1 .session-row.next{border-left:3px solid #62d5ff;background:rgba(98,213,255,.065)}.plugin-f1 .session-row.qualifying{min-height:2.35rem;padding:.44rem .6rem;background:rgba(229,160,13,.05);border-color:rgba(229,160,13,.16);font-size:.69rem}.plugin-f1 .session-row.race{min-height:2.8rem;padding:.58rem .7rem;background:linear-gradient(90deg,rgba(229,160,13,.12),rgba(229,160,13,.035));border-color:rgba(229,160,13,.3);font-size:.78rem}.plugin-f1 .session-row.race .session-name{font-size:.9rem;letter-spacing:.02em}.plugin-f1 .session-row.qualifying .session-name{font-size:.76rem}.plugin-f1 .session-name{font-weight:900}.plugin-f1 .session-date{color:var(--muted)}.plugin-f1 .session-countdown{color:#f4c45c;font-weight:900;min-width:3.8rem;text-align:right}

.plugin-f1 .f1-weather-block{min-width:0;padding-top:.75rem;border-top:1px solid var(--border)}
.plugin-f1 .weather-card{margin-top:.48rem;min-height:8.2rem;display:grid;grid-template-columns:minmax(0,1.1fr) repeat(3,minmax(78px,.72fr));gap:.45rem;align-items:stretch}
.plugin-f1 .weather-primary,.plugin-f1 .weather-metric{border:1px solid var(--border);border-radius:.45rem;background:rgba(255,255,255,.018);padding:.6rem .65rem}
.plugin-f1 .weather-primary{display:flex;flex-direction:column;justify-content:center;background:linear-gradient(145deg,rgba(98,213,255,.055),rgba(255,255,255,.012))}
.plugin-f1 .weather-condition{font-size:.9rem;font-weight:900;line-height:1.05}
.plugin-f1 .weather-temp{margin-top:.35rem;font-size:1.4rem;font-weight:950;letter-spacing:-.04em}
.plugin-f1 .weather-temp small{font-size:.56rem;font-weight:650;color:var(--muted)}
.plugin-f1 .weather-metric{display:flex;flex-direction:column;justify-content:center}
.plugin-f1 .weather-metric span{display:block;font-size:.48rem;color:var(--muted);font-weight:850;letter-spacing:.04em}
.plugin-f1 .weather-metric strong{display:block;margin-top:.18rem;font-size:.86rem}
.plugin-f1 .weather-note{grid-column:1/-1;color:var(--muted);font-size:.52rem}
.plugin-f1 .weather-unavailable{grid-column:1/-1;display:grid;place-items:center;min-height:6rem;border:1px dashed var(--border);border-radius:.45rem;color:var(--muted);font-size:.58rem}

.plugin-f1 .driver-standings{grid-area:drivers}.plugin-f1 .constructor-standings{grid-area:constructors}.plugin-f1 .standings-list{display:grid;gap:.28rem;margin-top:.5rem}.plugin-f1 .standing-row{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;align-items:center;gap:.5rem;min-height:1.65rem;padding:.18rem .35rem;border-radius:.35rem;background:rgba(255,255,255,.018)}.plugin-f1 .standing-pos{display:grid;place-items:center;width:1.55rem;height:1.55rem;border:1px solid var(--border);border-radius:.32rem;font-weight:900;font-size:.7rem;color:#fff}.plugin-f1 .standing-main{min-width:0}.plugin-f1 .standing-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.72rem;font-weight:820}.plugin-f1 .standing-sub{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--muted);font-size:.56rem}.plugin-f1 .standing-points{text-align:right;font-size:.72rem;font-weight:900;color:#f4c45c}.plugin-f1 .standing-points small{display:block;font-size:.5rem;font-weight:600;color:var(--muted)}
.plugin-f1 .recent-race{grid-area:recent}.plugin-f1 .recent-race-name{margin:.45rem 0 .55rem;font-size:.8rem;font-weight:900}.plugin-f1 .podium-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.4rem}.plugin-f1 .podium-card{padding:.5rem;border:1px solid var(--border);border-radius:.42rem;background:rgba(255,255,255,.015)}.plugin-f1 .podium-card strong{display:block;font-size:.74rem}.plugin-f1 .podium-card small{display:block;color:var(--muted);font-size:.5rem;margin-top:.15rem}.plugin-f1 .fastest-lap{margin-top:.55rem;font-size:.56rem;color:#c4d0d6}
.plugin-f1 .f1-headlines{grid-area:headlines}.plugin-f1 .headline-list{margin-top:.5rem;display:grid;gap:.3rem}.plugin-f1 .headline-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.6rem;align-items:start;padding:.38rem .42rem;border-radius:.36rem;background:rgba(255,255,255,.014);text-decoration:none;color:inherit;border:1px solid transparent}.plugin-f1 .headline-row:hover{border-color:rgba(229,160,13,.4);background:rgba(229,160,13,.04)}.plugin-f1 .headline-title{font-size:.62rem;font-weight:780;line-height:1.25}.plugin-f1 .headline-meta{font-size:.48rem;color:var(--muted);white-space:nowrap;text-align:right}
@media(min-width:1000px) and (max-height:500px){.plugin-f1 .f1-layout{grid-template-columns:minmax(330px,.78fr) minmax(510px,1.22fr);grid-template-areas:"track race" "drivers constructors" "recent headlines"}.plugin-f1 .track-surface{min-height:420px;grid-template-rows:auto minmax(350px,72vh) auto}.plugin-f1 .track-host{min-height:350px}.plugin-f1 .f1-copy{grid-template-columns:minmax(0,.9fr) minmax(280px,1.1fr)}.plugin-f1 .standing-row{min-height:1.42rem}.plugin-f1 .standing-name{font-size:.66rem}.plugin-f1 .standing-sub{font-size:.52rem}}
@media(max-width:1050px){.plugin-f1 .weather-card{grid-template-columns:1fr 1fr}.plugin-f1 .f1-layout{grid-template-columns:minmax(320px,.9fr) minmax(420px,1.1fr)}.plugin-f1 .f1-copy{grid-template-columns:1fr}.plugin-f1 .f1-session-block{margin-top:.85rem;padding-top:.65rem;border-top:1px solid var(--border)}}
@media(max-width:720px){.plugin-f1 .f1-layout{grid-template-columns:1fr;grid-template-areas:"race" "track" "drivers" "constructors" "recent" "headlines"}.plugin-f1 .f1-copy{border-left:0;padding-left:0}.plugin-f1 .track-surface{min-height:360px}}
@media(prefers-reduced-motion:reduce){.plugin-f1 .track-host .rackdash-racing-line{animation:none}.plugin-f1 .track-host::before{animation:none}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.f1={
  tracerAnimations:new WeakMap(),
  standings(rows,type){return (rows||[]).map(row=>`<div class="standing-row"><div class="standing-pos">${RackDash.escape(row.position||"-")}</div><div class="standing-main"><div class="standing-name">${RackDash.escape(row.code||row.name||"")}</div><div class="standing-sub">${RackDash.escape(type==="driver"?(row.team||row.name||""):(row.name||""))}</div></div><div class="standing-points">${RackDash.escape(row.points||"0")}<small>PTS${row.wins&&Number(row.wins)>0?` · ${RackDash.escape(row.wins)}W`:""}</small></div></div>`).join("")},
  duration(seconds){seconds=Math.max(0,Number(seconds||0));const d=Math.floor(seconds/86400),h=Math.floor((seconds%86400)/3600),m=Math.floor((seconds%3600)/60);if(d)return `${d}d ${h}h`;if(h)return `${h}h ${m}m`;return `${m}m`},
  newsAge(seconds){if(seconds==null)return "";seconds=Number(seconds);if(seconds<3600)return `${Math.max(1,Math.floor(seconds/60))}m ago`;if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;return `${Math.floor(seconds/86400)}d ago`},
  sessions(rows){if(!rows?.length)return `<div class="empty-state">Weekend schedule unavailable.</div>`;const now=Date.now()/1000;let foundNext=false;return rows.map(row=>{const epoch=Number(row.epoch||0),isFuture=epoch>=now-7200,isNext=!foundNext&&isFuture;if(isNext)foundNext=true;const date=epoch?new Date(epoch*1000).toLocaleString([],{weekday:"short",hour:"2-digit",minute:"2-digit"}):[row.date,row.time].filter(Boolean).join(" ");const kind=(row.name||"").toLowerCase().includes("qualifying")?"qualifying":((row.name||"").toLowerCase()==="race"?"race":"");return `<div class="session-row ${isNext?"next":""} ${kind}"><span class="session-name">${RackDash.escape(row.name||"Session")}</span><span class="session-date">${RackDash.escape(date)}</span><span class="session-countdown">${isNext?RackDash.escape(this.duration(Math.max(0,row.countdown||0))):""}</span></div>`}).join("")},
  recent(data){if(!data)return {podium:`<div class="empty-state">Recent race results unavailable.</div>`,fastest:""};const podium=(data.podium||[]).map(row=>`<div class="podium-card"><strong>P${RackDash.escape(row.position||"-")} · ${RackDash.escape(row.driver||"")}</strong><small>${RackDash.escape(row.team||"")}</small></div>`).join("");const fastest=data.fastest_lap?`FASTEST LAP · ${RackDash.escape(data.fastest_lap.driver||"")} · LAP ${RackDash.escape(data.fastest_lap.lap||"-")} · ${RackDash.escape(data.fastest_lap.time||"")}${data.fastest_lap.speed?` · ${RackDash.escape(data.fastest_lap.speed)} ${RackDash.escape(data.fastest_lap.speed_units||"")}`:""}`:"";return {podium,fastest}},
  headlines(rows){if(!rows?.length)return `<div class="empty-state">F1 headlines unavailable.</div>`;return rows.map(row=>`<a class="headline-row" href="${RackDash.escape(row.url||"#")}" target="_blank" rel="noopener"><span class="headline-title">${RackDash.escape(row.title||"")}</span><span class="headline-meta">${RackDash.escape(row.source||"")}${row.age_seconds!=null?`<br>${RackDash.escape(this.newsAge(row.age_seconds))}`:""}</span></a>`).join("")},
  weather(data){if(!data||!data.available)return `<div class="weather-unavailable">Race-day forecast is not available yet.</div>`;const high=data.temp_high_f==null?"--":`${Math.round(Number(data.temp_high_f))}°`,low=data.temp_low_f==null?"--":`${Math.round(Number(data.temp_low_f))}°`,rain=data.rain_chance==null?"--":`${Math.round(Number(data.rain_chance))}%`,wind=data.wind_mph==null?"--":`${Math.round(Number(data.wind_mph))} mph`,gust=data.gust_mph==null?"--":`${Math.round(Number(data.gust_mph))} mph`,precip=data.precipitation_in==null?"--":`${Number(data.precipitation_in).toFixed(2)} in`;return `<div class="weather-primary"><div class="weather-condition">${RackDash.escape(data.condition||"Forecast")}</div><div class="weather-temp">${RackDash.escape(high)} <small>HIGH · ${RackDash.escape(low)} LOW</small></div></div><div class="weather-metric"><span>RAIN CHANCE</span><strong>${RackDash.escape(rain)}</strong></div><div class="weather-metric"><span>MAX WIND</span><strong>${RackDash.escape(wind)}</strong></div><div class="weather-metric"><span>GUSTS</span><strong>${RackDash.escape(gust)}</strong></div><div class="weather-note">Expected precipitation: ${RackDash.escape(precip)} · Forecast updates automatically as race day approaches.</div>`},
  animateTrack(svg){if(!svg||window.matchMedia("(prefers-reduced-motion: reduce)").matches)return;const old=this.tracerAnimations.get(svg);if(old)cancelAnimationFrame(old);const candidates=[...svg.querySelectorAll("path")].filter(path=>{try{return path.getTotalLength()>20}catch(e){return false}});if(!candidates.length)return;candidates.sort((a,b)=>{try{return b.getTotalLength()-a.getTotalLength()}catch(e){return 0}});const path=candidates[0],racingLine=path.cloneNode(true);racingLine.removeAttribute("id");racingLine.classList.add("rackdash-racing-line");path.parentNode.appendChild(racingLine);const ns="http://www.w3.org/2000/svg",halo=document.createElementNS(ns,"circle"),tracer=document.createElementNS(ns,"circle");halo.setAttribute("r","10");halo.classList.add("rackdash-tracer-halo");tracer.setAttribute("r","4.2");tracer.classList.add("rackdash-tracer");svg.appendChild(halo);svg.appendChild(tracer);let length=0;try{length=path.getTotalLength()}catch(e){return}const started=performance.now();const frame=now=>{if(!svg.isConnected)return;const distance=(((now-started)/1000)/7.5%1)*length;try{const point=path.getPointAtLength(distance);tracer.setAttribute("cx",point.x);tracer.setAttribute("cy",point.y);halo.setAttribute("cx",point.x);halo.setAttribute("cy",point.y)}catch(e){}const id=requestAnimationFrame(frame);this.tracerAnimations.set(svg,id)};const id=requestAnimationFrame(frame);this.tracerAnimations.set(svg,id)},
  async render(data,root){
    root.querySelector('[data-role="drivers"]').innerHTML=this.standings(data.drivers,"driver")||`<div class="empty-state">Driver standings unavailable.</div>`;
    root.querySelector('[data-role="constructors"]').innerHTML=this.standings(data.constructors,"constructor")||`<div class="empty-state">Constructor standings unavailable.</div>`;
    root.querySelector('[data-role="headlines"]').innerHTML=this.headlines(data.headlines);
    const recent=this.recent(data.recent_race);root.querySelector('[data-role="recent-name"]').textContent=data.recent_race?.name||"Recent race";root.querySelector('[data-role="podium"]').innerHTML=recent.podium;root.querySelector('[data-role="fastest"]').textContent=recent.fastest;
    if(!data.available){root.querySelector('[data-role="name"]').textContent="No upcoming race";root.querySelector('[data-role="sessions"]').innerHTML=`<div class="empty-state">Weekend schedule unavailable.</div>`;return}
    root.querySelector('[data-role="name"]').textContent=data.name;const location=[data.city,data.country].filter(Boolean).join(" • ");root.querySelector('[data-role="race-location"]').textContent=[data.circuit,location].filter(Boolean).join(" • ");root.querySelector('[data-role="track-location"]').textContent=location;root.querySelector('[data-role="circuit"]').textContent=data.circuit||"";root.querySelector('[data-role="round"]').textContent=`ROUND ${data.round}`;root.querySelector('[data-role="date"]').textContent=data.date;root.querySelector('[data-role="time"]').textContent=data.time;
    const sec=Number(data.countdown||0);root.querySelector('[data-role="countdown"]').textContent=`${Math.floor(sec/86400)}d ${Math.floor((sec%86400)/3600)}h ${Math.floor((sec%3600)/60)}m`;root.querySelector('[data-role="sessions"]').innerHTML=this.sessions(data.sessions);
    const weather=root.querySelector('[data-role="race-weather"]');
    if(weather)weather.innerHTML=this.weather(data.race_weather);
    const host=root.querySelector('[data-role="track"]');if(!data.track_key)return;
    try{const response=await fetch(`/api/plugin/f1/track/${encodeURIComponent(data.track_key)}.svg`);if(!response.ok)return;host.innerHTML=await response.text();const svg=host.querySelector("svg");if(!svg)return;svg.removeAttribute("width");svg.removeAttribute("height");svg.setAttribute("preserveAspectRatio","xMidYMid meet");requestAnimationFrame(()=>{try{const box=(svg.querySelector("g")||svg).getBBox(),pad=Math.max(box.width,box.height)*.035;svg.setAttribute("viewBox",`${box.x-pad} ${box.y-pad} ${box.width+pad*2} ${box.height+pad*2}`)}catch(e){}this.animateTrack(svg)})}catch(e){}
  }
};
'''
