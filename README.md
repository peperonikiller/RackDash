# RackDash

RackDash is a lightweight, plugin-driven dashboard for **rackmount LCDs,
touchscreen status panels, Raspberry Pis, homelabs, and unusual display
resolutions**.

It began as a 1280×400 Pi-hole screen and evolved into a general dashboard
where **every top-level Python file placed in `plugins/` becomes a tab**.

## Built-in plugins

- Pi-hole
- Plex, Recently Added, and optional TMDB upcoming movies
- Weather
- Formula 1
- Klipper / Moonraker 3D printer
- Bitaxe / AxeOS

Spotify was intentionally removed. RackDash favors unattended integrations
that do not require frequent interactive reauthorization.

## Features

- Drop-in Python plugin system.
- Touchscreen support.
  - Swipe vertically to scroll plugin content.
  - Swipe horizontally across a page to change tabs.
  - Swipe the tab bar itself horizontally when the tabs do not fit.
- Responsive layouts for:
  - ultra-wide rack displays
  - standard widescreen monitors
  - tablets
  - portrait displays
- Per-plugin refresh intervals.
- Plugin failures are isolated from the rest of the dashboard.
- Secrets remain server-side in `config.env`.
- Auto-rotation toggle in the footer, persisted in the kiosk browser.
- Manual-only **Plugins / Health** tab for plugin status and GitHub update checks.
- No frontend framework and no Node.js runtime required.

## Quick start

```bash
sudo apt install python3-venv python3-pip
git clone <your-repository-url>
cd RackDash
./install.sh
nano config.env
./venv/bin/python app.py
```

Open:

```text
http://127.0.0.1:8080
```

Optional systemd service:

```bash
./scripts/install-systemd.sh
```

Kiosk example:

```bash
chromium --kiosk --no-first-run --noerrdialogs \
  --disable-session-crashed-bubble http://127.0.0.1:8080
```

## Plugin system

A plugin is a Python file directly inside `plugins/`.

Minimal example:

```python
PLUGIN_ID = "hello"
PLUGIN_NAME = "Hello"
PLUGIN_HTML = "<h1 data-role='message'>Loading...</h1>"

def get_data():
    return {"message": "Hello from RackDash"}

PLUGIN_JS = """
window.RackDashPlugins.hello = {
  render(data, root) {
    root.querySelector('[data-role="message"]').textContent = data.message;
  }
};
"""
```

Restart RackDash and the **Hello** tab is discovered automatically.

See [`PLUGIN_GUIDE.md`](PLUGIN_GUIDE.md) and the heavily commented
[`plugins/examples/sample_api_plugin.py`](plugins/examples/sample_api_plugin.py).

## Responsive design

RackDash no longer assumes 1280×400. The browser automatically classifies the
current display as ultrawide, wide, standard, or portrait and adjusts shared
spacing/header behavior.

Plugins should use the shared responsive classes instead of fixed dimensions.

Each plugin gets a native vertical scroll area automatically. This is especially
useful on short rack screens and touchscreens.

## Auto rotation

The footer includes an **AUTO ROTATE** switch. It is saved using local browser
storage, so turning rotation off remains off across reloads in the same kiosk
profile.

The interval itself is configured with:

```text
ROTATE_SECONDS=12
```

## Security

RackDash binds to `127.0.0.1` by default.

Set:

```text
RACKDASH_HOST=0.0.0.0
```

only when you intentionally want the dashboard accessible to other LAN devices.


## License

MIT


## Plugins / Health tab

RackDash always adds a **Plugins** tab on the far right.

This tab is intentionally excluded from auto rotation. It opens only when the
user clicks or taps it.

The Health page shows:

- RackDash version
- loaded plugin count
- installed plugin versions
- configured GitHub repository for each plugin
- one-click update checks
- a **Check All Updates** action

Plugins can opt into update checks with:

```python
PLUGIN_VERSION = "1.2.0"
PLUGIN_GITHUB = "https://github.com/owner/repository"
```

RackDash checks GitHub's latest release first and falls back to the repository's
latest tag. Results are cached for 15 minutes.



## Plugin configuration API

Plugins may declare their own configuration fields:

```python
PLUGIN_CONFIG = [
    {"key":"MY_PLUGIN_URL","label":"Server URL","type":"text","default":"http://127.0.0.1:9000"},
    {"key":"MY_PLUGIN_TOKEN","label":"API Token","type":"token","default":""},
    {"key":"MY_PLUGIN_MODE","label":"Mode","type":"select","default":"compact",
     "options":[{"value":"compact","label":"Compact"},{"value":"full","label":"Full"}]}
]
```

RackDash statically discovers `PLUGIN_CONFIG` before importing plugins and
automatically adds missing keys to `config.env`. Plugins then read values with
ordinary `os.getenv()`.

The manual **Plugins / Health** page automatically gives every configurable
plugin its own **SETTINGS** window. RackDash core settings are available from
**CORE SETTINGS**.

The Health page also supports enabling/disabling plugins and GitHub
manifest-based third-party installs, updates, and uninstalls. Third-party
repositories must provide `rackdash-plugin.json`. Newly installed or updated
Python plugins require a RackDash restart before execution.


## Health restart and connection recovery

Plugins / Health includes **Restart RackDash**. RackDash replies to the browser,
then exits with a non-zero code. The bundled systemd service uses
`Restart=on-failure`, so systemd immediately brings the server back without
requiring passwordless sudo from the web app.

If the browser loses the RackDash backend, it shows a connection-lost overlay
and checks `/api/system` every 30 seconds. When the server is reachable again,
the page reloads automatically.



## Live plugin diagnostics

Plugins / Health now records live runtime diagnostics for every plugin:

- enabled / disabled
- configured / missing required settings
- healthy / error / waiting
- last poll time
- last successful poll
- last API response time
- consecutive failures
- last sanitized server-side error

The Health page refreshes these diagnostics every 10 seconds while it is open.
Each plugin also has a **TEST** button that immediately executes its `get_data()`
call and updates the diagnostics.

Plugin authors can mark configuration fields as mandatory:

```python
PLUGIN_CONFIG = [
    {
        "key": "MY_SERVICE_URL",
        "label": "Service URL",
        "type": "text",
        "default": "",
        "required": True
    }
]
```

RackDash reports the plugin as **Needs setup** until all required fields have
values.


## I2C OLED displays

Admin includes an I2C Display section for small auxiliary OLEDs. Current
controller presets include SH1106/SSH1106, SH1107, SSD1306 (128×64 and 128×32),
SSD1309, SSD1325, and SSD1327.

Modes:

- **System Only** — IP, CPU, RAM, CPU temperature, root-disk usage, and uptime.
- **System + Plugins** — rotates the system page with plugin-provided I2C frames.
- **Static Icon** — uploads an image no larger than the selected display,
  centers it, dithers it to monochrome, and displays it continuously.

### Raspberry Pi wiring for SH1106 / SSH1106 I2C OLED

Use 3.3 V unless the exact module documentation explicitly requires otherwise:

| OLED | Raspberry Pi 5 |
| --- | --- |
| VCC | 3.3 V physical pin 1 |
| GND | Ground physical pin 6 |
| SDA | GPIO2 / SDA1 physical pin 3 |
| SCL | GPIO3 / SCL1 physical pin 5 |

Enable I2C and verify the module before enabling it in RackDash:

```bash
sudo raspi-config
# Interface Options -> I2C -> Enable

sudo apt install i2c-tools
sudo usermod -aG i2c "$USER"
sudo reboot
```

After reboot:

```bash
i2cdetect -y 1
```

Most SH1106 boards appear at `0x3c`; some use `0x3d`.

### Plugin I2C output

In **System + Plugins** mode, a plugin can participate by defining:

```python
def get_i2c_data():
    return {
        "title": "My Plugin",
        "lines": [
            "Status: Online",
            "Value: 42"
        ]
    }
```

A plugin may also return an icon:

```python
def get_i2c_data():
    return {
        "title": "My Plugin",
        "lines": ["3 active jobs"],
        "icon": "my_plugin_icon.png"
    }
```

The icon path can be absolute or relative to the plugin's Python file. If no
text lines are provided, RackDash centers the icon on the display. Images are
converted to a display-compatible monochrome frame automatically.
