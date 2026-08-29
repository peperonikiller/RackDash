# RackDash plugin discovery, validation, isolation, and runtime health.

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass
class PluginFailure:
    filename: str
    path: str
    stage: str
    error: str
    error_type: str
    traceback: str
    detected_at: float

    def public_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "path": self.path,
            "stage": self.stage,
            "error": self.error,
            "error_type": self.error_type,
            "detected_at": self.detected_at,
        }


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
    min_rackdash: str
    max_rackdash: str
    capabilities: list[str]
    official: bool
    source_path: str
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
            if not isinstance(data, dict):
                raise TypeError(
                    f"{self.id}.get_data() returned {type(data).__name__}; expected dict"
                )
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
    """
    Loads integrations without allowing a broken plugin to take RackDash down.

    Import/validation/route-registration failures are quarantined in-memory and
    surfaced through Admin. Healthy plugins continue loading normally.
    """

    def __init__(self, app, plugin_dir: Path, state_file: Path | None = None):
        self.app = app
        self.plugin_dir = Path(plugin_dir)
        self.state_file = (
            Path(state_file)
            if state_file
            else self.plugin_dir.parent / "data" / "plugin_state.json"
        )
        self._plugins: list[Plugin] = []
        self._failures: list[PluginFailure] = []
        self._state = {"plugins": {}}

    def _record_failure(self, path: Path, stage: str, exc: Exception):
        failure = PluginFailure(
            filename=path.name,
            path=str(path),
            stage=stage,
            error=str(exc)[:500] or exc.__class__.__name__,
            error_type=exc.__class__.__name__,
            traceback=traceback.format_exc(limit=20),
            detected_at=time.time(),
        )
        self._failures.append(failure)
        try:
            self.app.logger.error(
                "Plugin quarantined: %s during %s: %s",
                path.name,
                stage,
                failure.error,
                exc_info=True,
            )
        except Exception:
            pass
        return failure

    def failures(self) -> list[dict[str, Any]]:
        return [row.public_dict() for row in self._failures]

    def _load_state(self):
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            if "plugins" not in raw:
                disabled = set(raw.get("disabled", []))
                raw = {
                    "plugins": {
                        pid: {"enabled": False}
                        for pid in disabled
                    }
                }
            self._state = raw
        except FileNotFoundError:
            self._state = {"plugins": {}}
        except Exception as exc:
            # Corrupt presentation state must never stop startup.
            self._state = {"plugins": {}}
            try:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                corrupt = self.state_file.with_name(
                    f"{self.state_file.stem}.corrupt-{stamp}{self.state_file.suffix}"
                )
                if self.state_file.exists():
                    self.state_file.replace(corrupt)
                self.app.logger.warning(
                    "Recovered from invalid plugin state file: %s",
                    exc,
                )
            except Exception:
                pass

    def _save_state(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        temp.write_text(
            json.dumps(self._state, indent=2),
            encoding="utf-8",
        )
        temp.replace(self.state_file)

    def _settings(self, plugin: Plugin):
        row = self._state.setdefault("plugins", {}).setdefault(plugin.id, {})
        return {
            "enabled": bool(row.get("enabled", True)),
            "show_tab": bool(row.get("show_tab", True)),
            "auto_rotate": bool(row.get("auto_rotate", True)),
            "auto_scroll": bool(row.get("auto_scroll", False)),
            "order": int(row.get("order", plugin.order)),
            "refresh_seconds": max(
                1,
                int(row.get("refresh_seconds", plugin.refresh_seconds)),
            ),
            "rotation_seconds": max(
                3,
                int(row.get("rotation_seconds", 30)),
            ),
        }

    def update_display_settings(self, plugin_id: str, values: dict):
        plugin = self.get(plugin_id)
        if not plugin:
            raise ValueError("Unknown plugin")

        row = self._state.setdefault("plugins", {}).setdefault(plugin_id, {})

        for key in ("enabled", "show_tab", "auto_rotate", "auto_scroll"):
            if key in values:
                row[key] = bool(values[key])

        for key in ("order", "refresh_seconds", "rotation_seconds"):
            if key in values:
                row[key] = int(values[key])

        self._save_state()
        return self._settings(plugin)

    def update_plugin_order(self, plugin_ids: list[str]):
        """
        Persist plugin order from the Admin drag-and-drop list.

        PLUGIN_ORDER remains the default for plugins that have never been
        manually ordered. Once the user reorders the list, RackDash stores
        order values in plugin_state.json so plugin source files do not need
        to change.
        """
        if not isinstance(plugin_ids, list):
            raise ValueError("plugin_ids must be a list")

        known = {plugin.id for plugin in self._plugins}
        requested = []

        for plugin_id in plugin_ids:
            plugin_id = str(plugin_id).strip()
            if plugin_id in known and plugin_id not in requested:
                requested.append(plugin_id)

        # Preserve any loaded plugins omitted by an older/stale browser.
        remaining = [
            plugin.id
            for plugin in sorted(
                self._plugins,
                key=lambda item: (
                    self._settings(item)["order"],
                    item.name.lower(),
                ),
            )
            if plugin.id not in requested
        ]

        final_order = requested + remaining

        for index, plugin_id in enumerate(final_order, start=1):
            row = self._state.setdefault("plugins", {}).setdefault(plugin_id, {})
            row["order"] = index * 10

        self._save_state()

        # Keep the in-memory ordering consistent for Admin/API callers until
        # the frontend performs its normal refresh.
        self._plugins.sort(
            key=lambda item: (
                self._settings(item)["order"],
                item.name.lower(),
            )
        )

        return [
            {
                "id": plugin.id,
                "order": self._settings(plugin)["order"],
            }
            for plugin in self._plugins
        ]

    def load_all(self):
        self._plugins.clear()
        self._failures.clear()
        self._load_state()

        plugin_path = str(self.plugin_dir)
        if plugin_path not in sys.path:
            sys.path.insert(0, plugin_path)

        seen_ids: set[str] = set()

        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue

            try:
                plugin = self._load(path)
                if plugin.id in seen_ids:
                    raise ValueError(
                        f"duplicate PLUGIN_ID '{plugin.id}'"
                    )
                seen_ids.add(plugin.id)
                self._plugins.append(plugin)
            except Exception as exc:
                self._record_failure(path, "load", exc)

        # Route registration is isolated separately because plugin code can
        # import correctly and still fail while adding custom Flask routes.
        healthy: list[Plugin] = []

        for plugin in self._plugins:
            register = getattr(plugin.module, "register_routes", None)
            if callable(register):
                try:
                    register(self.app)
                except Exception as exc:
                    path = Path(plugin.module.__file__ or f"{plugin.id}.py")
                    self._record_failure(path, "register_routes", exc)
                    continue
            healthy.append(plugin)

        self._plugins = healthy
        self._plugins.sort(
            key=lambda p: (
                self._settings(p)["order"],
                p.name.lower(),
            )
        )

        try:
            self.app.logger.info(
                "Plugin startup complete: %d loaded, %d quarantined",
                len(self._plugins),
                len(self._failures),
            )
        except Exception:
            pass

    def _load(self, path: Path) -> Plugin:
        # Register the module before exec_module(). This matches normal Python
        # import semantics and avoids decorators/libraries (including dataclass)
        # failing because sys.modules does not contain the executing module.
        module_name = f"rackdash_plugin_{path.stem}_{abs(hash(str(path.resolve())))}"
        spec = importlib.util.spec_from_file_location(module_name, path)

        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load plugin: {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        plugin_id = str(getattr(module, "PLUGIN_ID", "")).strip()
        name = str(getattr(module, "PLUGIN_NAME", "")).strip()
        html = str(getattr(module, "PLUGIN_HTML", "")).strip()

        if not plugin_id or not ID_RE.fullmatch(plugin_id):
            raise RuntimeError(
                f"{path.name}: invalid or missing PLUGIN_ID"
            )
        if not name:
            raise RuntimeError(f"{path.name}: missing PLUGIN_NAME")
        if not html:
            raise RuntimeError(f"{path.name}: missing PLUGIN_HTML")
        if not callable(getattr(module, "get_data", None)):
            raise RuntimeError(f"{path.name}: missing get_data()")

        config_schema = getattr(module, "PLUGIN_CONFIG", []) or []
        if not isinstance(config_schema, list):
            raise RuntimeError(
                f"{path.name}: PLUGIN_CONFIG must be a list"
            )

        capabilities = getattr(module, "PLUGIN_CAPABILITIES", []) or []
        if not isinstance(capabilities, list):
            raise RuntimeError(
                f"{path.name}: PLUGIN_CAPABILITIES must be a list"
            )

        return Plugin(
            module=module,
            id=plugin_id,
            name=name,
            order=int(getattr(module, "PLUGIN_ORDER", 100)),
            refresh_seconds=max(
                1,
                int(getattr(module, "PLUGIN_REFRESH_SECONDS", 10)),
            ),
            accent=str(getattr(module, "PLUGIN_ACCENT", "#dce8ee")),
            icon=str(getattr(module, "PLUGIN_ICON", "")),
            html=html,
            css=str(getattr(module, "PLUGIN_CSS", "")),
            js=str(getattr(module, "PLUGIN_JS", "")),
            public_error=str(
                getattr(
                    module,
                    "PLUGIN_PUBLIC_ERROR",
                    f"{name} unavailable",
                )
            ),
            github_url=str(
                getattr(module, "PLUGIN_GITHUB", "")
            ).strip(),
            plugin_version=str(
                getattr(module, "PLUGIN_VERSION", "0.0.0")
            ).strip(),
            config_schema=list(config_schema),
            min_rackdash=str(
                getattr(module, "PLUGIN_MIN_RACKDASH", "")
            ).strip(),
            max_rackdash=str(
                getattr(module, "PLUGIN_MAX_RACKDASH", "")
            ).strip(),
            capabilities=list(capabilities),
            official=bool(
                getattr(module, "PLUGIN_OFFICIAL", False)
            ),
            source_path=str(
                getattr(module, "PLUGIN_SOURCE_PATH", "")
            ).strip(),
        )

    def get(self, plugin_id: str) -> Plugin | None:
        return next(
            (plugin for plugin in self._plugins if plugin.id == plugin_id),
            None,
        )

    def is_enabled(self, plugin_id: str) -> bool:
        plugin = self.get(plugin_id)
        return self._settings(plugin)["enabled"] if plugin else False

    def set_enabled(self, plugin_id: str, enabled: bool):
        return self.update_display_settings(
            plugin_id,
            {"enabled": enabled},
        )

    def display_settings(self, plugin_id: str):
        plugin = self.get(plugin_id)
        return self._settings(plugin) if plugin else None

    def public_plugins(
        self,
        include_html: bool = True,
        include_disabled: bool = False,
        include_hidden: bool = False,
    ) -> list[dict[str, Any]]:
        rows = []

        for plugin in sorted(
            self._plugins,
            key=lambda item: (
                self._settings(item)["order"],
                item.name.lower(),
            ),
        ):
            settings = self._settings(plugin)

            if not include_disabled and not settings["enabled"]:
                continue
            if not include_hidden and not settings["show_tab"]:
                continue

            item = {
                "id": plugin.id,
                "name": plugin.name,
                "order": settings["order"],
                "refresh_seconds": settings["refresh_seconds"],
                "rotation_seconds": settings["rotation_seconds"],
                "auto_rotate": settings["auto_rotate"],
                "auto_scroll": settings["auto_scroll"],
                "show_tab": settings["show_tab"],
                "enabled": settings["enabled"],
                "accent": plugin.accent,
                "icon": plugin.icon,
                "github_url": plugin.github_url,
                "version": plugin.plugin_version,
                "config_schema": plugin.config_schema,
                "min_rackdash": plugin.min_rackdash,
                "max_rackdash": plugin.max_rackdash,
                "capabilities": plugin.capabilities,
                "official": plugin.official,
                "source_path": plugin.source_path,
            }

            if include_html:
                item["html"] = plugin.html

            rows.append(item)

        return rows

    def combined_css(self):
        return "\n".join(
            plugin.css
            for plugin in self._plugins
            if self._settings(plugin)["enabled"]
            and self._settings(plugin)["show_tab"]
            and plugin.css
        )

    def combined_js(self):
        return "\n".join(
            plugin.js
            for plugin in self._plugins
            if self._settings(plugin)["enabled"]
            and self._settings(plugin)["show_tab"]
            and plugin.js
        )

    def configuration_status(
        self,
        plugin: Plugin,
        env_values: dict[str, str],
    ):
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

    def runtime_health(
        self,
        plugin: Plugin,
        env_values: dict[str, str],
    ):
        settings = self._settings(plugin)
        config = self.configuration_status(plugin, env_values)

        if not settings["enabled"]:
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

    def reload_plugin(self, plugin_id: str):
        """
        Safely reload a plugin that does not define custom routes.

        The old plugin remains active until the replacement has imported and
        validated successfully. Plugins with register_routes() require a normal
        RackDash restart because Flask cannot safely replace routes after the
        application has started serving requests.
        """
        plugin = self.get(plugin_id)

        if not plugin:
            raise ValueError("Unknown plugin")

        path = Path(plugin.module.__file__)

        if callable(getattr(plugin.module, "register_routes", None)):
            return {
                "id": plugin.id,
                "name": plugin.name,
                "version": plugin.plugin_version,
                "restart_required": True,
                "message": "Plugin defines custom routes and requires a RackDash restart.",
            }

        replacement = self._load(path)

        if replacement.id != plugin.id:
            raise ValueError(
                "Reloaded plugin PLUGIN_ID does not match the active plugin"
            )

        replacement.last_attempt = plugin.last_attempt
        replacement.last_success = plugin.last_success
        replacement.last_error = plugin.last_error
        replacement.response_ms = plugin.response_ms
        replacement.consecutive_failures = plugin.consecutive_failures

        index = self._plugins.index(plugin)
        self._plugins[index] = replacement

        return {
            "id": replacement.id,
            "name": replacement.name,
            "version": replacement.plugin_version,
            "restart_required": False,
        }
