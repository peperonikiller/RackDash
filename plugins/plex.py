from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import requests

from _shared import TTLCache


PLUGIN_ID = "plex"
PLUGIN_NAME = "Plex"
PLUGIN_VERSION = "1.1.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/plex.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "custom_routes", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 20
PLUGIN_REFRESH_SECONDS = 5
PLUGIN_ACCENT = "#e5a00d"
PLUGIN_ICON = "PLEX"
PLUGIN_PUBLIC_ERROR = "Plex unavailable"

PLUGIN_CONFIG = [
    {
        "key": "PLEX_URL",
        "label": "Plex URL",
        "type": "text",
        "default": "http://127.0.0.1:32400",
        "required": True,
    },
    {
        "key": "PLEX_TOKEN",
        "label": "Plex Token",
        "type": "token",
        "default": "",
        "required": True,
    },
]

PLEX_URL = os.getenv("PLEX_URL", "http://127.0.0.1:32400").rstrip("/")
PLEX_TOKEN = os.getenv("PLEX_TOKEN", "")

_detail_cache = TTLCache(60)
_server_cache = TTLCache(300)


PLUGIN_HTML = r'''
<div class="plex-shell">
  <section class="plex-hero surface">
    <div class="plex-brand">
      <div class="plex-mark">PLEX</div>
      <div>
        <span class="eyebrow">MEDIA SERVER</span>
        <h1 data-role="server-title">Plex</h1>
        <div class="muted" data-role="server-subtitle">Checking server...</div>
      </div>
    </div>

    <div class="plex-hero-stats">
      <div class="hero-stat"><strong data-role="stream-count">0</strong><small>ACTIVE STREAMS</small></div>
      <div class="hero-stat"><strong data-role="transcode-count">0</strong><small>TRANSCODES</small></div>
      <div class="hero-stat"><strong data-role="bandwidth">0 Mbps</strong><small>EST. BANDWIDTH</small></div>
    </div>
  </section>

  <section class="plex-main-grid">
    <article class="surface plex-feature">
      <div class="plex-section-head">
        <div><div class="section-label" data-role="feature-label">NOW PLAYING</div><div class="muted tiny" data-role="feature-subtitle"></div></div>
        <span class="plex-live-chip" data-role="feature-chip">LIVE</span>
      </div>
      <div class="plex-feature-body" data-role="feature"></div>
    </article>

    <article class="surface plex-sidebar">
      <div class="plex-section-head"><div class="section-label">SERVER OVERVIEW</div><span class="detail-note" data-role="server-version"></span></div>
      <div class="plex-overview-grid" data-role="overview"></div>
    </article>
  </section>

  <section class="surface plex-strip-card">
    <div class="plex-section-head"><div><div class="section-label">RECENTLY ADDED</div><div class="muted tiny">Fresh additions to your libraries</div></div></div>
    <div class="plex-poster-strip" data-role="recent-added"></div>
  </section>

  <section class="plex-bottom-grid">
    <article class="surface">
      <div class="plex-section-head"><div><div class="section-label">RECENTLY PLAYED</div><div class="muted tiny">Latest watched or listened items</div></div></div>
      <div class="plex-history-list" data-role="recent-played"></div>
    </article>

    <article class="surface">
      <div class="plex-section-head"><div><div class="section-label">CONTINUE WATCHING</div><div class="muted tiny">On Deck</div></div></div>
      <div class="plex-history-list" data-role="on-deck"></div>
    </article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-plex{--plex:#e5a00d;--plex-soft:rgba(229,160,13,.12);--plex-line:rgba(229,160,13,.34)}
.plugin-plex .plex-shell{display:grid;gap:var(--gap)}
.plugin-plex .plex-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;border-left:3px solid var(--plex);background:linear-gradient(115deg,rgba(229,160,13,.08),rgba(255,255,255,.012) 40%,rgba(255,255,255,.006))}
.plugin-plex .plex-brand{display:flex;align-items:center;gap:.8rem;min-width:0}
.plugin-plex .plex-mark{display:grid;place-items:center;width:3.05rem;height:3.05rem;border-radius:.6rem;background:#111;color:var(--plex);font-size:.72rem;font-weight:1000;letter-spacing:.08em;border:1px solid rgba(229,160,13,.45);box-shadow:0 0 28px rgba(229,160,13,.08)}
.plugin-plex .plex-hero h1{margin:.16rem 0 .12rem;font-size:clamp(1.45rem,3vw,2.55rem);line-height:1}
.plugin-plex .plex-hero-stats{display:flex;gap:.6rem;flex-wrap:wrap;justify-content:flex-end}
.plugin-plex .hero-stat{min-width:6.5rem;padding:.48rem .6rem;border-radius:.46rem;border:1px solid var(--border);background:rgba(0,0,0,.16);text-align:right}
.plugin-plex .hero-stat strong{display:block;color:#fff;font-size:.92rem}.plugin-plex .hero-stat small{display:block;margin-top:.1rem;color:var(--muted);font-size:.43rem;font-weight:850;letter-spacing:.045em}
.plugin-plex .plex-main-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.7fr);gap:var(--gap);align-items:stretch}
.plugin-plex .plex-feature{min-height:23rem;overflow:hidden;position:relative}.plugin-plex .plex-sidebar{min-height:23rem}
.plugin-plex .plex-section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:.75rem;position:relative;z-index:2}.plugin-plex .tiny,.plugin-plex .detail-note{font-size:.46rem;color:var(--muted)}
.plugin-plex .plex-live-chip{padding:.24rem .4rem;border-radius:.3rem;border:1px solid var(--plex-line);background:var(--plex-soft);color:#f4bd48;font-size:.45rem;font-weight:900;letter-spacing:.05em}
.plugin-plex .plex-feature-body{margin-top:.55rem;min-height:19.5rem}
.plugin-plex .plex-now-card{position:relative;display:grid;grid-template-columns:minmax(140px,28%) minmax(0,1fr);gap:clamp(.8rem,2vw,1.3rem);min-height:19rem;align-items:stretch}
.plugin-plex .plex-art{position:relative;min-height:18rem;border-radius:.55rem;overflow:hidden;background:#111;border:1px solid rgba(255,255,255,.05)}
.plugin-plex .plex-art img{width:100%;height:100%;object-fit:cover;display:block}.plugin-plex .plex-art::after{content:"";position:absolute;inset:0;background:linear-gradient(to top,rgba(0,0,0,.42),transparent 42%)}
.plugin-plex .plex-media-copy{align-self:center;min-width:0}.plugin-plex .plex-media-title{font-size:clamp(1.25rem,3.2vw,2.6rem);font-weight:900;line-height:1.02;letter-spacing:-.035em}
.plugin-plex .plex-media-sub{margin-top:.28rem;color:#c5cbd0;font-size:.68rem}.plugin-plex .plex-media-user{margin-top:.75rem;color:var(--muted);font-size:.58rem}
.plugin-plex .plex-badges{display:flex;gap:.35rem;flex-wrap:wrap;margin:.65rem 0}.plugin-plex .plex-badge{font-size:.52rem;padding:.25rem .38rem;border-radius:.3rem;border:1px solid var(--border);background:rgba(255,255,255,.025);color:#d8e1e5}
.plugin-plex .plex-badge.plex-good{border-color:rgba(89,214,120,.34);background:rgba(89,214,120,.055);color:#79e59a}.plugin-plex .plex-badge.plex-warn{border-color:rgba(229,160,13,.45);background:rgba(229,160,13,.08);color:#f4bd48}
.plugin-plex .plex-progress{margin-top:.75rem}.plugin-plex .plex-progress-track{height:.36rem;background:rgba(255,255,255,.08);border-radius:1rem;overflow:hidden}.plugin-plex .plex-progress-bar{height:100%;background:linear-gradient(90deg,#c67f00,var(--plex));border-radius:1rem;box-shadow:0 0 10px rgba(229,160,13,.25)}
.plugin-plex .plex-time{display:flex;justify-content:space-between;gap:.5rem;margin-top:.26rem;color:var(--muted);font-size:.49rem}
.plugin-plex .plex-overview-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.4rem;margin-top:.65rem}.plugin-plex .overview-item{padding:.55rem;border-radius:.42rem;border:1px solid var(--border);background:rgba(255,255,255,.014);min-width:0}
.plugin-plex .overview-item span{display:block;color:var(--muted);font-size:.44rem;font-weight:850;letter-spacing:.04em}.plugin-plex .overview-item strong{display:block;margin-top:.14rem;font-size:.67rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-plex .overview-item.wide{grid-column:1/-1}
.plugin-plex .plex-strip-card{overflow:hidden}.plugin-plex .plex-poster-strip{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:.52rem;margin-top:.58rem}.plugin-plex .plex-poster{min-width:0}
.plugin-plex .plex-poster-art{aspect-ratio:2/3;border-radius:.43rem;overflow:hidden;background:#111;border:1px solid rgba(255,255,255,.04);position:relative}.plugin-plex .plex-poster-art img{width:100%;height:100%;object-fit:cover;display:block}.plugin-plex .plex-poster-art::after{content:"";position:absolute;inset:auto 0 0;height:25%;background:linear-gradient(to top,rgba(0,0,0,.62),transparent)}
.plugin-plex .plex-poster-title{margin-top:.3rem;font-size:.55rem;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-plex .plex-poster-sub{font-size:.45rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-plex .plex-bottom-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--gap);align-items:start}.plugin-plex .plex-history-list{display:grid;gap:.34rem;margin-top:.55rem}
.plugin-plex .history-row{display:grid;grid-template-columns:3.7rem minmax(0,1fr) auto;gap:.55rem;align-items:center;min-height:3.2rem;padding:.35rem;border-radius:.4rem;border:1px solid rgba(255,255,255,.025);background:rgba(255,255,255,.012)}
.plugin-plex .history-thumb{width:3.7rem;height:2.45rem;object-fit:cover;border-radius:.32rem;background:#111}.plugin-plex .history-copy{min-width:0}.plugin-plex .history-title{font-size:.59rem;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-plex .history-sub{margin-top:.08rem;color:var(--muted);font-size:.47rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.plugin-plex .history-time{font-size:.47rem;color:#f0b63b;text-align:right;white-space:nowrap}
.plugin-plex .plex-empty{display:grid;place-items:center;min-height:11rem;border:1px dashed var(--border);border-radius:.48rem;color:var(--muted);font-size:.58rem;text-align:center;padding:1rem}
@media(max-width:1150px){.plugin-plex .plex-poster-strip{grid-template-columns:repeat(6,minmax(0,1fr))}}
@media(max-width:900px){.plugin-plex .plex-main-grid{grid-template-columns:1fr}.plugin-plex .plex-bottom-grid{grid-template-columns:1fr}.plugin-plex .plex-poster-strip{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:650px){.plugin-plex .plex-hero{align-items:flex-start;flex-direction:column}.plugin-plex .plex-hero-stats{justify-content:flex-start}.plugin-plex .plex-now-card{grid-template-columns:1fr}.plugin-plex .plex-art{min-height:15rem}.plugin-plex .plex-poster-strip{grid-template-columns:repeat(3,minmax(0,1fr))}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.plex={
  mediaIndex:0,
  image(path){return path?`/api/plugin/plex/image?path=${encodeURIComponent(path)}`:"";},
  badge(text,kind=""){if(!text)return "";return `<span class="plex-badge ${kind}">${RackDash.escape(text)}</span>`;},
  featureCard(item){
    if(!item)return `<div class="plex-empty">Nothing to display.</div>`;
    const art=this.image(item.thumb),decisionClass=item.decision==="Transcode"?"plex-warn":"plex-good",progress=Math.max(0,Math.min(100,Number(item.progress||0)));
    return `<div class="plex-now-card"><div class="plex-art">${art?`<img src="${art}" alt="">`:""}</div><div class="plex-media-copy"><div class="plex-media-title">${RackDash.escape(item.title||"Unknown")}</div><div class="plex-media-sub">${RackDash.escape(item.subtitle||"")}</div><div class="plex-badges">${item.decision?this.badge(item.decision,decisionClass):""}${this.badge([item.resolution,item.codec].filter(Boolean).join(" "))}${this.badge(item.bitrate)}${this.badge(item.state?item.state.toUpperCase():"")}</div>${item.user?`<div class="plex-media-user">${RackDash.escape(item.user)} · ${RackDash.escape(item.player||"")}</div>`:""}${item.duration?`<div class="plex-progress"><div class="plex-progress-track"><div class="plex-progress-bar" style="width:${progress}%"></div></div><div class="plex-time"><span>${RackDash.escape(item.position||"0:00:00")}</span><span>${RackDash.escape(item.duration||"")}</span></div></div>`:""}</div></div>`;
  },
  posters(rows){if(!rows?.length)return `<div class="plex-empty">No recently added media.</div>`;return rows.slice(0,8).map(item=>`<div class="plex-poster"><div class="plex-poster-art">${item.thumb?`<img src="${this.image(item.thumb)}" alt="">`:""}</div><div class="plex-poster-title">${RackDash.escape(item.title||"Unknown")}</div><div class="plex-poster-sub">${RackDash.escape(item.subtitle||"")}</div></div>`).join("");},
  history(rows,emptyText){if(!rows?.length)return `<div class="plex-empty">${RackDash.escape(emptyText)}</div>`;return rows.slice(0,7).map(item=>`<div class="history-row">${item.thumb?`<img class="history-thumb" src="${this.image(item.thumb)}" alt="">`:`<div class="history-thumb"></div>`}<div class="history-copy"><div class="history-title">${RackDash.escape(item.title||"Unknown")}</div><div class="history-sub">${RackDash.escape(item.subtitle||"")}</div></div><div class="history-time">${RackDash.escape(item.when||item.progress_text||"")}</div></div>`).join("");},
  overview(data){const rows=[["SERVER",data.server_name],["VERSION",data.server_version],["LIBRARIES",data.library_count],["MOVIES",data.library_movies],["TV EPISODES",data.library_episodes],["MUSIC TRACKS",data.library_tracks],["DIRECT PLAY",data.direct_plays],["DIRECT STREAM",data.direct_streams]].filter(row=>row[1]!==null&&row[1]!==undefined&&String(row[1])!=="");return rows.map(([label,value],index)=>`<div class="overview-item ${index===0?"wide":""}"><span>${RackDash.escape(label)}</span><strong title="${RackDash.escape(String(value))}">${RackDash.escape(String(value))}</strong></div>`).join("")||`<div class="plex-empty">Server details unavailable.</div>`;},
  render(data,root){
    root.querySelector('[data-role="stream-count"]').textContent=data.streams||0;root.querySelector('[data-role="transcode-count"]').textContent=data.transcodes||0;root.querySelector('[data-role="bandwidth"]').textContent=`${Number(data.bandwidth_mbps||0).toFixed(1)} Mbps`;root.querySelector('[data-role="server-title"]').textContent=data.server_name||"Plex";root.querySelector('[data-role="server-subtitle"]').textContent=[data.server_platform,data.server_version?`v${data.server_version}`:""].filter(Boolean).join(" · ")||"Media server";root.querySelector('[data-role="server-version"]').textContent=data.server_version?`v${data.server_version}`:"";
    const sessions=data.sessions||[],recentPlayed=data.recent_played||[];
    if(sessions.length){this.mediaIndex%=sessions.length;root.querySelector('[data-role="feature-label"]').textContent="NOW PLAYING";root.querySelector('[data-role="feature-subtitle"]').textContent=sessions.length===1?"1 active stream":`${sessions.length} active streams`;root.querySelector('[data-role="feature-chip"]').textContent="LIVE";root.querySelector('[data-role="feature-chip"]').style.display="";root.querySelector('[data-role="feature"]').innerHTML=this.featureCard(sessions[this.mediaIndex]);}
    else{root.querySelector('[data-role="feature-label"]').textContent="RECENTLY PLAYED";root.querySelector('[data-role="feature-subtitle"]').textContent="Nothing is currently playing";root.querySelector('[data-role="feature-chip"]').style.display="none";root.querySelector('[data-role="feature"]').innerHTML=recentPlayed.length?this.featureCard(recentPlayed[0]):`<div class="plex-empty">Nothing is playing and no recent playback history was returned.</div>`;}
    root.querySelector('[data-role="overview"]').innerHTML=this.overview(data);root.querySelector('[data-role="recent-added"]').innerHTML=this.posters(data.recent_added||[]);root.querySelector('[data-role="recent-played"]').innerHTML=this.history(recentPlayed,"No recent playback history.");root.querySelector('[data-role="on-deck"]').innerHTML=this.history(data.on_deck||[],"Nothing waiting On Deck.");
  },
  onShow(root){this.mediaIndex++;}
};
'''


def _plex(path, params=None):
    if not PLEX_TOKEN:
        raise RuntimeError("Plex token not configured")
    query = dict(params or {})
    query["X-Plex-Token"] = PLEX_TOKEN
    return requests.get(f"{PLEX_URL}{path}", params=query, timeout=5, headers={"Accept":"application/xml","X-Plex-Product":"RackDash","X-Plex-Client-Identifier":"rackdash-plex-plugin"})


def _xml(path, params=None):
    response = _plex(path, params=params)
    response.raise_for_status()
    return ET.fromstring(response.content)


def _safe_xml(path, params=None):
    try:return _xml(path, params=params)
    except Exception:return None


def _fmt_ms(ms):
    return str(timedelta(seconds=max(0, int(ms or 0)//1000)))


def _relative_time(epoch):
    try:epoch=int(epoch or 0)
    except Exception:epoch=0
    if epoch<=0:return ""
    delta=max(0,int(time.time()-epoch))
    if delta<60:return "just now"
    if delta<3600:return f"{delta//60}m ago"
    if delta<86400:return f"{delta//3600}h ago"
    if delta<604800:return f"{delta//86400}d ago"
    return datetime.fromtimestamp(epoch).strftime("%b %d").replace(" 0"," ")


def _display_title(node):
    typ=node.attrib.get("type","");title=node.attrib.get("title","Unknown");subtitle=node.attrib.get("year","")
    if typ=="episode":
        show=node.attrib.get("grandparentTitle","");season=node.attrib.get("parentTitle","");episode=node.attrib.get("index","")
        if show:title=f"{show} — {title}"
        bits=[]
        if season:bits.append(season)
        if episode:bits.append(f"Episode {episode}")
        subtitle=" · ".join(bits)
    elif typ=="track":
        album=node.attrib.get("parentTitle","");artist=node.attrib.get("grandparentTitle","");subtitle=" · ".join(v for v in (artist,album) if v)
    return title,subtitle


def _media_art(node):
    return node.attrib.get("thumb") or node.attrib.get("parentThumb") or node.attrib.get("grandparentThumb") or ""


def _session(node):
    media=node.find("Media");player=node.find("Player");user=node.find("User");transcode=node.find("TranscodeSession");title,subtitle=_display_title(node)
    decision="Transcode" if transcode is not None else "Direct Play"
    if transcode is None and media is not None:
        vd=media.attrib.get("videoDecision","");ad=media.attrib.get("audioDecision","")
        if "transcode" in (vd,ad):decision="Transcode"
        elif "copy" in (vd,ad):decision="Direct Stream"
    duration=int(node.attrib.get("duration",0) or 0);position=int(node.attrib.get("viewOffset",0) or 0);bitrate=media.attrib.get("bitrate","") if media is not None else "";bitrate_mbps=round(int(bitrate)/1000,1) if str(bitrate).isdigit() else 0
    return {"title":title,"subtitle":subtitle,"user":user.attrib.get("title","Unknown") if user is not None else "Unknown","player":player.attrib.get("title","Unknown") if player is not None else "Unknown","state":player.attrib.get("state","") if player is not None else "","decision":decision,"resolution":(media.attrib.get("videoResolution","") if media is not None else "").upper(),"codec":(media.attrib.get("videoCodec","") if media is not None else "").upper(),"bitrate":f"{bitrate_mbps:.1f} Mbps" if bitrate_mbps else "","bitrate_mbps":bitrate_mbps,"progress":round(position/duration*100,1) if duration else 0,"position":_fmt_ms(position),"duration":_fmt_ms(duration),"thumb":_media_art(node)}


def _sessions():
    root=_xml("/status/sessions");return [_session(node) for node in root if node.tag in ("Video","Track","Photo")]


def _recent_added():
    root=_safe_xml("/library/recentlyAdded")
    if root is None:return []
    items=[]
    for node in list(root)[:18]:
        if node.tag not in ("Video","Directory","Track","Photo"):continue
        title,subtitle=_display_title(node);items.append({"title":title,"subtitle":subtitle,"thumb":_media_art(node),"added_at":node.attrib.get("addedAt",""),"type":node.attrib.get("type","")})
    return items


def _recent_played():
    root=_safe_xml("/status/sessions/history/all",params={"sort":"viewedAt:desc","limit":20})
    if root is None:return []
    items=[]
    for node in list(root):
        if node.tag not in ("Video","Track","Photo"):continue
        title,subtitle=_display_title(node);duration=int(node.attrib.get("duration",0) or 0);position=int(node.attrib.get("viewOffset",duration) or 0)
        items.append({"title":title,"subtitle":subtitle,"thumb":_media_art(node),"when":_relative_time(node.attrib.get("viewedAt") or node.attrib.get("lastViewedAt")),"progress":round(position/duration*100,1) if duration else 100,"position":_fmt_ms(position),"duration":_fmt_ms(duration),"decision":"","resolution":"","codec":"","bitrate":"","state":"","user":"","player":""})
        if len(items)>=12:break
    return items


def _on_deck():
    root=_safe_xml("/library/onDeck")
    if root is None:return []
    items=[]
    for node in list(root)[:12]:
        if node.tag not in ("Video","Track"):continue
        title,subtitle=_display_title(node);duration=int(node.attrib.get("duration",0) or 0);position=int(node.attrib.get("viewOffset",0) or 0);progress=round(position/duration*100,1) if duration else 0
        items.append({"title":title,"subtitle":subtitle,"thumb":_media_art(node),"progress":progress,"progress_text":f"{progress:.0f}% watched" if progress else "Up next"})
    return items


def _server_details():
    cached=_server_cache.get()
    if cached is not None:return dict(cached)
    identity=_safe_xml("/identity");sections=_safe_xml("/library/sections")
    server_name=server_version=server_platform=machine_id=""
    if identity is not None:
        server_name=identity.attrib.get("friendlyName") or identity.attrib.get("name") or "";server_version=identity.attrib.get("version","");server_platform=identity.attrib.get("platform","");machine_id=identity.attrib.get("machineIdentifier","")
    library_count=movie_total=episode_total=track_total=0
    if sections is not None:
        directories=[node for node in list(sections) if node.tag=="Directory"];library_count=len(directories)
        for directory in directories:
            key=directory.attrib.get("key","");typ=directory.attrib.get("type","")
            if not key:continue
            root=_safe_xml(f"/library/sections/{key}/all",params={"X-Plex-Container-Start":0,"X-Plex-Container-Size":0})
            total=int((root.attrib.get("totalSize") or root.attrib.get("size") or 0)) if root is not None else 0
            if typ=="movie":movie_total+=total
            elif typ=="show":
                leaf=_safe_xml(f"/library/sections/{key}/all",params={"type":4,"X-Plex-Container-Start":0,"X-Plex-Container-Size":0})
                if leaf is not None:episode_total+=int(leaf.attrib.get("totalSize") or leaf.attrib.get("size") or 0)
            elif typ=="artist":
                tracks=_safe_xml(f"/library/sections/{key}/all",params={"type":10,"X-Plex-Container-Start":0,"X-Plex-Container-Size":0})
                if tracks is not None:track_total+=int(tracks.attrib.get("totalSize") or tracks.attrib.get("size") or 0)
    result={"server_name":server_name,"server_version":server_version,"server_platform":server_platform,"machine_id":machine_id,"library_count":library_count,"library_movies":movie_total,"library_episodes":episode_total,"library_tracks":track_total};_server_cache.set(result);return dict(result)


def _detail_data():
    cached=_detail_cache.get()
    if cached is not None:return dict(cached)
    result={"recent_added":_recent_added(),"recent_played":_recent_played(),"on_deck":_on_deck()};_detail_cache.set(result);return dict(result)


def get_data():
    sessions=_sessions();details=_detail_data();server=_server_details();direct_plays=sum(1 for i in sessions if i["decision"]=="Direct Play");direct_streams=sum(1 for i in sessions if i["decision"]=="Direct Stream");transcodes=sum(1 for i in sessions if i["decision"]=="Transcode");bandwidth=sum(float(i.get("bitrate_mbps") or 0) for i in sessions)
    data={"sessions":sessions,"streams":len(sessions),"transcodes":transcodes,"direct_plays":direct_plays,"direct_streams":direct_streams,"bandwidth_mbps":round(bandwidth,1)};data.update(details);data.update(server);return data


def register_routes(app):
    @app.get("/api/plugin/plex/image")
    def plex_image():
        from flask import request
        path=request.args.get("path","")
        if not path.startswith("/"):return app.response_class(status=404)
        try:
            response=_plex(path);response.raise_for_status();result=app.response_class(response.content,content_type=response.headers.get("Content-Type","image/jpeg"));result.headers["Cache-Control"]="private, max-age=3600";return result
        except Exception:return app.response_class(status=404)


def get_i2c_data():
    try:data=get_data()
    except Exception:return {"title":"Plex","lines":["Server unavailable"]}
    sessions=data.get("sessions") or []
    if sessions:
        item=sessions[0];return {"title":"Plex","lines":[f"{data.get('streams',0)} stream(s)",str(item.get("title") or "")[:18],f"{item.get('decision','')[:10]} {item.get('progress',0):.0f}%"]}
    recent=data.get("recent_played") or []
    return {"title":"Plex","lines":["Idle","Last: "+str(recent[0].get("title") if recent else "No recent plays")[:13],f"{data.get('library_count',0)} libraries"]}
