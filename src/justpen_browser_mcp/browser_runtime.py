"""Resolve and activate Camoufox, preferring upstream over the temporary CI mirror.

SDK download/activation work runs in an owned child process, so a startup deadline
or cancellation can stop it. The returned executable and Firefox major keep later
instance launches independent of changes to the SDK's shared active selection.
"""

import asyncio
import json
import logging
import sys
from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from camoufox.multiversion import (
    InstalledVersion,
    find_install,
    get_active_path,
    get_repo_name,
    list_installed,
    set_active,
)
from camoufox.pkgman import CamoufoxFetcher, RepoConfig, Version, launch_path

from .browser_mirror import MIRROR_VERSION, mirror_candidate
from .browser_releases import list_available_versions
from .errors import BinaryNotFoundError

logger = logging.getLogger(__name__)
STARTUP_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class BrowserRuntime:
    """One startup's verified browser selection, reused for every instance."""

    version: str
    executable_path: str
    installation: str

    @property
    def firefox_major(self) -> int:
        """Firefox major used for the default generated fingerprint."""
        return int(self.version.split(".", 1)[0])


def _version_key(version: Version) -> tuple[tuple[int, ...], Version]:
    """Order Firefox numbers first: SDK Version comparisons only order the build."""
    if version.version is None:
        raise BinaryNotFoundError("Camoufox release is missing its Firefox version")
    return tuple(int(part) for part in version.version.split(".")), version


def prepare_runtime() -> BrowserRuntime:
    """Check upstream every time; equal/newer official builds supersede the mirror."""
    repo = next((repo for repo in RepoConfig.load_repos() if repo.name.lower() == "official"), None)
    if repo is None:
        raise BinaryNotFoundError("Camoufox official repository configuration is unavailable")
    logger.info("Checking latest official Camoufox release")
    releases = list_available_versions(repo_config=repo, include_prerelease=True)
    if not releases:
        raise BinaryNotFoundError("No latest official Camoufox release is available for this platform")
    latest = max(
        (release for release in releases if release.version.is_supported()),
        key=lambda release: _version_key(release.version),
        default=None,
    )
    if latest is None or _version_key(latest.version) < _version_key(MIRROR_VERSION):
        mirror = mirror_candidate()
        if mirror is None:
            raise BinaryNotFoundError("No fixed Camoufox release or temporary CI mirror is available for this platform")
        repo, latest = mirror
        if not latest.version.is_supported():
            raise BinaryNotFoundError(
                "The temporary Camoufox CI mirror is not compatible with the installed SDK/driver"
            )
        logger.info("Using the temporary Justpen mirror of official CI %s", latest.version.full_string)
    else:
        logger.info("Using official Camoufox %s; temporary CI mirror is not needed", latest.version.full_string)
    version = latest.version.full_string
    repo_name = get_repo_name(repo.repo)

    def installed_release() -> InstalledVersion | None:
        return find_install(
            version,
            latest.sha256,
            [
                item
                for item in list_installed()
                if item.repo_name.lower() == repo_name and (latest.sha256 is None or item.sha256 == latest.sha256)
            ],
        )

    installed = installed_release()
    if installed is None:
        logger.info("Installing Camoufox %s", version)
        CamoufoxFetcher(repo_config=repo, selected_version=latest).install()
        installed = installed_release()
    if installed is None:
        raise BinaryNotFoundError(f"Camoufox {version} was not installed after fetch")
    executable = launch_path(installed.path)
    logger.info("Activating Camoufox %s", version)
    set_active(installed.relative_path)
    if get_active_path() != installed.path:
        raise BinaryNotFoundError(f"Camoufox {version} activation did not select the installed release")
    return BrowserRuntime(version=version, executable_path=executable, installation=installed.relative_path)


def _parse_runtime_result(stdout: bytes) -> BrowserRuntime:
    result = json.loads(stdout)
    if not isinstance(result, dict):
        raise TypeError("expected an object")
    result = cast("dict[str, Any]", result)
    version = result.get("version")
    executable = result.get("executable_path")
    installation = result.get("installation")
    if not isinstance(version, str) or not isinstance(executable, str) or not isinstance(installation, str):
        raise TypeError("missing browser version or executable")
    runtime = BrowserRuntime(version=version, executable_path=executable, installation=installation)
    if runtime.firefox_major < 1 or not Path(executable).is_file():
        raise ValueError("browser executable is unavailable")
    return runtime


async def ensure_camoufox_binary() -> BrowserRuntime:
    """Prepare the latest browser on every server startup, including cached installs."""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "justpen_browser_mcp.browser_runtime",
        "--prepare",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(STARTUP_TIMEOUT_SECONDS):
            stdout, stderr = await process.communicate()
    except (asyncio.CancelledError, TimeoutError) as exc:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        if isinstance(exc, TimeoutError):
            raise BinaryNotFoundError("Camoufox startup update exceeded its time limit") from exc
        raise
    if process.returncode != 0:
        detail = stderr.decode(errors="replace").strip()[-4096:]
        raise BinaryNotFoundError(f"Camoufox startup preparation failed: {detail}")
    try:
        runtime = await asyncio.to_thread(_parse_runtime_result, stdout)
    except (ValueError, TypeError, OSError) as exc:
        raise BinaryNotFoundError(f"Invalid Camoufox preparation result: {exc}") from exc
    logger.info("Camoufox %s is active and ready: %s", runtime.version, runtime.installation)
    return runtime


def cli() -> None:
    """Prepare the browser for developer setup, CI or server startup."""
    if sys.argv[1:] == ["--prepare"]:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)
        with redirect_stdout(sys.stderr):
            runtime = prepare_runtime()
        sys.stdout.write(json.dumps(asdict(runtime)) + "\n")
    else:
        asyncio.run(ensure_camoufox_binary())


if __name__ == "__main__":
    cli()
