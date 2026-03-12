#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/.run"
ENV_PATH="$PROJECT_ROOT/.env"
APP_PATH="$PROJECT_ROOT/app.py"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
WSL_PID_PATH="$RUN_DIR/wsl_streamlit.pid"
PANDOC_EXE="$VENV_DIR/bin/pandoc"
STREAMLIT_LOG_PATH="$RUN_DIR/streamlit.log"
DEFAULT_PORT="8501"

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

print_runtime_status() {
    local port="${1:-$DEFAULT_PORT}"
    local managed_pid=""
    local managed_pid_running="false"
    local port_open="false"
    local health_status="false"

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

    if health_ok "$port"; then
        health_status="true"
    fi

    local state="stopped"
    if [[ "$managed_pid_running" == "true" && "$health_status" == "true" ]]; then
        state="running"
    elif [[ "$managed_pid_running" == "true" ]]; then
        state="managed-unhealthy"
    elif [[ "$port_open" == "true" ]]; then
        state="port-conflict"
    fi

    printf 'managed_pid=%s\n' "$managed_pid"
    printf 'managed_pid_running=%s\n' "$managed_pid_running"
    printf 'port_open=%s\n' "$port_open"
    printf 'health_ok=%s\n' "$health_status"
    printf 'state=%s\n' "$state"
}

print_environment_status() {
    local venv_ok="false"
    if venv_ready; then
        venv_ok="true"
    fi

    printf 'venv_ok=%s\n' "$venv_ok"

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
    # nohup ignores SIGHUP; disown removes from job table so the process
    # survives after this bash script exits. $! is the real Streamlit PID.
    nohup "$VENV_PYTHON" -m streamlit run "$APP_PATH" \
        --server.headless true \
        --server.address "$server_host" \
        --server.port "$server_port" \
        >> "$STREAMLIT_LOG_PATH" 2>&1 < /dev/null &
    local streamlit_pid="$!"
    disown "$streamlit_pid" 2>/dev/null || true

    # Give the process 3 seconds to fail fast (bad import, port conflict, etc.)
    sleep 3
    if ! kill -0 "$streamlit_pid" 2>/dev/null; then
        echo "streamlit process died immediately" >&2
        [[ -s "$STREAMLIT_LOG_PATH" ]] && tail -n 80 "$STREAMLIT_LOG_PATH" >&2 || true
        return 1
    fi

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
        sleep 1
    done
    echo "timeout"
    return 1
}

stop_streamlit() {
    local streamlit_pid
    streamlit_pid="$(read_managed_pid)"
    if [[ -n "$streamlit_pid" ]] && kill -0 "$streamlit_pid" 2>/dev/null; then
        kill "$streamlit_pid" 2>/dev/null || true
        # Escalate to SIGKILL if SIGTERM is ignored
        sleep 2
        if kill -0 "$streamlit_pid" 2>/dev/null; then
            kill -9 "$streamlit_pid" 2>/dev/null || true
        fi
    fi
    rm -f "$WSL_PID_PATH"
}

tail_log() {
    local lines="${1:-80}"
    if [[ -f "$STREAMLIT_LOG_PATH" ]]; then
        tail -n "$lines" "$STREAMLIT_LOG_PATH"
    fi
}

case "${1:-}" in
    check-python)
        check_python
        ;;
    check-pandoc)
        check_pandoc
        ;;
    check-api-key)
        check_api_key
        ;;
    status)
        status "${2:-$DEFAULT_PORT}"
        ;;
    run-streamlit)
        run_streamlit "${2:-localhost}" "${3:-$DEFAULT_PORT}"
        ;;
    wait-health)
        wait_health "${2:-$DEFAULT_PORT}" "${3:-90}"
        ;;
    stop-streamlit)
        stop_streamlit
        ;;
    tail-log)
        tail_log "${2:-80}"
        ;;
    *)
        echo "Unsupported action: ${1:-}" >&2
        exit 2
        ;;
esac