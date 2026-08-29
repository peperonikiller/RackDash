#!/usr/bin/env python3
# RackDash core application. Integrations live in ./plugins.

from __future__ import annotations

import os
import re
import socket
import time
from pathlib import Path

import psutil
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, render_template, request, session, send_file

from plugin_manager import PluginManager
from health import github_update_status
from plugin_installer import PluginInstaller
from config_manager import ensure_defaults, schema_values, update_schema_values, parse_env
from i2c_display import I2CDisplayManager, I2C_CONFIG, DISPLAY_TYPES
from admin_security import AdminSecurity
from backup_manager import BackupManager
from core_updater import CoreUpdater
from admin_diagnostics import diagnostics, tail_file
from official_plugin_updater import OfficialPluginUpdater
from update_monitor import UpdateMonitor

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "config.env")

APP_NAME = "RackDash"
APP_VERSION = "3.0.8"
RACKDASH_GITHUB = "https://github.com/peperonikiller/RackDash"
ROTATE_SECONDS = max(3, int(os.getenv("ROTATE_SECONDS", "30")))

CORE_CONFIG = [
    {"key":"RACKDASH_HOST","label":"Listen Host","type":"text","default":"127.0.0.1","help":"Use 0.0.0.0 only if LAN access is intended."},
    {"key":"RACKDASH_PORT","label":"Port","type":"number","default":"8080","min":1,"max":65535},
    {"key":"ROTATE_SECONDS","label":"Default Rotation Seconds","type":"number","default":"30","min":3,"max":300},
    {"key":"RACKDASH_THEME","label":"Theme","type":"select","default":"dark","options":[{"value":"dark","label":"Dark"},{"value":"black","label":"OLED Black"},{"value":"blue","label":"Blue Steel"}]},
    {"key":"RACKDASH_UI_SCALE","label":"UI Scale","type":"number","default":"1.0","min":0.7,"max":1.5,"step":0.05},
    {"key":"RACKDASH_SAFE_AREA","label":"Safe Area / Overscan px","type":"number","default":"0","min":0,"max":80},
    {"key":"RACKDASH_LARGE_TOUCH","label":"Large Touch Targets","type":"checkbox","default":"false"},
    {"key":"RACKDASH_BURN_IN","label":"Burn-in Protection","type":"checkbox","default":"false"},
    {"key":"RACKDASH_BURN_IN_SECONDS","label":"Pixel Shift Interval","type":"number","default":"90","min":30,"max":3600},
    {"key":"RACKDASH_DIM_MINUTES","label":"Dim After Minutes","type":"number","default":"0","min":0,"max":1440,"help":"0 disables idle dimming."},
    {"key":"RACKDASH_DEVELOPER_MODE","label":"Developer Mode","type":"checkbox","default":"false"},
]

def discover_config_schemas(plugin_dir: Path):
    import ast
    rows=[]
    for path in sorted(plugin_dir.glob("*.py")):
        if path.name.startswith("_"): continue
        try:
            tree=ast.parse(path.read_text(encoding="utf-8"));vals={}
            for node in tree.body:
                if isinstance(node,ast.Assign):
                    for target in node.targets:
                        if isinstance(target,ast.Name) and target.id in ("PLUGIN_NAME","PLUGIN_CONFIG"):
                            vals[target.id]=ast.literal_eval(node.value)
            rows.append((str(vals.get("PLUGIN_NAME",path.stem)),list(vals.get("PLUGIN_CONFIG",[]) or [])))
        except Exception: pass
    return rows

app = Flask(__name__)
admin_security = AdminSecurity(BASE_DIR / "data" / "admin_auth.json")
app.secret_key = admin_security.secret_key
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

import logging
from logging.handlers import RotatingFileHandler
LOG_PATH = BASE_DIR / "data" / "rackdash.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
_file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
_file_handler.setLevel(logging.INFO)
app.logger.addHandler(_file_handler)
app.logger.setLevel(logging.INFO)

backup_manager = BackupManager(BASE_DIR)
ensure_defaults(BASE_DIR / "config.env", [("RackDash", CORE_CONFIG), ("I2C Display", I2C_CONFIG), *discover_config_schemas(BASE_DIR / "plugins")])
load_dotenv(BASE_DIR / "config.env", override=True)
plugins = PluginManager(app=app, plugin_dir=BASE_DIR / "plugins", state_file=BASE_DIR / "data" / "plugin_state.json")
plugins.load_all()
plugin_installer = PluginInstaller(BASE_DIR / "plugins", BASE_DIR / "data" / "plugin_sources.json", APP_VERSION)
core_updater = CoreUpdater(BASE_DIR, RACKDASH_GITHUB, backup_manager)
official_plugin_updater = OfficialPluginUpdater(
    BASE_DIR / "plugins",
    BASE_DIR / "data" / "plugin_backups",
    RACKDASH_GITHUB,
    branch="main",
)


_RELEASE_NOTES_CACHE = {}
_RELEASE_NOTES_CACHE_SECONDS = 900


def _github_repo_parts(url: str):
    match = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)",
        str(url or "").strip(),
        re.I,
    )
    if not match:
        return None
    return (
        match.group(1),
        re.sub(r"\.git$", "", match.group(2)),
    )


def _github_release_notes(github_url: str, version: str):
    """
    Fetch release notes for a detected update. Prefer a release whose tag
    exactly matches the detected version, then fall back to the latest release.
    Results are cached so opening Admin never adds unnecessary GitHub traffic.
    """
    repo = _github_repo_parts(github_url)
    if not repo or not version:
        return None

    owner, name = repo
    clean = str(version).strip()
    cache_key = (owner, name, clean)
    cached = _RELEASE_NOTES_CACHE.get(cache_key)
    now = time.time()

    if cached and now - cached["checked_at"] < _RELEASE_NOTES_CACHE_SECONDS:
        return dict(cached["result"]) if cached["result"] else None

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RackDash-Release-Notes",
    }

    payload = None
    for tag in (clean, clean.lstrip("v"), f"v{clean.lstrip('v')}"):
        try:
            response = requests.get(
                f"https://api.github.com/repos/{owner}/{name}/releases/tags/{tag}",
                headers=headers,
                timeout=6,
            )
            if response.status_code == 200:
                payload = response.json()
                break
            if response.status_code not in (404, 422):
                response.raise_for_status()
        except Exception:
            payload = None

    if payload is None:
        try:
            response = requests.get(
                f"https://api.github.com/repos/{owner}/{name}/releases/latest",
                headers=headers,
                timeout=6,
            )
            if response.status_code == 200:
                latest = response.json()
                latest_tag = str(latest.get("tag_name") or "").strip()
                if _version_key(latest_tag) == _version_key(clean):
                    payload = latest
        except Exception:
            payload = None

    result = None
    if payload:
        body = str(payload.get("body") or "").strip()
        result = {
            "title": str(payload.get("name") or payload.get("tag_name") or clean),
            "body": body[:12000],
            "url": str(payload.get("html_url") or "").strip(),
            "published_at": str(payload.get("published_at") or "").strip(),
        }

    _RELEASE_NOTES_CACHE[cache_key] = {
        "checked_at": now,
        "result": result,
    }
    return dict(result) if result else None


def _attach_release_notes(result: dict, github_url: str):
    result = dict(result or {})
    if result.get("status") != "update_available":
        return result

    notes = _github_release_notes(
        github_url,
        result.get("latest"),
    )
    if notes:
        result["release_notes"] = notes
    return result


def _check_core_update_now():
    result = github_update_status(
        RACKDASH_GITHUB,
        APP_VERSION,
        force=True,
    )
    return _attach_release_notes(
        result,
        RACKDASH_GITHUB,
    )


def _check_plugin_update_now(plugin):
    if plugin.official:
        if not plugin.source_path:
            raise ValueError(
                "Official plugin is missing PLUGIN_SOURCE_PATH"
            )
        result = official_plugin_updater.check(
            plugin.id,
            plugin.source_path,
            plugin.plugin_version,
            force=True,
        )
        return _attach_release_notes(
            result,
            RACKDASH_GITHUB,
        )

    result = github_update_status(
        plugin.github_url,
        plugin.plugin_version,
        force=True,
    )
    return _attach_release_notes(
        result,
        plugin.github_url,
    )


update_monitor = UpdateMonitor(
    BASE_DIR / "config.env",
    BASE_DIR / "data" / "update_checks.json",
    core_checker=_check_core_update_now,
    plugin_provider=lambda: list(plugins._plugins),
    plugin_checker=_check_plugin_update_now,
    logger=app.logger,
)
update_monitor.start()


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()



def _version_key(value: str):
    parts = []
    for token in re.findall(r"\d+", str(value or "")):
        try:
            parts.append(int(token))
        except ValueError:
            parts.append(0)
    return tuple((parts + [0, 0, 0])[:3])


def update_attention_status() -> dict:
    """
    Read persisted update-monitor state only. This never contacts GitHub, so it
    is cheap enough to include in /api/system for kiosk notification polling.
    """
    status = update_monitor.status()
    count = 0

    core = status.get("core") or {}
    if core.get("ok") and isinstance(core.get("result"), dict):
        result = core["result"]
        if (
            result.get("status") == "update_available"
            and _version_key(result.get("latest")) > _version_key(APP_VERSION)
        ):
            count += 1

    plugin_rows = status.get("plugins") or {}
    for plugin in plugins._plugins:
        row = plugin_rows.get(plugin.id) or {}
        result = row.get("result") if row.get("ok") else None
        if not isinstance(result, dict):
            continue
        if (
            result.get("status") == "update_available"
            and _version_key(result.get("latest"))
                > _version_key(plugin.plugin_version)
        ):
            count += 1

    return {
        "available": count > 0,
        "count": count,
        "checked_at": max(
            int((core or {}).get("checked_at") or 0),
            int(status.get("plugin_batch_checked_at") or 0),
        ),
    }

def system_status() -> dict:
    temp = None
    try:
        temperatures = psutil.sensors_temperatures()
        temp = next(
            (round(items[0].current, 1) for items in temperatures.values() if items),
            None,
        )
    except Exception:
        pass

    if temp is None:
        try:
            temp = round(
                int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000,
                1,
            )
        except Exception:
            pass

    return {
        "cpu": psutil.cpu_percent(interval=None),
        "ram": psutil.virtual_memory().percent,
        "temp": temp,
        "uptime": int(time.time() - psutil.boot_time()),
        "disk": psutil.disk_usage("/").percent,
        "ip": local_ip(),
        "version": APP_VERSION,
        "update_attention": update_attention_status(),
    }


i2c_manager = I2CDisplayManager(
    BASE_DIR / "config.env",
    plugin_provider=lambda: [p for p in plugins._plugins if plugins.is_enabled(p.id)],
)
i2c_manager.start()


@app.get("/")
def index():
    response = make_response(render_template(
        "index.html",
        app_name=APP_NAME,
        app_version=APP_VERSION,
        rotate_seconds=ROTATE_SECONDS,
        plugins=plugins.public_plugins(),
        plugin_css=plugins.combined_css(),
        plugin_js=plugins.combined_js(),
        ui_config={
            "theme": os.getenv("RACKDASH_THEME","dark"),
            "scale": os.getenv("RACKDASH_UI_SCALE","1.0"),
            "safe_area": os.getenv("RACKDASH_SAFE_AREA","0"),
            "large_touch": os.getenv("RACKDASH_LARGE_TOUCH","false").lower() in ("1","true","yes","on"),
            "burn_in": os.getenv("RACKDASH_BURN_IN","false").lower() in ("1","true","yes","on"),
            "burn_in_seconds": int(os.getenv("RACKDASH_BURN_IN_SECONDS","90") or 90),
            "dim_minutes": int(os.getenv("RACKDASH_DIM_MINUTES","0") or 0),
            "developer_mode": os.getenv("RACKDASH_DEVELOPER_MODE","false").lower() in ("1","true","yes","on"),
        },
    ))
    # Dashboard HTML contains plugin HTML/CSS/JS. Never let the browser reuse
    # stale document markup after a plugin update or display-setting change.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/api/system")
def api_system():
    return jsonify(system_status())


@app.get("/api/plugins")
def api_plugins():
    return jsonify(plugins.public_plugins(include_html=False))


@app.get("/api/plugin/<plugin_id>")
def api_plugin(plugin_id: str):
    plugin = plugins.get(plugin_id)
    if plugin is None:
        return jsonify({"ok": False, "error": "Unknown plugin"}), 404
    if not plugins.is_enabled(plugin_id):
        return jsonify({"ok": False, "error": "Plugin disabled"}), 403

    try:
        return jsonify({"ok": True, "data": plugin.get_data()})
    except Exception:
        app.logger.exception("Plugin %s failed", plugin_id)
        return jsonify({
            "ok": False,
            "error": plugin.public_error or f"{plugin.name} unavailable",
        }), 200


@app.get("/api/health")
def api_health():
    """
    Local health report. This endpoint does not contact GitHub.
    """
    rows = []
    env_values = parse_env(BASE_DIR / "config.env")
    for plugin in plugins._plugins:
        runtime = plugins.runtime_health(plugin, env_values)
        rows.append({
            "id": plugin.id,
            "name": plugin.name,
            "version": plugin.plugin_version,
            "github_url": plugin.github_url,
            "refresh_seconds": plugin.refresh_seconds,
            "accent": plugin.accent,
            "enabled": plugins.is_enabled(plugin.id),
            "installer_managed": bool(plugin_installer.source_for(plugin.id)),
            "official": plugin.official,
            "source_path": plugin.source_path,
            "config_fields": schema_values(BASE_DIR / "config.env", plugin.config_schema),
            "health": runtime,
            "display": plugins.display_settings(plugin.id),
            "capabilities": plugin.capabilities,
            "min_rackdash": plugin.min_rackdash,
            "max_rackdash": plugin.max_rackdash,
            "backups": plugin_installer.backups(plugin.id)[:5],
            "update_status": update_monitor.plugin_status(plugin.id),
        })

    return jsonify({
        "system": system_status(),
        "admin_auth": admin_security.status(),
        "diagnostics": diagnostics(BASE_DIR),
        "backups": backup_manager.list()[:10],
        "updates": update_monitor.status(),
        "i2c": i2c_manager.status(),
        "plugins": rows,
        "plugin_failures": plugins.failures(),
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "github_url": RACKDASH_GITHUB,
            "plugin_count": len(rows),
            "plugin_failure_count": len(plugins.failures()),
            "plugin_discovered_count": len(rows) + len(plugins.failures()),
            "config_fields": schema_values(BASE_DIR / "config.env", CORE_CONFIG),
        },
    })


@app.get("/api/health/plugin/<plugin_id>/update")
def api_health_plugin_update(plugin_id: str):
    """Perform and persist a fresh update check for one plugin."""
    plugin = plugins.get(plugin_id)
    if plugin is None:
        return jsonify({"ok": False, "error": "Unknown plugin"}), 404

    row = update_monitor.check_plugin(plugin, automatic=False)
    if row.get("ok"):
        return jsonify({
            "ok": True,
            "plugin": plugin_id,
            "update": row.get("result") or {},
            "checked_at": row.get("checked_at"),
        })

    return jsonify({
        "ok": False,
        "plugin": plugin_id,
        "error": row.get("error") or "Unable to check GitHub for updates",
        "checked_at": row.get("checked_at"),
    }), 200


def _admin_denied():
    return jsonify({"ok":False,"error":"Admin authentication required","auth_required":True}),401

def _require_admin():
    return admin_security.require()

@app.post("/api/health/plugin/<plugin_id>/enabled")
def api_health_plugin_enabled(plugin_id: str):
    if not _require_admin(): return _admin_denied()
    from flask import request
    plugin=plugins.get(plugin_id)
    if plugin is None:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    enabled=bool((request.get_json(silent=True) or {}).get("enabled"))
    plugins.set_enabled(plugin_id,enabled)
    return jsonify({"ok":True,"enabled":enabled,"reload_required":True})

@app.post("/api/health/core/config")
def api_health_core_config():
    if not _require_admin(): return _admin_denied()
    payload=request.get_json(silent=True) or {}
    update_schema_values(BASE_DIR/"config.env",CORE_CONFIG,payload.get("values") or {})
    if payload.get("restart"):
        import threading
        def _restart():
            time.sleep(.8);os._exit(3)
        threading.Thread(target=_restart,daemon=True).start()
    return jsonify({"ok":True,"restart_required":not bool(payload.get("restart"))})

@app.post("/api/health/plugin/<plugin_id>/config")
def api_health_plugin_config(plugin_id:str):
    if not _require_admin(): return _admin_denied()
    plugin=plugins.get(plugin_id)
    if plugin is None:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    payload=request.get_json(silent=True) or {}
    update_schema_values(BASE_DIR/"config.env",plugin.config_schema,payload.get("values") or {})
    if payload.get("restart"):
        import threading
        def _restart():
            time.sleep(.8);os._exit(3)
        threading.Thread(target=_restart,daemon=True).start()
    return jsonify({"ok":True,"restart_required":not bool(payload.get("restart"))})

@app.post("/api/health/plugins/install")
def api_health_plugins_install():
    if not _require_admin(): return _admin_denied()
    from flask import request
    url=str((request.get_json(silent=True) or {}).get("github_url","")).strip()
    if not url:return jsonify({"ok":False,"error":"GitHub repository URL is required"}),400
    try:return jsonify({"ok":True,"plugin":plugin_installer.install_from_github(url)})
    except Exception as exc:
        app.logger.exception("Plugin install failed");return jsonify({"ok":False,"error":str(exc)}),200


@app.post("/api/health/plugin/<plugin_id>/update-official")
def api_health_plugin_update_official(plugin_id:str):
    if not _require_admin(): return _admin_denied()
    plugin=plugins.get(plugin_id)
    if plugin is None:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    if not plugin.official:return jsonify({"ok":False,"error":"Plugin is not an official RackDash plugin"}),400
    if not plugin.source_path:return jsonify({"ok":False,"error":"Official plugin has no source path"}),400
    try:
        return jsonify({
            "ok":True,
            "plugin":official_plugin_updater.update(plugin.id,plugin.source_path),
        })
    except Exception as exc:
        app.logger.exception("Official plugin update failed for %s",plugin_id)
        return jsonify({"ok":False,"error":str(exc)}),200

@app.post("/api/health/plugin/<plugin_id>/update-managed")
def api_health_plugin_update_managed(plugin_id:str):
    if not _require_admin(): return _admin_denied()
    source=plugin_installer.source_for(plugin_id)
    if not source:return jsonify({"ok":False,"error":"Plugin is not installer-managed"}),400
    try:return jsonify({"ok":True,"plugin":plugin_installer.install_from_github(source["github_url"])})
    except Exception as exc:
        app.logger.exception("Plugin update failed");return jsonify({"ok":False,"error":str(exc)}),200

@app.post("/api/health/plugin/<plugin_id>/uninstall")
def api_health_plugin_uninstall(plugin_id:str):
    if not _require_admin(): return _admin_denied()
    try:return jsonify({"ok":True,"plugin":plugin_installer.uninstall(plugin_id)})
    except Exception as exc:
        app.logger.exception("Plugin uninstall failed");return jsonify({"ok":False,"error":str(exc)}),200
@app.post("/api/health/plugin/<plugin_id>/test")
def api_health_plugin_test(plugin_id: str):
    plugin = plugins.get(plugin_id)
    if plugin is None:
        return jsonify({"ok": False, "error": "Unknown plugin"}), 404

    env_values = parse_env(BASE_DIR / "config.env")
    config = plugins.configuration_status(plugin, env_values)
    if not config["configured"]:
        return jsonify({
            "ok": False,
            "error": "Plugin is not configured",
            "missing": config["missing"],
            "health": plugins.runtime_health(plugin, env_values),
        }), 200

    try:
        plugin.get_data()
        return jsonify({
            "ok": True,
            "health": plugins.runtime_health(plugin, env_values),
        })
    except Exception:
        app.logger.exception("Plugin health test failed for %s", plugin_id)
        return jsonify({
            "ok": False,
            "error": plugin.public_error,
            "health": plugins.runtime_health(plugin, env_values),
        }), 200
@app.get("/api/health/rackdash/update")
def api_health_rackdash_update():
    row = update_monitor.check_core(automatic=False)
    if row.get("ok"):
        return jsonify({
            "ok": True,
            "current": APP_VERSION,
            "github_url": RACKDASH_GITHUB,
            "update": row.get("result") or {},
            "checked_at": row.get("checked_at"),
        })

    return jsonify({
        "ok": False,
        "current": APP_VERSION,
        "github_url": RACKDASH_GITHUB,
        "error": row.get("error")
            or "Unable to check GitHub for RackDash updates",
        "checked_at": row.get("checked_at"),
    }), 200


@app.get("/api/admin/update-settings")
def api_admin_update_settings():
    return jsonify({"ok": True, **update_monitor.status()})


@app.post("/api/admin/update-settings")
def api_admin_update_settings_save():
    if not _require_admin():
        return _admin_denied()

    payload = request.get_json(silent=True) or {}
    settings = update_monitor.set_settings(
        bool(payload.get("core_daily")),
        bool(payload.get("plugins_daily")),
    )
    return jsonify({"ok": True, "settings": settings})


@app.post("/api/admin/plugin-updates/check-all")
def api_admin_plugin_updates_check_all():
    """Check RackDash core and every update-capable plugin in one action."""
    if not _require_admin():
        return _admin_denied()

    core = update_monitor.check_core(automatic=False)
    plugins_checked = update_monitor.check_plugins(automatic=False)

    return jsonify({
        "ok": True,
        "core": core,
        "plugins": plugins_checked,
        "checked_at": int(time.time()),
    })


@app.post("/api/admin/plugins/order")
def api_admin_plugins_order():
    """Persist the visual plugin order without requiring plugin source changes."""
    if not _require_admin():
        return _admin_denied()

    payload = request.get_json(silent=True) or {}
    plugin_ids = payload.get("plugin_ids") or []

    try:
        order = plugins.update_plugin_order(plugin_ids)
        return jsonify({
            "ok": True,
            "order": order,
            "reload_required": True,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


@app.get("/api/admin/i2c")
def api_admin_i2c():
    fields=schema_values(BASE_DIR / "config.env", I2C_CONFIG)
    return jsonify({
        "ok":True,
        "fields":fields,
        "displays":DISPLAY_TYPES,
        "status":i2c_manager.status(),
    })


@app.post("/api/admin/i2c")
def api_admin_i2c_save():
    if not _require_admin(): return _admin_denied()
    from flask import request
    payload=request.get_json(silent=True) or {}
    try:
        status=i2c_manager.save_settings(payload)
        return jsonify({"ok":True,"status":status})
    except Exception as exc:
        app.logger.exception("I2C settings save failed")
        return jsonify({"ok":False,"error":str(exc)}),200


@app.post("/api/admin/i2c/test")
def api_admin_i2c_test():
    if not _require_admin(): return _admin_denied()
    try:
        return jsonify({"ok":True,"status":i2c_manager.test()})
    except Exception as exc:
        app.logger.exception("I2C display test failed")
        return jsonify({"ok":False,"error":str(exc)}),200


@app.post("/api/admin/i2c/icon")
def api_admin_i2c_icon():
    if not _require_admin(): return _admin_denied()
    from flask import request
    upload=request.files.get("icon")
    if upload is None or not upload.filename:
        return jsonify({"ok":False,"error":"Choose an image first."}),400
    try:
        info=i2c_manager.save_icon(upload)
        return jsonify({"ok":True,"image":info,"status":i2c_manager.status()})
    except Exception as exc:
        return jsonify({"ok":False,"error":str(exc)}),200


@app.post("/api/health/restart")
def api_health_restart():
    if not _require_admin(): return _admin_denied()
    import os
    import threading
    import time

    def _restart():
        time.sleep(0.75)
        os._exit(3)

    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "RackDash is restarting"})

@app.get("/api/admin/auth")
def api_admin_auth_status():
    return jsonify({"ok":True,**admin_security.status()})

@app.post("/api/admin/auth/login")
def api_admin_auth_login():
    password=str((request.get_json(silent=True) or {}).get("password",""))
    if admin_security.login(password):return jsonify({"ok":True,**admin_security.status()})
    return jsonify({"ok":False,"error":"Invalid admin password/PIN"}),401

@app.post("/api/admin/auth/logout")
def api_admin_auth_logout():
    admin_security.logout();return jsonify({"ok":True})

@app.post("/api/admin/auth/config")
def api_admin_auth_config():
    if admin_security.enabled and not admin_security.is_authenticated():return _admin_denied()
    payload=request.get_json(silent=True) or {}
    try:
        if payload.get("password"):
            admin_security.set_password(str(payload["password"]));session["rackdash_admin"]=True
        if "enabled" in payload:admin_security.set_enabled(bool(payload["enabled"]))
        return jsonify({"ok":True,**admin_security.status()})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.post("/api/admin/plugins/display-settings")
def api_admin_plugins_display_settings():
    if not _require_admin():
        return _admin_denied()

    payload = request.get_json(silent=True) or {}
    try:
        result = plugins.update_display_settings_batch(
            payload.get("plugins") or {},
            payload.get("plugin_ids") or [],
        )
        return jsonify({
            "ok": True,
            "display": result,
            "reload_required": True,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


@app.post("/api/admin/plugin/<plugin_id>/display")
def api_admin_plugin_display(plugin_id):
    if not _require_admin():return _admin_denied()
    try:return jsonify({"ok":True,"display":plugins.update_display_settings(plugin_id,request.get_json(silent=True) or {}),"reload_required":True})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.get("/api/admin/plugins/preview")
def api_admin_plugins_preview():
    if not _require_admin():return _admin_denied()
    try:return jsonify({"ok":True,"plugin":plugin_installer.preview(request.args.get("github_url",""))})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.get("/api/admin/plugin/<plugin_id>/backups")
def api_admin_plugin_backups(plugin_id):
    if not _require_admin():return _admin_denied()
    return jsonify({"ok":True,"backups":plugin_installer.backups(plugin_id)})

@app.post("/api/admin/plugin/<plugin_id>/rollback")
def api_admin_plugin_rollback(plugin_id):
    if not _require_admin():return _admin_denied()
    try:return jsonify({"ok":True,"plugin":plugin_installer.rollback(plugin_id,str((request.get_json(silent=True) or {}).get("backup","")))})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.get("/api/admin/backup")
def api_admin_backup_create():
    if not _require_admin():return _admin_denied()
    path=backup_manager.create("manual");return send_file(path,as_attachment=True,download_name=path.name)

@app.post("/api/admin/restore")
def api_admin_restore():
    if not _require_admin():return _admin_denied()
    upload=request.files.get("backup")
    if not upload:return jsonify({"ok":False,"error":"Choose a RackDash backup zip."}),400
    try:return jsonify({"ok":True,**backup_manager.restore_upload(upload.stream)})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.get("/api/admin/logs")
def api_admin_logs():
    if not _require_admin():return _admin_denied()
    rows=tail_file(LOG_PATH,request.args.get("lines",200,type=int));plugin=request.args.get("plugin","").lower().strip()
    if plugin:rows=[row for row in rows if plugin in row.lower()]
    return jsonify({"ok":True,"lines":rows})

@app.get("/api/admin/diagnostics")
def api_admin_diagnostics():
    return jsonify({"ok":True,"server":diagnostics(BASE_DIR)})

@app.post("/api/admin/plugin/<plugin_id>/reload")
def api_admin_plugin_reload(plugin_id):
    if not _require_admin():return _admin_denied()
    try:return jsonify({"ok":True,"plugin":plugins.reload_plugin(plugin_id)})
    except Exception as exc:return jsonify({"ok":False,"error":str(exc)}),200

@app.get("/api/admin/plugin/<plugin_id>/debug")
def api_admin_plugin_debug(plugin_id):
    if not _require_admin():return _admin_denied()
    plugin=plugins.get(plugin_id)
    if not plugin:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    raw=None;error=None
    if request.args.get("fetch")=="1":
        try:raw=plugin.get_data()
        except Exception as exc:error=str(exc)
    return jsonify({"ok":True,"metadata":{"id":plugin.id,"name":plugin.name,"version":plugin.plugin_version,"github":plugin.github_url,"capabilities":plugin.capabilities,"min_rackdash":plugin.min_rackdash,"max_rackdash":plugin.max_rackdash,"display":plugins.display_settings(plugin.id)},"data":raw,"error":error})

@app.post("/api/admin/core/update")
def api_admin_core_update():
    if not _require_admin():return _admin_denied()
    try:
        result=core_updater.apply_latest()
        import threading
        def _exit():
            time.sleep(1.0);os._exit(3)
        threading.Thread(target=_exit,daemon=True).start()
        return jsonify({"ok":True,"update":result})
    except Exception as exc:
        app.logger.exception("Core update failed");return jsonify({"ok":False,"error":str(exc)}),200


if __name__ == "__main__":
    app.run(
        host=os.getenv("RACKDASH_HOST", "127.0.0.1"),
        port=int(os.getenv("RACKDASH_PORT", "8080")),
        threaded=True,
    )
