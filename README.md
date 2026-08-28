<p align="center">
  <img src="[http://some_place.com/image.png](https://raw.githubusercontent.com/peperonikiller/RackDash/refs/heads/main/rackdash_logo.png)" />
</p>

# RackDash

RackDash is a lightweight, plugin-driven dashboard for **Raspberry Pi, rackmount LCDs, touchscreen status panels, homelabs, and unusual display resolutions**.

It started as a 1280×400 Pi-hole dashboard and grew into a general-purpose system where each plugin provides its own tab, data source, settings, health status, update information, and optional I2C output.

RackDash is designed to run continuously on a small Linux system with Chromium in kiosk mode.

> Official repository: `https://github.com/peperonikiller/RackDash`

---

## Features

- Responsive dashboard for ultrawide rack displays, normal monitors, tablets, and portrait screens
- Touchscreen support
  - horizontal swipe to change dashboard tabs
  - vertical scrolling inside plugin pages
  - horizontally scrollable tab bar when needed
- Keyboard Left/Right arrow navigation
- Optional automatic tab rotation
- Per-plugin:
  - enabled/disabled state
  - visible/hidden tab
  - auto-rotation inclusion
  - tab order
  - refresh interval
  - rotation duration
- Manual-only **Admin** tab that is never included in dashboard auto-rotation
- Plugin health monitoring
  - configured/unconfigured state
  - last poll
  - last successful poll
  - response time
  - consecutive failures
  - last error
- Built-in settings UI for RackDash and plugins
- Admin authentication with password/PIN protection
- Backup and restore
- Plugin rollback
- Official and third-party plugin update systems
- RackDash self-update from GitHub Releases
- Optional daily RackDash and plugin update checks
- System logs and diagnostics
- I2C OLED display support
- Themes, UI scaling, overscan/safe-area adjustment, idle dimming, and burn-in protection
- No frontend framework or Node.js runtime required on the RackDash host

---

## Built-in Plugins

RackDash currently includes:

| Plugin | Purpose |
| --- | --- |
| Pi-hole | DNS queries, blocked requests, block rate, clients, and activity |
| Plex | Now Playing, recently added media, and optional TMDB upcoming movies |
| Weather | Current weather and forecast using Open-Meteo |
| Formula 1 | Next race, circuit, countdown, Driver standings, and Constructor standings |
| 3D Printer | Klipper / Moonraker print status, temperatures, progress, and ETA |
| Bitaxe | AxeOS hashrate, power, efficiency, temperature, shares, and device status |
| Twitch | Live/offline channel monitoring, game/category, viewers, uptime, and recent broadcast information |

Official plugins live in:

```text
plugins/
```

Official plugin source is maintained in the main RackDash repository.

---

# Installation

## Recommended Platform

RackDash is primarily developed and tested for Raspberry Pi OS / Debian Linux, but should work on most modern Linux distributions with:

- Python 3
- `python3-venv`
- `pip`
- Chromium or another modern browser
- systemd if you want RackDash to start automatically at boot

A Raspberry Pi 4 or Pi 5 is more than sufficient for typical use.

---

## 1. Install Required System Packages

On Raspberry Pi OS / Debian:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
```

If you plan to use an I2C OLED display, also install:

```bash
sudo apt install -y i2c-tools
```

---

## 2. Clone RackDash

```bash
cd ~
git clone https://github.com/peperonikiller/RackDash.git
cd RackDash
```

If you prefer the traditional RackDash path used throughout the examples:

```bash
mv ~/RackDash ~/rackdash
cd ~/rackdash
```

The rest of this README assumes:

```text
/home/<your-user>/rackdash
```

---

## 3. Run the Installer

RackDash includes an installation script that creates a Python virtual environment and installs the required Python packages.

```bash
chmod +x install.sh
./install.sh
```

The installer creates:

```text
venv/
```

and, if one does not already exist:

```text
config.env
```

Your existing `config.env` is not meant to be committed to GitHub.

---

## 4. Configure RackDash

Open:

```bash
nano config.env
```

At minimum, the core defaults can be left alone:

```env
RACKDASH_HOST=127.0.0.1
RACKDASH_PORT=8080
ROTATE_SECONDS=12
```

`127.0.0.1` is the recommended host when RackDash is only being displayed locally on the Pi.

To intentionally expose RackDash to other devices on your LAN:

```env
RACKDASH_HOST=0.0.0.0
```

If you expose RackDash to the LAN, enabling **Admin authentication** is strongly recommended.

Save with:

```text
Ctrl+O
Enter
Ctrl+X
```

---

## 5. Test RackDash Manually

Start RackDash:

```bash
cd ~/rackdash
./venv/bin/python app.py
```

Then open:

```text
http://127.0.0.1:8080
```

If RackDash loads successfully, stop the manual server with:

```text
Ctrl+C
```

and install the systemd service.

---

# Running RackDash as a Service

RackDash includes a systemd installer:

```bash
cd ~/rackdash
chmod +x scripts/install-systemd.sh
./scripts/install-systemd.sh
```

Check the service:

```bash
systemctl status rackdash.service
```

You should see:

```text
active (running)
```

Useful commands:

```bash
sudo systemctl restart rackdash.service
sudo systemctl stop rackdash.service
sudo systemctl start rackdash.service
```

View systemd logs:

```bash
journalctl -u rackdash.service -f
```

RackDash also keeps its own rotating application log under:

```text
data/rackdash.log
```

---

# Chromium Kiosk Mode

For a dedicated rack display, Chromium can launch RackDash full-screen:

```bash
chromium \
  --kiosk \
  --no-first-run \
  --noerrdialogs \
  --disable-session-crashed-bubble \
  --disable-background-networking \
  --disable-sync \
  --disable-default-apps \
  --disable-extensions \
  --disable-features=MediaRouter \
  http://127.0.0.1:8080
```

The additional flags reduce unnecessary browser background activity on a dedicated kiosk.

---

## Start Chromium Automatically After Desktop Login

Create the autostart directory:

```bash
mkdir -p ~/.config/autostart
```

Create:

```bash
nano ~/.config/autostart/rackdash.desktop
```

Use:

```ini
[Desktop Entry]
Type=Application
Name=RackDash
Comment=RackDash kiosk dashboard
Exec=chromium --kiosk --no-first-run --noerrdialogs --disable-session-crashed-bubble --disable-background-networking --disable-sync --disable-default-apps --disable-extensions --disable-features=MediaRouter http://127.0.0.1:8080
Terminal=false
X-GNOME-Autostart-enabled=true
```

After the next desktop login, Chromium should open RackDash automatically.

---

# Admin

The **Admin** tab is located at the far right of the RackDash tab bar.

Admin is intentionally **manual-only**. It never participates in automatic dashboard rotation.

Admin contains:

- RackDash health summary
- plugin health
- plugin settings
- plugin display/rotation controls
- RackDash core settings
- Admin authentication
- backups and restore
- logs and diagnostics
- RackDash update controls
- plugin update controls
- third-party plugin installation
- I2C display configuration

---

## Admin Authentication

RackDash can protect write operations behind a password or PIN.

In:

```text
Admin → Authentication
```

set a password/PIN and enable protection.

Protected actions include:

- changing RackDash settings
- changing plugin settings
- restarting RackDash
- installing/updating/removing plugins
- plugin rollback
- RackDash self-update
- backup/restore
- I2C hardware controls

Normal dashboard viewing remains available.

The Admin password is stored as an **scrypt hash** in RackDash state and is not stored as plaintext in `config.env`.

---

# Core Settings

Open:

```text
Admin → Core Settings
```

Available options include:

| Setting | Description |
| --- | --- |
| Listen Host | `127.0.0.1` for local-only access, `0.0.0.0` for LAN access |
| Port | RackDash HTTP port; default `8080` |
| Default Rotation Seconds | Default time before switching tabs |
| Theme | Dark, OLED Black, or Blue Steel |
| UI Scale | Global dashboard scaling |
| Safe Area / Overscan | Adds padding around the dashboard |
| Large Touch Targets | Enlarges controls for touch displays |
| Burn-in Protection | Periodically shifts the interface by a few pixels |
| Pixel Shift Interval | Frequency of burn-in protection movement |
| Dim After Minutes | Dims the display after inactivity; `0` disables |
| Developer Mode | Enables developer-oriented controls |
| Daily RackDash Update Check | Checks for RackDash updates once every 24 hours |
| Daily Plugin Update Checks | Checks plugins for updates once every 24 hours |

Settings can be saved with:

```text
SAVE
```

or:

```text
SAVE + RESTART
```

Use **Save + Restart** when changing server-side settings that require RackDash to reload.

---

# Automatic Tab Rotation

The footer contains an:

```text
AUTO ROTATE
```

switch.

The browser remembers this setting in local storage.

Each plugin can also be individually configured from Admin with:

- **TAB** — show or hide the plugin tab
- **AUTO** — include or exclude the plugin from automatic rotation
- **ORDER** — change tab order
- **REFRESH** — override API polling frequency
- **ROTATE** — set how long the plugin remains visible during auto-rotation

The Admin tab is always excluded.

---

# Plugin Health

Admin continuously tracks plugin runtime status.

Possible states include:

- Healthy
- Waiting
- Needs setup / Unconfigured
- Error
- Disabled

For each plugin, RackDash records:

- last polling attempt
- last successful poll
- response time
- consecutive failures
- last error
- missing required configuration

The **TEST** button immediately runs that plugin's `get_data()` function.

This is useful when configuring a new integration.

---

# Configuring the Built-in Plugins

Most settings can be entered from:

```text
Admin → <Plugin> → Settings
```

They can also be edited directly in `config.env`.

## Pi-hole

Typical configuration:

```env
PIHOLE_URL=http://127.0.0.1
PIHOLE_PASSWORD=
```

Use a Pi-hole app password if authentication is enabled.

---

## Plex

```env
PLEX_URL=http://192.168.1.10:32400
PLEX_TOKEN=
TMDB_API_KEY=
TMDB_REGION=US
TMDB_LANGUAGE=en-US
```

`TMDB_API_KEY` is optional and is only needed for the **Upcoming Movies** section.

---

## Weather

```env
WEATHER_LOCATION=Chicago, IL
WEATHER_UNITS=fahrenheit
```

Supported units:

```text
fahrenheit
celsius
```

Weather data is retrieved through Open-Meteo.

---

## Formula 1

```env
F1_API=https://api.jolpi.ca/ergast/f1
```

The F1 plugin shows the next race, circuit layout, countdown, top Driver Championship positions, and Constructor Championship standings.

---

## Klipper / Moonraker 3D Printer

```env
KLIPPER_URL=http://192.168.1.20:7125
```

RackDash connects directly to Moonraker.

---

## Bitaxe / AxeOS

```env
BITAXE_URL=http://192.168.1.30
```

The Bitaxe plugin reads AxeOS system information.

---

# Twitch Plugin

The Twitch plugin can watch one or more channels.

Example:

```env
TWITCH_CHANNELS=channelone,channeltwo,channelthree
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
```

Channel names are comma-separated.

RackDash accepts simple channel names such as:

```text
shroud,lirik,cohhcarnage
```

The plugin shows, for live channels:

- channel name
- profile image
- current game/category
- stream title
- viewer count
- stream uptime

If nobody is live, RackDash shows the configured offline channels and the age of their newest archived broadcast.

Twitch does not expose a direct public `last_streamed_at` value. RackDash therefore uses the newest archived VOD as the best official API approximation. A channel with VOD archiving disabled may show its last broadcast as unavailable.

---

## Creating a Twitch Developer Application

Go to the Twitch Developer Console and create an application.

RackDash uses the Twitch **Client Credentials** server-to-server OAuth flow.

Use an OAuth Redirect URL such as:

```text
http://localhost:3000
```

RackDash does not actually redirect users through OAuth for this integration; Twitch requires a redirect URL when registering the developer application.

After creating the application:

1. Copy the **Client ID**.
2. Generate a **Client Secret**.
3. Enter both values in:
   ```text
   Admin → Twitch → Settings
   ```
4. Enter your comma-separated channels.
5. Choose **Save + Restart**.

Treat the Client Secret like a password.

RackDash masks secret/password/token configuration fields in Admin.

---

# RackDash Updates

The **RackDash Update** section in Admin displays:

- current installed version
- latest GitHub version
- update status
- time of the last update check

Manual controls:

```text
CHECK RACKDASH UPDATE
UPDATE RACKDASH NOW
```

Manual checks always perform a fresh GitHub check.

RackDash compares semantic version numbers correctly, including equivalent forms such as:

```text
2.0
v2.0
2.0.0
v2.0.0
```

---

## Daily RackDash Update Checks

Enable:

```text
DAILY RACKDASH UPDATE CHECK
```

and save the update settings.

RackDash will check GitHub at most once every 24 hours.

This option only **checks** for updates. RackDash will never automatically install a new version.

Results are persisted in:

```text
data/update_checks.json
```

so update status survives browser refreshes, service restarts, and Pi reboots.

---

## RackDash Self-Update

When:

```text
UPDATE RACKDASH NOW
```

is pressed, RackDash:

1. finds the latest GitHub Release
2. creates a pre-update backup
3. prefers an attached RackDash ZIP release asset
4. falls back to GitHub's automatically generated release zipball if necessary
5. validates and extracts the update
6. preserves persistent configuration/data
7. replaces RackDash core files
8. restarts through systemd

Persistent items such as these are preserved:

```text
config.env
data/
venv/
.git/
```

Third-party plugin files not present in the release are also preserved.

---

# Plugin Updates

RackDash distinguishes between **official** and **third-party** plugins.

## Official Plugins

Official plugins live in:

```text
https://github.com/peperonikiller/RackDash/tree/main/plugins
```

Each official plugin has its own version.

RackDash checks the plugin's exact source file on the `main` branch rather than comparing it against the RackDash application release.

For example:

```text
plugins/twitch.py
```

can be version `1.1.0` while RackDash itself is version `2.3.0`.

Admin can:

```text
CHECK
UPDATE OFFICIAL
ROLLBACK
```

Official updates are validated before replacing the installed plugin, and RackDash keeps rollback copies under:

```text
data/plugin_backups/
```

---

## Third-Party Plugins

Third-party plugins use their own GitHub repository and a:

```text
rackdash-plugin.json
```

manifest.

They can be installed from Admin by entering the GitHub repository URL.

Before installation, RackDash previews:

- plugin name
- version
- compatibility
- declared capabilities

RackDash can then install, update, uninstall, and roll back installer-managed third-party plugins.

Third-party plugins execute Python code with the same OS permissions as the RackDash process. Only install plugins you trust.

---

## Daily Plugin Update Checks

Enable:

```text
DAILY PLUGIN UPDATE CHECKS
```

in the RackDash Update section.

RackDash will check official and supported third-party plugins at most once every 24 hours.

As with RackDash core updates, this only performs an update **check**. Plugins are never automatically installed or upgraded.

Use:

```text
CHECK ALL UPDATES
```

for an immediate manual refresh.

---

# Backups and Restore

Admin provides:

```text
DOWNLOAD BACKUP
RESTORE BACKUP
RESTORE SELECTED
```

A RackDash backup contains persistent configuration/state including:

- `config.env`
- plugin state
- plugin source metadata
- Admin authentication state
- I2C artwork
- top-level plugin files

RackDash also automatically creates backups before some update and rollback operations.

It is a good idea to download a backup before making major changes.

---

# Logs and Diagnostics

Admin → Platform Tools provides:

```text
DIAGNOSTICS
VIEW LOGS
```

Diagnostics can include:

- Python version
- Linux/platform version
- system architecture
- hostname
- RackDash systemd state
- Chromium process detection
- I2C bus scan
- available disk space
- browser resolution
- browser device-pixel ratio
- browser user agent

The log viewer displays RackDash's rotating application log and can optionally filter by plugin/name.

---

# I2C OLED Displays

RackDash can drive a small secondary OLED display from the Raspberry Pi.

Supported presets include:

- SH1106 / SSH1106 — 128×64
- SH1107 — 128×64
- SSD1306 — 128×64
- SSD1306 — 128×32
- SSD1309 — 128×64
- SSD1325 — 128×64
- SSD1327 — 128×128

Available modes:

### System Only

Displays useful Raspberry Pi information such as:

- IP address
- CPU usage
- RAM usage
- CPU temperature
- disk usage
- uptime

### System + Plugins

Rotates between RackDash system information and I2C output supplied by compatible plugins.

### Static Icon

Allows an image to be uploaded from Admin.

RackDash verifies that the uploaded image is no larger than the selected display and automatically converts it to a display-friendly monochrome image.

---

## Raspberry Pi I2C Wiring

Typical four-pin I2C OLED wiring:

| OLED | Raspberry Pi |
| --- | --- |
| VCC | 3.3 V — physical pin 1 |
| GND | Ground — physical pin 6 |
| SDA | GPIO2 / SDA1 — physical pin 3 |
| SCL | GPIO3 / SCL1 — physical pin 5 |

Use 3.3 V unless the documentation for your exact display module explicitly specifies otherwise.

Enable I2C:

```bash
sudo raspi-config
```

Select:

```text
Interface Options → I2C → Enable
```

Install tools and allow your user to access I2C:

```bash
sudo apt install -y i2c-tools
sudo usermod -aG i2c "$USER"
sudo reboot
```

After reboot:

```bash
i2cdetect -y 1
```

Many SH1106/SSD1306 boards appear at:

```text
0x3C
```

and some use:

```text
0x3D
```

Then configure the detected bus/address from:

```text
Admin → I2C Display
```

Use **TEST DISPLAY** before enabling a permanent mode.

---

# Security

RackDash defaults to:

```env
RACKDASH_HOST=127.0.0.1
```

which only accepts connections from the same machine.

If you deliberately use:

```env
RACKDASH_HOST=0.0.0.0
```

RackDash can become reachable from other systems on your LAN.

When exposing RackDash beyond localhost:

- enable Admin authentication
- use a strong password
- do not expose RackDash directly to the public Internet
- do not commit `config.env`
- protect API tokens and passwords
- install only trusted third-party plugins

Fields declared by plugins as:

```text
password
secret
token
```

are masked in the Admin UI. Leaving the masked `********` value unchanged preserves the existing secret.

---

# Updating an Existing Installation Manually

For a manual upgrade:

```bash
sudo systemctl stop rackdash.service
```

Replace the RackDash application files while preserving:

```text
config.env
data/
venv/
```

Then reinstall/update Python requirements:

```bash
cd ~/rackdash
source venv/bin/activate
pip install -r requirements.txt
deactivate
```

Restart:

```bash
sudo systemctl start rackdash.service
```

Verify:

```bash
systemctl status rackdash.service
```

---

# Troubleshooting

## RackDash Does Not Load

Check:

```bash
systemctl status rackdash.service
```

and:

```bash
journalctl -u rackdash.service -n 100 --no-pager
```

Also verify:

```bash
curl http://127.0.0.1:8080/api/system
```

---

## Port 8080 Is Already in Use

Check:

```bash
ss -ltnp | grep :8080
```

If you previously started RackDash manually while systemd was also running, stop the manual process and let systemd own the port.

---

## Chromium Shows Google/GCM Errors

Messages similar to:

```text
Registration response error message: DEPRECATED_ENDPOINT
```

come from Chromium background services and are unrelated to RackDash.

Using the recommended kiosk flags above reduces this background activity.

---

## Plugin Shows "Needs Setup"

Open:

```text
Admin → Plugin → Settings
```

and fill in all required fields.

Then use:

```text
TEST
```

to run the plugin immediately.

---

## Plugin Shows an Error

Use:

```text
Admin → VIEW LOGS
```

or:

```bash
journalctl -u rackdash.service -f
```

You can also use the plugin's:

```text
DEBUG
TEST
RELOAD
```

controls from Admin.

---

## I2C Display Is Not Found

Run:

```bash
i2cdetect -y 1
```

If no address appears:

- verify VCC/GND
- verify SDA/SCL
- confirm I2C is enabled
- reboot after adding your user to the `i2c` group
- check whether your board uses `0x3C` or `0x3D`

---

# Project Layout

A typical RackDash installation looks like:

```text
RackDash/
├── app.py
├── plugin_manager.py
├── plugin_installer.py
├── official_plugin_updater.py
├── update_monitor.py
├── config_manager.py
├── i2c_display.py
├── admin_security.py
├── backup_manager.py
├── core_updater.py
├── admin_diagnostics.py
├── config.env
├── config.env.example
├── requirements.txt
├── install.sh
├── plugins/
│   ├── _shared.py
│   ├── pihole.py
│   ├── plex.py
│   ├── weather.py
│   ├── f1.py
│   ├── printer.py
│   ├── bitaxe.py
│   ├── twitch.py
│   └── examples/
├── static/
│   ├── app.js
│   └── style.css
├── templates/
│   └── index.html
├── scripts/
│   └── install-systemd.sh
└── data/
```

`config.env`, authentication state, update state, backups, and other runtime data should not be committed to Git.

---

# Developing Plugins

RackDash is designed so integrations can be developed independently from the core dashboard.

For complete plugin documentation, see:

```text
PLUGIN_GUIDE.md
```

and the commented example under:

```text
plugins/examples/
```

---

## Minimal Plugin

A minimal plugin is a Python file placed directly in:

```text
plugins/
```

Example:

```python
PLUGIN_ID = "hello"
PLUGIN_NAME = "Hello"
PLUGIN_VERSION = "1.0.0"
PLUGIN_HTML = """
<div>
    <h1 data-role="message">Loading...</h1>
</div>
"""

def get_data():
    return {
        "message": "Hello from RackDash"
    }

PLUGIN_JS = """
window.RackDashPlugins.hello = {
    render(data, root) {
        root.querySelector('[data-role="message"]').textContent =
            data.message;
    }
};
"""
```

Restart RackDash and the plugin will be discovered automatically.

---

## Plugin Metadata

Recommended metadata:

```python
PLUGIN_ID = "my_plugin"
PLUGIN_NAME = "My Plugin"
PLUGIN_VERSION = "1.0.0"

PLUGIN_ORDER = 100
PLUGIN_REFRESH_SECONDS = 30
PLUGIN_ACCENT = "#6fb7ff"

PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""

PLUGIN_CAPABILITIES = ["network"]
```

Common capability declarations include:

```text
network
i2c
custom_routes
```

Capabilities are shown to the user before a third-party plugin is installed.

---

## Plugin Configuration

Plugins can define fields that automatically appear in Admin:

```python
PLUGIN_CONFIG = [
    {
        "key": "MY_SERVICE_URL",
        "label": "Service URL",
        "type": "text",
        "default": "http://127.0.0.1:9000",
        "required": True
    },
    {
        "key": "MY_SERVICE_TOKEN",
        "label": "API Token",
        "type": "token",
        "default": "",
        "required": True
    }
]
```

Supported field types include:

```text
text
number
password
token
secret
checkbox
select
```

Plugins normally read configuration with:

```python
import os

url = os.getenv("MY_SERVICE_URL", "")
```

---

## Plugin Data

Every plugin must provide:

```python
def get_data():
    return {
        "status": "online"
    }
```

RackDash calls this on the plugin refresh interval and sends the returned JSON-compatible data to the browser renderer.

Plugin exceptions are isolated so a failure in one plugin does not bring down the entire dashboard.

---

## Plugin I2C Output

Plugins can optionally expose data to the I2C display when RackDash is in **System + Plugins** mode:

```python
def get_i2c_data():
    return {
        "title": "My Plugin",
        "lines": [
            "Status: Online",
            "Jobs: 3"
        ]
    }
```

An icon can also be supplied:

```python
def get_i2c_data():
    return {
        "title": "My Plugin",
        "lines": ["3 active jobs"],
        "icon": "plugin_icon.png"
    }
```

Plugin developers should not open the I2C bus directly. RackDash owns the display connection and handles display rotation.

---

## Official RackDash Plugins

Plugins maintained directly in this repository use:

```python
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/my_plugin.py"
```

RackDash uses `PLUGIN_SOURCE_PATH` to check that exact file on the `main` branch for a newer `PLUGIN_VERSION`.

Official plugins should live directly under:

```text
plugins/
```

---

## Third-Party Plugin Manifest

A third-party plugin repository should contain:

```text
rackdash-plugin.json
```

Example:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entry": "my_plugin.py",
  "description": "Example RackDash integration",
  "min_rackdash": "2.0.0",
  "max_rackdash": "",
  "capabilities": ["network"]
}
```

RackDash validates the manifest and plugin source before installing it.

Third-party plugin code is **not sandboxed**. It runs with RackDash's OS permissions.

---

## Custom Routes

Plugins may optionally provide:

```python
def register_routes(app):
    ...
```

Use custom routes for things such as:

- image proxying
- SVG/track assets
- browser-facing helper endpoints

Changes to custom Flask routes require a full RackDash restart.

---

## Developer Tools

Admin provides:

```text
DEBUG
RELOAD
TEST
```

for plugin development and troubleshooting.

`RELOAD` refreshes the Python module and `get_data()` logic without restarting the full RackDash service.

If route registration changes, restart RackDash instead.

---

## Contributing

Contributions, bug reports, plugin improvements, and additional integrations are welcome.

Before submitting code:

- do not commit credentials or `config.env`
- do not commit `__pycache__/` or `.pyc` files
- keep plugin failures isolated
- use responsive layouts
- support short/ultrawide rack screens where practical
- declare required configuration fields
- declare compatibility/capabilities
- keep secrets server-side

See:

```text
CONTRIBUTING.md
PLUGIN_GUIDE.md
```

for additional project/developer information.

---

# License

RackDash is released under the **MIT License**.

See:

```text
LICENSE
```
