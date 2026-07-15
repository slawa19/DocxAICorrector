# Feature Specification: Align Pyright pythonVersion with the project (3.12)

Date: 2026-07-15
Status: **PLANNED (Wave 3 / hygiene).** Type-check config correctness. Pyright analyzes against 3.13 while the
package contract and CI run 3.12, so it can miss uses of API unavailable on the supported minimum.
Owner surface: `pyrightconfig.json`, `tests/test_typecheck.py` (baseline re-measure only).

## Problem (verified against HEAD d27c137)

`pyrightconfig.json:2` sets `"pythonVersion": "3.13"`, but `pyproject.toml:5` declares `requires-python = ">=3.12"`
and CI runs `python-version: '3.12'` (`.github/workflows/ci.yml`). Type-checking against a newer interpreter than
the supported minimum can accept code that fails to import/typecheck on 3.12.

## Scope (planned)

1. `pyrightconfig.json` → `"pythonVersion": "3.12"`.
2. Re-measure the clean-tree Pyright error count (the pinned `pyright==1.1.409`) and update `_ERROR_BASELINE` in
   `tests/test_typecheck.py` to the new value; refresh the baseline comment (it currently says 244 was measured at
   3.13). Measure on a clean checkout (the gitignored `run_reader_cleanup_replay_experiment.py` under
   tests/artifacts inflates the count — exclude it, matching CI's `git clean -fdx`).

## Test plan

- `tests/test_typecheck.py::test_pyright_no_regression` passes on a clean tree with `pythonVersion = 3.12` and the
  updated baseline (ratchet: not higher, not lower).

## Out of scope

- Reducing the error count itself (the review's per-module-ratchet reduction is separate Wave-3 work).

## SaaS rationale

Neutral; correctness hygiene so the type gate reflects the actually-shipped runtime.
