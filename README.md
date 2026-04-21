# justpen-browser-mcp

Camoufox-based MCP server with multi-context browser session isolation.

Exposes a stealth-patched Firefox (via [Camoufox](https://github.com/daijro/camoufox))
to MCP-aware clients as a set of browser automation tools. Each named context
is a fully isolated `BrowserContext` — cookies, storage, and cache do not leak
between contexts — so a single server process can drive parallel logged-in
flows for different users or tenants.

## Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.1.0"
uv run python -m camoufox fetch   # one-time ~150MB Camoufox binary download
```

Run the server (stdio transport):

```bash
justpen-browser-mcp
```

## Documentation

Full docs are on the MkDocs site: **<https://justpenkit.github.io/justpen-browser-mcp/>**

- [Install](https://justpenkit.github.io/justpen-browser-mcp/getting-started/install/) · [Run the server](https://justpenkit.github.io/justpen-browser-mcp/getting-started/run-server/) · [Configuration](https://justpenkit.github.io/justpen-browser-mcp/getting-started/configuration/)
- Client setup: [Claude Code](https://justpenkit.github.io/justpen-browser-mcp/client-setup/claude-code/) · [Copilot CLI](https://justpenkit.github.io/justpen-browser-mcp/client-setup/copilot-cli/) · [Gemini CLI](https://justpenkit.github.io/justpen-browser-mcp/client-setup/gemini-cli/)
- Concepts: [Response envelope](https://justpenkit.github.io/justpen-browser-mcp/concepts/response-envelope/) · [Contexts & isolation](https://justpenkit.github.io/justpen-browser-mcp/concepts/contexts-isolation/) · [Refs & snapshots](https://justpenkit.github.io/justpen-browser-mcp/concepts/refs-snapshots/) · [Modal state](https://justpenkit.github.io/justpen-browser-mcp/concepts/modal-state/)
- [Tools reference](https://justpenkit.github.io/justpen-browser-mcp/tools-reference/lifecycle/) — lifecycle, navigation, interaction, mouse, inspection, verification, code execution, cookies, utility, page, server

## Contributing

See the [contributing guides](https://justpenkit.github.io/justpen-browser-mcp/contributing/pr-checklist/) on the site for the PR checklist, lint/typing rules, code-intelligence conventions, and release process.

## License

MIT — see `LICENSE`.
