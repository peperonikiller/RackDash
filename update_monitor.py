from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from config_manager import parse_env, update_schema_values


UPDATE_CHECK_SECONDS = 30 * 60
SCHEDULER_WAKE_SECONDS = 60


class UpdateMonitor:
    """Persist and optionally perform automatic RackDash/plugin update checks."""

    def __init__(
        self,
        config_path: Path,
        state_path: Path,
        core_checker,
        plugin_provider,
        plugin_checker,
        logger=None,
    ):
        self.config_path = Path(config_path)
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.core_checker = core_checker
        self.plugin_provider = plugin_provider
        self.plugin_checker = plugin_checker
        self.logger = logger

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._state = self._load()

    def _load(self):
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError("invalid state")
        except Exception:
            state = {}

        state.setdefault("core", {})
        state.setdefault("plugins", {})
        state.setdefault("plugin_batch_checked_at", 0)
        state.setdefault("plugin_batch_automatic", False)
        return state

    def _save(self):
        temp = self.state_path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        temp.replace(self.state_path)
        try:
            os.chmod(self.state_path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _bool(value):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def settings(self):
        values = parse_env(self.config_path)
        # Retain the historical env keys for backwards compatibility. The UI
        # presents them as one "Automatically check for updates" setting.
        return {
            "core_daily": self._bool(
                values.get("RACKDASH_DAILY_UPDATE_CHECK", "false")
            ),
            "plugins_daily": self._bool(
                values.get("PLUGINS_DAILY_UPDATE_CHECK", "false")
            ),
        }

    def status(self):
        with self._lock:
            return {
                "settings": self.settings(),
                "core": dict(self._state.get("core") or {}),
                "plugins": {
                    key: dict(value)
                    for key, value in (self._state.get("plugins") or {}).items()
                },
                "plugin_batch_checked_at": int(
                    self._state.get("plugin_batch_checked_at") or 0
                ),
                "plugin_batch_automatic": bool(
                    self._state.get("plugin_batch_automatic")
                ),
            }

    def set_settings(self, core_daily: bool, plugins_daily: bool):
        schema = [
            {
                "key": "RACKDASH_DAILY_UPDATE_CHECK",
                "type": "checkbox",
                "default": "false",
            },
            {
                "key": "PLUGINS_DAILY_UPDATE_CHECK",
                "type": "checkbox",
                "default": "false",
            },
        ]
        update_schema_values(
            self.config_path,
            schema,
            {
                "RACKDASH_DAILY_UPDATE_CHECK":
                    "true" if core_daily else "false",
                "PLUGINS_DAILY_UPDATE_CHECK":
                    "true" if plugins_daily else "false",
            },
        )
        # Run due-check evaluation immediately after the setting changes.
        self._wake.set()
        return self.settings()

    def core_status(self):
        with self._lock:
            return dict(self._state.get("core") or {})

    def plugin_status(self, plugin_id: str):
        with self._lock:
            return dict(
                (self._state.get("plugins") or {}).get(plugin_id) or {}
            )

    def check_core(self, automatic=False):
        checked_at = int(time.time())
        try:
            result = self.core_checker()
            row = {
                "ok": True,
                "checked_at": checked_at,
                "automatic": bool(automatic),
                "result": result,
            }
        except Exception:
            if self.logger:
                self.logger.exception("RackDash update check failed")
            row = {
                "ok": False,
                "checked_at": checked_at,
                "automatic": bool(automatic),
                "error": "Unable to check GitHub for RackDash updates",
            }

        with self._lock:
            self._state["core"] = row
            self._save()
        return row

    def check_plugin(self, plugin, automatic=False):
        checked_at = int(time.time())
        try:
            result = self.plugin_checker(plugin)
            row = {
                "ok": True,
                "checked_at": checked_at,
                "automatic": bool(automatic),
                "result": result,
            }
        except Exception:
            if self.logger:
                self.logger.exception(
                    "Update check failed for plugin %s", plugin.id
                )
            row = {
                "ok": False,
                "checked_at": checked_at,
                "automatic": bool(automatic),
                "error": "Unable to check GitHub for updates",
            }

        with self._lock:
            self._state.setdefault("plugins", {})[plugin.id] = row
            self._save()
        return row

    def check_plugins(self, automatic=False):
        rows = {}
        for plugin in self.plugin_provider():
            if (
                not getattr(plugin, "official", False)
                and not getattr(plugin, "github_url", "")
            ):
                continue
            rows[plugin.id] = self.check_plugin(
                plugin, automatic=automatic
            )

        with self._lock:
            self._state["plugin_batch_checked_at"] = int(time.time())
            self._state["plugin_batch_automatic"] = bool(automatic)
            self._save()
        return rows

    @staticmethod
    def _due(timestamp):
        try:
            timestamp = int(timestamp or 0)
        except Exception:
            timestamp = 0
        return (
            timestamp <= 0
            or time.time() - timestamp >= UPDATE_CHECK_SECONDS
        )

    def run_due_checks(self):
        settings = self.settings()
        state = self.status()

        if (
            settings["core_daily"]
            and self._due((state.get("core") or {}).get("checked_at"))
        ):
            self.check_core(automatic=True)

        if (
            settings["plugins_daily"]
            and self._due(state.get("plugin_batch_checked_at"))
        ):
            self.check_plugins(automatic=True)

    def _run(self):
        # Let RackDash finish plugin/I2C startup first.
        if self._stop.wait(15):
            return

        while not self._stop.is_set():
            try:
                self.run_due_checks()
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "Automatic update monitor failed"
                    )

            self._wake.clear()
            # One-minute scheduler resolution keeps the 30-minute interval
            # accurate without generating unnecessary GitHub requests.
            self._wake.wait(SCHEDULER_WAKE_SECONDS)
            if self._stop.is_set():
                return

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="rackdash-update-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._wake.set()
