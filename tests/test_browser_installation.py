"""Real SDK installation must retain provenance and automatically return upstream."""

import hashlib
import io
import zipfile

import pytest
from camoufox import multiversion, pkgman
from camoufox.exceptions import CorruptedDownload

from justpen_browser_mcp import browser_runtime

pytestmark = pytest.mark.integration


def _archive(content):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Camoufox.app/Contents/Resources/", "")
        for executable in ("Camoufox.app/Contents/MacOS/camoufox", "camoufox-bin", "camoufox.exe"):
            archive.writestr(executable, content)
    return buffer.getvalue()


@pytest.fixture
def isolated_sdk(tmp_path, monkeypatch):
    for module in (pkgman, multiversion):
        monkeypatch.setattr(module, "INSTALL_DIR", tmp_path)
    monkeypatch.setattr(multiversion, "BROWSERS_DIR", tmp_path / "browsers")
    monkeypatch.setattr(multiversion, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(multiversion, "COMPAT_FLAG", tmp_path / ".0.5_FLAG")
    monkeypatch.setattr(pkgman, "ensure_browser_profile_dir", lambda: None)
    data = {"https://example.test/ci.zip": _archive("ci"), "https://example.test/official.zip": _archive("official")}
    downloads = []

    def download(file, url):
        downloads.append(url)
        file.write(data[url])
        file.seek(0)
        return file

    monkeypatch.setattr(pkgman.CamoufoxFetcher, "download_file", staticmethod(download))
    version = pkgman.Version(version="152.0.4", build="beta.31")
    repo = pkgman.RepoConfig.from_dict(
        {
            "name": "JustpenKit",
            "repo": "justpenkit/justpen-browser-mcp",
            "pattern": "{name}-{version}-{build}-{os}.{arch}.zip",
        }
    )
    mirror = pkgman.AvailableVersion(
        version,
        "https://example.test/ci.zip",
        is_prerelease=True,
        sha256=hashlib.sha256(data["https://example.test/ci.zip"]).hexdigest(),
    )
    monkeypatch.setattr(browser_runtime, "mirror_candidate", lambda: (repo, mirror))
    official = pkgman.AvailableVersion(
        pkgman.Version(version="152.0.4", build="beta.30"),
        "https://example.test/official.zip",
        is_prerelease=False,
        sha256=hashlib.sha256(data["https://example.test/official.zip"]).hexdigest(),
    )
    monkeypatch.setattr(browser_runtime, "list_available_versions", lambda **_kwargs: [official])
    return official, mirror, downloads


def test_installed_mirror_yields_to_same_version_official_and_preserves_source_hash(isolated_sdk):
    official, _mirror, downloads = isolated_sdk
    first = browser_runtime.prepare_runtime()
    assert first.installation.startswith("browsers/justpenkit/152.0.4-beta.31-")
    assert browser_runtime.prepare_runtime() == first
    assert downloads == ["https://example.test/ci.zip"]

    official.version = pkgman.Version(version="152.0.4", build="beta.31")
    official.is_prerelease = True
    second = browser_runtime.prepare_runtime()
    assert second.installation.startswith("browsers/official/152.0.4-beta.31-")
    assert multiversion.get_active_path() == pkgman.INSTALL_DIR / second.installation
    assert downloads == ["https://example.test/ci.zip", "https://example.test/official.zip"]
    assert browser_runtime.prepare_runtime() == second
    assert len(downloads) == 2
    installed = {item.repo_name: item for item in multiversion.list_installed()}
    assert installed["official"].sha256 == official.sha256
    assert installed["official"].sha256 != installed["justpenkit"].sha256


def test_mirror_hash_mismatch_does_not_activate_or_leave_partial_install(isolated_sdk):
    _official, mirror, _downloads = isolated_sdk
    mirror.sha256 = "0" * 64
    with pytest.raises(CorruptedDownload, match="Checksum mismatch"):
        browser_runtime.prepare_runtime()
    assert multiversion.get_active_path() is None
    assert multiversion.list_installed() == []
