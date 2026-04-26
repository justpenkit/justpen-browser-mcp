.PHONY: help version setup clean test test-e2e lint lint-fix format format-check format-ruff format-ruff-check format-prettier format-prettier-check typecheck audit check \
        docs-build docs-serve bump-patch bump-minor bump-major \
        pre-commit lock-check

VERSION := $(shell grep '^version' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
VENV := .venv
PRETTIER := ./node_modules/.bin/prettier
NPX := npx

help:
	@echo "justpen-browser-mcp Makefile targets:"
	@echo "  setup                  uv sync dev, fetch Camoufox binary, npm install, install git hooks, astro sync"
	@echo "  clean                  Remove venv, node_modules, caches"
	@echo "  test                   Run non-e2e tests"
	@echo "  test-e2e               Run e2e tests (requires Camoufox)"
	@echo "  lint                   Run ruff check"
	@echo "  lint-fix               Run ruff check --fix (auto-fix safe violations)"
	@echo "  format                 Run format-ruff + format-prettier (writes changes)"
	@echo "  format-check           Run format-ruff-check + format-prettier-check"
	@echo "  format-ruff            Run ruff format --write on src/ tests/ scripts/"
	@echo "  format-ruff-check      Run ruff format --check on src/ tests/ scripts/"
	@echo "  format-prettier        Run prettier --write (auto-discovers via .prettierignore)"
	@echo "  format-prettier-check  Run prettier --check (auto-discovers via .prettierignore)"
	@echo "  typecheck              Run pyright over src/, tests/ and scripts/"
	@echo "  audit                  Run pip-audit vulnerability scan"
	@echo "  lock-check             Verify uv.lock is in sync with pyproject.toml"
	@echo "  check                  format-check + lint + typecheck + test"
	@echo "  pre-commit             Run all pre-commit hooks"
	@echo "  docs-build             Build the docs site (Astro Starlight static build)"
	@echo "  docs-serve             Serve the docs site locally with live reload"
	@echo "  bump-patch             Bump patch version, commit, tag locally"
	@echo "  bump-minor             Bump minor version, commit, tag locally"
	@echo "  bump-major             Bump major version, commit, tag locally"
	@echo "  version                Print current version"

version:
	@echo $(VERSION)

setup:
	@command -v npm >/dev/null 2>&1 || { \
	    echo "ERROR: npm not found in PATH. Install Node.js 24+ from https://nodejs.org and re-run 'make setup'."; \
	    exit 1; \
	}
	uv sync --locked --group dev
	uv run python -m camoufox fetch
	uv run --group dev pre-commit install --install-hooks
	npm install --no-audit --no-fund
	$(NPX) astro --root docs sync

pre-commit:
	uv run --group dev pre-commit run --all-files

clean:
	rm -rf $(VENV)
	rm -rf dist/ htmlcov/ node_modules/ docs/dist/ docs/.astro/
	rm -rf .pytest_cache .ruff_cache
	rm -f .coverage .coverage.* coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned."

# Auto-bootstrap node_modules so format-prettier* targets work even if `make setup`
# wasn't run yet (used by CI). Tracks package-lock.json so a changed lockfile
# re-syncs on the next invocation.
node_modules: package.json package-lock.json
	@command -v npm >/dev/null 2>&1 || { \
	    echo "ERROR: npm not found in PATH. Install Node.js 24+ from https://nodejs.org."; \
	    exit 1; \
	}
	npm install --no-audit --no-fund
	@touch node_modules

test:
	uv run --group dev pytest tests/ -v -m "not e2e" \
	    --cov=justpen_browser_mcp --cov-report=term-missing

test-e2e:
	uv run --group dev pytest tests/ -v -m e2e

lint:
	uv run --group dev ruff check src/ tests/ scripts/

lint-fix:
	uv run --group dev ruff check --fix src/ tests/ scripts/

format: format-ruff format-prettier

format-check: format-ruff-check format-prettier-check

format-ruff:
	uv run --group dev ruff format src/ tests/ scripts/

format-ruff-check:
	uv run --group dev ruff format --check src/ tests/ scripts/

format-prettier: node_modules
	$(PRETTIER) --write .

format-prettier-check: node_modules
	$(PRETTIER) --check .

typecheck:
	uv run --group dev pyright src/ tests/ scripts/

audit:
	uv tool run pip-audit --strict .

lock-check:
	uv lock --check

check: format-check lint typecheck test

docs-build: node_modules
	$(NPX) astro --root docs build

docs-serve: node_modules
	$(NPX) astro --root docs dev

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
