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
        self.app=app
        self.plugin_dir=Path(plugin_dir)
        self.state_file=Path(state_file) if state_file else self.plugin_dir.parent/"data"/"plugin_state.json"
        self._plugins:list[Plugin]=[]
        self._state={"plugins":{}}

    def _load_state(self):
        import json
        try:
            raw=json.loads(self.state_file.read_text(encoding="utf-8"))
            if "plugins" not in raw:
                disabled=set(raw.get("disabled",[]))
                raw={"plugins":{pid:{"enabled":False} for pid in disabled}}
            self._state=raw
        except Exception:self._state={"plugins":{}}

    def _save_state(self):
        import json
        self.state_file.parent.mkdir(parents=True,exist_ok=True)
        self.state_file.write_text(json.dumps(self._state,indent=2),encoding="utf-8")

    def _settings(self,plugin:Plugin):
        row=self._state.setdefault("plugins",{}).setdefault(plugin.id,{})
        return {
            "enabled":bool(row.get("enabled",True)),
            "show_tab":bool(row.get("show_tab",True)),
            "auto_rotate":bool(row.get("auto_rotate",True)),
            "order":int(row.get("order",plugin.order)),
            "refresh_seconds":max(1,int(row.get("refresh_seconds",plugin.refresh_seconds))),
            "rotation_seconds":max(3,int(row.get("rotation_seconds",12))),
        }

    def update_display_settings(self,plugin_id:str,values:dict):
        plugin=self.get(plugin_id)
        if not plugin:raise ValueError("Unknown plugin")
        row=self._state.setdefault("plugins",{}).setdefault(plugin_id,{})
        for key in ("enabled","show_tab","auto_rotate"):
            if key in values:row[key]=bool(values[key])
        for key in ("order","refresh_seconds","rotation_seconds"):
            if key in values:row[key]=int(values[key])
        self._save_state();return self._settings(plugin)

    def load_all(self):
        self._plugins.clear();self._load_state()
        plugin_path=str(self.plugin_dir)
        if plugin_path not in sys.path:sys.path.insert(0,plugin_path)
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_"):continue
            self._plugins.append(self._load(path))
        self._plugins.sort(key=lambda p:(self._settings(p)["order"],p.name.lower()))
        for plugin in self._plugins:
            register=getattr(plugin.module,"register_routes",None)
            if callable(register):register(self.app)

    def _load(self,path:Path)->Plugin:
        spec=importlib.util.spec_from_file_location(f"rackdash_plugin_{path.stem}",path)
        if spec is None or spec.loader is None:raise RuntimeError(f"Unable to load plugin: {path}")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        plugin_id=str(getattr(module,"PLUGIN_ID","")).strip();name=str(getattr(module,"PLUGIN_NAME","")).strip();html=str(getattr(module,"PLUGIN_HTML","")).strip()
        if not plugin_id or not ID_RE.fullmatch(plugin_id):raise RuntimeError(f"{path.name}: invalid or missing PLUGIN_ID")
        if not name:raise RuntimeError(f"{path.name}: missing PLUGIN_NAME")
        if not html:raise RuntimeError(f"{path.name}: missing PLUGIN_HTML")
        if not callable(getattr(module,"get_data",None)):raise RuntimeError(f"{path.name}: missing get_data()")
        return Plugin(
            module=module,id=plugin_id,name=name,order=int(getattr(module,"PLUGIN_ORDER",100)),
            refresh_seconds=max(1,int(getattr(module,"PLUGIN_REFRESH_SECONDS",10))),
            accent=str(getattr(module,"PLUGIN_ACCENT","#dce8ee")),icon=str(getattr(module,"PLUGIN_ICON","")),
            html=html,css=str(getattr(module,"PLUGIN_CSS","")),js=str(getattr(module,"PLUGIN_JS","")),
            public_error=str(getattr(module,"PLUGIN_PUBLIC_ERROR",f"{name} unavailable")),
            github_url=str(getattr(module,"PLUGIN_GITHUB","")).strip(),
            plugin_version=str(getattr(module,"PLUGIN_VERSION","0.0.0")).strip(),
            config_schema=list(getattr(module,"PLUGIN_CONFIG",[]) or []),
            min_rackdash=str(getattr(module,"PLUGIN_MIN_RACKDASH","")).strip(),
            max_rackdash=str(getattr(module,"PLUGIN_MAX_RACKDASH","")).strip(),
            capabilities=list(getattr(module,"PLUGIN_CAPABILITIES",[]) or []),
            official=bool(getattr(module,"PLUGIN_OFFICIAL",False)),
            source_path=str(getattr(module,"PLUGIN_SOURCE_PATH","")).strip(),
        )

    def get(self,plugin_id:str)->Plugin|None:
        return next((p for p in self._plugins if p.id==plugin_id),None)
    def is_enabled(self,plugin_id:str)->bool:
        p=self.get(plugin_id);return self._settings(p)["enabled"] if p else False
    def set_enabled(self,plugin_id:str,enabled:bool):return self.update_display_settings(plugin_id,{"enabled":enabled})
    def display_settings(self,plugin_id:str):
        p=self.get(plugin_id);return self._settings(p) if p else None

    def public_plugins(self,include_html:bool=True,include_disabled:bool=False,include_hidden:bool=False)->list[dict[str,Any]]:
        rows=[]
        for p in sorted(self._plugins,key=lambda x:(self._settings(x)["order"],x.name.lower())):
            st=self._settings(p)
            if not include_disabled and not st["enabled"]:continue
            if not include_hidden and not st["show_tab"]:continue
            item={"id":p.id,"name":p.name,"order":st["order"],"refresh_seconds":st["refresh_seconds"],"rotation_seconds":st["rotation_seconds"],"auto_rotate":st["auto_rotate"],"show_tab":st["show_tab"],"enabled":st["enabled"],"accent":p.accent,"icon":p.icon,"github_url":p.github_url,"version":p.plugin_version,"config_schema":p.config_schema,"min_rackdash":p.min_rackdash,"max_rackdash":p.max_rackdash,"capabilities":p.capabilities,"official":p.official,"source_path":p.source_path}
            if include_html:item["html"]=p.html
            rows.append(item)
        return rows

    def combined_css(self):return "\n".join(p.css for p in self._plugins if self._settings(p)["enabled"] and self._settings(p)["show_tab"] and p.css)
    def combined_js(self):return "\n".join(p.js for p in self._plugins if self._settings(p)["enabled"] and self._settings(p)["show_tab"] and p.js)

    def configuration_status(self,plugin:Plugin,env_values:dict[str,str]):
        missing=[]
        for field in plugin.config_schema or []:
            if not field.get("required"):continue
            key=str(field.get("key","")).strip()
            if key and not str(env_values.get(key,"")).strip():missing.append(key)
        return {"configured":not missing,"missing":missing}

    def runtime_health(self,plugin:Plugin,env_values:dict[str,str]):
        st=self._settings(plugin);config=self.configuration_status(plugin,env_values)
        if not st["enabled"]:status="disabled"
        elif not config["configured"]:status="unconfigured"
        elif plugin.last_attempt is None:status="waiting"
        elif plugin.last_error:status="error"
        else:status="healthy"
        return {"status":status,"configured":config["configured"],"missing_config":config["missing"],"last_attempt":plugin.last_attempt,"last_success":plugin.last_success,"last_error":plugin.last_error,"response_ms":plugin.response_ms,"consecutive_failures":plugin.consecutive_failures}

    def reload_plugin(self,plugin_id:str):
        plugin=self.get(plugin_id)
        if not plugin:raise ValueError("Unknown plugin")
        new=self._load(Path(plugin.module.__file__))
        new.last_attempt=plugin.last_attempt;new.last_success=plugin.last_success;new.last_error=plugin.last_error;new.response_ms=plugin.response_ms;new.consecutive_failures=plugin.consecutive_failures
        self._plugins[self._plugins.index(plugin)]=new
        return {"id":new.id,"name":new.name,"version":new.plugin_version}
