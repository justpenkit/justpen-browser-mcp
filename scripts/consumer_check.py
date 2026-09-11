"""Build and exercise the wheel in isolated locked and minimum consumer environments."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


def _run(cwd: Path, *arguments: str, timeout: float = 600) -> None:
    excluded = {"VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT", "UV_PROJECT", "UV_WORKING_DIR", "PYTHONPATH"}
    environment = {
        key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("BROWSER_MCP_")
    }
    if os.name == "nt":
        raise RuntimeError("Run browser consumer checks inside WSL on Windows.")
    with subprocess.Popen(arguments, cwd=cwd, env=environment, start_new_session=True) as process:
        try:
            code = process.wait(timeout=timeout)
        finally:
            _stop_group(process)
        if code:
            raise subprocess.CalledProcessError(code, arguments)


def _stop_group(process: subprocess.Popen[bytes]) -> None:
    """Drain the owned subprocess group before deleting its temporary environment."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=2)
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def check_consumers(repo: Path, *, browser: bool) -> None:
    """Resolve genuine consumer installations without editing the project lock."""
    project = tomllib.loads((repo / "pyproject.toml").read_text())["project"]
    with tempfile.TemporaryDirectory(prefix="browser-mcp-consumer-") as directory:
        scratch = Path(directory)
        wheels = scratch / "dist"
        _run(repo, "uv", "build", "--wheel", "--out-dir", str(wheels))
        wheel = next(wheels.glob("*.whl"))
        requirements = scratch / "locked.txt"
        _run(
            repo,
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--output-file",
            str(requirements),
        )
        for mode in ("locked", "minimum"):
            environment = scratch / mode
            _run(scratch, "uv", "venv", "--python", sys.executable, str(environment))
            python = environment / "bin/python"
            if mode == "locked":
                _run(scratch, "uv", "pip", "sync", "--python", str(python), str(requirements))
                _run(scratch, "uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel))
            else:
                # Supplying direct requirements explicitly makes lowest-direct
                # apply to the application's dependencies, not just its wheel.
                _run(
                    scratch,
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--resolution",
                    "lowest-direct",
                    str(wheel),
                    *project["dependencies"],
                )
            smoke = [str(python), "-I", str(repo / "tests/consumer_smoke.py"), "--source-root", str(repo)]
            if browser:
                smoke.append("--browser")
            _run(scratch, *smoke)
            executable = python.with_name("justpen-browser-mcp")
            _run(scratch, str(executable), "--help")
            print(f"Consumer wheel check passed: {mode}", flush=True)


def main() -> None:
    """Run the Make consumer verification target."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="Exercise the installed Camoufox binary as well.")
    arguments = parser.parse_args()
    check_consumers(Path(__file__).resolve().parent.parent, browser=arguments.browser)


if __name__ == "__main__":
    main()
