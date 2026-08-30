# RackDash Plugin Guide

RackDash loads every top-level `*.py` file inside `plugins/`, except files whose
names begin with `_`.

A plugin can contain its server-side API code, HTML, CSS, JavaScript, and
optional Flask routes in one Python file.

## Required pieces

```python
PLUGIN_ID = "demo"
PLUGIN_NAME = "Demo"
PLUGIN_HTML = "<h1 data-role='value'>Loading...</h1>"

def get_data():
    return {"value": 123}
```

Most plugins also need a browser renderer:

```python
PLUGIN_JS = """
window.RackDashPlugins.demo = {
  render(data, root) {
    root.querySelector('[data-role="value"]').textContent = data.value;
  }
};
"""
```

## Metadata

| Setting | Required | Description |
| --- | --- | --- |
| `PLUGIN_ID` | yes | Unique lowercase identifier |
| `PLUGIN_NAME` | yes | Tab label |
| `PLUGIN_HTML` | yes | Page HTML fragment |
| `get_data()` | yes | Returns JSON-serializable data |
| `PLUGIN_ORDER` | no | Sort order, default 100 |
| `PLUGIN_REFRESH_SECONDS` | no | Refresh cadence, default 10 |
| `PLUGIN_ACCENT` | no | Active page accent |
| `PLUGIN_ICON` | no | Small tab subtitle |
| `PLUGIN_PUBLIC_ERROR` | no | Safe browser-facing error |
| `PLUGIN_CSS` | no | Scoped plugin stylesheet |
| `PLUGIN_JS` | no | Browser renderer |
| `register_routes(app)` | no | Custom Flask routes |

## Browser callbacks

```javascript
window.RackDashPlugins.demo = {
  render(data, root) {
    // Fresh server data arrived.
  },
  onShow(root) {
    // The tab became visible.
  },
  onResize(root) {
    // The viewport size changed.
  }
};
```

Always query inside `root`.

Good:

```javascript
root.querySelector('[data-role="temperature"]')
```

Avoid global IDs and document-wide selectors where possible.

## Shared UI classes

RackDash provides responsive reusable classes:

- `.plugin-head`
- `.eyebrow`
- `.metric-grid`
- `.metric`
- `.surface`
- `.chart-card`
- `.chip-row`
- `.status-chip`
- `.muted`
- `.split`
- `.progress-track`
- `.empty-state`

Using these lets your plugin inherit themes, screen scaling, and touch-friendly
spacing automatically.

## Touch and overflow

Do not build your own full-page scroll container. RackDash already wraps every
plugin in `.plugin-scroll`, which supports native touch scrolling.

Horizontal swipes across plugin pages switch tabs. Vertical movement remains
available for page scrolling.

## Responsive layout

Avoid fixed dimensions such as:

```css
width: 600px;
height: 250px;
```

Prefer:

```css
grid-template-columns: repeat(3, minmax(0, 1fr));
font-size: clamp(.8rem, 2vw, 1.5rem);
gap: var(--gap);
padding: var(--pad);
```

Use media queries when necessary.

## API access

Third-party requests should happen in `get_data()` on the Python side.

This keeps secrets out of the browser and avoids CORS issues.

## Custom routes

If your plugin needs images, SVGs, or another endpoint:

```python
from flask import Response

def register_routes(app):
    @app.get("/api/plugin/demo/image")
    def demo_image():
        return Response(...)
```

Prefix custom routes with `/api/plugin/<PLUGIN_ID>/`.

## Errors

Raise exceptions normally from `get_data()`. RackDash logs the traceback
server-side and sends only `PLUGIN_PUBLIC_ERROR` to the browser.

Do not place tokens or passwords in error strings.

## Full example

Read `plugins/examples/sample_api_plugin.py`. It is intentionally heavily
commented and demonstrates the whole plugin contract.


## GitHub update checking

Plugins may provide:

```python
PLUGIN_VERSION = "1.4.2"
PLUGIN_GITHUB = "https://github.com/yourname/your-plugin"
```

When both are present, RackDash's manual **Plugins** health page can compare the
installed version with the repository's latest GitHub release.

If the repository has no GitHub releases, RackDash falls back to the newest tag.

Use semantic-looking version tags such as:

```text
v1.4.2
1.4.2
release-1.4.2
```

The Health page is never part of auto rotation, and GitHub is queried only when
the user explicitly asks for an update check.


## Declarative settings

Use `PLUGIN_CONFIG` so RackDash can create and edit plugin configuration for
you. Supported types are `text`, `number`, `password`, `token`, `secret`,
`checkbox`, and `select`.

Missing config keys are generated automatically from each field's `default`.
Each plugin gets its own Settings dialog in Plugins / Health.

Read values normally:

```python
import os
URL = os.getenv("MY_PLUGIN_URL", "http://127.0.0.1:9000")
```

For Health-page installation, add this repository-root manifest:

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "entry": "my_plugin.py"
}
```


## Health diagnostics and required settings

Add `"required": True` to a `PLUGIN_CONFIG` field when the plugin cannot operate
without that value.

RackDash uses required fields to distinguish an API failure from an
unconfigured plugin. Runtime health metrics are collected automatically around
`get_data()`; plugin authors do not need to implement timing or error tracking.



## WLED lighting plugin output

Plugins can request WLED state through `get_wled_data()` and should declare `"wled"` in `PLUGIN_CAPABILITIES`. Return `None` or `{}` when not requesting control.

```python
def get_wled_data():
    return {
        "effect": "Breathe",
        "palette": "Party",
        "color": "#9146ff",
        "speed": 120,
        "intensity": 160,
        "priority": 50,
    }
```

Core priority is failure red, update orange, plugin request, then idle RackDash green. Plugin priority is 0-100; ties follow plugin order.

Plugins may use WLED effect/palette names or IDs, up to three colors, speed, intensity, target segment, transition, presets, playlists, reverse/mirror and 2D transforms, custom sliders `c1/c2/c3`, custom toggles `option1/2/3`, direct `pixels`, and `on`.

Plugins cannot set brightness: `brightness`, `bri`, and `global_brightness` are removed. The Admin brightness slider always wins.

## Optional I2C display output

When the administrator selects **System + Plugins**, RackDash looks for an
optional `get_i2c_data()` function on enabled plugins.

Text example:

```python
def get_i2c_data():
    return {
        "title": "Weather",
        "lines": ["72F Clear", "Humidity 42%"]
    }
```

Text plus icon:

```python
def get_i2c_data():
    return {
        "title": "Printer",
        "lines": ["Printing", "Layer 53 / 240"],
        "icon": "printer.png"
    }
```

Icon-only:

```python
def get_i2c_data():
    return {"icon": "logo.png"}
```

RackDash resolves relative icon paths from the plugin file's directory, scales
them down as needed, and converts them to the target display's monochrome image
format. The display manager handles rotation between System and plugin frames;
plugin authors should not create their own I2C connection or display thread.


# RackDash 2.0 plugin platform

## Compatibility metadata

Recommended metadata:

```python
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network"]
```

Common capability declarations include:

- `network`
- `i2c`
- `wled`
- `custom_routes`

Capabilities are informational permission declarations shown to the user before
GitHub installation.

## Runtime presentation overrides

Users can override tab order, refresh interval, auto-rotation participation,
rotation duration, and tab visibility without editing plugin source. Plugin
authors should therefore treat `PLUGIN_ORDER`, `PLUGIN_REFRESH_SECONDS`, and
the core rotation interval as defaults rather than fixed values.

## Debugging

Developer/Admin tools can invoke `get_data()` and inspect its JSON result. A
single plugin module can also be reloaded at runtime. If a plugin registers
custom Flask routes, changing those routes still requires a process restart.

## Secrets

Configuration fields using `password`, `token`, or `secret` are masked by
RackDash when sent to the browser. Plugin authors should continue reading them
with `os.getenv()` and should never return secret values from `get_data()`.


## Official RackDash plugins

First-party plugins shipped from the RackDash repository are marked:

```python
PLUGIN_OFFICIAL = True
PLUGIN_SOURCE_PATH = "plugins/example.py"
```

Do not use those fields for third-party plugins. Third-party plugins should
continue using a standalone GitHub repository plus `rackdash-plugin.json`.

RackDash checks official plugin versions by reading their exact source file
from the RackDash `main` branch. It does not compare official plugin versions
against the RackDash application's GitHub release version.
