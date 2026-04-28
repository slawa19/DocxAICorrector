# PDF Candidate Benchmark Specification

Date: 2026-04-28

## Problem

The current PDF import contract is intentionally narrow:

```text
PDF -> LibreOffice DOCX normalization -> existing DOCX pipeline
```

That contract is still correct for production until a better option is proven. The observed failure on `end-times-pdf-core` shows that the current pain is not generic PDF support in isolation, but structural unsafety after normalization:

- TOC/body concatenation;
- isolated list-marker fragments;
- weak heading recovery;
- unsafe first-block composition;
- preparation quality gate blocking the document before normal AI processing.

We need a small, decision-oriented benchmark for a few realistic library candidates on the known problematic PDF, not a broad PDF tooling research project and not a hidden rewrite of the application architecture.

## Goal

Build a simple benchmark harness that compares a small set of promising PDF candidates on the same problematic source document and produces side-by-side structural quality evidence.

The benchmark must answer one practical question:

```text
Is there a candidate that gives materially safer structure than the current LibreOffice path,
without forcing a premature production rewrite?
```

The benchmark must preserve one strict distinction throughout the design:

- canonical DOCX structural diagnostics for DOCX-producing candidates;
- benchmark-only structural proxy signals for non-DOCX structural extractors.

The summary must never present those two signal classes as if they were identical without explicit basis metadata.

## Non-Goals

- Do not replace the production PDF path in this pass.
- Do not add UI wiring for candidate selection.
- Do not expand to a multi-document benchmark suite yet.
- Do not add OCR or scanned-PDF handling in this pass.
- Do not design a second full production document model yet.

## Decision Boundary

This benchmark is a development aid. It is allowed to exercise candidate libraries through debug-only adapters, as long as the benchmark output is explicit about what is comparable and what is not.

Two candidate classes are acceptable:

1. Same-contract candidates that produce DOCX and can be compared more directly against the current pipeline.
2. Structural-benchmark candidates that produce structured blocks or markdown-like output and are used only to test whether the current LibreOffice-based normalization is leaving too much structure on the floor.

Only candidates that show clear value in this benchmark may justify a later production integration spec.

## Comparability Contract

The benchmark compares two different candidate classes, so the result contract must explicitly encode metric provenance.

Required distinction:

1. `docx-normalizer` candidates are evaluated through the same existing structural diagnostic code path as the LibreOffice baseline.
2. `structural-extractor` candidates are evaluated through benchmark-only block projection and heuristic structural proxy metrics.

This means that some fields cannot carry the same evidentiary weight for every candidate.

### Required Basis Fields

Each successful candidate result must expose at least these basis fields:

- `metric_basis` with values `existing_docx_diagnostics` or `benchmark_block_projection`
- `preparation_gate_basis` with values `production_docx_pipeline`, `benchmark_structural_proxy`, or `unavailable`
- `toc_body_concat_detector` with values `existing_markdown_detector`, `benchmark_block_detector`, or `unavailable`

### Preparation Gate Rule

The benchmark must not imply that non-DOCX structural extractors passed the current production preparation gate unless they actually produced DOCX and were evaluated through the same structural diagnostic path.

Required fields:

- `preparation_gate_outcome` with values `pass`, `blocked`, `error`, or `not_applicable`
- `preparation_gate_basis`

`preparation_gate_outcome = not_applicable` must never count as an improvement over a blocked production gate by itself.

## Benchmark Input

Use exactly one source document in this pass:

- `tests/sources/Are_We_In_The_End_Times.pdf`
- corpus id: `end-times-pdf-core`

Reason: this is the known regression source and already has real-document validation context, expected failure semantics, and existing structural diagnostics.

## Selected Candidates

### Baseline

- Current path: LibreOffice PDF import via `--infilter=writer_pdf_import`

Reason: baseline source of truth for current behavior.

Baseline comparison must include both:

```text
PDF -> LibreOffice normalized DOCX artifact
PDF -> LibreOffice normalized DOCX -> existing structural diagnostic result
```

Required baseline artifacts:

```text
baseline/
   normalized.docx
   structural_diagnostic.json
   recovered_preview.md or recovered_preview.txt
```

### Candidate A. `pdf2docx`

Class: same-contract candidate.

Why it is included:

- closest conceptual replacement for the current PDF -> DOCX step;
- cheap to compare because it stays inside the DOCX-centric contract;
- answers whether a different converter alone materially improves structure.

### Candidate B. `docling`

Class: structural-benchmark candidate.

Why it is included:

- high potential for layout-aware structured extraction;
- more likely than converter-only tools to recover headings, list items, and document sections;
- useful even if not production-ready, because it tests the ceiling of better structural extraction on the same source.

### Candidate C. `PyMuPDF` plus a minimal block adapter

Class: structural-benchmark candidate.

Why it is included:

- practical low-level control over text blocks, reading order, and page coordinates;
- lower integration risk than a large framework because the benchmark adapter can stay small;
- useful as a fallback signal if `docling` is too opinionated or too heavy.

The initial adapter must stay minimal: block extraction, reading-order flattening, and simple block-to-paragraph projection only. It must not grow into a second production pipeline during this pass.

Additional guardrail:

```text
The PyMuPDF adapter must not infer semantic hierarchy beyond simple heading/list heuristics used for benchmark scoring.
```

## Explicitly Deferred Candidates

These are intentionally out of scope for the first benchmark pass:

- `unstructured`: overlaps with `docling` as a higher-level structural extractor; defer until one such framework proves necessary.
- `pdfplumber` as a standalone candidate: valuable as a helper, but too low-level to justify a separate first-pass benchmark track.
- OCR stacks such as `ocrmypdf` or `tesseract`: this source is not being evaluated as a scanned-PDF problem.

## Proposed Harness Shape

Keep the harness narrow and reversible.

### Files

Add a small benchmark slice under a dedicated development surface, for example:

- `scripts/run-pdf-candidate-benchmark.sh`
- `tests/artifacts/pdf_candidate_benchmark/<run_id>/`
- one focused Python module for adapters and score aggregation
- one focused test file for scorecard logic and adapter contract checks

Latest-alias pattern is allowed, for example:

- `tests/artifacts/pdf_candidate_benchmark/latest_summary.json`
- `tests/artifacts/pdf_candidate_benchmark/latest_manifest.json`

Avoid touching the production upload/runtime/UI path in this pass.

### Canonical DOCX Diagnostic Path

For LibreOffice baseline and any other DOCX-producing candidate such as `pdf2docx`, evaluation must use the same structural diagnostic code path as the current DOCX-based structural workflow.

Preferred contract:

- same underlying code path used by `real_document_validation_structural.py`
- same structural preparation diagnostic semantics already used for `end-times-pdf-core`

If a DOCX-producing candidate cannot be evaluated through that same code path, the result must be marked:

```text
status=ok
diagnostic_mode=debug-only
metric_basis=existing_docx_diagnostics
preparation_gate_basis=unavailable
```

and the summary must explicitly state that the result is non-canonical.

The benchmark should prefer the existing structural diagnostic entrypoint contract represented by `scripts/run-structural-preparation-diagnostic.sh` and its underlying `real_document_validation_structural.py` flow over ad-hoc duplicate scoring logic.

### Dependency Policy

Candidate dependencies are benchmark-only dependencies in this pass.

Allowed implementation patterns:

- optional benchmark requirements file such as `requirements-pdf-benchmark.txt`; or
- equivalent optional dependency mechanism kept outside required production runtime dependencies.

Missing optional dependencies must produce `status = unsupported` with a clear note and must not fail the benchmark run.

### Run Manifest

Each benchmark run must emit a manifest with at least:

- `benchmark_run_id`
- `source_pdf_path`
- `source_pdf_sha256`
- `created_at`
- `candidates_requested`
- `candidates_completed`
- `candidates_unsupported`
- `thresholds`
- `artifact_root`

### Candidate Adapter Contract

Each candidate adapter must return a normalized benchmark result object with these fields:

- `candidate_id`
- `candidate_version`
- `execution_class` with values `docx-normalizer` or `structural-extractor`
- `status` with values `ok`, `error`, or `unsupported`
- `dependency_status`
- `runtime_platform`
- `duration_seconds`
- `diagnostic_mode` with values `canonical`, `debug-only`, or `benchmark-only`
- `metric_basis`
- `preparation_gate_basis`
- `artifact_paths`
- `visible_text_chars`
- `paragraph_count`
- `heading_candidates_count`
- `list_item_candidates_count`
- `toc_like_block_count`
- `preparation_gate_outcome`
- `failed_checks`
- `toc_body_concat_detected`
- `toc_body_concat_detector`
- `first_block_risk`
- `first_block_risk_reasons`
- `first_block_preview`
- `notes`

### Candidate-Specific Outputs

For `docx-normalizer` candidates:

- emit DOCX artifact;
- run the existing structural diagnostic code path on that DOCX;
- reuse current metrics where possible instead of inventing a parallel metrics system.

Required outputs:

- normalized DOCX artifact;
- structural diagnostic JSON;
- recovered preview text or markdown.

For `structural-extractor` candidates:

- emit JSON snapshot of recovered blocks;
- emit plain text or markdown projection for human review;
- compute a minimal comparable scorecard from recovered blocks.

Required constraints:

- no fake production gate result may be inferred;
- missing optional dependencies must produce `unsupported` results and must not fail the benchmark run;
- the benchmark block detector set must stay simple, documented, and covered by focused tests.

The first pass must not require a perfect DOCX writer for non-DOCX candidates.

## Threshold Constants

The benchmark contract should expose explicit threshold names in code and in the run manifest.

Initial constants:

```text
MEANINGFUL_RELATIVE_IMPROVEMENT = 0.20
MIN_VISIBLE_TEXT_CHAR_RATIO_VS_BASELINE = 0.90
```

Additional thresholds may be added only if they are necessary to make a comparison deterministic and testable.

## Scorecard

The benchmark must produce a side-by-side summary for all candidates using the same source PDF.

### Required Metrics

1. `preparation_gate_outcome`
2. `preparation_gate_basis`
3. `failed_checks`
4. `visible_text_chars`
5. `paragraph_count`
6. `isolated_marker_paragraph_count`
7. `toc_body_concat_detected`
8. `toc_body_concat_detector`
9. `heading_like_block_count`
10. `toc_like_block_count`
11. `first_block_risk`
12. `first_block_risk_reasons`
13. `notes`

Every candidate summary entry must also expose either per-metric provenance or one candidate-level provenance field set that makes the basis of those metrics explicit.

Minimum acceptable form:

- candidate-level `metric_basis`
- candidate-level `preparation_gate_basis`
- candidate-level `toc_body_concat_detector`

Preferred form for future extension:

```json
{
   "paragraph_count": 123,
   "paragraph_count_basis": "docx_extraction"
}
```

### Content Survival Metrics

The scorecard must include a simple first-pass content survival section so that candidates are not judged only by structural heuristics.

Required fields:

- `visible_text_chars`
- `normalized_text_similarity_to_baseline`
- `first_20_blocks_have_nonempty_text`

For structural extractors, `normalized_text_similarity_to_baseline` may be debug-only and computed from a plain text projection, but its basis must be documented.

### First Block Risk

`first_block_risk` must not be a free-form judgment.

Required shape:

- `first_block_risk` with values `low`, `medium`, `high`, or `unknown`
- `first_block_risk_reasons` as a list

Risk reasons should map to already known signals when available, for example:

- `first_block_has_toc`
- `first_block_has_epigraph`
- `first_block_has_body_start`
- `first_block_has_isolated_marker`
- `first_block_target_chars_large`

### Human Review Snapshot

For each candidate, store a short diagnostic preview containing:

- first 20 recovered paragraphs or blocks;
- first detected TOC region, if any;
- first 10 heading-like entries;
- first 10 list-marker fragments;
- first block preview.

This is needed because purely numeric metrics can miss obvious reading-order failures.

## Comparison Method

The benchmark decision must follow this order:

1. Can the candidate run reliably on the source PDF and produce usable artifacts?
2. Does it reduce structural failure signals versus LibreOffice baseline?
3. Does it do so without obvious reading-order collapse or content loss?

The benchmark should prefer structural evidence over subjective text quality judgments. Translation quality is explicitly out of scope for this comparison pass.

When a candidate uses `benchmark_block_projection` instead of `existing_docx_diagnostics`, the summary must state that the comparison is informative but not fully canonical relative to the production DOCX preparation gate.

## Acceptance Criteria For The Benchmark Itself

The benchmark implementation is accepted when all of the following are true:

1. A single canonical benchmark entrypoint runs the baseline and all selected candidates against `end-times-pdf-core`.
2. The run writes a machine-readable summary, run manifest, and per-candidate artifacts under `tests/artifacts/pdf_candidate_benchmark/<run_id>/`.
3. The summary clearly distinguishes `docx-normalizer` candidates from `structural-extractor` candidates.
4. The summary includes the required metrics for every candidate that completed successfully.
5. Adapter failures are reported as benchmark results, not as benchmark crashes.
6. DOCX-normalizer candidates are evaluated through the same existing structural diagnostic code path as the LibreOffice baseline, or the summary marks them as debug-only and non-canonical.
7. The harness does not alter the production app import path, corpus registry defaults, or UI behavior.
8. Missing optional candidate dependencies produce `unsupported` results and do not fail the benchmark run.
9. The benchmark is invalid without the LibreOffice baseline result, because candidate comparisons are baseline-relative.

## Acceptance Criteria For Calling A Candidate Promising

A candidate is considered promising only if all of the following are true on the benchmark source:

1. It completes successfully and produces reviewable artifacts.
2. It is not worse than the LibreOffice baseline on obvious content survival, based on `visible_text_chars`, preview inspection, and the configured minimum visible-text ratio versus baseline.
3. It shows at least one material structural improvement over baseline in a high-value signal:
   - `preparation_gate_outcome` improves from blocked to pass when both sides use `production_docx_pipeline`; or
   - `toc_body_concat_detected` improves from true to false; or
   - `isolated_marker_paragraph_count` drops meaningfully; or
   - heading/list recovery is visibly better in the stored preview and summary.
4. It does not introduce an obvious reading-order collapse in the first 20 recovered blocks.
5. A `not_applicable` preparation gate result from a structural extractor does not count as a gate improvement by itself.

For this pass, "meaningfully" should be implemented against explicit threshold constants such as `MEANINGFUL_RELATIVE_IMPROVEMENT` or a clear boolean improvement on a binary risk signal.

## Acceptance Criteria For Recommending A Follow-Up Integration Spec

A follow-up production-integration spec is justified only if at least one candidate is promising and one of these conditions is true:

1. `pdf2docx` materially outperforms LibreOffice, suggesting a converter swap or fallback is plausible within the existing architecture.
2. `docling` or `PyMuPDF` materially outperforms LibreOffice, suggesting the current architecture may need an explicitly scoped alternative ingestion path.

If no candidate clears the promising threshold, the benchmark is still successful if it produces enough evidence to stop speculative library switching and refocus on generic repair/readiness inside the current contract.

## Recommended Implementation Sequence

1. Implement the baseline runner and summary writer first.
2. Add `pdf2docx` adapter next, because it is the closest same-contract comparison.
3. Add `docling` adapter third, because it tests the strongest alternative structural extractor.
4. Add the minimal `PyMuPDF` adapter last, keeping it deliberately small.
5. Add one focused test file that validates summary generation, adapter status handling, and threshold logic.

## Summary Shape

The machine-readable summary should look like a benchmark run artifact rather than a flat dump of mixed metrics.

Recommended shape:

```json
{
   "benchmark_run_id": "20260428-114800",
   "source": {
      "document_profile_id": "end-times-pdf-core",
      "path": "tests/sources/Are_We_In_The_End_Times.pdf",
      "sha256": "..."
   },
   "thresholds": {
      "meaningful_relative_improvement": 0.2,
      "min_visible_text_char_ratio_vs_baseline": 0.9
   },
   "candidates": [
      {
         "candidate_id": "libreoffice",
         "execution_class": "docx-normalizer",
         "status": "ok",
         "metric_basis": "existing_docx_diagnostics",
         "preparation_gate_outcome": "blocked",
         "preparation_gate_basis": "production_docx_pipeline",
         "failed_checks": ["preparation_quality_gate_blocked"],
         "paragraph_count": 0,
         "visible_text_chars": 0,
         "toc_body_concat_detected": true,
         "toc_body_concat_detector": "existing_markdown_detector",
         "first_block_risk": "high",
         "first_block_risk_reasons": ["first_block_has_isolated_marker"],
         "artifact_paths": []
      }
   ],
   "recommendation": {
      "outcome": "keep_libreoffice_and_continue_structural_repair_work",
      "promising_candidates": [],
      "notes": []
   }
}
```

## Risks And Guardrails

- Do not let the `PyMuPDF` adapter grow into a production pipeline by accident.
- Do not require every candidate to emit DOCX in the first pass.
- Do not interpret better extracted text as proof of better end-to-end translation quality.
- Do not widen the benchmark to multiple PDFs before the single-document decision is clear.
- Do not silently substitute benchmark output for canonical real-document validation output.
- Do not present benchmark-block detector results as equivalent to the current production preparation gate.
- Do not mix stale artifacts from previous runs into the current scorecard; artifact directories must be run-scoped or explicitly cleaned.

## Test Requirements

The first implementation should include focused tests for:

1. adapter failure isolation, including missing optional dependencies producing `status = unsupported`;
2. scorecard basis metadata, including `execution_class`, `metric_basis`, and `preparation_gate_basis`;
3. promising-threshold logic for boolean improvements and relative-improvement thresholds;
4. baseline-presence validation, because comparisons are baseline-relative;
5. no production-path mutation, at least at a narrow contract level.

## Deliverables

The implementation guided by this spec should produce:

- one canonical benchmark command;
- one benchmark run manifest with source hash, candidate versions, and threshold values;
- one machine-readable summary artifact;
- one per-candidate artifact folder;
- one short human-readable comparison report;
- one recommendation section in the final developer-facing output stating one of:
  - keep LibreOffice and continue structural repair work;
  - investigate converter swap candidate;
  - write a separate integration spec for an alternative structural extraction path.