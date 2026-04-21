.PHONY: help version setup clean test test-e2e lint lint-fix format format-check typecheck audit check \
        docs-build docs-serve bump-patch bump-minor bump-major \
        pre-commit lock-check

VERSION := $(shell grep '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
VENV := .venv

help:
	@echo "justpen-browser-mcp Makefile targets:"
	@echo "  setup           uv sync dev+docs, fetch Camoufox binary, install git hooks"
	@echo "  clean           Remove venv, caches"
	@echo "  test            Run non-e2e tests"
	@echo "  test-e2e        Run e2e tests (requires Camoufox)"
	@echo "  lint            Run ruff check"
	@echo "  lint-fix        Run ruff check --fix (auto-fix safe violations)"
	@echo "  format          Run ruff format (writes changes)"
	@echo "  format-check    Run ruff format --check"
	@echo "  typecheck       Run pyright over src/ and tests/"
	@echo "  audit           Run pip-audit vulnerability scan"
	@echo "  lock-check      Verify uv.lock is in sync with pyproject.toml"
	@echo "  check           format-check + lint + typecheck + test"
	@echo "  pre-commit      Run all pre-commit hooks against every file"
	@echo "  docs-build      Build the MkDocs site (strict mode)"
	@echo "  docs-serve      Serve the MkDocs site locally with live reload"
	@echo "  bump-patch      Bump patch version, commit, tag locally"
	@echo "  bump-minor      Bump minor version, commit, tag locally"
	@echo "  bump-major      Bump major version, commit, tag locally"
	@echo "  version         Print current version"

version:
	@echo $(VERSION)

setup:
	uv sync --locked --group dev --group docs
	uv run python -m camoufox fetch
	uv run --group dev pre-commit install --install-hooks

pre-commit:
	uv run --group dev pre-commit run --all-files

clean:
	rm -rf $(VENV)
	rm -rf dist/ site/ htmlcov/
	rm -rf .pytest_cache .ruff_cache
	rm -f .coverage .coverage.* coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

test:
	uv run --group dev pytest tests/ -v -m "not e2e" \
	    --cov=justpen_browser_mcp --cov-report=term-missing

test-e2e:
	uv run --group dev pytest tests/ -v -m e2e

lint:
	uv run --group dev ruff check src/ tests/ scripts/

lint-fix:
	uv run --group dev ruff check --fix src/ tests/ scripts/

format:
	uv run --group dev ruff format src/ tests/ scripts/

format-check:
	uv run --group dev ruff format --check src/ tests/ scripts/

typecheck:
	uv run --group dev pyright src/ tests/ scripts/

audit:
	uv tool run pip-audit --strict .

lock-check:
	uv lock --check

check: format-check lint typecheck test

docs-build:
	uv run --group docs mkdocs build --strict

docs-serve:
	uv run --group docs mkdocs serve

bump-patch bump-minor bump-major:
	@segment=$$(echo $@ | sed 's/^bump-//'); \
	uv version --bump $$segment; \
	new=$$(uv version --short); \
	git add pyproject.toml uv.lock; \
	git commit -m "chore: bump version to v$$new"; \
	git tag "v$$new"; \
	branch=$$(git rev-parse --abbrev-ref HEAD); \
	printf "\nLocal tag v%s created. Next steps:\n" "$$new"; \
	printf "  git push -u origin %s\n" "$$branch"; \
	printf "  # open PR, merge with a regular merge commit, then:\n"; \
	printf "  git switch main && git pull && git push origin v%s\n" "$$new"
