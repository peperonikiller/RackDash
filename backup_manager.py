from __future__ import annotations
import json, shutil, tempfile, time, zipfile
from pathlib import Path

class BackupManager:
    def __init__(self,root):
        self.root=Path(root);self.backup_dir=self.root/"data"/"backups";self.backup_dir.mkdir(parents=True,exist_ok=True)
    def create(self,label="manual"):
        stamp=time.strftime("%Y%m%d-%H%M%S");out=self.backup_dir/f"rackdash-{label}-{stamp}.zip"
        files=[self.root/"config.env",self.root/"data"/"plugin_state.json",self.root/"data"/"plugin_sources.json",self.root/"data"/"admin_auth.json",self.root/"data"/"i2c_icon.png"]
        with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
            z.writestr("backup-manifest.json",json.dumps({"created":int(time.time()),"label":label,"format":1},indent=2))
            for p in files:
                if p.exists() and p.is_file():z.write(p,p.relative_to(self.root))
            for p in (self.root/"plugins").glob("*.py"):
                if p.is_file():z.write(p,p.relative_to(self.root))
        return out
    def list(self):
        return [{"name":p.name,"size":p.stat().st_size,"mtime":int(p.stat().st_mtime)} for p in sorted(self.backup_dir.glob("rackdash-*.zip"),reverse=True)]
    def restore_upload(self,stream):
        with tempfile.TemporaryDirectory(prefix="rackdash-restore-") as td:
            archive=Path(td)/"restore.zip"
            with archive.open("wb") as f:shutil.copyfileobj(stream,f)
            with zipfile.ZipFile(archive) as z:
                if "backup-manifest.json" not in z.namelist():raise ValueError("This does not appear to be a RackDash backup.")
                for name in z.namelist():
                    p=Path(name)
                    if p.is_absolute() or ".." in p.parts:raise ValueError("Unsafe backup path.")
                    if name=="backup-manifest.json":continue
                    if not (name=="config.env" or name.startswith("data/") or (name.startswith("plugins/") and name.endswith(".py"))):continue
                    target=self.root/p;target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(name) as src,target.open("wb") as dest:shutil.copyfileobj(src,dest)
        return {"restart_required":True}
