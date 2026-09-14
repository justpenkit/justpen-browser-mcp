# Template updates

For maintainers updating the shared CI, hooks and development tools from
`justpen-mcp-dev-template`. MCP users do not need this procedure.

Start from a clean, committed full clone:

```bash
git switch -c codex/update-template
git fetch --no-tags https://github.com/justpenkit/justpen-mcp-dev-template.git main:refs/remotes/template/main
template_commit=$(git rev-parse refs/remotes/template/main)
uvx --from 'copier>=9.18.2,<10' copier update --vcs-ref="$template_commit" --defaults
git diff
```

Keep `.copier-answers.yml` and let Copier maintain it. Review the diff and resolve
conflicts while preserving browser code, tests, application version and release
history. Do not merge template branches/tags or use `copier recopy`.

Use uv for dependency changes and `make setup` to refresh tooling and hooks.
Commit/push hooks and CI provide validation; ship the update through a PR.
The server version is independent of the template; read it with `make version`.
Follow the [agent guide](agents.md) for protected metadata changes and the
[PR checklist](pr-checklist.md) before merging.
