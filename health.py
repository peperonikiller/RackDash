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
    Parse semantic-ish version text into numeric components.

    Examples:
        v2.2.0 -> (2, 2, 0)
        2.2    -> (2, 2)
    """
    nums = re.findall(r"\d+", value or "")
    return tuple(int(x) for x in nums) if nums else (0,)


def _compare_versions(left: str, right: str) -> int:
    """
    Compare numeric version components while treating omitted trailing zeros
    as equivalent. This fixes cases such as v2.0.0 versus 2.0.

    Returns:
        -1 when left < right
         0 when left == right
         1 when left > right
    """
    a = _version_tuple(left)
    b = _version_tuple(right)
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return (a > b) - (a < b)


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


def github_update_status(github_url: str, current_version: str, force: bool = False) -> dict:
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

    if cached and not force and now - cached["checked_at"] < CACHE_SECONDS:
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

    comparison = _compare_versions(current_version, remote)

    if comparison < 0:
        status = "update_available"
        message = f"Update available: {remote}"
    elif comparison == 0:
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
