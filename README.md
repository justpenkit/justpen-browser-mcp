# justpen-browser-mcp

Camoufox-based MCP server with multi-instance browser isolation.

Exposes a stealth-patched Firefox (via [Camoufox](https://github.com/daijro/camoufox))
to MCP-aware clients as a set of browser automation tools. Each named instance
runs in its own Camoufox process with its own BrowserForge fingerprint and
(optionally) its own persistent profile on disk, so a single server can drive
fully isolated parallel sessions for different users, tenants, or pentest
identities.

## Install

Install with [uv](https://docs.astral.sh/uv/). Release `v0.4.0` predates Python
3.11/3.12 support and requires Python 3.13. The current checkout supports Python
3.11–3.13; [clone current main](docs/contributing/getting-started.md#clone-and-set-up)
for unreleased improvements.

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.4.0"
```

Run the server (stdio transport); startup fetches Camoufox if needed:

```bash
justpen-browser-mcp
```

## Documentation

Read the [documentation](docs/index.md) in this repository, or run `make docs-serve`
after `make setup` to browse the MkDocs site locally. `make docs-build` creates
the static site in `site/` for deployment to a host of your choice.

- [Install](docs/getting-started/install.md) · [Run the server](docs/getting-started/run-server.md) · [Configuration](docs/getting-started/configuration.md)
- Client setup: [Codex](docs/client-setup/codex.md) · [Claude Code](docs/client-setup/claude-code.md) · [Copilot CLI](docs/client-setup/copilot-cli.md) · [Gemini CLI](docs/client-setup/gemini-cli.md)
- Concepts: [Response envelope](docs/concepts/response-envelope.md) · [Instances & isolation](docs/concepts/instances-isolation.md) · [Refs & snapshots](docs/concepts/refs-snapshots.md) · [Modal state](docs/concepts/modal-state.md)
- [Tools reference](docs/tools-reference/lifecycle.md) — lifecycle, navigation, interaction, mouse, inspection, verification, code execution, cookies, utility, page

## Contributing

See the [contributing guides](docs/contributing/pr-checklist.md) for the PR checklist, lint/typing rules, code-intelligence conventions, and release process.

## License

MIT — see `LICENSE`.
