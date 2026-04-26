from __future__ import annotations

import json
import os
import socket
import shutil
import subprocess
import tempfile
import time
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

def test_vscode_test_tasks_normalize_windows_relative_paths() -> None:
    tasks_by_label = {task["label"]: task for task in _load_vscode_tasks()}

    setup_task = tasks_by_label["Setup Project"]
    tail_log_task = tasks_by_label["Tail Streamlit Log"]
    full_task = tasks_by_label["Run Full Pytest"]
    docker_parity_task = tasks_by_label["Run Docker CI Parity Pytest"]
    file_task = tasks_by_label["Run Current Test File"]
    node_task = tasks_by_label["Run Current Test Node"]
    lietaer_task = tasks_by_label["Run Lietaer Real Validation"]
    lietaer_ai_task = tasks_by_label["Run Lietaer Real Validation AI"]
    real_document_task = tasks_by_label["Run Real Document Validation Profile"]

    assert setup_task["command"].endswith("scripts\\setup-project.ps1")
    assert tail_log_task["command"].endswith("scripts\\tail-streamlit-log.ps1")
    assert tail_log_task["args"] == ["-Lines", "${input:streamlitLogLines}"]

    assert full_task["command"] == "bash scripts/test.sh"

    assert docker_parity_task["command"].startswith(
        'bash -lc \'docker run --rm -v "$(pwd)":/src -w /src python:3.12 bash -lc "'
    )
    assert docker_parity_task.get("args", []) == []
    assert "pip install -r requirements.txt" in docker_parity_task["command"]
    assert "pytest tests/ -q" in docker_parity_task["command"]

    assert file_task["command"] == 'bash scripts/test.sh "${relativeFile}"'
    assert file_task.get("args", []) == []

    assert node_task["command"] == (
        'bash scripts/test.sh "${relativeFile}::${input:pytestNodeSuffix}"'
    )
    assert node_task.get("args", []) == []

    assert lietaer_task["command"] == "bash"
    lietaer_args = lietaer_task["args"]
    assert lietaer_args == [
        "-lc",
        "export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-core; export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-default; bash scripts/run-real-document-validation.sh",
    ]

    assert lietaer_ai_task["command"] == "bash"
    lietaer_ai_args = lietaer_ai_task["args"]
    assert lietaer_ai_args == [
        "-lc",
        "export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-core; export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-ai-default; bash scripts/run-real-document-validation.sh",
    ]

    assert real_document_task["command"] == "bash"
    real_document_args = real_document_task["args"]
    assert real_document_args[0] == "-lc"
    assert 'profile="$1"' in real_document_args[1]
    assert 'run_profile="$2"' in real_document_args[1]
    assert 'export DOCXAI_REAL_DOCUMENT_PROFILE="$profile"' in real_document_args[1]
    assert 'export DOCXAI_REAL_DOCUMENT_RUN_PROFILE="$run_profile"' in real_document_args[1]
    assert 'bash scripts/run-real-document-validation.sh' in real_document_args[1]
    assert real_document_args[2:] == ["_", "${input:realDocumentProfileId}", "${input:realDocumentRunProfileId}"]


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


def test_setup_contract_declares_required_system_packages() -> None:
    apt_requirements = (REPO_ROOT / "system-requirements.apt").read_text(encoding="utf-8")
    setup_script = (REPO_ROOT / "scripts" / "setup-wsl.sh").read_text(encoding="utf-8")
    status_script = (REPO_ROOT / "scripts" / "project-control-wsl.sh").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    workflow_doc = (REPO_ROOT / "docs" / "WORKFLOW_AND_IMAGE_MODES.md").read_text(encoding="utf-8")
    agent_rules = (REPO_ROOT / "docs" / "AI_AGENT_DEVELOPMENT_RULES.md").read_text(encoding="utf-8")
    copilot_instructions = (REPO_ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")

    assert "pandoc" in apt_requirements
    assert "libreoffice" in apt_requirements
    assert "antiword" in apt_requirements
    assert "apt-get install" in setup_script
    assert "DOCXAI_APT_TIMEOUT_SECONDS" in setup_script
    assert "system-requirements.apt" in setup_script
    assert "libreoffice_ok" in status_script
    assert "bash scripts/setup-wsl.sh" in readme
    assert "bash scripts/setup-wsl.sh" in contributing
    assert "system-requirements.apt" in workflow_doc
    assert "system-requirements.apt" in agent_rules
    assert "Setup Project" in copilot_instructions


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
