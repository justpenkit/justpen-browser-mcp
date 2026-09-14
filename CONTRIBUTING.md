# Contributing

Run `make setup` once to install the locked development and docs dependencies,
fetch Camoufox and install Git hooks. Commit hooks format, lint and check types;
the pre-push hook runs `make check` and one strict `make docs-build`. Do not repeat
passing gates manually. CI runs the supported Python matrix, real integration and
browser scenarios, and installed-wheel consumer checks.

Contributor documentation lives under [`docs/contributing/`](docs/contributing/):

- [Getting started](docs/contributing/getting-started.md)
- [Claude Code and Codex](docs/contributing/agents.md)
- [PR checklist](docs/contributing/pr-checklist.md)
- [Lint & typing rules](docs/contributing/lint-typing.md)
- [Release process](docs/contributing/release-process.md)
- [Template updates](docs/contributing/template-updates.md)

Follow [`AGENTS.md`](AGENTS.md) for shared development rules. Use a feature
branch and PR, keep Git hooks enabled, and merge with a regular merge commit.
