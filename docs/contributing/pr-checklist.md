# Pre-PR checklist { #_top }

Complete this checklist before opening a pull request.

## 1. Branch and commits { #1-branch-and-commits }

- Use `codex/short-description` for Codex branches, otherwise
    `type/short-description`. Never commit or push directly to `main`.
- Use [Conventional Commits](https://www.conventionalcommits.org/):
    `type(scope): subject`, with optional scope, subject no longer than 72
    characters and no trailing period. Commitizen validates these rules with the
    project schema. The allowed types are `feat`, `fix`, `docs`,
    `chore`, `ci`, `refactor`, `test`, `style`, `build`, `perf`, and `revert`.
- Keep normal Git hooks enabled. Merge with a regular merge commit, never squash.

## 2. Local verification { #2-local-verification }

The pre-push hook must pass `make check` and one strict `make docs-build`. Do not
repeat those gates manually for the same passing push. `make check` covers lock
consistency, Python/Markdown/TOML/YAML/JSON/HTML/CSS formatting, lint, strict typing
and unit tests with 80% branch coverage in the active Python environment.
The strict docs build validates local links, anchors and Python API references.
Do not substitute direct tool invocations or weaker flags.

CI runs shared quality checks once, typing/unit tests across Python 3.11–3.13,
and real integration/browser/consumer scenarios separately. A passing local unit
gate does not replace the CI integration results.

## 3. Tests { #3-tests }

- Cover new behavior with focused tests and include regressions for bug fixes.
- Classify tests by component boundaries: isolated behavior belongs in unit tests;
    real tool, transport, docs and browser interactions belong in integration.
- When developing an integration test or its harness, run the relevant scenario
    with `make test-one TEST=...`; do not repeat the entire local browser matrix.
    See [End-to-end tests](getting-started.md#end-to-end-tests).
- Preserve CI's installed-wheel consumer coverage with locked and minimum direct
    dependencies when runtime APIs, packaging or dependency bounds change.
- When developing permission tests or the native sandbox harness, use the focused
    test and follow the [agent guide](agents.md#verify-and-troubleshoot) for the
    explicit `CODEX_TEST_BINARY` probe. It is not an automatic routine gate.

## 4. Documentation { #4-documentation }

- Update the relevant product guides and tool references for user-facing behavior.
- Preserve existing page URLs and heading anchors when reorganizing content.
- Verify that versioned installation commands use the project's current version.
- Follow [Lint & typing](lint-typing.md) for formatting and the suppression policy.

## 5. Opening the PR { #5-opening-the-pr }

- Give the PR a Conventional Commit title.
- Explain the problem, resulting behavior and validation, with linked issues
    where relevant.
- Confirm that CI is green for the current PR revision before merging.
- For a release, follow the [release process](release-process.md): push the
    branch, merge the PR with a regular merge commit, update main, create the
    reviewed tag with `make release-tag`, then push it.
