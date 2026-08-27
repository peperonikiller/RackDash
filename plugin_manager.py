# RackDash plugin discovery and validation.

from __future__ import annotations

import importlib.util
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass
class Plugin:
    module: ModuleType
    id: str
    name: str
    order: int
    refresh_seconds: int
    accent: str
    icon: str
    html: str
    css: str
    js: str
    public_error: str
    github_url: str
    plugin_version: str
    config_schema: list[dict]
    last_attempt: float | None = None
    last_success: float | None = None
    last_error: str = ""
    response_ms: float | None = None
    consecutive_failures: int = 0

    def get_data(self) -> dict:
        self.last_attempt = time.time()
        started = time.perf_counter()
        try:
            data = self.module.get_data()
            self.response_ms = round((time.perf_counter() - started) * 1000, 1)
            self.last_success = time.time()
            self.last_error = ""
            self.consecutive_failures = 0
            return data
        except Exception as exc:
            self.response_ms = round((time.perf_counter() - started) * 1000, 1)
            self.last_error = str(exc)[:300]
            self.consecutive_failures += 1
            raise


class PluginManager:
    def __init__(self, app, plugin_dir: Path, state_file: Path | None = None):
        self.app = app
        self.plugin_dir = Path(plugin_dir)
        self.state_file = Path(state_file) if state_file else self.plugin_dir.parent / "data" / "plugin_state.json"
        self._plugins: list[Plugin] = []
        self._disabled: set[str] = set()

    def _load_state(self):
        try:
            import json
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            self._disabled = set(payload.get("disabled", []))
        except Exception:
            self._disabled = set()

    def _save_state(self):
        import json
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"disabled": sorted(self._disabled)}, indent=2), encoding="utf-8")

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id not in self._disabled

    def set_enabled(self, plugin_id: str, enabled: bool):
        if enabled:
            self._disabled.discard(plugin_id)
        else:
            self._disabled.add(plugin_id)
        self._save_state()

    def load_all(self):
        self._plugins.clear()
        self._load_state()
        plugin_path = str(self.plugin_dir)
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            self._plugins.append(self._load(path))

        self._plugins.sort(key=lambda p: (p.order, p.name.lower()))

        for plugin in self._plugins:
            register = getattr(plugin.module, "register_routes", None)
            if callable(register):
                register(self.app)

    def _load(self, path: Path) -> Plugin:
        spec = importlib.util.spec_from_file_location(f"rackdash_plugin_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load plugin: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        plugin_id = str(getattr(module, "PLUGIN_ID", "")).strip()
        name = str(getattr(module, "PLUGIN_NAME", "")).strip()
        html = str(getattr(module, "PLUGIN_HTML", "")).strip()

        if not plugin_id or not ID_RE.fullmatch(plugin_id):
            raise RuntimeError(f"{path.name}: invalid or missing PLUGIN_ID")
        if not name:
            raise RuntimeError(f"{path.name}: missing PLUGIN_NAME")
        if not html:
            raise RuntimeError(f"{path.name}: missing PLUGIN_HTML")
        if not callable(getattr(module, "get_data", None)):
            raise RuntimeError(f"{path.name}: missing get_data()")

        return Plugin(
            module=module,
            id=plugin_id,
            name=name,
            order=int(getattr(module, "PLUGIN_ORDER", 100)),
            refresh_seconds=max(1, int(getattr(module, "PLUGIN_REFRESH_SECONDS", 10))),
            accent=str(getattr(module, "PLUGIN_ACCENT", "#dce8ee")),
            icon=str(getattr(module, "PLUGIN_ICON", "")),
            html=html,
            css=str(getattr(module, "PLUGIN_CSS", "")),
            js=str(getattr(module, "PLUGIN_JS", "")),
            public_error=str(getattr(module, "PLUGIN_PUBLIC_ERROR", f"{name} unavailable")),
            github_url=str(getattr(module, "PLUGIN_GITHUB", "")).strip(),
            plugin_version=str(getattr(module, "PLUGIN_VERSION", "0.0.0")).strip(),
            config_schema=list(getattr(module, "PLUGIN_CONFIG", []) or []),
        )

    def get(self, plugin_id: str) -> Plugin | None:
        return next((p for p in self._plugins if p.id == plugin_id), None)

    def configuration_status(self, plugin: Plugin, env_values: dict[str, str]) -> dict:
        missing = []
        for field in plugin.config_schema or []:
            if not field.get("required"):
                continue
            key = str(field.get("key", "")).strip()
            if key and not str(env_values.get(key, "")).strip():
                missing.append(key)
        return {
            "configured": not missing,
            "missing": missing,
        }

    def runtime_health(self, plugin: Plugin, env_values: dict[str, str]) -> dict:
        enabled = self.is_enabled(plugin.id)
        config = self.configuration_status(plugin, env_values)

        if not enabled:
            status = "disabled"
        elif not config["configured"]:
            status = "unconfigured"
        elif plugin.last_attempt is None:
            status = "waiting"
        elif plugin.last_error:
            status = "error"
        else:
            status = "healthy"

        return {
            "status": status,
            "configured": config["configured"],
            "missing_config": config["missing"],
            "last_attempt": plugin.last_attempt,
            "last_success": plugin.last_success,
            "last_error": plugin.last_error,
            "response_ms": plugin.response_ms,
            "consecutive_failures": plugin.consecutive_failures,
        }

    def public_plugins(self, include_html: bool = True, include_disabled: bool = False) -> list[dict[str, Any]]:
        rows = []
        for p in self._plugins:
            enabled = self.is_enabled(p.id)
            if not include_disabled and not enabled:
                continue
            item = {
                "id": p.id,
                "name": p.name,
                "order": p.order,
                "refresh_seconds": p.refresh_seconds,
                "accent": p.accent,
                "icon": p.icon,
                "github_url": p.github_url,
                "version": p.plugin_version,
                "enabled": enabled,
                "config_schema": p.config_schema,
            }
            if include_html:
                item["html"] = p.html
            rows.append(item)
        return rows

    def combined_css(self) -> str:
        return "\n".join(p.css for p in self._plugins if p.css)

    def combined_js(self) -> str:
        return "\n".join(p.js for p in self._plugins if p.js)
