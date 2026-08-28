from __future__ import annotations

import bz2
import os
import socket
import struct
import time
import zlib

from _shared import TTLCache


PLUGIN_ID = "serverspy"
PLUGIN_NAME = "ServerSpy"
PLUGIN_VERSION = "1.1.1"
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
PLUGIN_PUBLIC_ERROR = "Source game server unavailable"

GAME_PRESETS = {
    "cs2": ("Counter-Strike 2", 27015),
    "csgo": ("Counter-Strike: Global Offensive", 27015),
    "css": ("Counter-Strike: Source", 27015),
    "tf2": ("Team Fortress 2", 27015),
    "gmod": ("Garry's Mod", 27015),
    "l4d": ("Left 4 Dead", 27015),
    "l4d2": ("Left 4 Dead 2", 27015),
    "dods": ("Day of Defeat: Source", 27015),
    "hl2dm": ("Half-Life 2: Deathmatch", 27015),
    "portal2": ("Portal 2", 27015),
    "alien_swarm": ("Alien Swarm", 27015),
    "black_mesa": ("Black Mesa", 27015),
    "synergy": ("Synergy", 27015),
    "insurgency": ("Insurgency (2014)", 27015),
    "fistful_of_frags": ("Fistful of Frags", 27015),
    "source_generic": ("Source / Source 2 (Generic A2S)", 27015),
}

PLUGIN_CONFIG = [
    {
        "key": "SERVERSPY_GAME",
        "label": "Source Game",
        "type": "select",
        "default": "cs2",
        "required": True,
        "options": [
            {"value": "cs2", "label": "Counter-Strike 2"},
            {"value": "csgo", "label": "Counter-Strike: Global Offensive"},
            {"value": "css", "label": "Counter-Strike: Source"},
            {"value": "tf2", "label": "Team Fortress 2"},
            {"value": "gmod", "label": "Garry's Mod"},
            {"value": "l4d", "label": "Left 4 Dead"},
            {"value": "l4d2", "label": "Left 4 Dead 2"},
            {"value": "dods", "label": "Day of Defeat: Source"},
            {"value": "hl2dm", "label": "Half-Life 2: Deathmatch"},
            {"value": "portal2", "label": "Portal 2"},
            {"value": "alien_swarm", "label": "Alien Swarm"},
            {"value": "black_mesa", "label": "Black Mesa"},
            {"value": "synergy", "label": "Synergy"},
            {"value": "insurgency", "label": "Insurgency (2014)"},
            {"value": "fistful_of_frags", "label": "Fistful of Frags"},
            {"value": "source_generic", "label": "Source / Source 2 (Generic A2S)"},
        ],
        "help": "ServerSpy is restricted to Source and Source 2 servers using Valve A2S queries.",
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
        "help": "Enter the A2S query port. Many Source servers use 27015, but hosted servers may use another port.",
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
    {
        "key": "SERVERSPY_DETAILED_QUERIES",
        "label": "Player & Rules Details",
        "type": "checkbox",
        "default": "true",
        "required": False,
        "help": "Also request A2S_PLAYER and A2S_RULES. Player details refresh every 30 seconds; rules are limited to once every 5 minutes.",
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

_info_cache = TTLCache(20)
_player_cache = TTLCache(30)
_rules_cache = TTLCache(300)

_info_cache_key = None
_player_cache_key = None
_rules_cache_key = None

A2S_SINGLE = b"\xff\xff\xff\xff"
A2S_SPLIT = b"\xfe\xff\xff\xff"
A2S_INFO_BODY = b"TSource Engine Query\x00"

MAX_SPLIT_PACKETS = 32
MAX_RESPONSE_BYTES = 512 * 1024


class QueryResponse:
    """Small response container that is safe under RackDash's plugin loader."""

    __slots__ = ("payload", "ping_ms")

    def __init__(self, payload, ping_ms):
        self.payload = payload
        self.ping_ms = ping_ms


def _bool_env(name, default="false"):
    return os.getenv(name, default).strip().lower() in {
        "1", "true", "yes", "on",
    }


def _config():
    game_key = os.getenv("SERVERSPY_GAME", "cs2").strip()
    if game_key not in GAME_PRESETS:
        game_key = "source_generic"

    game_label, default_port = GAME_PRESETS[game_key]
    host = os.getenv("SERVERSPY_HOST", "").strip()
    if not host:
        raise RuntimeError("Server IP / Hostname is required")

    try:
        port = int(os.getenv("SERVERSPY_PORT", "") or default_port)
    except ValueError:
        port = default_port

    if not 1 <= port <= 65535:
        raise RuntimeError("Query port must be between 1 and 65535")

    try:
        timeout = float(os.getenv("SERVERSPY_TIMEOUT", "3") or 3)
    except ValueError:
        timeout = 3.0
    timeout = max(1.0, min(10.0, timeout))

    return {
        "game_key": game_key,
        "game_label": game_label,
        "host": host,
        "port": port,
        "timeout": timeout,
        "detailed": _bool_env("SERVERSPY_DETAILED_QUERIES", "true"),
    }


def _cache_key(config):
    return (
        config["game_key"],
        config["host"].lower(),
        config["port"],
    )


def _make_socket(host, port, timeout):
    rows = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    if not rows:
        raise OSError("Unable to resolve server address")

    family, _, _, _, address = rows[0]
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    sock.connect(address)
    return sock


def _strip_single_header(data):
    return data[4:] if data.startswith(A2S_SINGLE) else data


def _receive_split(sock, first_packet, deadline):
    chunks = {}
    request_id = None
    compressed = False
    total = None
    expected_size = None
    expected_crc = None
    packet = first_packet

    while True:
        if not packet.startswith(A2S_SPLIT) or len(packet) < 12:
            raise ValueError("Malformed split A2S packet")

        offset = 4
        packet_id = struct.unpack_from("<I", packet, offset)[0]
        offset += 4

        packet_compressed = bool(packet_id & 0x80000000)
        clean_id = packet_id & 0x7FFFFFFF

        packet_total = packet[offset]
        packet_number = packet[offset + 1]
        offset += 2

        # Source/Source 2 split responses advertise the max fragment size.
        _fragment_size = struct.unpack_from("<H", packet, offset)[0]
        offset += 2

        if request_id is None:
            request_id = clean_id
            compressed = packet_compressed
            total = packet_total
            if total < 1 or total > MAX_SPLIT_PACKETS:
                raise ValueError("Invalid split-packet count")

        if (
            clean_id == request_id
            and packet_total == total
            and packet_compressed == compressed
        ):
            if packet_number >= total:
                raise ValueError("Invalid split-packet number")

            if compressed and packet_number == 0:
                if len(packet) < offset + 8:
                    raise ValueError("Malformed compressed A2S packet")
                expected_size = struct.unpack_from("<I", packet, offset)[0]
                expected_crc = struct.unpack_from("<I", packet, offset + 4)[0]
                offset += 8

            chunks[packet_number] = packet[offset:]

            if sum(len(chunk) for chunk in chunks.values()) > MAX_RESPONSE_BYTES:
                raise ValueError("A2S response exceeded size limit")

            if len(chunks) == total:
                break

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Timed out receiving split A2S response")

        sock.settimeout(remaining)
        packet = sock.recv(65535)

    combined = b"".join(chunks[index] for index in range(total))

    if compressed:
        combined = bz2.decompress(combined)

        if expected_size is not None and len(combined) != expected_size:
            raise ValueError("A2S decompressed-size check failed")

        if (
            expected_crc is not None
            and (zlib.crc32(combined) & 0xFFFFFFFF) != expected_crc
        ):
            raise ValueError("A2S CRC check failed")

    if len(combined) > MAX_RESPONSE_BYTES:
        raise ValueError("A2S response exceeded size limit")

    return _strip_single_header(combined)


def _send_query(host, port, request, timeout):
    with _make_socket(host, port, timeout) as sock:
        start = time.perf_counter()
        deadline = time.monotonic() + timeout

        sock.send(request)
        first = sock.recv(65535)

        ping_ms = (time.perf_counter() - start) * 1000.0

        if first.startswith(A2S_SINGLE):
            payload = first[4:]
        elif first.startswith(A2S_SPLIT):
            payload = _receive_split(sock, first, deadline)
        else:
            raise ValueError("Unexpected A2S packet header")

        return QueryResponse(payload=payload, ping_ms=ping_ms)


def _query_with_challenge(
    host,
    port,
    base_request,
    expected_type,
    timeout,
    info_query=False,
):
    request = base_request

    for _ in range(3):
        result = _send_query(host, port, request, timeout)
        payload = result.payload

        if not payload:
            raise ValueError("Empty A2S response")

        if payload[0] == 0x41:
            if len(payload) < 5:
                raise ValueError("Malformed A2S challenge")

            challenge = payload[1:5]

            if info_query:
                request = base_request + challenge
            else:
                request = base_request[:-4] + challenge
            continue

        if payload[0] != expected_type:
            raise ValueError(
                f"Unexpected A2S response type 0x{payload[0]:02x}"
            )

        return result

    raise ValueError("A2S challenge retry limit reached")


def _require(data, offset, size):
    if offset + size > len(data):
        raise ValueError("Truncated A2S response")


def _cstring(data, offset):
    end = data.find(b"\x00", offset)
    if end < 0:
        raise ValueError("Malformed A2S string")
    return data[offset:end].decode("utf-8", "replace"), end + 1


def _u8(data, offset):
    _require(data, offset, 1)
    return data[offset], offset + 1


def _u16(data, offset):
    _require(data, offset, 2)
    return struct.unpack_from("<H", data, offset)[0], offset + 2


def _i32(data, offset):
    _require(data, offset, 4)
    return struct.unpack_from("<i", data, offset)[0], offset + 4


def _u64(data, offset):
    _require(data, offset, 8)
    return struct.unpack_from("<Q", data, offset)[0], offset + 8


def _f32(data, offset):
    _require(data, offset, 4)
    return struct.unpack_from("<f", data, offset)[0], offset + 4


def _parse_info(payload, ping_ms):
    if not payload or payload[0] != 0x49:
        raise ValueError("Invalid A2S_INFO payload")

    offset = 1
    protocol, offset = _u8(payload, offset)
    name, offset = _cstring(payload, offset)
    map_name, offset = _cstring(payload, offset)
    folder, offset = _cstring(payload, offset)
    game, offset = _cstring(payload, offset)
    app_id, offset = _u16(payload, offset)
    players, offset = _u8(payload, offset)
    max_players, offset = _u8(payload, offset)
    bots, offset = _u8(payload, offset)
    server_type_raw, offset = _u8(payload, offset)
    environment_raw, offset = _u8(payload, offset)
    visibility, offset = _u8(payload, offset)
    vac, offset = _u8(payload, offset)
    version, offset = _cstring(payload, offset)

    result = {
        "online": True,
        "ping_ms": round(ping_ms, 1),
        "protocol_version": protocol,
        "name": name,
        "map": map_name,
        "folder": folder,
        "game": game,
        "app_id": app_id,
        "players": players,
        "max_players": max_players,
        "bots": bots,
        "server_type": {
            ord("d"): "Dedicated",
            ord("l"): "Listen",
            ord("p"): "SourceTV / Proxy",
        }.get(server_type_raw, chr(server_type_raw)),
        "environment": {
            ord("l"): "Linux",
            ord("w"): "Windows",
            ord("m"): "macOS",
            ord("o"): "macOS",
        }.get(environment_raw, chr(environment_raw)),
        "password": bool(visibility),
        "vac": bool(vac),
        "version": version,
    }

    if offset >= len(payload):
        return result

    edf, offset = _u8(payload, offset)

    if edf & 0x80:
        result["game_port"], offset = _u16(payload, offset)

    if edf & 0x10:
        result["steam_id"], offset = _u64(payload, offset)

    if edf & 0x40:
        result["spectator_port"], offset = _u16(payload, offset)
        result["spectator_name"], offset = _cstring(payload, offset)

    if edf & 0x20:
        result["keywords"], offset = _cstring(payload, offset)

    if edf & 0x01:
        result["game_id"], offset = _u64(payload, offset)

    return result


def _fetch_info(config):
    global _info_cache_key

    key = _cache_key(config)
    cached = _info_cache.get()
    if cached is not None and _info_cache_key == key:
        return dict(cached)

    base_request = A2S_SINGLE + b"T" + A2S_INFO_BODY

    result = _query_with_challenge(
        config["host"],
        config["port"],
        base_request,
        0x49,
        config["timeout"],
        info_query=True,
    )

    parsed = _parse_info(result.payload, result.ping_ms)

    _info_cache_key = key
    return dict(_info_cache.set(parsed))


def _parse_players(payload):
    if not payload or payload[0] != 0x44:
        raise ValueError("Invalid A2S_PLAYER payload")

    count = payload[1] if len(payload) > 1 else 0
    offset = 2
    players = []

    for _ in range(count):
        _, offset = _u8(payload, offset)
        name, offset = _cstring(payload, offset)
        score, offset = _i32(payload, offset)
        duration, offset = _f32(payload, offset)

        players.append({
            "name": name,
            "score": score,
            "duration": max(0, int(duration)),
        })

    players.sort(
        key=lambda row: (-row["score"], row["name"].lower())
    )
    return players


def _fetch_players(config):
    global _player_cache_key

    key = _cache_key(config)
    cached = _player_cache.get()
    if cached is not None and _player_cache_key == key:
        return list(cached)

    base_request = A2S_SINGLE + b"U" + b"\xff\xff\xff\xff"

    result = _query_with_challenge(
        config["host"],
        config["port"],
        base_request,
        0x44,
        config["timeout"],
    )

    players = _parse_players(result.payload)
    _player_cache_key = key
    return list(_player_cache.set(players))


def _parse_rules(payload):
    if not payload or payload[0] != 0x45:
        raise ValueError("Invalid A2S_RULES payload")

    _require(payload, 1, 2)
    count = struct.unpack_from("<H", payload, 1)[0]
    offset = 3
    rules = {}

    for _ in range(min(count, 512)):
        if offset >= len(payload):
            break
        key, offset = _cstring(payload, offset)
        value, offset = _cstring(payload, offset)
        rules[key] = value

    return rules


def _fetch_rules(config):
    global _rules_cache_key

    key = _cache_key(config)
    cached = _rules_cache.get()
    if cached is not None and _rules_cache_key == key:
        return dict(cached)

    base_request = A2S_SINGLE + b"V" + b"\xff\xff\xff\xff"

    result = _query_with_challenge(
        config["host"],
        config["port"],
        base_request,
        0x45,
        config["timeout"],
    )

    rules = _parse_rules(result.payload)
    _rules_cache_key = key
    return dict(_rules_cache.set(rules))


def get_data():
    config = _config()

    # A2S_INFO is the only required query. PLAYER/RULES failures are isolated,
    # so a server that blocks detailed queries still renders normally.
    data = _fetch_info(config)

    player_list = []
    rules = {}

    if config["detailed"]:
        try:
            player_list = _fetch_players(config)
        except Exception:
            player_list = []

        try:
            rules = _fetch_rules(config)
        except Exception:
            rules = {}

    data.update({
        "game_key": config["game_key"],
        "game_label": config["game_label"],
        "host": config["host"],
        "query_port": config["port"],
        "protocol_label": "Valve A2S",
        "detailed_queries": config["detailed"],
        "player_list": player_list,
        "rules": rules,
    })

    return data


def get_i2c_data():
    try:
        data = get_data()
    except Exception:
        return {
            "title": "ServerSpy",
            "lines": ["Server offline"],
        }

    ping = (
        "--"
        if data.get("ping_ms") is None
        else f"{int(round(float(data['ping_ms'])))}ms"
    )

    name = str(
        data.get("name")
        or data.get("game_label")
        or "Source Server"
    )[:18]

    map_name = str(
        data.get("map")
        or "Unknown"
    )[:18]

    players = (
        f"{data.get('players', 0)}/"
        f"{data.get('max_players', 0)}"
    )

    return {
        "title": "ServerSpy",
        "lines": [
            name,
            f"Ping {ping}  P {players}",
            f"Map {map_name}",
        ],
    }
