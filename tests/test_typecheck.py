"""Smoke test: run pyright and ensure type errors don't regress."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.typecheck]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Baseline: known pyright error count measured on a **clean worktree** with the
# PINNED pyright version (requirements.txt / pyproject.toml: pyright==1.1.409).
# This is a RATCHET: the test fails only if pyright finds MORE errors than the
# baseline. Lower the number whenever you clear errors; never raise it to admit NEW
# code debt. Re-measure and update ONLY when the pinned pyright version changes
# (a newer tool counts differently) — that is a deliberate tool bump, not new debt.
#
# History: this was 0 — accurate at fb7b83b (2026-04-27) but stale from 2026-05-12,
# when a `pyright fail-hard` CI step landed on a codebase that had already drifted to
# ~271 errors. CI stayed red for ~2 months and the test suite, gated behind it, never
# ran. Then pyright was UNPINNED (>=1.1.400): the 244 baseline (set 2026-07-10) went
# stale as the tool + code drifted, so CI's editable-install job failed on every push
# regardless of the diff. 2026-07-14: pinned pyright==1.1.409 and re-measured the true
# clean-checkout count on main (276; every 1.1.40x version yields 276-278 here). The
# excess over 244 is pre-existing debt in files unrelated to recent work
# (generation/formatting_transfer.py, structure tests, late_phases.py) — a future
# cleanup should LOWER this number.
#
# IMPORTANT: Always run this test on a clean checkout (`git status --porcelain` must be empty).
# Dirty worktrees (uncommitted docs/, specs/, etc.) can change the error count
# and cause flaky CI failures.
_ERROR_BASELINE = 276


def _run_pyright() -> dict:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"

    # Explicitly target only source and test code.
    # This prevents pyright from scanning docs/, uncommitted files,
    # or other directories that can cause flaky baseline counts
    # between local dirty worktrees and clean CI checkouts.
    #
    # We also pass --pythonpath pointing to the project venv when available
    # so pyright resolves imports the same way as the test environment.
    cmd = [
        sys.executable,
        "-m",
        "pyright",
        "src/docxaicorrector",
        "tests",
        "--outputjson",
    ]
    if venv_python.exists():
        cmd += ["--pythonpath", str(venv_python)]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
            timeout=180,
        )
    except FileNotFoundError:
        pytest.skip("pyright is not installed")
    except subprocess.TimeoutExpired:
        pytest.skip("pyright timed out")

    stdout = result.stdout
    # Some environments print a non-JSON preamble before the actual
    # --outputjson payload (for example nodeenv architecture diagnostics).
    # Anchor parsing to the object containing the standard "version" key.
    version_index = stdout.find('"version"')
    if version_index >= 0:
        json_start = stdout.rfind("{", 0, version_index + 1)
        if json_start >= 0:
            stdout = stdout[json_start:]
    else:
        json_start = stdout.find("{")
        if json_start > 0:
            stdout = stdout[json_start:]

    try:
        return json.JSONDecoder().raw_decode(stdout.lstrip())[0]
    except json.JSONDecodeError:
        pytest.fail(
            f"pyright produced invalid JSON.\nstdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"
        )
        raise AssertionError("unreachable")

def test_pyright_no_regression():
    """Fail if pyright error count exceeds the known baseline."""
    report = _run_pyright()

    diagnostics = report.get("generalDiagnostics", [])
    errors = [d for d in diagnostics if d.get("severity") == "error"]
    error_count = len(errors)

    if error_count > _ERROR_BASELINE:
        new_errors = errors[_ERROR_BASELINE:]
        messages = []
        for err in new_errors[:20]:
            file = err.get("file", "?")
            rng = err.get("range", {}).get("start", {})
            line = rng.get("line", "?")
            msg = err.get("message", "")
            messages.append(f"  {file}:{line}: {msg}")
        summary = "\n".join(messages)
        pytest.fail(
            f"pyright regression: {error_count} errors (baseline {_ERROR_BASELINE}).\n"
            f"New errors (first 20):\n{summary}"
        )

    if error_count < _ERROR_BASELINE:
        pytest.fail(
            f"pyright improved: {error_count} errors (baseline was {_ERROR_BASELINE}). "
            f"Update _ERROR_BASELINE in tests/test_typecheck.py to {error_count}."
        )
