#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export DOCXAI_RUN_REAL_DOCUMENT_QUALITY=1
# Force the capability-sensitive corpus checks to fail hard instead of skipping,
# so this exceptional gate cannot report a "green" run that silently skipped every
# real-document check when a conversion capability or source is missing.
export DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1
exec bash scripts/test.sh tests/test_real_document_validation_corpus.py -vv -s