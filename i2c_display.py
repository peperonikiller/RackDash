from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from typing import Callable

import psutil
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config_manager import parse_env, update_schema_values


DISPLAY_TYPES = {
    "sh1106_128x64": {
        "label": "SH1106 / SSH1106 · 128×64",
        "driver": "sh1106",
        "width": 128,
        "height": 64,
        "monochrome": True,
    },
    "sh1107_128x64": {
        "label": "SH1107 · 128×64",
        "driver": "sh1107",
        "width": 128,
        "height": 64,
        "monochrome": True,
    },
    "ssd1306_128x64": {
        "label": "SSD1306 · 128×64",
        "driver": "ssd1306",
        "width": 128,
        "height": 64,
        "monochrome": True,
    },
    "ssd1306_128x32": {
        "label": "SSD1306 · 128×32",
        "driver": "ssd1306",
        "width": 128,
        "height": 32,
        "monochrome": True,
    },
    "ssd1309_128x64": {
        "label": "SSD1309 · 128×64",
        "driver": "ssd1309",
        "width": 128,
        "height": 64,
        "monochrome": True,
    },
    "ssd1325_128x64": {
        "label": "SSD1325 · 128×64",
        "driver": "ssd1325",
        "width": 128,
        "height": 64,
        "monochrome": False,
    },
    "ssd1327_128x128": {
        "label": "SSD1327 · 128×128",
        "driver": "ssd1327",
        "width": 128,
        "height": 128,
        "monochrome": False,
    },
}

I2C_CONFIG = [
    {"key":"I2C_ENABLED","label":"Enable I2C Display","type":"checkbox","default":"false"},
    {
        "key":"I2C_DISPLAY","label":"Display Controller / Size","type":"select",
        "default":"sh1106_128x64",
        "options":[{"value":key,"label":value["label"]} for key,value in DISPLAY_TYPES.items()]
    },
    {
        "key":"I2C_MODE","label":"Display Mode","type":"select","default":"system",
        "options":[
            {"value":"system","label":"System Only"},
            {"value":"system_plugin","label":"System + Plugins"},
            {"value":"icon","label":"Static Icon"},
        ]
    },
    {"key":"I2C_BUS","label":"I2C Bus","type":"number","default":"1","help":"Raspberry Pi 4/5 normally uses bus 1."},
    {"key":"I2C_ADDRESS","label":"I2C Address","type":"text","default":"0x3C","help":"Most small OLED modules use 0x3C or 0x3D."},
    {"key":"I2C_ROTATE_SECONDS","label":"System/Plugin Rotation Seconds","type":"number","default":"8"},
    {
        "key":"I2C_CONTRAST","label":"Contrast","type":"number","default":"255",
        "help":"0–255 where supported by the controller."
    },
]


def _bool(value: str) -> bool:
    return str(value).strip().lower() in {"1","true","yes","on"}


def _address(value: str) -> int:
    return int(str(value).strip(), 0)


def _font():
    # Pillow's built-in font is deliberately used: no system font dependency.
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> str:
    text=str(text)
    if draw.textlength(text,font=_font()) <= max_width:
        return text
    while text and draw.textlength(text+"…",font=_font()) > max_width:
        text=text[:-1]
    return text+"…" if text else ""


def _system_snapshot():
    try:
        temp_values=psutil.sensors_temperatures()
        temp=next((items[0].current for items in temp_values.values() if items),None)
    except Exception:
        temp=None
    if temp is None:
        try:
            temp=int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip())/1000
        except Exception:
            temp=None

    ip="127.0.0.1"
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.connect(("1.1.1.1",80));ip=sock.getsockname()[0]
    except OSError:
        pass
    finally:
        sock.close()

    disk=psutil.disk_usage("/").percent
    return {
        "ip":ip,
        "cpu":psutil.cpu_percent(interval=None),
        "ram":psutil.virtual_memory().percent,
        "temp":temp,
        "disk":disk,
        "uptime":int(time.time()-psutil.boot_time()),
    }


class I2CDisplayManager:
    def __init__(self, config_path: Path, plugin_provider: Callable):
        self.config_path=Path(config_path)
        self.plugin_provider=plugin_provider
        self.icon_path=self.config_path.parent/"data"/"i2c_icon.png"
        self._device=None
        self._thread=None
        self._stop=threading.Event()
        self._lock=threading.RLock()
        self._last_error=""
        self._last_render=None
        self._active_source="system"
        self._plugin_index=0
        self._last_switch=0.0
        self.reconfigure()

    def config(self):
        values=parse_env(self.config_path)
        key=values.get("I2C_DISPLAY","sh1106_128x64")
        spec=DISPLAY_TYPES.get(key,DISPLAY_TYPES["sh1106_128x64"])
        return {
            "enabled":_bool(values.get("I2C_ENABLED","false")),
            "display":key,
            "mode":values.get("I2C_MODE","system"),
            "bus":int(values.get("I2C_BUS","1") or 1),
            "address":values.get("I2C_ADDRESS","0x3C"),
            "rotate_seconds":max(2,int(values.get("I2C_ROTATE_SECONDS","8") or 8)),
            "contrast":max(0,min(255,int(values.get("I2C_CONTRAST","255") or 255))),
            "width":spec["width"],
            "height":spec["height"],
            "label":spec["label"],
        }

    def status(self):
        cfg=self.config()
        return {
            **cfg,
            "connected":self._device is not None,
            "last_error":self._last_error,
            "last_render":self._last_render,
            "active_source":self._active_source,
            "icon_exists":self.icon_path.exists(),
            "dependencies":self._dependency_status(),
        }

    def _dependency_status(self):
        try:
            import luma.oled  # noqa
            return {"ok":True,"message":"luma.oled available"}
        except Exception:
            return {"ok":False,"message":"Install luma.oled (included in requirements.txt)"}

    def reconfigure(self):
        with self._lock:
            self._device=None
            self._last_error=""
            cfg=self.config()
            if not cfg["enabled"]:
                return
            try:
                from luma.core.interface.serial import i2c
                from luma.oled import device as devices

                spec=DISPLAY_TYPES[cfg["display"]]
                klass=getattr(devices,spec["driver"])
                serial=i2c(port=cfg["bus"],address=_address(cfg["address"]))
                kwargs={"width":spec["width"],"height":spec["height"]}
                try:
                    device=klass(serial,**kwargs)
                except TypeError:
                    device=klass(serial)
                try:
                    device.contrast(cfg["contrast"])
                except Exception:
                    pass
                self._device=device
            except Exception as exc:
                self._last_error=str(exc)[:300]

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,name="rackdash-i2c",daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(2.0):
            try:
                self.render_next()
            except Exception as exc:
                self._last_error=str(exc)[:300]

    def save_settings(self, values: dict):
        submitted={
            "I2C_ENABLED":str(values.get("enabled","false")).lower(),
            "I2C_DISPLAY":str(values.get("display","sh1106_128x64")),
            "I2C_MODE":str(values.get("mode","system")),
            "I2C_BUS":str(values.get("bus","1")),
            "I2C_ADDRESS":str(values.get("address","0x3C")),
            "I2C_ROTATE_SECONDS":str(values.get("rotate_seconds","8")),
            "I2C_CONTRAST":str(values.get("contrast","255")),
        }
        update_schema_values(self.config_path,I2C_CONFIG,submitted)
        self.reconfigure()
        return self.status()

    def save_icon(self, upload):
        cfg=self.config()
        image=Image.open(upload.stream)
        if image.width>cfg["width"] or image.height>cfg["height"]:
            raise ValueError(
                f"Image is {image.width}×{image.height}; selected display allows at most "
                f"{cfg['width']}×{cfg['height']}."
            )
        # Flatten transparency onto black, convert to grayscale, then dither to
        # one-bit monochrome. This preserves detail better than a hard threshold.
        rgba=image.convert("RGBA")
        background=Image.new("RGBA",rgba.size,(0,0,0,255))
        background.alpha_composite(rgba)
        mono=background.convert("L").convert("1",dither=Image.Dither.FLOYDSTEINBERG)
        canvas=Image.new("1",(cfg["width"],cfg["height"]),0)
        x=(cfg["width"]-mono.width)//2
        y=(cfg["height"]-mono.height)//2
        canvas.paste(mono,(x,y))
        self.icon_path.parent.mkdir(parents=True,exist_ok=True)
        canvas.save(self.icon_path)
        return {"width":image.width,"height":image.height,"stored_width":cfg["width"],"stored_height":cfg["height"]}

    def _system_image(self):
        cfg=self.config();s=_system_snapshot()
        image=Image.new("1",(cfg["width"],cfg["height"]),0)
        draw=ImageDraw.Draw(image)
        font=_font()

        if cfg["height"]<=32:
            draw.text((0,0),_fit_text(draw,f"IP {s['ip']}",cfg["width"]),font=font,fill=1)
            line=f"CPU {s['cpu']:.0f}%"
            if s["temp"] is not None: line+=f" {s['temp']:.0f}C"
            draw.text((0,12),_fit_text(draw,line,cfg["width"]),font=font,fill=1)
            draw.text((0,23),_fit_text(draw,f"RAM {s['ram']:.0f}% DISK {s['disk']:.0f}%",cfg["width"]),font=font,fill=1)
        else:
            draw.text((0,0),"RackDash",font=font,fill=1)
            draw.line((0,10,cfg["width"]-1,10),fill=1)
            draw.text((0,14),_fit_text(draw,f"IP   {s['ip']}",cfg["width"]),font=font,fill=1)
            draw.text((0,26),f"CPU  {s['cpu']:.0f}%   RAM {s['ram']:.0f}%",font=font,fill=1)
            temp="--" if s["temp"] is None else f"{s['temp']:.0f}C"
            draw.text((0,38),f"TEMP {temp}   DISK {s['disk']:.0f}%",font=font,fill=1)
            days=s["uptime"]//86400;hours=(s["uptime"]%86400)//3600
            draw.text((0,50),f"UP   {days}d {hours}h",font=font,fill=1)
        return image

    def _plugin_frames(self):
        frames=[]
        for plugin in self.plugin_provider():
            if not getattr(plugin.module,"get_i2c_data",None):
                continue
            try:
                payload=plugin.module.get_i2c_data()
                if payload:
                    frames.append((plugin,payload))
            except Exception:
                continue
        return frames

    def _plugin_image(self, plugin, payload):
        cfg=self.config()
        image=Image.new("1",(cfg["width"],cfg["height"]),0)
        draw=ImageDraw.Draw(image);font=_font()
        lines=payload.get("lines") or []
        if isinstance(lines,str): lines=[lines]
        title=payload.get("title") or plugin.name
        icon=payload.get("icon")

        if icon:
            path=Path(icon)
            if not path.is_absolute():
                path=Path(plugin.module.__file__).resolve().parent/path
            try:
                icon_img=Image.open(path).convert("L").convert("1")
                if not lines:
                    icon_img.thumbnail((cfg["width"],cfg["height"]))
                    image.paste(icon_img,((cfg["width"]-icon_img.width)//2,(cfg["height"]-icon_img.height)//2))
                    return image
                max_icon=min(cfg["height"]-2,32)
                icon_img.thumbnail((max_icon,max_icon))
                image.paste(icon_img,(0,0))
                text_x=icon_img.width+4
            except Exception:
                text_x=0
        else:
            text_x=0

        draw.text((text_x,0),_fit_text(draw,str(title),cfg["width"]-text_x),font=font,fill=1)
        y=13
        for line in lines:
            if y+8>cfg["height"]: break
            draw.text((0,y),_fit_text(draw,str(line),cfg["width"]),font=font,fill=1)
            y+=11
        return image

    def render_next(self):
        with self._lock:
            cfg=self.config()
            if not cfg["enabled"] or self._device is None:
                return

            if cfg["mode"]=="icon":
                if not self.icon_path.exists():
                    image=self._system_image();source="system (icon missing)"
                else:
                    image=Image.open(self.icon_path).convert("1");source="icon"
            elif cfg["mode"]=="system_plugin":
                frames=self._plugin_frames()
                slots=[("system",None,None)]+[("plugin",p,payload) for p,payload in frames]
                now=time.time()
                if now-self._last_switch>=cfg["rotate_seconds"]:
                    self._plugin_index=(self._plugin_index+1)%max(1,len(slots))
                    self._last_switch=now
                kind,plugin,payload=slots[self._plugin_index%len(slots)]
                if kind=="system":
                    image=self._system_image();source="system"
                else:
                    image=self._plugin_image(plugin,payload);source=plugin.id
            else:
                image=self._system_image();source="system"

            self._device.display(image)
            self._last_render=time.time()
            self._active_source=source
            self._last_error=""

    def test(self):
        with self._lock:
            if self._device is None:
                self.reconfigure()
            if self._device is None:
                raise RuntimeError(self._last_error or "Display is not connected")
            cfg=self.config()
            image=Image.new("1",(cfg["width"],cfg["height"]),0)
            draw=ImageDraw.Draw(image)
            draw.rectangle((0,0,cfg["width"]-1,cfg["height"]-1),outline=1)
            draw.text((4,4),"RackDash I2C",font=_font(),fill=1)
            draw.text((4,18),cfg["label"].split("·")[0].strip(),font=_font(),fill=1)
            draw.text((4,32),f"{cfg['address']} bus {cfg['bus']}",font=_font(),fill=1)
            self._device.display(image)
            self._last_render=time.time()
            self._active_source="test"
            return self.status()
