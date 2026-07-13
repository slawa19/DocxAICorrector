# Feature Specification: Remove partial translation + the structure-review panel (full-document-only)

Date: 2026-07-13
Status: DRAFT — approved scope, pre-implementation. Removes the "partial translation" feature (translating only
selected sections) AND the entire structure-review panel, leaving a single full-document processing flow. Keeps
the segmentation infrastructure (load-bearing for full-document translate context).
Owner surface: `ui/structure_review_panel.py` (deleted), `ui/_app.py` (dispatch + start plumbing),
`chapter_workflow/service.py` (selection helpers), `pipeline/reassembly.py` + `pipeline/late_phases.py`
(selected/hybrid/final output-mode branches), `runtime/state.py` (selection/confirmation state), `locales/*.json`
(`structure.*` keys), and the partial-translation tests.
Companion: `specs/013-ui-minimal-screen-and-result/spec.md`, `specs/015-simplify-preparation-summary/spec.md`
(same simplification arc). Depends on the partial-translation footprint audit (orchestrator-verified 2026-07-13).
Changelog:
- 2026-07-13 — Created. Director decision: drop partial translation and remove the structure panel ENTIRELY
  (structure overview, terminology review, and manifest tooling go with it — maximal simplification). Audit
  confirmed segmentation is NOT partial-only — `document_segments` feeds full-document translate context — so it
  MUST be kept; only the selection layer built on top of segments is removed.

## Verified findings (Constitution VIII — verified 2026-07-13 by direct code reading)

- The structure panel (`ui/structure_review_panel.py`, ~1254 LOC, entry `_render_analysis_review_panel`, called at
  `_app.py:1101`) is ~90% partial selection; it is also the only UI home for structure overview, terminology
  review (`_render_terminology_review`), and manifest import/export (advanced-tools expander). Per director
  decision all of it is removed.
- `_app.py` dispatch: `start_selected` (:1157 → `selected_only`), `start_selected_with_context`
  (:1199 → `selected_with_context`), `start_retry_failed` (:1244 → `selected_only`), `start_final_book`
  (:1305 → `final_translated_book`) are partial/final-only. `start` (:1136) and the now-unreachable `start_full_book`
  (:1283) → `legacy_full_document` are the full-document path (KEEP `start`; drop `start_full_book`).
- `chapter_workflow/service.py` (~640 LOC): `build_selected_processing_payload` (:346),
  `build_effective_selected_processing_state` (:477), `build_retry_failed_processing_state` (:539) + private
  helpers (~350 LOC) are selection-only. **KEEP** `build_document_context_prompt` (:148) — used on the full path.
  `build_structure_manifest_payload`/`export_structure_manifest` are panel-only → remove if no other consumer.
- `pipeline/reassembly.py`: `OutputMode` = `selected_only | selected_with_context | legacy_full_document |
  hybrid_document | final_translated_book` (:14). Selected/hybrid/final branches (:50-82, `_coerce_selected_output_mode`
  :151, hybrid resolvers) are partial-only; the `legacy_full_document` branch (:83-96) is the keeper.
- `pipeline/late_phases.py`: `hybrid_document` (:4080), `final_translated_book` (:4111-4180),
  `selected_with_context` (:4181-4207) branches are partial-only.
- **Segmentation is LOAD-BEARING for full-document translate runs (KEEP):** `document_segments` (= `prepared.segments`)
  is passed on the full path (`_app.py:1144`, `processing_service.py:428`) and consumed by
  `_build_block_segment_focus_prompt` (`block_execution.py:204-254`, gated `operation=="translate"`),
  `_build_previous_completed_segment_summary_prompt` (:282+), and `build_document_context_prompt`
  (`chapter_workflow/service.py:148`, used at `_app.py:1135`). Removing it would silently degrade full-document
  translation prompt quality.
- State: partial-only keys/helpers in `runtime/state.py` — `selected_segment_ids` (:566), the confirmation set
  (`structure_confirmed`, `confirmed_structure_fingerprint`, `confirmed_structure_segment_ids`,
  `confirmed_at_settings_hash`, `segments_loaded_for_source_token`; getters :529-546, `set_structure_confirmation_state`
  :591, `clear_structure_review_state` :608), and the segment-checkbox/filter/manifest widget keys.

## Scope

1. **Delete the panel.** Remove `ui/structure_review_panel.py` and its import + call site in `_app.py` (:1101, and
   the `_render_analysis_review_panel` wrapper :154-161). With the panel gone, the FILE_SELECTED view is: prepared
   summary + the single "Начать обработку" control.
2. **Remove partial dispatch + start plumbing (`_app.py`).** Delete the `start_selected`,
   `start_selected_with_context`, `start_retry_failed`, `start_final_book`, and (unreachable) `start_full_book`
   branches. Keep only `start` → `legacy_full_document`. Remove the selection parameters (`selected_segment_ids`,
   `segment_selection`, `include_front_matter`, `include_toc`) from `_start_background_processing` and its callees
   — OR default them to the full-document values — whichever keeps the shared worker signature clean.
3. **Remove selection helpers (`chapter_workflow/service.py`).** Delete `build_selected_processing_payload`,
   `build_effective_selected_processing_state`, `build_retry_failed_processing_state` and their private helpers.
   KEEP `build_document_context_prompt`. Remove `build_structure_manifest_payload`/`export_structure_manifest` only
   if grep shows no remaining consumer after the panel is gone.
4. **Collapse output modes (`pipeline/reassembly.py`, `pipeline/late_phases.py`).** Remove the `selected_only`,
   `selected_with_context`, `hybrid_document`, `final_translated_book` branches and their resolvers. KEEP
   `build_reassembly_plan` / `build_reassembly_result_manifest` / `assemble_final_markdown` for the full path.
   **Keep `output_mode` as a parameter defaulting to `legacy_full_document`** threaded through
   `setup.py`/`_pipeline.py`/`processing_service.py`/`processing_runtime.py`/`contracts.py` — do NOT rip it out of
   every signature (reduce the enum to what remains, or keep the enum and only remove the dead branches).
5. **State (`runtime/state.py`).** Remove the selection/confirmation keys + helpers listed in findings and their
   `_app.py` imports. Keep runtime segment-status/progress display only if it is still used by the full-run
   progress panel (grep `get_segment_status_by_id`/`get_segment_progress_by_id`); otherwise remove.
6. **i18n.** Remove ALL `structure.*` keys from `ru.json`/`en.json` (the panel is gone). Keep catalog parity.
7. **Tests.** Delete `tests/test_structure_review_panel.py`. Surgically update the mixed tests that reference
   partial symbols (`test_app_preparation.py`, `test_document_pipeline.py`, `test_app.py`, `test_state.py`,
   `test_processing_service.py`, `test_processing_runtime.py`, `test_runtime_artifacts.py`, `test_ui.py`,
   `test_ui_i18n.py`) — remove partial-path assertions, keep the full-document-path ones. Update
   `docs/testing/TEST_TIER_INVENTORY.md` (remove the deleted test file).

## Non-goals

- **Do NOT remove or degrade segmentation** (`document_segments`), `build_document_context_prompt`, or the per-block
  segment-focus / previous-segment-summary prompts — full-document TRANSLATE quality depends on them.
- Do NOT touch preparation/extraction, the gate, or edit/audiobook behavior.
- Do NOT rip `output_mode` out of every threaded signature — default it to `legacy_full_document`.
- Do NOT keep a slimmed panel — the whole panel is removed (director decision). The underlying glossary/terminology
  logic used by TRANSLATION stays; only its review UI is removed.
- No new custom CSS; all copy via `t()`.

## Anti-regression

- **Full-document TRANSLATE prompt quality is preserved (the #1 risk):** a translate run still builds
  `_build_block_segment_focus_prompt` / `build_document_context_prompt` from `document_segments`. A test drives a
  translate run (mocked LLM) and asserts the segment-focus/context prompts are still constructed (segments still
  flow to the worker). Edit-mode tests alone would NOT catch a regression here, so a translate-path assertion is
  mandatory.
- Full-document edit / translate / audiobook runs unchanged end-to-end; `legacy_full_document` reassembly path
  intact; DOCX/MD/review outputs unchanged.
- No dangling references: `grep -rn "start_selected\|start_final_book\|selected_with_context\|structure_review\|SegmentSelection\|set_structure_confirmation_state\|structure\." src/ tests/` returns only intended residue (the
  `output_mode` param default and any kept `segment` progress display). All `structure.*` i18n keys gone.
- Full suite green (except documented pre-existing env corpus/typecheck); pyright delta ≤ 0; catalog parity kept.

## Verification (Constitution I/II/VIII)

- `wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh` — full suite green.
- A translate-path test proves `document_segments` still reaches the worker and the segment-focus/context prompts
  are still built (anti-regression #1).
- `grep` proofs of complete removal (partial dispatch symbols + `structure.*` keys) empty.
- pyright delta ≤ 0.
- Eyes-on: reload the app, load a multi-chapter book, confirm no structure panel appears and full-document
  processing starts from the single control and completes.

## Rollout

Implement via the delivery loop on a branch off the updated `main` (after the UI batch merge), given the size
(~900-1000 LOC). Orchestrator verifies: full `scripts/test.sh`, grep-clean, pyright delta ≤0, and the translate-path
anti-regression assertion, before merge.
