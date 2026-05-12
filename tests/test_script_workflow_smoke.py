from __future__ import annotations

import os
import socket
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
POWERSHELL_EXE = shutil.which("powershell.exe")
WSLPATH_EXE = shutil.which("wslpath")

pytestmark = [
    pytest.mark.integration_local,
    pytest.mark.skipif(
        os.environ.get("DOCXAI_SKIP_WORKFLOW_SMOKE") == "1",
        reason="workflow smoke checks are excluded from mandatory CI signal",
    ),
]


def _to_windows_path(path: Path) -> str:
    resolved = path.resolve()
    if WSLPATH_EXE is not None:
        result = subprocess.run([WSLPATH_EXE, "-w", str(resolved)], capture_output=True, text=True, check=True)
        return result.stdout.strip()

    raw = str(resolved)
    if len(raw) >= 8 and raw.startswith("/mnt/") and raw[5].isalpha() and raw[6] == "/":
        suffix = raw[7:].replace("/", "\\")
        return f"{raw[5].upper()}:\\{suffix}"
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
    powershell_exe = POWERSHELL_EXE
    if powershell_exe is None:
        pytest.skip("requires PowerShell interop")
    assert powershell_exe is not None

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
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
        env=env,
    )


def _run_powershell_script(script_name: str, *args: str, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    powershell_exe = POWERSHELL_EXE
    if powershell_exe is None:
        pytest.skip("requires PowerShell interop")
    assert powershell_exe is not None

    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [
            powershell_exe,
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


def test_status_wrapper_smoke_reports_wsl_runtime() -> None:
    result = _run_powershell_script("status-project.ps1", env_overrides={"DOCX_AI_RUNTIME_MODE": "wsl"})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Runtime: wsl" in (result.stdout + result.stderr)


def test_wait_project_stopped_prefers_wsl_runtime_state_over_stale_windows_port() -> None:
    shared_path = _quote_for_powershell(_to_windows_path(REPO_ROOT / "scripts" / "_shared.ps1"))
    result = _run_powershell_command(
        (
            f"& {{ . '{shared_path}'; "
            "function Get-ProjectRuntimeStatus { @{ managed_pid_running = 'false'; port_open = 'false' } }; "
            "function Test-TcpPort { param([string]$ComputerName, [int]$Port) $true }; "
            "$status = Wait-ProjectStopped -Port 8501 -TimeoutSeconds 1; "
            "Write-Output ('STOPPED=' + $status['stopped']); "
            "Write-Output ('WINDOWS_PORT_OPEN=' + $status['windows_port_open']); "
            "exit 0 }"
        )
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "STOPPED=True" in (result.stdout + result.stderr)
    assert "WINDOWS_PORT_OPEN=True" in (result.stdout + result.stderr)


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


def test_runtime_status_recovers_repo_owned_pid_when_pid_file_is_missing() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        port = probe_socket.getsockname()[1]

    pid_override_dir = Path(tempfile.mkdtemp())
    pid_override_path = pid_override_dir / "wsl_streamlit.pid"
    app_path = str(REPO_ROOT / "app.py")
    process = subprocess.Popen(
        [
            "bash",
            "-lc",
            (
                "exec -a streamlit python3 -c 'import socket, sys, time; "
                "sock = socket.socket(); "
                "sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); "
                "sock.bind((\"127.0.0.1\", int(sys.argv[1]))); "
                "sock.listen(1); "
                "time.sleep(20)' \"$1\" \"$2\""
            ),
            "_",
            str(port),
            app_path,
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.fail("fake streamlit probe process exited unexpectedly")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check_socket:
                if check_socket.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.1)
        else:
            pytest.fail("fake streamlit probe process did not open the test port")

        result = subprocess.run(
            [str(REPO_ROOT / "scripts" / "project-control-wsl.sh"), "runtime-status", str(port)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
            env={**os.environ, "DOCXAI_WSL_PID_PATH": str(pid_override_path)},
        )

        assert result.returncode == 0, result.stdout + result.stderr
        status_lines = dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )
        assert status_lines["managed_pid_running"] == "true"
        assert status_lines["managed_pid"] == str(process.pid)
        assert status_lines["state"] == "managed-starting"
        assert pid_override_path.read_text(encoding="utf-8").strip() == str(process.pid)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        shutil.rmtree(pid_override_dir, ignore_errors=True)
