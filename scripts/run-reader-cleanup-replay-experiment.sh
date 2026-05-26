#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"
source .venv/bin/activate
python tests/artifacts/real_document_pipeline/run_reader_cleanup_replay_experiment.py "$@"
