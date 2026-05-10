# Follow-up: AI-First Structure Recovery

Date: 2026-05-09
Status: Mechanical follow-up checklist complete; relation-kind separation, final TOC relation authority, Stage 2/apply anchor-conflict arbitration cleanup, and the downstream semantic-block / first-block authority leak-proofing slices are closed, but broader authority-boundary hardening remains open
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
- Reconciliation cleanup is now complete: reconciliation artifacts and
	preparation-side logging expose only canonical
	`patched_logical_indexes` / `anchor_disagreements_seen`, and the
	reconciliation schema version is bumped for the alias-removal payload.
- Stage 1 now carries an explicit `DocumentMap` status contract through
	preparation, processing outcome logging, and preparation diagnostic snapshots,
	so AI-first runs no longer hide Stage 1 loss behind an implicit
	`document_map = None` state.
- Targeted recall now uses bounded `DocumentMap.review_zones`, body-start and
	TOC-boundary neighbourhoods, persists per-index selection reasons in the
	reconciliation report/artifact payload for auditability, and preparation now
	invokes the Stage 3 targeted pass from that bounded Stage 1 uncertainty
	context instead of only through the classic divergence-count threshold.
- Segment detection now prefers applied AI/explicit structure in final
	post-AI mode, keeps typography fallback only for pre-AI diagnostic or
	explicitly degraded runs, and records the boundary source accordingly.
- Post-AI validation now treats heuristic-only heading/body facts as diagnostic
	evidence rather than final readiness authority when running in
	`post_ai_readiness` mode.
- TOC relation authority is now split explicitly: pre-AI relation
	normalization emits diagnostic `toc_region_candidate` relations, while the
	AI-first post-AI rebuild projects final `toc_region` from
	`DocumentMap.toc_region` when that authority exists; semantic-block grouping
	ignores candidate relations in final post-AI mode even if they are
	accidentally forwarded downstream.
- Relation-kind separation is therefore no longer the main open item in this
	follow-up.
- Downstream post-AI leak-proofing is now explicit for semantic blocks and the
	translate first-block composition gate: final TOC-only / mixed-structure
	decisions read binding or applied structure, while advisory heuristic and
	embedded hints remain diagnostic-only except for explicitly degraded fallback
	paths that preserve current fallback behaviour.
- Reconciliation targeting now accepts one canonical computed targeted
	selection for chosen paragraphs, prompt payload, and persisted
	`targeted_selection_reasons`, avoiding duplicate selection recomputation.
- Medium- and high-confidence `DocumentMap` anchor conflicts are now treated as
	Stage 2 proposals rather than hidden local arbitration inside
	`apply_structure_map(...)`: conflicting classifications are deferred for
	Stage 3/reconciliation, while the existing audited
	`document_map_reconciliation` locked-override path remains intact.
- `anchor_disagreements_seen` is now the only supported reconciliation
	disagreement field; the deprecated `anchor_conflicts` alias and the stale
	`patched_source_indexes` alias have been removed from report payloads,
	artifact payloads, preparation logging, tests, and docs on the reconciliation
	schema bump.
- Focused duplicate-`source_index` regressions already cover Stage 2 and Stage 3,
	and canonical structural diagnostic acceptance coverage already exists in
	`tests/test_real_document_validation_corpus.py`.

## Priority Findings

The previous mechanical follow-up checklist is complete, and the substantive
authority-boundary work is mostly closed. The remaining follow-up is now mainly
about stabilization, maintenance, and optional diagnostic review rather than a
large unresolved architecture gap.

Still-open follow-up framing:

- keep the parent spec's broader architecture work tracked in
	`Open Authority-Boundary Work`.

Current focus for future work is now narrower than the full parent-spec list:


- keep optional downstream audits narrow if any new post-AI consumer is added
	beyond the already hardened validation, segment-detection, semantic-block,
	first-block-gate, relation-authority, reconciliation, and degraded-status
	surfaces;
- keep preparation-visible AI-first fallback status explicit if future test or
	diagnostic work touches `structure_processing_outcome` or structural
	snapshot plumbing;
- continue small preparation-test maintenance work instead of broad test-architecture rewrites;
- keep follow-up docs honest about completed slices versus the still-open
	parent-spec authority-boundary backlog.

These are stabilization and audit tasks, not requests to add smarter
heuristics or reopen Stage 1/2/3 semantics.

## Removed As Stale

- The finding that `[structure_recovery].enabled = true` in `config.toml` is a direct implementation bug is stale. Current decision: AI-first must remain enabled by default so the new functionality is exercised, tested, and debugged as the primary path.
- The finding that `clean_paragraph_layout_artifacts(...)` must restore physical removal when recovery is disabled is stale relative to the parent spec's latest checklist. It remains a spec-consistency issue, not a code defect, because flag-only cleanup for all modes is now recorded as completed work.
- The finding that `boundary_normalization_applied` alone is missing is subsumed by the broader missing `ParagraphUnit` signal-field finding.
- The finding that Stage 2 descriptor `i = source_index` is duplicated by the broader end-to-end logical-coordinate finding.

## Testing Strategy Review

Current tests cover several important units: Stage 1 sampling/schema/retry paths, Stage 3 reconciliation basics, validation advisory fields, anchored classification wiring, cache-key anchor fingerprinting, structure-validation artifact plumbing, and the main authority-boundary cleanup contracts. At this point the remaining work is test/doc stabilization, not a core architecture-hardening blocker.

Optional review / milestone checks:

- Review whether additional real-document structural diagnostic assertions are needed beyond the existing canonical `lietaer-pdf-first-20-structure-core` acceptance coverage in `tests/test_real_document_validation_corpus.py`.

Simplicity improvements:

- Keep repeated preparation `app_config` boilerplate behind a small local helper such as `_make_ai_first_config(**overrides)` instead of introducing deep fixture layers.
- Continue opportunistic simplification of over-mocked preparation tests when a tiny helper can reduce wiring noise without hiding assertions.
- Prefer narrow unit tests for coordinate and cache-key contracts before real-document diagnostics; reserve full real-document validation for milestone checks.

## Acceptance Criteria For Closing This Follow-up

- [x] Stage 1/2/3 classifications and artifacts use `logical_index` end-to-end.
- [x] `source_index` is no longer overwritten as final identity, or the parent spec is amended to define a different provenance field explicitly.
- [x] Targeted reconciliation applies the same patched `StructureMap` that its report describes.
- [x] Missing Stage 0 signal fields are persisted on `ParagraphUnit` or the parent spec is amended to remove them from the required persistent contract.
- [x] Parent spec Configuration/Safety/Layout sections are reconciled with the current decision: AI-first enabled by default, legacy only as emergency/debug fallback, and flag-only cleanup as the active cleanup contract.
- [x] Focused tests cover duplicate source indexes, targeted-recall re-patching, document-map cache versioning, provider validation, and canonical structural diagnostic acceptance metrics.
 
