"""Tests for BrowserServerConfig environment parsing."""

from justpen_browser_mcp.config import BrowserServerConfig


def test_defaults_when_env_empty():
    cfg = BrowserServerConfig.from_env({})
    assert cfg.log_level == "INFO"
    assert cfg.max_instances == 10


def test_log_level_uppercased():
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_LOG_LEVEL": "debug"})
    assert cfg.log_level == "DEBUG"


def test_max_instances_parsed():
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_MAX_INSTANCES": "25"})
    assert cfg.max_instances == 25


def test_max_instances_invalid_falls_back():
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_MAX_INSTANCES": "nope"})
    assert cfg.max_instances == 10


def test_max_instances_zero_or_negative_falls_back():
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_MAX_INSTANCES": "0"})
    assert cfg.max_instances == 10
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_MAX_INSTANCES": "-5"})
    assert cfg.max_instances == 10


def test_from_env_parses_new_management_fields():
    cfg = BrowserServerConfig.from_env(
        {
            "BROWSER_MCP_IDLE_TTL_SECONDS": "1800",
            "BROWSER_MCP_REAPER_INTERVAL_SECONDS": "60",
            "BROWSER_MCP_TRANSPORT": "http",
            "BROWSER_MCP_HOST": "127.0.0.1",
            "BROWSER_MCP_PORT": "8931",
        }
    )
    assert cfg.idle_ttl_seconds == 1800
    assert cfg.reaper_interval_seconds == 60
    assert cfg.transport == "http"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8931


def test_from_env_parses_camoufox_defaults():
    cfg = BrowserServerConfig.from_env(
        {
            "BROWSER_MCP_HEADLESS": "false",
            "BROWSER_MCP_PROXY_SERVER": "http://proxy:8080",
            "BROWSER_MCP_CAMOUFOX_OS": "windows,macos",
            "BROWSER_MCP_LOCALE": "en-US",
            "BROWSER_MCP_GEOIP": "true",
            "BROWSER_MCP_WINDOW": "1280x800",
            "BROWSER_MCP_FIREFOX_PREFS": "intl.accept_languages=en-US;dom.webnotifications.enabled=false",
        }
    )
    assert cfg.headless is False
    assert cfg.proxy == {"server": "http://proxy:8080"}
    assert cfg.camoufox_os == ("windows", "macos")
    assert cfg.locale == "en-US"
    assert cfg.geoip is True
    assert cfg.window == (1280, 800)
    assert cfg.firefox_user_prefs == {
        "intl.accept_languages": "en-US",
        "dom.webnotifications.enabled": False,
    }


def test_from_env_invalid_values_fall_back_with_warning(caplog):
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_TRANSPORT": "carrier-pigeon", "BROWSER_MCP_PORT": "not-an-int"})
    assert cfg.transport == "stdio"
    assert cfg.port == 8931


def test_defaults_are_conservative():
    cfg = BrowserServerConfig.from_env({})
    assert cfg.idle_ttl_seconds == 0  # reaper disabled by default
    assert cfg.transport == "stdio"
    assert cfg.headless is True
    assert cfg.proxy is None
    assert cfg.firefox_user_prefs == {}


def test_ff_version_invalid_falls_back_to_none_with_warning(caplog):
    with caplog.at_level("WARNING"):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_FF_VERSION": "abc"})
    assert cfg.ff_version is None
    assert "BROWSER_MCP_FF_VERSION" in caplog.text
    assert "abc" in caplog.text


def test_ff_version_valid_parsed():
    cfg = BrowserServerConfig.from_env({"BROWSER_MCP_FF_VERSION": "135"})
    assert cfg.ff_version == 135


def test_ff_version_unset_defaults_to_none_without_warning(caplog):
    with caplog.at_level("WARNING"):
        cfg = BrowserServerConfig.from_env({})
    assert cfg.ff_version is None
    assert "BROWSER_MCP_FF_VERSION" not in caplog.text


def test_host_empty_but_set_falls_back_with_warning(caplog):
    with caplog.at_level("WARNING"):
        cfg = BrowserServerConfig.from_env({"BROWSER_MCP_HOST": "   "})
    assert cfg.host == "127.0.0.1"
    assert "BROWSER_MCP_HOST" in caplog.text
