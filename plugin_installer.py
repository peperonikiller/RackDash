from __future__ import annotations
import ast, hashlib, json, re, shutil, time
from pathlib import Path
import requests

MANIFEST_NAME="rackdash-plugin.json"
GITHUB_RE=re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$",re.I)

def parse_repo(url):
    m=GITHUB_RE.match((url or "").strip())
    return (m.group(1),m.group(2)) if m else None

def safe_id(v):
    v=re.sub(r"[^a-z0-9_-]","",(v or "").lower())
    if not v or not re.match(r"^[a-z0-9][a-z0-9_-]*$",v): raise ValueError("Invalid plugin id")
    return v

def headers(): return {"Accept":"application/vnd.github+json","User-Agent":"RackDash-Plugin-Installer"}

def default_branch(owner,repo):
    r=requests.get(f"https://api.github.com/repos/{owner}/{repo}",headers=headers(),timeout=8);r.raise_for_status()
    return r.json().get("default_branch") or "main"

def raw(owner,repo,branch,path):
    r=requests.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path.lstrip('/')}",headers=headers(),timeout=8)
    r.raise_for_status();return r.content

def manifest(repo_url):
    parsed=parse_repo(repo_url)
    if not parsed: raise ValueError("Only GitHub repository URLs are supported")
    owner,repo=parsed;branch=default_branch(owner,repo)
    data=json.loads(raw(owner,repo,branch,MANIFEST_NAME).decode("utf-8"))
    for key in ("id","name","version","entry"):
        if not data.get(key): raise ValueError(f"Manifest missing: {key}")
    data["id"]=safe_id(data["id"]);data["_owner"]=owner;data["_repo"]=repo;data["_branch"]=branch
    data["_repo_url"]=f"https://github.com/{owner}/{repo}"
    return data

def validate(source,man):
    tree=ast.parse(source);const={};funcs=set()
    for node in tree.body:
        if isinstance(node,ast.Assign):
            for t in node.targets:
                if isinstance(t,ast.Name) and isinstance(node.value,ast.Constant): const[t.id]=node.value.value
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): funcs.add(node.name)
    for k in ("PLUGIN_ID","PLUGIN_NAME","PLUGIN_HTML"):
        if k not in const: raise ValueError(f"Plugin missing {k}")
    if "get_data" not in funcs: raise ValueError("Plugin must define get_data()")
    if str(const["PLUGIN_ID"]).strip()!=man["id"]: raise ValueError("Manifest id does not match PLUGIN_ID")

class PluginInstaller:
    def __init__(self,plugin_dir,source_file):
        self.plugin_dir=Path(plugin_dir);self.source_file=Path(source_file)
        self.plugin_dir.mkdir(parents=True,exist_ok=True);self.source_file.parent.mkdir(parents=True,exist_ok=True)
    def _sources(self):
        try:return json.loads(self.source_file.read_text(encoding="utf-8"))
        except Exception:return {"plugins":{}}
    def _save(self,p): self.source_file.write_text(json.dumps(p,indent=2),encoding="utf-8")
    def source_for(self,id): return self._sources().get("plugins",{}).get(id)
    def install_from_github(self,url):
        man=manifest(url);content=raw(man["_owner"],man["_repo"],man["_branch"],man["entry"]);source=content.decode("utf-8");validate(source,man)
        pid=man["id"];dest=self.plugin_dir/f"{pid}.py";sources=self._sources();known=sources.setdefault("plugins",{})
        if dest.exists() and pid not in known: raise ValueError(f"{pid}.py already exists and is not installer-managed")
        if dest.exists():
            b=self.plugin_dir.parent/"data"/"plugin_backups";b.mkdir(parents=True,exist_ok=True)
            shutil.copy2(dest,b/f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}.py")
        dest.write_text(source,encoding="utf-8")
        known[pid]={"github_url":man["_repo_url"],"version":str(man["version"]),"entry":man["entry"],"branch":man["_branch"],"sha256":hashlib.sha256(content).hexdigest(),"installed_at":int(time.time())}
        self._save(sources)
        return {"id":pid,"name":man["name"],"version":str(man["version"]),"github_url":man["_repo_url"],"restart_required":True}
    def uninstall(self,pid):
        pid=safe_id(pid);sources=self._sources();known=sources.setdefault("plugins",{})
        if pid not in known: raise ValueError("Only installer-managed plugins can be uninstalled here")
        path=self.plugin_dir/f"{pid}.py"
        if path.exists():
            b=self.plugin_dir.parent/"data"/"plugin_backups";b.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,b/f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}-uninstalled.py");path.unlink()
        known.pop(pid,None);self._save(sources)
        return {"id":pid,"restart_required":True}
