from __future__ import annotations

import ast
import re
import shutil
import time
from pathlib import Path
from typing import Optional

import requests


def _version_tuple(value: str):
    nums = re.findall(r"\d+", value or "")
    return tuple(int(x) for x in nums) if nums else (0,)


def _compare_versions(left: str, right: str) -> int:
    a = _version_tuple(left)
    b = _version_tuple(right)
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return (a > b) - (a < b)


def _github_repo(url: str) -> Optional[tuple[str, str]]:
    if not url:
        return None
    match = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)",
        url.strip(),
        re.I,
    )
    if not match:
        return None
    return match.group(1), re.sub(r"\.git$", "", match.group(2))


class OfficialPluginUpdater:
    """
    Updates first-party RackDash plugins stored inside the main RackDash repo.

    Third-party plugins remain managed by PluginInstaller and rackdash-plugin.json.
    Official plugins are compared directly against their source file on the
    configured branch (main by default), so RackDash application releases do not
    determine plugin update availability.
    """

    def __init__(self, plugin_dir: Path, backup_dir: Path, repo_url: str, branch: str = "main"):
        self.plugin_dir = Path(plugin_dir)
        self.backup_dir = Path(backup_dir)
        self.repo_url = repo_url.rstrip("/")
        self.branch = branch
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}
        self.cache_seconds = 300

    def _repo(self):
        repo = _github_repo(self.repo_url)
        if not repo:
            raise ValueError("Official RackDash GitHub repository is invalid")
        return repo

    def _raw_url(self, source_path: str):
        owner, repo = self._repo()
        path = source_path.lstrip("/")
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{self.branch}/{path}"

    def _fetch_source(self, source_path: str) -> str:
        response = requests.get(
            self._raw_url(source_path),
            headers={"User-Agent": "RackDash-Official-Plugin-Updater"},
            timeout=8,
        )
        if response.status_code == 404:
            raise FileNotFoundError(f"Official plugin source not found: {source_path}")
        response.raise_for_status()
        return response.text

    def _metadata(self, source: str):
        tree = ast.parse(source)
        values = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "PLUGIN_ID",
                    "PLUGIN_NAME",
                    "PLUGIN_VERSION",
                    "PLUGIN_OFFICIAL",
                    "PLUGIN_SOURCE_PATH",
                }:
                    try:
                        values[target.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
        return values

    def check(self, plugin_id: str, source_path: str, current_version: str, force: bool = False):
        cache_key = (source_path, current_version)
        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and not force and now - cached["checked_at"] < self.cache_seconds:
            return dict(cached["result"])

        source = self._fetch_source(source_path)
        metadata = self._metadata(source)
        remote_id = str(metadata.get("PLUGIN_ID", "")).strip()
        remote_version = str(metadata.get("PLUGIN_VERSION", "")).strip()

        if remote_id != plugin_id:
            raise ValueError(
                f"Official source PLUGIN_ID is '{remote_id or 'missing'}', expected '{plugin_id}'"
            )
        if not remote_version:
            raise ValueError("Official plugin source does not declare PLUGIN_VERSION")

        comparison = _compare_versions(current_version, remote_version)

        if comparison < 0:
            status = "update_available"
            message = f"Official update available: v{remote_version}"
        elif comparison == 0:
            status = "current"
            message = "Official plugin is up to date"
        else:
            status = "ahead"
            message = f"Local version is newer than main (v{remote_version})"

        result = {
            "supported": True,
            "official": True,
            "status": status,
            "message": message,
            "current": current_version,
            "latest": remote_version,
            "source": "official_file",
            "source_path": source_path,
            "branch": self.branch,
            "github_url": f"{self.repo_url}/blob/{self.branch}/{source_path}",
        }
        self._cache[cache_key] = {"checked_at": now, "result": result}
        return dict(result)

    def update(self, plugin_id: str, source_path: str):
        source = self._fetch_source(source_path)
        metadata = self._metadata(source)

        if str(metadata.get("PLUGIN_ID", "")).strip() != plugin_id:
            raise ValueError("Downloaded official plugin ID does not match the installed plugin")
        if metadata.get("PLUGIN_OFFICIAL") is not True:
            raise ValueError("Downloaded file is not marked PLUGIN_OFFICIAL = True")
        if str(metadata.get("PLUGIN_SOURCE_PATH", "")).strip() != source_path:
            raise ValueError("Downloaded plugin source path metadata does not match")
        version = str(metadata.get("PLUGIN_VERSION", "")).strip()
        if not version:
            raise ValueError("Downloaded official plugin has no PLUGIN_VERSION")

        # Compile before replacing the current plugin.
        compile(source, source_path, "exec")

        destination = self.plugin_dir / Path(source_path).name
        if destination.name != f"{plugin_id}.py":
            raise ValueError("Official plugin filename must match PLUGIN_ID")

        backup = None
        if destination.exists():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup = self.backup_dir / f"{plugin_id}-{stamp}-official-update.py"
            shutil.copy2(destination, backup)

        temp = destination.with_suffix(".py.new")
        temp.write_text(source, encoding="utf-8")
        temp.replace(destination)

        # Invalidate check cache for this source.
        self._cache = {
            key: value for key, value in self._cache.items()
            if key[0] != source_path
        }

        return {
            "id": plugin_id,
            "version": version,
            "source_path": source_path,
            "backup": backup.name if backup else None,
            "restart_required": True,
        }
