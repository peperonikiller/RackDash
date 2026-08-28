from __future__ import annotations
import os,platform,shutil,subprocess,sys
from pathlib import Path
def _cmd(args,default="unknown"):
    try:return subprocess.run(args,capture_output=True,text=True,timeout=3).stdout.strip() or default
    except Exception:return default
def diagnostics(root):
    root=Path(root)
    return {"python":sys.version.split()[0],"platform":platform.platform(),"machine":platform.machine(),"hostname":platform.node(),"systemd":_cmd(["systemctl","is-active","rackdash.service"]),"chromium":_cmd(["pgrep","-a","chromium"],"not detected"),"i2c_devices":_cmd(["bash","-lc","command -v i2cdetect >/dev/null && i2cdetect -y 1 || echo unavailable"]),"disk_free_gb":round(shutil.disk_usage(root).free/1024**3,2),"root":str(root),"uid":os.getuid() if hasattr(os,"getuid") else None}
def tail_file(path,lines=200):
    path=Path(path)
    if not path.exists():return []
    with path.open("r",encoding="utf-8",errors="replace") as f:data=f.readlines()
    return [x.rstrip("\n") for x in data[-max(1,min(int(lines),1000)):]]
