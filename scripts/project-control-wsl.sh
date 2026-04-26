#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${DOCXAI_RUN_DIR:-$PROJECT_ROOT/.run}"
ENV_PATH="$PROJECT_ROOT/.env"
APP_PATH="$PROJECT_ROOT/app.py"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
WSL_PID_PATH="${DOCXAI_WSL_PID_PATH:-$RUN_DIR/wsl_streamlit.pid}"
PANDOC_EXE="$VENV_DIR/bin/pandoc"
STREAMLIT_LOG_PATH="$RUN_DIR/streamlit.log"
APP_READY_PATH="$RUN_DIR/app.ready"
DEFAULT_PORT="8501"
STREAMLIT_LOG_MAX_BYTES="${DOCXAI_STREAMLIT_LOG_MAX_BYTES:-262144}"
STREAMLIT_LOG_BACKUP_COUNT="${DOCXAI_STREAMLIT_LOG_BACKUP_COUNT:-5}"
STREAMLIT_LOG_CHECK_INTERVAL_SECONDS="${DOCXAI_STREAMLIT_LOG_CHECK_INTERVAL_SECONDS:-30}"
STREAMLIT_LOG_ROTATOR_PID_PATH="${DOCXAI_STREAMLIT_LOG_ROTATOR_PID_PATH:-$RUN_DIR/streamlit_log_rotator.pid}"

mkdir -p "$RUN_DIR"

export PATH="$VENV_DIR/bin:$VENV_DIR/Scripts:$PATH"
if [[ -f "$PANDOC_EXE" ]]; then
    export PYPANDOC_PANDOC="$PANDOC_EXE"
fi

venv_ready() {
    [[ -x "$VENV_PYTHON" ]]
}

require_venv() {
    if ! venv_ready; then
        echo "WSL venv python not found: $VENV_PYTHON" >&2
        exit 1
    fi
}

is_positive_integer() {
    [[ "${1:-}" =~ ^[0-9]+$ ]] && [[ "${1:-0}" -gt 0 ]]
}

streamlit_log_retention_enabled() {
    is_positive_integer "$STREAMLIT_LOG_MAX_BYTES" && is_positive_integer "$STREAMLIT_LOG_BACKUP_COUNT"
}

rotate_streamlit_log_if_needed() {
    if ! streamlit_log_retention_enabled; then
        return 0
    fi

    if [[ ! -f "$STREAMLIT_LOG_PATH" ]]; then
        : > "$STREAMLIT_LOG_PATH"
        return 0
    fi

    local current_size="0"
    current_size="$(wc -c < "$STREAMLIT_LOG_PATH" 2>/dev/null | tr -d '[:space:]')"
    if [[ -z "$current_size" ]] || [[ "$current_size" -lt "$STREAMLIT_LOG_MAX_BYTES" ]]; then
        return 0
    fi

    local last_index="$STREAMLIT_LOG_BACKUP_COUNT"
    rm -f "$STREAMLIT_LOG_PATH.$last_index"

    local index=""
    for ((index=last_index-1; index>=1; index--)); do
        if [[ -f "$STREAMLIT_LOG_PATH.$index" ]]; then
            mv -f "$STREAMLIT_LOG_PATH.$index" "$STREAMLIT_LOG_PATH.$((index + 1))"
        fi
    done

    cp "$STREAMLIT_LOG_PATH" "$STREAMLIT_LOG_PATH.1"
    : > "$STREAMLIT_LOG_PATH"
}

streamlit_log_rotator_loop() {
    while true; do
        sleep "$STREAMLIT_LOG_CHECK_INTERVAL_SECONDS"
        rotate_streamlit_log_if_needed || true
    done
}

start_streamlit_log_rotator() {
    if ! streamlit_log_retention_enabled; then
        rm -f "$STREAMLIT_LOG_ROTATOR_PID_PATH"
        return 0
    fi

    stop_streamlit_log_rotator
    nohup bash "$0" internal-streamlit-log-rotator > /dev/null 2>&1 < /dev/null &
    local rotator_pid="$!"
    disown "$rotator_pid" 2>/dev/null || true
    printf '%s\n' "$rotator_pid" > "$STREAMLIT_LOG_ROTATOR_PID_PATH"
}

stop_streamlit_log_rotator() {
    if [[ -f "$STREAMLIT_LOG_ROTATOR_PID_PATH" ]]; then
        local rotator_pid
        rotator_pid="$(tr -d '[:space:]' < "$STREAMLIT_LOG_ROTATOR_PID_PATH")"
        if [[ -n "$rotator_pid" ]] && kill -0 "$rotator_pid" 2>/dev/null; then
            kill "$rotator_pid" 2>/dev/null || true
        fi
        rm -f "$STREAMLIT_LOG_ROTATOR_PID_PATH"
    fi
}

is_port_open() {
    local port="${1:-$DEFAULT_PORT}"
    (echo > "/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1
}

health_ok() {
    local port="${1:-$DEFAULT_PORT}"
    local url="http://127.0.0.1:${port}/_stcore/health"
    local result=""

    if command -v curl >/dev/null 2>&1; then
        result="$(curl -s --max-time 2 "$url" 2>/dev/null || true)"
    elif command -v wget >/dev/null 2>&1; then
        result="$(wget -q -O- --timeout=2 "$url" 2>/dev/null || true)"
    elif venv_ready; then
        result="$(HEALTH_URL="$url" "$VENV_PYTHON" - <<'PY'
from urllib.request import urlopen
import os

with urlopen(os.environ["HEALTH_URL"], timeout=2) as response:
    print(response.read().decode("utf-8", errors="replace").strip())
PY
        2>/dev/null || true)"
    elif command -v python3 >/dev/null 2>&1; then
        result="$(HEALTH_URL="$url" python3 - <<'PY'
from urllib.request import urlopen
import os

with urlopen(os.environ["HEALTH_URL"], timeout=2) as response:
    print(response.read().decode("utf-8", errors="replace").strip())
PY
        2>/dev/null || true)"
    else
        return 1
    fi

    [[ "$result" == "ok" ]]
}

read_managed_pid() {
    if [[ ! -f "$WSL_PID_PATH" ]]; then
        return 0
    fi
    tr -d '[:space:]' < "$WSL_PID_PATH"
}

app_page_ok() {
    local port="${1:-$DEFAULT_PORT}"
    local response=""
    local attempt=""
    for attempt in 1 2 3 4; do
        response="$(curl -fsS --max-time 2 "http://127.0.0.1:${port}/" 2>/dev/null || true)"
        if [[ "$response" == *"<title>Streamlit</title>"* || "$response" == *"<div id=\"root\"></div>"* ]]; then
            return 0
        fi
        sleep 0.25
    done
    return 1
}

app_ready() {
    [[ -f "$APP_READY_PATH" ]]
}

recover_managed_pid_from_port() {
    local port="${1:-$DEFAULT_PORT}"
    local probe_output=""
    local probe_exit=0
    local pid=""
    local found="false"
    local owned="false"

    if probe_output="$(find_repo_owned_streamlit_by_port "$port")"; then
        probe_exit=0
    else
        probe_exit=$?
    fi

    if [[ "$probe_exit" -ne 0 ]]; then
        return 1
    fi

    while IFS='=' read -r key value; do
        [[ -n "$key" ]] || continue
        case "$key" in
            found) found="$value" ;;
            owned) owned="$value" ;;
            pid) pid="$value" ;;
        esac
    done <<< "$probe_output"

    if [[ "$found" != "true" || "$owned" != "true" || -z "$pid" ]]; then
        return 1
    fi

    if ! kill -0 "$pid" 2>/dev/null; then
        return 1
    fi

    printf '%s\n' "$pid" > "$WSL_PID_PATH"
    printf '%s\n' "$pid"
}

print_runtime_status() {
    local port="${1:-$DEFAULT_PORT}"
    local managed_pid=""
    local managed_pid_running="false"
    local port_open="false"
    local health_status="false"
    local app_page_status="false"
    local app_ready_status="false"

    managed_pid="$(read_managed_pid)"
    if [[ -n "$managed_pid" ]] && kill -0 "$managed_pid" 2>/dev/null; then
        managed_pid_running="true"
    elif [[ -n "$managed_pid" ]]; then
        rm -f "$WSL_PID_PATH"
        managed_pid=""
    fi

    if is_port_open "$port"; then
        port_open="true"
    fi

    if [[ "$managed_pid_running" != "true" && "$port_open" == "true" ]]; then
        local recovered_pid=""
        if recovered_pid="$(recover_managed_pid_from_port "$port")"; then
            managed_pid="$recovered_pid"
            managed_pid_running="true"
        fi
    fi

    if health_ok "$port"; then
        health_status="true"
    fi

    if app_page_ok "$port"; then
        app_page_status="true"
    fi

    if app_ready; then
        app_ready_status="true"
    fi

    local state="stopped"
    if [[ "$managed_pid_running" == "true" && "$health_status" == "true" && "$app_page_status" == "true" ]]; then
        state="running"
    elif [[ "$managed_pid_running" == "true" ]]; then
        state="managed-starting"
    elif [[ "$port_open" == "true" ]]; then
        state="port-conflict"
    fi

    printf 'managed_pid=%s\n' "$managed_pid"
    printf 'managed_pid_running=%s\n' "$managed_pid_running"
    printf 'port_open=%s\n' "$port_open"
    printf 'health_ok=%s\n' "$health_status"
    printf 'app_page_ok=%s\n' "$app_page_status"
    printf 'app_ready_ok=%s\n' "$app_ready_status"
    printf 'state=%s\n' "$state"
}

print_environment_status() {
    local venv_ok="false"
    local libreoffice_ok="false"
    local libreoffice_path=""
    if venv_ready; then
        venv_ok="true"
    fi
    if libreoffice_path="$(command -v soffice 2>/dev/null)" && [[ -n "$libreoffice_path" ]]; then
        libreoffice_ok="true"
    elif libreoffice_path="$(command -v libreoffice 2>/dev/null)" && [[ -n "$libreoffice_path" ]]; then
        libreoffice_ok="true"
    else
        libreoffice_path=""
    fi

    printf 'venv_ok=%s\n' "$venv_ok"
    printf 'libreoffice_ok=%s\n' "$libreoffice_ok"
    printf 'libreoffice_path=%s\n' "$libreoffice_path"

    if [[ "$venv_ok" != "true" ]]; then
        printf 'deps_ok=false\n'
        printf 'pandoc_ok=false\n'
        printf 'api_key_ok=false\n'
        printf 'missing_packages=venv\n'
        printf 'pandoc_path=\n'
        return 0
    fi

    ENV_PATH="$ENV_PATH" PYPANDOC_PANDOC="${PYPANDOC_PANDOC:-}" "$VENV_PYTHON" - <<'PY'
from __future__ import annotations

import importlib
import os
from pathlib import Path

status = {
    "deps_ok": True,
    "pandoc_ok": False,
    "api_key_ok": False,
    "missing_packages": "",
    "pandoc_path": "",
}
missing = []

for module_name in ("openai", "streamlit", "docx", "pypandoc", "dotenv"):
    try:
        importlib.import_module(module_name)
    except Exception:
        missing.append(module_name)

status["deps_ok"] = not missing
status["missing_packages"] = ",".join(missing)

try:
    import pypandoc

    pypandoc.get_pandoc_version()
    status["pandoc_ok"] = True
    try:
        status["pandoc_path"] = pypandoc.get_pandoc_path()
    except Exception:
        status["pandoc_path"] = os.environ.get("PYPANDOC_PANDOC", "")
except Exception:
    status["pandoc_ok"] = False
    status["pandoc_path"] = os.environ.get("PYPANDOC_PANDOC", "")

try:
    from dotenv import load_dotenv

    env_path = Path(os.environ["ENV_PATH"])
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    value = os.getenv("OPENAI_API_KEY", "").strip()
    status["api_key_ok"] = bool(value and value != "your_api_key_here")
except Exception:
    status["api_key_ok"] = False

for key, value in status.items():
    if isinstance(value, bool):
        value = "true" if value else "false"
    print(f"{key}={value}")
PY
}

runtime_status() {
    local port="${1:-$DEFAULT_PORT}"
    print_runtime_status "$port"
}

environment_status() {
    print_environment_status
}

status() {
    local port="${1:-$DEFAULT_PORT}"
    print_runtime_status "$port"
    print_environment_status
}

check_python() {
    require_venv
    "$VENV_PYTHON" - <<'PY'
import openai
import streamlit
import docx
import pypandoc
import dotenv
PY
}

check_pandoc() {
    require_venv
    PYPANDOC_PANDOC="${PYPANDOC_PANDOC:-}" "$VENV_PYTHON" - <<'PY'
import pypandoc

pypandoc.get_pandoc_version()
print(pypandoc.get_pandoc_path())
PY
}

check_libreoffice() {
    if command -v soffice >/dev/null 2>&1; then
        soffice --headless --version
        return 0
    fi
    if command -v libreoffice >/dev/null 2>&1; then
        libreoffice --headless --version
        return 0
    fi
    echo "LibreOffice executable not found: expected soffice or libreoffice" >&2
    return 1
}

setup_project() {
    bash "$PROJECT_ROOT/scripts/setup-wsl.sh"
}

check_api_key() {
    require_venv
    ENV_PATH="$ENV_PATH" "$VENV_PYTHON" - <<'PY'
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path=os.environ["ENV_PATH"])
value = os.getenv("OPENAI_API_KEY", "").strip()
print("KEY_OK" if value and value != "your_api_key_here" else "KEY_MISSING")
PY
}

run_streamlit() {
    local server_host="$1"
    local server_port="$2"

    require_venv

    if [[ -f "$WSL_PID_PATH" ]]; then
        local existing_pid
        existing_pid="$(tr -d '[:space:]' < "$WSL_PID_PATH")"
        if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
            exit 0
        fi
        rm -f "$WSL_PID_PATH"
    fi

    : > "$STREAMLIT_LOG_PATH"
    rm -f "$APP_READY_PATH"
    start_streamlit_log_rotator
    # nohup ignores SIGHUP; disown removes from job table so the process
    # survives after this bash script exits. $! is the real Streamlit PID.
    nohup "$VENV_PYTHON" -m streamlit run "$APP_PATH" \
        --server.headless true \
        --server.address "$server_host" \
        --server.port "$server_port" \
        >> "$STREAMLIT_LOG_PATH" 2>&1 < /dev/null &
    local streamlit_pid="$!"
    disown "$streamlit_pid" 2>/dev/null || true

    # Fail fast without imposing a fixed 3-second startup penalty on every launch.
    local probe=""
    for probe in 1 2 3 4; do
        sleep 0.25
        if ! kill -0 "$streamlit_pid" 2>/dev/null; then
            stop_streamlit_log_rotator
            echo "streamlit process died immediately" >&2
            [[ -s "$STREAMLIT_LOG_PATH" ]] && tail -n 80 "$STREAMLIT_LOG_PATH" >&2 || true
            return 1
        fi
    done

    printf '%s\n' "$streamlit_pid" > "$WSL_PID_PATH"
}

wait_health() {
    local port="${1:-$DEFAULT_PORT}"
    local deadline=$((SECONDS + ${2:-90}))
    while [[ $SECONDS -lt $deadline ]]; do
        if health_ok "$port"; then
            echo "ok"
            return 0
        fi
        sleep 0.25
    done
    echo "timeout"
    return 1
}

wait_ready() {
    local port="${1:-$DEFAULT_PORT}"
    local deadline=$((SECONDS + ${2:-90}))
    while [[ $SECONDS -lt $deadline ]]; do
        if health_ok "$port" && app_page_ok "$port"; then
            echo "ok"
            return 0
        fi
        sleep 0.25
    done
    echo "timeout"
    return 1
}

stop_streamlit() {
    local streamlit_pid
    streamlit_pid="$(read_managed_pid)"
    if [[ -n "$streamlit_pid" ]] && kill -0 "$streamlit_pid" 2>/dev/null; then
        kill "$streamlit_pid" 2>/dev/null || true
        # Give SIGTERM a short grace period, but do not impose a fixed 2-second delay.
        local probe=""
        for probe in 1 2 3 4 5 6 7 8; do
            if ! kill -0 "$streamlit_pid" 2>/dev/null; then
                break
            fi
            sleep 0.25
        done
        if kill -0 "$streamlit_pid" 2>/dev/null; then
            kill -9 "$streamlit_pid" 2>/dev/null || true
        fi
    fi
    rm -f "$WSL_PID_PATH"
    rm -f "$APP_READY_PATH"
    stop_streamlit_log_rotator
}

find_repo_owned_streamlit_by_port() {
    local port="${1:-$DEFAULT_PORT}"
    local python_bin=""

    if venv_ready; then
        python_bin="$VENV_PYTHON"
    elif command -v python3 >/dev/null 2>&1; then
        python_bin="$(command -v python3)"
    else
        echo "error=python_not_available"
        return 2
    fi

    "$python_bin" - "$port" "$APP_PATH" <<'PY'
from __future__ import annotations

import os
import sys


def _listening_socket_inodes(port: int) -> set[str]:
    inodes: set[str] = set()
    port_hex = f"{port:04X}"
    for table_path in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table_path, encoding="utf-8") as handle:
                next(handle, None)
                for raw_line in handle:
                    columns = raw_line.split()
                    if len(columns) < 10:
                        continue
                    local_address = columns[1]
                    state = columns[3]
                    inode = columns[9]
                    if state != "0A":
                        continue
                    _, local_port_hex = local_address.rsplit(":", 1)
                    if local_port_hex.upper() == port_hex:
                        inodes.add(inode)
        except OSError:
            continue
    return inodes


def _pids_for_inodes(inodes: set[str]) -> list[int]:
    pids: set[int] = set()
    for pid_name in os.listdir("/proc"):
        if not pid_name.isdigit():
            continue
        fd_dir = f"/proc/{pid_name}/fd"
        try:
            fd_names = os.listdir(fd_dir)
        except OSError:
            continue
        for fd_name in fd_names:
            fd_path = f"{fd_dir}/{fd_name}"
            try:
                target = os.readlink(fd_path)
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]") and target[8:-1] in inodes:
                pids.add(int(pid_name))
                break
    return sorted(pids)


def _read_cmdline(pid: int) -> list[str]:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            return [part.decode("utf-8", errors="replace") for part in handle.read().split(b"\0") if part]
    except OSError:
        return []


def _is_repo_owned_streamlit(cmdline: list[str], app_path: str) -> bool:
    if not cmdline:
        return False
    joined = " ".join(cmdline)
    real_tokens = {
        os.path.realpath(token)
        for token in cmdline
        if token.startswith("/") and os.path.exists(token)
    }
    return app_path in real_tokens and "streamlit" in joined


def main() -> int:
    port = int(sys.argv[1])
    app_path = os.path.realpath(sys.argv[2])
    inodes = _listening_socket_inodes(port)
    if not inodes:
        print("found=false")
        return 0

    pids = _pids_for_inodes(inodes)
    if not pids:
        print("found=false")
        return 0

    repo_owned: tuple[int, str] | None = None
    foreign: tuple[int, str] | None = None

    for pid in pids:
        cmdline = _read_cmdline(pid)
        joined = " ".join(cmdline).replace("\n", " ").strip()
        if _is_repo_owned_streamlit(cmdline, app_path):
            repo_owned = (pid, joined)
            break
        if foreign is None:
            foreign = (pid, joined)

    if repo_owned is not None:
        pid, command = repo_owned
        print("found=true")
        print("owned=true")
        print(f"pid={pid}")
        print(f"cmdline={command}")
        return 0

    if foreign is not None:
        pid, command = foreign
        print("found=true")
        print("owned=false")
        print(f"pid={pid}")
        print(f"cmdline={command}")
        return 3

    print("found=false")
    return 0


raise SystemExit(main())
PY
}

tail_log() {
    local lines="${1:-80}"
    if [[ -f "$STREAMLIT_LOG_PATH" ]]; then
        tail -n "$lines" "$STREAMLIT_LOG_PATH"
    fi
}

rotate_log_now() {
    rotate_streamlit_log_if_needed
}

case "${1:-}" in
    check-python)
        check_python
        ;;
    check-pandoc)
        check_pandoc
        ;;
    check-libreoffice)
        check_libreoffice
        ;;
    check-api-key)
        check_api_key
        ;;
    setup)
        setup_project
        ;;
    status)
        status "${2:-$DEFAULT_PORT}"
        ;;
    runtime-status)
        runtime_status "${2:-$DEFAULT_PORT}"
        ;;
    env-status)
        environment_status
        ;;
    run-streamlit)
        run_streamlit "${2:-localhost}" "${3:-$DEFAULT_PORT}"
        ;;
    wait-health)
        wait_health "${2:-$DEFAULT_PORT}" "${3:-90}"
        ;;
    wait-ready)
        wait_ready "${2:-$DEFAULT_PORT}" "${3:-90}"
        ;;
    stop-streamlit)
        stop_streamlit
        ;;
    tail-log)
        tail_log "${2:-80}"
        ;;
    rotate-log-now)
        rotate_log_now
        ;;
    internal-streamlit-log-rotator)
        streamlit_log_rotator_loop
        ;;
    *)
        echo "Unsupported action: ${1:-}" >&2
        exit 2
        ;;
esac
