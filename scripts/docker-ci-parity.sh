#!/usr/bin/env bash
# Mirror .github/workflows/ci.yml inside a python:3.12 container WITHOUT touching the
# host working tree. The repo is expected mounted READ-ONLY at /src; we copy it into a
# container-only work dir (excluding .venv/.run/.git) so the editable install and the
# .venv that scripts/test.sh requires are created in the container only — a local run
# never clobbers the developer's host/WSL .venv or writes build artifacts into the tree.
set -euo pipefail

src="${1:-/src}"
work="/work"

mkdir -p "$work"
tar -C "$src" --exclude=./.venv --exclude=./.run --exclude=./.git -cf - . | tar -C "$work" -xf -
cd "$work"

python -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python -c "import docxaicorrector"

# Pyright ratchet — same wrapper CI uses.
bash scripts/test.sh tests/test_typecheck.py -q

# Full static tier — selected BY MARKER, exactly as ci.yml. This used to be a
# hardcoded list of five files, which meant a sixth file carrying the marker ran
# nowhere: the marker-excluded suite below deselects it and the list did not name it.
bash scripts/test.sh tests/ -q -m static_workflow

# Marker-excluded suite, exactly as ci.yml.
bash scripts/test.sh tests/ -q -m "not static_workflow and not typecheck and not system_deps and not manual_ai_heavy and not browser_ui"
