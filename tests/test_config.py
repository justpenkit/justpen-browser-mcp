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


def test_no_headless_attribute():
    cfg = BrowserServerConfig.from_env({})
    assert not hasattr(cfg, "headless")
