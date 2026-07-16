# Feature Specification: Decompose pipeline/output_validation.py (behaviour-preserving)

Date: 2026-07-16
Status: **PLANNED (Wave 3 / decomposition, module 5 of 5 — final).** Pure structural refactor of the ~2453-line
`pipeline/output_validation.py`: isolate the two self-contained satellite clusters and pin the interwoven core behind
a golden. No behaviour change.
Owner surface: `pipeline/output_validation.py`, new `pipeline/paragraph_break_detection.py` +
`pipeline/toc_block_validation.py`, and a new characterization test.

## Problem + favourable facts (verified) — and an honest scope note

Unlike the prior four modules, this one is **core-dominated**: a ~1800-line tightly-recursive engine (markdown line
primitives + final-markdown assembly + heading-fragment detectors + the `collect_*`/`normalize_*` families, all sharing
an `_entry_*`/heading-helper web) plus three thin tail satellites. **Splitting the core would force a dense
function-local-import mesh or a genuine cycle for near-zero cohesion gain** — higher risk than the lines are worth. So
the safe, honest win is: extract the two cleanest satellites (paragraph-break detection, TOC-block validation), pin the
core behind a characterization golden, and STOP. Realistic reduction ~2453 → ~2150.

Verified favourable facts:
- **ZERO monkeypatch sites** against `output_validation` (multi-line + string-form checked) — every consumer is a
  read/call through a module alias, so a comprehensive re-export shim covers everything: **situation-1 everywhere, no
  repoints**. Lowest-risk of the five.
- **No module-level mutable state / caches / singletons.** Pure CPU / fully offline (only imports re/collections/
  dataclasses/typing + the pure `resolve_main_content_scope`).
- Heavy consumers (via re-export): `quality_gate.py` (12 symbols), `runtime_display_markdown.py` (6 normalizers),
  `structural_checks.py` (7 collectors), `late_phases.py` (2), `block_execution.py` (`validate_translated_toc_block`),
  `_pipeline.py` (`classify_processed_block`), plus 3 whole-module test aliases that read some **private** names
  (`_is_page_reference_like`, `_has_page_reference_suffix`, `_is_substantive_toc_line`,
  `_is_allowlisted_unchanged_toc_line`) — the shim MUST re-export those privates.

## Scope — staged

**Step 0** — characterization golden `tests/test_output_validation_characterization.py` (offline, no fixtures): snapshot
`assemble_final_markdown` (full `FinalMarkdownAssemblyResult`) over 3-4 triples, all 9 `collect_*`, all 7 `normalize_*`,
`validate_translated_toc_block` (each reason), `classify_processed_block` (each status), and the 4 private-via-alias TOC
pins. `UPDATE_*=1` regen. Commit — the core's safety net.

**Step 1** — extract `pipeline/paragraph_break_detection.py` (the cleanest leaf): `ParagraphBreakSample`,
`_PARAGRAPH_BREAK_*` constants, the `_paragraph_break_*` helpers, `collect_paragraph_break_samples`. Its only shared
primitive `_SENTENCE_TERMINAL_PATTERN` stays in the original → function-local import inside the one helper that needs
it (avoid relocating a widely-shared constant). `resolve_main_content_scope` imported directly from
`validation.formatting_coverage`. Re-export into the original.

**Step 2** — extract `pipeline/toc_block_validation.py`: `TocValidationResult`, the TOC constants,
`_normalize_toc_comparison_text`, `_is_page_reference_like`, `_is_allowlisted_acronym_or_label_line`,
`_is_allowlisted_unchanged_toc_line`, `_is_substantive_toc_line`, `validate_translated_toc_block`. Shared primitives
(`_split_markdown_paragraphs`, `_has_page_reference_suffix`, `DISALLOWED_GENERIC_TOC_LABELS`) STAY in the original →
function-local imports inside the TOC functions. Re-export into the original — **including the 4 private names the tests
read by alias**.

**Step 3 (OPTIONAL — recommend SKIP)** — `pipeline/processed_block_classification.py` (cluster B). More shared leakage
(a longer function-local import list) for a ~60-line gain; only do it if further reduction is mandated. Do NOT split
the primitives (A) or the C+D assembly/collector/normalizer core.

## Test plan (every step)

`tests/test_output_validation_characterization.py` (byte-identical each step), `tests/test_document_pipeline_output_validation.py`
(the near-exhaustive suite), `tests/test_document_pipeline.py`, `tests/test_late_phases_characterization.py`,
`tests/test_real_document_pipeline_validation.py`, `tests/test_script_contract_static.py`. Import smoke: `quality_gate`,
`runtime_display_markdown`, `structural_checks`, `block_execution`, `_pipeline` resolve; both entry orders no cycle;
the 4 private-via-alias TOC names resolve on `output_validation`.

## Out of scope

- Behaviour changes; splitting the interwoven core; the optional Step 3 unless mandated.

## SaaS rationale

Neutral; isolating the self-contained validation satellites and golden-pinning the core improves testability without
risking the correctness-dense assembly engine.
