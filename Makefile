.DEFAULT_GOAL := help
PYTHON_PATHS := src/ tests/ scripts/
COVERAGE_SOURCE := justpen_browser_mcp

include scripts/development.mk

.PHONY: browser-fetch zstd-headers test-e2e test-consumer test-consumer-smoke schema-update

# Camoufox's indexed-zstd dependency has no linux aarch64 wheel, so it builds from
# source there and needs the zstd C headers.
ZSTD_PLATFORM ?= $(shell uname -s)-$(shell uname -m)

help::
	@echo "  schema-update          Regenerate MCP input schemas for review (no browser)"
	@echo "  zstd-headers           Install the zstd headers indexed-zstd needs on linux aarch64"
	@echo "  browser-fetch          Install the Camoufox browser binary"
	@echo "  test-e2e               Run the real Camoufox browser suite"
	@echo "  test-consumer          Test isolated locked/minimum wheel installs with Camoufox"
	@echo "  test-consumer-smoke    Test isolated wheel contracts without launching Camoufox"

setup: browser-fetch

install: zstd-headers

zstd-headers:
	@if [ "$(ZSTD_PLATFORM)" = "Linux-aarch64" ] && ! printf '#include <zstd.h>\n' | cc -E -x c - >/dev/null 2>&1; then \
	    if command -v apt-get >/dev/null 2>&1; then \
	        echo "Installing libzstd-dev: indexed-zstd builds from source on linux aarch64."; \
	        sudo apt-get install -y libzstd-dev; \
	    else \
	        echo "Install the zstd development headers (zstd.h): indexed-zstd builds from source on linux aarch64." >&2; \
	        exit 1; \
	    fi; \
	fi

browser-fetch: install
	uv run python -m justpen_browser_mcp.browser_runtime

test-e2e:
	uv run --group dev --group docs pytest tests/e2e/ -v -m e2e

test-consumer:
	uv run --group dev python scripts/consumer_check.py --browser

test-consumer-smoke:
	uv run --group dev python scripts/consumer_check.py

schema-update:
	uv run python scripts/update_tool_schemas.py
