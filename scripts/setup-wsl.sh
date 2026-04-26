#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APT_REQUIREMENTS_FILE="${DOCXAI_APT_REQUIREMENTS_FILE:-$PROJECT_ROOT/system-requirements.apt}"
VENV_DIR="${DOCXAI_VENV_DIR:-$PROJECT_ROOT/.venv}"
PYTHON_BIN="${DOCXAI_PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

require_file() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo "Required file not found: $path" >&2
        exit 2
    fi
}

resolve_sudo_prefix() {
    if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
        return 0
    fi
    if command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
        printf 'sudo\n'
        return 0
    fi
    echo "Passwordless sudo is required to install system packages. Run this script as root or configure sudo for the deployment user." >&2
    exit 1
}

read_apt_packages() {
    grep -Ev '^\s*(#|$)' "$APT_REQUIREMENTS_FILE"
}

install_system_packages() {
    local sudo_prefix="$1"
    local apt_timeout_seconds="${DOCXAI_APT_TIMEOUT_SECONDS:-1800}"
    mapfile -t packages < <(read_apt_packages)
    if [[ "${#packages[@]}" -eq 0 ]]; then
        echo "No apt packages listed in $APT_REQUIREMENTS_FILE"
        return 0
    fi

    echo "Installing system packages: ${packages[*]}"
    if [[ -n "$sudo_prefix" ]]; then
        "$sudo_prefix" timeout "$apt_timeout_seconds" apt-get update
        "$sudo_prefix" timeout "$apt_timeout_seconds" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
    else
        timeout "$apt_timeout_seconds" apt-get update
        timeout "$apt_timeout_seconds" env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
    fi
}

install_python_packages() {
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then
        echo "Creating virtualenv: $VENV_DIR"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    fi

    . "$VENV_DIR/bin/activate"
    python -m pip install --upgrade pip
    pip install -r requirements.txt
}

verify_runtime() {
    . "$VENV_DIR/bin/activate"
    python - <<'PY'
import importlib

for module_name in ("openai", "streamlit", "docx", "pypandoc", "dotenv"):
    importlib.import_module(module_name)
PY
    pandoc --version >/dev/null
    if command -v soffice >/dev/null 2>&1; then
        soffice --headless --version >/dev/null
    elif command -v libreoffice >/dev/null 2>&1; then
        libreoffice --headless --version >/dev/null
    else
        echo "LibreOffice executable not found after setup: expected soffice or libreoffice." >&2
        exit 1
    fi
}

require_file "$APT_REQUIREMENTS_FILE"
require_file "$PROJECT_ROOT/requirements.txt"

sudo_prefix="$(resolve_sudo_prefix)"
install_system_packages "$sudo_prefix"
install_python_packages
verify_runtime

echo "Setup complete. WSL runtime dependencies are installed."
