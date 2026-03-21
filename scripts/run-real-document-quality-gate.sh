#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export DOCXAI_RUN_REAL_DOCUMENT_QUALITY=1
exec bash scripts/test.sh tests/test_real_document_quality_gate.py -vv -s