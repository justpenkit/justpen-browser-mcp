"""Server configuration loaded from environment variables."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserServerConfig:
    """Runtime configuration for the camoufox-mcp server.

    Loaded once at server startup from environment variables. Defaults
    are conservative (headless=True, log_level=INFO) and suitable for
    Docker container execution.
    """

    headless: bool = True
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BrowserServerConfig":
        """Build a config from a dict-like env mapping (typically os.environ).

        Recognized variables:
            BROWSER_MCP_HEADLESS: 'true' or 'false' (case-insensitive),
                defaults to 'true'.
            BROWSER_MCP_LOG_LEVEL: standard Python log level name,
                defaults to 'INFO'.
        """
        headless_raw = env.get("BROWSER_MCP_HEADLESS", "true").strip().lower()
        if headless_raw not in ("true", "false"):
            logger.warning(
                "BROWSER_MCP_HEADLESS=%r is not 'true' or 'false', defaulting to 'true'",
                headless_raw,
            )
            headless_raw = "true"
        headless = headless_raw == "true"

        log_level = env.get("BROWSER_MCP_LOG_LEVEL", "INFO").strip().upper()

        return cls(headless=headless, log_level=log_level)
