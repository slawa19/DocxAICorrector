from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_EXE = shutil.which("powershell.exe")
WSLPATH_EXE = shutil.which("wslpath")


def _to_windows_path(path: Path) -> str:
    resolved = path.resolve()
    if WSLPATH_EXE is not None:
        result = subprocess.run([WSLPATH_EXE, "-w", str(resolved)], capture_output=True, text=True, check=True)
        return result.stdout.strip()

    raw = str(resolved)
    if len(raw) >= 8 and raw.startswith("/mnt/") and raw[5].isalpha() and raw[6] == "/":
        return f"{raw[5].upper()}:\\{raw[7:].replace('/', '\\')}"
    return str(resolved)


def _run_test_sh(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "test.sh"), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def _quote_for_powershell(value: str) -> str:
    return value.replace("'", "''")


def _run_powershell_command(command: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    if POWERSHELL_EXE is None:
        pytest.skip("requires PowerShell interop")

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [
            POWERSHELL_EXE,
            "-NoProfile",
            "-NoLogo",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def _run_powershell_script(script_name: str, *args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    if POWERSHELL_EXE is None:
        pytest.skip("requires PowerShell interop")

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [
            POWERSHELL_EXE,
            "-NoProfile",
            "-NoLogo",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            _to_windows_path(REPO_ROOT / "scripts" / script_name),
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=env,
    )


def _load_vscode_tasks() -> list[dict[str, Any]]:
    tasks_path = REPO_ROOT / ".vscode" / "tasks.json"
    return json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"]


def test_test_sh_run_test_file_smoke() -> None:
    result = _run_test_sh(
        "tests/test_config.py",
        "-q",
        "-k",
        "test_load_app_config_exposes_image_validation_defaults",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_test_sh_run_test_node_smoke() -> None:
    result = _run_test_sh(
        "tests/test_config.py::test_load_app_config_exposes_image_validation_defaults",
        "-q",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_status_wrapper_smoke_reports_wsl_runtime() -> None:
    result = _run_powershell_script("status-project.ps1", env_overrides={"DOCX_AI_RUNTIME_MODE": "wsl"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Runtime: wsl" in (result.stdout + result.stderr)


def test_wrapper_rejects_native_runtime_mode() -> None:
    shared_path = _quote_for_powershell(_to_windows_path(REPO_ROOT / "scripts" / "_shared.ps1"))
    result = _run_powershell_command(
        (
            "& { $env:DOCX_AI_RUNTIME_MODE = 'native'; "
            f". '{shared_path}'; "
            "try { Get-PreferredRuntimeMode | Out-Null; exit 0 } "
            "catch { Write-Output $_.Exception.Message; exit 2 } }"
        )
    )

    assert result.returncode == 2
    assert "WSL-first workflow" in (result.stdout + result.stderr)


def test_vscode_test_tasks_normalize_windows_relative_paths() -> None:
    tasks_by_label = {task["label"]: task for task in _load_vscode_tasks()}

    full_task = tasks_by_label["Run Full Pytest"]
    file_task = tasks_by_label["Run Current Test File"]
    node_task = tasks_by_label["Run Current Test Node"]

    assert full_task["command"] == "bash scripts/test.sh"

    assert file_task["command"] == "bash"
    file_args = file_task["args"]
    assert file_args[0] == "-lc"
    assert 'path="$1"' in file_args[1]
    assert '${path//' in file_args[1]
    assert 'bash scripts/test.sh "$path"' in file_args[1]
    assert file_args[2:] == ["_", "${relativeFile}"]

    assert node_task["command"] == "bash"
    node_args = node_task["args"]
    assert node_args[0] == "-lc"
    assert 'path="$1"' in node_args[1]
    assert 'node_suffix="$2"' in node_args[1]
    assert '${path//' in node_args[1]
    assert 'bash scripts/test.sh "${path}::${node_suffix}"' in node_args[1]
    assert node_args[2:] == ["_", "${relativeFile}", "${input:pytestNodeSuffix}"]


def test_test_sh_rejects_non_test_file_selector() -> None:
    result = _run_test_sh("preparation.py", "-q")

    assert result.returncode == 2
    assert "Test selector must be under tests/: preparation.py" in (result.stdout + result.stderr)


def test_test_sh_rejects_empty_node_suffix() -> None:
    result = _run_test_sh("tests/test_config.py::", "-q")

    assert result.returncode == 2
    assert "Pytest node suffix must not be empty" in (result.stdout + result.stderr)


def test_test_sh_rejects_selector_after_pytest_options() -> None:
    result = _run_test_sh("-k", "test_load_app_config_exposes_image_validation_defaults", "tests/test_config.py", "-q")

    assert result.returncode == 2
    assert "Test selector must appear before pytest options: tests/test_config.py" in (result.stdout + result.stderr)


def test_test_sh_reports_missing_venv_clearly() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_copy = tmp_path / "test.sh"
        script_copy.write_text((REPO_ROOT / "scripts" / "test.sh").read_text(encoding="utf-8"), encoding="utf-8")

        result = subprocess.run(
            ["bash", str(script_copy)],
            capture_output=True,
            text=True,
            check=False,
            cwd=tmp_path,
        )

    assert result.returncode == 2
    assert "WSL venv activate script not found: .venv/bin/activate" in (result.stdout + result.stderr)


def test_dispatcher_rejects_legacy_test_actions() -> None:
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "project-control-wsl.sh"), "run-test-file", "tests/test_config.py"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )

    assert result.returncode == 2
    assert "Unsupported action: run-test-file" in (result.stdout + result.stderr)


def test_legacy_powershell_test_wrappers_are_removed() -> None:
    for script_name in ["run-tests.ps1", "run-test-file.ps1", "run-test-node.ps1"]:
        assert not (REPO_ROOT / "scripts" / script_name).exists()


def test_ci_exposes_separate_workflow_and_startup_contract_jobs() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "workflow-contract:" in ci_text
    assert "startup-contract:" in ci_text
    assert "needs: [workflow-contract, startup-contract]" in ci_text
    assert "bash scripts/test.sh tests/test_startup_performance_contract.py -q" in ci_text


def test_codeowners_protects_workflow_and_startup_contract_files() -> None:
    codeowners_text = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "/scripts/test.sh @slawa19" in codeowners_text
    assert "/.vscode/tasks.json @slawa19" in codeowners_text
    assert "/tests/test_script_workflow_smoke.py @slawa19" in codeowners_text
    assert "/docs/STARTUP_PERFORMANCE_CONTRACT.md @slawa19" in codeowners_text
    assert "/tests/test_startup_performance_contract.py @slawa19" in codeowners_text


def test_ci_uses_canonical_bash_test_contract() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in ci_text
    assert "python -m venv .venv" in ci_text
    assert ". .venv/bin/activate" in ci_text
    assert "bash scripts/test.sh tests/test_script_workflow_smoke.py -q" in ci_text
    assert "bash scripts/test.sh tests/ -q" in ci_text
    assert "python -m pytest tests -q" not in ci_text
