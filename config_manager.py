from __future__ import annotations
import os
from pathlib import Path

SENSITIVE_TYPES={"password","secret","token"}

def parse_env(path:Path)->dict[str,str]:
    out={}
    if not path.exists(): return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1);out[k.strip()]=v.strip()
    return out

def write_all(path:Path,values:dict[str,str]):
    lines=["# RackDash configuration"]
    for k,v in sorted(values.items()):
        lines.append(f"{k}={v}")
    lines.append("")
    path.write_text("\n".join(lines),encoding="utf-8")
    os.chmod(path,0o600)

def ensure_defaults(path:Path,schemas):
    current=parse_env(path);changed=False
    for _,fields in schemas:
        for field in fields or []:
            key=str(field.get("key","")).strip()
            if key and key not in current:
                current[key]=str(field.get("default",""));changed=True
    if changed: write_all(path,current)
    return changed

def schema_values(path:Path,schema:list[dict])->list[dict]:
    current=parse_env(path);rows=[]
    for raw in schema or []:
        field=dict(raw);key=str(field.get("key","")).strip()
        if not key: continue
        field["value"]=current.get(key,str(field.get("default","")))
        rows.append(field)
    return rows

def update_schema_values(path:Path,schema:list[dict],submitted:dict[str,str]):
    current=parse_env(path)
    allowed={str(f.get("key","")).strip() for f in schema or []}
    for key,val in submitted.items():
        if key in allowed:
            current[key]=str(val)
    write_all(path,current)
