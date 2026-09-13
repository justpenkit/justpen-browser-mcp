.DEFAULT_GOAL := help
PYTHON_PATHS := src/ tests/ scripts/
COVERAGE_SOURCE := justpen_browser_mcp

include scripts/development.mk

.PHONY: browser-fetch test-e2e test-consumer schema-update

help::
	@echo "  schema-update          Regenerate MCP input schemas for review (no browser)"
	@echo "  browser-fetch          Install the Camoufox browser binary"
	@echo "  test-e2e               Run the real Camoufox browser suite"
	@echo "  test-consumer          Test isolated locked/minimum wheel installs with Camoufox"

setup: browser-fetch

browser-fetch: install
	uv run python -m justpen_browser_mcp.browser_runtime

test-e2e:
	uv run --group dev --group docs pytest tests/e2e/ -v -m e2e

test-consumer:
	uv run --group dev python scripts/consumer_check.py --browser

schema-update:
	uv run python scripts/update_tool_schemas.py
