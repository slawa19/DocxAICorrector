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

The severity model for the legacy-hygiene gates currently lives as hand-copied
code blocks (see *Architecture Hygiene* below); extracting it into a single
table makes this audit a glance over data rather than a reverse-engineering of
five near-identical branches. Do that extraction as part of this item.

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
books and the UI cannot show a meaningful pass/fail. The verdict must be
format-aware **and** flagging-untranslated: a structural element whose formatting
survives but whose text remains in the source language (for example an English
heading in a Russian translation) must surface for review instead of silently
passing as role-aware coverage. Large body-text regions left in the source
language are a translation-completeness failure, not a formatting warning. Profiles
must also use finite acceptance thresholds; sentinel/vacuum thresholds are
provisional/fail and must not report `acceptance_passed=true`. **Done:** a clean
full book passes; a book with a real structural loss (e.g. a heading rendered as
body) fails with a short, hand-checkable list; untranslated structural
headings/captions produce a visible review item; large untranslated body residue
hard-fails.

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

## Runs Alongside: Architecture Hygiene (secondary, opportunistic)

Secondary to the five items, but tracked so it is not lost. The constraint:
decompose **only inside an iteration that is already editing the code in
question** for a functional reason — never as a standalone "big refactor" that
displaces the main task (book reliability). Every change is behaviour-preserving:
full test files green before and after.

Findings (measured 2026-06-16):

- `src/docxaicorrector/pipeline/late_phases.py` is a **3871-line** module.
  `_build_translation_quality_report` alone is **474 lines** and is edited on
  nearly every gate iteration — it grows by accretion.
- The five legacy-hygiene gates inside it (`bullet_heading`, `false_fragment`,
  `residual_bullet`, `mixed_script`, and the near-identical `role_loss`) repeat
  one hand-copied block: classify via `_apply_manual_review_or_fail` → serialize
  samples → loop-append `_build_formatting_review_item` → set `count=0`/
  `aggregate_count` on the first item when samples are capped. The same
  capping/aggregate invariant is duplicated a sixth time in
  `runtime/artifacts.py`. This duplication is the **source of the report ↔
  `formatting_review.txt` divergence bugs** fixed across the last iterations: any
  rule change must be re-applied in six places or the totals drift.

Task A — **extract `_emit_hygiene_gate`** (do within item 1, while these blocks
are open). One helper encapsulates classify + status update + capped-sample
emission + `aggregate_count`. Each of the five gates collapses to a single call;
the severity model (`reason_review`, `reason_fail`, threshold per gate) becomes a
table — single-sourced, directly serving the item-1 audit. The capping invariant
lives in one place; `runtime/artifacts.py` stays a pure consumer of
`aggregate_count`, not a second implementation. **Done:** five blocks become five
calls; no behaviour change; the six duplicate count/aggregate sites become one.

Task B — **split the quality-report cluster** out of `late_phases.py` into
`pipeline/quality_report.py` (`_build_translation_quality_report`,
`_derive_translation_quality_authority_fields`, the severity table, review-item
rendering). Larger move; **deferred** — do it opportunistically when that cluster
is next open for a functional change, not for its own sake, and not while item 2
(controlled-fallback) is the active priority.

## PDF Source Conversion — heading-detection gap & converter alternatives

Findings (measured 2026-06-18, manual review of produced DOCX vs FineReader
references in `tests/sources/book/*.docx`; experiment artifacts under
`.run/layout_parser_experiment/` and `.run/current_conversion_check/`).

**Paragraph segmentation is solved; do not swap the importer.** The earlier
catastrophe (epub→pdf Creating Wealth produced 19,557-char concatenated blobs and
~12% untranslated body) was rooted in `build_paragraph_units_from_text_spans`,
not the DOCX writer. The first-line-indent fix brought all three books to near the
FineReader reference: % of text in oversized (>2000) blocks is 1.8% (Creating
Wealth) / 0.0% / 0.0%, with text fidelity 0.99–1.0 and images preserved (34–62).
A rigorous re-bench (`measure_v2.py`, severity-aware metric `pct_chars_in_gt2000`)
confirmed no tested OSS parser beats it: Docling 66.9% in giants + 0.76 fidelity
(its default OCR path mangles a digital PDF), PyMuPDF blocks 2.2% but no roles,
pymupdf4llm 39.7% + 237 spurious headings + 8% text loss, Marker timed out.

**Converter alternatives — brief verdict.** The 2025–2026 frontier (MinerU,
olmOCR, dots.mocr, Qwen-VL-class) is VLM-based, optimised for *scanned/complex*
documents (tables, formulas, multilingual) at GPU cost and with text-fidelity
risk. Our books are *clean digital PDFs* where the only hard part is structure, so
these are overkill and a fidelity downgrade now. Keep them in reserve: MinerU for
future complex tables; olmOCR/dots.mocr only if scanned books (no text layer)
appear. FineReader-class quality is real, but FineReader's own DOCX export drops
all images (0 vs our 34–62).

**Open defect — heading/subheading detection (metrics hid it).** Manual DOCX
comparison against the FineReader references shows `current` flattens section
*subheadings* into body: Mazzucato detects **19** headings vs FineReader's **75**;
Rethinking Money **62** vs **129** — roughly half to two-thirds of real
subheadings lost. Root cause: `_looks_like_heading_candidate` keys on font *size*,
so small-caps subheadings at body size (e.g. "THE MERCANTILISTS: TRADE AND
TREASURE", "GDP: A SOCIAL CONVENTION") slip through. The same root produces
Creating Wealth's 3 residual >2000 blocks: inline list subheadings
(`Employment / Education / Child Care`, `Paper and Coins / Electronic Media`) the
detector misses and therefore merges. No experiment metric caught this —
`heading_count` alone looked fine; only heading **recall vs the FineReader
ground-truth** exposes it. **Do:** strengthen heading detection in
`logical_import.py` with case/style cues (all-caps/small-caps, standalone short
line, indentation), not size alone; measure heading-recall against the three
FineReader references and confirm by hand that subheadings stop leaking into body
and the Creating Wealth lists split. **Why before UI:** lost section hierarchy is
a visible formatting-preservation failure in the very output the UI surfaces.

## Generalization of structure detection (self-calibration over heuristics)

Empirical trigger (2026-06-18): heading detection hit the heuristic ceiling. After
suppressing dash-attribution / FIGURE-caption / location-byline false positives,
Creating Wealth precision-vs-FineReader moved only 0.083→0.091. Manual review of the
220 predicted headings shows why: (a) most ARE real subheadings the coarse FineReader
Creating Wealth export (23 labels, vs 75/129 for Mazzucato/Rethinking) simply omitted
— so that precision number is mostly a weak-reference artifact, not over-detection;
(b) the genuine residual false positives are all-caps epigraph **author names**
("VIRGIL", "MARSHALL MCLUHAN", "BARTHOLD GEORG NIEBUHR") which are **typographically
identical** to real all-caps subheadings ("THE CORE ECONOMY") and separable only by
**meaning**. No typographic hand-rule can fix that tail; more rules just overfit our
three books. This is the rule against doc-specific literals (Working Rule #7) in
spirit: absolute thresholds tuned on a tiny corpus are doc-specific in disguise.

**Principle — replace accreting absolute thresholds with PER-DOCUMENT
self-calibration.** A PDF text layer has no semantic structure; inference is
unavoidable, so the question is "our general heuristics vs a learned model", and the
generalizing move is to measure each book's own typography first, then judge relative
to it:

- **Profile-first.** Measure the document's distributions (body font mode, body
  left-margin mode, body leading, line-length distribution, body case usage) before
  classifying; judge every line **relative** to that profile, never against absolute
  constants. `median_font_size` and repeated-furniture detection already do this in
  part — extend it to all features.
- **Heading levels by clustering** style-signatures (size, weight, case, isolation),
  not thresholds: largest/most-frequent cluster = body; higher clusters = heading
  levels; small/distinct = caption. Auto-discovers each book's hierarchy.
- **Paragraph boundaries:** auto-detect which convention the book uses (first-line
  indent / inter-paragraph spacing / neither) and add **line-fill ratio** (short last
  line + return to left margin) — the near-universal, indent-independent end-of-
  paragraph signal that was missing on the epub→pdf case.
- **Small, GENERAL negative-convention set only** (dash-attribution, FIGURE/TABLE,
  page furniture). Never per-book patches.
- **Intra-document consistency:** same style-signature → same role throughout; flag
  outliers.
- **Confidence-gated escalation for the ceiling.** Where a line is genuinely
  ambiguous (all-caps author-name vs all-caps subheading), do not force a typographic
  guess — decide conservatively or escalate the low-confidence minority to a
  semantic/LM check or review. ML is a fallback for the ambiguous tail, not a
  wholesale replacement; paragraph segmentation stays homegrown (faithful, cheap).

**Validation discipline (else "universal" is self-deception):**
- Tune ONE global score/clustering on a corpus; never per-book thresholds.
- Validate on **held-out** books not used for tuning (the FineReader DOCX set is a
  ground-truth corpus; keep some books validation-only).
- Success metric = the **spread** of recall/precision across books, not the average —
  stable on any book, not excellent on three.
- The FineReader references are themselves uneven (Creating Wealth 23 vs 75/129) — use
  them as a recall guide and corpus, but confirm precision by manual false-positive
  typing, not the raw score.
- **Tripwire:** the first new book needing a fresh typographic hand-rule is the signal
  the heuristic tail is exhausted and the ambiguous case belongs to the semantic/ML
  fallback.

This is a redesign of the importer's classification core; do it incrementally under
held-out validation, not as more patches.

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
