from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from _shared import TTLCache


PLUGIN_ID = "twitch"
PLUGIN_NAME = "Twitch"
PLUGIN_VERSION = "3.1.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/twitch.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 70
PLUGIN_REFRESH_SECONDS = 60
PLUGIN_ACCENT = "#9146ff"
PLUGIN_ICON = "TW"
PLUGIN_PUBLIC_ERROR = "Twitch data unavailable"

PLUGIN_CONFIG = [
    {
        "key": "TWITCH_CHANNELS",
        "label": "Channels",
        "type": "text",
        "default": "",
        "required": True,
        "placeholder": "channelone, channeltwo, channelthree",
        "help": "Twitch channel names separated by commas. Up to 100 channels.",
    },
    {
        "key": "TWITCH_CLIENT_ID",
        "label": "Twitch Client ID",
        "type": "text",
        "default": "",
        "required": True,
        "help": "Create an application in the Twitch Developer Console.",
    },
    {
        "key": "TWITCH_CLIENT_SECRET",
        "label": "Twitch Client Secret",
        "type": "secret",
        "default": "",
        "required": True,
        "help": "Stored in config.env and masked in the RackDash Admin page.",
    },
]

PLUGIN_HTML = r'''
<div class="twitch-shell">
  <section class="twitch-hero surface">
    <div class="twitch-hero-copy">
      <div class="eyebrow">TWITCH COMMAND CENTER</div>
      <h1 data-role="headline">Checking channels...</h1>
      <div class="muted" data-role="subhead">Loading channel activity</div>
    </div>

    <div class="twitch-summary-metrics">
      <div class="twitch-summary-metric live">
        <span>LIVE</span>
        <strong data-role="live-count">--</strong>
      </div>
      <div class="twitch-summary-metric">
        <span>VIEWERS</span>
        <strong data-role="viewer-total">--</strong>
      </div>
      <div class="twitch-summary-metric">
        <span>CHANNELS</span>
        <strong data-role="channel-count">--</strong>
      </div>
    </div>
  </section>

  <section class="twitch-live-section" data-role="live-section">
    <div class="twitch-section-head">
      <div>
        <div class="section-label">LIVE NOW</div>
        <div class="muted">Current streams across your configured channels</div>
      </div>
      <div class="twitch-live-pill" data-role="live-pill">0 LIVE</div>
    </div>
    <div class="twitch-live-grid" data-role="live-grid"></div>
  </section>

  <section class="twitch-offline-section" data-role="offline-section">
    <div class="twitch-section-head">
      <div>
        <div class="section-label">OFFLINE CHANNELS</div>
        <div class="muted">Latest broadcast and current channel information</div>
      </div>
    </div>
    <div class="twitch-offline-grid" data-role="offline-grid"></div>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-twitch{
  --tw:#9146ff;
  --tw-soft:rgba(145,70,255,.10);
  --tw-line:rgba(145,70,255,.35);
  --tw-live:#ff3b57;
}

.plugin-twitch .twitch-shell{
  min-height:100%;
  display:grid;
  gap:var(--gap);
  align-content:start;
}

.plugin-twitch .twitch-hero{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:1rem;
  min-height:7rem;
  padding:1rem 1.15rem;
  border-left:3px solid var(--tw);
  background:
    radial-gradient(circle at 12% 15%,rgba(145,70,255,.12),transparent 30%),
    linear-gradient(120deg,rgba(145,70,255,.035),rgba(255,255,255,.006));
}

.plugin-twitch .twitch-hero-copy{min-width:0}
.plugin-twitch .twitch-hero h1{
  margin:.12rem 0 .15rem;
  font-size:clamp(1.45rem,3vw,2.7rem);
  line-height:1;
}

.plugin-twitch .twitch-summary-metrics{
  display:grid;
  grid-template-columns:repeat(3,minmax(5.3rem,1fr));
  gap:.45rem;
}

.plugin-twitch .twitch-summary-metric{
  min-width:5.3rem;
  padding:.55rem .65rem;
  border:1px solid var(--border);
  border-radius:.52rem;
  text-align:right;
  background:rgba(255,255,255,.012);
}
.plugin-twitch .twitch-summary-metric span{
  display:block;
  font-size:.42rem;
  font-weight:850;
  letter-spacing:.08em;
  color:var(--muted);
}
.plugin-twitch .twitch-summary-metric strong{
  display:block;
  margin-top:.08rem;
  font-size:1rem;
}
.plugin-twitch .twitch-summary-metric.live strong{color:#fff}
.plugin-twitch .twitch-summary-metric.live{
  border-color:rgba(255,59,87,.30);
  background:rgba(255,59,87,.045);
}

.plugin-twitch .twitch-section-head{
  display:flex;
  align-items:end;
  justify-content:space-between;
  gap:.7rem;
  margin:.1rem .1rem .42rem;
}

.plugin-twitch .twitch-live-pill{
  padding:.26rem .48rem;
  border:1px solid rgba(255,59,87,.35);
  border-radius:999px;
  background:rgba(255,59,87,.08);
  color:#ff6a7e;
  font-size:.48rem;
  font-weight:950;
  letter-spacing:.05em;
}

.plugin-twitch .twitch-live-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(330px,1fr));
  gap:var(--gap);
}

.plugin-twitch .twitch-live-card{
  position:relative;
  min-height:13.2rem;
  overflow:hidden;
  border:1px solid rgba(145,70,255,.35);
  border-radius:.72rem;
  background:#090c10;
  text-decoration:none;
  color:inherit;
  isolation:isolate;
  box-shadow:0 8px 28px rgba(0,0,0,.18);
}

.plugin-twitch .twitch-live-card::after{
  content:"";
  position:absolute;
  inset:0;
  z-index:2;
  pointer-events:none;
  background:
    linear-gradient(180deg,rgba(3,5,8,.02) 15%,rgba(3,5,8,.55) 58%,rgba(3,5,8,.96) 100%),
    linear-gradient(90deg,rgba(3,5,8,.54),transparent 48%);
}

.plugin-twitch .twitch-live-card:hover{
  border-color:rgba(145,70,255,.72);
  transform:translateY(-1px);
}

.plugin-twitch .twitch-live-thumb{
  position:absolute;
  inset:0;
  z-index:0;
  width:100%;
  height:100%;
  object-fit:cover;
  opacity:.72;
  transition:transform .35s ease,opacity .35s ease;
}
.plugin-twitch .twitch-live-card:hover .twitch-live-thumb{
  transform:scale(1.018);
  opacity:.82;
}

.plugin-twitch .twitch-live-overlay{
  position:relative;
  z-index:3;
  min-height:13.2rem;
  display:grid;
  grid-template-rows:auto 1fr auto;
  padding:.72rem;
}

.plugin-twitch .twitch-live-top{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:.5rem;
}

.plugin-twitch .twitch-live-badge{
  display:inline-flex;
  align-items:center;
  gap:.28rem;
  padding:.26rem .42rem;
  border-radius:.28rem;
  background:#e91916;
  color:#fff;
  font-size:.48rem;
  font-weight:950;
  letter-spacing:.05em;
  box-shadow:0 0 15px rgba(233,25,22,.20);
}
.plugin-twitch .twitch-live-badge::before{
  content:"";
  width:.34rem;
  height:.34rem;
  border-radius:50%;
  background:#fff;
}

.plugin-twitch .twitch-live-viewers{
  padding:.26rem .42rem;
  border-radius:.28rem;
  background:rgba(0,0,0,.62);
  backdrop-filter:blur(6px);
  font-size:.48rem;
  font-weight:850;
}

.plugin-twitch .twitch-channel-row{
  align-self:end;
  display:grid;
  grid-template-columns:3rem minmax(0,1fr);
  gap:.62rem;
  align-items:center;
}

.plugin-twitch .twitch-avatar{
  width:3rem;
  height:3rem;
  border-radius:50%;
  overflow:hidden;
  border:2px solid rgba(255,255,255,.78);
  background:#151b20;
  box-shadow:0 0 0 3px rgba(145,70,255,.25);
}
.plugin-twitch .twitch-avatar img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
}

.plugin-twitch .twitch-channel-copy{min-width:0}
.plugin-twitch .twitch-channel-name{
  font-size:.87rem;
  font-weight:950;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-twitch .twitch-game{
  margin-top:.08rem;
  color:#c5adff;
  font-size:.58rem;
  font-weight:800;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-twitch .twitch-title{
  margin-top:.18rem;
  color:#d8e1e5;
  font-size:.56rem;
  line-height:1.23;
  display:-webkit-box;
  -webkit-line-clamp:2;
  -webkit-box-orient:vertical;
  overflow:hidden;
}

.plugin-twitch .twitch-live-bottom{
  display:flex;
  gap:.35rem;
  align-items:center;
  flex-wrap:wrap;
  margin-top:.5rem;
}
.plugin-twitch .twitch-meta-chip{
  padding:.2rem .32rem;
  border:1px solid rgba(255,255,255,.13);
  border-radius:.28rem;
  background:rgba(0,0,0,.45);
  backdrop-filter:blur(5px);
  font-size:.43rem;
  color:#cbd6db;
}
.plugin-twitch .twitch-tag{
  color:#d4c0ff;
  border-color:rgba(145,70,255,.25);
}

.plugin-twitch .twitch-offline-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
  gap:var(--gap);
}

.plugin-twitch .twitch-offline-card{
  position:relative;
  display:grid;
  grid-template-columns:4.6rem minmax(0,1fr);
  gap:.65rem;
  min-height:6.1rem;
  padding:.6rem;
  overflow:hidden;
  border:1px solid var(--border);
  border-radius:.62rem;
  background:
    linear-gradient(145deg,rgba(145,70,255,.035),rgba(255,255,255,.008));
  text-decoration:none;
  color:inherit;
}
.plugin-twitch .twitch-offline-card:hover{
  border-color:#485963;
  background:
    linear-gradient(145deg,rgba(145,70,255,.055),rgba(255,255,255,.012));
}

.plugin-twitch .twitch-offline-media{
  position:relative;
  width:4.6rem;
  height:4.9rem;
  border-radius:.46rem;
  overflow:hidden;
  background:#11171c;
  border:1px solid #2d3a42;
}
.plugin-twitch .twitch-offline-media img{
  width:100%;
  height:100%;
  object-fit:cover;
  display:block;
  filter:saturate(.72) brightness(.72);
}
.plugin-twitch .twitch-offline-avatar{
  position:absolute;
  left:.3rem;
  bottom:.3rem;
  width:1.7rem;
  height:1.7rem;
  border-radius:50%;
  overflow:hidden;
  border:2px solid #0a0e12;
  background:#161c20;
}
.plugin-twitch .twitch-offline-avatar img{
  filter:none;
  width:100%;
  height:100%;
  object-fit:cover;
}

.plugin-twitch .twitch-offline-copy{
  min-width:0;
  display:grid;
  align-content:center;
}
.plugin-twitch .twitch-offline-name{
  font-size:.72rem;
  font-weight:950;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.plugin-twitch .twitch-offline-status{
  margin-top:.11rem;
  color:#8998a0;
  font-size:.48rem;
  font-weight:800;
}
.plugin-twitch .twitch-offline-last{
  margin-top:.22rem;
  color:#cbd6db;
  font-size:.52rem;
  line-height:1.2;
  display:-webkit-box;
  -webkit-line-clamp:2;
  -webkit-box-orient:vertical;
  overflow:hidden;
}
.plugin-twitch .twitch-offline-meta{
  display:flex;
  gap:.28rem;
  flex-wrap:wrap;
  margin-top:.32rem;
}

.plugin-twitch .twitch-empty{
  grid-column:1/-1;
  display:grid;
  place-items:center;
  min-height:8rem;
  border:1px dashed var(--border);
  border-radius:.62rem;
  color:var(--muted);
}

@media(min-width:1200px) and (max-height:520px){
  .plugin-twitch .twitch-hero{min-height:5.2rem;padding:.65rem .8rem}
  .plugin-twitch .twitch-live-card,
  .plugin-twitch .twitch-live-overlay{min-height:10rem}
  .plugin-twitch .twitch-live-grid{grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
  .plugin-twitch .twitch-offline-card{min-height:5.2rem}
}

@media(max-width:760px){
  .plugin-twitch .twitch-hero{align-items:flex-start;flex-direction:column}
  .plugin-twitch .twitch-summary-metrics{width:100%}
  .plugin-twitch .twitch-summary-metric{text-align:left}
  .plugin-twitch .twitch-live-grid,
  .plugin-twitch .twitch-offline-grid{grid-template-columns:1fr}
}

@media(prefers-reduced-motion:reduce){
  .plugin-twitch .twitch-live-thumb{transition:none}
  .plugin-twitch .twitch-live-card:hover .twitch-live-thumb{transform:none}
}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.twitch={
  viewers(n){
    n=Number(n||0);
    if(n>=1000000)return `${(n/1000000).toFixed(n>=10000000?0:1)}M`;
    if(n>=1000)return `${(n/1000).toFixed(n>=10000?0:1)}K`;
    return String(n);
  },

  ago(seconds){
    if(seconds==null)return "No recent VOD";
    seconds=Math.max(0,Number(seconds));
    if(seconds<60)return "just now";
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    if(seconds<604800)return `${Math.floor(seconds/86400)}d ago`;
    return `${Math.floor(seconds/604800)}w ago`;
  },

  thumb(url,w=640,h=360){
    return String(url||"")
      .replace("{width}",String(w))
      .replace("{height}",String(h));
  },

  tags(tags,max=3){
    return (tags||[])
      .filter(Boolean)
      .slice(0,max)
      .map(tag=>`<span class="twitch-meta-chip twitch-tag">${RackDash.escape(tag)}</span>`)
      .join("");
  },

  liveCard(channel){
    const name=RackDash.escape(channel.display_name||channel.login||"Unknown");
    const login=encodeURIComponent(channel.login||"");
    const avatar=channel.profile_image_url
      ?`<img src="${RackDash.escape(channel.profile_image_url)}" alt="">`
      :"";
    const thumbnail=this.thumb(channel.thumbnail_url,640,360);
    const thumb=thumbnail
      ?`<img class="twitch-live-thumb" src="${RackDash.escape(thumbnail)}" alt="">`
      :"";
    const language=channel.language
      ?`<span class="twitch-meta-chip">${RackDash.escape(String(channel.language).toUpperCase())}</span>`
      :"";
    const mature=channel.is_mature
      ?`<span class="twitch-meta-chip">MATURE</span>`
      :"";

    return `
      <a class="twitch-live-card" href="https://www.twitch.tv/${login}" target="_blank" rel="noopener">
        ${thumb}
        <div class="twitch-live-overlay">
          <div class="twitch-live-top">
            <span class="twitch-live-badge">LIVE</span>
            <span class="twitch-live-viewers">${this.viewers(channel.viewer_count)} VIEWERS</span>
          </div>

          <div></div>

          <div>
            <div class="twitch-channel-row">
              <div class="twitch-avatar">${avatar}</div>
              <div class="twitch-channel-copy">
                <div class="twitch-channel-name">${name}</div>
                <div class="twitch-game">${RackDash.escape(channel.game_name||"No category")}</div>
                <div class="twitch-title">${RackDash.escape(channel.title||"Live on Twitch")}</div>
              </div>
            </div>

            <div class="twitch-live-bottom">
              <span class="twitch-meta-chip">${RackDash.escape(channel.uptime_short||"--")} UPTIME</span>
              ${language}
              ${mature}
              ${this.tags(channel.tags)}
            </div>
          </div>
        </div>
      </a>
    `;
  },

  offlineCard(channel){
    const name=RackDash.escape(channel.display_name||channel.login||"Unknown");
    const login=encodeURIComponent(channel.login||"");
    const avatar=channel.profile_image_url
      ?`<img src="${RackDash.escape(channel.profile_image_url)}" alt="">`
      :"";
    const vodThumb=this.thumb(channel.last_thumbnail_url,320,180);
    const fallback=channel.profile_image_url||"";
    const media=vodThumb||fallback;
    const mediaImg=media
      ?`<img src="${RackDash.escape(media)}" alt="">`
      :"";
    const game=channel.channel_game_name||channel.last_game_name||"";
    const lang=channel.language
      ?`<span class="twitch-meta-chip">${RackDash.escape(String(channel.language).toUpperCase())}</span>`
      :"";

    return `
      <a class="twitch-offline-card" href="https://www.twitch.tv/${login}" target="_blank" rel="noopener">
        <div class="twitch-offline-media">
          ${mediaImg}
          <div class="twitch-offline-avatar">${avatar}</div>
        </div>

        <div class="twitch-offline-copy">
          <div class="twitch-offline-name">${name}</div>
          <div class="twitch-offline-status">OFFLINE · LAST LIVE ${RackDash.escape(this.ago(channel.last_broadcast_age))}</div>
          <div class="twitch-offline-last">${RackDash.escape(channel.last_title||channel.channel_title||"No recent broadcast title")}</div>
          <div class="twitch-offline-meta">
            ${game?`<span class="twitch-meta-chip">${RackDash.escape(game)}</span>`:""}
            ${lang}
            ${this.tags(channel.tags,2)}
          </div>
        </div>
      </a>
    `;
  },

  render(data,root){
    const live=data.live||[];
    const offline=data.offline||[];
    const totalViewers=live.reduce((sum,row)=>sum+Number(row.viewer_count||0),0);

    root.querySelector('[data-role="live-count"]').textContent=String(live.length);
    root.querySelector('[data-role="viewer-total"]').textContent=this.viewers(totalViewers);
    root.querySelector('[data-role="channel-count"]').textContent=String(data.resolved_count||data.configured_count||0);
    root.querySelector('[data-role="live-pill"]').textContent=`${live.length} LIVE`;

    const headline=root.querySelector('[data-role="headline"]');
    const subhead=root.querySelector('[data-role="subhead"]');

    if(live.length){
      headline.textContent=live.length===1
        ?`${live[0].display_name||live[0].login} is live`
        :`${live.length} channels are live`;
      subhead.textContent=totalViewers
        ?`${this.viewers(totalViewers)} combined viewers across live channels`
        :`${live.length} active stream${live.length===1?"":"s"}`;
    }else{
      headline.textContent="Nobody is live right now";
      subhead.textContent=`Tracking ${data.resolved_count||0} Twitch channel${data.resolved_count===1?"":"s"}`;
    }

    const liveSection=root.querySelector('[data-role="live-section"]');
    const liveGrid=root.querySelector('[data-role="live-grid"]');
    liveGrid.innerHTML=live.map(row=>this.liveCard(row)).join("");
    liveSection.hidden=!live.length;

    const offlineSection=root.querySelector('[data-role="offline-section"]');
    const offlineGrid=root.querySelector('[data-role="offline-grid"]');
    offlineGrid.innerHTML=offline.map(row=>this.offlineCard(row)).join("")||
      `<div class="twitch-empty">All configured channels are currently live.</div>`;
    offlineSection.hidden=!offline.length;
  }
};
'''

_token_lock = threading.Lock()
_token = {"access_token": "", "expires_at": 0.0}
_cache = TTLCache(45)


def _channels() -> list[str]:
    raw = os.getenv("TWITCH_CHANNELS", "")
    result = []
    seen = set()
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        value = value.rstrip("/").split("/")[-1].strip().lower().lstrip("@")
        if value and value not in seen:
            seen.add(value)
            result.append(value)
        if len(result) >= 100:
            break
    return result


def _credentials():
    client_id = os.getenv("TWITCH_CLIENT_ID", "").strip()
    secret = os.getenv("TWITCH_CLIENT_SECRET", "").strip()
    if not client_id or not secret:
        raise RuntimeError("Twitch Client ID and Client Secret are required")
    return client_id, secret


def _access_token() -> str:
    now = time.time()
    if _token["access_token"] and now < _token["expires_at"] - 120:
        return _token["access_token"]

    with _token_lock:
        now = time.time()
        if _token["access_token"] and now < _token["expires_at"] - 120:
            return _token["access_token"]

        client_id, secret = _credentials()
        response = requests.post(
            "https://id.twitch.tv/oauth2/token",
            data={
                "client_id": client_id,
                "client_secret": secret,
                "grant_type": "client_credentials",
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        _token["access_token"] = payload["access_token"]
        _token["expires_at"] = now + int(payload.get("expires_in", 3600))
        return _token["access_token"]


def _headers():
    client_id, _ = _credentials()
    return {
        "Authorization": f"Bearer {_access_token()}",
        "Client-Id": client_id,
    }


def _get(path: str, params=None):
    response = requests.get(
        f"https://api.twitch.tv/helix/{path}",
        headers=_headers(),
        params=params,
        timeout=8,
    )
    if response.status_code == 401:
        with _token_lock:
            _token["access_token"] = ""
            _token["expires_at"] = 0.0
        response = requests.get(
            f"https://api.twitch.tv/helix/{path}",
            headers=_headers(),
            params=params,
            timeout=8,
        )
    response.raise_for_status()
    return response.json().get("data", [])


def _users(logins: list[str]):
    return _get("users", [("login", login) for login in logins])


def _streams(logins: list[str]):
    return _get("streams", [("user_login", login) for login in logins])


def _channel_information(user_ids: list[str]):
    if not user_ids:
        return []
    return _get(
        "channels",
        [("broadcaster_id", user_id) for user_id in user_ids[:100]],
    )


def _latest_archive(user_id: str):
    rows = _get("videos", {"user_id": user_id, "type": "archive", "first": 1})
    return rows[0] if rows else None


def _parse_time(value: str | None):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _short_duration(seconds: int):
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def get_data():
    cached = _cache.get()
    if cached:
        now = datetime.now(timezone.utc)
        data = {
            **cached,
            "live": [dict(x) for x in cached.get("live", [])],
            "offline": [dict(x) for x in cached.get("offline", [])],
        }
        for row in data["live"]:
            started = _parse_time(row.get("started_at"))
            if started:
                row["uptime_seconds"] = int((now - started).total_seconds())
                row["uptime_short"] = _short_duration(row["uptime_seconds"])
        for row in data["offline"]:
            last = _parse_time(row.get("last_broadcast_at"))
            row["last_broadcast_age"] = int((now-last).total_seconds()) if last else None
        return data

    logins = _channels()
    if not logins:
        raise RuntimeError("Configure at least one Twitch channel")

    user_rows = _users(logins)
    users_by_login = {row["login"].lower(): row for row in user_rows}
    stream_rows = _streams(logins)
    streams_by_login = {row["user_login"].lower(): row for row in stream_rows}

    user_ids = [row.get("id") for row in user_rows if row.get("id")]
    try:
        channel_rows = _channel_information(user_ids)
    except Exception:
        channel_rows = []
    channels_by_id = {
        row.get("broadcaster_id"): row
        for row in channel_rows
        if row.get("broadcaster_id")
    }

    now = datetime.now(timezone.utc)
    live = []
    offline = []
    offline_users = []

    for login in logins:
        user = users_by_login.get(login)
        if not user:
            continue
        stream = streams_by_login.get(login)
        channel_info = channels_by_id.get(user.get("id"), {})
        common = {
            "login": user.get("login", login),
            "display_name": user.get("display_name") or user.get("login") or login,
            "profile_image_url": user.get("profile_image_url", ""),
            "description": user.get("description", ""),
            "channel_title": channel_info.get("title", ""),
            "channel_game_name": channel_info.get("game_name", ""),
            "language": channel_info.get("broadcaster_language", ""),
            "tags": channel_info.get("tags", []) or [],
            "is_branded_content": bool(channel_info.get("is_branded_content", False)),
        }
        if stream:
            started = _parse_time(stream.get("started_at"))
            uptime = int((now-started).total_seconds()) if started else 0
            live.append({
                **common,
                "game_name": stream.get("game_name", ""),
                "viewer_count": int(stream.get("viewer_count", 0)),
                "started_at": stream.get("started_at", ""),
                "uptime_seconds": uptime,
                "uptime_short": _short_duration(uptime),
                "title": stream.get("title", ""),
                "thumbnail_url": stream.get("thumbnail_url", ""),
                "language": stream.get("language") or common.get("language", ""),
                "tags": stream.get("tags") or common.get("tags", []),
                "is_mature": bool(stream.get("is_mature", False)),
                "stream_type": stream.get("type", ""),
            })
        else:
            offline_users.append((login, user, common))

    archive_by_id = {}
    if offline_users:
        workers = min(8, len(offline_users))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(_latest_archive, user["id"]): user["id"]
                for _, user, _ in offline_users
            }
            for future in as_completed(future_map):
                user_id = future_map[future]
                try:
                    archive_by_id[user_id] = future.result()
                except Exception:
                    archive_by_id[user_id] = None

    for _, user, common in offline_users:
        archive = archive_by_id.get(user["id"])
        last_at = ""
        if archive:
            last_at = archive.get("created_at") or archive.get("published_at") or ""
        last_dt = _parse_time(last_at)
        offline.append({
            **common,
            "last_broadcast_at": last_at,
            "last_broadcast_age": int((now-last_dt).total_seconds()) if last_dt else None,
            "last_title": archive.get("title", "") if archive else "",
            "last_url": archive.get("url", "") if archive else "",
            "last_thumbnail_url": archive.get("thumbnail_url", "") if archive else "",
            "last_duration": archive.get("duration", "") if archive else "",
            "last_view_count": int(archive.get("view_count", 0)) if archive else 0,
        })

    payload = {
        "configured_count": len(logins),
        "resolved_count": len(user_rows),
        "live": live,
        "offline": offline,
    }
    _cache.set(payload)
    return payload


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {"title": "Twitch", "lines": ["Data unavailable"]}

    live = data.get("live", [])
    if live:
        lines = [f"{len(live)} LIVE"]
        for channel in live[:4]:
            viewers = int(channel.get("viewer_count", 0))
            viewer_text = f"{viewers/1000:.1f}K" if viewers >= 1000 else str(viewers)
            lines.append(
                f"{channel.get('display_name','')[:10]} {viewer_text} {channel.get('uptime_short','')}"
            )
        return {"title": "Twitch", "lines": lines}

    offline = data.get("offline", [])
    lines = ["Nobody live"]
    for channel in offline[:4]:
        age = channel.get("last_broadcast_age")
        if age is None:
            when = "?"
        elif age < 3600:
            when = f"{age//60}m"
        elif age < 86400:
            when = f"{age//3600}h"
        else:
            when = f"{age//86400}d"
        lines.append(f"{channel.get('display_name','')[:12]} {when}")
    return {"title": "Twitch", "lines": lines}
