from __future__ import annotations
import json, threading, time
from pathlib import Path
from typing import Any, Callable
import requests
from config_manager import parse_env, update_schema_values

LOGO_GREEN='#58d67d'; FAILURE_RED='#ff4757'; UPDATE_ORANGE='#ff9f43'
WLED_CONFIG=[
 {'key':'WLED_ENABLED','label':'Enable WLED Lighting','type':'checkbox','default':'false'},
 {'key':'WLED_URL','label':'WLED Device URL','type':'text','default':'http://wled.local','help':'Example: http://192.168.1.50 or http://wled.local'},
 {'key':'WLED_SEGMENT','label':'RackDash Segment','type':'number','default':'0','min':0,'max':31},
 {'key':'WLED_BRIGHTNESS','label':'Brightness','type':'number','default':'35','min':0,'max':100,'step':1},
 {'key':'WLED_STATUS_EFFECT','label':'Status Effect','type':'text','default':'Breathe'},
 {'key':'WLED_STATUS_SPEED','label':'Status Effect Speed','type':'number','default':'96','min':0,'max':255,'step':1},
 {'key':'WLED_STATUS_INTENSITY','label':'Status Effect Intensity','type':'number','default':'128','min':0,'max':255,'step':1},
 {'key':'WLED_TRANSITION_MS','label':'Transition','type':'number','default':'700','min':0,'max':65000,'step':100},
 {'key':'WLED_TIMEOUT','label':'Network Timeout','type':'number','default':'3.0','min':0.5,'max':15,'step':0.5},
]
def _truthy(v): return str(v or '').strip().lower() in {'1','true','yes','on'}
def _clamp(v,a,b): return max(a,min(b,v))
def _rgb(v,fb='#000000'):
 s=str(v or '').strip().lstrip('#'); s=''.join(c*2 for c in s) if len(s)==3 else s
 if len(s)!=6:s=fb.lstrip('#')
 try:return [int(s[i:i+2],16) for i in (0,2,4)]
 except:return _rgb(fb)
def _hex(v):
 if isinstance(v,(list,tuple)) and len(v)>=3:return ''.join(f'{int(_clamp(float(x),0,255)):02X}' for x in v[:3])
 return ''.join(f'{x:02X}' for x in _rgb(v))

class WLEDLightingManager:
 def __init__(self,config_path:Path,plugin_provider:Callable|None=None,system_state_provider:Callable|None=None,logger=None,session=None):
  self.config_path=Path(config_path); self.plugin_provider=plugin_provider or (lambda:[]); self.system_state_provider=system_state_provider or (lambda:{})
  self.logger=logger; self.session=session or requests.Session(); self._stop=threading.Event(); self._thread=None; self._connected=False; self._last_error=''; self._last_success=0.0
  self._info={}; self._effects=[]; self._palettes=[]; self._checked=0.0; self._last_key=''; self._last_sent=0.0; self._active_source='disabled'; self._active_effect='off'; self._active_color='#000000'; self._test_until=0.0
 def _log(self,l,m,*a):
  try:
   f=getattr(self.logger,l,None); f(m,*a) if callable(f) else None
  except:pass
 def _cfg(self):
  e=parse_env(self.config_path)
  return {'enabled':_truthy(e.get('WLED_ENABLED','false')),'url':str(e.get('WLED_URL','http://wled.local') or '').strip().rstrip('/'),'segment':int(_clamp(float(e.get('WLED_SEGMENT','0') or 0),0,31)),'brightness':int(_clamp(float(e.get('WLED_BRIGHTNESS','35') or 35),0,100)),'status_effect':str(e.get('WLED_STATUS_EFFECT','Breathe') or 'Breathe').strip(),'status_speed':int(_clamp(float(e.get('WLED_STATUS_SPEED','96') or 96),0,255)),'status_intensity':int(_clamp(float(e.get('WLED_STATUS_INTENSITY','128') or 128),0,255)),'transition_ms':int(_clamp(float(e.get('WLED_TRANSITION_MS','700') or 700),0,65000)),'timeout':float(_clamp(float(e.get('WLED_TIMEOUT','3') or 3),.5,15))}
 def _request(self,method,path,payload=None):
  c=self._cfg();
  if not c['url']: raise RuntimeError('WLED URL is not configured.')
  r=self.session.request(method,c['url']+path,json=payload,timeout=c['timeout'],headers={'User-Agent':'RackDash-WLED/3.1.0'}); r.raise_for_status(); return r.json() if getattr(r,'content',b'') else {}
 def refresh_device(self,force=False):
  now=time.monotonic()
  if not force and now-self._checked<60:return
  j=self._request('GET','/json'); self._info=dict(j.get('info') or {}); self._effects=list(j.get('effects') or []); self._palettes=list(j.get('palettes') or []); self._checked=now; self._connected=True; self._last_error=''; self._last_success=time.time()
 def _idx(self,names,v,fb=None):
  if v is None:return fb
  if isinstance(v,(int,float)) and not isinstance(v,bool):return int(v)
  s=str(v).strip();
  if s.isdigit():return int(s)
  for i,n in enumerate(names):
   if str(n).strip().lower()==s.lower():return i
  return fb
 def _plugin(self):
  out=[]
  try:rows=self.plugin_provider() or []
  except Exception as e:self._log('warning','WLED plugin provider failed: %s',e); rows=[]
  for row in rows:
   if not isinstance(row,dict) or not isinstance(row.get('request'),dict):continue
   q=dict(row['request'])
   for k in list(q):
    if str(k).lower() in {'brightness','bri','global_brightness'}:q.pop(k,None)
   if not q:continue
   q['_plugin_id']=str(row.get('id') or 'plugin'); q['_order']=int(row.get('order') or 100); q['_priority']=int(_clamp(float(q.get('priority',50) or 50),0,100)); out.append(q)
  if not out:return None
  out.sort(key=lambda x:(-x['_priority'],x['_order'],x['_plugin_id'])); return out[0]
 def _core(self,color,source,c):return {'source':source,'effect':c['status_effect'],'color':color,'speed':c['status_speed'],'intensity':c['status_intensity'],'transition_ms':c['transition_ms'],'segment':c['segment'],'on':True}
 def _resolve_state(self,c,now):
  if not c['enabled']:return {'source':'disabled','on':False}
  if now<self._test_until:
   colors=['#58d67d','#ff9f43','#ff4757','#9146ff','#00bfff']; return {'source':'admin-test','effect':'Breathe','color':colors[int(now*2)%len(colors)],'speed':140,'intensity':160,'transition_ms':150,'segment':c['segment'],'on':True}
  try:s=self.system_state_provider() or {}
  except:s={}
  if s.get('failure'):return self._core(FAILURE_RED,'system-failure',c)
  if s.get('update'):return self._core(UPDATE_ORANGE,'update-available',c)
  p=self._plugin()
  if p:p['source']='plugin:'+p['_plugin_id']; p.setdefault('segment',c['segment']); p.setdefault('transition_ms',c['transition_ms']); p.setdefault('on',True); return p
  return self._core(LOGO_GREEN,'rackdash-idle',c)
 def _segment(self,s,c):
  g={'id':int(_clamp(float(s.get('segment',c['segment'])),0,31)),'on':bool(s.get('on',True))}
  colors=s.get('colors')
  if isinstance(colors,list) and colors:g['col']=[_rgb(x) for x in colors[:3]]
  elif s.get('color') is not None:
   g['col']=[_rgb(s.get('color'))]
   for k in ('secondary','tertiary'):
    if s.get(k) is not None:g['col'].append(_rgb(s[k]))
  fx=self._idx(self._effects,s.get('effect'),self._idx(self._effects,'Breathe',0)); g['fx']=int(fx) if fx is not None else 0
  pal=self._idx(self._palettes,s.get('palette'))
  if pal is not None:g['pal']=int(pal)
  for src,dst,lo,hi in [('speed','sx',0,255),('intensity','ix',0,255),('c1','c1',0,255),('c2','c2',0,255),('c3','c3',0,31)]:
   if src in s:g[dst]=int(_clamp(float(s[src]),lo,hi))
  for src,dst in [('reverse','rev'),('mirror','mi'),('reverse_y','rY'),('mirror_y','mY'),('transpose','tp'),('option1','o1'),('option2','o2'),('option3','o3')]:
   if src in s:g[dst]=bool(s[src])
  if isinstance(s.get('pixels'),list):g['i']=[_hex(x) for x in s['pixels']]
  return g
 def _build_payload(self,s,c):
  p={'on':bool(s.get('on',True)),'bri':int(round(c['brightness']*255/100)),'tt':int(_clamp(float(s.get('transition_ms',c['transition_ms']))/100,0,65535)),'v':False}
  if s.get('preset') is not None:p['ps']=int(_clamp(float(s['preset']),1,250)); return p
  if isinstance(s.get('playlist'),dict):p['playlist']=dict(s['playlist'])
  p['seg']=[self._segment(s,c)]; return p
 def _send(self,s,c,force=False):
  p=self._build_payload(s,c); k=json.dumps(p,sort_keys=True,separators=(',',':')); now=time.monotonic()
  if not force and k==self._last_key and now-self._last_sent<60:return
  self._request('POST','/json/state',p); self._last_key=k; self._last_sent=now; self._connected=True; self._last_error=''; self._last_success=time.time()
 def _loop(self):
  while not self._stop.is_set():
   c=self._cfg()
   if not c['enabled']:self._active_source='disabled'; self._connected=False; self._stop.wait(1); continue
   try:
    self.refresh_device(); s=self._resolve_state(c,time.monotonic()); self._active_source=str(s.get('source') or 'unknown'); self._active_effect=str(s.get('effect') or ('preset' if s.get('preset') else 'solid')); self._active_color=str(s.get('color') or '#000000'); self._send(s,c,force=self._active_source=='admin-test')
   except Exception as e:self._connected=False; self._last_error=str(e)[:300]; self._log('warning','WLED update failed: %s',e)
   self._stop.wait(.5)
 def start(self):
  if self._thread and self._thread.is_alive():return
  self._stop.clear(); self._thread=threading.Thread(target=self._loop,name='rackdash-wled',daemon=True); self._thread.start()
 def stop(self):
  self._stop.set();
  if self._thread and self._thread.is_alive():self._thread.join(timeout=2)
  self._thread=None
 def save_settings(self,p):
  vals={'WLED_ENABLED':'true' if p.get('enabled') else 'false','WLED_URL':str(p.get('url') or '').strip().rstrip('/'),'WLED_SEGMENT':str(int(_clamp(float(p.get('segment') or 0),0,31))),'WLED_BRIGHTNESS':str(int(_clamp(float(p.get('brightness') or 0),0,100))),'WLED_STATUS_EFFECT':str(p.get('status_effect') or 'Breathe').strip(),'WLED_STATUS_SPEED':str(int(_clamp(float(p.get('status_speed') or 96),0,255))),'WLED_STATUS_INTENSITY':str(int(_clamp(float(p.get('status_intensity') or 128),0,255))),'WLED_TRANSITION_MS':str(int(_clamp(float(p.get('transition_ms') or 700),0,65000))),'WLED_TIMEOUT':str(float(_clamp(float(p.get('timeout') or 3),.5,15)))}
  update_schema_values(self.config_path,WLED_CONFIG,vals); self._last_key=''; self._checked=0
  if p.get('enabled'):self.refresh_device(force=True)
  return self.status()
 def test(self):
  if not self._cfg()['enabled']:raise RuntimeError('Enable WLED lighting before running the test.')
  self.refresh_device(force=True); self._test_until=time.monotonic()+8; self._last_key=''; return self.status()
 def device_options(self):
  if self._cfg()['enabled']:self.refresh_device(force=True)
  return {'effects':list(self._effects),'palettes':list(self._palettes),'info':dict(self._info)}
 def status(self):
  c=self._cfg(); leds=self._info.get('leds') or {}; wifi=self._info.get('wifi') or {}
  return {**c,'connected':bool(self._connected),'last_error':self._last_error,'last_success':self._last_success,'active_source':self._active_source,'active_effect':self._active_effect,'active_color':self._active_color,'device_name':self._info.get('name') or self._info.get('brand') or '','version':self._info.get('ver') or '','led_count':leds.get('count'),'max_segments':leds.get('maxseg'),'rssi':wifi.get('rssi'),'effect_count':len(self._effects),'palette_count':len(self._palettes),'logo_green':LOGO_GREEN,'failure_red':FAILURE_RED,'update_orange':UPDATE_ORANGE}
