<img src="docs/assets/logo.svg" alt="justpen-browser-mcp logo" width="144" height="144">

# justpen-browser-mcp

Camoufox-based MCP server with multi-instance browser isolation.

Exposes a stealth-patched Firefox (via [Camoufox](https://github.com/daijro/camoufox))
to MCP-aware clients as a set of browser automation tools. Each named instance
runs in its own Camoufox process with its own BrowserForge fingerprint and
(optionally) its own persistent profile on disk, so a single server can drive
separate parallel browser sessions for different users, tenants, or pentest
identities.

The runtime provides stable instance/page/frame identities, cooperative operation deadlines,
46 tools, optional action observations, original screenshot files, retained downloads,
bounded console/network evidence with cursor pagination, and explicit recovery
metadata on tool results. See the [framework integration guide](docs/guides/framework-integration.md)
for lifecycle ownership, artifact collection and process supervision.

## Install

Requires Python 3.11–3.13. Install with [uv](https://docs.astral.sh/uv/)
inside your Python project. See the [installation guide](docs/getting-started/install.md)
for platform requirements, or [clone the repository](docs/contributing/getting-started.md#clone-and-set-up)
to contribute.

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.6.1"
```

Run the server (stdio transport); every startup checks and activates the latest official Camoufox release before serving, downloading it when needed:

```bash
uv run justpen-browser-mcp
```

## Documentation

Read the [online documentation](https://justpen-browser-mcp.justpenkit.justmumu.com/)
or its [source in this repository](docs/index.md).

- [Install](docs/getting-started/install.md) · [Run the server](docs/getting-started/run-server.md) · [Configuration](docs/getting-started/configuration.md)
- Client setup: [Codex](docs/client-setup/codex.md) · [Claude Code](docs/client-setup/claude-code.md) · [Copilot CLI](docs/client-setup/copilot-cli.md) · [Gemini CLI](docs/client-setup/gemini-cli.md)
- Concepts: [Response envelope](docs/concepts/response-envelope.md) · [Instances & isolation](docs/concepts/instances-isolation.md) · [Refs & snapshots](docs/concepts/refs-snapshots.md) · [Modal state](docs/concepts/modal-state.md)
- [Tools reference](docs/tools-reference/lifecycle.md) — lifecycle, navigation, interaction, mouse, inspection, verification, code execution, cookies, utility, page

## Contributing

Run `make setup` once to install development tools, Camoufox and Git hooks.
The hooks run routine checks when you commit and push; CI runs the Python matrix
and real integration/browser/consumer scenarios. No duplicate manual gate is needed
after a passing push. See the [contributing guides](docs/contributing/pr-checklist.md)
for focused checks, lint/typing rules, code navigation and the release process.

## License

MIT — see `LICENSE`.
