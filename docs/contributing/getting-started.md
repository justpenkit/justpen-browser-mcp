# Getting started { #_top }

Install the shared development tools and the Camoufox browser before changing the server.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python, dependencies and development tools.
- Git and Make on Apple silicon macOS, Linux or 64-bit Windows with WSL.
- Space for the Camoufox browser binary (approximately 150 MB).

uv manages Python 3.11–3.13, with 3.13 as the local default. All formatters and
MkDocs are installed through uv; Node/npm is not a separate prerequisite.
The locked cryptography dependency no longer supports Intel macOS or 32-bit Windows.

These requirements apply to the current checkout. Release `v0.4.0` predates
Python 3.11/3.12 support and requires Python 3.13. Clone current main for
unreleased improvements.

## Clone and set up

```bash
git clone https://github.com/justpenkit/justpen-browser-mcp.git
cd justpen-browser-mcp
make setup
```

`make setup` installs the locked development and documentation dependencies into
`.venv`, fetches Camoufox and installs the pre-commit, pre-push and commit-msg
Git hooks. `make install` installs dependencies only. Run setup again after
cloning onto another computer or when hooks need reinstalling.

The current checkout selects Camoufox `135.0.1-beta.24` for compatibility with
Playwright `<1.60`. Setup, `make browser-fetch` and server startup all use this
selection, updating the SDK's shared default browser for subsequent Camoufox
launches.

Use uv for dependency management and application commands; do not install project
dependencies into system Python. The standalone permission hook uses isolated
system Python independently of the project environment. See the
[agent guide](agents.md) before starting Claude Code or Codex.

## The dev gate

Run before every PR:

```bash
make check
make docs-build
```

`make check` verifies lock consistency, all supported formatting, lint, strict
Python 3.11/3.12/3.13 typing and the fast tests once in the active interpreter.
`make docs-build` runs the strict MkDocs build, including local file and anchor
validation. CI builds documentation on Python 3.13. The pre-push hook runs both
gates for early feedback; CI verifies the PR independently.

Use `make lint-fix`, `make format` and `make typecheck` for individual checks.
`make test-one TEST=tests/test_file.py::test_name` provides focused feedback; it
does not replace the full `make check` coverage gate.

### End-to-end tests

`make check` and `make test` exclude the Camoufox-backed tests marked `e2e`.
CI's fast test jobs do not run them. To exercise a real fetched browser:

```bash
make test-e2e
```

Run this separate gate locally when changing navigation, interaction, modal
handling, page code execution, instance isolation or other browser behavior.
`make setup` fetches the binary; run `make browser-fetch` if the browser
installation is missing or another Camoufox release has become the shared default.

## Make a change

1. Create a feature branch: `codex/short-description` for Codex, otherwise
    `type/short-description`. Never commit directly to `main`.
2. Cover behavior changes with a focused regression test, implement the fix and
    run the relevant Make checks.
3. Follow the [PR checklist](pr-checklist.md), including the full local gates.
4. Use Conventional Commits with subjects no longer than 72 characters. Keep
    Git hooks enabled and merge PRs with a regular merge commit.

See [Lint & typing](lint-typing.md) for formatting and suppressions,
[Release process](release-process.md) for version bumps and
[Template updates](../guides/template-updates.md) for framework updates.
