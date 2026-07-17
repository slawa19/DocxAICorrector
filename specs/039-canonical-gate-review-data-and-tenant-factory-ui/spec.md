# Feature Specification: Canonical structural gate honors coverage-is-review-data + tenant client_factory reaches the UI preparation path

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Two verified round-6 findings, both strong-effect:

1. **The canonical real-document gate fixes were applied to the wrong module.** Specs 037/038 made the
   coverage checks review-data in `validation/acceptance.py`, but the canonical
   `test_corpus_structural_passthrough` gate builds its verdict through
   `validation/structural.py::run_structural_passthrough_validation` →
   `validation/structural_checks.py::_build_structural_checks` (a SEPARATE check set that hard-gates
   `unmapped_source_threshold` / `unmapped_target_threshold` with `passed = actual <= allowed`, no
   furniture credit, no advisory concept). Constitution VII (lines 149-153) NAMES this gate: *"Any check
   that treats residual unmapped coverage as a HARD failure — including the real-document structural
   passthrough gate — is a defect… it MUST emit the residual as review data."* So the fix must land in
   `structural_checks.py`. The semantics are ALREADY decided (owner + Constitution: coverage is fully
   review-data, NOT spec-037's variant-2 "gate the genuine remainder") — this spec applies that same
   decision to the correct module. No new semantics decision.

2. **Tenant `client_factory` never reaches the main Streamlit UI preparation path.** `ProcessingService`
   injects a tenant factory into preparation (`processing_service.py:379-383`:
   `prepare_document_for_processing(get_client_fn=_prepare_client_factory, client_factory=_prepare_client_factory, …)`),
   but the UI path `_app.py::_start_background_preparation` →
   `application_flow.prepare_run_context_for_background` → `_prepare_run_context_core` (no
   `client_factory` parameter at all) → `prepare_document_for_processing(...)` (line ~303, no
   `client_factory`). With a tenant-specific endpoint/credentials, boundary review + extraction fall back
   to global config — a real SaaS-isolation gap, not polish.

Owner surface: (A) `validation/structural_checks.py` (the two coverage checks). (B)
`processing/application_flow.py` (thread `client_factory` through `_prepare_run_context_core` /
`prepare_run_context*`) + `ui/_app.py` (build + pass the tenant factory, mirroring
`processing_service.py`). (C) one cheap `structural_checks` anti-regression test.

Verification: the rewritten/added unit tests below stay green; the canonical
`test_corpus_structural_passthrough[mazzucato-*]` selector is re-run once and shows the coverage checks
no longer in `failed_checks` (a residual on a GENUINE structural gate — heading drift / text similarity —
if any, is reported honestly, NOT masked); full suite green; pyright ≤246. Changelog: 2026-07-17 —
created after round-6 confirmed 038 targeted `acceptance.py` while the canonical gate is
`structural_checks.py`, and that the UI preparation path lacks tenant-factory plumbing.

## (A) Canonical structural gate: coverage is review data

In `validation/structural_checks.py::_build_structural_checks`, the `unmapped_source_threshold` and
`unmapped_target_threshold` checks currently set `passed = actual <= allowed`. Make them ADVISORY:
- `passed` hardcoded `True` (the `_build_validation_result` roll-up at `structural.py:624` only reads
  `passed`, so `True` keeps them out of `failed_checks`).
- KEEP `actual`, `allowed`, `count_basis`, and every existing provenance field — they remain review data.
- ADD non-gating markers: `review_data: True`, `advisory: True`, and
  `exceeds_threshold: bool(actual > allowed)` so residual severity is visible without gating.

Scope discipline (do NOT over-reach):
- Leave `formatting_diagnostics_threshold` (gates on `formatting_diagnostics_count <=
  max_formatting_diagnostics` — a formatting-transfer defect COUNT, not one of the two named unmapped
  coverage axes) as a HARD gate. Constitution names the unmapped-source/target coverage axes only.
- Leave EVERY genuine structural gate hard: `pipeline_succeeded`, `output_docx_openable`,
  `heading_level_drift_threshold`, `text_similarity_threshold`, the sentinel-threshold checks, and the
  image/table minimum checks. If the gate stays red on one of THOSE, that is a genuine structural
  finding (F13/F14 territory), reported honestly — not something this spec masks.

## (B) Tenant client_factory reaches the UI preparation path

Mirror `processing_service.py:359-383` in the UI path:
- Add a `client_factory` (and, if the wrapper needs it, `get_client_fn`) parameter to
  `_prepare_run_context_core` and the public `prepare_run_context*` / `prepare_run_context_for_background`
  entry points, forwarded into the `prepare_document_for_processing_fn(...)` call (~line 303) exactly as
  `ProcessingService` does.
- In `ui/_app.py::_start_background_preparation`, build a tenant client-factory from the same
  model-selector / client resolution the app already uses (the UI's equivalent of
  `deps.get_client_for_model_selector_fn` / `deps.get_client_fn`) and pass it through
  `start_background_preparation`. If the UI genuinely has only one global client resolution, pass THAT
  resolution as the factory so boundary review + extraction honor it explicitly (closing the fallback),
  rather than relying on the module-global default.
- Do NOT change preparation behavior when `client_factory` is None (backward-compatible default).

## (C) Cheap passthrough anti-regression test

Add ONE focused unit test (no real-document run) guarding the passthrough classifier bypass (commit
`c7a5283`) so it is not protected ONLY by the ~25-min real-document gate: assert a genuine passthrough
block with a `heading_only_output` (a heading whose processed output is heading-only) is marked `valid`
via the bypass, WHILE a TOC block actually routed through the LLM (`_should_route_toc_through_llm` True)
still goes through the normal classifier. Reuse existing fixtures/helpers; keep it fast and deterministic.

## Non-goals / explicitly excluded (overengineering per owner)

- Concurrency retention refcount (active registry uses a `set`, not reference counting): P2, only
  reachable if two concurrent writers share one artifact path — left `partial`/documented, NOT fixed
  here (owner excluded low-effect/overengineering items).
- NO change to spec-037/038 `acceptance.py` behavior — that path is legitimately review-data already and
  is exercised by `test_real_document_pipeline_validation` / the breadth tests; it simply is not the
  canonical gate. Both paths now agree (coverage = review data).
- NO per-book literals, NO new region detectors (Constitution VII).
- NOT the deeper structure recognition of real PDFs (F13/F14) — genuine structural residual stays an
  honestly-reported gate, not masked.

## Anti-regression

- `structural_checks.py`: a synthetic metrics dict where `effective_unmapped_source_count` exceeds
  `max_unmapped_source_paragraphs` → `unmapped_source_threshold` is present with `passed=True`,
  `advisory=True`, `exceeds_threshold=True`, and is NOT in `failed_checks`; a genuine structural
  regression (e.g. `text_similarity` below `min_text_similarity`) STILL lands in `failed_checks`
  (coverage advisory did not blind the genuine gates).
- (B): a UI-path preparation test asserts the injected `client_factory` reaches
  `prepare_document_for_processing` (the boundary-review/extraction client is the tenant one, not the
  global default); the None default path is unchanged.
- Existing `tests/test_structure_validation.py`, `tests/test_real_document_validation_corpus.py`
  (fast/skip parts), and the UI/application-flow tests stay green; pyright ≤246.
- One real `test_corpus_structural_passthrough[mazzucato-*]` run: the two coverage checks are absent from
  `failed_checks`; any residual is a named genuine structural gate, reported honestly.

## SaaS rationale

(A) aligns the canonical gate with the single enshrined acceptance policy (coverage is review data) — it
no longer red-lights a real book for a bibliography/index/front-matter coverage tail, while genuine
structural regressions still fail. (B) closes a real tenant-isolation hole so the main UI's boundary
review + extraction honor per-tenant endpoint/credentials. (C) makes the passthrough bypass cheap to
protect in CI instead of relying on a 25-minute gate.
