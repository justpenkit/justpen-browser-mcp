"""`make install` provides the zstd headers indexed-zstd needs where it has no wheel."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def run_target(tmp_path: Path, platform: str, *, header_present: bool) -> list[str]:
    """Run the target with stub compiler and package tools; return the commands they saw."""
    log = tmp_path / "calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "cc": f"exit {0 if header_present else 1}",
        "sudo": f'echo "sudo $*" >> "{log}"',
        "apt-get": f'echo "apt-get $*" >> "{log}"',
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(f"#!/bin/sh\n{body}\n")
        stub.chmod(0o755)
    subprocess.run(
        ["make", "-s", "zstd-headers", f"ZSTD_PLATFORM={platform}"],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        check=True,
        capture_output=True,
        text=True,
    )
    return log.read_text().splitlines() if log.exists() else []


def test_missing_headers_are_installed_on_linux_aarch64(tmp_path):
    assert run_target(tmp_path, "Linux-aarch64", header_present=False) == ["sudo apt-get install -y libzstd-dev"]


@pytest.mark.parametrize(
    ("platform", "header_present"),
    [("Linux-aarch64", True), ("Linux-x86_64", False), ("Darwin-arm64", False)],
)
def test_nothing_is_installed_where_the_headers_or_wheels_exist(tmp_path, platform, header_present):
    assert run_target(tmp_path, platform, header_present=header_present) == []


def test_install_provides_the_headers_first():
    plan = subprocess.run(
        ["make", "-n", "install", "ZSTD_PLATFORM=Linux-x86_64"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    assert plan.index("libzstd-dev") < plan.index("uv sync")
