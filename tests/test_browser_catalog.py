"""Only published platform assets may outrank the temporary fixed browser."""

import json
from typing import Any
from urllib.parse import urlsplit

import pytest
import requests
from camoufox import pkgman

from justpen_browser_mcp import browser_releases, browser_runtime


@pytest.fixture
def api(monkeypatch):
    responses = []
    requests = []

    def send(_session, request, **kwargs):
        url = urlsplit(request.url)
        assert url.hostname == "api.github.com"
        assert url.scheme == "https"
        assert kwargs["timeout"] > 0
        requests.append((request.method, url.path + "?" + url.query, dict(request.headers)))
        status, value = responses.pop(0)
        response = browser_releases.requests.Response()
        response.status_code = status
        response.url = request.url
        response._content = json.dumps(value).encode()
        _ = response.content
        return response

    monkeypatch.setattr(browser_releases.requests.Session, "send", send)
    return responses, requests


def _repo():
    return next(repo for repo in pkgman.RepoConfig.load_repos() if repo.name == "Official")


def _release(build, *, draft=False, prerelease=True) -> dict[str, Any]:
    repo = _repo()
    return {
        "draft": draft,
        "prerelease": prerelease,
        "published_at": None if draft else "2026-09-14T00:00:00Z",
        "assets": [
            {
                "name": f"camoufox-152.0.4-{build}-{repo.get_os_name()}.{repo.get_arch()}.zip",
                "browser_download_url": f"https://example.test/{build}.zip",
                "digest": "sha256:" + "a" * 64,
                "id": 10,
                "size": 100,
                "updated_at": "2026-09-14T00:00:00Z",
                "created_at": "2026-09-13T00:00:00Z",
            }
        ],
    }


def test_authorized_catalog_draft_cannot_outrank_published_release(api, monkeypatch):
    responses, requests = api
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    responses.append((200, [_release("beta.99", draft=True), _release("beta.31")]))
    selected = browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.31"]
    assert requests[0][2]["Authorization"] == "Bearer test-token"
    assert selected[0].sha256 == "a" * 64
    assert selected[0].asset_id == 10
    assert selected[0].asset_size == 100


def test_catalog_pagination_cannot_hide_a_new_published_browser(api):
    responses, requests = api
    responses.extend([(200, [_release("beta.99", draft=True)] * 100), (200, [_release("beta.32")])])
    selected = browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.32"]
    assert len(requests) == 2
    assert requests[1][1].endswith("page=2")


def test_unpublished_and_wrong_platform_assets_are_excluded(api):
    responses, _requests = api
    unpublished = _release("beta.99")
    unpublished["published_at"] = None
    wrong_platform = _release("beta.98")
    wrong_platform["assets"][0]["name"] = "camoufox-152.0.4-beta.98-unknown.cpu.zip"
    responses.append((200, [unpublished, wrong_platform, _release("beta.31")]))
    selected = browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.31"]


def test_explicit_stable_only_filter_is_preserved(api):
    responses, _requests = api
    responses.append((200, [_release("beta.32"), _release("beta.31", prerelease=False)]))
    selected = browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=False)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.31"]


def test_configured_official_repository_fallback_is_used(api):
    responses, requests = api
    responses.extend([(503, {}), (200, [_release("beta.31")])])
    selected = browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.31"]
    assert "/repos/daijro/camoufox/" in requests[0][1]
    assert "/repos/camoufox/camoufox/" in requests[1][1]


def test_all_remote_failures_propagate_instead_of_using_a_stale_catalog(api):
    responses, _requests = api
    responses.extend([(403, {}), (503, {})])
    with pytest.raises(requests.HTTPError, match="503"):
        browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)


def test_malformed_catalog_is_rejected(api):
    responses, _requests = api
    responses.extend([(200, {}), (200, ["not a release"])])
    with pytest.raises(TypeError, match="Malformed"):
        browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)


def test_repository_version_constraints_are_preserved(api):
    responses, _requests = api
    repo = next(repo for repo in pkgman.RepoConfig.load_repos() if repo.name == "Official")
    repo.prerelease_min = "beta.31"
    repo.prerelease_max = "beta.32"
    responses.append((200, [_release("beta.99"), _release("beta.31")]))
    selected = browser_runtime.list_available_versions(repo_config=repo, include_prerelease=True)
    assert [entry.version.full_string for entry in selected] == ["152.0.4-beta.31"]


def test_proxy_and_custom_ca_environment_reaches_https_transport(api, monkeypatch, tmp_path):
    responses, _requests = api
    responses.append((200, [_release("beta.31")]))
    ca_file = tmp_path / "ca.pem"
    ca_file.touch()
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(ca_file))
    options = []
    original_send = requests.Session.send

    def send(session, request, **kwargs):
        options.append(kwargs)
        return original_send(session, request, **kwargs)

    monkeypatch.setattr(requests.Session, "send", send)
    browser_runtime.list_available_versions(repo_config=_repo(), include_prerelease=True)
    assert options
    assert options[0]["proxies"]["https"] == "http://proxy.example:8080"
    assert options[0]["verify"] == str(ca_file)
