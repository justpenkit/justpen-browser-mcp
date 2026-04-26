# Lint & Type Check

We use **ruff** (broad ruleset) and **pyright** in `typeCheckingMode = "strict"` for Python; **prettier** (with `prettier-plugin-toml`) for `*.md` / `*.yml` / `*.yaml` / `*.json` / `*.toml`.

**Fix the root cause, do not silence warnings.** Try `ruff check --fix` before editing by hand.

## Suppressions

Suppressions (`# noqa`, `# type: ignore`, `# pyright: ignore[...]`, `# pragma: no cover`) are a last resort. If one is genuinely necessary:

- Always use the **specific rule code** (e.g. `# noqa: E501`, `# pyright: ignore[reportUnknownMemberType]`) — never the blanket form.
- Add an inline comment explaining **why**, on the same line or the line directly above.
- Prefer refactoring the code over suppressing.

Never modify the lint/type config in `pyproject.toml` to make a warning disappear without raising the issue first.

## Git hooks

`make setup` installs three `pre-commit` git hook stages:

- `pre-commit` — `make lint-fix`, `make format` (ruff + prettier), `make lock-check` (latter only when `pyproject.toml` or `uv.lock` changes).
- `pre-push` — `make check` (`format-check` + `lint` + `typecheck` + `test`; mirrors CI).
- `commit-msg` — Conventional Commits format.

Never bypass a failing hook with `--no-verify`. Hooks are ergonomic; CI runs `make check` as the source of truth.
