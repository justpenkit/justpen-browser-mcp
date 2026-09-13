"""Browser's existing release history survives Copier enrollment and later bumps."""

from __future__ import annotations

import os
import sys

import pytest

from .test_release import commit, git, release

pytestmark = pytest.mark.integration


@pytest.fixture
def project(tmp_path, monkeypatch):
    for key in os.environ:
        if key.startswith(("GIT_", "UV_")) or key in {"VIRTUAL_ENV", "MAKEFLAGS", "MAKEOVERRIDES", "MFLAGS"}:
            monkeypatch.delenv(key)
    monkeypatch.setenv("UV_PYTHON", sys.executable)
    monkeypatch.setenv("UV_OFFLINE", "1")
    repo = tmp_path / "app"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "release-fixture"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
        "[dependency-groups]\ndev = []\n"
        '[tool.commitizen]\nname = "cz_conventional_commits"\nversion_provider = "pep621"\ntag_format = "v$version"\n'
    )
    (repo / ".gitignore").write_text(".venv/\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Release Test")
    git(repo, "config", "user.email", "release@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    commit(repo, "feat: inherited template feature")
    git(repo, "tag", "-a", "v9.0.0", "-m", "template release")
    (repo / "history.py").write_text('"""History before Copier adoption."""\n')
    commit(repo, "fix: inherited template correction")
    (repo / ".copier-answers.yml").write_text("project_name: release-fixture\n")
    commit(repo, "chore: initialize application")
    git(repo, "switch", "-qc", "release/first")
    (repo / "app.py").write_text('"""Application."""\n')
    commit(repo, "feat: application feature")
    return repo


@pytest.mark.parametrize("start_rev", ["", "v9.0.0"])
def test_explicit_changelog_start_rev_preserves_existing_application_history(project, start_rev):
    metadata = project / "pyproject.toml"
    metadata.write_text(metadata.read_text() + f'changelog_start_rev = "{start_rev}"\n')
    commit(project, "chore: configure existing application history")
    original_metadata = metadata.read_bytes()
    original_tags = git(project, "show-ref", "--tags")

    release.changelog(project)
    changelog = (project / "CHANGELOG.md").read_text()
    assert "application feature" in changelog
    assert "inherited template correction" in changelog
    if start_rev:
        assert "inherited template feature" not in changelog
    else:
        assert "inherited template feature" in changelog
        assert "v9.0.0" in changelog

    release.changelog(project)
    assert (project / "CHANGELOG.md").read_text() == changelog
    assert metadata.read_bytes() == original_metadata
    assert git(project, "show-ref", "--tags") == original_tags


@pytest.mark.parametrize("project_name", ["release-fixture", "custom.project"])
def test_future_bump_preserves_existing_application_history_and_tag(project, project_name):
    metadata = project / "pyproject.toml"
    repository = f"https://github.com/acme/{project_name}"
    metadata.write_text(
        metadata.read_text()
        .replace('name = "release-fixture"', f'name = "{project_name}"')
        .replace('version = "0.0.0"', 'version = "0.4.0"')
        + 'changelog_start_rev = ""\n'
        + f'\n[project.urls]\nRepository = "{repository}"\n'
    )
    original_metadata = metadata.read_text()
    original = f'uv add "{project_name} @ git+{repository}@v0.4.0"\n'
    (project / "README.md").write_text(original)
    commit(project, "docs: document current application release")
    git(project, "tag", "-a", "v0.4.0", "-m", "existing application release")
    previous_tag = git(project, "rev-parse", "v0.4.0")
    (project / "app.py").write_text('"""Next application feature."""\n')
    commit(project, "feat: next application feature")

    release.bump(project, "patch")

    assert (project / "README.md").read_text() == original.replace("@v0.4.0", "@v0.4.1")
    assert git(project, "show", "v0.4.0:README.md") == original.strip()
    assert git(project, "show", "v0.4.0:pyproject.toml") == original_metadata.strip()
    assert git(project, "rev-parse", "v0.4.0") == previous_tag
    changelog = (project / "CHANGELOG.md").read_text()
    assert "inherited template feature" in changelog
    assert "inherited template correction" in changelog
    assert "next application feature" in changelog
    assert "v9.0.0" in changelog
    assert "v0.4.1" not in git(project, "tag").splitlines()
    assert git(project, "status", "--porcelain") == ""
