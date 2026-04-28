#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

if [[ ! -f .venv/bin/activate ]]; then
	echo "WSL venv activate script not found: .venv/bin/activate" >&2
	exit 2
fi

. .venv/bin/activate
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

exec python -u benchmark_projects/pdf_candidate_benchmark/benchmark_runner.py "$@"