"""Integrate project configuration with Commitizen's real checker."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parent.parent


def check_message(*arguments):
    # Commitizen configures process-wide logging at import; isolate its real CLI
    # so collecting or running these tests cannot disable application loggers.
    return subprocess.run(
        [sys.executable, "-m", "commitizen", "-n", "cz_customize", "check", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize(
    ("message", "accepted"),
    [
        ("feat: add a tool", True),
        ("fix(browser tools)!: correct lifecycle", True),
        ("docs: ölçüm örneği", True),
        ("chore: " + "a" * 65, True),
        ("chore: " + "a" * 66, False),
        ("fix: trailing period.", False),
        ("bump: 0.1.0", False),
        ("unknown: a message", False),
        ("fix(): empty scope", False),
        ("fix((nested)): scope", False),
        ("fix:subject", False),
        ("", False),
        ("fix: subject\nBody without a blank separator", True),
        ("fix: subject\n\nBody with a separator", True),
        ("Merge branch 'feature'", True),
        ('Revert "old change"', True),
        ("fixup! old subject", True),
        ("squash! old subject", True),
        ("amend! old subject", True),
        ("Mergeanything", False),
        ("Pull request anything", False),
    ],
)
def test_commitizen_checks_project_policy(message, accepted):
    settings = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["commitizen"]
    assert settings["name"] == "cz_conventional_commits"
    assert settings["version_provider"] == "pep621"
    result = check_message("--message", message)
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("raw", "accepted"),
    [
        pytest.param("# Git comment\nfix: message\n", True, id="git-comment"),
        # The previous script discarded indented comments as well.
        pytest.param("  # comment\nfix: message\n", False, id="indented-comment-is-content"),
        # Commitizen trims the outside of a message; the previous script rejected
        # a leading blank line and counted the trailing space in this 73-char line.
        pytest.param("\nfix: message\n", True, id="leading-blank-normalized"),
        pytest.param("fix: " + "a" * 67 + " \n", True, id="trailing-space-normalized"),
        # The period is terminal after normalization, unlike the previous script.
        pytest.param("fix: message. \n", False, id="period-before-trailing-space"),
        pytest.param(
            "fix: message\n# ------------------------ >8 ------------------------\ndiff --git a/a b/a\n",
            True,
            id="verbose-diff-excluded",
        ),
        # The previous script ignored the scissors comment and accepted the
        # following subject; Commitizen correctly treats that content as excluded.
        pytest.param(
            "# ------------------------ >8 ------------------------\nfix: message\n",
            False,
            id="subject-after-scissors-excluded",
        ),
    ],
)
def test_commitizen_normalizes_git_message_files(tmp_path, raw, accepted):
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text(raw)
    result = check_message("--commit-msg-file", str(message))
    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
