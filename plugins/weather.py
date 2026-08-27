from __future__ import annotations
import os
import requests
from _shared import TTLCache

PLUGIN_ID = "weather"
PLUGIN_NAME = "Weather"
PLUGIN_VERSION = "1.0.0"
PLUGIN_GITHUB = "https://github.com/YOUR_GITHUB_USERNAME/RackDash"
PLUGIN_ORDER = 30
PLUGIN_REFRESH_SECONDS = 300
PLUGIN_ACCENT = "#6fb7ff"
PLUGIN_ICON = "WX"
PLUGIN_PUBLIC_ERROR = "Weather unavailable"

PLUGIN_CONFIG = [{'key': 'WEATHER_LOCATION', 'label': 'City / State / ZIP', 'type': 'text', 'default': '', 'required': True}, {'key': 'WEATHER_UNITS', 'label': 'Units', 'type': 'select', 'default': 'fahrenheit', 'options': [{'value': 'fahrenheit', 'label': 'Fahrenheit'}, {'value': 'celsius', 'label': 'Celsius'}]}]

LOCATION = os.getenv("WEATHER_LOCATION", "")
UNITS = os.getenv("WEATHER_UNITS", "fahrenheit").lower()
_cache = TTLCache(600)


def get_data():
    cached = _cache.get()
    if cached:
        return cached
    if not LOCATION:
        return {"configured": False}

    geo = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": LOCATION, "count": 1, "language": "en", "format": "json"},
        timeout=5,
    )
    geo.raise_for_status()
    results = geo.json().get("results") or []
    if not results:
        raise RuntimeError("Location not found")

    loc = results[0]
    temp_unit = "fahrenheit" if UNITS.startswith("f") else "celsius"
    wind_unit = "mph" if UNITS.startswith("f") else "kmh"
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day,precipitation",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset",
            "temperature_unit": temp_unit,
            "wind_speed_unit": wind_unit,
            "timezone": "auto",
            "forecast_days": 5,
        },
        timeout=5,
    )
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current", {})
    daily = payload.get("daily", {})

    forecast = []
    for i, date in enumerate(daily.get("time", [])[:5]):
        forecast.append({
            "date": date,
            "high": daily.get("temperature_2m_max", [None] * 5)[i],
            "low": daily.get("temperature_2m_min", [None] * 5)[i],
            "precip": daily.get("precipitation_probability_max", [None] * 5)[i],
            "code": daily.get("weather_code", [None] * 5)[i],
        })

    return _cache.set({
        "configured": True,
        "location": ", ".join(x for x in (loc.get("name"), loc.get("admin1")) if x),
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind": current.get("wind_speed_10m"),
        "precip": current.get("precipitation"),
        "code": current.get("weather_code"),
        "is_day": current.get("is_day", 1),
        "unit": "°F" if temp_unit == "fahrenheit" else "°C",
        "wind_unit": "mph" if wind_unit == "mph" else "km/h",
        "sunrise": (daily.get("sunrise") or ["--"])[0][-5:],
        "sunset": (daily.get("sunset") or ["--"])[0][-5:],
        "forecast": forecast,
    })


PLUGIN_HTML = r'''
<div class="weather-hero">
  <div class="wx-icon" data-role="icon">◌</div>
  <div class="grow"><span class="eyebrow">LOCAL WEATHER</span><h1 data-role="location">Weather</h1><div class="muted" data-role="condition"></div></div>
  <div class="hero-number" data-role="temp">--°</div>
</div>
<div class="metric-grid weather-metrics">
  <article class="metric"><label>FEELS</label><strong data-role="feels">--</strong></article>
  <article class="metric"><label>HUMIDITY</label><strong data-role="humidity">--</strong></article>
  <article class="metric"><label>WIND</label><strong data-role="wind">--</strong></article>
  <article class="metric"><label>SUNRISE</label><strong data-role="sunrise">--</strong></article>
  <article class="metric"><label>SUNSET</label><strong data-role="sunset">--</strong></article>
</div>
<div class="forecast-grid" data-role="forecast"></div>
'''

PLUGIN_CSS = r'''
.plugin-weather .weather-hero{display:grid;grid-template-columns:auto 1fr auto;gap:var(--gap);align-items:center}
.plugin-weather .wx-icon{width:clamp(64px,9vw,110px);aspect-ratio:1;display:grid;place-items:center;font-size:clamp(2.5rem,6vw,5rem);border:1px solid var(--border);border-radius:var(--radius);background:var(--surface)}
.plugin-weather .hero-number{font-size:clamp(3rem,10vw,7rem);font-weight:900;letter-spacing:-.05em}
.plugin-weather .weather-metrics{grid-template-columns:repeat(5,1fr)}
.plugin-weather .forecast-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:var(--gap);margin-top:var(--gap)}
.plugin-weather .forecast-day{padding:var(--pad);border-top:1px solid var(--border);background:linear-gradient(180deg,rgba(255,255,255,.015),transparent);border-radius:var(--radius-sm)}
.plugin-weather .forecast-day b{display:block;font-size:clamp(.85rem,1.5vw,1.2rem);margin:.2rem 0}
@media(max-width:700px){.plugin-weather .weather-metrics,.plugin-weather .forecast-grid{grid-template-columns:repeat(2,1fr)}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.weather={
  text(code){
    if(code===0)return"Clear"; if([1,2].includes(code))return"Partly cloudy"; if(code===3)return"Overcast";
    if([45,48].includes(code))return"Fog"; if(code>=51&&code<=67)return"Rain"; if(code>=71&&code<=77)return"Snow";
    if(code>=80&&code<=82)return"Showers"; if(code>=95)return"Thunderstorms"; return"Conditions";
  },
  icon(code,day=true){
    if(code===0)return day?"☀️":"🌙"; if([1,2].includes(code))return day?"🌤️":"☁️"; if(code===3)return"☁️";
    if([45,48].includes(code))return"🌫️"; if(code>=51&&code<=67)return"🌧️"; if(code>=71&&code<=77)return"🌨️";
    if(code>=80&&code<=82)return"🌦️"; if(code>=95)return"⛈️"; return"◌";
  },
  render(data,root){
    if(!data.configured){
      root.querySelector('[data-role="location"]').textContent="Weather not configured";
      root.querySelector('[data-role="condition"]').textContent="Set WEATHER_LOCATION in config.env";
      return;
    }
    root.querySelector('[data-role="icon"]').textContent=this.icon(data.code,data.is_day!==0);
    root.querySelector('[data-role="location"]').textContent=data.location;
    root.querySelector('[data-role="condition"]').textContent=this.text(data.code);
    root.querySelector('[data-role="temp"]').textContent=`${Math.round(data.temp)}${data.unit}`;
    root.querySelector('[data-role="feels"]').textContent=`${Math.round(data.feels)}${data.unit}`;
    root.querySelector('[data-role="humidity"]').textContent=`${data.humidity}%`;
    root.querySelector('[data-role="wind"]').textContent=`${Math.round(data.wind)} ${data.wind_unit}`;
    root.querySelector('[data-role="sunrise"]').textContent=data.sunrise;
    root.querySelector('[data-role="sunset"]').textContent=data.sunset;
    root.querySelector('[data-role="forecast"]').innerHTML=(data.forecast||[]).map(d=>`
      <div class="forecast-day"><span>${new Date(d.date+"T12:00:00").toLocaleDateString([],{weekday:"short"})}</span>
      <b>${this.icon(d.code,true)} ${Math.round(d.high)}° / ${Math.round(d.low)}°</b><small>${d.precip??0}% precip</small></div>`).join("");
  }
};
'''
