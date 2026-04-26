---
title: Getting started
description: Clone the repo, install the toolchain, run the dev gate.
---

If you're contributing to this project for the first time, here's the minimum to get up and running.

## Prerequisites

- **uv** — Python package + project manager. Install: <https://docs.astral.sh/uv/>
- **Node.js 24+** — for the prettier and Astro Starlight toolchain. Install: <https://nodejs.org/>

## Clone and set up

```bash
git clone https://github.com/justpenkit/justpen-browser-mcp.git
cd justpen-browser-mcp
make setup
```

`make setup` does:

- `uv sync --locked --group dev` — installs Python deps into `.venv/`.
- `uv run python -m camoufox fetch` — downloads the Camoufox browser binary.
- `pre-commit install` — wires the pre-commit, pre-push, and commit-msg git hooks.
- `npm install` — installs prettier (with `prettier-plugin-toml`) and Astro Starlight.
- `astro --root docs sync` — generates Astro content types so editors resolve `astro:content` and `@astrojs/starlight/*` imports.

## The dev gate

Run before any PR:

```bash
make check       # ruff format-check + prettier --check + ruff check + pyright + pytest
make docs-build  # astro static build (CI also runs lychee for broken-link detection)
```

`make check` is also enforced on `git push` via the pre-push hook, so a broken push is impossible.

## Make a change

1. Open a feature branch: `git switch -c type/short-description` (e.g. `feat/foo-bar`).
2. Implement the change with TDD: failing test → minimal fix → verify → commit.
3. Walk the [Pre-PR checklist](/contributing/pr-checklist/) before opening the PR.
4. Use Conventional Commits for every commit subject (`type(scope): subject`, ≤72 chars).

For lint and type-check rules — including the suppression protocol — see [Lint & typing](/contributing/lint-typing/).
