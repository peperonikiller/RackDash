from __future__ import annotations
import shutil,tempfile,zipfile
from pathlib import Path
import requests

class CoreUpdater:
    def __init__(self,root,github_repo,backup_manager):
        self.root=Path(root);self.github_repo=github_repo.rstrip("/");self.backups=backup_manager
    def _repo(self):
        p=self.github_repo.split("/");return p[-2],p[-1]
    def latest_release(self):
        owner,repo=self._repo();r=requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest",headers={"Accept":"application/vnd.github+json","User-Agent":"RackDash-Updater"},timeout=10)
        if r.status_code==404:return None
        r.raise_for_status();return r.json()
    def apply_latest(self):
        release=self.latest_release()
        if not release:raise ValueError("No GitHub release is available yet.")
        assets=[a for a in release.get("assets",[]) if str(a.get("name","")).lower().endswith(".zip") and "rackdash" in str(a.get("name","")).lower()]
        if not assets:raise ValueError("Latest release has no RackDash .zip asset.")
        self.backups.create("pre-core-update")
        with tempfile.TemporaryDirectory(prefix="rackdash-update-") as td:
            archive=Path(td)/"release.zip";r=requests.get(assets[0]["browser_download_url"],timeout=60);r.raise_for_status();archive.write_bytes(r.content)
            extract=Path(td)/"extract";extract.mkdir()
            with zipfile.ZipFile(archive) as z:
                for n in z.namelist():
                    p=Path(n)
                    if p.is_absolute() or ".." in p.parts:raise ValueError("Unsafe release archive.")
                z.extractall(extract)
            candidate=extract
            roots=[p for p in extract.iterdir() if p.is_dir()]
            if len(roots)==1:candidate=roots[0]
            if not (candidate/"app.py").exists():
                found=list(extract.glob("*/app.py"))
                if found:candidate=found[0].parent
            if not (candidate/"app.py").exists():raise ValueError("Release asset does not contain RackDash app.py.")
            preserve={"config.env","data","venv",".git"}
            for item in candidate.iterdir():
                if item.name in preserve:continue
                target=self.root/item.name
                if item.name=="plugins" and item.is_dir():
                    target.mkdir(exist_ok=True)
                    for pf in item.glob("*.py"):shutil.copy2(pf,target/pf.name)
                    if (item/"examples").exists():
                        if (target/"examples").exists():shutil.rmtree(target/"examples")
                        shutil.copytree(item/"examples",target/"examples")
                    continue
                if target.exists():
                    if target.is_dir():shutil.rmtree(target)
                    else:target.unlink()
                shutil.copytree(item,target) if item.is_dir() else shutil.copy2(item,target)
        return {"version":release.get("tag_name") or release.get("name"),"restart_required":True}
