from __future__ import annotations

import json
import os
import socket
import struct
import time
from dataclasses import dataclass

from _shared import TTLCache


PLUGIN_ID = "serverspy"
PLUGIN_NAME = "ServerSpy"
PLUGIN_VERSION = "1.0.0"
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/serverspy.py"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network", "i2c"]
PLUGIN_GITHUB = "https://github.com/peperonikiller/RackDash"
PLUGIN_ORDER = 85
PLUGIN_REFRESH_SECONDS = 30
PLUGIN_ACCENT = "#65c7ff"
PLUGIN_ICON = "GAME"
PLUGIN_PUBLIC_ERROR = "Game server unavailable"

GAME_PRESETS = {
    "cs2": ("Counter-Strike 2", "a2s", 27015),
    "csgo": ("Counter-Strike: Global Offensive", "a2s", 27015),
    "css": ("Counter-Strike: Source", "a2s", 27015),
    "tf2": ("Team Fortress 2", "a2s", 27015),
    "gmod": ("Garry's Mod", "a2s", 27015),
    "l4d2": ("Left 4 Dead 2", "a2s", 27015),
    "dayz": ("DayZ", "a2s", 2302),
    "rust": ("Rust", "a2s", 28015),
    "ark": ("ARK: Survival Evolved / Ascended", "a2s", 27015),
    "7dtd": ("7 Days to Die", "a2s", 26900),
    "valheim": ("Valheim", "a2s", 2457),
    "unturned": ("Unturned", "a2s", 27015),
    "project_zomboid": ("Project Zomboid", "a2s", 16261),
    "squad": ("Squad", "a2s", 27165),
    "insurgency_sandstorm": ("Insurgency: Sandstorm", "a2s", 27131),
    "conan_exiles": ("Conan Exiles", "a2s", 27015),
    "palworld": ("Palworld", "a2s", 8211),
    "source_generic": ("Steam / Source / A2S (Generic)", "a2s", 27015),
    "minecraft_java": ("Minecraft: Java Edition", "mc_java", 25565),
    "minecraft_bedrock": ("Minecraft: Bedrock Edition", "mc_bedrock", 19132),
}

PLUGIN_CONFIG = [
    {
        "key": "SERVERSPY_GAME",
        "label": "Game Server",
        "type": "select",
        "default": "cs2",
        "required": True,
        "options": [
            {"value": key, "label": value[0]}
            for key, value in GAME_PRESETS.items()
        ],
        "help": "Select the server type. Use Generic Steam/A2S for other compatible Steam game servers.",
    },
    {
        "key": "SERVERSPY_HOST",
        "label": "Server IP / Hostname",
        "type": "text",
        "default": "",
        "required": True,
        "placeholder": "192.168.1.50",
    },
    {
        "key": "SERVERSPY_PORT",
        "label": "Query Port",
        "type": "number",
        "default": "27015",
        "required": True,
        "min": 1,
        "max": 65535,
        "help": "The query/status port. Some games use a different query port than gameplay port.",
    },
    {
        "key": "SERVERSPY_TIMEOUT",
        "label": "Query Timeout",
        "type": "number",
        "default": "3",
        "required": False,
        "min": 1,
        "max": 10,
    },
]

PLUGIN_HTML = r'''
<div class="serverspy-shell">
  <section class="serverspy-hero surface">
    <div>
      <span class="eyebrow" data-role="game-label">SERVERSPY</span>
      <h1 data-role="server-name">Checking server...</h1>
      <div class="muted" data-role="address"></div>
    </div>
    <div class="serverspy-status" data-role="status">--</div>
  </section>

  <section class="serverspy-metrics">
    <article class="surface metric-card"><span>PLAYERS</span><strong data-role="players">--</strong><small data-role="bots"></small></article>
    <article class="surface metric-card"><span>PING</span><strong data-role="ping">--</strong><small>query round trip</small></article>
    <article class="surface metric-card"><span>MAP</span><strong data-role="map">--</strong><small data-role="folder"></small></article>
    <article class="surface metric-card"><span>SECURITY</span><strong data-role="security">--</strong><small data-role="visibility"></small></article>
  </section>

  <section class="serverspy-grid">
    <article class="surface serverspy-info"><div class="section-label">SERVER INFO</div><div class="info-grid" data-role="info"></div></article>
    <article class="surface serverspy-players"><div class="section-label">PLAYERS</div><div class="player-list" data-role="player-list"></div></article>
    <article class="surface serverspy-rules"><div class="section-label">SERVER RULES / DETAILS</div><div class="rule-list" data-role="rules"></div></article>
  </section>
</div>
'''

PLUGIN_CSS = r'''
.plugin-serverspy .serverspy-shell{display:grid;gap:var(--gap)}
.plugin-serverspy .serverspy-hero{display:flex;align-items:center;justify-content:space-between;gap:1rem;border-left:2px solid rgba(101,199,255,.62)}
.plugin-serverspy .serverspy-hero h1{margin:.22rem 0 .14rem;font-size:clamp(1.35rem,3vw,2.6rem);line-height:1}
.plugin-serverspy .serverspy-status{padding:.46rem .72rem;border:1px solid var(--border);border-radius:.45rem;font-size:.68rem;font-weight:950;letter-spacing:.04em}
.plugin-serverspy .serverspy-status.online{color:#6be88d;border-color:rgba(107,232,141,.5);background:rgba(107,232,141,.055)}
.plugin-serverspy .serverspy-status.offline{color:#ff737d;border-color:rgba(255,115,125,.48);background:rgba(255,115,125,.05)}
.plugin-serverspy .serverspy-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--gap)}
.plugin-serverspy .metric-card span{display:block;font-size:.5rem;color:var(--muted);font-weight:850}
.plugin-serverspy .metric-card strong{display:block;margin-top:.14rem;font-size:clamp(.95rem,2vw,1.5rem);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-serverspy .metric-card small{display:block;margin-top:.08rem;font-size:.48rem;color:var(--muted)}
.plugin-serverspy .serverspy-grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);grid-template-areas:"info players" "rules rules";gap:var(--gap);align-items:start}
.plugin-serverspy .serverspy-info{grid-area:info}.plugin-serverspy .serverspy-players{grid-area:players}.plugin-serverspy .serverspy-rules{grid-area:rules}
.plugin-serverspy .info-grid{margin-top:.5rem;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.35rem}
.plugin-serverspy .info-item,.plugin-serverspy .rule-item{padding:.4rem .46rem;border:1px solid var(--border);border-radius:.38rem;background:rgba(255,255,255,.014);min-width:0}
.plugin-serverspy .info-item span,.plugin-serverspy .rule-item span{display:block;font-size:.47rem;color:var(--muted)}
.plugin-serverspy .info-item strong,.plugin-serverspy .rule-item strong{display:block;margin-top:.12rem;font-size:.61rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-serverspy .player-list{margin-top:.5rem;display:grid;gap:.28rem}
.plugin-serverspy .player-row{display:grid;grid-template-columns:2rem minmax(0,1fr) auto auto;gap:.55rem;align-items:center;min-height:1.8rem;padding:.3rem .42rem;border-radius:.36rem;background:rgba(255,255,255,.015);border:1px solid rgba(255,255,255,.025)}
.plugin-serverspy .player-index{display:grid;place-items:center;width:1.45rem;height:1.45rem;border:1px solid var(--border);border-radius:.3rem;font-size:.55rem;font-weight:900}
.plugin-serverspy .player-name{font-size:.63rem;font-weight:850;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.plugin-serverspy .player-score{font-size:.55rem;color:#f1c55e;font-weight:900}.plugin-serverspy .player-time{font-size:.5rem;color:var(--muted)}
.plugin-serverspy .rule-list{margin-top:.5rem;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.28rem}
.plugin-serverspy .empty-state{display:grid;place-items:center;min-height:6rem;color:var(--muted);font-size:.58rem;border:1px dashed var(--border);border-radius:.4rem}
@media(max-width:760px){.plugin-serverspy .serverspy-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.plugin-serverspy .serverspy-grid{grid-template-columns:1fr;grid-template-areas:"info" "players" "rules"}.plugin-serverspy .rule-list{grid-template-columns:repeat(2,minmax(0,1fr))}}
'''

PLUGIN_JS = r'''
window.RackDashPlugins.serverspy={
  duration(seconds){seconds=Math.max(0,Number(seconds||0));const h=Math.floor(seconds/3600),m=Math.floor((seconds%3600)/60);return h?`${h}h ${m}m`:`${m}m`},
  info(data){const rows=[["GAME",data.game],["PROTOCOL",data.protocol_label],["VERSION",data.version],["APP ID",data.app_id],["GAME PORT",data.game_port],["QUERY PORT",data.query_port],["SERVER TYPE",data.server_type],["ENVIRONMENT",data.environment],["KEYWORDS",data.keywords],["GAME ID",data.game_id]].filter(r=>r[1]!==null&&r[1]!==undefined&&String(r[1])!=="");return rows.map(([l,v])=>`<div class="info-item"><span>${RackDash.escape(l)}</span><strong>${RackDash.escape(String(v))}</strong></div>`).join("")||`<div class="empty-state">No additional server information.</div>`},
  players(rows){if(!rows?.length)return `<div class="empty-state">No player details returned by this server.</div>`;return rows.map((p,i)=>`<div class="player-row"><div class="player-index">${i+1}</div><div class="player-name">${RackDash.escape(p.name||"Unnamed")}</div><div class="player-score">${p.score==null?"":`${RackDash.escape(String(p.score))} pts`}</div><div class="player-time">${p.duration==null?"":this.duration(p.duration)}</div></div>`).join("")},
  rules(rules){const e=Object.entries(rules||{});if(!e.length)return `<div class="empty-state">No rules/details returned by this server.</div>`;return e.slice(0,60).map(([k,v])=>`<div class="rule-item"><span>${RackDash.escape(k)}</span><strong>${RackDash.escape(String(v))}</strong></div>`).join("")},
  render(data,root){
    root.querySelector('[data-role="game-label"]').textContent=data.game_label||"SERVERSPY";
    root.querySelector('[data-role="server-name"]').textContent=data.name||"Game Server";
    root.querySelector('[data-role="address"]').textContent=`${data.host||""}:${data.query_port||""}`;
    const status=root.querySelector('[data-role="status"]');status.textContent=data.online?"ONLINE":"OFFLINE";status.className=`serverspy-status ${data.online?"online":"offline"}`;
    root.querySelector('[data-role="players"]').textContent=`${data.players??0} / ${data.max_players??0}`;
    root.querySelector('[data-role="bots"]').textContent=data.bots?`${data.bots} bot${data.bots===1?"":"s"}`:"";
    root.querySelector('[data-role="ping"]').textContent=data.ping_ms==null?"--":`${Math.round(data.ping_ms)} ms`;
    root.querySelector('[data-role="map"]').textContent=data.map||"--";
    root.querySelector('[data-role="folder"]').textContent=data.folder||"";
    root.querySelector('[data-role="security"]').textContent=data.vac===true?"VAC":data.vac===false?"NO VAC":data.secure===true?"SECURE":data.secure===false?"OPEN":"--";
    root.querySelector('[data-role="visibility"]').textContent=data.password?"Password protected":"Public";
    root.querySelector('[data-role="info"]').innerHTML=this.info(data);
    root.querySelector('[data-role="player-list"]').innerHTML=this.players(data.player_list);
    root.querySelector('[data-role="rules"]').innerHTML=this.rules(data.rules);
  }
};
'''

_cache = TTLCache(20)

def _config():
    key=os.getenv("SERVERSPY_GAME","cs2").strip()
    if key not in GAME_PRESETS:key="source_generic"
    label,protocol,default_port=GAME_PRESETS[key]
    host=os.getenv("SERVERSPY_HOST","").strip()
    if not host:raise RuntimeError("Server IP / Hostname is required")
    try:port=int(os.getenv("SERVERSPY_PORT","") or default_port)
    except ValueError:port=default_port
    try:timeout=max(1.0,min(10.0,float(os.getenv("SERVERSPY_TIMEOUT","3") or 3)))
    except ValueError:timeout=3.0
    return {"game_key":key,"game_label":label,"protocol":protocol,"host":host,"port":port,"timeout":timeout}

def _cstring(data,offset):
    end=data.find(b"\x00",offset)
    if end<0:raise ValueError("Malformed string")
    return data[offset:end].decode("utf-8","replace"),end+1

def _u8(data,o):return data[o],o+1
def _u16(data,o):return struct.unpack_from("<H",data,o)[0],o+2
def _i32(data,o):return struct.unpack_from("<i",data,o)[0],o+4
def _u64(data,o):return struct.unpack_from("<Q",data,o)[0],o+8
def _f32(data,o):return struct.unpack_from("<f",data,o)[0],o+4

@dataclass
class _UdpResult:
    payload: bytes
    ping_ms: float

def _udp_request(host,port,payload,timeout):
    info=socket.getaddrinfo(host,port,type=socket.SOCK_DGRAM)[0]
    family=info[0];addr=info[-1]
    with socket.socket(family,socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        start=time.perf_counter();sock.sendto(payload,addr);response,_=sock.recvfrom(65535)
        return _UdpResult(response,(time.perf_counter()-start)*1000.0)

A2S_HEADER=b"\xff\xff\xff\xff"
A2S_INFO_REQUEST=A2S_HEADER+b"TSource Engine Query\x00"

def _a2s_payload(result):
    data=result.payload
    if data[:4]==A2S_HEADER:return data[4:]
    raise ValueError("Unsupported A2S packet")

def _a2s_info(host,port,timeout):
    result=_udp_request(host,port,A2S_INFO_REQUEST,timeout)
    data=_a2s_payload(result)
    if not data or data[0]!=0x49:raise ValueError("Unexpected A2S_INFO response")
    o=1
    protocol,o=_u8(data,o);name,o=_cstring(data,o);map_name,o=_cstring(data,o);folder,o=_cstring(data,o);game,o=_cstring(data,o)
    app_id,o=_u16(data,o);players,o=_u8(data,o);max_players,o=_u8(data,o);bots,o=_u8(data,o)
    server_type,o=_u8(data,o);environment,o=_u8(data,o);visibility,o=_u8(data,o);vac,o=_u8(data,o);version,o=_cstring(data,o)
    d={"online":True,"ping_ms":result.ping_ms,"protocol_version":protocol,"name":name,"map":map_name,"folder":folder,"game":game,"app_id":app_id,"players":players,"max_players":max_players,"bots":bots,"server_type":{100:"Dedicated",108:"Listen",112:"Proxy"}.get(server_type,chr(server_type)),"environment":{108:"Linux",119:"Windows",109:"macOS",111:"macOS"}.get(environment,chr(environment)),"password":bool(visibility),"vac":bool(vac),"version":version}
    if o<len(data):
        edf=data[o];o+=1
        if edf&0x80 and o+2<=len(data):d["game_port"],o=_u16(data,o)
        if edf&0x10 and o+8<=len(data):d["steam_id"],o=_u64(data,o)
        if edf&0x40:
            if o+2<=len(data):d["spectator_port"],o=_u16(data,o)
            if o<len(data):d["spectator_name"],o=_cstring(data,o)
        if edf&0x20 and o<len(data):d["keywords"],o=_cstring(data,o)
        if edf&0x01 and o+8<=len(data):d["game_id"],o=_u64(data,o)
    return d

def _a2s_challenge(host,port,timeout,kind):
    result=_udp_request(host,port,A2S_HEADER+bytes([kind])+b"\xff\xff\xff\xff",timeout)
    data=_a2s_payload(result)
    return data[1:5] if data and data[0]==0x41 and len(data)>=5 else None

def _a2s_players(host,port,timeout):
    try:
        ch=_a2s_challenge(host,port,timeout,0x55)
        if not ch:return []
        data=_a2s_payload(_udp_request(host,port,A2S_HEADER+b"U"+ch,timeout))
        if not data or data[0]!=0x44:return []
        count=data[1];o=2;rows=[]
        for _ in range(count):
            if o>=len(data):break
            _,o=_u8(data,o);name,o=_cstring(data,o);score,o=_i32(data,o);duration,o=_f32(data,o)
            rows.append({"name":name,"score":score,"duration":max(0,int(duration))})
        return sorted(rows,key=lambda r:(-r["score"],r["name"].lower()))
    except Exception:return []

def _a2s_rules(host,port,timeout):
    try:
        ch=_a2s_challenge(host,port,timeout,0x56)
        if not ch:return {}
        data=_a2s_payload(_udp_request(host,port,A2S_HEADER+b"V"+ch,timeout))
        if not data or data[0]!=0x45:return {}
        count=struct.unpack_from("<H",data,1)[0];o=3;rules={}
        for _ in range(count):
            if o>=len(data):break
            k,o=_cstring(data,o);v,o=_cstring(data,o);rules[k]=v
        return rules
    except Exception:return {}

def _query_a2s(c):
    d=_a2s_info(c["host"],c["port"],c["timeout"])
    d.update({"protocol_label":"Steam A2S","player_list":_a2s_players(c["host"],c["port"],c["timeout"]),"rules":_a2s_rules(c["host"],c["port"],c["timeout"]),"secure":d.get("vac")})
    return d

def _mc_varint(value):
    out=bytearray();value&=0xffffffff
    while True:
        b=value&0x7f;value>>=7
        if value:b|=0x80
        out.append(b)
        if not value:return bytes(out)

def _mc_read_varint(sock):
    value=0;pos=0
    while True:
        raw=sock.recv(1)
        if not raw:raise ValueError("Minecraft connection closed")
        b=raw[0];value|=(b&0x7f)<<pos
        if not b&0x80:return value
        pos+=7
        if pos>=35:raise ValueError("VarInt too large")

def _mc_read_exact(sock,n):
    out=bytearray()
    while len(out)<n:
        part=sock.recv(n-len(out))
        if not part:raise ValueError("Minecraft connection closed")
        out.extend(part)
    return bytes(out)

def _query_minecraft_java(c):
    with socket.create_connection((c["host"],c["port"]),timeout=c["timeout"]) as sock:
        hb=c["host"].encode();handshake=_mc_varint(0)+_mc_varint(47)+_mc_varint(len(hb))+hb+struct.pack(">H",c["port"])+_mc_varint(1)
        sock.sendall(_mc_varint(len(handshake))+handshake)
        start=time.perf_counter();sock.sendall(b"\x01\x00")
        _mc_read_varint(sock);packet_id=_mc_read_varint(sock)
        if packet_id!=0:raise ValueError("Unexpected Minecraft status response")
        length=_mc_read_varint(sock);status=json.loads(_mc_read_exact(sock,length).decode())
        ping_ms=(time.perf_counter()-start)*1000.0
    players=status.get("players") or {};version=status.get("version") or {};desc=status.get("description")
    name=desc.get("text","Minecraft Server") if isinstance(desc,dict) else str(desc or "Minecraft Server")
    sample=players.get("sample") or []
    return {"online":True,"name":name,"game":"Minecraft","map":"","players":int(players.get("online",0) or 0),"max_players":int(players.get("max",0) or 0),"bots":0,"ping_ms":ping_ms,"version":version.get("name",""),"protocol_version":version.get("protocol"),"protocol_label":"Minecraft Java Status","player_list":[{"name":p.get("name","Player"),"score":None,"duration":None} for p in sample],"rules":{"motd":name,"version":version.get("name",""),"protocol":version.get("protocol","")},"password":False,"vac":None,"secure":None}

BEDROCK_MAGIC=bytes.fromhex("00ffff00fefefefefdfdfdfd12345678")

def _query_minecraft_bedrock(c):
    packet=b"\x01"+struct.pack(">Q",int(time.time()*1000))+BEDROCK_MAGIC+struct.pack(">Q",0x123456789abcdef)
    result=_udp_request(c["host"],c["port"],packet,c["timeout"]);data=result.payload
    if not data or data[0]!=0x1c:raise ValueError("Unexpected Bedrock response")
    o=1+8+8+16;length=struct.unpack_from(">H",data,o)[0];o+=2;fields=data[o:o+length].decode("utf-8","replace").split(";")
    name=fields[1] if len(fields)>1 else "Minecraft Bedrock";protocol=fields[2] if len(fields)>2 else "";version=fields[3] if len(fields)>3 else ""
    players=int(fields[4]) if len(fields)>4 and fields[4].isdigit() else 0;max_players=int(fields[5]) if len(fields)>5 and fields[5].isdigit() else 0
    sub=fields[7] if len(fields)>7 else "";mode=fields[8] if len(fields)>8 else ""
    return {"online":True,"name":name,"game":"Minecraft Bedrock","map":sub,"players":players,"max_players":max_players,"bots":0,"ping_ms":result.ping_ms,"version":version,"protocol_version":protocol,"protocol_label":"Minecraft Bedrock RakNet","player_list":[],"rules":{"motd":name,"sub_motd":sub,"game_mode":mode,"version":version,"protocol":protocol},"password":False,"vac":None,"secure":None}

def get_data():
    cached=_cache.get()
    if cached:return cached
    c=_config()
    if c["protocol"]=="a2s":d=_query_a2s(c)
    elif c["protocol"]=="mc_java":d=_query_minecraft_java(c)
    elif c["protocol"]=="mc_bedrock":d=_query_minecraft_bedrock(c)
    else:raise RuntimeError("Unsupported ServerSpy protocol")
    d.update({"game_key":c["game_key"],"game_label":c["game_label"],"host":c["host"],"query_port":c["port"]})
    return _cache.set(d)

def get_i2c_data():
    try:d=get_data()
    except Exception:return {"title":"ServerSpy","lines":["Server offline"]}
    ping="--" if d.get("ping_ms") is None else f"{int(round(float(d['ping_ms'])))}ms"
    return {"title":"ServerSpy","lines":[str(d.get("name") or d.get("game_label") or "")[:18],f"Ping {ping}  P {d.get('players',0)}/{d.get('max_players',0)}",f"Map {str(d.get('map') or 'No map')[:18]}"]}
