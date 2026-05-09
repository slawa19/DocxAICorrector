# Follow-up: AI-First Structure Recovery

Date: 2026-05-09
Status: Follow-up implementation complete
Parent spec: `docs/AI_FIRST_STRUCTURE_RECOVERY_SPEC_2026-05-08.md`

## Scope

This document consolidates the currently actionable follow-up findings for the
AI-first structure recovery implementation. It removes stale transcript logs and
drops findings that are no longer defects because later implementation notes in
the parent spec's `Closed Checklist` intentionally changed the contract.

The most important contract update is that the canonical repository default is
now intentionally AI-first. `structure_recovery.enabled = true` and Stage 1
Document Map generation should stay enabled by default because the current goal
is to test, debug, and improve the new structure-recovery pipeline, not to keep
the weak legacy path as the everyday behaviour. Legacy remains useful only as a
diagnostic or emergency rollback path.

Layout cleanup also now runs as flag-only signal extraction for all modes. These
two behaviours conflict with older sections of the parent spec but are
explicitly recorded as completed follow-up work in the parent spec's checklist.
The remaining work below is therefore split into implementation defects, spec
cleanups, and test-strategy gaps.

## Completed Since Previous Review

- Stage 1/2/3 coordinates now use `logical_index` end-to-end in descriptor
	payloads, `StructureMap.classifications`, `apply_structure_map(...)`,
	reconciliation patching, targeted recall scope validation, and reconciliation
	artifacts.
- Preparation now preserves the final post-targeted-reconciliation patched
	`StructureMap` instead of applying the intermediate pre-reconciliation map.
- Document-map cache keys now include `DOCUMENT_MAP_PROMPT_VERSION` and
	`DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION`, so prompt/schema changes invalidate
	stale cached maps.
- The parent spec has already been aligned to the current default-on contract:
	AI-first is canonical, legacy is emergency/debug fallback, and flag-only
	layout cleanup is the active cleanup contract.
- Extraction identity plumbing now preserves provenance in `source_index` and
	assigns only dense final `logical_index` / `paragraph_id` during final
	identity normalization.
- Missing Stage 0 signal fields were added to `ParagraphUnit`, populated once
	in final extraction/Stage 0 annotation, and Stage 1/2 descriptor builders now
	prefer persisted signal fields before falling back to defensive recomputation.
- `structure_recovery.document_map.model` is now validated through the same
	provider/capability contract as other text roles, with focused config tests
	for an explicit valid selector and an invalid selector.
- `_build_document_map_user_prompt(...)` now advertises only the canonical
	object shape for `paragraph_anchors`; list-shape tolerance remains parser-only
	compatibility code instead of the prompt contract.
- Stage 1 schema validation now rejects non-string `outline.evidence` entries
	instead of coercing them with `str(...)`.
- Focused preparation regressions now pin the corrected fallback literals:
	`120s` for document-map stage timeout, `60s` for targeted reconciliation
	timeout, and a narrowed `_run_structure_recognition(...)` regression proves
	that the final post-targeted reconciled `StructureMap` is the one applied.
- Stage 0 `signal_only` now holds consistently across structure repair and
	inline-break TOC annotation: AI-first paths emit advisory hints without
	mutating `role`, `structural_role`, `heading_level`, or `heading_source`
	binding fields.
- Targeted reconciliation now drops hallucinated out-of-scope classifications
	with a warning instead of failing the whole Stage 3 pass.
- Post-AI validation now has an explicit locked contract in code/tests that
	`outline_coverage_ratio` and `document_map_present` remain advisory-only
	fields for artifacts and diagnostics rather than readiness/escalation inputs.
- Final reconciliation artifacts now preserve the union of deterministic patch
	indexes from both reconciliation passes around targeted recall, so the audit
	trail no longer loses first-pass patches.
- The parent spec and owning code now define `logical_index` explicitly as the
	dense final-topology coordinate for the extracted paragraph list used by
	Stage 1/2/3, while `source_index` and `origin_raw_indexes` remain the
	provenance contract.
- Medium-confidence document-map anchors are now locked as advisory-only Stage
	2 inputs and targeted-recall context, not deterministic Stage 3 patch
	sources; the existing reconciliation regression coverage now represents an
	explicit contract rather than an accidental asymmetry.
- `_shrink_window_to_token_budget(...)` now keeps preview-first semantics but
	stops re-running preview shrink for every smaller prefix: it attempts preview
	shrink once for the full candidate window, then binary-searches the largest
	minimum-preview prefix that fits the token budget.
- Locked `explicit` / `adjacent` paragraphs now remain protected from ordinary
	Stage 2 AI classifications, but audited high-confidence
	`document_map_reconciliation` patches may override non-asset paragraphs when
	the same high-confidence Stage 1 anchor matches the requested role/level.
- Front-matter reporting now distinguishes advisory pre-body `body` paragraphs
	(`front_matter_body_advisories`) from true `front_matter_leaks`.
- Heuristic hint readers now share centralized whitelist/normalization helpers,
	and embedded hint payload builders sanitize invalid hint values instead of
	serializing arbitrary strings.
- The three OpenAI hard-timeout thread wrappers now use one shared fallback
	helper, preserving module-specific timeout exceptions while logging
	`request_abandoned=True` on hard timeout.
- Reconciliation artifacts now describe `patched_source_indexes` explicitly as a
	compatibility alias for `patched_logical_indexes`, and the reconciliation
	schema version is bumped for the extended report payload.
- `anchor_disagreements_seen` is now the canonical reconciliation disagreement
	field. Deprecated compatibility alias `anchor_conflicts` remains in payloads
	for one cleanup pass / next reconciliation schema bump only; the planned
	cleanup slice is: remove alias, update readers/docs/tests, then bump schema.
- Focused duplicate-`source_index` regressions already cover Stage 2 and Stage 3,
	and canonical structural diagnostic acceptance coverage already exists in
	`tests/test_real_document_validation_corpus.py`.

## Priority Findings

No open findings remain from the previous mechanical follow-up checklist. The
parent spec now tracks the remaining architecture hardening work in
`Open Authority-Boundary Work`.

Current focus for future work is the full parent-spec authority-boundary list:

- keep Stage 0 heuristic hints out of final post-AI structural authority;
- move high-anchor conflict arbitration out of local heuristics and into
  reconciliation/reporting;
- allow only audited high-confidence Stage 3 reconciliation patches to override
  locked legacy state;
- make post-AI validation phase-aware so diagnostic hints do not become final
  readiness facts;
- split strict `front_matter_leaks` from AI-approved front-matter body
  advisories;
- stop creating final TOC-region relations from pre-AI heuristic hints;
- make default/fallback `DocumentMap` status explicit;
- keep prompts from over-trusting heuristic hints;
- use `DocumentMap.review_zones`, anchor conflicts, and TOC/body boundary
  uncertainty to drive targeted recall;
- make AI-first fallback stage-specific and visibly degraded instead of silently
  returning to current heuristic roles;
- keep segment detection subordinate to applied AI structure;
- keep follow-up docs honest about completed checklist vs open authority work.

These are AI-first authority-boundary tasks, not requests to add smarter
heuristics.

## Removed As Stale

- The finding that `[structure_recovery].enabled = true` in `config.toml` is a direct implementation bug is stale. Current decision: AI-first must remain enabled by default so the new functionality is exercised, tested, and debugged as the primary path.
- The finding that `clean_paragraph_layout_artifacts(...)` must restore physical removal when recovery is disabled is stale relative to the parent spec's latest checklist. It remains a spec-consistency issue, not a code defect, because flag-only cleanup for all modes is now recorded as completed work.
- The finding that `boundary_normalization_applied` alone is missing is subsumed by the broader missing `ParagraphUnit` signal-field finding.
- The finding that Stage 2 descriptor `i = source_index` is duplicated by the broader end-to-end logical-coordinate finding.

## Testing Strategy Review

Current tests cover several important units: Stage 1 sampling/schema/retry paths, Stage 3 reconciliation basics, validation advisory fields, anchored classification wiring, cache-key anchor fingerprinting, and structure-validation artifact plumbing. The strategy is useful but does not yet fully protect the spec's highest-risk behaviours.

Required test additions:

- Review whether additional real-document structural diagnostic assertions are needed beyond the existing canonical `lietaer-pdf-first-20-structure-core` acceptance coverage in `tests/test_real_document_validation_corpus.py`.

Simplicity improvements:

- Replace repeated large `app_config` dictionaries in preparation tests with a small `_make_ai_first_config(**overrides)` helper or fixture.
- Split over-mocked preparation tests into focused wiring tests: one for Stage 1 to Stage 3 orchestration, one for final application/validation, and one for downstream document building.
- Prefer narrow unit tests for coordinate and cache-key contracts before real-document diagnostics; reserve full real-document validation for milestone checks.

## Acceptance Criteria For Closing This Follow-up

- [x] Stage 1/2/3 classifications and artifacts use `logical_index` end-to-end.
- [x] `source_index` is no longer overwritten as final identity, or the parent spec is amended to define a different provenance field explicitly.
- [x] Targeted reconciliation applies the same patched `StructureMap` that its report describes.
- [x] Missing Stage 0 signal fields are persisted on `ParagraphUnit` or the parent spec is amended to remove them from the required persistent contract.
- [x] Parent spec Configuration/Safety/Layout sections are reconciled with the current decision: AI-first enabled by default, legacy only as emergency/debug fallback, and flag-only cleanup as the active cleanup contract.
- [x] Focused tests cover duplicate source indexes, targeted-recall re-patching, document-map cache versioning, provider validation, and canonical structural diagnostic acceptance metrics.
 
