"""Server configuration loaded from environment variables."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _parse_bool(raw: str, *, default: bool, name: str) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    logger.warning("%s=%r is not a boolean, defaulting to %s", name, raw, default)
    return default


def _parse_int(raw: str, *, default: int, name: str, minimum: int | None = None) -> int:
    try:
        val = int(raw.strip())
    except ValueError:
        logger.warning("%s=%r is not an int, defaulting to %d", name, raw, default)
        return default
    if minimum is not None and val < minimum:
        logger.warning("%s=%d is below minimum %d, defaulting to %d", name, val, minimum, default)
        return default
    return val


def _parse_window(raw: str) -> tuple[int, int] | None:
    txt = raw.strip().lower().replace(" ", "")
    if not txt:
        return None
    if "x" not in txt:
        logger.warning("BROWSER_MCP_WINDOW=%r is not WxH, ignoring", raw)
        return None
    w, _, h = txt.partition("x")
    try:
        return (int(w), int(h))
    except ValueError:
        logger.warning("BROWSER_MCP_WINDOW=%r is not WxH, ignoring", raw)
        return None


def _coerce_pref(value: str) -> bool | int | str:
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def _parse_prefs(raw: str) -> dict[str, Any]:
    prefs: dict[str, Any] = {}
    for chunk in raw.split(";"):
        item = chunk.strip()
        if not item:
            continue
        if "=" not in item:
            logger.warning("Ignoring malformed firefox pref %r (expected k=v)", item)
            continue
        k, _, v = item.partition("=")
        prefs[k.strip()] = _coerce_pref(v.strip())
    return prefs


def _parse_proxy(env: Mapping[str, str]) -> dict[str, str] | None:
    server = env.get("BROWSER_MCP_PROXY_SERVER", "").strip()
    if not server:
        return None
    proxy = {"server": server}
    user = env.get("BROWSER_MCP_PROXY_USERNAME", "").strip()
    pwd = env.get("BROWSER_MCP_PROXY_PASSWORD", "").strip()
    if user:
        proxy["username"] = user
    if pwd:
        proxy["password"] = pwd
    return proxy


@dataclass(frozen=True)
class BrowserServerConfig:
    """Runtime configuration for the camoufox-mcp server.

    Loaded once at server startup from environment variables.
    """

    log_level: str = "INFO"
    max_instances: int = 10
    idle_ttl_seconds: int = 0
    reaper_interval_seconds: int = 30
    transport: Literal["stdio", "http"] = "stdio"
    host: str = "127.0.0.1"
    port: int = 8931
    headless: bool | Literal["virtual"] = True
    proxy: dict[str, str] | None = None
    camoufox_os: tuple[str, ...] | None = None
    locale: str | None = None
    geoip: bool = False
    humanize: bool | float = True
    block_images: bool = False
    block_webrtc: bool = True
    block_webgl: bool = False
    window: tuple[int, int] | None = None
    firefox_user_prefs: dict[str, Any] = field(default_factory=dict[str, Any])
    camoufox_args: tuple[str, ...] = ()
    enable_cache: bool = True
    ff_version: int | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> BrowserServerConfig:
        """Build a config from a dict-like env mapping (typically os.environ).

        Recognized variables (all prefixed ``BROWSER_MCP_``): ``LOG_LEVEL``,
        ``MAX_INSTANCES``, ``IDLE_TTL_SECONDS``, ``REAPER_INTERVAL_SECONDS``,
        ``TRANSPORT``, ``HOST``, ``PORT``, ``HEADLESS``, ``PROXY_SERVER`` (+
        ``PROXY_USERNAME``/``PROXY_PASSWORD``), ``CAMOUFOX_OS``, ``LOCALE``,
        ``GEOIP``, ``BLOCK_IMAGES``, ``BLOCK_WEBRTC``, ``BLOCK_WEBGL``,
        ``WINDOW``, ``FIREFOX_PREFS``, ``CAMOUFOX_ARGS``, ``ENABLE_CACHE``,
        ``FF_VERSION``. Invalid values log a warning and fall back to the
        default (validate-warn-default).
        """
        log_level = env.get("BROWSER_MCP_LOG_LEVEL", "INFO").strip().upper()
        max_instances = _parse_int(
            env.get("BROWSER_MCP_MAX_INSTANCES", "10"), default=10, name="BROWSER_MCP_MAX_INSTANCES", minimum=1
        )
        idle_ttl = _parse_int(
            env.get("BROWSER_MCP_IDLE_TTL_SECONDS", "0"), default=0, name="BROWSER_MCP_IDLE_TTL_SECONDS", minimum=0
        )
        reaper_interval = _parse_int(
            env.get("BROWSER_MCP_REAPER_INTERVAL_SECONDS", "30"),
            default=30,
            name="BROWSER_MCP_REAPER_INTERVAL_SECONDS",
            minimum=1,
        )
        transport_raw = env.get("BROWSER_MCP_TRANSPORT", "stdio").strip().lower()
        if transport_raw not in {"stdio", "http"}:
            logger.warning("BROWSER_MCP_TRANSPORT=%r invalid, defaulting to stdio", transport_raw)
            transport_raw = "stdio"
        transport: Literal["stdio", "http"] = "http" if transport_raw == "http" else "stdio"
        host = env.get("BROWSER_MCP_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port = _parse_int(env.get("BROWSER_MCP_PORT", "8931"), default=8931, name="BROWSER_MCP_PORT", minimum=1)

        headless_raw = env.get("BROWSER_MCP_HEADLESS", "true").strip().lower()
        headless: bool | Literal["virtual"] = (
            "virtual"
            if headless_raw == "virtual"
            else _parse_bool(headless_raw, default=True, name="BROWSER_MCP_HEADLESS")
        )
        os_raw = env.get("BROWSER_MCP_CAMOUFOX_OS", "").strip()
        camoufox_os = tuple(p.strip() for p in os_raw.split(",") if p.strip()) or None
        locale = env.get("BROWSER_MCP_LOCALE", "").strip() or None
        geoip = _parse_bool(env.get("BROWSER_MCP_GEOIP", "false"), default=False, name="BROWSER_MCP_GEOIP")
        block_images = _parse_bool(
            env.get("BROWSER_MCP_BLOCK_IMAGES", "false"), default=False, name="BROWSER_MCP_BLOCK_IMAGES"
        )
        block_webrtc = _parse_bool(
            env.get("BROWSER_MCP_BLOCK_WEBRTC", "true"), default=True, name="BROWSER_MCP_BLOCK_WEBRTC"
        )
        block_webgl = _parse_bool(
            env.get("BROWSER_MCP_BLOCK_WEBGL", "false"), default=False, name="BROWSER_MCP_BLOCK_WEBGL"
        )
        enable_cache = _parse_bool(
            env.get("BROWSER_MCP_ENABLE_CACHE", "true"), default=True, name="BROWSER_MCP_ENABLE_CACHE"
        )
        window = _parse_window(env.get("BROWSER_MCP_WINDOW", ""))
        prefs = _parse_prefs(env.get("BROWSER_MCP_FIREFOX_PREFS", ""))
        args_raw = env.get("BROWSER_MCP_CAMOUFOX_ARGS", "").strip()
        camoufox_args = tuple(p for p in args_raw.split() if p)
        ff_version_raw = env.get("BROWSER_MCP_FF_VERSION", "").strip()
        ff_version = int(ff_version_raw) if ff_version_raw.isdigit() else None

        return cls(
            log_level=log_level,
            max_instances=max_instances,
            idle_ttl_seconds=idle_ttl,
            reaper_interval_seconds=reaper_interval,
            transport=transport,
            host=host,
            port=port,
            headless=headless,
            proxy=_parse_proxy(env),
            camoufox_os=camoufox_os,
            locale=locale,
            geoip=geoip,
            block_images=block_images,
            block_webrtc=block_webrtc,
            block_webgl=block_webgl,
            window=window,
            firefox_user_prefs=prefs,
            camoufox_args=camoufox_args,
            enable_cache=enable_cache,
            ff_version=ff_version,
        )
