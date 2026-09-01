from __future__ import annotations
import json, threading, time
from pathlib import Path
from typing import Callable
import requests
from config_manager import parse_env, update_schema_values

WLED_CONFIG=[
 {"key":"WLED_ENABLED","label":"Enable WLED Lighting","type":"checkbox","default":"false"},
 {"key":"WLED_URL","label":"WLED Device URL","type":"text","default":"http://wled.local","help":"Example: http://192.168.1.50 or http://wled.local"},
 {"key":"WLED_HEALTHY_PRESET","label":"Healthy Preset","type":"number","default":"0","min":0,"max":250},
 {"key":"WLED_UPDATE_PRESET","label":"Update Preset","type":"number","default":"0","min":0,"max":250},
 {"key":"WLED_ERROR_PRESET","label":"Error Preset","type":"number","default":"0","min":0,"max":250},
 {"key":"WLED_TIMEOUT","label":"Network Timeout","type":"number","default":"3.0","min":0.5,"max":15,"step":0.5},
]

def _truthy(v):return str(v or '').strip().lower() in {'1','true','yes','on'}
def _clamp(v,a,b):return max(a,min(b,v))

class WLEDLightingManager:
 def __init__(self,config_path:Path,plugin_provider:Callable|None=None,system_state_provider:Callable|None=None,logger=None,session=None):
  self.config_path=Path(config_path);self.plugin_provider=plugin_provider or (lambda:[]);self.system_state_provider=system_state_provider or (lambda:{})
  self.logger=logger;self.session=session or requests.Session();self._stop=threading.Event();self._thread=None
  self._connected=False;self._last_error='';self._last_success=0.;self._info={};self._state={};self._presets=[];self._effects=[];self._palettes=[];self._checked=0.
  self._last_key='';self._last_sent=0.;self._last_state_signature='';self._active_source='disabled';self._active_preset=0;self._active_preset_name='';self._test_until=0.;self._test_started=0.
 def _cfg(self):
  e=parse_env(self.config_path)
  return {
   'enabled':_truthy(e.get('WLED_ENABLED','false')),
   'url':str(e.get('WLED_URL','http://wled.local') or '').strip().rstrip('/'),
   'healthy_preset':int(_clamp(float(e.get('WLED_HEALTHY_PRESET','0') or 0),0,250)),
   'update_preset':int(_clamp(float(e.get('WLED_UPDATE_PRESET','0') or 0),0,250)),
   'error_preset':int(_clamp(float(e.get('WLED_ERROR_PRESET','0') or 0),0,250)),
   'timeout':float(_clamp(float(e.get('WLED_TIMEOUT','3') or 3),.5,15)),
  }
 def _request(self,method,path,payload=None):
  c=self._cfg()
  if not c['url']:raise RuntimeError('WLED URL is not configured.')
  r=self.session.request(method,c['url']+path,json=payload,timeout=c['timeout'],headers={'User-Agent':'RackDash-WLED/3.1.9'});r.raise_for_status()
  return r.json() if getattr(r,'content',b'') else {}
 def _load_presets(self):
  raw=self._request('GET','/presets.json')
  presets=[]
  if isinstance(raw,dict):
   for key,value in raw.items():
    try:pid=int(key)
    except:continue
    if pid<=0 or pid>250 or not isinstance(value,dict):continue
    name=str(value.get('n') or f'Preset {pid}').strip()
    presets.append({'id':pid,'name':name or f'Preset {pid}'})
  presets.sort(key=lambda row:row['id'])
  self._presets=presets
 def refresh_device(self,force=False):
  n=time.monotonic()
  if not force and n-self._checked<60:return
  x=self._request('GET','/json');self._info=dict(x.get('info') or {});self._state=dict(x.get('state') or {});self._effects=list(x.get('effects') or []);self._palettes=list(x.get('palettes') or [])
  try:self._load_presets()
  except Exception as exc:
   self._presets=[]
   if self.logger:self.logger.warning('Unable to load WLED presets: %s',exc)
  self._checked=n;self._connected=True;self._last_error='';self._last_success=time.time()
 def _preset_name(self,preset_id):
  return next((row['name'] for row in self._presets if row['id']==int(preset_id or 0)),'')
 def _plugin(self):
  out=[]
  try:rows=self.plugin_provider() or []
  except:rows=[]
  for row in rows:
   if not isinstance(row,dict) or not isinstance(row.get('request'),dict):continue
   q=dict(row['request'])
   if not q:continue
   q['_plugin_id']=str(row.get('id') or 'plugin');q['_order']=int(row.get('order') or 100);q['_priority']=int(_clamp(float(q.get('priority',50) or 50),0,100));out.append(q)
  out.sort(key=lambda x:(-x['_priority'],x['_order'],x['_plugin_id']))
  return out[0] if out else None
 def _preset_state(self,preset,source):return {'source':source,'preset':int(preset or 0),'rackdash_core':True,'on':True}
 def _resolve_state(self,c,now):
  if not c['enabled']:return {'source':'disabled','on':False}
  if now<self._test_until:
   choices=[c['healthy_preset'],c['update_preset'],c['error_preset']]
   preset=choices[min(2,int(max(0,now-self._test_started)/3))]
   return self._preset_state(preset,'admin-test')
  try:s=self.system_state_provider() or {}
  except:s={}
  if s.get('failure'):return self._preset_state(c['error_preset'],'system-failure')
  if s.get('update'):return self._preset_state(c['update_preset'],'update-available')
  q=self._plugin()
  if q:q['source']='plugin:'+q['_plugin_id'];q.setdefault('on',True);return q
  return self._preset_state(c['healthy_preset'],'rackdash-idle')
 def _payload(self,state,c):
  # RackDash core states now only select WLED presets. WLED owns all color,
  # brightness, effects, segments, transitions and animation timing.
  if state.get('rackdash_core'):
   preset=int(_clamp(float(state.get('preset') or 0),0,250))
   if preset<=0:return None
   return {'ps':preset,'v':False}
  # Plugin requests retain the existing WLED JSON contract. Presets remain the
  # simplest/recommended plugin path, but existing effect/palette requests
  # continue to work.
  if state.get('preset') is not None:
   preset=int(_clamp(float(state.get('preset') or 0),0,250))
   return {'ps':preset,'v':False} if preset>0 else None
  payload={'on':bool(state.get('on',True)),'v':False}
  if isinstance(state.get('playlist'),dict):payload['playlist']=dict(state['playlist'])
  segment={}
  if state.get('segment') is not None:segment['id']=int(_clamp(float(state['segment']),0,31))
  def resolve_index(values,value,default=0):
   if value is None:return default
   try:return int(value)
   except:pass
   wanted=str(value).strip().lower()
   for index,name in enumerate(values):
    if str(name).strip().lower()==wanted:return index
   return default
  if state.get('effect') is not None:segment['fx']=resolve_index(self._effects,state.get('effect'),0)
  if state.get('palette') is not None:segment['pal']=resolve_index(self._palettes,state.get('palette'),0)
  for src,dst,lo,hi in [('speed','sx',0,255),('intensity','ix',0,255),('c1','c1',0,255),('c2','c2',0,255),('c3','c3',0,31)]:
   if src in state:
    try:segment[dst]=int(_clamp(float(state[src]),lo,hi))
    except:pass
  for src,dst in [('reverse','rev'),('mirror','mi'),('reverse_y','rY'),('mirror_y','mY'),('transpose','tp'),('option1','o1'),('option2','o2'),('option3','o3')]:
   if src in state:segment[dst]=bool(state[src])
  colors=state.get('colors') if isinstance(state.get('colors'),list) else None
  if colors is None and state.get('color') is not None:
   colors=[state.get('color')]
   if state.get('secondary') is not None:colors.append(state.get('secondary'))
   if state.get('tertiary') is not None:colors.append(state.get('tertiary'))
  if colors:
   converted=[]
   for value in colors[:3]:
    h=str(value or '').strip().lstrip('#')
    if len(h)==6:
     try:converted.append([int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)])
     except:pass
   if converted:segment['col']=converted
  if isinstance(state.get('pixels'),list):
   segment['i']=state['pixels']
  if segment:payload['seg']=[segment]
  return payload
 def _send(self,state,c,force=False):
  payload=self._payload(state,c)
  if payload is None:return
  now=time.monotonic();key=json.dumps(payload,sort_keys=True,separators=(',',':'))
  if not force and key==self._last_key and now-self._last_sent<60:return
  self._request('POST','/json/state',payload);self._last_key=key;self._last_sent=now;self._connected=True;self._last_error='';self._last_success=time.time()
 def _loop(self):
  while not self._stop.is_set():
   c=self._cfg()
   if not c['enabled']:
    self._connected=False;self._active_source='disabled';self._active_preset=0;self._active_preset_name='';self._stop.wait(1);continue
   try:
    self.refresh_device();state=self._resolve_state(c,time.monotonic());self._active_source=state.get('source','unknown')
    self._active_preset=int(state.get('preset') or 0);self._active_preset_name=self._preset_name(self._active_preset)
    signature=f"{self._active_source}:{self._active_preset}"
    changed=signature!=self._last_state_signature
    self._send(state,c,self._active_source=='admin-test' or changed)
    self._last_state_signature=signature
   except Exception as exc:
    self._connected=False;self._last_error=str(exc)[:300]
   self._stop.wait(.5)
 def start(self):
  if self._thread and self._thread.is_alive():return
  self._stop.clear();self._thread=threading.Thread(target=self._loop,name='rackdash-wled',daemon=True);self._thread.start()
 def stop(self):
  self._stop.set()
  if self._thread:self._thread.join(timeout=2)
 def apply_current_state(self,force=True):
  c=self._cfg()
  if not c['enabled']:
   self._active_source='disabled';self._active_preset=0;self._active_preset_name=''
   return self.status()
  self.refresh_device(True)
  state=self._resolve_state(c,time.monotonic())
  self._active_source=state.get('source','unknown')
  self._active_preset=int(state.get('preset') or 0)
  self._active_preset_name=self._preset_name(self._active_preset)
  self._send(state,c,force)
  self._last_state_signature=f"{self._active_source}:{self._active_preset}"
  return self.status()

 def save_settings(self,x):
  vals={
   'WLED_ENABLED':'true' if x.get('enabled') else 'false',
   'WLED_URL':str(x.get('url') or '').strip().rstrip('/'),
   'WLED_HEALTHY_PRESET':str(int(_clamp(float(x.get('healthy_preset') or 0),0,250))),
   'WLED_UPDATE_PRESET':str(int(_clamp(float(x.get('update_preset') or 0),0,250))),
   'WLED_ERROR_PRESET':str(int(_clamp(float(x.get('error_preset') or 0),0,250))),
   'WLED_TIMEOUT':str(float(_clamp(float(x.get('timeout') or 3),.5,15))),
  }
  update_schema_values(self.config_path,WLED_CONFIG,vals);self._checked=0;self._last_key=''
  if x.get('enabled'):
   self.refresh_device(True)
   configured=[vals['WLED_HEALTHY_PRESET'],vals['WLED_UPDATE_PRESET'],vals['WLED_ERROR_PRESET']]
   if all(int(v or 0)>0 for v in configured):
    return self.apply_current_state(True)
  return self.status()
 def test(self):
  c=self._cfg()
  if not c['enabled']:raise RuntimeError('Enable WLED lighting first.')
  missing=[name for name,key in [('Healthy','healthy_preset'),('Update','update_preset'),('Error','error_preset')] if not c[key]]
  if missing:raise RuntimeError('Configure all three WLED presets before testing.')
  self.refresh_device(True);self._test_started=time.monotonic();self._test_until=self._test_started+9;self._last_key='';return self.status()
 def device_options(self):
  if self._cfg()['enabled']:self.refresh_device(True)
  return {'presets':list(self._presets),'info':dict(self._info),'state':dict(self._state),'current_preset':int((self._state or {}).get('ps') or 0),'configured':self._cfg()}
 def status(self):
  c=self._cfg();leds=self._info.get('leds') or {};wifi=self._info.get('wifi') or {}
  return {**c,'connected':self._connected,'last_error':self._last_error,'last_success':self._last_success,'active_source':self._active_source,'active_preset':self._active_preset,'active_preset_name':self._active_preset_name,'device_name':self._info.get('name') or self._info.get('brand') or '', 'version':self._info.get('ver') or '', 'led_count':leds.get('count'),'rssi':wifi.get('rssi'),'preset_count':len(self._presets)}
