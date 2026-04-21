# Contexts & isolation

`justpen-browser-mcp` runs a single Camoufox browser process but exposes any
number of named **contexts**. Each context is a Playwright `BrowserContext` —
its own cookies, storage, cache, and origin isolation.

## Why contexts matter

A single server process can drive:

- **Parallel logged-in sessions** — one context per user / tenant, no cookie
  bleed.
- **Clean-slate flows** — destroy a context after a test to reset state.
- **Experiment isolation** — try two login flows side by side without one
  polluting the other.

## Naming

Contexts are identified by a string name of your choice. Names are
case-sensitive. Tools that operate on a context accept a `context` parameter;
see the [Lifecycle tools](../tools-reference/lifecycle.md) page for
creation / teardown.

## Lifetime

A context exists from the first lifecycle call that creates it until it is
explicitly closed or the server process exits. There is no automatic TTL.

## Single active page assumption

Within a context, the MCP surface currently operates on a single active page.
Opening a second tab is supported, but most tools target the active page; see
[Page tools](../tools-reference/page.md) for switching.
