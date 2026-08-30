from __future__ import annotations
import json, math, threading, time
from pathlib import Path
from typing import Any, Callable
import requests
from config_manager import parse_env, update_schema_values

LOGO_GREEN="#58d67d"
FAILURE_RED="#ff4757"
UPDATE_ORANGE="#ff9f43"

WLED_CONFIG=[
 {"key":"WLED_ENABLED","label":"Enable WLED Lighting","type":"checkbox","default":"false"},
 {"key":"WLED_URL","label":"WLED Device URL","type":"text","default":"http://wled.local","help":"Example: http://192.168.1.50 or http://wled.local"},
 {"key":"WLED_SEGMENT","label":"RackDash Segment","type":"number","default":"0","min":0,"max":31},
 {"key":"WLED_BRIGHTNESS","label":"Brightness","type":"number","default":"35","min":0,"max":100,"step":1},
 {"key":"WLED_STATUS_MODE","label":"Status Animation","type":"select","default":"center_breathe","options":[{"value":"center_breathe","label":"Centered Breathe"},{"value":"solid","label":"Solid"}]},
 {"key":"WLED_BREATHE_SECONDS","label":"Breathe Cycle","type":"number","default":"4.0","min":1,"max":20,"step":0.25},
 {"key":"WLED_BREATHE_SPREAD","label":"Center Spread","type":"number","default":"65","min":10,"max":100,"step":1},
 {"key":"WLED_BREATHE_FLOOR","label":"Edge Glow","type":"number","default":"8","min":0,"max":40,"step":1},
 {"key":"WLED_TRANSITION_MS","label":"Transition","type":"number","default":"350","min":0,"max":65000,"step":50},
 {"key":"WLED_TIMEOUT","label":"Network Timeout","type":"number","default":"3.0","min":0.5,"max":15,"step":0.5},
]
def _truthy(v): return str(v or "").strip().lower() in {"1","true","yes","on"}
def _clamp(v,a,b): return max(a,min(b,v))
def _rgb(v,fb="#000000"):
 s=str(v or "").strip().lstrip("#"); s="".join(c*2 for c in s) if len(s)==3 else s
 if len(s)!=6:s=fb.lstrip("#")
 try:return [int(s[i:i+2],16) for i in (0,2,4)]
 except:return _rgb(fb)
def _hex(v):
 if isinstance(v,(list,tuple)) and len(v)>=3:return "".join(f"{int(_clamp(float(x),0,255)):02X}" for x in v[:3])
 return "".join(f"{x:02X}" for x in _rgb(v))

class WLEDLightingManager:
 CORE_FPS=10
 def __init__(self,config_path:Path,plugin_provider:Callable|None=None,system_state_provider:Callable|None=None,logger=None,session=None):
  self.config_path=Path(config_path);self.plugin_provider=plugin_provider or (lambda:[]);self.system_state_provider=system_state_provider or (lambda:{})
  self.logger=logger;self.session=session or requests.Session();self._stop=threading.Event();self._thread=None
  self._connected=False;self._last_error="";self._last_success=0.;self._info={};self._state={};self._effects=[];self._palettes=[];self._checked=0.
  self._last_key="";self._last_sent=0.;self._active_source="disabled";self._active_effect="off";self._active_color="#000000";self._test_until=0.
 def _cfg(self):
  e=parse_env(self.config_path)
  return {"enabled":_truthy(e.get("WLED_ENABLED","false")),"url":str(e.get("WLED_URL","http://wled.local") or "").strip().rstrip("/"),
   "segment":int(_clamp(float(e.get("WLED_SEGMENT","0") or 0),0,31)),"brightness":int(_clamp(float(e.get("WLED_BRIGHTNESS","35") or 35),0,100)),
   "status_mode":str(e.get("WLED_STATUS_MODE","center_breathe") or "center_breathe"),"breathe_seconds":float(_clamp(float(e.get("WLED_BREATHE_SECONDS","4") or 4),1,20)),
   "breathe_spread":int(_clamp(float(e.get("WLED_BREATHE_SPREAD","65") or 65),10,100)),"breathe_floor":int(_clamp(float(e.get("WLED_BREATHE_FLOOR","8") or 8),0,40)),
   "transition_ms":int(_clamp(float(e.get("WLED_TRANSITION_MS","350") or 350),0,65000)),"timeout":float(_clamp(float(e.get("WLED_TIMEOUT","3") or 3),.5,15))}
 def _request(self,method,path,payload=None):
  c=self._cfg()
  if not c["url"]:raise RuntimeError("WLED URL is not configured.")
  r=self.session.request(method,c["url"]+path,json=payload,timeout=c["timeout"],headers={"User-Agent":"RackDash-WLED/3.1.1"});r.raise_for_status()
  return r.json() if getattr(r,"content",b"") else {}
 def refresh_device(self,force=False):
  n=time.monotonic()
  if not force and n-self._checked<60:return
  x=self._request("GET","/json");self._info=dict(x.get("info") or {});self._state=dict(x.get("state") or {});self._effects=list(x.get("effects") or []);self._palettes=list(x.get("palettes") or [])
  self._checked=n;self._connected=True;self._last_error="";self._last_success=time.time()
 def _geometry(self,segid):
  rows=self._state.get("seg") or [];s=next((x for x in rows if isinstance(x,dict) and int(x.get("id",-1))==segid),{})
  if not s and 0<=segid<len(rows) and isinstance(rows[segid],dict):s=rows[segid]
  start=int(s.get("start",0) or 0);stop=s.get("stop")
  if stop is None:
   total=int((self._info.get("leds") or {}).get("count") or 0);stop=total if total>start else start+1
  stop=max(start+1,int(stop));count=stop-start;center=(count-1)/2
  return {"start":start,"stop":stop,"count":count,"center":center,"center_left":math.floor(center),"center_right":math.ceil(center)}
 def _plugin(self):
  out=[]
  try:rows=self.plugin_provider() or []
  except:rows=[]
  for row in rows:
   if not isinstance(row,dict) or not isinstance(row.get("request"),dict):continue
   q=dict(row["request"])
   for k in list(q):
    if str(k).lower() in {"brightness","bri","global_brightness"}:q.pop(k,None)
   if not q:continue
   q["_plugin_id"]=str(row.get("id") or "plugin");q["_order"]=int(row.get("order") or 100);q["_priority"]=int(_clamp(float(q.get("priority",50) or 50),0,100));out.append(q)
  out.sort(key=lambda x:(-x["_priority"],x["_order"],x["_plugin_id"]))
  return out[0] if out else None
 def _core(self,color,source,c):return {"source":source,"rackdash_core":True,"mode":c["status_mode"],"color":color,"segment":c["segment"],"on":True}
 def _resolve_state(self,c,now):
  if not c["enabled"]:return {"source":"disabled","on":False}
  if now<self._test_until:
   colors=[LOGO_GREEN,UPDATE_ORANGE,FAILURE_RED,"#9146ff","#00bfff"];return self._core(colors[int(now*1.5)%len(colors)],"admin-test",c)
  try:s=self.system_state_provider() or {}
  except:s={}
  if s.get("failure"):return self._core(FAILURE_RED,"system-failure",c)
  if s.get("update"):return self._core(UPDATE_ORANGE,"update-available",c)
  q=self._plugin()
  if q:q["source"]="plugin:"+q["_plugin_id"];q.setdefault("segment",c["segment"]);q.setdefault("on",True);return q
  return self._core(LOGO_GREEN,"rackdash-idle",c)
 def _breathe_pixels(self,color,count,now,c):
  center=(count-1)/2;maxd=max(center,.5);phase=(now%c["breathe_seconds"])/c["breathe_seconds"];temporal=.28+.72*((math.sin(phase*math.tau-math.pi/2)+1)/2)
  spread=c["breathe_spread"]/100;floor=c["breathe_floor"]/100;base=_rgb(color);out=[]
  for i in range(count):
   n=abs(i-center)/maxd;sp=math.exp(-((n/spread)**2)*2.25);f=_clamp((floor+(1-floor)*sp)*temporal,0,1);out.append(_hex([round(x*f) for x in base]))
  return out
 def _idx(self,names,v,fb=0):
  if v is None:return fb
  if isinstance(v,(int,float)) and not isinstance(v,bool):return int(v)
  s=str(v).strip()
  if s.isdigit():return int(s)
  for i,n in enumerate(names):
   if str(n).strip().lower()==s.lower():return i
  return fb
 def _payload(self,state,c,now=None):
  now=time.monotonic() if now is None else now
  if state.get("rackdash_core"):
   g=self._geometry(int(state.get("segment",c["segment"])));seg={"id":int(state.get("segment",c["segment"])),"on":bool(state.get("on",True)),"fx":0,"pal":0}
   if state.get("mode")=="solid":seg["col"]=[_rgb(state.get("color",LOGO_GREEN))]
   else:seg["i"]=self._breathe_pixels(state.get("color",LOGO_GREEN),g["count"],now,c)
   return {"on":True,"bri":round(c["brightness"]*255/100),"tt":0,"v":False,"seg":[seg]}
  p={"on":bool(state.get("on",True)),"bri":round(c["brightness"]*255/100),"tt":round(float(state.get("transition_ms",c["transition_ms"]))/100),"v":False}
  if state.get("preset") is not None:p["ps"]=int(_clamp(float(state["preset"]),1,250));return p
  if isinstance(state.get("playlist"),dict):p["playlist"]=dict(state["playlist"])
  seg={"id":int(_clamp(float(state.get("segment",c["segment"])),0,31)),"on":bool(state.get("on",True)),"fx":self._idx(self._effects,state.get("effect"),0),"pal":self._idx(self._palettes,state.get("palette"),0)}
  if isinstance(state.get("colors"),list):seg["col"]=[_rgb(x) for x in state["colors"][:3]]
  elif state.get("color") is not None:
   seg["col"]=[_rgb(state["color"])]
   for k in ("secondary","tertiary"):
    if state.get(k) is not None:seg["col"].append(_rgb(state[k]))
  for src,dst,lo,hi in [("speed","sx",0,255),("intensity","ix",0,255),("c1","c1",0,255),("c2","c2",0,255),("c3","c3",0,31)]:
   if src in state:seg[dst]=int(_clamp(float(state[src]),lo,hi))
  for src,dst in [("reverse","rev"),("mirror","mi"),("reverse_y","rY"),("mirror_y","mY"),("transpose","tp"),("option1","o1"),("option2","o2"),("option3","o3")]:
   if src in state:seg[dst]=bool(state[src])
  if isinstance(state.get("pixels"),list):seg["i"]=[_hex(x) for x in state["pixels"]]
  p["seg"]=[seg];return p
 def _send(self,state,c,force=False):
  now=time.monotonic();p=self._payload(state,c,now);key=json.dumps(p,sort_keys=True,separators=(",",":"));animated=bool(state.get("rackdash_core") and state.get("mode")!="solid")
  if animated and now-self._last_sent<1/self.CORE_FPS:return
  if not animated and not force and key==self._last_key and now-self._last_sent<60:return
  self._request("POST","/json/state",p);self._last_key=key;self._last_sent=now;self._connected=True;self._last_error="";self._last_success=time.time()
 def _loop(self):
  while not self._stop.is_set():
   c=self._cfg()
   if not c["enabled"]:self._connected=False;self._active_source="disabled";self._stop.wait(1);continue
   try:
    self.refresh_device();s=self._resolve_state(c,time.monotonic());self._active_source=s.get("source","unknown");self._active_color=s.get("color","#000000");self._active_effect="Centered Breathe" if s.get("rackdash_core") and s.get("mode")!="solid" else "Solid" if s.get("rackdash_core") else str(s.get("effect") or ("Preset" if s.get("preset") else "Solid"));self._send(s,c,self._active_source=="admin-test")
   except Exception as exc:self._connected=False;self._last_error=str(exc)[:300]
   self._stop.wait(.04)
 def start(self):
  if self._thread and self._thread.is_alive():return
  self._stop.clear();self._thread=threading.Thread(target=self._loop,name="rackdash-wled",daemon=True);self._thread.start()
 def stop(self):
  self._stop.set()
  if self._thread:self._thread.join(timeout=2)
 def save_settings(self,x):
  vals={"WLED_ENABLED":"true" if x.get("enabled") else "false","WLED_URL":str(x.get("url") or "").strip().rstrip("/"),"WLED_SEGMENT":str(int(_clamp(float(x.get("segment") or 0),0,31))),"WLED_BRIGHTNESS":str(int(_clamp(float(x.get("brightness") or 0),0,100))),"WLED_STATUS_MODE":str(x.get("status_mode") or "center_breathe"),"WLED_BREATHE_SECONDS":str(float(_clamp(float(x.get("breathe_seconds") or 4),1,20))),"WLED_BREATHE_SPREAD":str(int(_clamp(float(x.get("breathe_spread") or 65),10,100))),"WLED_BREATHE_FLOOR":str(int(_clamp(float(x.get("breathe_floor") or 8),0,40))),"WLED_TRANSITION_MS":str(int(_clamp(float(x.get("transition_ms") or 350),0,65000))),"WLED_TIMEOUT":str(float(_clamp(float(x.get("timeout") or 3),.5,15)))}
  update_schema_values(self.config_path,WLED_CONFIG,vals);self._checked=0;self._last_key=""
  if x.get("enabled"):self.refresh_device(True)
  return self.status()
 def test(self):
  if not self._cfg()["enabled"]:raise RuntimeError("Enable WLED lighting first.")
  self.refresh_device(True);self._test_until=time.monotonic()+10;return self.status()
 def device_options(self):
  if self._cfg()["enabled"]:self.refresh_device(True)
  return {"effects":self._effects,"palettes":self._palettes,"info":self._info,"state":self._state,"geometry":self._geometry(self._cfg()["segment"])}
 def status(self):
  c=self._cfg();leds=self._info.get("leds") or {};wifi=self._info.get("wifi") or {};g=self._geometry(c["segment"]) if self._info else {}
  return {**c,"connected":self._connected,"last_error":self._last_error,"last_success":self._last_success,"active_source":self._active_source,"active_effect":self._active_effect,"active_color":self._active_color,"device_name":self._info.get("name") or self._info.get("brand") or "","version":self._info.get("ver") or "","led_count":leds.get("count"),"max_segments":leds.get("maxseg"),"rssi":wifi.get("rssi"),"effect_count":len(self._effects),"palette_count":len(self._palettes),"segment_count":g.get("count"),"segment_start":g.get("start"),"segment_stop":g.get("stop"),"center":g.get("center"),"center_left":g.get("center_left"),"center_right":g.get("center_right")}
