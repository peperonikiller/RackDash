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
PLUGIN_VERSION = "1.0.0"
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
  <div class="twitch-summary">
    <div>
      <span class="eyebrow">TWITCH</span>
      <h1 data-role="headline">Checking channels...</h1>
      <div class="muted" data-role="subhead"></div>
    </div>
    <div class="twitch-live-badge" data-role="live-badge">--</div>
  </div>
  <div class="twitch-grid" data-role="channels"></div>
</div>
'''

PLUGIN_CSS = r'''
.plugin-twitch .twitch-shell{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr);gap:var(--gap)}
.plugin-twitch .twitch-summary{display:flex;justify-content:space-between;align-items:center;gap:1rem}
.plugin-twitch .twitch-summary h1{margin:.18rem 0 0;font-size:clamp(1.1rem,2.4vw,2rem)}
.plugin-twitch .twitch-live-badge{min-width:5rem;text-align:center;padding:.45rem .7rem;border:1px solid var(--border);border-radius:.5rem;font-size:.7rem;font-weight:900;color:var(--muted);background:rgba(255,255,255,.018)}
.plugin-twitch .twitch-live-badge.live{color:#fff;border-color:rgba(145,70,255,.75);background:rgba(145,70,255,.18);box-shadow:0 0 18px rgba(145,70,255,.12)}
.plugin-twitch .twitch-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:var(--gap);align-content:start;overflow:auto;padding-bottom:.2rem}
.plugin-twitch .twitch-card{position:relative;display:grid;grid-template-columns:54px minmax(0,1fr) auto;align-items:center;gap:.65rem;min-height:78px;padding:.65rem;border:1px solid var(--border);border-radius:.65rem;background:linear-gradient(145deg,rgba(145,70,255,.055),rgba(255,255,255,.012));text-decoration:none;color:inherit;overflow:hidden}
.plugin-twitch .twitch-card:hover{border-color:#515f68}
.plugin-twitch .twitch-card.live{border-color:rgba(145,70,255,.42)}
.plugin-twitch .twitch-avatar{position:relative;width:54px;height:54px;border-radius:50%;overflow:hidden;background:#121a20;border:1px solid #34434c;flex:none}
.plugin-twitch .twitch-avatar img{width:100%;height:100%;object-fit:cover;display:block}
.plugin-twitch .twitch-avatar .dot{position:absolute;right:1px;bottom:2px;width:11px;height:11px;border-radius:50%;background:#626f76;border:2px solid #0c1318}
.plugin-twitch .twitch-card.live .twitch-avatar .dot{background:#e91916;box-shadow:0 0 8px rgba(233,25,22,.55)}
.plugin-twitch .twitch-copy{min-width:0}
.plugin-twitch .twitch-name{font-size:.86rem;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-twitch .twitch-game{margin-top:.18rem;font-size:.68rem;font-weight:760;color:#b9a0f5;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-twitch .twitch-detail{margin-top:.18rem;font-size:.58rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-twitch .twitch-stat{text-align:right;min-width:62px}
.plugin-twitch .twitch-stat strong{display:block;font-size:.85rem}
.plugin-twitch .twitch-stat small{display:block;margin-top:.12rem;font-size:.52rem;color:var(--muted);text-transform:uppercase}
.plugin-twitch .offline .twitch-avatar img{filter:grayscale(1);opacity:.66}
.plugin-twitch .offline .twitch-game{color:#8b989f}
.plugin-twitch .twitch-empty{grid-column:1/-1;display:grid;place-items:center;min-height:160px;border:1px dashed var(--border);border-radius:.6rem;color:var(--muted)}
@media(min-width:1000px) and (max-height:500px){
  .plugin-twitch .twitch-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
  .plugin-twitch .twitch-card{min-height:70px;padding:.5rem}
  .plugin-twitch .twitch-avatar{width:46px;height:46px}
}
@media(max-width:650px){
  .plugin-twitch .twitch-grid{grid-template-columns:1fr}
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
    if(seconds==null)return "Unavailable";
    seconds=Math.max(0,Number(seconds));
    if(seconds<60)return "just now";
    if(seconds<3600)return `${Math.floor(seconds/60)}m ago`;
    if(seconds<86400)return `${Math.floor(seconds/3600)}h ago`;
    if(seconds<604800)return `${Math.floor(seconds/86400)}d ago`;
    return `${Math.floor(seconds/604800)}w ago`;
  },

  card(channel,live){
    const name=RackDash.escape(channel.display_name||channel.login||"Unknown");
    const login=encodeURIComponent(channel.login||"");
    const avatar=channel.profile_image_url
      ?`<img src="${RackDash.escape(channel.profile_image_url)}" alt="">`
      :"";
    if(live){
      return `<a class="twitch-card live" href="https://www.twitch.tv/${login}" target="_blank" rel="noopener">
        <div class="twitch-avatar">${avatar}<span class="dot"></span></div>
        <div class="twitch-copy">
          <div class="twitch-name">${name}</div>
          <div class="twitch-game">${RackDash.escape(channel.game_name||"No category")}</div>
          <div class="twitch-detail">${RackDash.escape(channel.title||"Live on Twitch")}</div>
        </div>
        <div class="twitch-stat">
          <strong>${this.viewers(channel.viewer_count)}</strong><small>viewers</small>
          <strong>${RackDash.escape(channel.uptime_short||"--")}</strong><small>uptime</small>
        </div>
      </a>`;
    }
    return `<a class="twitch-card offline" href="https://www.twitch.tv/${login}" target="_blank" rel="noopener">
      <div class="twitch-avatar">${avatar}<span class="dot"></span></div>
      <div class="twitch-copy">
        <div class="twitch-name">${name}</div>
        <div class="twitch-game">OFFLINE</div>
        <div class="twitch-detail">${channel.last_title?RackDash.escape(channel.last_title):"No archived broadcast found"}</div>
      </div>
      <div class="twitch-stat">
        <strong>${this.ago(channel.last_broadcast_age)}</strong><small>last broadcast</small>
      </div>
    </a>`;
  },

  render(data,root){
    const headline=root.querySelector('[data-role="headline"]');
    const subhead=root.querySelector('[data-role="subhead"]');
    const badge=root.querySelector('[data-role="live-badge"]');
    const grid=root.querySelector('[data-role="channels"]');

    const live=data.live||[];
    if(live.length){
      headline.textContent=live.length===1?"1 channel is live":`${live.length} channels are live`;
      subhead.textContent=`Watching ${data.configured_count||0} configured channel${data.configured_count===1?"":"s"}`;
      badge.textContent=`${live.length} LIVE`;
      badge.classList.add("live");
      grid.innerHTML=live.map(x=>this.card(x,true)).join("");
      return;
    }

    badge.textContent="OFFLINE";
    badge.classList.remove("live");
    headline.textContent="Nobody is live right now";
    subhead.textContent=`${data.offline?.length||0} configured channel${data.offline?.length===1?"":"s"} offline`;
    grid.innerHTML=(data.offline||[]).map(x=>this.card(x,false)).join("")||
      `<div class="twitch-empty">No valid Twitch channels were found.</div>`;
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

    now = datetime.now(timezone.utc)
    live = []
    offline = []
    offline_users = []

    for login in logins:
        user = users_by_login.get(login)
        if not user:
            continue
        stream = streams_by_login.get(login)
        common = {
            "login": user.get("login", login),
            "display_name": user.get("display_name") or user.get("login") or login,
            "profile_image_url": user.get("profile_image_url", ""),
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
