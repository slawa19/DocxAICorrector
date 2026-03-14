from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

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


def _run_dispatcher(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "scripts" / "project-control-wsl.sh"), *args],
        capture_output=True,
        text=True,
        check=False,
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


def test_dispatcher_run_test_file_smoke() -> None:
    result = _run_dispatcher(
        "run-test-file",
        "tests/test_config.py",
        "-q",
        "-k",
        "test_load_app_config_exposes_image_validation_defaults",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_dispatcher_run_test_node_smoke() -> None:
    result = _run_dispatcher(
        "run-test-node",
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
    result = _run_powershell_script("run-tests.ps1", env_overrides={"DOCX_AI_RUNTIME_MODE": "native"})

    assert result.returncode != 0
    assert "WSL-first workflow" in (result.stdout + result.stderr)