from __future__ import annotations
import os
import xml.etree.ElementTree as ET
from datetime import timedelta
import requests
from flask import Response, request

PLUGIN_ID = "plex"
PLUGIN_NAME = "Plex"
PLUGIN_VERSION = "1.0.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/plex.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ['network', 'custom_routes']
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 20
PLUGIN_REFRESH_SECONDS = 3
PLUGIN_ACCENT = "#e5a00d"
PLUGIN_ICON = "MEDIA"
PLUGIN_PUBLIC_ERROR = "Plex unavailable"

PLUGIN_CONFIG = [{'key': 'PLEX_URL', 'label': 'Plex URL', 'type': 'text', 'default': 'http://127.0.0.1:32400', 'required': True}, {'key': 'PLEX_TOKEN', 'label': 'Plex Token', 'type': 'token', 'default': '', 'required': True}, {'key': 'TMDB_API_KEY', 'label': 'TMDB API Key', 'type': 'token', 'default': '', 'help': 'Optional. Enables Upcoming Movies.'}, {'key': 'TMDB_REGION', 'label': 'TMDB Region', 'type': 'text', 'default': 'US'}, {'key': 'TMDB_LANGUAGE', 'label': 'TMDB Language', 'type': 'text', 'default': 'en-US'}]

PLEX_URL = os.getenv("PLEX_URL", "http://127.0.0.1:32400").rstrip("/")
PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_REGION = os.getenv("TMDB_REGION", "US")
TMDB_LANGUAGE = os.getenv("TMDB_LANGUAGE", "en-US")


def _plex(path):
    if not PLEX_TOKEN:
        raise RuntimeError("Plex token not configured")
    return requests.get(
        f"{PLEX_URL}{path}",
        params={"X-Plex-Token": PLEX_TOKEN},
        timeout=4,
    )


def _fmt_ms(ms):
    return str(timedelta(seconds=max(0, int(ms or 0) // 1000)))


def _session(node):
    media = node.find("Media")
    player = node.find("Player")
    user = node.find("User")
    transcode = node.find("TranscodeSession")
    typ = node.attrib.get("type", "")
    title = node.attrib.get("title", "Unknown")
    subtitle = node.attrib.get("year", "")
    if typ == "episode":
        show = node.attrib.get("grandparentTitle", "")
        title = f"{show} — {title}" if show else title
        subtitle = node.attrib.get("parentTitle", "")

    decision = "Transcode" if transcode is not None else "Direct Play"
    if transcode is None and media is not None:
        vd = media.attrib.get("videoDecision", "")
        ad = media.attrib.get("audioDecision", "")
        if "transcode" in (vd, ad):
            decision = "Transcode"
        elif "copy" in (vd, ad):
            decision = "Direct Stream"

    duration = int(node.attrib.get("duration", 0) or 0)
    position = int(node.attrib.get("viewOffset", 0) or 0)
    bitrate = media.attrib.get("bitrate", "") if media is not None else ""

    return {
        "title": title,
        "subtitle": subtitle,
        "user": user.attrib.get("title", "Unknown") if user is not None else "Unknown",
        "player": player.attrib.get("title", "Unknown") if player is not None else "Unknown",
        "state": player.attrib.get("state", "") if player is not None else "",
        "decision": decision,
        "resolution": (media.attrib.get("videoResolution", "") if media is not None else "").upper(),
        "codec": (media.attrib.get("videoCodec", "") if media is not None else "").upper(),
        "bitrate": f"{round(int(bitrate)/1000,1)} Mbps" if bitrate.isdigit() else "",
        "progress": round(position / duration * 100, 1) if duration else 0,
        "position": _fmt_ms(position),
        "duration": _fmt_ms(duration),
        "thumb": node.attrib.get("thumb", ""),
    }


def _sessions():
    response = _plex("/status/sessions")
    response.raise_for_status()
    root = ET.fromstring(response.content)
    return [_session(node) for node in root if node.tag in ("Video", "Track", "Photo")]


def _recent():
    response = _plex("/library/recentlyAdded")
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for node in list(root)[:9]:
        if node.tag not in ("Video", "Directory", "Track"):
            continue
        typ = node.attrib.get("type", "")
        title = node.attrib.get("title", "Unknown")
        subtitle = node.attrib.get("year", "")
        if typ == "episode":
            show = node.attrib.get("grandparentTitle", "")
            if show:
                title = f"{show} — {title}"
            subtitle = node.attrib.get("parentTitle", "")
        items.append({
            "title": title,
            "subtitle": subtitle,
            "thumb": node.attrib.get("thumb", ""),
        })
    return items


def _upcoming():
    if not TMDB_API_KEY:
        return {"enabled": False, "movies": []}
    response = requests.get(
        "https://api.themoviedb.org/3/movie/upcoming",
        params={
            "api_key": TMDB_API_KEY,
            "region": TMDB_REGION,
            "language": TMDB_LANGUAGE,
            "page": 1,
        },
        timeout=6,
    )
    response.raise_for_status()
    movies = []
    for movie in response.json().get("results", [])[:6]:
        poster = movie.get("poster_path") or ""
        movies.append({
            "title": movie.get("title") or "Upcoming Movie",
            "release_date": movie.get("release_date", ""),
            "overview": movie.get("overview", ""),
            "poster": f"https://image.tmdb.org/t/p/w342{poster}" if poster else "",
        })
    return {"enabled": True, "movies": movies}


def get_data():
    sessions = _sessions()
    return {
        "sessions": sessions,
        "streams": len(sessions),
        "transcodes": sum(1 for item in sessions if item["decision"] == "Transcode"),
        "recent": _recent(),
        "upcoming": _upcoming(),
    }


def register_routes(app):
    @app.get("/api/plugin/plex/image")
    def plex_image():
        path = request.args.get("path", "")
        if not path.startswith("/"):
            return Response(status=404)
        try:
            response = _plex(path)
            response.raise_for_status()
            return Response(
                response.content,
                content_type=response.headers.get("Content-Type", "image/jpeg"),
            )
        except Exception:
            return Response(status=404)


PLUGIN_HTML = r'''
<div class="plugin-head">
  <div><span class="eyebrow">PLEX MEDIA</span><h1>Server Overview</h1></div>
  <div class="head-stat"><strong data-role="stream-count">0</strong><small>ACTIVE STREAMS</small></div>
</div>
<div class="plex-grid">
  <section class="surface plex-now">
    <div class="section-label">NOW PLAYING</div>
    <div data-role="now"></div>
  </section>
  <section class="surface">
    <div class="section-label">RECENTLY ADDED</div>
    <div class="poster-grid" data-role="recent"></div>
  </section>
  <section class="surface">
    <div class="section-label">UPCOMING MOVIES</div>
    <div class="compact-list" data-role="upcoming"></div>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-plex .plex-grid{display:grid;grid-template-columns:1.35fr 1fr 1fr;gap:var(--gap);min-height:0}
.plugin-plex .plex-now-card{display:grid;grid-template-columns:minmax(90px,28%) 1fr;gap:var(--gap)}
.plugin-plex .plex-now-card img{width:100%;max-height:220px;object-fit:cover;border-radius:var(--radius-sm)}
.plugin-plex .media-title{font-size:clamp(1rem,2.4vw,1.7rem);font-weight:800}
.plugin-plex .media-meta{color:var(--muted);font-size:.8rem;margin:.25rem 0}
.plugin-plex .media-badges{display:flex;gap:.35rem;flex-wrap:wrap;margin:.45rem 0}
.plugin-plex .media-badge{font-size:.65rem;padding:.25rem .4rem;border-radius:.3rem;background:#172129}
.plugin-plex .media-badge.good{background:#1d8f46;color:#fff}.plugin-plex .media-badge.warn{background:#c87816;color:#fff}
.plugin-plex .poster-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.45rem}
.plugin-plex .poster-tile img{width:100%;aspect-ratio:2/3;object-fit:cover;border-radius:.4rem}
.plugin-plex .poster-title{font-size:.68rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-plex .poster-sub{font-size:.6rem;color:var(--muted)}
.plugin-plex .compact-list{display:grid;gap:.45rem}
.plugin-plex .movie-row{display:grid;grid-template-columns:42px 1fr;gap:.5rem}
.plugin-plex .movie-row img{width:42px;height:62px;object-fit:cover;border-radius:.3rem}
.plugin-plex .movie-title{font-size:.72rem;font-weight:750}.plugin-plex .movie-date{font-size:.62rem;color:var(--muted)}
.plugin-plex .movie-overview{font-size:.6rem;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
@media(max-width:850px){.plugin-plex .plex-grid{grid-template-columns:1fr}.plugin-plex .poster-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.plex={
  mediaIndex:0,
  render(data,root){
    root.querySelector('[data-role="stream-count"]').textContent=data.streams||0;
    const now=root.querySelector('[data-role="now"]');
    const sessions=data.sessions||[];
    if(sessions.length){
      this.mediaIndex%=sessions.length;
      const s=sessions[this.mediaIndex];
      const decisionClass=s.decision==="Transcode"?"warn":"good";
      now.innerHTML=`
        <div class="plex-now-card">
          <img src="/api/plugin/plex/image?path=${encodeURIComponent(s.thumb||"")}" alt="">
          <div>
            <div class="media-title">${RackDash.escape(s.title)}</div>
            <div class="media-meta">${RackDash.escape(s.subtitle||"")}</div>
            <div class="media-badges">
              <span class="media-badge ${decisionClass}">${RackDash.escape(s.decision)}</span>
              <span class="media-badge">${RackDash.escape([s.resolution,s.codec].filter(Boolean).join(" "))}</span>
              <span class="media-badge">${RackDash.escape(s.bitrate||"")}</span>
            </div>
            <div class="media-meta">${RackDash.escape(s.user)} • ${RackDash.escape(s.player)}</div>
            ${RackDash.progress(s.progress)}
            <div class="split meta-small"><span>${RackDash.escape(s.position)}</span><span>${RackDash.escape(s.duration)}</span></div>
          </div>
        </div>`;
    }else{
      now.innerHTML=`<div class="empty-state"><strong>Nothing playing</strong><span>Server is ready.</span></div>`;
    }

    root.querySelector('[data-role="recent"]').innerHTML=(data.recent||[]).slice(0,6).map(item=>`
      <div class="poster-tile">
        <img src="/api/plugin/plex/image?path=${encodeURIComponent(item.thumb||"")}" alt="">
        <div class="poster-title">${RackDash.escape(item.title)}</div>
        <div class="poster-sub">${RackDash.escape(item.subtitle||"")}</div>
      </div>`).join("") || `<div class="empty-state">No recent media.</div>`;

    const upcoming=data.upcoming||{};
    root.querySelector('[data-role="upcoming"]').innerHTML=!upcoming.enabled
      ? `<div class="empty-state"><strong>TMDB not configured</strong><span>Add TMDB_API_KEY to config.env.</span></div>`
      : (upcoming.movies||[]).slice(0,4).map(m=>`
        <div class="movie-row">
          ${m.poster?`<img src="${m.poster}" alt="">`:"<div></div>"}
          <div><div class="movie-title">${RackDash.escape(m.title)}</div>
          <div class="movie-date">${RackDash.escape(m.release_date||"Release TBA")}</div>
          <div class="movie-overview">${RackDash.escape(m.overview||"")}</div></div>
        </div>`).join("");
  },
  onShow(root){ this.mediaIndex++; }
};
'''
