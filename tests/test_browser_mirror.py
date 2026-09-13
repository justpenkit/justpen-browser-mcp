"""The temporary mirror maps each supported host to a verified upstream asset."""

import pytest
from camoufox.pkgman import RepoConfig

from justpen_browser_mcp import browser_mirror


@pytest.mark.parametrize(
    ("os_name", "arch", "filename"),
    [
        ("lin", "x86_64", "camoufox-152.0.4-beta.31-lin.x86_64.zip"),
        ("lin", "arm64", "camoufox-152.0.4-beta.31-lin.arm64.zip"),
        ("mac", "arm64", "camoufox-152.0.4-beta.31-mac.arm64.zip"),
        ("mac", "x86_64", "camoufox-152.0.4-beta.31-mac.x86_64.zip"),
        ("win", "x86_64", "camoufox-152.0.4-beta.31-win.x86_64.zip"),
        ("win", "i686", "camoufox-152.0.4-beta.31-win.i686.zip"),
    ],
)
def test_host_gets_matching_pinned_browser_asset(monkeypatch, os_name, arch, filename):
    monkeypatch.setattr(RepoConfig, "get_os_name", lambda _self: os_name)
    monkeypatch.setattr(RepoConfig, "get_arch", lambda _self: arch)
    candidate = browser_mirror.mirror_candidate()
    assert candidate is not None
    repo, asset = candidate
    assert repo.repo == "justpenkit/justpen-browser-mcp"
    assert asset.url == (
        "https://github.com/justpenkit/justpen-browser-mcp/releases/download/"
        "camoufox-ci-152.0.4-beta.31-eb5dc3b/" + filename
    )
    assert asset.sha256 is not None
    assert len(bytes.fromhex(asset.sha256)) == 32
    assert asset.asset_size is not None
    assert asset.asset_size > 0


def test_missing_platform_never_receives_another_architecture(monkeypatch):
    monkeypatch.setattr(RepoConfig, "get_os_name", lambda _self: "lin")
    monkeypatch.setattr(RepoConfig, "get_arch", lambda _self: "i686")
    assert browser_mirror.mirror_candidate() is None
