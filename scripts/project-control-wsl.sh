#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$PROJECT_ROOT/.run"
ENV_PATH="$PROJECT_ROOT/.env"
APP_PATH="$PROJECT_ROOT/app.py"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
WSL_PID_PATH="$RUN_DIR/wsl_streamlit.pid"
PANDOC_EXE="$VENV_DIR/Scripts/pandoc.exe"
STREAMLIT_LOG_PATH="$RUN_DIR/streamlit.log"

mkdir -p "$RUN_DIR"

export PATH="$VENV_DIR/bin:$VENV_DIR/Scripts:$PATH"
if [[ -f "$PANDOC_EXE" ]]; then
    export PYPANDOC_PANDOC="$PANDOC_EXE"
fi

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "WSL venv python not found: $VENV_PYTHON" >&2
    exit 1
fi

source "$VENV_DIR/bin/activate"

check_python() {
    python - <<'PY'
import openai
import streamlit
import docx
import pypandoc
import dotenv
PY
}

check_pandoc() {
    if [[ -n "${PYPANDOC_PANDOC:-}" && -f "$PYPANDOC_PANDOC" ]]; then
        "$PYPANDOC_PANDOC" --version >/dev/null
        return
    fi
    if command -v pandoc >/dev/null 2>&1; then
        pandoc --version >/dev/null
        return
    fi
    if command -v pandoc.exe >/dev/null 2>&1; then
        pandoc.exe --version >/dev/null
        return
    fi
    echo "pandoc not found" >&2
    return 1
}

check_api_key() {
    ENV_PATH="$ENV_PATH" python - <<'PY'
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
    nohup python -m streamlit run "$APP_PATH" \
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
    local url="http://127.0.0.1:${1:-8501}/_stcore/health"
    local deadline=$((SECONDS + ${2:-90}))
    while [[ $SECONDS -lt $deadline ]]; do
        if command -v curl >/dev/null 2>&1; then
            result=$(curl -s --max-time 2 "$url" 2>/dev/null || true)
        else
            result=$(wget -q -O- --timeout=2 "$url" 2>/dev/null || true)
        fi
        if [[ "$result" == "ok" ]]; then
            echo "ok"
            return 0
        fi
        sleep 1
    done
    echo "timeout"
    return 1
}

stop_streamlit() {
    if [[ ! -f "$WSL_PID_PATH" ]]; then
        exit 0
    fi

    local streamlit_pid
    streamlit_pid="$(tr -d '[:space:]' < "$WSL_PID_PATH")"
    if [[ -n "$streamlit_pid" ]] && kill -0 "$streamlit_pid" 2>/dev/null; then
        kill "$streamlit_pid" 2>/dev/null || true
    fi
    rm -f "$WSL_PID_PATH"
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
    run-streamlit)
        run_streamlit "${2:-localhost}" "${3:-8501}"
        ;;
    wait-health)
        wait_health "${2:-8501}" "${3:-90}"
        ;;
    stop-streamlit)
        stop_streamlit
        ;;
    *)
        echo "Unsupported action: ${1:-}" >&2
        exit 2
        ;;
esac