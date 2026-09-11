---
description: Camoufox-based MCP server with multi-instance browser session isolation.
---

# justpen-browser-mcp { #_top }

Stealth-patched Firefox via Camoufox, exposed as MCP browser tools with per-instance session isolation.

[Quick start](getting-started/install.md) · [Tools reference](tools-reference/lifecycle.md)

`justpen-browser-mcp` exposes a stealth-patched Firefox (via [Camoufox](https://github.com/daijro/camoufox)) to MCP-aware clients as a set of browser automation tools. Every named instance runs its own Camoufox process with its own BrowserForge fingerprint — cookies, storage, and cache do not leak between instances — so a single server process can drive parallel logged-in flows for different users or tenants.

## 60-second quickstart { #60-second-quickstart }

Release `v0.4.0` predates Python 3.11/3.12 support and requires Python 3.13.
The current checkout supports Python 3.11–3.13; [clone current main](contributing/getting-started.md#clone-and-set-up)
for unreleased improvements.

Install with [uv](https://docs.astral.sh/uv/):

```bash
uv add "justpen-browser-mcp @ git+https://github.com/justpenkit/justpen-browser-mcp@v0.4.0"
```

Run the server (stdio transport); startup fetches Camoufox if needed:

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

## Where to go next { #where-to-go-next }

- [Install the server](getting-started/install.md) — uv add + first run.
- [Wire up a client](client-setup/claude-code.md) or [configure Codex](client-setup/codex.md) — Claude Code, Codex, Copilot CLI, Gemini CLI.
- [Browse the tools](tools-reference/lifecycle.md) — All browser automation tools, organized by purpose.
- [Understand the model](concepts/instances-isolation.md) — Per-instance fingerprint, cookies, storage isolation.
- [Contribute](contributing/pr-checklist.md) — Pre-PR checklist + lint/typing rules.
