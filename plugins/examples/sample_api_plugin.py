# RackDash example plugin
#
# This file is intentionally stored in plugins/examples/, so RackDash does NOT
# load it automatically. To try it:
#
#   cp plugins/examples/sample_api_plugin.py plugins/github_example.py
#   sudo systemctl restart rackdash.service
#
# This example uses GitHub's public repository API and requires no API key.
# It is deliberately verbose and heavily commented for plugin authors.

from __future__ import annotations
import os
import requests

# REQUIRED: unique plugin ID.
PLUGIN_ID = "github_example"

# REQUIRED: tab label shown to the user.
PLUGIN_NAME = "GitHub Example"

# OPTIONAL but recommended: semantic plugin version shown on Health.
PLUGIN_VERSION = "1.0.0"
PLUGIN_MIN_RACKDASH = "2.0.0"
PLUGIN_MAX_RACKDASH = ""
PLUGIN_CAPABILITIES = ["network"]

# OPTIONAL: GitHub repository URL. If set, the Health page can compare
# PLUGIN_VERSION with the repository's latest GitHub release/tag.
PLUGIN_GITHUB = "https://github.com/python/cpython"

# OPTIONAL: tab ordering. Lower values appear first.
PLUGIN_ORDER = 900

# OPTIONAL: browser refresh cadence in seconds.
# GitHub's unauthenticated API has a relatively low rate limit, so this sample
# intentionally refreshes only every 10 minutes.
PLUGIN_REFRESH_SECONDS = 600

# OPTIONAL: accent color used by the active tab indicator and shared UI.
PLUGIN_ACCENT = "#9b87f5"

# OPTIONAL: tiny secondary label inside the tab.
PLUGIN_ICON = "API"

# OPTIONAL: safe error text displayed in the browser.
# Do NOT expose raw exceptions or secrets here.
PLUGIN_PUBLIC_ERROR = "GitHub example unavailable"

PLUGIN_CONFIG = [
    {"key":"GITHUB_EXAMPLE_REPOSITORY","label":"Repository","type":"text","default":"python/cpython","help":"owner/repository","required":True},
    {"key":"GITHUB_EXAMPLE_SHOW_ISSUES","label":"Show issue count","type":"checkbox","default":"true"}
]


# REQUIRED: server-side data function.
#
# RackDash calls get_data() when the browser requests:
#   /api/plugin/github_example
#
# Return any JSON-serializable dictionary.
#
# Fetch remote APIs here in Python rather than directly in browser JavaScript:
#   1. API keys remain server-side.
#   2. CORS is not a problem.
#   3. failures are sanitized by RackDash.
#   4. kiosk browsers only need to talk to RackDash itself.
def get_data():
    response = requests.get(
        f"https://api.github.com/repos/{os.getenv('GITHUB_EXAMPLE_REPOSITORY','python/cpython')}",
        headers={"Accept": "application/vnd.github+json"},
        timeout=5,
    )
    response.raise_for_status()
    repo = response.json()

    # Return only what the UI needs.
    return {
        "name": repo.get("full_name", "python/cpython"),
        "description": repo.get("description", ""),
        "stars": repo.get("stargazers_count", 0),
        "forks": repo.get("forks_count", 0),
        "issues": repo.get("open_issues_count", 0),
        "watchers": repo.get("subscribers_count", 0),
    }


# REQUIRED: HTML fragment.
#
# Prefer data-role attributes over global element IDs so plugins cannot collide.
# RackDash already provides reusable CSS classes such as:
# plugin-head, eyebrow, metric-grid, metric, surface, chart-card, chip-row,
# status-chip, muted, split, progress-track, empty-state
PLUGIN_HTML = r'''
<div class="plugin-head">
  <div>
    <span class="eyebrow">EXAMPLE PLUGIN</span>
    <h1 data-role="name">Loading repository...</h1>
    <div class="muted" data-role="description"></div>
  </div>
</div>

<div class="metric-grid">
  <article class="metric"><label>STARS</label><strong data-role="stars">-</strong></article>
  <article class="metric"><label>FORKS</label><strong data-role="forks">-</strong></article>
  <article class="metric"><label>OPEN ISSUES</label><strong data-role="issues">-</strong></article>
  <article class="metric"><label>WATCHERS</label><strong data-role="watchers">-</strong></article>
</div>
'''


# OPTIONAL: plugin-specific CSS.
# Prefix selectors with .plugin-<PLUGIN_ID> so styles remain scoped.
PLUGIN_CSS = r'''
.plugin-github_example .metric {
  border-top: 2px solid rgba(155, 135, 245, .45);
}
'''


# OPTIONAL (normally needed): browser renderer.
#
# render(data, root):
#   data = dictionary returned by get_data()
#   root = DOM element for THIS plugin only
#
# Query inside root rather than document.
PLUGIN_JS = r'''
window.RackDashPlugins.github_example = {
  render(data, root) {
    root.querySelector('[data-role="name"]').textContent = data.name;
    root.querySelector('[data-role="description"]').textContent = data.description;
    root.querySelector('[data-role="stars"]').textContent = RackDash.formatNumber(data.stars);
    root.querySelector('[data-role="forks"]').textContent = RackDash.formatNumber(data.forks);
    root.querySelector('[data-role="issues"]').textContent = RackDash.formatNumber(data.issues);
    root.querySelector('[data-role="watchers"]').textContent = RackDash.formatNumber(data.watchers);
  },

  // Optional: called whenever the user switches to this tab.
  onShow(root) {
  },

  // Optional: called after a viewport resize.
  onResize(root) {
  }
};
'''


# OPTIONAL: custom Flask routes.
#
# If a plugin needs an image proxy, download endpoint, SVG route, etc.,
# define register_routes(app), keeping routes under /api/plugin/<PLUGIN_ID>/.
#
# def register_routes(app):
#     @app.get("/api/plugin/github_example/avatar")
#     def avatar():
#         ...
