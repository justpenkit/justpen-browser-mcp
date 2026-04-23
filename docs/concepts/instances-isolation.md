# Instances & isolation

`justpen-browser-mcp` manages any number of named **instances**. Each instance
is its own Camoufox process — a separate stealth-patched Firefox — with its own
BrowserForge fingerprint and completely isolated browser state.

## Why instances matter

A single server process can drive:

- **Parallel logged-in sessions** — one instance per user / tenant, no cookie
  bleed.
- **Clean-slate flows** — destroy an instance after a test to reset all state,
  including the on-disk profile if one was used.
- **Fingerprint diversity** — each instance rolls a fresh BrowserForge
  fingerprint at launch, making parallel sessions look like different real
  browsers to fingerprinting detectors.
- **Per-instance proxies** — route different instances through different
  outbound proxies without shared state.

## Isolation boundaries

Each instance has its own:

| Boundary | What it covers |
|---|---|
| **OS process** | Camoufox runs in a separate process; a crash in one instance does not affect others. |
| **BrowserForge fingerprint** | Canvas, WebGL, font list, timezone, language, and dozens of other signals are independently generated per launch. |
| **Cookies & storage** | Cookies, localStorage, sessionStorage, and cache are isolated from every other instance. |
| **Optional proxy** | The `proxy` parameter scopes a SOCKS5/HTTP proxy to this instance only. |
| **Optional persistent profile** | The `profile_dir` parameter pins a Chromium-style profile directory; omit it for an ephemeral instance. |

## Naming

Instances are identified by a string name of your choice. Names are
case-sensitive. Tools that operate on an instance accept a `name` parameter;
see the [Lifecycle tools](../tools-reference/lifecycle.md) page for creation
and teardown.

## Ephemeral vs. persistent

`profile_dir=None` (the default) creates an **ephemeral** instance. Camoufox
stores all browser state in memory; no profile is written to disk. When the
instance is destroyed, the state is gone entirely.

`profile_dir="/path/to/dir"` creates a **persistent** instance. Cookies,
localStorage, saved passwords, and other profile data survive across
`browser_destroy_instance` / `browser_create_instance` cycles. The directory
persists on disk even after the instance is destroyed.

!!! note "Fingerprint re-roll on restart"
    BrowserForge generates a fresh fingerprint on every Camoufox launch, even
    for persistent instances. This means the fingerprint will differ between
    runs of the same `profile_dir`. The stored profile data (cookies, storage)
    is still preserved; only the fingerprint signals change.

## Instance cap

`BROWSER_MCP_MAX_INSTANCES` (default `10`) sets the maximum number of
concurrently live instances. Attempting to create an instance beyond the cap
returns an `instance_limit_exceeded` error. Invalid values (non-integer, zero,
or negative) fall back to `10` with a warning logged to stderr.

## Why this is stronger than a shared process model

The old per-context model shared a single Camoufox process among all contexts.
Process-level isolation means:

- **No shared memory** — one misbehaving page cannot leak V8 heap, native
  libraries, or timing oracles into another instance.
- **Fingerprint diversity** — a shared process means all contexts expose
  identical fingerprint signals; separate processes roll separate fingerprints.
- **Fault containment** — a renderer crash is confined to the affected instance.

## Lifecycle tools

Use these tools to manage instance lifetimes:

- [`browser_create_instance`](../tools-reference/lifecycle.md#browser_create_instance) — launch a new instance.
- [`browser_destroy_instance`](../tools-reference/lifecycle.md#browser_destroy_instance) — shut down an instance and release its resources.
- [`browser_list_instances`](../tools-reference/lifecycle.md#browser_list_instances) — inspect all currently live instances.

## Single active page assumption

Within an instance, the MCP surface currently operates on a single active page.
Opening a second tab is supported, but most tools target the active page; see
[Page tools](../tools-reference/page.md) for switching.
