"""Smoke test: run pyright and ensure type errors don't regress."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Baseline: known pyright error count as of 2026-04-18 after test-suite hardening.
# When you fix type errors across the project, lower this number.
# The test fails if pyright finds MORE errors than the baseline (regression).
_ERROR_BASELINE = 0


def _run_pyright() -> dict:
    venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
    if not venv_python.exists():
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python"

    cmd = [sys.executable, "-m", "pyright", "--outputjson"]
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


@pytest.mark.integration
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
