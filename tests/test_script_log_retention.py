from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_EXE = shutil.which("powershell.exe")


def _run_wsl_script(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(REPO_ROOT / "scripts" / "project-control-wsl.sh"), script, *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
        env=env,
    )


def _to_windows_path(path: Path) -> str:
    resolved = path.resolve()
    raw = str(resolved)
    if len(raw) >= 8 and raw.startswith("/mnt/") and raw[5].isalpha() and raw[6] == "/":
        suffix = raw[7:].replace("/", "\\")
        return f"{raw[5].upper()}:\\{suffix}"
    return raw


def _run_powershell(command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    powershell_exe = POWERSHELL_EXE
    if powershell_exe is None:
        pytest.skip("requires PowerShell interop")
    assert powershell_exe is not None
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [
            powershell_exe,
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
        env=merged_env,
    )


def test_streamlit_log_rotation_preserves_active_path_and_backups() -> None:
    run_dir = Path(tempfile.mkdtemp())
    try:
        log_path = run_dir / "streamlit.log"
        log_path.write_text("A" * 150 + "\n" + "B" * 150 + "\n", encoding="utf-8")

        env = {
            **os.environ,
            "DOCXAI_RUN_DIR": str(run_dir),
            "DOCXAI_STREAMLIT_LOG_MAX_BYTES": "120",
            "DOCXAI_STREAMLIT_LOG_BACKUP_COUNT": "2",
        }
        result = _run_wsl_script("rotate-log-now", env=env)

        assert result.returncode == 0, result.stdout + result.stderr
        assert log_path.exists()
        assert log_path.read_text(encoding="utf-8") == ""
        backup_one = run_dir / "streamlit.log.1"
        assert backup_one.exists()
        assert "A" * 20 in backup_one.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_project_log_rollover_creates_numbered_backups() -> None:
    if platform.system() != "Windows":
        pytest.skip("requires Windows temp paths for PowerShell file access")
    run_dir = Path(tempfile.mkdtemp())
    try:
        shared_path = _to_windows_path(REPO_ROOT / "scripts" / "_shared.ps1")
        project_log_path = _to_windows_path(run_dir / "project.log")
        run_dir.mkdir(parents=True, exist_ok=True)
        command = (
            f"& {{ . '{shared_path}'; "
            f"$script:projectLogPath = '{project_log_path}'; "
            "$script:projectLogMaxBytes = 80; "
            "$script:projectLogBackupCount = 2; "
            "1..6 | ForEach-Object { Append-ProjectLogEntry ('line-' + $_ + '-' + ('X' * 30)) }; "
            "Get-ChildItem -LiteralPath (Split-Path -Parent $script:projectLogPath) -Filter 'project.log*' | "
            "Sort-Object Name | ForEach-Object { Write-Output $_.Name } }"
        )
        result = _run_powershell(command)

        assert result.returncode == 0, result.stdout + result.stderr
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        assert "project.log" in names
        assert "project.log.1" in names
        assert len([name for name in names if name.startswith("project.log.")]) <= 2
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
