---
title: Instances & isolation
description: "How named browser instances stay isolated: process, fingerprint, cookies, storage."
---

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

| Boundary                        | What it covers                                                                                                    |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| **OS process**                  | Camoufox runs in a separate process; a crash in one instance does not affect others.                              |
| **BrowserForge fingerprint**    | Canvas, WebGL, font list, timezone, language, and dozens of other signals are independently generated per launch. |
| **Cookies & storage**           | Cookies, localStorage, sessionStorage, and cache are isolated from every other instance.                          |
| **Optional proxy**              | The `proxy` parameter scopes a SOCKS5/HTTP proxy to this instance only.                                           |
| **Optional persistent profile** | The `profile_dir` parameter pins a Firefox-style profile directory; omit it for an ephemeral instance.            |

## Naming

Instances are identified by a string name of your choice. Names are
case-sensitive. Tools that operate on an instance accept a `name` parameter;
see the [Lifecycle tools](/tools-reference/lifecycle/) page for creation
and teardown.

## Ephemeral vs. persistent

`profile_dir=None` (the default) creates an **ephemeral** instance. Camoufox
stores all browser state in memory; no profile is written to disk. When the
instance is destroyed, the state is gone entirely.

`profile_dir="/path/to/dir"` creates a **persistent** instance. Cookies,
localStorage, saved passwords, and other profile data survive across
`browser_destroy_instance` / `browser_create_instance` cycles. The directory
persists on disk even after the instance is destroyed.

:::note[Fingerprint re-roll on restart]
BrowserForge generates a fresh fingerprint on every Camoufox launch, even
for persistent instances. This means the fingerprint will differ between
runs of the same `profile_dir`. The stored profile data (cookies, storage)
is still preserved; only the fingerprint signals change.
:::

## Instance cap

`BROWSER_MCP_MAX_INSTANCES` (default `10`) sets the maximum number of
concurrently live instances. Attempting to create an instance beyond the cap
returns an `instance_limit_exceeded` error. Invalid values (non-integer, zero,
or negative) fall back to `10` with a warning logged to stderr.

## Crash detection

Camoufox runs as a separate OS process per instance (see [Isolation
boundaries](#isolation-boundaries)), and that process can disconnect or crash
independently of the server. The manager listens for that disconnect and
flips the instance's internal `status` to `"crashed"` — it does not evict the
instance immediately.

Eviction happens lazily, on the **next tool call that resolves the
instance**: that call frees the crashed instance's resources asynchronously
and returns an `instance_crashed` error (see [envelope error
codes](/concepts/response-envelope/#error_type-values)) instead of operating
on a dead browser. Until that next call happens, [`browser_list_instances`](/tools-reference/lifecycle/#browser_list_instances)
and [`browser_health`](/tools-reference/lifecycle/#browser_health) will show
the instance with `status: "crashed"`.

[`browser_destroy_instance`](/tools-reference/lifecycle/#browser_destroy_instance)
is the exception to lazy eviction: it works on a crashed instance directly,
tearing it down cleanly and returning success, so you don't need to trigger
eviction with another tool first.

If the crashed instance was created with a `profile_dir`, that persistent
profile directory survives on disk — a crash does not delete stored cookies
or other profile data, same as a clean `browser_destroy_instance`.

## Idle reaper

A background task can automatically close instances that have been idle too
long, so long-running servers don't accumulate abandoned browser processes.
"Idle" is measured as time since the last tool operation on that instance —
each serialized tool call refreshes an instance's idle clock.

The reaper is controlled by two settings (see
[Configuration](/getting-started/configuration/)):

| Setting                               | CLI flag            | Default | Description                                                           |
| ------------------------------------- | ------------------- | ------- | --------------------------------------------------------------------- |
| `BROWSER_MCP_IDLE_TTL_SECONDS`        | `--idle-ttl`        | `0`     | Idle threshold in seconds. `0` **disables** the idle reaper entirely. |
| `BROWSER_MCP_REAPER_INTERVAL_SECONDS` | `--reaper-interval` | `30`    | How often (in seconds) the reaper checks for idle/crashed instances.  |

:::note[Disabled by default]
The idle reaper only runs when `BROWSER_MCP_IDLE_TTL_SECONDS` is set above
`0`. With the default of `0`, instances are never closed for being idle —
only explicit `browser_destroy_instance` calls (or a crash) remove them.
:::

When enabled, each reaper pass also closes any lingering `"crashed"`
instances as a backstop — instances usually get evicted the moment a caller
touches them again (see [crash detection](#crash-detection) above), but one
that nobody calls after crashing would otherwise sit in the registry
indefinitely. The crashed-instance backstop always runs when the reaper is
active, independent of the idle TTL value.

Reaping only closes the underlying browser process; a persistent instance's
`profile_dir` is left untouched on disk, exactly like `browser_destroy_instance`.

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

- [`browser_create_instance`](/tools-reference/lifecycle/#browser_create_instance) — launch a new instance.
- [`browser_destroy_instance`](/tools-reference/lifecycle/#browser_destroy_instance) — shut down an instance and release its resources.
- [`browser_list_instances`](/tools-reference/lifecycle/#browser_list_instances) — inspect all currently live instances.
- [`browser_health`](/tools-reference/lifecycle/#browser_health) — check server status without launching a browser.

## Single active page assumption

Within an instance, the MCP surface currently operates on a single active page.
Opening a second tab is supported, but most tools target the active page; see
[Page tools](/tools-reference/page/) for switching.
