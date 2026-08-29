from __future__ import annotations

import html
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

import requests

from _shared import TTLCache


PLUGIN_ID = "supercars"
PLUGIN_NAME = "V8 Supercars"
PLUGIN_VERSION = "3.0.3"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/supercars.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 45
PLUGIN_REFRESH_SECONDS = 300
PLUGIN_ACCENT = "#e6332a"
PLUGIN_ICON = "V8"
PLUGIN_PUBLIC_ERROR = "Supercars data unavailable"

PLUGIN_CONFIG = [
    {
        "key": "SUPERCARS_NEWS_RSS",
        "label": "Supercars Headlines RSS",
        "type": "text",
        "default": "https://news.google.com/rss/search?q=Repco+Supercars+Championship&hl=en-AU&gl=AU&ceid=AU:en",
        "required": False,
    }
]

SUPERCARS_NEWS_RSS = os.getenv(
    "SUPERCARS_NEWS_RSS",
    "https://news.google.com/rss/search?q=Repco+Supercars+Championship&hl=en-AU&gl=AU&ceid=AU:en",
).strip()

BASE = "https://www.supercars.com"
_cache = TTLCache(900)
_news_cache = TTLCache(600)
_weather_cache = TTLCache(1800)


# Official 2026 championship calendar. Supercars announced 14 rounds for 2026.
# Exact session times are not consistently published far in advance, so this
# plugin presents event-weekend dates and refreshes standings/results live.
CALENDAR_2026 = [
    {"round":1,"name":"Sydney 500","start":"2026-02-20","end":"2026-02-22","circuit":"Sydney Motorsport Park","city":"Sydney","region":"NSW","lat":-33.805,"lon":150.870,"format":"500","track_path":"M190 480 C130 405 155 285 245 235 L330 180 L430 200 L500 145 L610 180 L680 245 L790 230 L835 330 L780 420 L685 440 L615 505 L500 480 L405 525 L300 500 Z"},
    {"round":2,"name":"Melbourne SuperSprint","start":"2026-03-05","end":"2026-03-08","circuit":"Albert Park Grand Prix Circuit","city":"Melbourne","region":"VIC","lat":-37.8497,"lon":144.968,"format":"SuperSprint","track_path":"M180 455 L145 305 L220 210 L345 185 L430 125 L545 165 L650 140 L770 205 L835 300 L805 405 L700 435 L625 500 L510 470 L420 520 L305 490 L230 520 Z"},
    {"round":3,"name":"ITM Taupō Super 440","start":"2026-04-10","end":"2026-04-12","circuit":"Taupō International Motorsport Park","city":"Taupō","region":"NZ","lat":-38.665,"lon":176.143,"format":"Super 440","track_path":"M175 460 C120 385 155 270 255 235 C345 205 380 145 470 150 C560 155 585 220 665 205 C755 190 820 250 820 340 C820 425 745 445 685 485 C620 530 530 520 455 480 C385 445 305 535 235 495 Z"},
    {"round":4,"name":"Christchurch Super 440","start":"2026-04-17","end":"2026-04-19","circuit":"Euromarque Motorsport Park","city":"Christchurch","region":"NZ","lat":-43.531,"lon":172.480,"format":"Super 440","track_path":"M155 480 L140 350 L210 245 L320 225 L390 155 L510 170 L590 235 L690 210 L820 270 L840 375 L750 440 L650 420 L565 510 L450 480 L340 525 L250 500 Z"},
    {"round":5,"name":"Tasmania Super 440","start":"2026-05-22","end":"2026-05-24","circuit":"Symmons Plains Raceway","city":"Launceston","region":"TAS","lat":-41.661,"lon":147.253,"format":"Super 440","track_path":"M220 330 C220 180 355 140 500 150 C655 160 790 215 790 330 C790 445 655 500 500 510 C355 520 220 475 220 330 Z"},
    {"round":6,"name":"betr Darwin Triple Crown","start":"2026-06-19","end":"2026-06-21","circuit":"Hidden Valley Raceway","city":"Darwin","region":"NT","lat":-12.448,"lon":130.907,"format":"Triple Crown","track_path":"M165 445 C120 360 165 260 255 230 L350 170 L455 190 L530 135 L645 175 L730 245 L825 300 L790 400 L700 420 L630 505 L520 530 L430 475 L335 520 L235 485 Z"},
    {"round":7,"name":"NTI Townsville 500","start":"2026-07-10","end":"2026-07-12","circuit":"Reid Park Street Circuit","city":"Townsville","region":"QLD","lat":-19.270,"lon":146.815,"format":"500","track_path":"M150 490 L140 345 L205 285 L180 205 L305 165 L390 220 L475 145 L585 165 L675 230 L795 210 L845 315 L805 430 L695 460 L595 435 L505 515 L385 485 L270 525 Z"},
    {"round":8,"name":"Perth Super 440","start":"2026-07-31","end":"2026-08-02","circuit":"Carco.com.au Raceway","city":"Perth","region":"WA","lat":-31.664,"lon":115.787,"format":"Super 440","track_path":"M180 455 C120 375 150 270 250 240 C340 215 370 155 460 155 C545 155 580 215 655 200 C750 180 820 245 825 335 C830 420 755 445 685 465 C615 485 585 535 495 520 C405 505 360 455 285 500 C230 530 205 495 180 455 Z"},
    {"round":9,"name":"Century Batteries Ipswich Super 440","start":"2026-08-21","end":"2026-08-23","circuit":"Queensland Raceway","city":"Ipswich","region":"QLD","lat":-27.690,"lon":152.654,"format":"Super 440","track_path":"M210 325 C210 180 350 140 500 145 C655 150 800 205 800 325 C800 445 655 500 500 505 C350 510 210 470 210 325 Z"},
    {"round":10,"name":"AirTouch 500 at The Bend","start":"2026-09-11","end":"2026-09-13","circuit":"Shell V-Power Motorsport Park","city":"Tailem Bend","region":"SA","lat":-35.307,"lon":139.512,"format":"Enduro 500","track_path":"M160 430 C120 340 155 245 255 220 L340 160 L445 180 L535 125 L650 165 L735 250 L825 305 L780 395 L690 420 L635 505 L525 535 L440 480 L350 520 L245 480 Z"},
    {"round":11,"name":"Repco Bathurst 1000","start":"2026-10-08","end":"2026-10-11","circuit":"Mount Panorama Circuit","city":"Bathurst","region":"NSW","lat":-33.445,"lon":149.557,"format":"Enduro 1000","track_path":"M170 465 L145 335 L205 245 L320 215 L410 145 L535 160 L610 220 L715 200 L825 280 L815 395 L725 445 L625 430 L535 510 L420 490 L335 535 L250 505 Z"},
    {"round":12,"name":"Boost Mobile Gold Coast 500","start":"2026-10-23","end":"2026-10-25","circuit":"Surfers Paradise Street Circuit","city":"Gold Coast","region":"QLD","lat":-27.998,"lon":153.429,"format":"Finals","track_path":"M150 480 L135 345 L220 300 L185 210 L305 160 L395 215 L480 140 L600 165 L675 230 L790 215 L845 320 L800 435 L690 465 L585 440 L505 520 L385 490 L270 525 Z"},
    {"round":13,"name":"Penrite Oil Sandown 500","start":"2026-11-06","end":"2026-11-08","circuit":"Sandown Raceway","city":"Melbourne","region":"VIC","lat":-37.951,"lon":145.165,"format":"Finals 500","track_path":"M170 450 C115 365 150 260 245 235 C335 210 370 155 455 150 C540 145 585 205 650 190 C750 170 820 240 825 325 C830 410 755 440 690 455 C620 470 585 530 495 520 C405 510 360 455 290 500 C235 530 200 495 170 450 Z"},
    {"round":14,"name":"bp Adelaide Grand Final","start":"2026-11-26","end":"2026-11-29","circuit":"Adelaide Street Circuit","city":"Adelaide","region":"SA","lat":-34.927,"lon":138.617,"format":"Grand Final","track_path":"M145 470 L135 340 L205 255 L300 235 L360 160 L485 135 L565 190 L660 160 L790 230 L840 335 L800 445 L695 425 L620 505 L505 475 L415 525 L295 490 L225 525 Z"},
]


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self._cell.append(value)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self._text.append(value)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def _fetch(url):
    response = requests.get(
        url,
        timeout=8,
        headers={"User-Agent": "RackDash-Supercars/3.0.3"},
    )
    response.raise_for_status()
    return response.text


def _tables(url):
    parser = TableParser()
    parser.feed(_fetch(url))
    return parser.tables


def _split_driver_cell(text):
    text = re.sub(r"\s+", " ", text).strip()
    number = ""
    match = re.match(r"^(\d{1,3})\s*(.*)$", text)
    if match:
        number, text = match.group(1), match.group(2).strip()

    # Official cells concatenate driver and team text. Team names are difficult
    # to separate perfectly without private site data, so use known team suffix
    # markers and preserve the whole label if a split cannot be inferred.
    team_markers = [
        "Red Bull Ampol Racing","Penrite Racing","Shell V-Power Racing Team",
        "Monster Castrol Racing","DEWALT Racing","Mobil1 Optus Racing",
        "Mobil1 Truck Assist Racing","CoolDrive Racing","Brad Jones Racing",
        "PremiAir Racing","Erebus Motorsport","Objective Racing",
        "Bendix Racing","Sherrin Rentals Racing","Snowy River Caravans Racing",
        "LIQUI MOLY BLAHST Racing",
    ]
    for marker in team_markers:
        idx = text.find(marker)
        if idx > 0:
            return number, text[:idx].strip(), text[idx:].strip()
    return number, text, ""


def _driver_standings(year):
    tables = _tables(f"{BASE}/standings/{year}/supercars")
    for table in tables:
        header = " | ".join(table[0]).lower()
        if "driver" not in header or "pts" not in header:
            continue
        result = []
        for cells in table[1:]:
            if len(cells) < 5:
                continue
            # Common layout: Pos | Driver | Wins | Poles | Pts | Gap
            pos = re.sub(r"\D", "", cells[0]) or cells[0]
            number, name, team = _split_driver_cell(cells[1])
            wins = cells[2] if len(cells) > 2 else "0"
            poles = cells[3] if len(cells) > 3 else "0"
            points = cells[4] if len(cells) > 4 else "0"
            gap = cells[5] if len(cells) > 5 else ""
            result.append({
                "position": pos,
                "number": number,
                "name": name,
                "team": team,
                "wins": wins,
                "poles": poles,
                "points": points,
                "gap": gap,
            })
            if len(result) >= 10:
                break
        if result:
            return result
    return []


def _team_standings(year):
    tables = _tables(f"{BASE}/standings/{year}/supercars/teams")
    for table in tables:
        result = []
        for cells in table[1:] if len(table) > 1 else []:
            if len(cells) < 2:
                continue
            text = " ".join(cells[:-1]).strip()
            points = cells[-1]
            match = re.match(r"^(\d+)\s+(.*)$", text)
            if not match:
                continue
            result.append({
                "position": match.group(1),
                "name": match.group(2).strip(),
                "points": points,
            })
            if len(result) >= 10:
                break
        if result:
            return result
    return []


def _recent_race(year):
    try:
        url = f"{BASE}/results/{year}/supercars"
        source = _fetch(url)
        links = LinkParser()
        links.feed(source)

        candidates = []
        for href, label in links.links:
            if not href:
                continue
            if re.search(rf"/results/{year}/[^/]+/R\d+$", href):
                candidates.append(href)

        if not candidates:
            return None

        href = candidates[-1]
        page = _fetch(BASE + href if href.startswith("/") else href)

        title = ""
        match = re.search(
            r"Repco Supercars Championship\s*-\s*(Race\s+\d+)",
            re.sub(r"<[^>]+>", " ", page),
            re.I,
        )
        if match:
            title = match.group(1)

        parser = TableParser()
        parser.feed(page)
        podium = []

        for table in parser.tables:
            if not table:
                continue
            header = " | ".join(table[0]).lower()
            if "race time" not in header or "laps" not in header:
                continue
            for cells in table[1:4]:
                if not cells:
                    continue
                number, driver, team = _split_driver_cell(cells[0])
                podium.append({
                    "position": str(len(podium) + 1),
                    "driver": driver,
                    "team": team,
                    "number": number,
                })
            break

        return {
            "name": title or "Latest race",
            "podium": podium,
        }
    except Exception:
        return None


def _headlines():
    cached = _news_cache.get()
    if cached is not None:
        return cached
    if not SUPERCARS_NEWS_RSS:
        return []

    try:
        response = requests.get(
            SUPERCARS_NEWS_RSS,
            timeout=7,
            headers={"User-Agent": "RackDash-Supercars/3.0.3"},
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

            epoch = None
            try:
                dt = parsedate_to_datetime(item.findtext("pubDate") or "")
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


def _next_event(now=None):
    now = now or datetime.now(timezone.utc)
    for event in CALENDAR_2026:
        end = datetime.fromisoformat(event["end"] + "T23:59:59+10:00")
        if end.timestamp() >= now.timestamp():
            row = dict(event)
            # Countdown targets the first day at 9am local-ish. Exact race start
            # times vary per event and are added by Supercars closer to race day.
            start = datetime.fromisoformat(event["start"] + "T09:00:00+10:00")
            row["event_epoch"] = start.timestamp()
            row["countdown"] = max(0, int(start.timestamp() - now.timestamp()))
            row["sessions"] = [
                {"name":"Event opens","date":event["start"]},
                {"name":"Race weekend","date":f'{event["start"]} → {event["end"]}'},
                {"name":"Format","date":event["format"]},
            ]
            return row
    return None


def _weather_code_label(code):
    labels = {0:"Clear",1:"Mostly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Fog",51:"Drizzle",53:"Drizzle",55:"Heavy drizzle",61:"Light rain",63:"Rain",65:"Heavy rain",80:"Showers",81:"Showers",82:"Heavy showers",95:"Thunderstorms",96:"Storms + hail",99:"Severe storms"}
    try:
        return labels.get(int(code), "Forecast")
    except Exception:
        return "Forecast"


def _event_weather(event):
    if not event:
        return None

    key = f'{event["lat"]},{event["lon"]},{event["start"]}'
    cached = _weather_cache.get()
    if cached and cached.get("_key") == key:
        return dict(cached)

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": event["lat"],
                "longitude": event["lon"],
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "start_date": event["start"],
                "end_date": event["start"],
            },
            timeout=7,
            headers={"User-Agent": "RackDash-Supercars/3.0.3"},
        )
        response.raise_for_status()
        daily = response.json().get("daily") or []

        def first(key, default=None):
            values = daily.get(key) or []
            return values[0] if values else default

        if not daily.get("time"):
            raise RuntimeError("forecast outside range")

        result = {
            "_key": key,
            "available": True,
            "condition": _weather_code_label(first("weather_code")),
            "temp_high_f": first("temperature_2m_max"),
            "temp_low_f": first("temperature_2m_min"),
            "rain_chance": first("precipitation_probability_max"),
            "wind_mph": first("wind_speed_10m_max"),
            "gust_mph": first("wind_gusts_10m_max"),
        }
    except Exception:
        result = {"_key": key, "available": False}

    _weather_cache.set(result)
    return dict(result)


def _dynamic(data):
    now = datetime.now(timezone.utc).timestamp()
    result = dict(data)

    event = result.get("event")
    if event:
        event = dict(event)
        event["countdown"] = max(0, int(event.get("event_epoch", now) - now))
        result["event"] = event

    headlines = []
    for headline in result.get("headlines", []):
        row = dict(headline)
        epoch = row.get("published_epoch")
        row["age_seconds"] = max(0, int(now - epoch)) if epoch else None
        headlines.append(row)
    result["headlines"] = headlines
    return result


def get_data():
    cached = _cache.get()
    if cached is not None:
        cached = dict(cached)
        cached["headlines"] = _headlines()
        return _dynamic(cached)

    year = datetime.now(timezone.utc).year
    if year != 2026:
        year = 2026

    event = _next_event()
    data = {
        "year": year,
        "event": event,
        "drivers": _driver_standings(year),
        "teams": _team_standings(year),
        "recent_race": _recent_race(year),
        "headlines": _headlines(),
        "weather": _event_weather(event),
        "total_rounds": len(CALENDAR_2026),
    }

    return _cache.set(_dynamic(data))


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
        return {"title":"Supercars","lines":["Data unavailable"]}

    lines = []
    event = data.get("event") or {}
    if event:
        lines.append(str(event.get("name",""))[:18])
        lines.append(f'R{event.get("round","?")} {_short_countdown(event.get("countdown",0))}')

    drivers = data.get("drivers") or []
    if drivers:
        leader = drivers[0]
        lines.append(f'P1 {leader.get("name","")[:9]} {leader.get("points","0")}pt')

    return {"title":"V8 Supercars","lines":lines[:4]}


PLUGIN_HTML = r'''
<div class="sc-layout">
  <section class="surface sc-track">
    <div class="track-topline">
      <span class="section-label">NEXT CIRCUIT</span>
      <span class="track-location" data-role="location"></span>
    </div>
    <div class="sc-track-visual">
      <div class="sc-track-floor"></div>
      <svg class="sc-track-svg" viewBox="0 0 1000 650" preserveAspectRatio="xMidYMid meet" role="img" aria-label="3D Supercars circuit map">
        <defs>
          <filter id="scTrackGlow">
            <feGaussianBlur stdDeviation="8" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <linearGradient id="scTrackGradient" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#ffffff"/>
            <stop offset="45%" stop-color="#ff897f"/>
            <stop offset="100%" stop-color="#e6332a"/>
          </linearGradient>
        </defs>
        <path class="sc-track-shadow" data-role="track-shadow" d=""></path>
        <path class="sc-track-road" data-role="track-road" d=""></path>
        <path class="sc-track-light" data-role="track-light" d=""></path>
        <circle class="sc-start-dot" data-role="start-dot" cx="0" cy="0" r="9"></circle>
      </svg>
      <div class="sc-track-caption">
        <span data-role="track-kind">CIRCUIT</span>
        <strong data-role="circuit">--</strong>
      </div>
    </div>
    <div class="track-legend">
      <span><i class="track-glow"></i> REPCO SUPERCARS CHAMPIONSHIP</span>
      <span data-role="format"></span>
    </div>
  </section>

  <section class="surface sc-copy">
    <div class="sc-race-hero">
      <span class="eyebrow">NEXT SUPERCARS EVENT</span>
      <h1 data-role="name">Loading...</h1>
      <div class="muted" data-role="event-location"></div>
      <div class="countdown" data-role="countdown">--d --h --m</div>
      <div class="chip-row">
        <span data-role="round"></span>
        <span data-role="season-progress"></span>
        <span data-role="dates"></span>
      </div>
    </div>
    <div class="sc-weekend-column">
      <div>
        <div class="section-label">EVENT WEEKEND</div>
        <div class="session-list" data-role="sessions"></div>
      </div>
      <div class="sc-weather-block">
        <div class="section-label">EXPECTED OPENING-DAY WEATHER</div>
        <div class="weather-card" data-role="weather"></div>
      </div>
    </div>
  </section>

  <section class="surface sc-standings">
    <div class="section-label">DRIVER CHAMPIONSHIP · TOP 10</div>
    <div class="standings-list" data-role="drivers"></div>
  </section>

  <section class="surface sc-standings">
    <div class="section-label">TEAMS CHAMPIONSHIP · TOP 10</div>
    <div class="standings-list" data-role="teams"></div>
  </section>

  <section class="surface sc-recent">
    <div class="section-label">LAST RACE</div>
    <div class="recent-race-name" data-role="recent-name">--</div>
    <div class="podium-list" data-role="podium"></div>
  </section>

  <section class="surface sc-headlines">
    <div class="section-label">SUPERCARS HEADLINES</div>
    <div class="headline-list" data-role="headlines"></div>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-supercars{--sc:#e6332a;--sc-soft:rgba(230,51,42,.075);--sc-line:rgba(230,51,42,.3)}
.plugin-supercars .sc-layout{display:grid;grid-template-columns:minmax(360px,.82fr) minmax(520px,1.18fr);grid-template-areas:"track race" "drivers teams" "recent headlines";gap:calc(var(--gap)*1.15);align-items:stretch}
.plugin-supercars .sc-track{grid-area:track;display:grid;grid-template-rows:auto minmax(260px,1fr) auto;min-height:390px;overflow:hidden}
.plugin-supercars .sc-copy{grid-area:race;display:grid;grid-template-columns:minmax(0,1fr) minmax(290px,.9fr);gap:var(--gap);border-left:3px solid var(--sc);background:linear-gradient(110deg,rgba(230,51,42,.055),rgba(255,255,255,.007) 45%,rgba(255,255,255,.004))}
.plugin-supercars .sc-standings:nth-of-type(3){grid-area:drivers}.plugin-supercars .sc-standings:nth-of-type(4){grid-area:teams}.plugin-supercars .sc-recent{grid-area:recent}.plugin-supercars .sc-headlines{grid-area:headlines}
.plugin-supercars .track-topline,.plugin-supercars .track-legend{display:flex;justify-content:space-between;gap:.6rem;align-items:center}.plugin-supercars .track-location,.plugin-supercars .track-legend{font-size:.46rem;color:var(--muted)}
.plugin-supercars .sc-track-visual{position:relative;display:grid;place-items:center;min-height:280px;overflow:hidden;perspective:1000px;background:radial-gradient(circle at 50% 43%,rgba(230,51,42,.10),transparent 38%)}
.plugin-supercars .sc-track-floor{position:absolute;width:82%;height:58%;left:9%;bottom:7%;transform:rotateX(72deg);transform-origin:center bottom;border-radius:50%;background:radial-gradient(ellipse at center,rgba(230,51,42,.07),rgba(255,255,255,.01) 46%,transparent 73%);border:1px solid rgba(230,51,42,.035)}
.plugin-supercars .sc-track-floor::after{content:"";position:absolute;inset:0;border-radius:50%;background-image:linear-gradient(rgba(230,51,42,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(230,51,42,.025) 1px,transparent 1px);background-size:28px 28px;mask-image:radial-gradient(ellipse at center,#000,transparent 72%)}
.plugin-supercars .sc-track-svg{position:relative;z-index:2;width:min(92%,720px);height:88%;min-height:265px;overflow:visible;transform:rotateX(54deg) rotateZ(-2deg) translateY(-2%);transform-origin:center center;filter:drop-shadow(0 27px 18px rgba(0,0,0,.55))}
.plugin-supercars .sc-track-shadow,.plugin-supercars .sc-track-road,.plugin-supercars .sc-track-light{fill:none;stroke-linecap:round;stroke-linejoin:round}
.plugin-supercars .sc-track-shadow{stroke:#000;stroke-width:42;opacity:.62;transform:translateY(14px)}
.plugin-supercars .sc-track-road{stroke:#21191a;stroke-width:32}
.plugin-supercars .sc-track-light{stroke:url(#scTrackGradient);stroke-width:11;filter:url(#scTrackGlow);stroke-dasharray:19 11;animation:scTrackDash 2.35s linear infinite}
.plugin-supercars .sc-start-dot{fill:#fff;stroke:var(--sc);stroke-width:5;filter:drop-shadow(0 0 8px rgba(230,51,42,.78))}
.plugin-supercars .sc-track-caption{position:absolute;z-index:5;bottom:.45rem;left:50%;transform:translateX(-50%);width:92%;text-align:center;text-shadow:0 2px 12px #000}
.plugin-supercars .sc-track-caption span{display:block;font-size:.42rem;letter-spacing:.12em;color:var(--sc);font-weight:900}
.plugin-supercars .sc-track-caption strong{display:block;margin-top:.08rem;font-size:.66rem;color:#dce8ee}
@keyframes scTrackDash{to{stroke-dashoffset:-60}}
.plugin-supercars .track-glow{display:inline-block;width:.6rem;height:.18rem;border-radius:1rem;background:var(--sc);box-shadow:0 0 10px rgba(230,51,42,.5)}
.plugin-supercars .sc-race-hero h1{font-size:clamp(1.5rem,3vw,2.6rem);line-height:1;margin:.18rem 0}.plugin-supercars .countdown{font-size:clamp(1.5rem,3vw,2.5rem);font-weight:950;margin:.65rem 0;color:#fff}
.plugin-supercars .sc-weather-block{margin-top:.8rem;padding-top:.7rem;border-top:1px solid var(--border)}
.plugin-supercars .session-list{display:grid;gap:.3rem;margin-top:.45rem}.plugin-supercars .session-row{display:grid;grid-template-columns:1fr auto;gap:.5rem;padding:.35rem .45rem;border:1px solid var(--border);border-radius:.35rem;background:rgba(255,255,255,.012);font-size:.5rem}.plugin-supercars .session-row span:last-child{color:var(--muted)}
.plugin-supercars .weather-card{display:grid;grid-template-columns:1.3fr repeat(2,1fr);gap:.35rem;margin-top:.45rem}.plugin-supercars .weather-primary,.plugin-supercars .weather-metric{padding:.45rem;border:1px solid var(--border);border-radius:.4rem;background:rgba(255,255,255,.012)}.plugin-supercars .weather-condition{font-size:.58rem;font-weight:850}.plugin-supercars .weather-temp{font-size:.86rem;font-weight:900}.plugin-supercars .weather-temp small,.plugin-supercars .weather-metric span{display:block;font-size:.4rem;color:var(--muted)}.plugin-supercars .weather-metric strong{font-size:.65rem}
.plugin-supercars .standings-list{display:grid;gap:.22rem;margin-top:.48rem}.plugin-supercars .standing-row{display:grid;grid-template-columns:2rem minmax(0,1fr) auto;gap:.45rem;align-items:center;min-height:1.7rem;padding:.2rem .35rem;border-bottom:1px solid rgba(255,255,255,.035)}.plugin-supercars .standing-pos{font-size:.52rem;font-weight:950;color:var(--sc)}.plugin-supercars .standing-name{font-size:.59rem;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-supercars .standing-sub{font-size:.43rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-supercars .standing-points{text-align:right;font-size:.59rem;font-weight:900}.plugin-supercars .standing-points small{display:block;font-size:.39rem;color:var(--muted)}
.plugin-supercars .recent-race-name{margin:.45rem 0;font-size:.72rem;font-weight:900}.plugin-supercars .podium-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.35rem}.plugin-supercars .podium-card{padding:.48rem;border:1px solid var(--border);border-radius:.4rem}.plugin-supercars .podium-card strong{display:block;font-size:.57rem}.plugin-supercars .podium-card small{display:block;margin-top:.1rem;font-size:.42rem;color:var(--muted)}
.plugin-supercars .headline-list{display:grid;gap:.28rem;margin-top:.45rem}.plugin-supercars .headline-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.6rem;padding:.35rem .42rem;border:1px solid rgba(255,255,255,.035);border-radius:.35rem;text-decoration:none;color:inherit}.plugin-supercars .headline-title{font-size:.55rem;font-weight:780;line-height:1.2}.plugin-supercars .headline-meta{font-size:.42rem;color:var(--muted);text-align:right;white-space:nowrap}
@media(max-width:1050px){.plugin-supercars .sc-layout{grid-template-columns:minmax(320px,.9fr) minmax(420px,1.1fr)}.plugin-supercars .sc-copy{grid-template-columns:1fr}.plugin-supercars .weather-card{grid-template-columns:1fr 1fr}}
@media(max-width:720px){.plugin-supercars .sc-layout{grid-template-columns:1fr;grid-template-areas:"race" "track" "drivers" "teams" "recent" "headlines"}.plugin-supercars .sc-copy{border-left:0}.plugin-supercars .podium-list{grid-template-columns:1fr}.plugin-supercars .sc-track-svg{width:96%;height:82%}}
@media(prefers-reduced-motion:reduce){.plugin-supercars .sc-track-light{animation:none!important}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.supercars={
  duration(seconds){seconds=Math.max(0,Number(seconds||0));const d=Math.floor(seconds/86400),h=Math.floor((seconds%86400)/3600),m=Math.floor((seconds%3600)/60);if(d)return `${d}d ${h}h`;if(h)return `${h}h ${m}m`;return `${m}m`},
  age(seconds){if(seconds==null)return "";seconds=Number(seconds);if(seconds<3600)return `${Math.max(1,Math.floor(seconds/60))}m ago`;if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;return `${Math.floor(seconds/86400)}d ago`},
  standings(rows,drivers=false){return (rows||[]).map(row=>`<div class="standing-row"><div class="standing-pos">${RackDash.escape(row.position||"-")}</div><div><div class="standing-name">${RackDash.escape(drivers?`${row.number?`#${row.number} `:""}${row.name||""}`:row.name||"")}</div><div class="standing-sub">${RackDash.escape(drivers?(row.team||""):"")}${drivers&&row.gap&&row.gap!=="0"?` · GAP ${RackDash.escape(row.gap)}`:""}</div></div><div class="standing-points">${RackDash.escape(row.points||"0")}<small>PTS${drivers&&row.wins&&Number(row.wins)>0?` · ${RackDash.escape(row.wins)}W`:""}</small></div></div>`).join("")},
  sessions(rows){return (rows||[]).map(row=>`<div class="session-row"><span>${RackDash.escape(row.name||"")}</span><span>${RackDash.escape(row.date||"")}</span></div>`).join("")||`<div class="empty-state">Event schedule unavailable.</div>`},
  weather(data){if(!data?.available)return `<div class="empty-state">Forecast not available yet.</div>`;return `<div class="weather-primary"><div class="weather-condition">${RackDash.escape(data.condition||"Forecast")}</div><div class="weather-temp">${Math.round(Number(data.temp_high_f||0))}° <small>HIGH · ${Math.round(Number(data.temp_low_f||0))}° LOW</small></div></div><div class="weather-metric"><span>RAIN CHANCE</span><strong>${Math.round(Number(data.rain_chance||0))}%</strong></div><div class="weather-metric"><span>MAX WIND</span><strong>${Math.round(Number(data.wind_mph||0))} mph</strong></div>`},
  headlines(rows){return (rows||[]).map(row=>`<a class="headline-row" href="${RackDash.escape(row.url||"#")}" target="_blank" rel="noopener"><span class="headline-title">${RackDash.escape(row.title||"")}</span><span class="headline-meta">${RackDash.escape(row.source||"")}${row.age_seconds!=null?`<br>${RackDash.escape(this.age(row.age_seconds))}`:""}</span></a>`).join("")||`<div class="empty-state">Supercars headlines unavailable.</div>`},
  renderTrack(event,root){
    const path=String(event?.track_path||"");
    const road=root.querySelector('[data-role="track-road"]');
    const shadow=root.querySelector('[data-role="track-shadow"]');
    const light=root.querySelector('[data-role="track-light"]');
    const dot=root.querySelector('[data-role="start-dot"]');
    [road,shadow,light].forEach(node=>{if(node)node.setAttribute("d",path)});
    if(light&&dot&&path){
      try{
        const len=light.getTotalLength();
        const point=light.getPointAtLength(Math.min(18,len*.03));
        dot.setAttribute("cx",point.x);
        dot.setAttribute("cy",point.y);
      }catch(_err){
        dot.setAttribute("cx","0");
        dot.setAttribute("cy","0");
      }
    }
  },
  render(data,root){
    root.querySelector('[data-role="drivers"]').innerHTML=this.standings(data.drivers,true)||`<div class="empty-state">Driver standings unavailable.</div>`;
    root.querySelector('[data-role="teams"]').innerHTML=this.standings(data.teams,false)||`<div class="empty-state">Team standings unavailable.</div>`;
    root.querySelector('[data-role="headlines"]').innerHTML=this.headlines(data.headlines);

    const recent=data.recent_race;
    root.querySelector('[data-role="recent-name"]').textContent=recent?.name||"Latest race";
    root.querySelector('[data-role="podium"]').innerHTML=(recent?.podium||[]).map(row=>`<div class="podium-card"><strong>P${RackDash.escape(row.position||"-")} · ${RackDash.escape(row.driver||"")}</strong><small>${RackDash.escape(row.team||"")}</small></div>`).join("")||`<div class="empty-state">Recent results unavailable.</div>`;

    const e=data.event;
    if(!e){
      root.querySelector('[data-role="name"]').textContent="Season complete";
      return;
    }

    root.querySelector('[data-role="name"]').textContent=e.name;
    root.querySelector('[data-role="circuit"]').textContent=e.circuit||"";
    root.querySelector('[data-role="location"]').textContent=[e.city,e.region].filter(Boolean).join(", ");
    root.querySelector('[data-role="event-location"]').textContent=[e.circuit,e.city,e.region].filter(Boolean).join(" • ");
    root.querySelector('[data-role="format"]').textContent=e.format||"";
    root.querySelector('[data-role="round"]').textContent=`ROUND ${e.round}`;
    root.querySelector('[data-role="season-progress"]').textContent=`${e.round}/${data.total_rounds||14} ROUNDS`;
    root.querySelector('[data-role="dates"]').textContent=`${e.start} → ${e.end}`;
    root.querySelector('[data-role="countdown"]').textContent=this.duration(e.countdown);
    root.querySelector('[data-role="sessions"]').innerHTML=this.sessions(e.sessions);
    root.querySelector('[data-role="weather"]').innerHTML=this.weather(data.weather);
    const trackKind=root.querySelector('[data-role="track-kind"]');
    if(trackKind)trackKind.textContent=(e.format||"CIRCUIT").toUpperCase();
    this.renderTrack(e,root);
  }
};
'''
