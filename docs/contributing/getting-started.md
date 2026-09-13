# Getting started { #_top }

Install the shared development tools and the Camoufox browser before changing the server.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) for Python, dependencies and development tools.
- Git and Make on Apple silicon macOS, Linux or 64-bit Windows with WSL.
- Space for the Camoufox browser binary (approximately 150 MB).

uv manages Python 3.11–3.13, with 3.13 as the local default. All formatters and
MkDocs are installed through uv; Node/npm is not a separate prerequisite.
The locked cryptography dependency no longer supports Intel macOS or 32-bit Windows.

## Clone and set up

```bash
git clone https://github.com/justpenkit/justpen-browser-mcp.git
cd justpen-browser-mcp
make setup
```

`make setup` installs the locked development and documentation dependencies into
`.venv`, fetches Camoufox and installs the pre-commit, pre-push and commit-msg
Git hooks. `make install` installs dependencies only. Run setup again after
cloning onto another computer or when hooks need reinstalling.

Setup, `make browser-fetch`, and every server startup resolve, install if needed,
activate, and verify the newest compatible official Camoufox release, including
prereleases. A temporary mirror supplies the fixed official beta.31 CI build while
upstream is older; an equal or newer official release automatically supersedes it.
See [browser selection](../getting-started/run-server.md#latest-build-compatibility).
The application requires
Playwright 1.61.x and retains that startup's exact SDK browser selector for all
instance launches. See [installation](../getting-started/install.md).

Use uv for dependency management and application commands; do not install project
dependencies into system Python. The standalone permission hook uses isolated
system Python independently of the project environment. See the
[agent guide](agents.md) before starting Claude Code or Codex.

## The dev gate

Git hooks run the routine checks automatically:

| Stage      | Checks                                                                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pre-commit | Conflict/whitespace checks; lint and active-Python typing for Python changes; formatting for text changes; lock consistency for metadata changes |
| Commit-msg | Commitizen validates the project commit-message rules                                                                                            |
| Pre-push   | `make check` and one strict `make docs-build`                                                                                                    |

`make check` verifies lock consistency, all supported formatting, lint, strict
typing and unit tests with 80% branch coverage. Typing and tests each use the
active uv Python once, defaulting to 3.13. The strict MkDocs build validates
local file links, heading anchors and Python API references. A passing pre-push
already supplies these gates; no duplicate manual run is required before a PR.

CI runs shared formatting, lint and docs once on Python 3.13. Its unit matrix
checks strict typing and unit coverage once per Python 3.11, 3.12 and 3.13.
It rejects a missing or stale committed lock before installing dependencies.
Real tool, transport, hook, formatter, release and docs scenarios run separately
through `make test-integration` on 3.13, including the browser tests below.

Use `make lint-fix`, `make format` and `make typecheck` for focused checks when
diagnosing failures or seeking earlier feedback.
`make test-one TEST=tests/test_file.py::test_name` runs a relevant test without
the suite-wide coverage threshold; the pre-push unit gate applies that threshold.

### End-to-end tests

`make check` and `make test` select unit tests and exclude `integration` tests.
Every Camoufox-backed `e2e` test is also an integration test. CI runs these on
Python 3.11 and 3.12 through `make test-e2e`; on 3.13 they run once as part of
the full integration suite. A short test using real components still belongs
in integration: classification depends on its boundaries, not elapsed time.

When developing an integration test or its harness, use
`make test-one TEST=tests/e2e/test_e2e_smoke.py::test_harness_navigates`
for a relevant scenario, choosing the test that covers the change. There is no
routine requirement to repeat the full browser matrix locally. `make test-e2e`
remains available for deliberate suite diagnostics.

`make setup` fetches the binary; run `make browser-fetch` if the browser
installation is missing or another Camoufox release has become the shared default.

### Consumer installation checks

`make test-consumer` builds the wheel, installs it in disposable environments
outside the checkout, and checks the console entry point, installed package
identity, all 46 tool schemas and a real browser round trip. One environment uses
locked runtime dependencies; another resolves the lowest allowed direct versions
with compatible transitive packages. It does not upgrade `uv.lock`.

CI runs this on Python 3.11, 3.12 and 3.13. It is a real installation/MCP/browser
integration, not part of the local unit gate. A focused local run is useful while
developing the consumer harness; repeating it before every PR is unnecessary.
The local target needs network access and the fetched Camoufox binary.

### Editor tests

VS Code's default **Run Test Task** invokes `make check`. The Python Test
Explorer's **Run All Tests** selects unit tests with `-m "not integration"`;
it does not run the integration suite or invoke Make. Formatting on save remains
enabled.

## Make a change

1. Create a feature branch: `codex/short-description` for Codex, otherwise
    `type/short-description`. Never commit directly to `main`.
2. Cover behavior changes with a focused regression test, implement the fix and
    use focused Make checks for feedback.
3. Follow the [PR checklist](pr-checklist.md); passing commit/push hooks provide
    the routine local gates.
4. Use Conventional Commits with subjects no longer than 72 characters. Keep
    Git hooks enabled and merge PRs with a regular merge commit.

See [Lint & typing](lint-typing.md) for formatting and suppressions,
[Release process](release-process.md) for version bumps and
[Template updates](../guides/template-updates.md) for framework updates.
