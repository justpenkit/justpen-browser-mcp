## v0.8.0 (2026-09-14)

### Feat

- wire telemetry into MCP server lifecycle
- correlate browser operations with native MCP spans
- configure bounded OTLP telemetry export
- emit correlated operational events and metrics
- receive W3C context and MCP call metadata
- add telemetry configuration and resource identity

## v0.7.0 (2026-09-14)

### Feat

- **browser**: add pentest targeting and evidence workflows

### Fix

- bridge Camoufox mouse hangs with verified upstream CI builds

## v0.6.1 (2026-09-13)

### Maintenance

- Align development hooks, CI, Commitizen validation, release tooling and common documentation with template v0.4.0.
- Keep routine local verification in Git hooks and browser/integration/installed-package scenarios in CI.

## v0.6.0 (2026-09-12)

### Feat

- add project logo and custom deployment URL
- harden browser lifecycle, recovery and evidence

## v0.5.0 (2026-09-11)

### BREAKING CHANGE

- The secured cryptography dependency drops Intel macOS
    and 32-bit Windows support; current platform requirements are documented.

### Feat

- adopt shared MCP development framework

### Fix

- exclude the implicit request-blocking browser addon
- isolate sandbox probes and storage readiness
- preserve server failures and browser origin boundaries

## v0.4.0 (2026-07-03)

### Feat

- **tools**: add browser_health tool for launch-free status
- **instance**: background idle reaper with injectable-clock reap_once
- **instance**: crash detection, lazy eviction, and touch-on-lock
- **instance**: add status/last_used_at; launch returns browser
- **errors**: add InstanceCrashedError with instance_crashed error_type
- **tools**: expose per-instance camoufox overrides in create tool
- **server**: build config from CLI and select stdio/http transport
- **instance**: layer server camoufox defaults into create()
- **cli**: add argparse CLI with env fallback and CLI-wins precedence
- **config**: expand BrowserServerConfig with camoufox fields

### Fix

- pin playwright\<1.60 and adopt ariaSnapshot RPC for Camoufox compat
- guard reaper vs concurrent evict and robust localStorage nav
- **instance**: free resources on crash-evict and harden destroy/lock
- **config**: warn-and-default on invalid ff_version and empty host

## v0.3.0 (2026-04-26)

### Feat

- **docs**: scaffold astro starlight alongside mkdocs

## v0.2.0 (2026-04-23)

### Feat

- **main**: InstanceManager wiring + SIGTERM/SIGINT shutdown
- **tools/lifecycle**: rewrite as browser\_{create,destroy,list}\_instance
- **instance-manager**: registry, lifecycle, and profile_dir preflight
- **instance**: add InstanceRecord/State + launch_instance helper
- **pyproject**: expose justpen-browser-mcp console script

### Fix

- **tests**: add type params to Client and dict in tools conftest
- **tools/lifecycle**: close TOCTOU race and add limit test
- **instance-manager**: acquire registry_lock in shutdown_all

### Refactor

- **instance-manager**: destroy uses self.get too
- **instance-manager**: make get sync, dedupe lookup-or-raise
- **instance-manager**: use anyio.Path for profile_dir resolve
- remove launcher, context-manager, and server-tools modules
- **tools**: re-export renamed modules from package __init__
- **tools/utility**: rename context → instance
- **tools/page**: rename context → instance
- **tools/cookies**: rename context → instance
- **tools/code_execution**: rename context → instance
- **tools/verification**: rename context → instance
- **tools/inspection**: rename context → instance
- **tools/mouse**: rename context → instance
- **tools/interaction**: rename context → instance
- **tools/navigation**: rename context → instance
- **responses**: rename envelope field context → instance
- **config**: drop headless, add max_instances env + default 10
- **errors**: replace context\_\* with instance\_\* error types

### Perf

- **instance-manager**: resolve profile_dir once, store canonical

## v0.1.0 (2026-04-19)

### Fix

- **types**: enable strict pyright for browser_mcp
- **pyright**: resolve register_all import collision between tests/ and lib/ namespaces
- **browser_mcp**: remove dead comparisons flagged by pyright
- **types**: add explicit type arguments for generic containers
- **types**: tighten test fixtures for pyright
- **types**: tighten browser_mcp pyright diagnostics
- **ruff**: E402 move ContextState dataclass below all imports
- **ruff**: SLF001 replace monkey-patched ctx state with ContextState dataclass
- **ruff**: RUF043 mark pytest.raises match patterns as raw strings
- **ruff**: N802 snake_case localStorage in test name
- **ruff**: A002 rename MCP tool params shadowing builtins
- **ruff**: ARG001 consume unused function arguments
- **ruff**: FBT001/FBT002/FBT003 keyword-only bool arguments
- **ruff**: ASYNC240 offload blocking pathlib calls in async tests
- **ruff**: ASYNC240 offload blocking pathlib calls in async prod code
- **ruff**: S102/S606 document intentional suppression for tool-purpose code
- **ruff**: S108 replace hardcoded /tmp paths with tmp_path fixture
- **ruff**: TRY300 move post-try statements out of try body
- **ruff**: TRY301 return error_response instead of raising inside try
- **ruff**: B904 chain re-raised exceptions with `from e`
- **ruff**: BLE001 narrow blind except clauses
- **ruff**: PLW2901 stop shadowing loop variables
- **ruff**: RUF059 prefix unused unpacked variables with underscore
- **ruff**: ANN202 annotate private function return types
- **ruff**: ANN001 annotate function arguments
- **ruff**: PLC0415 move in-function imports to module top
- **ruff**: TC001 guard CamoufoxLauncher import behind TYPE_CHECKING
- **ruff**: TC002 guard playwright imports behind TYPE_CHECKING
- **ruff**: LOG015 route root-logger call through module logger
- **ruff**: G004 replace logging f-strings with lazy % formatting
- **ruff**: G003 avoid string concat in logging statement
- **ruff**: PIE810 merge multiple startswith calls
- **ruff**: SIM118 drop redundant .keys() in iteration
- **ruff**: SIM108 collapse if/else into ternary
- **ruff**: SIM105 replace try/except/pass with contextlib.suppress
- **ruff**: SIM300 flip yoda condition
- **ruff**: SIM117 merge nested with-statements
- **ruff**: SIM114 merge duplicate branches in form field handler
- **ruff**: RUF100 drop stale noqa directives
- **ruff**: RET505 drop superfluous elif after return
- **ruff**: PLC0207 pass maxsplit to str.split
- **ruff**: UP037 drop quoted annotation
- **ruff**: I001 re-sort imports after UP035 rewrite
- **ruff**: UP035 use collections.abc for Mapping/Callable
- **ruff**: F401 remove unused imports
- **ruff**: I001 sort imports
- two bugs from deep code review turn 2
- three bugs from deep code review turn 3 of 3
- three bugs from deep code review turn 2 of 3
- surface redirected origins in load_state failed_origins
- four bugs from deep code review turn 1 of 3
- three bugs from deep code review turn 3
- move new_origins_with_data.add after successful evaluate
- three bugs from deep code review turn 2
- handle query/fragment in IP detection and simplify download detection
- handle download-triggered navigation errors and IPv4 URL normalization
- validate cookie url/domain in load_state, check docker stop return codes

### Refactor

- **types**: revert module-private helper renames; rename navigation.normalize_url to avoid collision
- **browser_mcp**: extract \_playwright_internal facade for snapshotForAI/resolveSelector
- **browser_mcp**: isolate playwright \_impl_obj access and fix private symbols
- **browser_mcp**: decompose browser_fill_form
- **browser_mcp**: extract mode validation to reduce list_visible complexity
- **browser_mcp**: decompose browser_verify_list_visible
- **browser_mcp**: decompose browser_tabs to reduce complexity
- **browser_mcp**: split register() into per-tool helpers (interaction)
- **browser_mcp**: split register() into per-tool helpers (verification)
- **browser_mcp**: split register() into per-tool helpers (cookies)
- **browser_mcp**: split register() into per-tool helpers (inspection)
- **browser_mcp**: split register() into per-tool helpers (utility)
- **browser_mcp**: split register() into per-tool helpers (navigation)
- **browser_mcp**: split register() into per-tool helpers (mouse)
- **browser_mcp**: split register() into per-tool helpers (lifecycle)
- **browser_mcp**: split register() into per-tool helpers (code_execution)
- **browser_mcp**: split ContextManager.load_state into phase helpers
- **browser_mcp**: extract listener wiring from ContextManager.create
- move browser_mcp to mcps/browser_mcp
