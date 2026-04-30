# PDF Translation Residual Quality Hardening Spec

Date: 2026-04-28

Parent specs:

- `docs/specs/PDF_SOURCE_IMPORT_SPEC_2026-04-26.md`
- `docs/specs/PDF_TRANSLATION_QUALITY_RECOVERY_SPEC_2026-04-27.md`
- `docs/specs/PDF_TRANSLATION_QUALITY_RECOVERY_REMAINING_WORK_SPEC_2026-04-27.md`

## Goal

Close the remaining quality gap for long-form PDF-derived translation after the structural recovery pass.

The 2026-04-28 canonical real-document run for `end-times-pdf-core` shows that the catastrophic first failure has been largely repaired:

- PDF conversion succeeds through the existing DOCX pipeline.
- TOC is bounded and no longer concatenated with the epigraph/body start.
- `## ●` bullet-only headings are gone.
- Output paragraph count is preserved in the new full run.
- The result DOCX is openable.

However, the result is not yet high-quality enough for the broader PDF translation recovery goal. The main remaining class of problems is now:

```text
false promotion of short inline/fragment paragraphs into headings
+ residual bullet glyphs inside body/list text
+ weak quality gates for these defects
+ insufficient domain/style validation for theological Russian translation
```

This spec defines the next narrow hardening pass. It must not reopen the entire PDF ingestion architecture and must not create a second PDF document model.

## Verified Current State After Initial Hardening Slice

After the first implementation slice for FR-3 through FR-8, the canonical validation state changed materially.

Verified on 2026-04-28 with fresh canonical reruns:

```text
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
DOCXAI_REAL_DOCUMENT_PROFILE=end-times-pdf-core DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-pdf-structural-recovery bash scripts/run-real-document-validation.sh
```

Observed current state:

- structural diagnostic remains stable and still fails only `unmapped_source_threshold`;
- full validation no longer passes silently;
- full validation now fails explicitly on the new residual-quality defect set;
- the saved translation quality report exposes first-class counters for these defects;
- after the final 2026-04-28 rerun, the full real-document report again emits `readiness_status=ready` and `quality_gate_status=pass` inside `preparation_diagnostic_snapshot`;
- after the same rerun, the failed full run still preserves a saved DOCX artifact and reports `output_docx_openable=True`.

This means the hardening pass has now achieved the strict-gate portion of the goal and restored the metadata/artifact contract around failed strict runs. The remaining work is now isolated to fixing the underlying residual translation defects themselves.

## Verified Remaining Work After Review On 2026-04-29

Reviewing the current implementation against the spec and the latest canonical `end-times-pdf-core` rerun leaves three concrete work items open.

Confirmed remaining implementation gaps:

- source-side TOC-aligned repair can still over-promote inline title fragments into headings when a TOC title appears inside a sentence and surrounding context indicates continuation rather than a true section boundary;
- the repeated-heading heuristic in output validation is broader than the intended FR-2 / FR-5 contract and must stay narrow enough to preserve legitimate repeated sections;
- list-fragment detection still needs explicit regression coverage for body-to-bullet continuations where the next bullet fragment starts uppercase, not lowercase.

Explicitly not a current bug for this spec slice:

- structural passthrough metrics already expose the residual-quality counters, but `end-times-pdf-core` intentionally keeps `structural_expected_failed_checks = ["unmapped_source_threshold"]`; residual-quality gating belongs to the full translation-quality path, not to the structural passthrough contract for this profile.

So the next slice should focus on precision and source-side promotion guards, not on widening structural passthrough failure conditions.

## Verified Completion On 2026-04-29

The remaining work listed above has now been closed by the subsequent narrow hardening slices.

Latest verified canonical reruns:

```text
DOCXAI_REAL_DOCUMENT_PROFILE=end-times-pdf-core \
DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-pdf-structural-recovery \
bash scripts/run-real-document-validation.sh
```

Key run progression for the final closure:

```text
run_id=20260429T073557Z_1141_Are_We_In_The_End_Times
worst_unmapped_source_count=0
false_fragment_heading_count=0
residual_bullet_glyph_count=0
list_fragment_regression_count=0
theology_style_deterministic_issue_count=3
quality_status=fail
gate_reasons=theology_style_deterministic_issues_present

run_id=20260429T074152Z_1184_Are_We_In_The_End_Times
readiness_status=ready
quality_gate_status=pass
output_docx_openable=True
worst_unmapped_source_count=0
false_fragment_heading_count=0
residual_bullet_glyph_count=0
list_fragment_regression_count=0
theology_style_deterministic_issue_count=0
quality_status=pass
gate_reasons=[]
```

What was closed in the final slices:

- symbol-only carryover markers such as `😂 2.` no longer reopen formatting-diagnostics mapping failures after list normalization;
- exact theology-style residuals now normalize deterministically in final markdown for the confirmed real-run cases:
  - `Четвёртое чашеобразное судилище` -> `Четвёртая чаша суда`
  - `koinonia` -> `койнония`
  - `imago Dei` -> `образа Божьего`
- the problematic `end-times-pdf-core` profile now passes the full translation-quality gate with all residual counters at zero.

Remaining work for this spec slice:

- none on the verified `end-times-pdf-core` canonical path.

## Evidence

Canonical full validation run:

```text
DOCXAI_REAL_DOCUMENT_PROFILE=end-times-pdf-core \
DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-pdf-structural-recovery \
bash scripts/run-real-document-validation.sh
```

Run artifacts:

```text
tests/artifacts/real_document_pipeline/runs/20260428T130821Z_1235_Are_We_In_The_End_Times/end_times_pdf_validation_report.json
tests/artifacts/real_document_pipeline/runs/20260428T130821Z_1235_Are_We_In_The_End_Times/end_times_pdf_validation_summary.txt
tests/artifacts/real_document_pipeline/runs/20260428T130821Z_1235_Are_We_In_The_End_Times/Are_We_In_The_End_Times_validated.md
tests/artifacts/real_document_pipeline/runs/20260428T130821Z_1235_Are_We_In_The_End_Times/Are_We_In_The_End_Times_validated.docx
```

Observed good signals, directly from `end_times_pdf_validation_summary.txt` and `end_times_pdf_validation_report.json`:

```text
result=succeeded
acceptance_passed=True
paragraph_count=377
output_artifacts.output_paragraphs=377
formatting_diagnostics_count=0
output_docx_openable=True
acceptance.checks[5].worst_unmapped_source_count=0
```

Additional signals derived from manual grep of the generated Markdown (not present as explicit fields in the current summary/report):

```text
bullet_heading_count=0    # derived: no line matches ^#{1,6}\s*[●•\-*]\s*$
english_residual_line_count=0 for sampled explicit patterns
    # derived: no line matches Judgment|tribulationist|tribulation|mark of the beast|Antichrist|Revelation
```

These derived metrics are the ones this spec proposes to turn into first-class report fields under FR-5.

Structural diagnostic still good:

```text
paragraph_count=377
heading_count=47
toc_header_count=1
toc_entry_count=13
bounded_toc_region_count=1
repaired_bullet_items=19
repaired_numbered_items=16
toc_body_boundary_repairs=2
remaining_isolated_marker_count=0
readiness_status=ready
quality_gate_status=pass
```

Fresh canonical structural rerun on 2026-04-28 still matches that contract:

```text
passed=False
failed_checks=[unmapped_source_threshold]
paragraph_count=377
heading_count=47
toc_header_count=1
toc_entry_count=13
bounded_toc_region_count=1
repaired_bullet_items=19
repaired_numbered_items=16
toc_body_boundary_repairs=2
remaining_isolated_marker_count=0
readiness_status=ready
quality_gate_status=pass
semantic_block_count=53
```

Fresh canonical full rerun after the first hardening slice:

```text
run_id=20260428T181509Z_1238_Are_We_In_The_End_Times
status=failed
result=failed
acceptance_passed=False
translation_quality_status=fail
translation_quality_gate_reasons=false_fragment_headings_present,residual_bullet_glyphs_present,list_fragment_regressions_present,theology_style_deterministic_issues_present
acceptance_failed_checks=pipeline_succeeded,output_docx_openable,false_fragment_headings_present,residual_bullet_glyphs_present,list_fragment_regressions_present,theology_style_deterministic_issues_present,structural_comparison_available
output_docx_openable=False
docx_path=None
translation_quality_report_path=.run/quality_reports/Are_We_In_The_End_Times.docx_1777400361959.json
```

Fresh counters from the saved translation quality report for that run:

```text
bullet_heading_count=0
false_fragment_heading_count=14
suspicious_heading_repetition_count=12
scripture_reference_heading_count=1
residual_bullet_glyph_count=8
list_fragment_regression_count=7
theology_style_deterministic_issue_count=2
toc_body_concat_detected=false
quality_status=fail
```

Newly verified remaining gap in the full report contract:

```text
preparation_diagnostic_snapshot.readiness_status=""
preparation_diagnostic_snapshot.quality_gate_status=""
```

So AC-7 and AC-9 are now partially satisfied for the strict-gating aspect, while AC-8 remains open in the full-report path.

Final canonical full rerun after the remaining contract fixes:

```text
run_id=20260428T183822Z_1207_Are_We_In_The_End_Times
status=failed
result=failed
acceptance_passed=False
translation_quality_status=fail
acceptance_failed_checks=pipeline_succeeded,false_fragment_headings_present,residual_bullet_glyphs_present,list_fragment_regressions_present,theology_style_deterministic_issues_present
preparation_diagnostic_snapshot.readiness_status=ready
preparation_diagnostic_snapshot.quality_gate_status=pass
output_docx_openable=True
docx_path=tests/artifacts/real_document_pipeline/runs/20260428T183822Z_1207_Are_We_In_The_End_Times/Are_We_In_The_End_Times_validated.docx
```

This closes the previously verified metadata/artifact regressions while preserving the intended explicit failure on residual-quality defects.

Remaining defects in the generated Markdown:

```text
Are_We_In_The_End_Times_validated.md:69  ## начертание зверя
Are_We_In_The_End_Times_validated.md:91  ## (Матфея 24:36)
Are_We_In_The_End_Times_validated.md:103 ## Великая скорбь
Are_We_In_The_End_Times_validated.md:261 ## Спутники? Ракеты?)
Are_We_In_The_End_Times_validated.md:325 ## начертание зверя
Are_We_In_The_End_Times_validated.md:499 ## начертание зверя
Are_We_In_The_End_Times_validated.md:619 ## начертание зверя
Are_We_In_The_End_Times_validated.md:627 ## начертание зверя
```

Residual bullet glyphs:

```text
Are_We_In_The_End_Times_validated.md:435 - Есть некий вулкан ... ● пятимесячная атака ...
Are_We_In_The_End_Times_validated.md:439 ● собирают армию ...
Are_We_In_The_End_Times_validated.md:451 Китай ... технологическими ● достижениями?
Are_We_In_The_End_Times_validated.md:455 - Соединённые Штаты ... глобальную ● культуру ...
Are_We_In_The_End_Times_validated.md:465 ... стран ● десять ядерных держав ● расширенный БРИКС ...
Are_We_In_The_End_Times_validated.md:519 ... сила, ● где анти-троица ...
Are_We_In_The_End_Times_validated.md:701 ● Или можете отбросить подготовительные меры ...
```

List/fragment defects:

```text
Are_We_In_The_End_Times_validated.md:109-111
- Сторонники мидтрибулационного взгляда считают, что христиане будут восхищены в середине
- Великой скорби.

Are_We_In_The_End_Times_validated.md:137-143
- Поразительно ... схеме: 1.
...
2. Бог судит их за грех.
3. Бог спасает остаток ...

Are_We_In_The_End_Times_validated.md:515-523
... он может явиться ... с Седьмой
- Судной печатью № 1 ...

Are_We_In_The_End_Times_validated.md:685
... Таковых удаляйся». 6.
```

Style/domain issues:

```text
Are_We_In_The_End_Times_validated.md:137 ## Суд над пятым печатью ...
Are_We_In_The_End_Times_validated.md:343 ## Четвёртое чашеобразное судилище ...
Are_We_In_The_End_Times_validated.md:691 Создавайте кoinonia-сообщества ...
Are_We_In_The_End_Times_validated.md:707 богословие imago Dei ...
```

## Decision

The next pass should harden generic document-structure and output-quality validation around the actual remaining defects. It should not add a new PDF model, OCR, or direct PDF parsing.

Priority order:

1. Prevent false fragment headings in source structure and output Markdown.
2. Detect and gate residual bullet glyphs in body/list text.
3. Detect list-fragment regressions after translation.
4. Make quality gates fail/warn on those defects for strict PDF structural recovery profiles.
5. Add a small theology/style validation layer only for deterministic high-confidence issues, not a broad subjective literary review.

## Non-Goals

Do not implement in this pass:

- OCR for scanned PDF.
- Direct PDF extraction through PyMuPDF/pdfplumber.
- A second internal PDF paragraph model.
- Full human-level theological editing.
- A broad grammar checker.
- A general LLM-based post-editor.
- A separate domain translation pipeline.

## Functional Requirements

### FR-1. Demote Or Prevent False Fragment Headings

The pipeline must identify short source/output fragments that should not become Markdown/DOCX headings.

High-confidence false heading patterns include:

- scripture references only, e.g. `(Матфея 24:36)` or `(Matthew 24:36)`;
- single theological terms inserted mid-sentence, e.g. `начертание зверя` when previous paragraph ends with a continuation signal such as `является ли`, `что`, `относительно`, a preposition, or an opening parenthesis;
- repeated heading text that appears as a fragment inside a paragraph flow, not as a section boundary;
- dangling phrase headings with closing punctuation only, e.g. `Спутники? Ракеты?)`;
- heading immediately followed by a lowercase continuation or a punctuation-only continuation, indicating it was split from a sentence.

The detector must stay deterministic. The soft criterion "heading forms one grammatical sentence with surrounding body paragraphs" must not be implemented as general semantic analysis. It is allowed only as an advisory-only signal and only when it is expressed through narrow deterministic heuristics such as:

- previous non-empty paragraph ends with a continuation word from a closed allowlist (for example `является ли`, `что`, `относительно`, `с`, `в`, `на`, `к`, `по`, `для`, `о`, `у`, or an opening bracket/parenthesis);
- next non-empty paragraph starts with a lowercase letter, a closing bracket, or a sentence-continuation particle.

Anything beyond such deterministic triggers must be deferred to a future spec and must not fail strict gates here, to keep FR-2 (preserve legitimate headings) achievable without semantic analysis.

Required behavior:

- Prevent deterministic repair from promoting these fragments when source context indicates inline continuation.
- Add output validation that detects these patterns even if the LLM emits them as headings.
- For strict translation profiles, fail the document quality gate if false fragment heading count is above zero or above an explicitly configured tiny tolerance.
- For advisory mode, surface a machine-readable quality warning.

Candidate reason names:

```text
false_fragment_headings_present
scripture_reference_heading_present
inline_term_heading_present
sentence_split_heading_present
```

### FR-2. Preserve Legitimate Headings

The false-heading guard must not remove legitimate section headings.

Legitimate headings include:

- TOC-aligned major sections;
- section headers such as `Введение`, `Кто такой Антихрист?`, `Начертание зверя`, `Практические шаги для отдельных людей` when they occur at actual section boundaries;
- repeated section labels if the source truly repeats them as headings for a new section;
- judgment sequence headings when the source structure intentionally uses them as subsections.

Acceptance requires context-aware tests: the same text may be valid as a heading at a section boundary and invalid as an inline fragment.

### FR-3. Detect Residual Bullet Glyphs In Body/List Text

The final output quality report must count residual bullet glyphs `●`, `•`, `◦`, `‣` outside valid Markdown list syntax.

Defects include:

- `●` embedded inside a body sentence;
- a line starting with `●` but not normalized to `- ` or a valid list item;
- multiple bullet glyphs used as separators inside one paragraph;
- bullet glyphs inside list text where they indicate unrepaired source fragments.

Valid cases:

- Markdown list marker `- ` is valid.
- A literal bullet glyph may be allowed only inside quoted source text if explicitly protected, but this should be rare and should require a deliberate allowlist.

Candidate metric fields:

```json
{
  "residual_bullet_glyph_count": 7,
  "residual_bullet_glyph_samples": [
    {"line": 435, "text": "- Есть некий вулкан ..."}
  ]
}
```

Candidate gate reason:

```text
residual_bullet_glyphs_present
```

### FR-4. Detect List Fragment Regressions After Translation

The final output validation must detect list marker fragmentation that survives translation.

Patterns include:

- list item ending with a dangling number marker, e.g. `... схеме: 1.`;
- a numbered list where item `1.` is embedded in a body sentence and `2.`/`3.` are separate paragraphs;
- Markdown bullet item split into two bullet items where the second item starts with a continuation phrase, e.g. `- Великой скорби.`;
- body text split before a bullet/list continuation, e.g. `с Седьмой` followed by `- Судной печатью № 1`;
- sentence ending with `6.` where the next intended item heading/body starts separately.

Candidate metrics:

```json
{
  "list_fragment_regression_count": 4,
  "list_fragment_regression_samples": [...]
}
```

Candidate gate reason:

```text
list_fragment_regressions_present
```

### FR-5. Strengthen Final Quality Report

Extend the existing final quality report to include new first-class fields that today only exist as derived grep counts:

- `false_fragment_heading_count` and samples;
- `residual_bullet_glyph_count` and samples;
- `list_fragment_regression_count` and samples;
- `suspicious_heading_repetition_count` and samples, where "suspicious repetition" is defined narrowly as the same normalized heading text appearing more than one time in the document without intervening body paragraphs distinct enough to justify a new section; this detector is a specialization of FR-1 and reuses the same inline-continuation heuristics;
- `scripture_reference_heading_count` and samples, which is a specialization of FR-1 for heading lines whose payload matches a scripture reference pattern such as `(Книга 1:1)` or `(Matthew 24:36)`;
- `theology_style_deterministic_issue_count` and samples;
- first-class `bullet_heading_count` field, promoted from the current implicit detector so that it appears in the report/summary rather than only in code;
- paragraph mapping stability fields already computed in acceptance checks, lifted to top-level: `source_paragraph_count`, `output_paragraph_count`, `worst_unmapped_source_count`.

The report must remain machine-readable and must be referenced from logs and UI result metadata, as existing quality reports are.

### FR-6. Strengthen Strict Gate Policy For PDF Structural Recovery

For `end-times-pdf-core` and similar strict PDF structural recovery profiles, acceptance must fail or warn on the combined defect set. The following table separates already-gated defects from new ones introduced by this spec, so future work does not re-implement existing behavior.

Already covered by existing gates or detectors; must remain gated and must not regress:

- TOC/body concat (see `document_pipeline_output_validation.has_toc_body_concat_markdown` and parent recovery spec);
- bullet-only headings matching `^#{1,6}\s*[●•\-*]\s*$`;
- paragraph mapping drift, currently exposed as `worst_unmapped_source_count` in acceptance checks and as paragraph count mismatch logs;
- unexplained English residuals, currently covered by `has_unexplained_english_residuals`.

New, added by this spec; must become part of the strict gate:

- false fragment headings (FR-1);
- residual bullet glyphs inside body/list text (FR-3);
- list fragment regressions after translation (FR-4);
- deterministic theology/style issues under the theology domain (FR-7).

Current `acceptance_passed=True` for the 2026-04-28 run is too weak because it does not catch the new defect set above, even though it already covers the "already covered" set.

Expected outcome after adding gate coverage but before fixing all output generation:

```text
The same 20260428-style output should fail strict quality acceptance with explicit failed checks
covering at least false_fragment_headings_present, residual_bullet_glyphs_present,
list_fragment_regressions_present and, for theology profile, theology_style_deterministic_issues_present.
```

### FR-7. Add Deterministic Domain/Style Validation For Theology Profile

Add a small deterministic validator for high-confidence theology/style issues.

Initial checks:

- inconsistent or awkward judgment-heading grammar, e.g. `Суд над пятым печатью`;
- unnatural generated headings such as `Четвёртое чашеобразное судилище`;
- mixed-script terms, where one word contains both Cyrillic and Latin letters. The current live output contains a deterministic example at `Are_We_In_The_End_Times_validated.md:691`: the token `кoinonia` starts with Cyrillic `к` (U+043A) and continues with Latin letters, which is exactly the kind of issue a deterministic detector must catch. Synthetic fixtures in FR-9 must hard-code this exact byte composition and must not depend on live regeneration;
- unresolved glossary policy terms that should be either translated or explicitly preserved consistently, e.g. `imago Dei`, `koinonia`;
- inconsistent capitalization for key terms where glossary policy requires consistency.

This validator must not try to judge all Russian prose quality. It should only catch narrow deterministic issues that are easy to explain and regression-test.

Candidate gate reason:

```text
theology_style_deterministic_issues_present
```

### FR-8. Make Full Validation Preserve Readiness/Gate Metadata

The full real-document validation report currently records empty readiness/gate fields in `preparation_diagnostic_snapshot`, while the structural diagnostic reports `ready` and `pass`.

Required behavior:

- Full validation report must preserve or infer `readiness_status` and `quality_gate_status` consistently with preparation/structural diagnostic.
- If these statuses are unavailable, report should use explicit `unknown`, not empty string.
- Tests must cover this so future reports do not silently lose readiness metadata.

### FR-9. Add Regression Fixture From The 2026-04-28 Output

Create deterministic unit fixtures based on the observed bad snippets, not on the whole live PDF.

Fixtures must be deterministic and must not depend on live regeneration of `Are_We_In_The_End_Times.pdf`. The fixture payloads must be hard-coded in the test files, including exact byte composition for mixed-script cases such as `кoinonia` where the leading `к` is Cyrillic U+043A.

Fixtures must include:

- inline `начертание зверя` promoted to heading inside a sentence, with previous paragraph ending on `является ли` and next paragraph starting on lowercase;
- scripture reference promoted to heading, e.g. `## (Матфея 24:36)` followed by body continuation;
- dangling `Спутники? Ракеты?)` heading;
- residual bullet glyph inside body/list text (e.g. `технологическими ● достижениями`);
- split `- Великой скорби.` list continuation immediately after `- Сторонники мидтрибулационного взгляда ... в середине`;
- body-to-bullet continuation where the second line starts uppercase, e.g. `с Седьмой` followed by `- Судной печатью № 1`;
- mixed-script `кoinonia` with the exact Cyrillic-`к` plus Latin-`oinonia` composition;
- awkward judgment heading grammar such as `Суд над пятым печатью` and `Четвёртое чашеобразное судилище`.

Do not rely only on live `Are_We_In_The_End_Times.pdf` to test these defects.

### FR-10. Keep Existing Improvements Stable

The hardening must not regress already fixed behavior:

- bounded TOC reconstruction;
- no TOC/body/epigraph first-block concat;
- no bullet-only headings;
- paragraph count preservation;
- DOCX openability;
- generic DOCX safety for non-PDF documents.

## Proposed Implementation Areas

Inspect/change likely files:

- `document_pipeline_output_validation.py`
- `document_pipeline_late_phases.py`
- `real_document_validation_structural.py`
- `tests/test_document_pipeline_output_validation.py`
- `tests/test_document_pipeline.py`
- `tests/test_real_document_validation_corpus.py`
- `tests/test_document_structure_repair.py`
- `preparation.py`, only if source-side false heading prevention belongs before semantic block construction
- `document_structure_repair.py`, only for source-side fragment demotion/guarding
- `translation_domains.py` or prompt/domain files, only for deterministic theology style/glossary policy if already used there

Avoid changes to:

- `document_extraction.py` unless a source-side bug is proven there and cannot be handled in repair/validation.
- `formatting_transfer.py` unless output DOCX formatting mapping is directly involved.
- Core PDF normalization in `processing_runtime.py`; PDF ingestion is not the issue in this pass.

## Acceptance Criteria

### AC-1. False Fragment Headings Detected

A synthetic Markdown/output fixture containing these headings must fail strict quality validation:

```markdown
Является ли

## начертание зверя

на самом деле — квантовая технология?

## (Матфея 24:36)

Христос вернётся как вор в ночи.
```

Expected failed checks include `false_fragment_headings_present` or more specific reason names.

### AC-2. Legitimate Headings Preserved

A fixture with `## Начертание зверя` at a true section boundary must not be flagged as a false fragment heading.

### AC-3. Residual Bullet Glyphs Detected

A fixture containing `●` inside body/list text must fail strict output quality validation with `residual_bullet_glyphs_present`.

### AC-4. List Fragment Regressions Detected

A fixture with split list continuation, dangling `1.`, or body-to-bullet continuation must fail strict output validation with `list_fragment_regressions_present`.

### AC-5. Theology Style Deterministic Issues Detected

A fixture containing `Суд над пятым печатью`, `Четвёртое чашеобразное судилище`, or `кoinonia` must produce deterministic style issue samples under theology profile validation.

### AC-6. Full Quality Report Exposes New Metrics

The final quality report includes at least:

```json
{
  "false_fragment_heading_count": 0,
  "residual_bullet_glyph_count": 0,
  "list_fragment_regression_count": 0,
  "theology_style_deterministic_issue_count": 0
}
```

and non-empty sample arrays when counts are positive.

### AC-7. End-Times Current Output No Longer Passes Silently

Before fixing generation/repair, the existing 2026-04-28-style bad snippets must be enough to fail or warn strict PDF quality acceptance.

After fixing generation/repair, a new canonical run must satisfy:

```text
bullet_heading_count == 0
false_fragment_heading_count == 0
residual_bullet_glyph_count == 0
list_fragment_regression_count == 0
toc_body_concat_detected == false
source_paragraph_count == output_paragraph_count
worst_unmapped_source_count == 0
```

Note: the paragraph-mapping constraint is expressed via `source_paragraph_count == output_paragraph_count` and the existing `worst_unmapped_source_count` acceptance field rather than a new `unmapped_source_count` metric, because the current report exposes mapping drift through these two fields and `output_artifacts.output_paragraphs`.

Verified current status after the first hardening slice:

- satisfied for the "must fail or warn explicitly" part;
- not yet satisfied for the "after fixing generation/repair" zero-defect target;
- current rerun fails with explicit machine-readable reasons instead of silent `acceptance_passed=True`.

### AC-8. Full Validation Readiness Metadata Is Not Empty

Full real-document validation report for `end-times-pdf-core` must not emit empty-string readiness/gate status. It must emit `ready`/`pass` or an explicit `unknown` with reason.

Verified current status after the final 2026-04-28 rerun: satisfied. The fresh report now emits `readiness_status=ready` and `quality_gate_status=pass` in the full-report path for the same profile.

### AC-9. Canonical Real-Document Verification

Run canonical WSL validation:

```bash
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
DOCXAI_REAL_DOCUMENT_PROFILE=end-times-pdf-core DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-pdf-structural-recovery bash scripts/run-real-document-validation.sh
```

The result should either:

- pass with no remaining strict defects; or
- fail/warn with explicit machine-readable reasons matching the remaining defects.

Silent `acceptance_passed=True` with visible false headings/bullet glyph/list fragments is not acceptable.

Verified current status after the 2026-04-28 rerun: satisfied for the explicit-failure branch. The canonical full run now fails with `false_fragment_headings_present`, `residual_bullet_glyphs_present`, `list_fragment_regressions_present`, and `theology_style_deterministic_issues_present` instead of passing silently.

Additional acceptance/artifact note from the final rerun:

- `output_docx_openable=True` and `docx_path` points to a saved DOCX artifact even though the run correctly fails on strict residual-quality reasons.

This means the remaining work is now the content-quality repair itself, not the surrounding validation/reporting contract.

## Minimal Test Matrix

Run targeted tests through canonical WSL entrypoint:

```bash
bash scripts/test.sh tests/test_document_pipeline_output_validation.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_corpus_structural_passthrough -vv -x
bash scripts/test.sh tests/test_document_structure_repair.py -q
```

If source-side heading demotion/repair changes `preparation.py` or `document_structure_repair.py`, also run:

```bash
bash scripts/test.sh tests/test_preparation.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
```

For real validation:

```bash
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery
DOCXAI_REAL_DOCUMENT_PROFILE=end-times-pdf-core DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-pdf-structural-recovery bash scripts/run-real-document-validation.sh
```

## Development Plan

### Step 1. Add Output Detectors

Implement pure deterministic helpers for:

- false fragment headings;
- residual bullet glyphs;
- list fragment regressions;
- theology deterministic style issues.

Keep helpers independent and unit-testable.

### Step 2. Wire Detectors Into Final Quality Report

Add metrics and samples to the existing final quality report payload.

Strict translate profiles should convert positive counts into gate reasons.

### Step 3. Add Synthetic Regression Tests

Create small Markdown fixtures derived from the observed bad snippets.

Tests should fail on current behavior before implementation and pass after implementation.

### Step 4. Fix Source-Side Repair Only Where Evidence Supports It

If output detectors show source structure is already wrong before LLM, add narrow source-side guards:

- do not promote scripture reference fragments;
- do not promote inline term fragments when previous/next context forms a sentence;
- do not treat dangling question fragments as headings.

Verified remaining subtask after the 2026-04-29 review:

- do not split a body sentence at an inline TOC title anchor when the prefix ends in a deterministic continuation phrase and the suffix starts like sentence continuation.

Do not add broad heading demotion rules without fixtures.

### Step 5. Re-run End-Times Validation

Run the real PDF again.

If the generated output still has defects, it must no longer pass silently; the quality report must state the defects.

## Done Criteria

This pass is complete when:

- false fragment headings are detected and gated;
- residual bullet glyphs are detected and gated;
- list fragment regressions are detected and gated;
- deterministic theology/style issues are surfaced;
- full validation readiness/gate metadata is non-empty or explicitly unknown;
- synthetic fixtures cover the 2026-04-28 observed defects;
- `end-times-pdf-core` canonical validation either passes genuinely or fails/warns with explicit machine-readable reasons;
- when canonical full validation fails on strict quality gate reasons, it still preserves enough result metadata and artifact behavior to avoid regressing into `output_docx_openable=False` purely as a side effect of the gate itself;
- no new PDF-specific internal document model is introduced.
