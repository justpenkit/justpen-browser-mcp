# justpen-browser-mcp

Camoufox-based MCP server with multi-context browser session isolation.

`justpen-browser-mcp` is an MCP (Model Context Protocol) server that exposes a
Camoufox-driven Firefox to LLM clients as a set of tools. Every named context
is a fully isolated browser session — cookies, storage, and cache live inside
the context and do not leak between them — which makes it safe to run parallel
logged-in flows for different users or test tenants from a single server
process.

## What you get

- **Multi-context isolation** — spin up any number of `BrowserContext` objects
  by name; each one behaves like a fresh profile.
- **Stealth-first browser** — Camoufox ships pre-patched Firefox fingerprint
  flags, so the browser looks like a human session out of the box.
- **LLM-native tool surface** — tools return structured JSON, include aria-ref
  snapshots for reliable element targeting, and surface errors with typed
  `error_type` codes.
- **Single stdio transport** — works with any MCP-compatible client
  (Claude Code, Copilot CLI, Gemini CLI, custom stdio bridges).

## Where to go next

- **Running the server** — see the repo README.
- **Contributing** — start with the
  [PR checklist](contributing/pr-checklist.md). If you're cutting a release,
  follow the [release process](contributing/release-process.md). Internal
  tooling rules for linters, type checkers, and LSP use live under
  [lint & typing](contributing/lint-typing.md) and
  [code intelligence](contributing/code-intelligence.md).
- **Source** — [github.com/justpenkit/justpen-browser-mcp](https://github.com/justpenkit/justpen-browser-mcp).
