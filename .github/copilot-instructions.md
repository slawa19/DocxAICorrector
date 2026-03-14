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

## Project Lifecycle (app start/stop)

App lifecycle uses PowerShell tasks — those are fine:
- **Start Project** / **Stop Project** / **Project Status** — VS Code tasks

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
