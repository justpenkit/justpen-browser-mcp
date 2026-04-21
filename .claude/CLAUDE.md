## Development Rules

### Python Virtual Environment

Managed by **uv**. Deps in `pyproject.toml` (`[project.dependencies]` + `[dependency-groups] dev`). Lockfile `uv.lock` must be committed.

Run Python via `.venv/bin/<cmd>`, `source .venv/bin/activate`, or `uv run <cmd>`. If `.venv` missing → `make setup`. Never use system Python.

Add deps: `uv add <pkg>` (runtime), `uv add --group dev <pkg>` (dev). Never hand-edit lockfile.

---

### Lint & Type Check

Ruff + pyright strict. **Fix the root cause, do not silence warnings.** Try `ruff check --fix` before manual edits. After every edit, run `ruff check` and `pyright` on changed files before moving on — a broken baseline compounds fast.

Suppressions (`# noqa`, `# type: ignore`, `# pyright: ignore[...]`, `# pragma: no cover`) require a strong, documented reason. Never modify `pyproject.toml` lint/type config unilaterally.

Full rules — banned forms, acceptable reasons, suppression format, escalation protocol, verification gate: [`docs/contributing/lint-typing.md`](../docs/contributing/lint-typing.md).

---

### Code Intelligence

Symbol name → LSP. Text pattern (comment, string, config) → Grep. Reading a whole file to learn its shape is almost always wrong — use `documentSymbol`. Before any rename or signature change, run `findReferences` first. Treat `<new-diagnostics>` reminders as blockers, not notes.

Full reflex → LSP substitution table and rationale: [`docs/contributing/code-intelligence.md`](../docs/contributing/code-intelligence.md).

---

### Git Workflow

Every change ships through a feature branch + PR. **Never commit or push directly to `main`** — this applies to trivial changes too (typos, one-line doc fixes, version bumps).

- **Branches:** `type/short-description` (`feat/browser-retry`, `fix/docker-start-race`, `docs/release-process`, `chore/bump-v0.2.0`).
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/) — `type(scope): subject`. Scope optional when change is cross-cutting.
- **Merge:** Regular merge commits, **never squash**. Preserves individual commit SHAs so locally-created tags on the branch stay valid after merge.
- **Pre-PR gate:** Walk [`docs/contributing/pr-checklist.md`](../docs/contributing/pr-checklist.md). `make check` + `make docs-build` minimum.

---

### Release discipline

Version bumps follow the same branch + PR rule. `make bump-{patch,minor,major}` edits `pyproject.toml`, commits, and creates a local tag — it does **not** push.

Flow (full detail: [`docs/contributing/release-process.md`](../docs/contributing/release-process.md)):

1. From clean `main`: `git switch -c chore/bump-v<new>`
2. `make bump-<segment>` — creates bump commit + local tag
3. Push **branch only**: `git push -u origin chore/bump-v<new>`. **Do not push the tag yet.**
4. Open PR, review, merge (regular merge — preserves the bump commit SHA).
5. After merge: `git switch main && git pull && git push origin v<new>`.

The macro prints these next steps after tagging, so the flow is self-reminding.

---

### Superpowers Artifact Locations

Superpowers skills write artifacts under `.superpowers/` at repo root (gitignored, private working area). These paths override the default `docs/superpowers/` locations used by the brainstorming, writing-plans, and related skills:

- Design specs → `.superpowers/docs/specs/YYYY-MM-DD-<topic>-design.md`
- Implementation plans → `.superpowers/docs/plans/YYYY-MM-DD-<topic>-plan.md`

Never write superpowers artifacts into the tracked `docs/` tree — that directory is reserved for the public MkDocs site.
