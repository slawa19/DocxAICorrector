# Feature Specification: Production acceptance semantics — coverage is review-data, not a gate

Date: 2026-07-11
Status: DECISION RECORD (2026-07-11). No code change — records a product decision and locks it to the
already-implemented, already-tested behavior. Owner-approved 2026-07-11 (Option A).
Owner surface: the production acceptance verdict (`validation/acceptance.build_acceptance_verdict`,
`late_phases.build_report_acceptance_verdict`) and what the UI presents as the headline verdict.
Companion: `specs/002-gate-report-honesty/spec.md` (introduced the three-state verdict this builds on);
`docs/specs/GLOBAL_PLAN_2026-06-16.md` Remaining-Work item 3 (acceptance meaning — this closes its open
PRODUCT half); `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` residual (c).
Changelog:
- 2026-07-11 — Created after the pre-UI review flagged that production has NO universal coverage threshold
  (all coverage checks are NOT-APPLICABLE by design) and asked what a production verdict should MEAN. Owner
  chose Option A (show the numbers, do not gate coverage). This spec records that decision and the rejected
  alternatives; it changes no code.

## The decision

**In production, the acceptance verdict gates on the STRUCTURAL / HYGIENE axis only. The COVERAGE axis (how
many source/target paragraphs went unmapped) is surfaced as review DATA, never as pass/fail.**

Concretely (this is the CURRENT, tested behavior — the decision elevates it from an implementation default to
an explicit product contract):

- **Gated in production** (a real `passed=False` enters `failed_checks`): `pipeline_succeeded`,
  `reader_cleanup_stage_completed`, `output_docx_openable` / `no_placeholder_markup` (when the DOCX exists),
  `page_placeholder_heading_concat_hygiene_applied`, `translation_quality_report_not_failed`,
  `bullet_marker_headings_present`, `false_fragment_headings_present`, `residual_bullet_glyphs_present`,
  `list_fragment_regressions_present`, `mixed_script_terms_present` (`acceptance.py:347-631`). This axis carries
  the project's stated priority — headings/subheadings with correct weight, no demotion, no broken lists.
- **NOT gated in production** (emitted NOT-APPLICABLE, carrying the measured `actual` as data):
  `formatting_diagnostics_threshold`, `unmapped_source_threshold`, `unmapped_target_threshold` — because
  production has no per-book loss budget, so `mismatch_threshold` / `unmapped_target_threshold` arrive as `None`
  (`late_phases.py:2802-2819`, `acceptance.py:472-557`). The harness still supplies integer budgets for its
  own proofs; production does not fake one.
- **Advisory (surfaced, never gates):** `emphasis_coverage_advisory` (spec 004),
  `paragraph_break_advisory` (spec 008), `theology_style_deterministic_issues_present` — all
  `failed_reason="advisory_only"`.

**What the UI shows:** a PASS/FAIL headline driven by the structural/hygiene axis, plus the coverage counts
(`unmapped_*_threshold.actual`) and advisory metrics as review DATA the reader can inspect — not as a verdict.

## Rationale (why Option A, and why the alternatives were rejected)

- **A universal RATIO threshold (rejected).** Making the coverage axis gate on `effective_unmapped ≤ X%` of
  total paragraphs sounds universal, but `X` can only be calibrated on the current 4-book corpus — and this
  project's own roadmap already names that trap: "absolute thresholds tuned on a tiny corpus are doc-specific in
  disguise" (`GLOBAL_PLAN_2026-06-16.md`, Generalization section). A ratio is less per-book than an absolute
  count, but the CHOSEN percentage is still a corpus artifact, and it is strictly unverifiable (there is no
  ground-truth "acceptable unmapped %"). Constitution VII forbids inventing a budget the source cannot justify.
- **A hybrid advisory-ratio (rejected as unnecessary now).** Emitting the coverage ratio as an advisory metric
  (like emphasis/paragraph-break) is harmless but adds a second number the UI must explain without changing any
  outcome. The raw counts already reach the UI as data; a derived ratio can be added later at the UI layer
  without a gate decision. Deferred, not adopted.
- **Option A fits the philosophy.** The priority axis (structure/hygiene) already gates honestly. Coverage is a
  secondary, mostly back-matter/mapping signal; the honest move is to show it and let the human judge, rather
  than manufacture an unverifiable universal budget. Rare tails are a conscious outcome, not a gate.

## Requirements *(mandatory)*

> Binding (Constitution VII): production MUST NOT gate on a coverage budget it cannot universally justify; it
> MUST still expose the measured coverage counts so nothing is hidden.

- **FR-001**: Production coverage checks (`formatting_diagnostics_threshold`, `unmapped_source_threshold`,
  `unmapped_target_threshold`) remain NOT-APPLICABLE when their thresholds are unconfigured (`None`), and MUST
  NOT enter `failed_checks`. (Already true: `acceptance.py:479/509/532`; `late_phases.py:2811-2812` returns
  `None` for absent config keys.)
- **FR-002**: Each NOT-APPLICABLE coverage check MUST still carry its measured `actual` (and the passthrough
  breakdown) so the UI can render the counts as review data. (Already true: `acceptance.py:480/510/533`.)
- **FR-003**: A configured integer threshold (including `0`) STILL gates — the harness path is unchanged; this
  decision is about the production (unconfigured) path only. (Already true and tested — see Anti-regression.)
- **FR-004**: No universal ratio threshold is introduced. No new config key that would gate production coverage
  is added.
- **FR-005 (documentation)**: The production-verdict meaning above is recorded here and referenced from
  `GLOBAL_PLAN` item 3 and the UI spec, so the UI is built to present coverage as data, not as a verdict.

## Success Criteria *(mandatory)*

- **SC-001**: With `mismatch_threshold=None, unmapped_target_threshold=None` (the production call,
  `late_phases.py:2793-2799`), the verdict's `failed_checks` contains NO coverage threshold check, and the
  coverage checks carry their `actual`. (Locked by the existing test
  `test_configured_zero_threshold_still_gates_unlike_unconfigured_none`,
  `tests/test_real_document_pipeline_validation.py:659-683`.)
- **SC-002**: The three states remain distinguishable in the data (passed / failed / not-applicable). (Locked by
  `test_acceptance_check_states_are_distinguishable_in_data`, `:686-714`.)
- **SC-003**: Full suite green; pyright ratchet ≤ 244. (No code change; nothing to re-run beyond confirming the
  cited tests still pass.)

## Non-goals

- **Not adding a production coverage gate** (ratio or absolute) — the whole point of the decision.
- **Not changing the harness** — it keeps its per-book integer budgets and its own `passed`/`failed_checks`.
- **Not changing the structural/hygiene gates** — they already gate honestly and carry the priority axis.
- **Not building the UI** — this only fixes what the UI must treat as verdict vs data.
- **Not touching the advisory metrics** (emphasis, paragraph-break) — they stay advisory.

## Anti-regression

- **Production never hard-fails on coverage:** locked by
  `test_configured_zero_threshold_still_gates_unlike_unconfigured_none` (`None` → NOT-APPLICABLE → not in
  `failed_checks`).
- **Coverage data is never hidden (anti-vacuum for the DECISION):** the same test asserts the NOT-APPLICABLE
  check still carries `actual == 2` — the counts remain visible to the UI even though they do not gate. A
  decision to "not gate" must not become "not show".
- **Configured budgets still gate:** the same test's first half (`mismatch_threshold=0` → applicable, fails) —
  so the decision does not weaken the harness or a future explicitly-configured deployment.

## Assumptions

- Production continues to leave `mismatch_threshold` / `unmapped_target_threshold` unconfigured
  (absent from `config.toml`, `late_phases.py:2809-2810`). If a deployment ever sets them, it opts INTO gating
  deliberately — which this decision explicitly permits (FR-003).
