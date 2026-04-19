#!/usr/bin/env bash
# Manual cleanup helper for stale ad-hoc files accumulated in ``.run/``.
#
# Removes whitelisted patterns of one-off files that are produced outside the
# normal production writer paths (manual pytest wrappers, imported stderr
# captures, ad-hoc PowerShell fragments, legacy pytest logs). Protected files
# such as ``app.log``, ``app.ready``, ``project.log``, ``streamlit.log``, PID
# files, and managed subdirectories are never touched by this script.
#
# Default behaviour is a dry-run preview. Pass ``--apply`` to actually delete
# matching files. Files younger than ``--min-age-days`` are preserved; default
# minimum age is 14 days so freshly produced diagnostics are safe.
#
# Usage:
#   bash scripts/clean-stale-run-artifacts.sh               # dry-run
#   bash scripts/clean-stale-run-artifacts.sh --apply       # delete
#   bash scripts/clean-stale-run-artifacts.sh --apply --min-age-days 7
#
# The script intentionally avoids touching ``.run/*/`` subdirectories — those
# are handled by the Python-side retention in ``runtime_artifact_retention.py``
# and by ``formatting_diagnostics_retention.py``.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${DOCXAI_RUN_DIR:-$PROJECT_ROOT/.run}"
APPLY=0
MIN_AGE_DAYS=14

while [[ $# -gt 0 ]]; do
    case "$1" in
        --apply)
            APPLY=1
            shift
            ;;
        --min-age-days)
            MIN_AGE_DAYS="${2:-14}"
            shift 2
            ;;
        -h|--help)
            sed -n '1,25p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ! -d "$RUN_DIR" ]]; then
    echo "No .run dir at $RUN_DIR; nothing to do."
    exit 0
fi

# Whitelist of patterns that are known to be ad-hoc/stale test wrappers or
# manual diagnostic captures. Never add broad globs here — each entry must be
# safe to delete without coordination with running processes.
PATTERNS=(
    "full_pytest_*.txt"
    "full_pytest_*.log"
    "full_pytest_powershell.exit"
    "last-pytest-full.log"
    "pytest_wrapper_*.txt"
    "optimization_regression.txt"
    "script_smoke_result.txt"
    "status_smoke_single.txt"
    "importtime_app.stderr.log"
    "lietaer_rerun.out"
    "min*.ps1"
    "shared-fragment.ps1"
    "wrapper-*.out"
    "wrapper-*.exit"
    "real_image_test.log"
    "real_image_test.exit"
)

TOTAL=0
DELETED=0

for pattern in "${PATTERNS[@]}"; do
    while IFS= read -r -d '' candidate; do
        # Skip files too young to be safely considered stale.
        if [[ -n "$(find "$candidate" -maxdepth 0 -mtime -"$MIN_AGE_DAYS" -print 2>/dev/null)" ]]; then
            continue
        fi
        TOTAL=$((TOTAL + 1))
        if [[ "$APPLY" == "1" ]]; then
            rm -f "$candidate"
            DELETED=$((DELETED + 1))
            echo "deleted: $candidate"
        else
            echo "would delete: $candidate"
        fi
    done < <(find "$RUN_DIR" -maxdepth 1 -type f -name "$pattern" -print0 2>/dev/null)
done

if [[ "$APPLY" == "1" ]]; then
    echo "stale artifacts removed: $DELETED (of $TOTAL matches)"
else
    echo "dry-run: $TOTAL matching stale file(s). Re-run with --apply to delete."
fi
