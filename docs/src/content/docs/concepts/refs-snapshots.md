---
title: Refs & snapshots
description: Session-scoped refs from accessibility snapshots and how they are invalidated.
---

Most interaction tools consume a `ref` string (e.g. `"e12"`) obtained from `browser_snapshot`. Refs are annotated in the snapshot YAML as `[ref=eN]` on each interactive element. They are session-scoped and invalidated by any navigation or page reload — always take a fresh snapshot after navigating.

When `browser_snapshot` is called with `selector=<css-or-aria>`, it returns a scoped aria YAML **without** ref annotations (using `Locator.aria_snapshot`). Use the default `selector=None` mode when you need refs for subsequent interaction tools.

## When tools require a ref

Interaction tools (click, hover, fill, drag) operate on **refs** — opaque
identifiers returned by inspection tools (see
[Inspection tools](../tools-reference/inspection.md)). A ref is valid for the
lifetime of the snapshot it came from; re-snapshot if the page mutates.

## Why aria-refs instead of CSS selectors

- CSS selectors break on DOM churn; aria-refs target accessibility tree nodes.
- LLM clients produce more reliable calls against role + accessible-name than
  against brittle class hashes.

## Recovering from stale refs

If a tool returns `error_type: "stale_ref"`, re-run the relevant inspection
tool and retry with the new ref.
