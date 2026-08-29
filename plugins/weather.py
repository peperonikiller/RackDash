from __future__ import annotations

import math
import os
import time
from datetime import datetime

import requests

from _shared import TTLCache


PLUGIN_ID = "weather"
PLUGIN_NAME = "Weather"
PLUGIN_VERSION = "3.0.1"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/weather.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "custom_routes", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 30
PLUGIN_REFRESH_SECONDS = 300
PLUGIN_ACCENT = "#6fb7ff"
PLUGIN_ICON = "WX"
PLUGIN_PUBLIC_ERROR = "Weather unavailable"

PLUGIN_CONFIG = [
    {
        "key": "WEATHER_LOCATION",
        "label": "City / State / ZIP",
        "type": "text",
        "default": "",
        "required": True,
    },
    {
        "key": "WEATHER_UNITS",
        "label": "Units",
        "type": "select",
        "default": "fahrenheit",
        "options": [
            {"value": "fahrenheit", "label": "Fahrenheit"},
            {"value": "celsius", "label": "Celsius"},
        ],
    },
]

LOCATION = os.getenv("WEATHER_LOCATION", "")
UNITS = os.getenv("WEATHER_UNITS", "fahrenheit").lower()

_geo_cache = TTLCache(21600)
_weather_cache = TTLCache(300)
_radar_cache = TTLCache(300)


PLUGIN_HTML = r"""
<div class="weather-shell">
  <section class="weather-hero surface">
    <div class="wx-current-icon" data-role="animated-icon" aria-label="Current weather"></div>

    <div class="wx-current-copy">
      <span class="eyebrow">LOCAL WEATHER</span>
      <h1 data-role="location">Weather</h1>
      <div class="wx-condition-row">
        <strong data-role="condition">Loading conditions...</strong>
        <span data-role="updated"></span>
      </div>
      <div class="wx-today-summary" data-role="today-summary"></div>
    </div>

    <div class="wx-temperature-block">
      <div class="wx-temperature" data-role="temp">--°</div>
      <div class="wx-feels">Feels like <strong data-role="feels">--°</strong></div>
    </div>
  </section>

  <section class="weather-metrics">
    <article class="surface wx-metric">
      <span>HUMIDITY</span>
      <strong data-role="humidity">--</strong>
      <small data-role="dewpoint">Dew point --</small>
    </article>
    <article class="surface wx-metric">
      <span>WIND</span>
      <strong data-role="wind">--</strong>
      <small data-role="gusts">Gusts --</small>
    </article>
    <article class="surface wx-metric">
      <span>PRESSURE</span>
      <strong data-role="pressure">--</strong>
      <small>sea level</small>
    </article>
    <article class="surface wx-metric">
      <span>VISIBILITY</span>
      <strong data-role="visibility">--</strong>
      <small data-role="clouds">Clouds --</small>
    </article>
    <article class="surface wx-metric">
      <span>UV INDEX</span>
      <strong data-role="uv">--</strong>
      <small data-role="uv-label">--</small>
    </article>
    <article class="surface wx-metric">
      <span>PRECIPITATION</span>
      <strong data-role="precip">--</strong>
      <small data-role="precip-chance">Chance --</small>
    </article>
  </section>

  <section class="weather-main-grid">
    <article class="surface wx-hourly-card">
      <div class="wx-section-head">
        <div>
          <div class="section-label">HOURLY FORECAST</div>
          <div class="muted wx-small">Next 12 hours</div>
        </div>
        <div class="wx-sun-times">
          <span>↑ <b data-role="sunrise">--</b></span>
          <span>↓ <b data-role="sunset">--</b></span>
        </div>
      </div>
      <div class="wx-hourly" data-role="hourly"></div>
    </article>

    <article class="surface wx-radar-card">
      <div class="wx-section-head">
        <div>
          <div class="section-label">LIVE WEATHER RADAR</div>
          <div class="muted wx-small">Animated recent radar</div>
        </div>
        <div class="wx-radar-time" data-role="radar-time">--</div>
      </div>

      <div class="wx-radar-map" data-role="radar-map">
        <div class="wx-map-base" data-role="map-base"></div>
        <img class="wx-radar-overlay" data-role="radar-overlay" alt="Weather radar">
        <div class="wx-map-vignette"></div>
        <div class="wx-map-center" title="Forecast location"></div>
        <div class="wx-radar-unavailable" data-role="radar-unavailable" hidden>Radar unavailable</div>
      </div>

      <div class="wx-radar-footer">
        <span><a class="wx-source-link" data-role="radar-source" href="https://radar.weather.gov/" target="_blank" rel="noopener noreferrer">NOAA / NWS MRMS radar</a> · <a class="wx-source-link" href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a></span>
        <div class="wx-radar-legend">
          <span>Light</span>
          <i></i>
          <span>Heavy</span>
        </div>
      </div>
    </article>
  </section>

  <section class="surface wx-daily-card">
    <div class="wx-section-head">
      <div>
        <div class="section-label">7-DAY FORECAST</div>
        <div class="muted wx-small">High / low · precipitation</div>
      </div>
    </div>
    <div class="wx-daily" data-role="forecast"></div>
  </section>
</div>
"""

PLUGIN_CSS = r"""
.plugin-weather{
  --wx-blue:#6fb7ff;
  --wx-deep:#16293a;
  --wx-rain:#4ca6ff;
  --wx-sun:#ffd15c;
}
.plugin-weather .weather-shell{display:grid;gap:var(--gap)}
.plugin-weather .weather-hero{
  display:grid;
  grid-template-columns:auto minmax(0,1fr) auto;
  align-items:center;
  gap:clamp(.8rem,2vw,1.35rem);
  border-left:3px solid var(--wx-blue);
  background:
    radial-gradient(circle at 12% 25%,rgba(111,183,255,.11),transparent 24%),
    linear-gradient(115deg,rgba(111,183,255,.045),rgba(255,255,255,.008) 48%,rgba(255,255,255,.004));
}
.plugin-weather .wx-current-icon{
  width:clamp(7.5rem,13vw,11rem);
  aspect-ratio:1;
  position:relative;
  overflow:hidden;
  border-radius:1rem;
  border:1px solid rgba(111,183,255,.2);
  background:linear-gradient(160deg,rgba(55,102,142,.28),rgba(10,18,24,.18));
}
.plugin-weather .wx-current-copy{min-width:0}
.plugin-weather .wx-current-copy h1{
  margin:.12rem 0 .15rem;
  font-size:clamp(1.55rem,3vw,2.8rem);
  line-height:1;
}
.plugin-weather .wx-condition-row{display:flex;align-items:center;gap:.55rem;flex-wrap:wrap}
.plugin-weather .wx-condition-row strong{font-size:.68rem;color:#dce8ee}
.plugin-weather .wx-condition-row span{font-size:.47rem;color:var(--muted)}
.plugin-weather .wx-today-summary{
  margin-top:.42rem;
  color:var(--muted);
  font-size:.55rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-weather .wx-temperature-block{text-align:right}
.plugin-weather .wx-temperature{
  font-size:clamp(3.6rem,8vw,7rem);
  font-weight:950;
  letter-spacing:-.075em;
  line-height:.9;
}
.plugin-weather .wx-feels{margin-top:.25rem;color:var(--muted);font-size:.54rem}
.plugin-weather .wx-feels strong{color:#dce8ee}

.plugin-weather .weather-metrics{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:var(--gap);
}
.plugin-weather .wx-metric{min-width:0;border-top:1px solid rgba(111,183,255,.14)}
.plugin-weather .wx-metric span{
  display:block;
  font-size:.45rem;
  color:var(--muted);
  font-weight:850;
  letter-spacing:.05em;
}
.plugin-weather .wx-metric strong{
  display:block;
  margin-top:.1rem;
  font-size:clamp(.9rem,1.7vw,1.35rem);
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-weather .wx-metric small{
  display:block;
  margin-top:.09rem;
  color:var(--muted);
  font-size:.44rem;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}

.plugin-weather .weather-main-grid{
  display:grid;
  grid-template-columns:minmax(0,1.15fr) minmax(320px,.85fr);
  gap:var(--gap);
  align-items:stretch;
}
.plugin-weather .wx-section-head{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:.7rem;
}
.plugin-weather .wx-small{font-size:.46rem}
.plugin-weather .wx-sun-times{
  display:flex;
  gap:.7rem;
  color:var(--muted);
  font-size:.48rem;
}
.plugin-weather .wx-sun-times b{color:#dce8ee}

.plugin-weather .wx-hourly{
  display:grid;
  grid-template-columns:repeat(6,minmax(0,1fr));
  gap:.36rem;
  margin-top:.65rem;
}
.plugin-weather .wx-hour{
  padding:.48rem .3rem;
  border:1px solid var(--border);
  border-radius:.45rem;
  background:rgba(255,255,255,.012);
  text-align:center;
  min-width:0;
}
.plugin-weather .wx-hour.current{
  border-color:rgba(111,183,255,.42);
  background:rgba(111,183,255,.055);
}
.plugin-weather .wx-hour-time{font-size:.46rem;color:var(--muted);font-weight:800}
.plugin-weather .wx-hour-icon{font-size:1.25rem;line-height:1.1;margin:.28rem 0}
.plugin-weather .wx-hour-temp{font-size:.75rem;font-weight:900}
.plugin-weather .wx-hour-rain{margin-top:.16rem;font-size:.43rem;color:#7bc3ff}

.plugin-weather .wx-radar-card{overflow:hidden}
.plugin-weather .wx-radar-time{
  padding:.2rem .36rem;
  border:1px solid var(--border);
  border-radius:.3rem;
  color:#dce8ee;
  font-size:.46rem;
  font-variant-numeric:tabular-nums;
}
.plugin-weather .wx-radar-map{
  position:relative;
  height:18rem;
  margin-top:.55rem;
  overflow:hidden;
  border-radius:.55rem;
  background:linear-gradient(180deg,#0b1117,#0d151c);
  border:1px solid rgba(111,183,255,.16);
}
.plugin-weather .wx-map-base,
.plugin-weather .wx-radar-overlay,
.plugin-weather .wx-map-vignette{
  position:absolute;
  inset:0;
  width:100%;
  height:100%;
}
.plugin-weather .wx-map-base{overflow:hidden}
.plugin-weather .wx-map-tile{
  position:absolute;
  width:256px;
  height:256px;
  object-fit:cover;
  user-select:none;
  pointer-events:none;
  filter:grayscale(.35) brightness(.42) contrast(1.15) saturate(.7);
}
.plugin-weather .wx-radar-overlay{
  object-fit:fill;
  opacity:.86;
  z-index:2;
  transition:opacity .15s linear;
  mix-blend-mode:screen;
  filter:saturate(1.35) contrast(1.12) brightness(.96);
}
.plugin-weather .wx-map-vignette{
  z-index:3;
  pointer-events:none;
  background:linear-gradient(180deg,rgba(8,14,19,.10),rgba(8,14,19,.22));
  box-shadow:inset 0 0 58px rgba(0,0,0,.48);
}
.plugin-weather .wx-map-center{
  position:absolute;
  left:50%;
  top:50%;
  width:.55rem;
  height:.55rem;
  transform:translate(-50%,-50%);
  border-radius:50%;
  z-index:4;
  background:#fff;
  border:2px solid #1d79c8;
  box-shadow:0 0 0 3px rgba(29,121,200,.35),0 0 14px rgba(255,255,255,.55);
}
.plugin-weather .wx-radar-unavailable{
  position:absolute;
  inset:0;
  z-index:5;
  display:grid;
  place-items:center;
  color:var(--muted);
  font-size:.55rem;
  background:rgba(12,18,22,.74);
}
.plugin-weather .wx-radar-unavailable[hidden]{
  display:none!important;
}
.plugin-weather .wx-radar-footer{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:.6rem;
  margin-top:.38rem;
  color:var(--muted);
  font-size:.43rem;
}
.plugin-weather .wx-source-link{color:var(--muted);text-decoration:none}
.plugin-weather .wx-source-link:hover{color:#dce8ee}
.plugin-weather .wx-radar-legend{display:flex;align-items:center;gap:.3rem}
.plugin-weather .wx-radar-legend i{
  display:block;
  width:5rem;
  height:.28rem;
  border-radius:1rem;
  background:linear-gradient(90deg,#2d8cff,#31d9b7,#f7dc52,#ff8d38,#e94255);
}

.plugin-weather .wx-daily{
  display:grid;
  grid-template-columns:repeat(7,minmax(0,1fr));
  gap:.42rem;
  margin-top:.55rem;
}
.plugin-weather .wx-day{
  padding:.55rem .42rem;
  border:1px solid var(--border);
  border-radius:.45rem;
  background:linear-gradient(180deg,rgba(111,183,255,.025),rgba(255,255,255,.006));
  min-width:0;
  text-align:center;
}
.plugin-weather .wx-day-name{font-size:.48rem;color:var(--muted);font-weight:850}
.plugin-weather .wx-day-icon{font-size:1.45rem;margin:.24rem 0}
.plugin-weather .wx-day-temp{font-size:.68rem;font-weight:900}
.plugin-weather .wx-day-temp span{color:var(--muted);font-weight:700}
.plugin-weather .wx-day-rain{font-size:.42rem;color:#7bc3ff;margin-top:.16rem}

/* Animated current-condition artwork */
.plugin-weather .wx-scene{position:absolute;inset:0}
.plugin-weather .wx-sun{
  position:absolute;
  width:38%;
  aspect-ratio:1;
  border-radius:50%;
  background:#ffd15c;
  left:16%;
  top:14%;
  box-shadow:0 0 28px rgba(255,209,92,.45);
  animation:wxPulse 3.2s ease-in-out infinite;
}
.plugin-weather .wx-sun::before,
.plugin-weather .wx-sun::after{
  content:"";
  position:absolute;
  inset:-35%;
  border-radius:50%;
  border:2px dashed rgba(255,209,92,.55);
  animation:wxSpin 12s linear infinite;
}
.plugin-weather .wx-sun::after{inset:-58%;opacity:.4;animation-duration:18s;animation-direction:reverse}
.plugin-weather .wx-moon{
  position:absolute;
  width:42%;
  aspect-ratio:1;
  border-radius:50%;
  background:#dbe8f5;
  left:19%;
  top:12%;
  box-shadow:0 0 25px rgba(193,219,245,.26);
}
.plugin-weather .wx-moon::after{
  content:"";
  position:absolute;
  width:78%;
  height:78%;
  left:29%;
  top:-8%;
  border-radius:50%;
  background:#223444;
}
.plugin-weather .wx-cloud{
  position:absolute;
  width:55%;
  height:22%;
  left:30%;
  top:46%;
  border-radius:3rem;
  background:#e6edf2;
  filter:drop-shadow(0 5px 6px rgba(0,0,0,.22));
  animation:wxDrift 4.8s ease-in-out infinite;
}
.plugin-weather .wx-cloud::before,
.plugin-weather .wx-cloud::after{
  content:"";
  position:absolute;
  border-radius:50%;
  background:inherit;
}
.plugin-weather .wx-cloud::before{width:43%;aspect-ratio:1;left:12%;bottom:22%}
.plugin-weather .wx-cloud::after{width:55%;aspect-ratio:1;right:10%;bottom:12%}
.plugin-weather .wx-cloud.dark{background:#8ea1af}
.plugin-weather .wx-rain-drop{
  position:absolute;
  width:3px;
  height:13%;
  top:67%;
  border-radius:1rem;
  background:#67b9ff;
  animation:wxRain 1s linear infinite;
}
.plugin-weather .wx-snowflake{
  position:absolute;
  top:67%;
  color:#e7f6ff;
  font-size:.78rem;
  animation:wxSnow 2.4s linear infinite;
}
.plugin-weather .wx-fog-line{
  position:absolute;
  left:14%;
  width:72%;
  height:3px;
  border-radius:1rem;
  background:rgba(220,232,238,.65);
  animation:wxFog 3.4s ease-in-out infinite;
}
.plugin-weather .wx-lightning{
  position:absolute;
  left:49%;
  top:60%;
  color:#ffd95e;
  font-size:2.2rem;
  z-index:5;
  animation:wxFlash 2.8s infinite;
}
@keyframes wxPulse{50%{transform:scale(1.06);box-shadow:0 0 38px rgba(255,209,92,.55)}}
@keyframes wxSpin{to{transform:rotate(360deg)}}
@keyframes wxDrift{50%{transform:translateX(5%)}}
@keyframes wxRain{0%{transform:translateY(-3px);opacity:0}20%{opacity:1}100%{transform:translateY(27px);opacity:0}}
@keyframes wxSnow{0%{transform:translate(0,-3px) rotate(0);opacity:0}20%{opacity:1}100%{transform:translate(12px,27px) rotate(180deg);opacity:0}}
@keyframes wxFog{50%{transform:translateX(7%);opacity:.45}}
@keyframes wxFlash{0%,88%,100%{opacity:0}90%,94%{opacity:1}92%,96%{opacity:.15}}

@media(prefers-reduced-motion:reduce){
  .plugin-weather .wx-sun,
  .plugin-weather .wx-sun::before,
  .plugin-weather .wx-sun::after,
  .plugin-weather .wx-cloud,
  .plugin-weather .wx-rain-drop,
  .plugin-weather .wx-snowflake,
  .plugin-weather .wx-fog-line,
  .plugin-weather .wx-lightning{animation:none!important}
  .plugin-weather .wx-radar-overlay{transition:none}
}
@media(max-width:1100px){
  .plugin-weather .weather-metrics{grid-template-columns:repeat(3,minmax(0,1fr))}
  .plugin-weather .weather-main-grid{grid-template-columns:1fr}
}
@media(max-width:760px){
  .plugin-weather .weather-hero{grid-template-columns:auto minmax(0,1fr)}
  .plugin-weather .wx-temperature-block{grid-column:1/-1;text-align:left}
  .plugin-weather .weather-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}
  .plugin-weather .wx-hourly{grid-template-columns:repeat(4,minmax(0,1fr))}
  .plugin-weather .wx-daily{grid-template-columns:repeat(2,minmax(0,1fr))}
}
"""

PLUGIN_JS = r"""
window.RackDashPlugins.weather={
  radarTimer:null,
  radarFrame:0,
  radarSignature:"",
  radarData:null,

  text(code){
    if(code===0)return "Clear";
    if([1,2].includes(code))return "Partly cloudy";
    if(code===3)return "Overcast";
    if([45,48].includes(code))return "Fog";
    if(code>=51&&code<=57)return "Drizzle";
    if(code>=61&&code<=67)return "Rain";
    if(code>=71&&code<=77)return "Snow";
    if(code>=80&&code<=82)return "Rain showers";
    if(code>=85&&code<=86)return "Snow showers";
    if(code>=95)return "Thunderstorms";
    return "Conditions";
  },

  icon(code,day=true){
    if(code===0)return day?"☀️":"🌙";
    if([1,2].includes(code))return day?"🌤️":"☁️";
    if(code===3)return "☁️";
    if([45,48].includes(code))return "🌫️";
    if(code>=51&&code<=67)return "🌧️";
    if(code>=71&&code<=77)return "🌨️";
    if(code>=80&&code<=82)return "🌦️";
    if(code>=85&&code<=86)return "🌨️";
    if(code>=95)return "⛈️";
    return "◌";
  },

  animatedIcon(code,day=true){
    const sun=day
      ?`<div class="wx-sun"></div>`
      :`<div class="wx-moon"></div>`;

    const cloud=(dark=false)=>`<div class="wx-cloud ${dark?"dark":""}"></div>`;

    const rain=()=>[24,39,54,69].map((left,i)=>
      `<i class="wx-rain-drop" style="left:${left}%;animation-delay:${i*.18}s"></i>`
    ).join("");

    const snow=()=>[24,40,56,71].map((left,i)=>
      `<i class="wx-snowflake" style="left:${left}%;animation-delay:${i*.38}s">✦</i>`
    ).join("");

    if(code===0)return `<div class="wx-scene">${sun}</div>`;

    if([1,2].includes(code)){
      return `<div class="wx-scene">${sun}${cloud(false)}</div>`;
    }

    if(code===3){
      return `<div class="wx-scene">${cloud(true)}<div class="wx-cloud" style="left:8%;top:28%;transform:scale(.72)"></div></div>`;
    }

    if([45,48].includes(code)){
      return `<div class="wx-scene">${cloud(true)}
        <i class="wx-fog-line" style="top:70%"></i>
        <i class="wx-fog-line" style="top:80%;animation-delay:.7s"></i>
        <i class="wx-fog-line" style="top:90%;animation-delay:1.2s"></i>
      </div>`;
    }

    if((code>=51&&code<=67)||(code>=80&&code<=82)){
      return `<div class="wx-scene">${cloud(true)}${rain()}</div>`;
    }

    if((code>=71&&code<=77)||(code>=85&&code<=86)){
      return `<div class="wx-scene">${cloud(true)}${snow()}</div>`;
    }

    if(code>=95){
      return `<div class="wx-scene">${cloud(true)}${rain()}<div class="wx-lightning">ϟ</div></div>`;
    }

    return `<div class="wx-scene">${sun}</div>`;
  },

  uvLabel(value){
    const uv=Number(value||0);
    if(uv<3)return "Low";
    if(uv<6)return "Moderate";
    if(uv<8)return "High";
    if(uv<11)return "Very high";
    return "Extreme";
  },

  windDirection(deg){
    const dirs=["N","NE","E","SE","S","SW","W","NW"];
    return dirs[Math.round(Number(deg||0)/45)%8];
  },

  formatTime(value){
    if(!value)return "--";
    const d=new Date(value);
    return d.toLocaleTimeString([],{hour:"numeric",minute:"2-digit"});
  },

  tilePosition(lat,lon,zoom){
    const n=2**zoom;
    const x=(lon+180)/360*n;
    const latRad=lat*Math.PI/180;
    const y=(1-Math.asinh(Math.tan(latRad))/Math.PI)/2*n;
    return {x,y};
  },

  renderBaseMap(root,lat,lon,zoom=7){
    const host=root.querySelector('[data-role="map-base"]');
    if(!host)return;

    const map=root.querySelector('[data-role="radar-map"]');
    const width=map.clientWidth||600;
    const height=map.clientHeight||288;
    const center=this.tilePosition(lat,lon,zoom);
    const tileSize=256;
    const centerPixelX=center.x*tileSize;
    const centerPixelY=center.y*tileSize;
    const startX=Math.floor((centerPixelX-width/2)/tileSize);
    const endX=Math.floor((centerPixelX+width/2)/tileSize);
    const startY=Math.floor((centerPixelY-height/2)/tileSize);
    const endY=Math.floor((centerPixelY+height/2)/tileSize);
    const n=2**zoom;
    const parts=[];

    for(let y=startY;y<=endY;y++){
      if(y<0||y>=n)continue;
      for(let x=startX;x<=endX;x++){
        const wrapped=((x%n)+n)%n;
        const left=x*tileSize-(centerPixelX-width/2);
        const top=y*tileSize-(centerPixelY-height/2);
        parts.push(
          `<img class="wx-map-tile" src="https://tile.openstreetmap.org/${zoom}/${wrapped}/${y}.png" style="left:${left}px;top:${top}px" alt="">`
        );
      }
    }

    host.innerHTML=parts.join("");
  },

  radarUrl(minutesAgo){
    return `/api/plugin/weather/radar?minutes_ago=${encodeURIComponent(minutesAgo)}`;
  },

  startRadar(data,root){
    if(this.radarTimer){
      clearInterval(this.radarTimer);
      this.radarTimer=null;
    }

    const overlay=root.querySelector('[data-role="radar-overlay"]');
    const unavailable=root.querySelector('[data-role="radar-unavailable"]');
    const timeNode=root.querySelector('[data-role="radar-time"]');

    this.renderBaseMap(root,Number(data.latitude),Number(data.longitude),7);

    if(!overlay){
      if(unavailable)unavailable.hidden=false;
      return;
    }

    // NOAA's MRMS imagery service keeps a rolling multi-hour time window.
    // We animate the most recent hour, offset slightly so each requested
    // timestamp has had time to arrive in the service.
    const frames=[60,55,50,45,40,35,30,25,20,15,10,5];
    this.radarFrame=this.radarFrame%frames.length;

    const draw=()=>{
      const minutesAgo=frames[this.radarFrame];
      const next=new Image();

      overlay.style.opacity=".25";

      next.onload=()=>{
        overlay.src=next.src;
        overlay.style.opacity=".82";
        if(unavailable)unavailable.hidden=true;
      };

      next.onerror=()=>{
        overlay.style.opacity=".82";
        if(unavailable)unavailable.hidden=false;
      };

      // Cache-bust only per animation frame index; the backend itself caches
      // NOAA responses briefly so multiple browsers do not hammer NWS.
      next.src=`${this.radarUrl(minutesAgo)}&frame=${this.radarFrame}`;

      if(timeNode){
        const d=new Date(Date.now()-minutesAgo*60*1000);
        timeNode.textContent=d.toLocaleTimeString([],{hour:"numeric",minute:"2-digit"});
      }

      this.radarFrame=(this.radarFrame+1)%frames.length;
    };

    draw();
    this.radarTimer=setInterval(draw,1100);
  },

  hourly(rows,data){
    if(!rows?.length)return `<div class="wx-empty">Hourly forecast unavailable.</div>`;

    return rows.slice(0,12).map((h,index)=>`
      <div class="wx-hour ${index===0?"current":""}">
        <div class="wx-hour-time">${index===0?"NOW":this.formatTime(h.time)}</div>
        <div class="wx-hour-icon">${this.icon(h.code,h.is_day!==0)}</div>
        <div class="wx-hour-temp">${Math.round(h.temp)}°</div>
        <div class="wx-hour-rain">${Math.round(h.precip_probability||0)}%</div>
      </div>
    `).join("");
  },

  daily(rows){
    if(!rows?.length)return "";

    return rows.slice(0,7).map((d,index)=>`
      <div class="wx-day">
        <div class="wx-day-name">${
          index===0
            ?"TODAY"
            :new Date(d.date+"T12:00:00").toLocaleDateString([],{weekday:"short"}).toUpperCase()
        }</div>
        <div class="wx-day-icon">${this.icon(d.code,true)}</div>
        <div class="wx-day-temp">${Math.round(d.high)}° <span>${Math.round(d.low)}°</span></div>
        <div class="wx-day-rain">${Math.round(d.precip||0)}% precip</div>
      </div>
    `).join("");
  },

  render(data,root){
    this.radarData=data;
    if(!data.configured){
      root.querySelector('[data-role="location"]').textContent="Weather not configured";
      root.querySelector('[data-role="condition"]').textContent="Set WEATHER_LOCATION in Admin";
      return;
    }

    root.querySelector('[data-role="animated-icon"]').innerHTML=
      this.animatedIcon(data.code,data.is_day!==0);

    root.querySelector('[data-role="location"]').textContent=data.location;
    root.querySelector('[data-role="condition"]').textContent=this.text(data.code);
    root.querySelector('[data-role="updated"]').textContent=data.current_time?`Updated ${this.formatTime(data.current_time)}`:"";

    root.querySelector('[data-role="temp"]').textContent=`${Math.round(data.temp)}${data.unit}`;
    root.querySelector('[data-role="feels"]').textContent=`${Math.round(data.feels)}${data.unit}`;
    root.querySelector('[data-role="humidity"]').textContent=`${Math.round(data.humidity||0)}%`;
    root.querySelector('[data-role="dewpoint"]').textContent=`Dew point ${Math.round(data.dewpoint)}${data.unit}`;

    const dir=this.windDirection(data.wind_direction);
    root.querySelector('[data-role="wind"]').textContent=`${Math.round(data.wind)} ${data.wind_unit} ${dir}`;
    root.querySelector('[data-role="gusts"]').textContent=`Gusts ${Math.round(data.gusts||0)} ${data.wind_unit}`;

    root.querySelector('[data-role="pressure"]').textContent=`${Math.round(data.pressure||0)} hPa`;
    root.querySelector('[data-role="visibility"]').textContent=`${Number(data.visibility||0).toFixed(1)} ${data.distance_unit}`;
    root.querySelector('[data-role="clouds"]').textContent=`Cloud cover ${Math.round(data.cloud_cover||0)}%`;
    root.querySelector('[data-role="uv"]').textContent=Number(data.uv||0).toFixed(1);
    root.querySelector('[data-role="uv-label"]').textContent=this.uvLabel(data.uv);
    root.querySelector('[data-role="precip"]').textContent=`${Number(data.precip||0).toFixed(2)} ${data.precip_unit}`;
    root.querySelector('[data-role="precip-chance"]').textContent=`Chance ${Math.round(data.current_precip_probability||0)}%`;

    root.querySelector('[data-role="sunrise"]').textContent=this.formatTime(data.sunrise);
    root.querySelector('[data-role="sunset"]').textContent=this.formatTime(data.sunset);

    root.querySelector('[data-role="today-summary"]').textContent=
      `High ${Math.round(data.today_high)}° · Low ${Math.round(data.today_low)}° · ${Math.round(data.today_precip||0)}% chance of precipitation`;

    root.querySelector('[data-role="hourly"]').innerHTML=this.hourly(data.hourly||[],data);
    root.querySelector('[data-role="forecast"]').innerHTML=this.daily(data.forecast||[]);
    this.startRadar(data,root);
  },

  onResize(root){
    if(this.radarData){
      this.renderBaseMap(root,Number(this.radarData.latitude),Number(this.radarData.longitude),7);
    }
  },

  onHide(){
    if(this.radarTimer){
      clearInterval(this.radarTimer);
      this.radarTimer=null;
    }
  },

  onShow(root){
    if(this.radarData)this.startRadar(this.radarData,root);
  }
};
"""


def _geocode():
    cached = _geo_cache.get()
    if cached is not None:
        return dict(cached)

    if not LOCATION:
        return None

    response = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": LOCATION,
            "count": 1,
            "language": "en",
            "format": "json",
        },
        timeout=5,
    )
    response.raise_for_status()

    results = response.json().get("results") or []
    if not results:
        raise RuntimeError("Location not found")

    loc = results[0]
    result = {
        "name": ", ".join(
            value
            for value in (
                loc.get("name"),
                loc.get("admin1"),
            )
            if value
        ),
        "latitude": float(loc["latitude"]),
        "longitude": float(loc["longitude"]),
        "timezone": loc.get("timezone") or "auto",
    }

    _geo_cache.set(result)
    return dict(result)


NOAA_RADAR_URL = (
    "https://mapservices.weather.noaa.gov/eventdriven/rest/services/"
    "radar/radar_base_reflectivity_time/ImageServer/exportImage"
)

_radar_image_cache = {}


def _radar():
    # The browser no longer depends on third-party metadata endpoints.
    # NOAA radar frames are proxied through RackDash itself.
    return {
        "provider": "NOAA / NWS MRMS",
        "available": True,
    }


def _radar_bbox(latitude, longitude):
    """
    Return a local geographic window centered on the configured forecast
    location. Roughly a few hundred miles wide at mid-latitudes.
    """
    lat = float(latitude)
    lon = float(longitude)

    lat_span = 3.1
    cos_lat = max(0.35, math.cos(math.radians(lat)))
    lon_span = min(5.5, lat_span / cos_lat)

    return (
        lon - lon_span,
        lat - lat_span,
        lon + lon_span,
        lat + lat_span,
    )


def _radar_frame(latitude, longitude, minutes_ago):
    """
    Fetch one NOAA MRMS base-reflectivity image.

    NOAA's official ImageServer is time-enabled and maintains a rolling
    multi-hour window. Requests are made server-side so Chromium never needs
    direct access to NOAA and browser CORS/content-policy differences cannot
    break the radar panel.
    """
    try:
        minutes_ago = max(5, min(180, int(minutes_ago)))
    except (TypeError, ValueError):
        minutes_ago = 10

    # NOAA updates approximately every 5 minutes. Round to a five-minute UTC
    # boundary and keep a five-minute ingestion offset.
    now_ms = int(time.time() * 1000)
    step_ms = 5 * 60 * 1000
    requested_ms = now_ms - ((minutes_ago + 5) * 60 * 1000)
    requested_ms = (requested_ms // step_ms) * step_ms

    cache_key = (
        round(float(latitude), 3),
        round(float(longitude), 3),
        requested_ms,
    )

    cached = _radar_image_cache.get(cache_key)
    if cached:
        created_at, content, content_type = cached
        if time.time() - created_at < 600:
            return content, content_type, requested_ms

    west, south, east, north = _radar_bbox(
        latitude,
        longitude,
    )

    response = requests.get(
        NOAA_RADAR_URL,
        params={
            "bbox": f"{west:.5f},{south:.5f},{east:.5f},{north:.5f}",
            "bboxSR": "4326",
            "size": "900,520",
            "imageSR": "4326",
            "format": "png32",
            "transparent": "true",
            "time": str(requested_ms),
            "interpolation": "RSP_BilinearInterpolation",
            "f": "image",
        },
        timeout=12,
        headers={
            "User-Agent": "RackDash-Weather/3.0.1",
            "Accept": "image/png,image/*;q=0.8,*/*;q=0.2",
        },
    )
    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type",
        "image/png",
    )

    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"NOAA radar returned {content_type}"
        )

    if not response.content:
        raise RuntimeError("NOAA radar returned an empty image")

    # Keep the small in-memory cache bounded.
    if len(_radar_image_cache) > 48:
        oldest = sorted(
            _radar_image_cache.items(),
            key=lambda item: item[1][0],
        )[:16]
        for key, _ in oldest:
            _radar_image_cache.pop(key, None)

    _radar_image_cache[cache_key] = (
        time.time(),
        response.content,
        content_type,
    )

    return response.content, content_type, requested_ms


def _safe_index(values, index, default=None):
    try:
        return values[index]
    except (IndexError, TypeError):
        return default


def _visibility(value, imperial):
    try:
        meters = float(value or 0)
    except (TypeError, ValueError):
        meters = 0

    return round(
        meters / 1609.344 if imperial else meters / 1000,
        1,
    )


def _weather(loc):
    temp_unit = (
        "fahrenheit"
        if UNITS.startswith("f")
        else "celsius"
    )
    imperial = temp_unit == "fahrenheit"
    wind_unit = "mph" if imperial else "kmh"
    precip_unit = "inch" if imperial else "mm"

    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": loc["latitude"],
            "longitude": loc["longitude"],
            "current": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "dew_point_2m",
                "weather_code",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "is_day",
                "precipitation",
                "cloud_cover",
                "pressure_msl",
                "visibility",
            ]),
            "hourly": ",".join([
                "temperature_2m",
                "apparent_temperature",
                "precipitation_probability",
                "precipitation",
                "weather_code",
                "is_day",
                "wind_speed_10m",
                "wind_gusts_10m",
            ]),
            "daily": ",".join([
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
                "sunrise",
                "sunset",
                "uv_index_max",
                "wind_speed_10m_max",
                "wind_gusts_10m_max",
            ]),
            "temperature_unit": temp_unit,
            "wind_speed_unit": wind_unit,
            "precipitation_unit": precip_unit,
            "timezone": "auto",
            "forecast_days": 7,
        },
        timeout=7,
    )
    response.raise_for_status()

    payload = response.json()
    current = payload.get("current") or {}
    hourly = payload.get("hourly") or {}
    daily = payload.get("daily") or {}

    hourly_times = hourly.get("time") or []
    current_time = str(current.get("time") or "")

    start_index = 0
    if current_time and hourly_times:
        current_hour = current_time[:13]
        for idx, item in enumerate(hourly_times):
            if str(item)[:13] >= current_hour:
                start_index = idx
                break

    hourly_rows = []

    for idx in range(
        start_index,
        min(start_index + 12, len(hourly_times)),
    ):
        hourly_rows.append({
            "time": _safe_index(hourly_times, idx, ""),
            "temp": _safe_index(
                hourly.get("temperature_2m"),
                idx,
                0,
            ),
            "feels": _safe_index(
                hourly.get("apparent_temperature"),
                idx,
                0,
            ),
            "precip_probability": _safe_index(
                hourly.get("precipitation_probability"),
                idx,
                0,
            ),
            "precip": _safe_index(
                hourly.get("precipitation"),
                idx,
                0,
            ),
            "code": _safe_index(
                hourly.get("weather_code"),
                idx,
                0,
            ),
            "is_day": _safe_index(
                hourly.get("is_day"),
                idx,
                1,
            ),
            "wind": _safe_index(
                hourly.get("wind_speed_10m"),
                idx,
                0,
            ),
            "gusts": _safe_index(
                hourly.get("wind_gusts_10m"),
                idx,
                0,
            ),
        })

    forecast = []
    daily_times = daily.get("time") or []

    for idx, date in enumerate(daily_times[:7]):
        forecast.append({
            "date": date,
            "high": _safe_index(
                daily.get("temperature_2m_max"),
                idx,
                0,
            ),
            "low": _safe_index(
                daily.get("temperature_2m_min"),
                idx,
                0,
            ),
            "precip": _safe_index(
                daily.get("precipitation_probability_max"),
                idx,
                0,
            ),
            "code": _safe_index(
                daily.get("weather_code"),
                idx,
                0,
            ),
        })

    current_precip_probability = (
        hourly_rows[0].get("precip_probability", 0)
        if hourly_rows
        else 0
    )

    return {
        "location": loc["name"],
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "timezone": payload.get("timezone") or loc.get("timezone"),
        "current_time": current_time,
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "dewpoint": current.get("dew_point_2m"),
        "wind": current.get("wind_speed_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "gusts": current.get("wind_gusts_10m"),
        "precip": current.get("precipitation"),
        "cloud_cover": current.get("cloud_cover"),
        "pressure": current.get("pressure_msl"),
        "visibility": _visibility(
            current.get("visibility"),
            imperial,
        ),
        "code": current.get("weather_code"),
        "is_day": current.get("is_day", 1),
        "unit": "°F" if imperial else "°C",
        "wind_unit": "mph" if imperial else "km/h",
        "distance_unit": "mi" if imperial else "km",
        "precip_unit": "in" if imperial else "mm",
        "sunrise": _safe_index(
            daily.get("sunrise"),
            0,
            "",
        ),
        "sunset": _safe_index(
            daily.get("sunset"),
            0,
            "",
        ),
        "uv": _safe_index(
            daily.get("uv_index_max"),
            0,
            0,
        ),
        "today_high": _safe_index(
            daily.get("temperature_2m_max"),
            0,
            0,
        ),
        "today_low": _safe_index(
            daily.get("temperature_2m_min"),
            0,
            0,
        ),
        "today_precip": _safe_index(
            daily.get("precipitation_probability_max"),
            0,
            0,
        ),
        "current_precip_probability": current_precip_probability,
        "hourly": hourly_rows,
        "forecast": forecast,
    }


def get_data():
    cached = _weather_cache.get()
    if cached is not None:
        return dict(cached)

    if not LOCATION:
        return {"configured": False}

    loc = _geocode()
    if not loc:
        return {"configured": False}

    data = {
        "configured": True,
    }
    data.update(_weather(loc))
    data["radar"] = _radar()

    _weather_cache.set(data)
    return dict(data)



def register_routes(app):
    @app.get("/api/plugin/weather/radar")
    def weather_radar():
        from flask import request

        if not LOCATION:
            return app.response_class(status=404)

        try:
            loc = _geocode()
            if not loc:
                return app.response_class(status=404)

            content, content_type, timestamp_ms = _radar_frame(
                loc["latitude"],
                loc["longitude"],
                request.args.get("minutes_ago", "10"),
            )

            response = app.response_class(
                content,
                content_type=content_type,
            )
            response.headers["Cache-Control"] = (
                "public, max-age=180"
            )
            response.headers["X-RackDash-Radar-Provider"] = (
                "NOAA-NWS-MRMS"
            )
            response.headers["X-RackDash-Radar-Time"] = str(
                timestamp_ms
            )
            return response

        except Exception:
            app.logger.exception(
                "Weather radar frame failed"
            )
            return app.response_class(status=502)

def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "Weather",
            "lines": ["Forecast unavailable"],
        }

    if not data.get("configured"):
        return {
            "title": "Weather",
            "lines": ["Not configured"],
        }

    return {
        "title": "Weather",
        "lines": [
            (
                f"{round(float(data.get('temp') or 0))}"
                f"{data.get('unit', '')} "
                f"{_condition_text(data.get('code'))}"
            ),
            (
                f"Feels {round(float(data.get('feels') or 0))}"
                f"{data.get('unit', '')}  "
                f"RH {round(float(data.get('humidity') or 0))}%"
            ),
            (
                f"Wind {round(float(data.get('wind') or 0))} "
                f"{data.get('wind_unit', '')}"
            ),
        ],
    }


def _condition_text(code):
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "Weather"

    if code == 0:
        return "Clear"
    if code in (1, 2):
        return "Partly Cloudy"
    if code == 3:
        return "Overcast"
    if code in (45, 48):
        return "Fog"
    if 51 <= code <= 57:
        return "Drizzle"
    if 61 <= code <= 67:
        return "Rain"
    if 71 <= code <= 77:
        return "Snow"
    if 80 <= code <= 82:
        return "Showers"
    if 85 <= code <= 86:
        return "Snow Showers"
    if code >= 95:
        return "Storms"
    return "Weather"
