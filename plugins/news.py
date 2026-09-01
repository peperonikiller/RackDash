from __future__ import annotations

import html
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

import requests

from _shared import TTLCache

PLUGIN_ID = "news"
PLUGIN_NAME = "News"
PLUGIN_VERSION = "1.0.1"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/news.py"
PLUGIN_MIN_RACKDASH = "3.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 70
PLUGIN_REFRESH_SECONDS = 120
PLUGIN_ACCENT = "#7bb7ff"
PLUGIN_ICON = "NEWS"
PLUGIN_PUBLIC_ERROR = "News feed unavailable"

PLUGIN_CONFIG = [
    {"key":"NEWS_RSS_URL","label":"RSS / Atom Feed URL","type":"text","default":"","required":True,"help":"Full URL to an RSS 2.0 or Atom feed."},
    {"key":"NEWS_MAX_ITEMS","label":"Maximum Articles","type":"number","default":"10","min":3,"max":30,"required":False,"help":"Maximum number of stories shown on the News tab."},
    {"key":"NEWS_SHOW_SUMMARY","label":"Show Article Summaries","type":"checkbox","default":"true","required":False},
    {"key":"NEWS_SHOW_IMAGES","label":"Show Feed Images","type":"checkbox","default":"true","required":False,"help":"Uses image/media URLs supplied by the feed when available."},
    {"key":"NEWS_SOURCE_LABEL","label":"Source Label Override","type":"text","default":"","required":False,"help":"Optional display name. Leave blank to use the feed title."},
    {"key":"NEWS_REQUEST_TIMEOUT","label":"Request Timeout","type":"number","default":"8","min":2,"max":30,"required":False,"help":"Seconds RackDash waits for the feed server."},
]

_cache = TTLCache(90)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r'''<img[^>]+src=["']([^"']+)["']''', re.I)

def _env_bool(key, default):
    return str(os.getenv(key, "true" if default else "false") or "").strip().lower() in {"1","true","yes","on"}

def _strip_html(value, limit=500):
    value = html.unescape(str(value or ""))
    value = _TAG_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value if len(value) <= limit else value[:limit-1].rstrip() + "…"

def _first_text(node, names):
    names = {n.lower() for n in names}
    for child in list(node):
        if child.tag.rsplit("}",1)[-1].lower() in names and child.text:
            return child.text.strip()
    return ""

def _parse_timestamp(value):
    value = str(value or "").strip()
    if not value: return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None

def _link_from_node(node, base_url):
    for child in list(node):
        if child.tag.rsplit("}",1)[-1].lower() != "link": continue
        href = child.attrib.get("href")
        rel = str(child.attrib.get("rel", "alternate")).lower()
        if href and rel in {"alternate", ""}: return urljoin(base_url, href)
        if child.text and child.text.strip(): return urljoin(base_url, child.text.strip())
    return ""

def _image_from_node(node, base_url, description_html=""):
    for child in list(node):
        tag = child.tag.rsplit("}",1)[-1].lower()
        attrs = {str(k).lower(): str(v) for k,v in child.attrib.items()}
        url = attrs.get("url") or attrs.get("href") or ""
        media_type = attrs.get("type", "").lower()
        medium = attrs.get("medium", "").lower()
        if tag in {"content","thumbnail","enclosure"} and url:
            if tag == "thumbnail" or medium == "image" or media_type.startswith("image/") or re.search(r"\.(?:jpe?g|png|webp|gif)(?:\?|$)", url, re.I):
                return urljoin(base_url, url)
    m = _IMG_RE.search(description_html or "")
    return urljoin(base_url, m.group(1)) if m else ""

def _parse_feed(xml_bytes, base_url):
    root = ET.fromstring(xml_bytes)
    root_name = root.tag.rsplit("}",1)[-1].lower()
    if root_name == "rss" or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None: raise ValueError("RSS feed does not contain a channel.")
        title = _first_text(channel,["title"])
        description = _strip_html(_first_text(channel,["description"]),220)
        homepage = _first_text(channel,["link"])
        nodes = [c for c in list(channel) if c.tag.rsplit("}",1)[-1].lower()=="item"]
    elif root_name == "feed":
        title = _first_text(root,["title"])
        description = _strip_html(_first_text(root,["subtitle","tagline"]),220)
        homepage = _link_from_node(root,base_url)
        nodes = [c for c in list(root) if c.tag.rsplit("}",1)[-1].lower()=="entry"]
    else:
        raise ValueError("Unsupported feed format. Use RSS 2.0 or Atom.")

    max_items = max(3,min(30,int(float(os.getenv("NEWS_MAX_ITEMS","10") or 10))))
    show_summary = _env_bool("NEWS_SHOW_SUMMARY",True)
    show_images = _env_bool("NEWS_SHOW_IMAGES",True)
    items=[]
    for node in nodes[:max_items*2]:
        title_text = _strip_html(_first_text(node,["title"]),220)
        if not title_text: continue
        raw_summary = _first_text(node,["description","summary","content","encoded"])
        items.append({
            "title": title_text,
            "summary": _strip_html(raw_summary,420) if show_summary else "",
            "link": _link_from_node(node,base_url),
            "image": _image_from_node(node,base_url,raw_summary) if show_images else "",
            "author": _strip_html(_first_text(node,["author","creator"]),100),
            "published": _parse_timestamp(_first_text(node,["pubdate","published","updated","date"])),
        })
        if len(items) >= max_items: break
    return {"title":title or "News","description":description,"homepage":urljoin(base_url,homepage) if homepage else "","items":items}

def _fetch_feed():
    url = os.getenv("NEWS_RSS_URL","").strip()
    if not url:
        return {"configured":False,"source":"News","description":"Configure an RSS or Atom feed in Admin.","homepage":"","items":[],"fetched_at":int(time.time())}
    timeout = max(2.0,min(30.0,float(os.getenv("NEWS_REQUEST_TIMEOUT","8") or 8)))
    response = requests.get(url,headers={"Accept":"application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5","User-Agent":"RackDash-News/1.0.0"},timeout=timeout)
    response.raise_for_status()
    feed = _parse_feed(response.content,response.url or url)
    override = os.getenv("NEWS_SOURCE_LABEL","").strip()
    return {"configured":True,"source":override or feed["title"],"description":feed["description"],"homepage":feed["homepage"],"items":feed["items"],"fetched_at":int(time.time())}

def get_data():
    cached = _cache.get()
    if cached is not None: return cached
    data = _fetch_feed(); _cache.set(data); return data

PLUGIN_HTML = r'''
<div class="news-shell">
  <section class="surface news-hero">
    <div><span class="eyebrow">RSS NEWS</span><h1 data-role="source">News</h1><div class="muted news-description" data-role="description">Configure an RSS feed in Admin.</div></div>
    <div class="news-meta"><span class="news-status" data-role="status">WAITING</span><strong data-role="count">0</strong><small>STORIES</small></div>
  </section>
  <section class="news-grid" data-role="grid"><article class="surface news-empty"><strong>NO NEWS YET</strong><span class="muted">Configure an RSS or Atom URL from Admin.</span></article></section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-news{--news:#7bb7ff;--news-line:rgba(123,183,255,.22)}
.plugin-news .news-shell{display:grid;gap:var(--gap)}
.plugin-news .news-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;border-left:3px solid var(--news);background:radial-gradient(circle at 9% 30%,rgba(123,183,255,.10),transparent 32%),linear-gradient(115deg,rgba(123,183,255,.04),rgba(255,255,255,.005))}
.plugin-news .news-hero h1{margin:.1rem 0 .15rem;font-size:clamp(1.45rem,3vw,2.5rem);line-height:1}.plugin-news .news-description{max-width:62rem;font-size:clamp(.62rem,1vw,.82rem)}
.plugin-news .news-meta{min-width:8rem;text-align:right;display:grid;justify-items:end;gap:.08rem}.plugin-news .news-meta strong{font-size:clamp(1.5rem,3vw,2.35rem);line-height:1}.plugin-news .news-meta small{color:var(--muted);font-size:.48rem;letter-spacing:.08em;font-weight:850}.plugin-news .news-status{padding:.2rem .38rem;border:1px solid var(--news-line);border-radius:.3rem;color:var(--news);font-size:.48rem;font-weight:900;letter-spacing:.07em}
.plugin-news .news-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--gap);align-items:start}.plugin-news .news-card{min-width:0;display:grid;grid-template-columns:minmax(0,1fr);padding:0;overflow:hidden;border-color:rgba(123,183,255,.12)}.plugin-news .news-card.has-image{grid-template-columns:minmax(8.5rem,28%) minmax(0,1fr)}.plugin-news .news-image{width:100%;height:100%;min-height:8rem;object-fit:cover;background:#071016}.plugin-news .news-body{min-width:0;padding:.62rem .68rem;display:grid;gap:.3rem;align-content:start}.plugin-news .news-kicker{display:flex;gap:.35rem;flex-wrap:wrap;color:#81919a;font-size:.44rem;font-weight:800;letter-spacing:.05em;text-transform:uppercase}.plugin-news .news-card h2{margin:0;font-size:clamp(.82rem,1.25vw,1.08rem);line-height:1.16}.plugin-news .news-card h2 a{color:var(--text);text-decoration:none}.plugin-news .news-card h2 a:hover{color:var(--news)}.plugin-news .news-summary{margin:0;color:var(--muted);font-size:clamp(.54rem,.82vw,.68rem);line-height:1.42;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}.plugin-news .news-open{justify-self:start;color:var(--news);text-decoration:none;font-size:.48rem;font-weight:900}.plugin-news .news-empty{grid-column:1/-1;min-height:10rem;display:grid;place-content:center;text-align:center;gap:.25rem}
@media(max-width:900px){.plugin-news .news-grid{grid-template-columns:1fr}}@media(max-width:640px){.plugin-news .news-card.has-image{grid-template-columns:7rem minmax(0,1fr)}}
'''

PLUGIN_JS = r'''
(function(){
  const root=document.querySelector(".plugin-news"); if(!root)return;
  function relativeTime(ts){const v=Number(ts||0);if(!v)return "";const s=Math.max(0,Math.floor(Date.now()/1000-v));if(s<60)return "just now";if(s<3600)return `${Math.floor(s/60)}m ago`;if(s<86400)return `${Math.floor(s/3600)}h ago`;if(s<604800)return `${Math.floor(s/86400)}d ago`;return new Date(v*1000).toLocaleDateString()}
  function articleHtml(item,index){const title=RackDash.escape(item.title||"Untitled"),summary=RackDash.escape(item.summary||""),author=RackDash.escape(item.author||""),published=RackDash.escape(relativeTime(item.published)),link=String(item.link||"").trim(),image=String(item.image||"").trim();const titleHtml=link?`<a href="${RackDash.escape(link)}" target="_blank" rel="noopener noreferrer">${title}</a>`:title;return `<article class="surface news-card ${image?"has-image":""}">${image?`<img class="news-image" src="${RackDash.escape(image)}" alt="" loading="lazy" referrerpolicy="no-referrer">`:""}<div class="news-body"><div class="news-kicker"><span>#${String(index+1).padStart(2,"0")}</span>${published?`<span>${published}</span>`:""}${author?`<span>${author}</span>`:""}</div><h2>${titleHtml}</h2>${summary?`<p class="news-summary">${summary}</p>`:""}${link?`<a class="news-open" href="${RackDash.escape(link)}" target="_blank" rel="noopener noreferrer">OPEN ARTICLE ↗</a>`:""}</div></article>`}
  function render(data){const source=root.querySelector('[data-role="source"]'),description=root.querySelector('[data-role="description"]'),status=root.querySelector('[data-role="status"]'),count=root.querySelector('[data-role="count"]'),grid=root.querySelector('[data-role="grid"]');if(source)source.textContent=data.source||"News";if(description)description.textContent=data.description||(data.configured?"Latest stories from the configured feed.":"Configure an RSS or Atom feed in Admin.");const items=Array.isArray(data.items)?data.items:[];if(count)count.textContent=String(items.length);if(status)status.textContent=data.configured?"LIVE":"SETUP";if(!grid)return;if(!items.length){grid.innerHTML=`<article class="surface news-empty"><strong>${data.configured?"NO STORIES RETURNED":"RSS FEED NOT CONFIGURED"}</strong><span class="muted">${data.configured?"The feed did not return any readable stories.":"Open Admin → Plugins → News → Settings to add a feed URL."}</span></article>`;return}grid.innerHTML=items.map(articleHtml).join("")}
  window.RackDashPluginRender=window.RackDashPluginRender||{};window.RackDashPluginRender.news=render;
})();
'''
