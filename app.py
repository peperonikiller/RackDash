#!/usr/bin/env python3
# RackDash core application. Integrations live in ./plugins.

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

import psutil
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

from plugin_manager import PluginManager
from health import github_update_status
from plugin_installer import PluginInstaller
from config_manager import ensure_defaults, schema_values, update_schema_values, parse_env

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "config.env")

APP_NAME = "RackDash"
APP_VERSION = "1.4.0"
ROTATE_SECONDS = max(3, int(os.getenv("ROTATE_SECONDS", "12")))

CORE_CONFIG = [
    {"key":"RACKDASH_HOST","label":"Listen Host","type":"text","default":"127.0.0.1","help":"Use 0.0.0.0 only if LAN access is intended."},
    {"key":"RACKDASH_PORT","label":"Port","type":"number","default":"8080"},
    {"key":"ROTATE_SECONDS","label":"Auto Rotation Seconds","type":"number","default":"12"},
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
ensure_defaults(BASE_DIR / "config.env", [("RackDash", CORE_CONFIG), *discover_config_schemas(BASE_DIR / "plugins")])
load_dotenv(BASE_DIR / "config.env", override=True)
plugins = PluginManager(app=app, plugin_dir=BASE_DIR / "plugins", state_file=BASE_DIR / "data" / "plugin_state.json")
plugins.load_all()
plugin_installer = PluginInstaller(BASE_DIR / "plugins", BASE_DIR / "data" / "plugin_sources.json")


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


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
        "ip": local_ip(),
        "version": APP_VERSION,
    }


@app.get("/")
def index():
    return render_template(
        "index.html",
        app_name=APP_NAME,
        app_version=APP_VERSION,
        rotate_seconds=ROTATE_SECONDS,
        plugins=plugins.public_plugins(),
        plugin_css=plugins.combined_css(),
        plugin_js=plugins.combined_js(),
    )


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
            "config_fields": schema_values(BASE_DIR / "config.env", plugin.config_schema),
            "health": runtime,
        })

    return jsonify({
        "system": system_status(),
        "plugins": rows,
        "app": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "plugin_count": len(rows),
            "config_fields": schema_values(BASE_DIR / "config.env", CORE_CONFIG),
        },
    })


@app.get("/api/health/plugin/<plugin_id>/update")
def api_health_plugin_update(plugin_id: str):
    """
    Explicit update check for one plugin.

    It is intentionally separate from /api/health so merely opening RackDash
    never causes background calls to GitHub.
    """
    plugin = plugins.get(plugin_id)
    if plugin is None:
        return jsonify({"ok": False, "error": "Unknown plugin"}), 404

    try:
        result = github_update_status(plugin.github_url, plugin.plugin_version)
        return jsonify({"ok": True, "plugin": plugin_id, "update": result})
    except Exception:
        app.logger.exception("Update check failed for plugin %s", plugin_id)
        return jsonify({
            "ok": False,
            "plugin": plugin_id,
            "error": "Unable to check GitHub for updates",
        }), 200

@app.post("/api/health/plugin/<plugin_id>/enabled")
def api_health_plugin_enabled(plugin_id: str):
    from flask import request
    plugin=plugins.get(plugin_id)
    if plugin is None:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    enabled=bool((request.get_json(silent=True) or {}).get("enabled"))
    plugins.set_enabled(plugin_id,enabled)
    return jsonify({"ok":True,"enabled":enabled,"reload_required":True})

@app.post("/api/health/core/config")
def api_health_core_config():
    from flask import request
    update_schema_values(BASE_DIR/"config.env",CORE_CONFIG,(request.get_json(silent=True) or {}).get("values") or {})
    return jsonify({"ok":True,"restart_required":True})

@app.post("/api/health/plugin/<plugin_id>/config")
def api_health_plugin_config(plugin_id:str):
    from flask import request
    plugin=plugins.get(plugin_id)
    if plugin is None:return jsonify({"ok":False,"error":"Unknown plugin"}),404
    update_schema_values(BASE_DIR/"config.env",plugin.config_schema,(request.get_json(silent=True) or {}).get("values") or {})
    return jsonify({"ok":True,"restart_required":True})

@app.post("/api/health/plugins/install")
def api_health_plugins_install():
    from flask import request
    url=str((request.get_json(silent=True) or {}).get("github_url","")).strip()
    if not url:return jsonify({"ok":False,"error":"GitHub repository URL is required"}),400
    try:return jsonify({"ok":True,"plugin":plugin_installer.install_from_github(url)})
    except Exception as exc:
        app.logger.exception("Plugin install failed");return jsonify({"ok":False,"error":str(exc)}),200

@app.post("/api/health/plugin/<plugin_id>/update-managed")
def api_health_plugin_update_managed(plugin_id:str):
    source=plugin_installer.source_for(plugin_id)
    if not source:return jsonify({"ok":False,"error":"Plugin is not installer-managed"}),400
    try:return jsonify({"ok":True,"plugin":plugin_installer.install_from_github(source["github_url"])})
    except Exception as exc:
        app.logger.exception("Plugin update failed");return jsonify({"ok":False,"error":str(exc)}),200

@app.post("/api/health/plugin/<plugin_id>/uninstall")
def api_health_plugin_uninstall(plugin_id:str):
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


@app.post("/api/health/restart")
def api_health_restart():
    import os
    import threading
    import time

    def _restart():
        time.sleep(0.75)
        os._exit(3)

    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"ok": True, "message": "RackDash is restarting"})


if __name__ == "__main__":
    app.run(
        host=os.getenv("RACKDASH_HOST", "127.0.0.1"),
        port=int(os.getenv("RACKDASH_PORT", "8080")),
        threaded=True,
    )
