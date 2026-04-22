"""Server configuration loaded from environment variables."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrowserServerConfig:
    """Runtime configuration for the camoufox-mcp server.

    Loaded once at server startup from environment variables.
    """

    log_level: str = "INFO"
    max_instances: int = 10

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BrowserServerConfig":
        """Build a config from a dict-like env mapping (typically os.environ).

        Recognized variables:
            BROWSER_MCP_LOG_LEVEL: standard Python log level name, defaults to 'INFO'.
            BROWSER_MCP_MAX_INSTANCES: positive int cap on live instances, defaults to 10.
                Invalid or non-positive values log a warning and fall back to the default.
        """
        log_level = env.get("BROWSER_MCP_LOG_LEVEL", "INFO").strip().upper()

        raw = env.get("BROWSER_MCP_MAX_INSTANCES", "10").strip()
        try:
            max_instances = int(raw)
        except ValueError:
            logger.warning("BROWSER_MCP_MAX_INSTANCES=%r is not an int, defaulting to 10", raw)
            max_instances = 10
        if max_instances < 1:
            logger.warning("BROWSER_MCP_MAX_INSTANCES=%d is not positive, defaulting to 10", max_instances)
            max_instances = 10

        return cls(log_level=log_level, max_instances=max_instances)
