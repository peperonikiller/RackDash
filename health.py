from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional

import requests


_GITHUB_CACHE = {}
CACHE_SECONDS = 900


def _version_tuple(value: str):
    """
    Convert common semantic-ish versions to a tuple suitable for comparison.

    Examples:
        v1.2.3       -> (1, 2, 3)
        2.0          -> (2, 0)
        release-3.1  -> (3, 1)

    This intentionally avoids adding packaging/version dependencies to RackDash.
    """
    nums = re.findall(r"\d+", value or "")
    return tuple(int(x) for x in nums) if nums else (0,)


def _github_repo(url: str) -> Optional[tuple[str, str]]:
    """
    Accept normal GitHub repository URLs and return (owner, repo).

    Supported:
        https://github.com/owner/repo
        https://github.com/owner/repo/
        https://github.com/owner/repo.git
    """
    if not url:
        return None
    match = re.match(
        r"^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)",
        url.strip(),
        re.I,
    )
    if not match:
        return None
    owner = match.group(1)
    repo = re.sub(r"\.git$", "", match.group(2))
    return owner, repo


def github_update_status(github_url: str, current_version: str) -> dict:
    """
    Check the latest GitHub release first, then fall back to the latest tag.

    The result is cached for 15 minutes so repeatedly opening Health does not
    hammer GitHub's unauthenticated API rate limit.
    """
    repo = _github_repo(github_url)
    if not repo:
        return {
            "supported": False,
            "status": "no_github",
            "message": "No GitHub repository configured",
        }

    owner, name = repo
    cache_key = f"{owner}/{name}"
    cached = _GITHUB_CACHE.get(cache_key)
    now = time.time()

    if cached and now - cached["checked_at"] < CACHE_SECONDS:
        remote = cached["remote"]
        source = cached["source"]
    else:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "RackDash-Health",
        }
        remote = None
        source = None

        release = requests.get(
            f"https://api.github.com/repos/{owner}/{name}/releases/latest",
            headers=headers,
            timeout=6,
        )
        if release.status_code == 200:
            payload = release.json()
            remote = payload.get("tag_name") or payload.get("name")
            source = "release"
        elif release.status_code not in (404, 422):
            release.raise_for_status()

        if not remote:
            tags = requests.get(
                f"https://api.github.com/repos/{owner}/{name}/tags",
                headers=headers,
                params={"per_page": 1},
                timeout=6,
            )
            tags.raise_for_status()
            rows = tags.json()
            if rows:
                remote = rows[0].get("name")
                source = "tag"

        _GITHUB_CACHE[cache_key] = {
            "checked_at": now,
            "remote": remote,
            "source": source,
        }

    if not remote:
        return {
            "supported": True,
            "status": "unknown",
            "message": "No releases or tags found",
            "github_url": github_url,
            "current": current_version,
            "latest": None,
        }

    current_tuple = _version_tuple(current_version)
    latest_tuple = _version_tuple(remote)

    if latest_tuple > current_tuple:
        status = "update_available"
        message = f"Update available: {remote}"
    elif latest_tuple == current_tuple:
        status = "current"
        message = "Up to date"
    else:
        status = "ahead"
        message = f"Local version is newer than GitHub ({remote})"

    return {
        "supported": True,
        "status": status,
        "message": message,
        "github_url": github_url,
        "current": current_version,
        "latest": remote,
        "source": source,
    }
