# Contributing

Run `make setup` once to install the locked development and docs dependencies,
fetch Camoufox and install Git hooks. Before a PR, run `make check` and
`make docs-build`; browser behavior changes also need `make test-e2e`.

Contributor documentation lives under [`docs/contributing/`](docs/contributing/):

- [Getting started](docs/contributing/getting-started.md)
- [Claude Code and Codex](docs/contributing/agents.md)
- [PR checklist](docs/contributing/pr-checklist.md)
- [Lint & typing rules](docs/contributing/lint-typing.md)
- [Release process](docs/contributing/release-process.md)
- [Template updates](docs/guides/template-updates.md)

Follow [`AGENTS.md`](AGENTS.md) for shared development rules. Use a feature
branch and PR, keep Git hooks enabled, and merge with a regular merge commit.
