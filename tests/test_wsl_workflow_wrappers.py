from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_EXE = shutil.which("powershell.exe")
WSLPATH_EXE = shutil.which("wslpath")


pytestmark = pytest.mark.skipif(
    POWERSHELL_EXE is None or WSLPATH_EXE is None,
    reason="requires WSL interop with powershell.exe and wslpath",
)


def _to_windows_path(path: Path) -> str:
    assert WSLPATH_EXE is not None
    result = subprocess.run(
        [WSLPATH_EXE, "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _quote_for_powershell(value: str) -> str:
    return value.replace("'", "''")


def _run_powershell(command: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL_EXE is not None
    return subprocess.run(
        [POWERSHELL_EXE, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
    )


def _run_normalize_test_target(target: str) -> subprocess.CompletedProcess[str]:
    shared_path = _quote_for_powershell(_to_windows_path(REPO_ROOT / "scripts" / "_shared.ps1"))
    escaped_target = _quote_for_powershell(target)
    command = (
        f"& {{ . '{shared_path}'; "
        f"try {{ Normalize-TestTarget -Target '{escaped_target}' }} "
        f"catch {{ Write-Output $_.Exception.Message; exit 2 }} }}"
    )
    return _run_powershell(command)


def _run_dispatcher(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "scripts" / "project-control-wsl.sh"), *args],
        capture_output=True,
        text=True,
    )


def test_normalize_test_target_accepts_backslash_relative_path() -> None:
    result = _run_normalize_test_target(r"tests\test_config.py")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "tests/test_config.py"


def test_normalize_test_target_accepts_windows_absolute_path() -> None:
    absolute_target = _to_windows_path(REPO_ROOT / "tests" / "test_config.py")
    result = _run_normalize_test_target(absolute_target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == "tests/test_config.py"


def test_normalize_test_target_rejects_path_outside_repo() -> None:
    result = _run_normalize_test_target(r"C:\Windows\System32\notepad.exe")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "outside repository root" in (result.stdout + result.stderr)


def test_dispatcher_run_test_file_forwards_pytest_args() -> None:
    result = _run_dispatcher(
        "run-test-file",
        "tests/test_config.py",
        "-q",
        "-k",
        "test_load_app_config_exposes_image_validation_defaults",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_dispatcher_run_test_node_accepts_canonical_selector() -> None:
    result = _run_dispatcher(
        "run-test-node",
        "tests/test_config.py::test_load_app_config_exposes_image_validation_defaults",
        "-q",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
