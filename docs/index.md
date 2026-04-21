# justpen-browser-mcp

Camoufox-based MCP server with multi-context browser session isolation.

`justpen-browser-mcp` exposes a stealth-patched Firefox (via
[Camoufox](https://github.com/daijro/camoufox)) to MCP-aware clients as a set
of browser automation tools. Every named context is a fully isolated
`BrowserContext` — cookies, storage, and cache do not leak between contexts —
so a single server process can drive parallel logged-in flows for different
users or tenants.

## 60-second quickstart

Install (requires [uv](https://docs.astral.sh/uv/)):

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.1.0"
uv run python -m camoufox fetch
```

Run the server (stdio transport):

```bash
justpen-browser-mcp
```

Register with an MCP client (generic form):

```json
{
  "mcpServers": {
    "justpen-browser": { "command": "justpen-browser-mcp" }
  }
}
```

## Where to go next

- **Install the server** — [Getting started → Install](getting-started/install.md)
- **Wire up a client** — [Client setup](client-setup/claude-code.md) (Claude Code, Copilot CLI, Gemini CLI)
- **Browse the tools** — [Tools reference](tools-reference/lifecycle.md)
- **Understand the model** — [Concepts → Contexts & isolation](concepts/contexts-isolation.md)
- **Contribute** — [Contributing → PR checklist](contributing/pr-checklist.md)
