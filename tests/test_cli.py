from justpen_browser_mcp.cli import build_config


def test_cli_overrides_env():
    cfg = build_config(
        ["--max-instances", "3", "--transport", "http", "--port", "9000"],
        env={"BROWSER_MCP_MAX_INSTANCES": "10", "BROWSER_MCP_TRANSPORT": "stdio"},
    )
    assert cfg.max_instances == 3
    assert cfg.transport == "http"
    assert cfg.port == 9000


def test_cli_falls_back_to_env_when_flag_absent():
    cfg = build_config([], env={"BROWSER_MCP_MAX_INSTANCES": "7"})
    assert cfg.max_instances == 7


def test_cli_headful_flag_sets_headless_false():
    cfg = build_config(["--headful"], env={})
    assert cfg.headless is False


def test_cli_repeatable_firefox_pref():
    cfg = build_config(
        ["--firefox-pref", "intl.accept_languages=en-US", "--firefox-pref", "dom.webnotifications.enabled=false"],
        env={},
    )
    assert cfg.firefox_user_prefs == {
        "intl.accept_languages": "en-US",
        "dom.webnotifications.enabled": False,
    }


def test_cli_proxy_and_os():
    cfg = build_config(["--proxy", "http://p:8080", "--camoufox-os", "windows,macos"], env={})
    assert cfg.proxy == {"server": "http://p:8080"}
    assert cfg.camoufox_os == ("windows", "macos")


def test_cli_window_and_geoip():
    cfg = build_config(["--window", "1024x768", "--geoip"], env={})
    assert cfg.window == (1024, 768)
    assert cfg.geoip is True
