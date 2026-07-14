# Feature Specification: Gate verdict — produced-but-flagged translation is "completed, needs review" (warn), not a blocking failure

Date: 2026-07-14
Status: DRAFT — approved scope (both levels: verdict classification + presentation), pre-implementation.
Owner surface: the document-level translation quality gate + its finalization in `pipeline/late_phases.py`
(`quality_status` determination, the `fail` vs `warn` finalize branches, the result-notice), the humanized
reason labels (`processing/preparation.py`), and the completed-result delivery path.
Companion: `specs/010-production-acceptance-semantics/spec.md` (coverage = review-DATA, not a gate; DOCX always
delivered), `specs/002-gate-report-honesty/spec.md` (policy-independent review-item emission),
`specs/013-ui-minimal-screen-and-result/spec.md` (the review-presentation block + severity model
[ПРАВКА]/[ПРОВЕРКА]/[КРИТ]).
Changelog:
- 2026-07-14 — Created after an orchestrator-verified assessment of a real EN→RU run
  (`RESISTANCE FACTORS … UKRAINE.docx`, heavily OCR-corrupted CIA scan). The document-level gate HARD-FAILED with a
  red "Результат заблокирован / Критическая ошибка качества перевода" and 5 reasons — but the output was fully
  usable (RU body coherent + complete, `untranslated_body_text_count=0`, 86/86 images intact) and **0 of the 5
  reasons were genuine translation defects**; all were `fix`/`review`-severity, OCR-garbage-induced or
  false-positive. The one genuine `defect` (a ЧАСТЬ I↔VI mis-pair) was not even among the gate reasons. This
  contradicts spec 010 and Constitution VII (do not block on source garbage).

## Verified findings (Constitution VIII — verified 2026-07-14 by code reading + the run's quality report)

- Policy: `_resolve_translation_quality_gate_policy` (`late_phases.py:1694-1700`) defaults `translate` →
  **"strict"**, which lets the quality report's `quality_status="fail"` block the run.
- Fail finalize (`late_phases.py:4286-4339`): the DOCX is produced (`_validate_nonempty_docx_bytes_or_fail` is the
  only real fatal guard) but the run is then marked FAILED — `present_error(..., "Критическая ошибка качества
  перевода")`, `latest_result_notice={level:"error", message:"Результат заблокирован document-level quality
  gate."}`, `emit_failed_result(...)`. So a usable document is presented as a red failure, and the normal
  success delivery (which persists the browsable `.docx`/`.md`/`formatting_review.txt` under `.run/ui_results/`)
  does not run.
- Warn finalize (`late_phases.py:4261-4274`): already yellow with friendly copy ("Готово. N абзацев требуют
  проверки оформления…").
- Reason labels are already humanized (`preparation.py:50-53` etc.); the alarming part is the wrapper framing
  ("не прошёл … (translation_quality_gate_failed) … Критическая ошибка … заблокирован").
- Per the run's `acceptance_verdict`: all coverage/threshold checks were `applicable:false` (spec 010 holds — they
  don't gate); the hard FAIL came SOLELY from `translation_quality_report_not_failed` mirroring the quality
  module's `quality_status="fail"`, driven by `fix`/`review`-severity items.

## Scope (both levels)

### Level 1 — Verdict classification (the gate stops hard-failing on review-grade items)
The document-level translation quality gate produces a hard **fail** (blocking, red) ONLY for genuinely
non-deliverable output:
- empty / unopenable DOCX (already handled by `_validate_nonempty_docx_bytes_or_fail`), and
- **body** wholesale untranslated above the catastrophic threshold (`untranslated_body_text_above_threshold`).

All `fix`/`review`-severity review reasons — role_loss, heading_demotion, false_fragment_headings,
list_fragment_regressions, untranslated_**structural**_text_review_required, and the like — resolve to
**`warn`** (review-DATA), never a hard document-level fail. `defect`-severity items (`[КРИТ]`, e.g.
`mapping_text_quality.bad_pair`) surface prominently as review items but do **not** block delivery (per spec 010
the DOCX is always delivered). Concretely: when the only fail-drivers are review-grade, `quality_status` must be
`warn`, not `fail`. This aligns the document verdict with the existing [ПРАВКА]/[ПРОВЕРКА]/[КРИТ] severity model.
No per-book literals (Constitution VII) — the rule keys on item **severity**, not on document content.

### Level 2 — Presentation + delivery (produced-but-flagged reads as "completed, needs review")
When `quality_status == "warn"` (now covering the flagged-but-usable cases):
- The result notice is a **yellow warning** (`level:"warning"`) with human-readable Russian copy, e.g.
  "Перевод завершён. Документ готов к использованию, но требует ручной проверки оформления: {humanized reasons or
  counts}. Подробности — в отчёте проверки (formatting_review.txt)." NO internal tokens
  (`translation_quality_gate_failed`), NO "критическая ошибка"/"заблокирован".
- The run routes through the **normal success/delivery finalization** so the browsable `.docx`/`.md`/
  `formatting_review.txt` artifacts are persisted under `.run/ui_results/` and the UI review block (severity
  counts + report download from spec 013) is shown. The DOCX/MD downloads must work.
- The genuinely-fatal path (empty/unopenable DOCX, body above catastrophic threshold) is UNCHANGED — red error,
  blocked, because there is no usable document.

## Non-goals

- Do NOT fix the OCR-garbage detection itself (ticket 017) — the gate simply must not BLOCK on garbage.
- Do NOT change what the gate DETECTS or the review items it emits — only the document-level VERDICT severity
  (fail→warn for review-grade) and the presentation. All review items still surface (data preserved).
- Do NOT change the coverage/acceptance thresholds (spec 010 already NOT-APPLICABLE in production).
- No per-book literals; no new custom CSS; all copy via `t()` where UI-rendered.

## Anti-regression

- **Genuinely broken output still hard-fails (red):** a run with an empty/unopenable DOCX, or body untranslated
  above the catastrophic threshold, still returns a blocked red error. Counter-proof test for each fatal case.
- **Flagged-but-usable → warn (yellow), delivered:** a run whose only fail-drivers are `fix`/`review` (or a
  `defect` review item) yields `quality_status="warn"`, a yellow "завершён, требует проверки" notice, persisted
  `.docx`/`.md`/`formatting_review.txt`, and a working DOCX download. Modeled on the RESISTANCE quality report.
- **Review DATA preserved:** every review item that previously appeared (role_loss, heading_demotion,
  false_fragment, list_fragment, untranslated_structural, bad_pair `[КРИТ]`) still appears in the report +
  `formatting_review_items` + the UI review block. Only the verdict severity/framing changes.
- Full suite green (except the documented pre-existing env items); pyright delta 0; catalog parity.

## Verification (Constitution I/II/VIII)

- `wsl.exe -d Debian --cd "…" -- bash scripts/test.sh` — full suite green.
- New tests: (a) review-grade-only reasons + nonempty DOCX → `quality_status=warn`, notice `level=warning`,
  success-delivery path taken; (b) empty DOCX → still fatal red; (c) `untranslated_body_text_above_threshold`
  → still fatal red; (d) humanized warn copy contains no internal tokens; (e) review items still emitted.
- Offline replay: re-run the document-level verdict over the saved RESISTANCE quality report
  (`.run/quality_reports/RESISTANCE_…json`) → verdict becomes `warn` (was `fail`), all 5 reasons still present as
  review items.
- pyright delta 0.
- Eyes-on: reload the app, re-run a flagged document, confirm the yellow "завершён, требует проверки" notice +
  working downloads instead of the red block.

## Rollout

Implement via the delivery loop on a branch off `main`; orchestrator verifies (full `scripts/test.sh`, the
fatal-vs-warn counter-proofs, the RESISTANCE-report offline replay, pyright delta 0) before merge.
