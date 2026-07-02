"""Command-line argument parsing for the justpen-browser-mcp server.

CLI flags override BROWSER_MCP_* environment variables. Parsing/validation is
delegated to BrowserServerConfig.from_env by projecting CLI values onto an env
overlay, so the precedence rule (CLI > env > default) lives in one place.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from .config import BrowserServerConfig

if TYPE_CHECKING:
    from collections.abc import Mapping


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="justpen-browser-mcp", description="Camoufox multi-instance MCP server.")
    p.add_argument("--log-level")
    p.add_argument("--max-instances", type=int)
    p.add_argument("--idle-ttl", type=int, help="Idle TTL seconds; 0 disables the reaper.")
    p.add_argument("--reaper-interval", type=int)
    p.add_argument("--transport", choices=["stdio", "http"])
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    headless = p.add_mutually_exclusive_group()
    headless.add_argument("--headless", dest="headless", action="store_true", default=None)
    headless.add_argument("--headful", dest="headless", action="store_false", default=None)
    p.add_argument("--proxy", help="Proxy server URL, e.g. http://user:pass@host:port")
    p.add_argument("--proxy-username")
    p.add_argument("--proxy-password")
    p.add_argument("--camoufox-os", help="Comma-separated OS list, e.g. windows,macos,linux")
    p.add_argument("--locale")
    p.add_argument("--geoip", action="store_true", default=None)
    p.add_argument("--block-images", action="store_true", default=None)
    p.add_argument("--window", help="Window size as WxH, e.g. 1280x800")
    p.add_argument("--firefox-pref", action="append", default=None, metavar="K=V")
    p.add_argument("--camoufox-arg", action="append", default=None)
    cache = p.add_mutually_exclusive_group()
    cache.add_argument("--enable-cache", dest="enable_cache", action="store_true", default=None)
    cache.add_argument("--no-cache", dest="enable_cache", action="store_false", default=None)
    p.add_argument("--ff-version", type=int)
    return p


def build_config(argv: list[str], env: Mapping[str, str]) -> BrowserServerConfig:
    """Parse CLI args and merge over env (CLI wins), then build the config."""
    ns = _build_parser().parse_args(argv)
    overlay: dict[str, str] = dict(env)

    def put(key: str, value: object) -> None:
        if value is not None:
            overlay[key] = str(value)

    put("BROWSER_MCP_LOG_LEVEL", ns.log_level)
    put("BROWSER_MCP_MAX_INSTANCES", ns.max_instances)
    put("BROWSER_MCP_IDLE_TTL_SECONDS", ns.idle_ttl)
    put("BROWSER_MCP_REAPER_INTERVAL_SECONDS", ns.reaper_interval)
    put("BROWSER_MCP_TRANSPORT", ns.transport)
    put("BROWSER_MCP_HOST", ns.host)
    put("BROWSER_MCP_PORT", ns.port)
    if ns.headless is not None:
        overlay["BROWSER_MCP_HEADLESS"] = "true" if ns.headless else "false"
    put("BROWSER_MCP_PROXY_SERVER", ns.proxy)
    put("BROWSER_MCP_PROXY_USERNAME", ns.proxy_username)
    put("BROWSER_MCP_PROXY_PASSWORD", ns.proxy_password)
    put("BROWSER_MCP_CAMOUFOX_OS", ns.camoufox_os)
    put("BROWSER_MCP_LOCALE", ns.locale)
    if ns.geoip:
        overlay["BROWSER_MCP_GEOIP"] = "true"
    if ns.block_images:
        overlay["BROWSER_MCP_BLOCK_IMAGES"] = "true"
    put("BROWSER_MCP_WINDOW", ns.window)
    if ns.firefox_pref:
        overlay["BROWSER_MCP_FIREFOX_PREFS"] = ";".join(ns.firefox_pref)
    if ns.camoufox_arg:
        overlay["BROWSER_MCP_CAMOUFOX_ARGS"] = " ".join(ns.camoufox_arg)
    if ns.enable_cache is not None:
        overlay["BROWSER_MCP_ENABLE_CACHE"] = "true" if ns.enable_cache else "false"
    put("BROWSER_MCP_FF_VERSION", ns.ff_version)

    return BrowserServerConfig.from_env(overlay)
