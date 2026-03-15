# Testing

## Running Tests

Default terminal is WSL Debian. All test commands run directly in bash — no PowerShell wrappers.

```bash
# All tests (quiet)
bash scripts/test.sh tests/ -q

# One file (verbose)
bash scripts/test.sh tests/test_config.py -vv

# One test node (stop on first failure)
bash scripts/test.sh tests/test_config.py::test_name -vv -x

# With extra pytest flags
bash scripts/test.sh tests/ -q -x --tb=short
```

Never use PowerShell `.ps1` wrappers to run tests. They pipe output through WSL→PowerShell bridge which causes hangs and lost output.

When an AI agent runs tests for verification inside VS Code, prefer a user-visible execution path:

- use the existing VS Code tasks `Run Full Pytest`, `Run Current Test File`, or `Run Current Test Node` when they fit the requested scope;
- otherwise run the canonical WSL command in a foreground terminal, not in a hidden/background shell used only for internal capture;
- do not rely on unstable hidden terminal capture as the final source of truth for reporting test results;
- if a hidden or isolated rerun is needed for debugging, repeat the final verification in a visible user-facing path before claiming success.

## Project Lifecycle (app start/stop)

App lifecycle uses PowerShell tasks — those are fine:
- **Start Project** / **Stop Project** / **Project Status** — VS Code tasks

## Startup Performance Contract

Startup performance is a protected repository contract.

Canonical source of truth: `docs/STARTUP_PERFORMANCE_CONTRACT.md`.

AI agents must follow these rules:

- Do not add heavy synchronous cleanup, preload, environment bootstrap, or directory scanning back into the early startup path in `app.py` unless the user explicitly asked for a startup contract change.
- Do not remove one-time caching for app config, system prompt loading, Pandoc availability checks, or the process-wide OpenAI client without an explicit startup/performance task.
- Do not re-enable Streamlit file watching or `runOnSave` in `.streamlit/config.toml` as part of unrelated work.
- Do not change the WSL-first runtime contract for the app lifecycle as part of unrelated work.

If the user explicitly asks to change the startup contract, update the code, tests, and canonical docs together, then run `bash scripts/test.sh tests/test_startup_performance_contract.py -q` and `bash scripts/test.sh tests/test_app.py -q`.

## Key Directories

- `tests/` — all test files
- `scripts/test.sh` — test entry point (activates venv, runs pytest)
- `.run/` — runtime artifacts (logs, PID files)
- `.venv/` — WSL Python venv

## Test Conventions

- Unit tests: `tests/test_<module>.py`
- Markers: `@pytest.mark.integration` for tests needing external tools
- Fixtures: `tests/conftest.py`
- Test artifacts: `tests/artifacts/`

## Protected Test Workflow Contract

The WSL/bash test workflow is a protected repository contract.

AI agents must follow these rules:

- Do not add or restore PowerShell `.ps1` wrappers for test execution.
- Do not route tests through PowerShell, `ForEach-Object`, or any WSL to PowerShell output bridge.
- Do not change `.vscode/tasks.json` test tasks away from direct `wsl.exe` plus `bash scripts/test.sh` unless the user explicitly asked to redesign the test workflow.
- Do not change `scripts/test.sh`, `.vscode/tasks.json` test tasks, `tests/test_script_workflow_smoke.py`, or the test-workflow docs as part of unrelated work.
- If the user explicitly asks to change the test workflow contract, update all of these in the same change: `scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`, `README.md`, `CONTRIBUTING.md`, and `docs/WORKFLOW_AND_IMAGE_MODES.md`.
- After any intentional test-workflow change, run the canonical verification command `bash scripts/test.sh tests/test_script_workflow_smoke.py -q` and then `bash scripts/test.sh tests/ -q`.
