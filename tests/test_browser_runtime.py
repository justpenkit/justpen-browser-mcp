"""Latest browser preparation must resolve, install, activate and verify before readiness."""

import asyncio
import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from camoufox.multiversion import InstalledVersion
from camoufox.pkgman import AvailableVersion, RepoConfig, Version

import justpen_browser_mcp.__main__ as entrypoint
import justpen_browser_mcp.browser_runtime as runtime
from justpen_browser_mcp.config import BrowserServerConfig
from justpen_browser_mcp.errors import BinaryNotFoundError


@pytest.fixture
def prepared_install(tmp_path, monkeypatch):
    version = Version(version="152.0.4", build="beta.32")
    release = AvailableVersion(version=version, url="https://example.test/browser.zip", is_prerelease=False)
    install_path = tmp_path / version.full_string
    install_path.mkdir()
    installed = InstalledVersion(repo_name="official", version=version, path=install_path)
    executable = install_path / "browser"
    executable.touch()
    repo = RepoConfig.from_dict(
        {"name": "Official", "repo": "daijro/camoufox", "pattern": "{name}-{version}-{build}-{os}.{arch}.zip"}
    )
    catalog = MagicMock(return_value=[release])
    monkeypatch.setattr(runtime, "list_available_versions", catalog, raising=False)
    monkeypatch.setattr(runtime, "list_installed", lambda: [installed], raising=False)
    monkeypatch.setattr(runtime, "launch_path", lambda _path: str(executable), raising=False)
    monkeypatch.setattr(runtime, "get_active_path", lambda: install_path, raising=False)
    monkeypatch.setattr(runtime, "set_active", MagicMock(), raising=False)
    monkeypatch.setattr(runtime, "RepoConfig", MagicMock(load_repos=lambda: [repo]), raising=False)
    return release, installed, catalog


def test_cached_latest_is_resolved_and_activated_on_every_start(prepared_install):
    release, installed, catalog = prepared_install
    first = runtime.prepare_runtime()
    second = runtime.prepare_runtime()
    assert first == second
    assert first.version == release.version.full_string
    assert first.firefox_major == 152
    assert Path(first.executable_path).is_file()
    assert catalog.call_count == 2
    assert catalog.call_args.kwargs["include_prerelease"] is True
    assert isinstance(runtime.set_active, MagicMock)
    assert runtime.set_active.call_args.args == (installed.relative_path,)
    assert first.installation == installed.relative_path


@pytest.fixture
def mirror_install(prepared_install, tmp_path, monkeypatch):
    """Keep real selection and cache matching; replace only catalog/disk side effects."""
    _release, official, _catalog = prepared_install
    mirror_repo = RepoConfig.from_dict(
        {
            "name": "JustpenKit",
            "repo": "justpenkit/justpen-browser-mcp",
            "pattern": "{name}-{version}-{build}-{os}.{arch}.zip",
        }
    )
    version = Version(version="152.0.4", build="beta.31")
    mirror = AvailableVersion(version, "https://example.test/mirror.zip", is_prerelease=True, sha256="1" * 64)
    path = tmp_path / "mirror" / "152.0.4-beta.31-11111111"
    path.mkdir(parents=True)
    (path / "browser").touch()
    installed = InstalledVersion(repo_name="justpenkit", version=version, path=path, sha256="1" * 64)
    monkeypatch.setattr(runtime, "mirror_candidate", lambda: (mirror_repo, mirror), raising=False)
    monkeypatch.setattr(
        runtime, "CamoufoxFetcher", MagicMock(side_effect=AssertionError("Unexpected download for cached release"))
    )
    monkeypatch.setattr(runtime, "list_installed", lambda: [installed, official])
    monkeypatch.setattr(runtime, "launch_path", lambda folder: str(folder / "browser"))
    active = [installed.path]

    def activate(selector):
        active[0] = next(item.path for item in (installed, official) if item.relative_path == selector)

    monkeypatch.setattr(runtime, "set_active", activate)
    monkeypatch.setattr(runtime, "get_active_path", lambda: active[0])
    return mirror, installed


def _set_official_version(release, installed, firefox, build):
    release.version = installed.version = Version(version=firefox, build=build)
    installed.path = installed.path.parent / release.version.full_string
    installed.path.mkdir(exist_ok=True)
    (installed.path / "browser").touch()


@pytest.mark.parametrize(
    ("firefox", "build", "source", "expected"),
    [
        ("152.0.4", "beta.30", "mirror", "152.0.4-beta.31"),
        ("152.0.4", "beta.9", "mirror", "152.0.4-beta.31"),
        ("152.0.4", "beta.31", "official", "152.0.4-beta.31"),
        ("152.0.4", "beta.32", "official", "152.0.4-beta.32"),
        ("152.0.5", "beta.30", "official", "152.0.5-beta.30"),
        ("153.0.0", "beta.30", "official", "153.0.0-beta.30"),
        ("151.0.4", "beta.99", "mirror", "152.0.4-beta.31"),
    ],
)
def test_full_version_selection_prioritizes_official_on_ties(
    prepared_install, mirror_install, firefox, build, source, expected
):
    release, official, _catalog = prepared_install
    _mirror, mirrored = mirror_install
    _set_official_version(release, official, firefox, build)
    result = runtime.prepare_runtime()
    assert result.version == expected
    selected = official if source == "official" else mirrored
    assert result.installation == selected.relative_path
    assert runtime.get_active_path() == selected.path


def test_cached_mirror_automatically_yields_when_official_advances(prepared_install, mirror_install):
    release, official, catalog = prepared_install
    _mirror, mirrored = mirror_install
    _set_official_version(release, official, "152.0.4", "beta.30")
    first = runtime.prepare_runtime()
    assert first.installation == mirrored.relative_path

    # A later startup sees a newly published prerelease, without any config change.
    _set_official_version(release, official, "152.0.4", "beta.32")
    release.is_prerelease = True
    second = runtime.prepare_runtime()
    assert second.installation == official.relative_path
    assert second.version == "152.0.4-beta.32"
    assert catalog.call_count == 2
    assert catalog.call_args.kwargs["include_prerelease"] is True


def test_catalog_order_and_build_suffix_cannot_hide_newer_firefox(prepared_install, mirror_install):
    release, official, catalog = prepared_install
    _set_official_version(release, official, "153.0.0", "beta.30")
    older = AvailableVersion(
        Version(version="152.0.4", build="beta.99"), "https://example.test/older.zip", is_prerelease=False
    )
    catalog.return_value = [older, release]
    result = runtime.prepare_runtime()
    assert result.version == "153.0.0-beta.30"
    assert result.installation == official.relative_path


def test_newer_official_does_not_need_a_mirror_for_this_platform(prepared_install, monkeypatch):
    monkeypatch.setattr(
        runtime, "mirror_candidate", MagicMock(side_effect=AssertionError("Mirror must not be accessed"))
    )
    assert runtime.prepare_runtime().version == "152.0.4-beta.32"


def test_older_official_without_platform_mirror_fails_before_activation(prepared_install, monkeypatch):
    release, official, _catalog = prepared_install
    _set_official_version(release, official, "152.0.4", "beta.30")
    monkeypatch.setattr(runtime, "mirror_candidate", lambda: None)
    with pytest.raises(BinaryNotFoundError, match="platform"):
        runtime.prepare_runtime()
    assert isinstance(runtime.set_active, MagicMock)
    runtime.set_active.assert_not_called()


def test_newer_but_sdk_incompatible_release_does_not_replace_usable_mirror(prepared_install, mirror_install):
    release, official, _catalog = prepared_install
    _mirror, mirrored = mirror_install
    _set_official_version(release, official, "153.0.0", "beta.1")
    result = runtime.prepare_runtime()
    assert result.installation == mirrored.relative_path


def test_incompatible_mirror_cannot_be_activated(prepared_install, mirror_install, monkeypatch):
    release, official, _catalog = prepared_install
    _mirror, _mirrored = mirror_install
    _set_official_version(release, official, "152.0.4", "beta.30")
    monkeypatch.setattr(Version, "is_supported", lambda _self: False)
    with pytest.raises(BinaryNotFoundError, match="compatible"):
        runtime.prepare_runtime()


def test_missing_latest_is_installed_before_activation(prepared_install, monkeypatch):
    _release, installed, _catalog = prepared_install
    stages = []
    available = []
    monkeypatch.setattr(runtime, "list_installed", lambda: available)

    def install():
        stages.append("install")
        available.append(installed)

    fetcher = MagicMock()
    fetcher.install.side_effect = install
    monkeypatch.setattr(runtime, "CamoufoxFetcher", MagicMock(return_value=fetcher), raising=False)
    monkeypatch.setattr(runtime, "set_active", lambda _path: stages.append("activate"))
    runtime.prepare_runtime()
    assert stages == ["install", "activate"]


def test_successful_install_without_binary_cannot_activate(prepared_install, monkeypatch):
    monkeypatch.setattr(runtime, "list_installed", list)
    monkeypatch.setattr(runtime, "CamoufoxFetcher", MagicMock(), raising=False)
    with pytest.raises(BinaryNotFoundError, match="installed"):
        runtime.prepare_runtime()
    assert isinstance(runtime.set_active, MagicMock)
    runtime.set_active.assert_not_called()


def test_empty_remote_catalog_cannot_reuse_old_active_browser(prepared_install):
    _release, _installed, catalog = prepared_install
    catalog.return_value = []
    with pytest.raises(BinaryNotFoundError, match="latest"):
        runtime.prepare_runtime()
    assert isinstance(runtime.set_active, MagicMock)
    runtime.set_active.assert_not_called()


def test_activation_is_verified(prepared_install, monkeypatch):
    monkeypatch.setattr(runtime, "get_active_path", lambda: Path("/different/browser"))
    with pytest.raises(BinaryNotFoundError, match="activat"):
        runtime.prepare_runtime()


@pytest.mark.parametrize("installed_hash", [None, "old-asset"])
def test_latest_asset_does_not_reuse_unverified_or_changed_hash(prepared_install, monkeypatch, installed_hash):
    release, installed, _catalog = prepared_install
    release.sha256 = "latest-asset"
    installed.sha256 = installed_hash
    fetched = MagicMock()
    fetched.install.side_effect = lambda: setattr(installed, "sha256", "latest-asset")
    monkeypatch.setattr(runtime, "CamoufoxFetcher", MagicMock(return_value=fetched))
    runtime.prepare_runtime()
    fetched.install.assert_called_once()


@pytest.fixture
def browser_fetch(monkeypatch, tmp_path):
    executable = tmp_path / "browser"
    executable.touch()
    output = json.dumps(
        {
            "version": "152.0.4-beta.30",
            "executable_path": str(executable),
            "installation": "browsers/official/latest-asset",
        }
    ).encode()
    process = MagicMock(returncode=0)
    process.communicate = AsyncMock(return_value=(output, b""))
    launch = AsyncMock(return_value=process)
    monkeypatch.setattr(runtime.asyncio, "create_subprocess_exec", launch)
    return launch, process


async def test_preparation_returns_concrete_runtime(browser_fetch, caplog):
    launch, _process = browser_fetch
    caplog.set_level(logging.INFO, logger=runtime.__name__)
    result = await runtime.ensure_camoufox_binary()
    assert result.version == "152.0.4-beta.30"
    assert result.firefox_major == 152
    assert await asyncio.to_thread(Path(result.executable_path).is_file)
    assert "--prepare" in launch.call_args.args
    assert "browsers/official/latest-asset" in caplog.text


async def test_worker_failure_prevents_success(browser_fetch):
    _launch, process = browser_fetch
    process.returncode = 2
    process.communicate.return_value = (b"", b"activation failed")
    with pytest.raises(BinaryNotFoundError, match="activation failed"):
        await runtime.ensure_camoufox_binary()


@pytest.mark.parametrize("output", [b"", b"{}", b"not json", b'{"version": false, "executable_path": 2}'])
async def test_invalid_worker_result_is_rejected(browser_fetch, output):
    _launch, process = browser_fetch
    process.communicate.return_value = (output, b"")
    with pytest.raises(BinaryNotFoundError):
        await runtime.ensure_camoufox_binary()


async def test_browser_failure_prevents_mcp_start(monkeypatch):
    failure = BinaryNotFoundError("pinned browser unavailable")
    monkeypatch.setattr(entrypoint, "build_config", lambda _args, _env: BrowserServerConfig())
    monkeypatch.setattr(entrypoint, "_ensure_camoufox_binary", AsyncMock(side_effect=failure))
    run_server = AsyncMock()
    monkeypatch.setattr(entrypoint.mcp, "run_async", run_server)

    with pytest.raises(BinaryNotFoundError, match="pinned browser unavailable"):
        await entrypoint.main()

    run_server.assert_not_awaited()


@pytest.mark.integration
def test_browser_helper_cli_exits_nonzero_on_failure():
    probe = """
from unittest.mock import AsyncMock
from justpen_browser_mcp import browser_runtime
from justpen_browser_mcp.errors import BinaryNotFoundError

browser_runtime.ensure_camoufox_binary = AsyncMock(side_effect=BinaryNotFoundError("browser unavailable"))
browser_runtime.cli()
"""
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False, timeout=30)
    assert result.returncode != 0
    assert "BinaryNotFoundError: browser unavailable" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("termination_times_out", [False, True])
async def test_cancelled_prepare_stops_and_reaps_child(browser_fetch, termination_times_out):
    _launch, process = browser_fetch
    process.returncode = None
    started = asyncio.Event()

    async def communicate():
        started.set()
        await asyncio.Event().wait()

    process.communicate.side_effect = communicate
    process.wait = AsyncMock(side_effect=[TimeoutError(), -9] if termination_times_out else [-15])
    task = asyncio.create_task(runtime.ensure_camoufox_binary())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    process.terminate.assert_called_once_with()
    assert process.wait.await_count == (2 if termination_times_out else 1)
    assert process.kill.call_count == int(termination_times_out)


async def test_preparation_deadline_stops_and_reaps_worker(browser_fetch, monkeypatch):
    _launch, process = browser_fetch
    process.returncode = None
    process.communicate.side_effect = asyncio.Event().wait
    process.wait = AsyncMock(return_value=-15)
    monkeypatch.setattr(runtime, "STARTUP_TIMEOUT_SECONDS", 0)
    with pytest.raises(BinaryNotFoundError, match="time limit"):
        await runtime.ensure_camoufox_binary()
    process.terminate.assert_called_once_with()
    process.wait.assert_awaited_once_with()
