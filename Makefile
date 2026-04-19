.PHONY: help version setup clean test test-e2e lint format format-check typecheck audit check

VERSION := $(shell grep '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
VENV := .venv

help:
	@echo "justpen-browser-mcp Makefile targets:"
	@echo "  setup           Install deps + fetch Camoufox binary"
	@echo "  clean           Remove venv, caches"
	@echo "  test            Run non-e2e tests"
	@echo "  test-e2e        Run e2e tests (requires Camoufox)"
	@echo "  lint            Run ruff check"
	@echo "  format          Run ruff format (writes changes)"
	@echo "  format-check    Run ruff format --check"
	@echo "  typecheck       Run pyright over src/ and tests/"
	@echo "  audit           Run pip-audit vulnerability scan"
	@echo "  check           format-check + lint + typecheck + test"
	@echo "  version         Print current version"

version:
	@echo $(VERSION)

setup:
	uv sync --locked --group dev
	uv run python -m camoufox fetch

clean:
	rm -rf $(VENV)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
	@echo "Cleaned."

test:
	uv run --group dev pytest tests/ -v -m "not e2e" \
	    --cov=justpen_browser_mcp --cov-report=term-missing

test-e2e:
	uv run --group dev pytest tests/ -v -m e2e

lint:
	uv run --group dev ruff check src/ tests/

format:
	uv run --group dev ruff format src/ tests/

format-check:
	uv run --group dev ruff format --check src/ tests/

typecheck:
	uv run --group dev pyright src/ tests/

audit:
	uv tool run pip-audit --strict .

check: format-check lint typecheck test
