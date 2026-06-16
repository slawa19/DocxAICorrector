# Global Plan — Book Translation Pipeline

Date: 2026-06-16
Status: Active. Single forward reference for the pipeline.
Supersedes (for forward work): the planning docs now archived under
`docs/archive/specs/` (roadmap, MVP spec/backlog, reader-cleanup experiments,
PDF-import pivot, structure-recognition migration). Those remain as lineage only.

Active companions:
- `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` — the first
  UI slice (how residual discrepancies reach the user).

## Product Goal

Translate **full books** (PDF -> translated DOCX) preserving formatting, images,
structure, and reading quality, at book scale, on a stream of different books —
not one perfected excerpt. Gemini is the translation baseline; advanced models do
reader cleanup where judgement helps.

## Where We Are (2026-06-16)

Working and validated on two full, dissimilar books (Lietaer Rethinking Money,
Mazzucato The Value of Everything — PDF):

- **PDF text-layer import** is the chosen source path; images preserved (12/12,
  42/42, 55/55 across runs).
- **Translation** (Gemini) + **reader cleanup** (AI-first, PR-H0 readable-draft
  boundary) run at book scale.
- **Formatting preservation** is solved at the contract level: the acceptance
  gate is **role-aware coverage** (a heading/list/caption that loses its role
  counts; body legitimately reshaped by translation is credited with evidence),
  computed in shared code consumed by both production validation and the proof
  harness. The matcher **generalises**: Mazzucato maps 1075/1140 with
  `bad_pair_count=0` and role-aware basis on source and target.
- **Reliability**: a full book now completes end to end. Two abort causes are
  fixed — progress-write permission (atomic temp in the run dir) and
  `english_residual_output`/`empty_response` (controlled per-block fallback that
  surfaces the bad block and continues instead of crashing the run).
- **Stale gates**: three document-specific legacy heuristics were narrowed to
  unit-aware rules (`false_fragment_headings`, `list_fragment_regressions`,
  target-side topology masking) — classify-then-narrow, never blanket-zero.

Net: we moved from "formatting is lost" to "two full dissimilar books pass
through with a meaningful, audited gate."

## Remaining Work Before Returning to UI

The UI surfaces results to users, so before UI work the pipeline must (a) reliably
finish **any** book, (b) produce a **stable, meaningful** verdict, (c) in
**production**, not just the harness. Five items, in priority order.

### 1. Gate stability — proactive legacy-gate audit (highest leverage)

We have been narrowing stale `legacy_markdown` gates reactively, one per book.
At least four remain on that basis (`bullet_heading`, `mixed_script_term`,
`residual_bullet_glyph`, `toc_body_concat`) plus a dozen heuristic checks
(`scripture_reference_heading`, `suspicious_heading_repetition`,
`heading_body_concat`, `inline_page_furniture_leakage`,
`pdf_blank_page_marker_leakage`, …) that may fire for the first time on a new
book type. **Do:** audit these, narrow each to unit-aware evidence or mark it
explicitly tolerant — proactively, so new books stop surfacing fresh red
heuristics. **Why before UI:** a noisy gate makes the UI show false failures the
user cannot distinguish from real defects. **Done:** running 3 dissimilar books
surfaces no new stale-gate failure; every gate is either unit-aware or documented
as tolerant.

### 2. Reliability completeness — generalise the controlled-fallback contract

We fixed two specific block-abort causes. A robust stream needs the
controlled-fallback to be the **general contract**: any block that cannot be
cleanly produced after retries emits a visible fallback artifact and continues,
rather than aborting an expensive run. **Why before UI:** otherwise the next book
hits a new abort cause and never reaches a result to display. **Done:** a book
with several deliberately un-producible blocks finishes with a complete DOCX, and
every fallback is visible in artifacts (no silent loss).

Pre-implementation classification table:

| Block failure class | Decision | Contract |
| --- | --- | --- |
| `empty_response` / `empty_processed_block` after retry budget | `fallback_continue` | Emit a controlled-fallback block, event, and artifact; keep paragraph IDs/registry visible; final DOCX must still be produced. |
| `english_residual_output` after retry budget | `fallback_continue` | Emit a controlled-fallback block, event, and artifact; do not count it as lost formatting when the content is present, but surface it for translation review. |
| `heading_only_output`, `bullet_heading_output`, `toc_body_concat` after retry budget | `fallback_continue` | Treat as generated-output rejection only when the original block payload and paragraph IDs are intact; surface the fallback block for manual review. |
| Missing provider/client/configuration, including OpenAI image-client setup failures | `fail` | Infrastructure/configuration failure; no translation fallback may pretend the requested phase succeeded. |
| Missing source segment, missing translated segment, or `final_translated_book_incomplete` | `fail` | Assembly invariant failure; continuing would silently drop content. |
| Marker registry build failure or missing paragraph registry/anchors | `fail` | Fallback cannot be safely anchored or accounted for. |
| Invalid processing job, corrupted input block, source extraction/preparation failure | `fail` | The block substrate is not trustworthy enough to preserve. |
| User stop/cancel | `stopped` | Preserve explicit stopped state, not controlled fallback. |

Implementation rule: controlled fallback is allowed only when the original block
payload, paragraph IDs, and target/source accounting substrate are intact. Every
fallback path must emit a user-visible artifact and must be distinguishable from a
successful translation block in logs, diagnostics, and `formatting_review.txt`.

### 3. Acceptance tolerance and meaning

Exact-zero residual on a 1140-paragraph book's back matter (notes, bibliography,
controlled-fallback blocks) is neither achievable nor the right bar. **Do:**
define the product acceptance bar — a small, explicit tolerance for back-matter /
notes / fallback edge cases, and credit controlled-fallback blocks whose content
is present. **Why before UI:** otherwise acceptance is perpetually red on good
books and the UI cannot show a meaningful pass/fail. **Done:** a clean full book
passes; a book with a real structural loss (e.g. a heading rendered as body)
fails with a short, hand-checkable list.

### 4. Harness ↔ production parity

Some fixes landed in the validation harness (e.g. progress-write). The UI runs the
**production** pipeline. **Do:** verify production has the same reliability and
gate guarantees (progress/state robustness; role-aware/coverage already shared via
`validation/formatting_coverage.py`). **Why before UI:** the UI must inherit the
guarantees the proofs demonstrate, not a weaker path. **Done:** a production-path
run matches a harness proof on reliability and gate basis.

### 5. Finish the current Mazzucato tail (minor)

Confirm the `list_fragment` narrowing on the saved run offline (48 -> ~3 real
standalone continuations), and close `unmapped_target` +1 by crediting the
controlled-fallback bibliography block in target accounting. Small; part of items
2–3.

## Runs Alongside: Breadth Validation

Run 2–3 more full, dissimilar books to confirm reliability + matcher + gates hold
across types. This is validation, not a blocker; it is also what exposes the
remaining stale gates for item 1. Use small no-LLM replays for diagnostics; spend
a full-book LLM run only to confirm.

## Then: UI

Once items 1–4 are solid, return to UI. The first UI slice is already specified:
`docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` — surface the
residual to the user via the existing result-notice / activity surfaces plus a
human-readable `formatting_review.txt` next to the output DOCX. It depends on a
stable, meaningful residual, which items 1–3 deliver.

## Working Rules (carry forward — earned the hard way)

1. **Classify before you fix.** A failing gate may be a stale heuristic, not a
   real defect. Forensic first (which stage, real vs measurement), then act.
2. **Measured results, not "confirmed".** Record actual numbers from a run.
3. **No-LLM replay for the inner loop.** Full-book LLM runs only to confirm
   finished, unit-tested changes — never to iterate.
4. **Run full test files, not focused selectors.**
5. **Production and harness share logic.** No gate/credit that lives only in the
   proof runner.
6. **Never credit content-presence as format-presence**, and never credit a pair
   without text evidence (target⊆source by containment; no position-only maps).
7. **No document-specific literals; no verifier as a gate.**

## Non-Goals (defer; not blocking UI)

- Full-book cost/time optimisation (~20–35 min/run).
- Audiobook postprocess and other separate features.
- Aggressive dead-surface deletion beyond what is proven unused.

## Lineage (archived, for reference only)

- `docs/archive/specs/POST_FC_DEVELOPMENT_ROADMAP_2026-06-14.md` — WS-1..WS-5 /
  WS-MAP execution detail and forensic findings.
- `docs/archive/specs/SIMPLE_READER_FIRST_MVP_REPAIR_PR_BACKLOG_2026-05-23.md` —
  PR-H0/PR-I history.
- `docs/archive/specs/FORMATTING_COVERAGE_CONSOLIDATION_PLAN_2026-06-13.md` —
  role-aware gate / matcher consolidation (FC1–FC8).
- `docs/archive/specs/PDF_TEXT_LAYER_SOURCE_IMPORT_PIVOT_SPEC_2026-06-01.md`,
  `READER_CLEANUP_MODEL_STRATEGY_EXPERIMENTS_2026-05-30.md`,
  `SIMPLE_READER_FIRST_MVP_SPEC_2026-05-21.md`,
  `STRUCTURE_RECOGNITION_TO_READER_FIRST_MIGRATION_PLAN_2026-05-29.md`.
