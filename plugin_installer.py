from __future__ import annotations
import ast,hashlib,json,re,shutil,time
from pathlib import Path
import requests

MANIFEST_NAME="rackdash-plugin.json"
GITHUB_RE=re.compile(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$",re.I)
def parse_repo(url):
    m=GITHUB_RE.match((url or "").strip());return (m.group(1),m.group(2)) if m else None
def safe_id(v):
    v=re.sub(r"[^a-z0-9_-]","",(v or "").lower())
    if not v or not re.match(r"^[a-z0-9][a-z0-9_-]*$",v):raise ValueError("Invalid plugin id")
    return v
def version_tuple(v):
    nums=re.findall(r"\d+",str(v or ""));return tuple(map(int,nums)) if nums else (0,)
def headers():return {"Accept":"application/vnd.github+json","User-Agent":"RackDash-Plugin-Installer"}

class PluginInstaller:
    def __init__(self,plugin_dir,source_file,rackdash_version="0.0.0"):
        self.plugin_dir=Path(plugin_dir);self.source_file=Path(source_file);self.rackdash_version=rackdash_version
        self.backup_dir=self.plugin_dir.parent/"data"/"plugin_backups"
        self.plugin_dir.mkdir(parents=True,exist_ok=True);self.source_file.parent.mkdir(parents=True,exist_ok=True);self.backup_dir.mkdir(parents=True,exist_ok=True)
    def _sources(self):
        try:return json.loads(self.source_file.read_text(encoding="utf-8"))
        except Exception:return {"plugins":{}}
    def _save(self,p):
        temp=self.source_file.with_suffix(self.source_file.suffix+".tmp")
        temp.write_text(json.dumps(p,indent=2),encoding="utf-8")
        temp.replace(self.source_file)
    def source_for(self,id):return self._sources().get("plugins",{}).get(id)
    def _repo_info(self,url):
        parsed=parse_repo(url)
        if not parsed:raise ValueError("Only GitHub repository URLs are supported")
        owner,repo=parsed;r=requests.get(f"https://api.github.com/repos/{owner}/{repo}",headers=headers(),timeout=8);r.raise_for_status()
        return owner,repo,r.json().get("default_branch") or "main"
    def _raw(self,owner,repo,branch,path):
        r=requests.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path.lstrip('/')}",headers=headers(),timeout=8);r.raise_for_status();return r.content
    def _check_compat(self,m):
        cur=version_tuple(self.rackdash_version)
        if m.get("min_rackdash") and cur<version_tuple(m["min_rackdash"]):raise ValueError(f"Plugin requires RackDash {m['min_rackdash']} or newer.")
        if m.get("max_rackdash") and cur>version_tuple(m["max_rackdash"]):raise ValueError(f"Plugin supports RackDash only through {m['max_rackdash']}.")
    def manifest(self,url):
        owner,repo,branch=self._repo_info(url);data=json.loads(self._raw(owner,repo,branch,MANIFEST_NAME).decode())
        for k in ("id","name","version","entry"):
            if not data.get(k):raise ValueError(f"Manifest missing: {k}")
        data["id"]=safe_id(data["id"]);data["_owner"]=owner;data["_repo"]=repo;data["_branch"]=branch;data["_repo_url"]=f"https://github.com/{owner}/{repo}"
        data.setdefault("capabilities",[]);data.setdefault("min_rackdash","");data.setdefault("max_rackdash","");self._check_compat(data);return data
    def preview(self,url):
        m=self.manifest(url)
        return {k:m.get(k) for k in ("id","name","version","entry","description","capabilities","min_rackdash","max_rackdash")}|{"github_url":m["_repo_url"]}
    def _validate(self,source,m):
        tree=ast.parse(source);const={};funcs=set()
        for n in tree.body:
            if isinstance(n,ast.Assign):
                for t in n.targets:
                    if isinstance(t,ast.Name):
                        try:const[t.id]=ast.literal_eval(n.value)
                        except Exception:pass
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):funcs.add(n.name)
        for k in ("PLUGIN_ID","PLUGIN_NAME","PLUGIN_HTML"):
            if k not in const:raise ValueError(f"Plugin missing {k}")
        if "get_data" not in funcs:raise ValueError("Plugin must define get_data()")
        if str(const["PLUGIN_ID"]).strip()!=m["id"]:raise ValueError("Manifest id does not match PLUGIN_ID")
    def _backup(self,pid,path,reason):
        if not path.exists():return None
        out=self.backup_dir/f"{pid}-{time.strftime('%Y%m%d-%H%M%S')}-{reason}.py";shutil.copy2(path,out);return out
    def install_from_github(self,url):
        m=self.manifest(url);content=self._raw(m["_owner"],m["_repo"],m["_branch"],m["entry"]);source=content.decode();self._validate(source,m)
        pid=m["id"];dest=self.plugin_dir/f"{pid}.py";sources=self._sources();known=sources.setdefault("plugins",{})
        if dest.exists() and pid not in known:raise ValueError(f"{pid}.py already exists and is not installer-managed")
        self._backup(pid,dest,"update")
        temp=dest.with_suffix(".py.new")
        temp.write_text(source,encoding="utf-8")
        temp.replace(dest)
        known[pid]={"github_url":m["_repo_url"],"version":str(m["version"]),"entry":m["entry"],"branch":m["_branch"],"sha256":hashlib.sha256(content).hexdigest(),"installed_at":int(time.time()),"capabilities":m.get("capabilities",[])}
        self._save(sources);return {"id":pid,"name":m["name"],"version":str(m["version"]),"github_url":m["_repo_url"],"restart_required":True}
    def uninstall(self,pid):
        pid=safe_id(pid);sources=self._sources();known=sources.setdefault("plugins",{})
        if pid not in known:raise ValueError("Only installer-managed plugins can be uninstalled here")
        path=self.plugin_dir/f"{pid}.py";self._backup(pid,path,"uninstalled")
        if path.exists():path.unlink()
        known.pop(pid,None);self._save(sources);return {"id":pid,"restart_required":True}
    def backups(self,pid=None):
        pattern=f"{safe_id(pid)}-*.py" if pid else "*.py"
        return [{"name":p.name,"size":p.stat().st_size,"mtime":int(p.stat().st_mtime)} for p in sorted(self.backup_dir.glob(pattern),reverse=True)]
    def rollback(self,pid,backup_name):
        pid=safe_id(pid);backup=self.backup_dir/Path(backup_name).name
        if not backup.exists() or not backup.name.startswith(pid+"-"):raise ValueError("Backup not found")
        dest=self.plugin_dir/f"{pid}.py";self._backup(pid,dest,"pre-rollback");shutil.copy2(backup,dest)
        return {"id":pid,"backup":backup.name,"restart_required":True}
