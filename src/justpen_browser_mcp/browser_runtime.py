"""Select the Camoufox release compatible with this project's Playwright driver.

The SDK commands update its shared default browser for future launches.
Checking again after fetch is necessary because the SDK can exit successfully
without installing the requested version.
"""

import asyncio
import logging
import sys

from camoufox.pkgman import installed_verstr

from .errors import BinaryNotFoundError

CAMOUFOX_VERSION = "135.0.1-beta.24"
CAMOUFOX_RELEASE = f"official/{CAMOUFOX_VERSION}"
CAMOUFOX_PIN = f"official/stable/{CAMOUFOX_VERSION}"

logger = logging.getLogger(__name__)


async def ensure_camoufox_binary() -> None:
    """Fetch the pinned browser when absent or when another release is active."""
    try:
        installed = installed_verstr()
    except (OSError, RuntimeError, ValueError):
        installed = None
    if installed == CAMOUFOX_VERSION:
        return

    logger.warning("Selecting Camoufox %s for Playwright compatibility (current: %s)", CAMOUFOX_VERSION, installed)
    # Fetch alone does not activate an already-cached release when another
    # version is active. The public set command handles that case explicitly.
    for command, specifier in (("fetch", CAMOUFOX_RELEASE), ("set", CAMOUFOX_PIN)):
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "camoufox",
            command,
            specifier,
            stdout=sys.stderr,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            raise
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise BinaryNotFoundError(f"Camoufox {command} failed for {CAMOUFOX_VERSION}: {detail}")

    try:
        installed = installed_verstr()
    except (OSError, RuntimeError, ValueError) as exc:
        raise BinaryNotFoundError(f"Camoufox {CAMOUFOX_VERSION} is still unavailable after fetch: {exc}") from exc
    if installed != CAMOUFOX_VERSION:
        raise BinaryNotFoundError(f"Camoufox fetch did not select {CAMOUFOX_VERSION}; active browser is {installed}")
    logger.info("Camoufox %s is ready", CAMOUFOX_VERSION)


def cli() -> None:
    """Install and verify the pinned browser for developer setup or CI."""
    asyncio.run(ensure_camoufox_binary())


if __name__ == "__main__":
    cli()
