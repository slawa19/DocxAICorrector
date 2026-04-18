# Test Suite Hardening Spec

Date: 2026-04-18

Status: implemented and verified

## Goal

Raise the signal quality of the main pytest suite by removing low-value tests, repairing stale tests that drifted from current runtime contracts, and fixing production regressions that the still-relevant tests correctly expose.

## Scope

This work covers the current baseline discovered by a full canonical WSL pytest run:

1. remove spec-like tests that validate archived markdown wording instead of production behavior
2. update stale tests that rely on outdated preparation-context contracts
3. fix lazy runtime model/config resolution where deterministic code paths should not require fully resolved model config
4. reconcile structure-recognition preparation expectations with the current contract
5. fix newly introduced pyright regressions rather than weakening the gate

## Non-Goals

This specification does not authorize:

1. broad refactoring of the entire test architecture
2. mass deletion of implementation-coupled tests without case-by-case review
3. weakening behavioral acceptance tests to make the suite green
4. raising the pyright baseline unless a separate explicit decision is made

## Current Failure Clusters

### 1. PreparedRunContext contract drift

Affected areas:

1. `tests/test_app.py`
2. `tests/test_state.py`

Problem:

1. `state.get_prepared_run_context_for_marker(...)` now returns only real `application_flow.PreparedRunContext`
2. several tests still inject ad-hoc objects or stubs and expect the old permissive behavior

Resolution policy:

1. update tests to use the real dataclass or a helper that builds it
2. do not loosen the production contract back to arbitrary object acceptance

### 2. Eager model resolution in image validation

Affected areas:

1. `image_validation.py`
2. `tests/test_image_validation.py`

Problem:

1. heuristic-only validation paths now fail early because model resolution happens before vision validation is known to be needed
2. this breaks deterministic unit tests and couples them unnecessarily to resolved runtime config

Resolution policy:

1. make model resolution lazy and only require it when vision validation is actually attempted
2. keep tests focused on behavioral validation outcomes

### 3. Eager text-model resolution in paragraph-boundary normalization

Affected areas:

1. `document.py`
2. `tests/test_paragraph_boundary_normalization.py`

Problem:

1. deterministic extraction/normalization paths call paragraph-boundary AI-review config resolution unconditionally
2. that resolution currently requires a text model even when AI review is disabled

Resolution policy:

1. make paragraph-boundary AI-review model resolution lazy
2. preserve deterministic normalization tests as high-value regression coverage

### 4. Structure-recognition preparation contract drift

Affected area:

1. `tests/test_preparation.py`

Problem:

1. some expected stage names and AI summary counters no longer match current behavior
2. part of the drift may be legitimate contract evolution, part may be a real counting bug

Resolution policy:

1. inspect current `apply_structure_map` and summary semantics
2. adjust code if metrics are wrong
3. otherwise update tests to assert the current intended contract

### 5. Spec-like archived-doc tests in main suite

Affected areas:

1. `tests/test_spec_image_level1.py`
2. `tests/test_spec_image_followup.py`

Problem:

1. these tests validate archived markdown/spec wording and headings
2. they violate the protected test quality contract

Resolution policy:

1. remove them from the main regression suite

### 6. Pyright regression gate

Affected areas:

1. `tests/test_typecheck.py`
2. current reported new diagnostics in `tests/test_config.py`

Problem:

1. pyright baseline is 9 errors
2. current report shows 11 errors, including new issues in test typing

Resolution policy:

1. fix the new diagnostics
2. keep the baseline unchanged unless the real count drops

## Execution Order

1. remove spec-like archived-doc tests
2. repair PreparedRunContext-based stale tests
3. fix lazy config/model resolution in production code
4. reconcile structure-recognition preparation tests
5. fix pyright regressions
6. rerun targeted tests
7. rerun full canonical pytest

## Implementation Status

Completed items:

1. removed spec-like archived-doc tests from the main regression suite:
   1. `tests/test_spec_image_level1.py`
   2. `tests/test_spec_image_followup.py`
2. updated stale PreparedRunContext-based tests to use the real runtime contract instead of permissive ad-hoc objects
3. made paragraph-boundary AI-review model resolution lazy so deterministic normalization paths no longer require unrelated text-model config
4. made image-validation model resolution lazy so heuristic-only validation paths no longer require unrelated runtime model config
5. reconciled structure-recognition preparation tests with the current runtime/model-registry contract
6. fixed new pyright diagnostics instead of weakening the gate
7. reran targeted pytest clusters during the repair work
8. reran the full canonical WSL pytest suite successfully
9. fixed the post-implementation follow-up items from local review:
   1. recommendation auto-apply now tracks an applied snapshot so application-written widget updates are not misclassified as manual overrides on the next rerun
   2. legacy model-config and model-registry migration logging is now deduplicated per process to avoid repeated warning/info spam on repeated config loads

Verification results:

1. full canonical pytest result after initial hardening: `790 passed, 7 skipped`
2. full canonical pytest result after follow-up fixes: `797 passed, 7 skipped`
3. pyright result after fixes: `0 errors`
4. typecheck baseline updated from `9` to `0` because the real error count was reduced to zero

## Acceptance Criteria Status

1. done: spec-like archived-doc tests are no longer part of the main `tests/` suite
2. done: deterministic normalization tests pass without requiring unrelated model config
3. done: image validation heuristic tests pass without requiring unrelated model config
4. done: preparation-context tests use real runtime contracts
5. done: pyright regression test improved below the original baseline and was updated to the new actual baseline of zero
6. done: full canonical pytest run is green and improved from the starting baseline

## Post-Implementation Follow-Up

Closed:

1. `app.py` recommendation auto-apply/manual-override drift resolved
2. `config.py` repeated migration logging spam resolved

Archive decision:

1. ready to archive
2. this specification is complete and should move to `docs/archive/specs/`

## Acceptance Criteria

1. spec-like archived-doc tests are no longer part of the main `tests/` suite
2. deterministic normalization tests pass without requiring unrelated model config
3. image validation heuristic tests pass without requiring unrelated model config
4. preparation-context tests use real runtime contracts
5. pyright regression test returns to baseline or improves below it with baseline updated separately if needed
6. full canonical pytest run has fewer failures than the starting baseline and no new unrelated regressions
