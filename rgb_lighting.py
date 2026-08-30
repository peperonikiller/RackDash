from __future__ import annotations

import colorsys
import math
import threading
import time
from pathlib import Path
from typing import Any, Callable

from config_manager import parse_env, update_schema_values


LOGO_GREEN = "#58d67d"
FAILURE_RED = "#ff4757"
UPDATE_ORANGE = "#ff9f43"

ARGB_CONFIG = [
    {
        "key": "ARGB_ENABLED",
        "label": "Enable ARGB Lighting",
        "type": "checkbox",
        "default": "false",
    },
    {
        "key": "ARGB_DRIVER",
        "label": "Driver",
        "type": "select",
        "default": "spi",
        "options": [
            {"value": "spi", "label": "SPI / NeoPixel (recommended for Pi 5)"},
        ],
        "help": "Uses the Raspberry Pi hardware SPI bus and the CircuitPython NeoPixel SPI driver.",
    },
    {
        "key": "ARGB_LED_COUNT",
        "label": "LED Count",
        "type": "number",
        "default": "30",
        "min": 1,
        "max": 1000,
    },
    {
        "key": "ARGB_COLOR_ORDER",
        "label": "Color Order",
        "type": "select",
        "default": "GRB",
        "options": [
            {"value": "GRB", "label": "GRB (most WS2812B strips)"},
            {"value": "RGB", "label": "RGB"},
            {"value": "BRG", "label": "BRG"},
            {"value": "BGR", "label": "BGR"},
            {"value": "RGBW", "label": "RGBW"},
            {"value": "GRBW", "label": "GRBW"},
        ],
    },
    {
        "key": "ARGB_BRIGHTNESS",
        "label": "Brightness",
        "type": "number",
        "default": "35",
        "min": 0,
        "max": 100,
        "step": 1,
    },
    {
        "key": "ARGB_BREATHE_SECONDS",
        "label": "Default Breathe Cycle",
        "type": "number",
        "default": "4.0",
        "min": 1.0,
        "max": 20.0,
        "step": 0.25,
        "help": "Seconds per full idle/status breathing cycle.",
    },
]


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _hex_color(value: Any, fallback: str = "#000000") -> tuple[int, int, int]:
    text = str(value or "").strip()
    if not text.startswith("#"):
        text = fallback
    text = text.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        text = fallback.lstrip("#")
    try:
        return tuple(int(text[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return _hex_color(fallback, "#000000")


def _scale_color(color: tuple[int, int, int], factor: float):
    factor = _clamp(float(factor), 0.0, 1.0)
    return tuple(int(round(channel * factor)) for channel in color)


def _color_to_int(color: tuple[int, int, int], white: int | None = None) -> int:
    r, g, b = color
    if white is None:
        return (r << 16) | (g << 8) | b
    return (r << 24) | (g << 16) | (b << 8) | int(white)


class _MockPixels:
    """Test backend used by RackDash validation; never exposed in Admin."""

    def __init__(self, count: int):
        self.n = count
        self.brightness = 1.0
        self.values = [(0, 0, 0)] * count
        self.frames = 0

    def fill(self, color):
        self.values = [color] * self.n

    def __setitem__(self, index, value):
        self.values[index] = value

    def show(self):
        self.frames += 1

    def deinit(self):
        self.fill((0, 0, 0))
        self.show()


class ARGBLightingManager:
    """
    RackDash addressable-RGB controller.

    State priority:
      1. RackDash/plugin failures -> red breathe
      2. Available updates        -> orange breathe
      3. Plugin get_argb_data()   -> plugin-requested effect
      4. Idle                     -> RackDash green breathe

    Plugins never control the global brightness. Brightness is always applied
    from Admin/config.env after plugin requests have been sanitized.
    """

    def __init__(
        self,
        config_path: Path,
        plugin_provider: Callable[[], list[dict[str, Any]]] | None = None,
        system_state_provider: Callable[[], dict[str, Any]] | None = None,
        logger=None,
        driver_factory=None,
    ):
        self.config_path = Path(config_path)
        self.plugin_provider = plugin_provider or (lambda: [])
        self.system_state_provider = system_state_provider or (lambda: {})
        self.logger = logger
        self.driver_factory = driver_factory

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._pixels = None
        self._signature = None
        self._connected = False
        self._last_error = ""
        self._active_source = "disabled"
        self._active_effect = "off"
        self._active_color = "#000000"
        self._last_frame = 0.0
        self._test_until = 0.0

    def _log(self, level: str, message: str, *args):
        try:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(message, *args)
        except Exception:
            pass

    def _config(self) -> dict[str, Any]:
        env = parse_env(self.config_path)
        return {
            "enabled": _truthy(env.get("ARGB_ENABLED", "false")),
            "driver": str(env.get("ARGB_DRIVER", "spi") or "spi").strip().lower(),
            "led_count": max(1, min(1000, int(float(env.get("ARGB_LED_COUNT", "30") or 30)))),
            "color_order": str(env.get("ARGB_COLOR_ORDER", "GRB") or "GRB").strip().upper(),
            "brightness": int(_clamp(float(env.get("ARGB_BRIGHTNESS", "35") or 35), 0, 100)),
            "breathe_seconds": float(_clamp(float(env.get("ARGB_BREATHE_SECONDS", "4.0") or 4), 1, 20)),
        }

    def _create_pixels(self, config):
        if self.driver_factory:
            return self.driver_factory(config)

        if config["driver"] == "mock":
            return _MockPixels(config["led_count"])

        if config["driver"] != "spi":
            raise RuntimeError(f"Unsupported ARGB driver: {config['driver']}")

        try:
            import board
            import neopixel_spi
        except Exception as exc:
            raise RuntimeError(
                "ARGB SPI driver unavailable. Install adafruit-blinka and "
                "adafruit-circuitpython-neopixel-spi."
            ) from exc

        order = config["color_order"]
        pixel_order = getattr(neopixel_spi, order, order)
        bpp = 4 if "W" in order else 3
        return neopixel_spi.NeoPixel_SPI(
            board.SPI(),
            config["led_count"],
            bpp=bpp,
            brightness=1.0,
            auto_write=False,
            pixel_order=pixel_order,
        )

    def _close_pixels(self):
        pixels = self._pixels
        self._pixels = None
        self._connected = False
        self._signature = None
        if pixels is None:
            return
        try:
            pixels.deinit()
        except Exception:
            pass

    def _ensure_pixels(self, config):
        if not config["enabled"]:
            self._close_pixels()
            self._last_error = ""
            return None

        signature = (
            config["driver"],
            config["led_count"],
            config["color_order"],
        )
        if self._pixels is not None and self._signature == signature:
            return self._pixels

        self._close_pixels()
        try:
            self._pixels = self._create_pixels(config)
            self._signature = signature
            self._connected = True
            self._last_error = ""
            self._log(
                "info",
                "ARGB connected using %s (%d LEDs, %s)",
                config["driver"],
                config["led_count"],
                config["color_order"],
            )
        except Exception as exc:
            self._pixels = None
            self._connected = False
            self._last_error = str(exc)[:300]
            self._log("warning", "ARGB initialization failed: %s", exc)
        return self._pixels

    def _plugin_request(self):
        requests = []
        try:
            rows = self.plugin_provider() or []
        except Exception as exc:
            self._log("warning", "ARGB plugin provider failed: %s", exc)
            rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            request = row.get("request")
            if not isinstance(request, dict) or not request:
                continue

            # Brightness is intentionally forbidden to plugins.
            request = {
                key: value
                for key, value in request.items()
                if str(key).lower() not in {"brightness", "global_brightness"}
            }
            if not request:
                continue

            request["_plugin_id"] = str(row.get("id") or "plugin")
            request["_plugin_name"] = str(row.get("name") or request["_plugin_id"])
            request["_order"] = int(row.get("order") or 100)
            request["_priority"] = int(_clamp(float(request.get("priority", 50) or 50), 0, 100))
            requests.append(request)

        if not requests:
            return None

        requests.sort(key=lambda item: (-item["_priority"], item["_order"], item["_plugin_id"]))
        return requests[0]

    def _resolve_state(self, config, now: float):
        if not config["enabled"]:
            return {
                "source": "disabled",
                "effect": "off",
                "color": "#000000",
                "speed": config["breathe_seconds"],
            }

        if now < self._test_until:
            return {
                "source": "admin-test",
                "effect": "rainbow",
                "color": LOGO_GREEN,
                "speed": 2.5,
            }

        try:
            system = self.system_state_provider() or {}
        except Exception as exc:
            self._log("warning", "ARGB system-state provider failed: %s", exc)
            system = {}

        if system.get("failure"):
            return {
                "source": "system-failure",
                "effect": "breathe",
                "color": FAILURE_RED,
                "speed": config["breathe_seconds"],
            }

        if system.get("update"):
            return {
                "source": "update-available",
                "effect": "breathe",
                "color": UPDATE_ORANGE,
                "speed": config["breathe_seconds"],
            }

        plugin = self._plugin_request()
        if plugin:
            return {
                "source": f"plugin:{plugin['_plugin_id']}",
                "effect": str(plugin.get("effect") or "solid").strip().lower(),
                "color": str(plugin.get("color") or LOGO_GREEN),
                "secondary": str(plugin.get("secondary") or "#000000"),
                "speed": float(_clamp(float(plugin.get("speed", 2.0) or 2), 0.25, 30)),
                "pixels": plugin.get("pixels"),
            }

        return {
            "source": "rackdash-idle",
            "effect": "breathe",
            "color": LOGO_GREEN,
            "speed": config["breathe_seconds"],
        }

    def _breathe_factor(self, now: float, speed: float) -> float:
        speed = max(0.25, float(speed))
        # Smooth 18%-100% breathing envelope.
        phase = (now % speed) / speed
        wave = (math.sin((phase * math.tau) - (math.pi / 2)) + 1.0) / 2.0
        return 0.18 + (0.82 * wave)

    def _render(self, pixels, config, state, now: float):
        count = config["led_count"]
        global_brightness = config["brightness"] / 100.0
        effect = state.get("effect", "solid")
        base = _hex_color(state.get("color"), LOGO_GREEN)
        secondary = _hex_color(state.get("secondary"), "#000000")
        speed = max(0.25, float(state.get("speed") or 2.0))

        if effect in {"off", "none"}:
            colors = [(0, 0, 0)] * count

        elif effect in {"breathe", "breath", "glow"}:
            factor = global_brightness * self._breathe_factor(now, speed)
            colors = [_scale_color(base, factor)] * count

        elif effect == "pulse":
            phase = (now % speed) / speed
            factor = global_brightness * (1.0 if phase < 0.22 else 0.16)
            colors = [_scale_color(base, factor)] * count

        elif effect == "chase":
            colors = [_scale_color(secondary, global_brightness)] * count
            head = int((now / speed) * max(1, count)) % max(1, count)
            for offset, factor in ((0, 1.0), (1, 0.55), (2, 0.25)):
                index = (head - offset) % count
                colors[index] = _scale_color(base, global_brightness * factor)

        elif effect == "rainbow":
            colors = []
            phase = (now / speed) % 1.0
            for index in range(count):
                hue = (phase + (index / max(1, count))) % 1.0
                rgb = tuple(int(channel * 255) for channel in colorsys.hsv_to_rgb(hue, 1.0, 1.0))
                colors.append(_scale_color(rgb, global_brightness))

        elif effect == "pixels" and isinstance(state.get("pixels"), list):
            raw = state["pixels"]
            colors = []
            for index in range(count):
                value = raw[index] if index < len(raw) else "#000000"
                colors.append(_scale_color(_hex_color(value, "#000000"), global_brightness))

        else:
            colors = [_scale_color(base, global_brightness)] * count

        for index, color in enumerate(colors):
            pixels[index] = color
        pixels.show()

    def _loop(self):
        while not self._stop.is_set():
            started = time.monotonic()
            config = self._config()
            pixels = self._ensure_pixels(config)
            now = time.monotonic()
            state = self._resolve_state(config, now)

            self._active_source = str(state.get("source") or "unknown")
            self._active_effect = str(state.get("effect") or "off")
            self._active_color = str(state.get("color") or "#000000")

            if pixels is not None:
                try:
                    self._render(pixels, config, state, now)
                    self._connected = True
                    self._last_error = ""
                    self._last_frame = time.time()
                except Exception as exc:
                    self._connected = False
                    self._last_error = str(exc)[:300]
                    self._log("warning", "ARGB frame failed: %s", exc)

            elapsed = time.monotonic() - started
            self._stop.wait(max(0.02, 0.05 - elapsed))

        self._close_pixels()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="rackdash-argb",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        self._close_pixels()

    def save_settings(self, payload: dict[str, Any]):
        values = {
            "ARGB_ENABLED": "true" if payload.get("enabled") else "false",
            "ARGB_DRIVER": str(payload.get("driver") or "spi"),
            "ARGB_LED_COUNT": str(max(1, min(1000, int(float(payload.get("led_count") or 30))))),
            "ARGB_COLOR_ORDER": str(payload.get("color_order") or "GRB").upper(),
            "ARGB_BRIGHTNESS": str(int(_clamp(float(payload.get("brightness") or 0), 0, 100))),
            "ARGB_BREATHE_SECONDS": str(_clamp(float(payload.get("breathe_seconds") or 4), 1, 20)),
        }
        update_schema_values(self.config_path, ARGB_CONFIG, values)
        # Force reconnection if hardware shape/order changed.
        with self._lock:
            config = self._config()
            signature = (config["driver"], config["led_count"], config["color_order"])
            if signature != self._signature or not config["enabled"]:
                self._close_pixels()
        return self.status()

    def test(self):
        if not self._config()["enabled"]:
            raise RuntimeError("Enable ARGB lighting before running the test.")
        self._test_until = time.monotonic() + 5.0
        return self.status()

    def status(self):
        config = self._config()
        return {
            **config,
            "connected": bool(self._connected),
            "last_error": self._last_error,
            "active_source": self._active_source,
            "active_effect": self._active_effect,
            "active_color": self._active_color,
            "last_frame": self._last_frame,
            "logo_green": LOGO_GREEN,
            "failure_red": FAILURE_RED,
            "update_orange": UPDATE_ORANGE,
        }
