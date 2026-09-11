"""Consumer checks clean up their subprocess tree when a deadline expires."""

import contextlib
import importlib.util
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "consumer_check", Path(__file__).resolve().parents[1] / "scripts/consumer_check.py"
)
assert SPEC is not None
assert SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(consumer)


@pytest.mark.skipif(os.name == "nt", reason="The browser consumer runs on POSIX/WSL.")
def test_timeout_terminates_the_check_and_its_grandchild(tmp_path):
    lockfile = tmp_path / "held.lock"
    child = tmp_path / "child.py"
    child.write_text(
        "import fcntl, os, time\n"
        f"with open({str(lockfile)!r}, 'w') as stream:\n"
        "    fcntl.flock(stream, fcntl.LOCK_EX)\n"
        "    stream.write(str(os.getpid())); stream.flush()\n"
        "    time.sleep(30)\n"
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, {str(child)!r}])\ntime.sleep(30)\n"
    )
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            consumer._run(tmp_path, sys.executable, str(parent), timeout=2)
        assert lockfile.read_text(), "Grandchild never acquired the test lock"
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import fcntl,sys; f=open(sys.argv[1]); fcntl.flock(f, fcntl.LOCK_EX|fcntl.LOCK_NB)",
                str(lockfile),
            ],
            capture_output=True,
            check=False,
            timeout=5,
        )
        assert probe.returncode == 0, "Grandchild still holds its lock after parent timeout"
    finally:
        if lockfile.exists() and lockfile.read_text():
            with contextlib.suppress(ProcessLookupError):
                os.kill(int(lockfile.read_text()), signal.SIGKILL)
