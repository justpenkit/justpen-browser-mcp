.DEFAULT_GOAL := help
PYTHON_PATHS := src/ tests/ scripts/
COVERAGE_SOURCE := justpen_browser_mcp
FAST_TEST_MARKERS := not e2e

include scripts/development.mk

.PHONY: browser-fetch test-e2e test-consumer format-html format-html-check format-css format-css-check

help::
	@echo "  browser-fetch          Install the Camoufox browser binary"
	@echo "  test-e2e               Run the real Camoufox browser suite"
	@echo "  test-consumer          Test isolated locked/minimum wheel installs with Camoufox"
	@echo "  format-{html,css}[-check]  Format browser fixtures/assets or check them"

setup: browser-fetch

browser-fetch: install
	uv run python -m justpen_browser_mcp.browser_runtime

test-e2e:
	uv run --group dev --group docs pytest tests/e2e/ -v -m e2e

test-consumer:
	uv run --group dev python scripts/consumer_check.py --browser

format: format-html format-css
format-check: format-html-check format-css-check

format-html format-css:
	uv run --group dev python scripts/format_files.py $(patsubst format-%,%,$@)

format-html-check format-css-check:
	uv run --group dev python scripts/format_files.py $(patsubst %-check,%,$(patsubst format-%,%,$@)) --check
