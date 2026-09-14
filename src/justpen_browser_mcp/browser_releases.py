"""Read published upstream assets before SDK parsing loses the draft status.

The SDK's catalog reader includes drafts visible to an authenticated caller.
Keep this publication boundary here; SDK types still own platform compatibility,
installation and hash verification. Requests only target GitHub's API host.
"""

import os
from typing import TYPE_CHECKING, Any, cast

import requests
from camoufox.pkgman import AvailableVersion, RepoConfig, Version

if TYPE_CHECKING:
    import re


def _release_catalog(repository: str) -> list[dict[str, Any]]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "justpen-browser-mcp"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    releases: list[dict[str, Any]] = []
    page = 1
    while True:
        with requests.get(
            f"https://api.github.com/repos/{repository}/releases",
            params={"per_page": 100, "page": page},
            headers=headers,
            timeout=20,
        ) as response:
            response.raise_for_status()
            decoded: object = response.json()
        if not isinstance(decoded, list):
            raise TypeError("Malformed GitHub release catalog")
        items = cast("list[object]", decoded)
        if any(not isinstance(item, dict) for item in items):
            raise TypeError("Malformed GitHub release catalog")
        batch = cast("list[dict[str, Any]]", items)
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def list_available_versions(*, repo_config: RepoConfig, include_prerelease: bool) -> list[AvailableVersion]:
    """Resolve all published pages, retaining the SDK's configured repository fallback."""
    for index, repository in enumerate(repo_config.repos):
        try:
            releases = _release_catalog(repository)
            break
        except (requests.RequestException, TypeError, ValueError):
            if index == len(repo_config.repos) - 1:
                raise
    else:
        raise ValueError("No official Camoufox repository is configured")
    # The SDK returns a text regex but annotates it as bare Pattern.
    pattern: re.Pattern[str] = cast("Any", repo_config).build_pattern()
    versions: list[AvailableVersion] = []
    for release in releases:
        if release.get("draft") or not release.get("published_at"):
            continue
        for asset in release["assets"]:
            match = pattern.fullmatch(asset["name"])
            if match is None:
                continue
            version = Version(version=match["version"], build=match["build"])
            prerelease = bool(release.get("prerelease")) or version.is_alpha
            if prerelease and not include_prerelease:
                continue
            if not repo_config.is_version_supported(version, prerelease):
                continue
            digest = asset.get("digest") or ""
            versions.append(
                AvailableVersion(
                    version=version,
                    url=asset["browser_download_url"],
                    is_prerelease=prerelease,
                    asset_id=asset.get("id"),
                    asset_size=asset.get("size"),
                    asset_updated_at=asset.get("updated_at"),
                    asset_created_at=asset.get("created_at"),
                    sha256=digest.removeprefix("sha256:") if digest.startswith("sha256:") else None,
                )
            )
    return versions
