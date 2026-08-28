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
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+".tmp")
    temp.write_text("\n".join(lines),encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(path)
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

def schema_values(path:Path,schema:list[dict],mask_sensitive:bool=True)->list[dict]:
    current=parse_env(path);rows=[]
    sensitive={"password","secret","token"}
    for raw in schema or []:
        field=dict(raw);key=str(field.get("key","")).strip()
        if not key:continue
        value=current.get(key,str(field.get("default","")))
        if mask_sensitive and field.get("type") in sensitive and value:
            value="********"
        field["value"]=value;rows.append(field)
    return rows

def _validate(field,value):
    kind=field.get("type","text")
    if field.get("required") and not str(value).strip():raise ValueError(f"{field.get('label',field.get('key'))} is required.")
    if kind=="number" and str(value).strip():
        num=float(value)
        if "min" in field and num<float(field["min"]):raise ValueError(f"{field.get('label')} must be at least {field['min']}.")
        if "max" in field and num>float(field["max"]):raise ValueError(f"{field.get('label')} must be at most {field['max']}.")
    if field.get("pattern") and str(value).strip():
        import re
        if not re.fullmatch(field["pattern"],str(value)):raise ValueError(field.get("validation_message") or f"{field.get('label')} has an invalid value.")
    return str(value)

def update_schema_values(path:Path,schema:list[dict],submitted:dict[str,str]):
    current=parse_env(path);fields={str(f.get("key","")).strip():f for f in schema or []}
    for key,val in submitted.items():
        if key in fields:
            if fields[key].get("type") in {"password","secret","token"} and str(val)=="********":
                continue
            current[key]=_validate(fields[key],val)
    write_all(path,current)
