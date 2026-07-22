# Concept: Two-column PDF reading order — findings, open questions, decision plan

**Feature Branch**: `[050-two-column-pdf-reading-order]`

**Created**: 2026-07-21

**Status**: **CONCEPT — NOT A SOLUTION SPEC.** This document records what is verified, what is
merely traced from code, and what contradicts it. It exists to be argued with and then settled by
measurement. Do NOT implement anything from it until the experiment in `## Decision plan` has run.

**Date**: 2026-07-21

**Owner surface**: PDF text-layer import (reading order), text-layer quality gate

**Companion**: `docs/reviews/CODE_REVIEW_ROUND10_2026-07-20.md` (F6);
`specs/049-pdf-import-preserves-font-size/spec.md` (the cautionary precedent — a flawless code trace
that measured to zero); `docs/WORKFLOW_AND_IMAGE_MODES.md` (Upload Normalization Contract)

**Changelog**:

- 2026-07-21 — Created after the owner challenged the F6 finding with contradicting real-world
  experience ("I once translated a two-column OCR document and it came out fine").

## Why this document exists

Round-10 finding F6 claimed that two-column PDFs are silently scrambled. That claim was produced by
**reading code, not by processing a two-column file** — the corpus contains four books, all
single-column, so this class has never been exercised.

The owner then reported the opposite from practice: a two-column OCR document was translated and the
result was fine. That is empirical evidence and it outranks a code trace.

We have just been burned by exactly this asymmetry: `specs/049` was a clean, well-argued trace that
measured to zero effect and one regression. The lesson is applied here **before** any work is
proposed.

## Verified facts (read from code at `2d9d8be`, 2026-07-21)

1. **There is no column detection anywhere in the importer.** `x0` is used only to compute a single
   `body_left_x0` — the median left edge of body spans (`pdf_import/logical_import.py:624-628`) —
   and then for indent depth and "near body left" proximity (`:831-832`, `:1152-1157`). A single
   median left edge is a **single-column model** by construction.
2. **Reading order is decided by one global sort**: `sorted(spans, key=(page_number, top, x0))`
   (`pdf_import/logical_import.py:121`). On a two-column page both columns occupy the same vertical
   band, so ordering by `top` interleaves them: left-line-1, right-line-1, left-line-2, …
3. **The text-layer quality gate has no layout signal.** `pdf_import/text_layer_quality.py`
   decides on character counts, furniture ratio and structure signals; the words "column"/"gutter"
   do not appear in its decision.
4. **The LibreOffice PDF path is gone.** `processing/processing_runtime.py::_convert_pdf_to_docx_with_optional_text_layer`
   now delegates unconditionally to `_convert_pdf_text_layer_to_docx` — the "optional" in its name is
   stale. `docs/WORKFLOW_AND_IMAGE_MODES.md` records the same: LibreOffice `writer_pdf_import` "is no
   longer the runtime PDF fallback". LibreOffice's PDF import **does** perform column segmentation.
5. **The corpus cannot detect this class.** All four registry books are single-column, so every
   green real-document run says nothing about two-column behaviour.

## The contradiction, and the most likely explanation

Fact 2 predicts scrambling. The owner's experience says otherwise. The leading hypothesis reconciles
both:

> **H1 — the successful run predates the importer switch.** When LibreOffice performed the PDF
> conversion, columns were segmented by LibreOffice and reading order arrived correct. The
> deterministic text-layer importer replaced it, and with it the only component that understood
> columns. If so, this is a **regression introduced by that switch**, not a defect that always
> existed — and the owner's memory and the code trace are both right, about different versions.

A second hypothesis matters just as much, and it points at a much cheaper fix:

> **H2 — the sort is the bug, not the missing column detection.** OCR engines (ABBYY, Tesseract with
> layout analysis) linearise into reading order themselves, and many born-digital PDFs emit column
> content sequentially too. If spans already arrive in correct reading order, then sorting them by
> `top` **actively destroys** that order. Under H2 the fix is not to build column detection but to
> stop re-ordering what was already correct — or to re-order only when the incoming order is
> demonstrably unreliable.

H1 and H2 are not mutually exclusive and both are testable in an afternoon.

## Open questions (to settle by measurement, not by argument)

- **Q1** Does an OCR'd two-column PDF's text layer already arrive in reading order? (Directly tests H2.)
- **Q2** Does a born-digital two-column PDF (LaTeX paper, InDesign magazine) arrive in reading order,
  column-sequential, or arbitrary?
- **Q3** What does the current pipeline actually produce for each — unusable scramble, subtle damage,
  or acceptable output? "Broken" must be shown, not assumed.
- **Q4** What does `text_layer_quality` decide for these files today: `promising`, or does it already
  refuse them for an unrelated reason?
- **Q5** Was the owner's successful document processed before the LibreOffice→text-layer switch?
  (Confirms or kills H1; answerable from git history plus the owner's recollection.)
- **Q6** If the incoming order is already correct, does anything else in the pipeline depend on the
  `top`-sort (heading layout profile, furniture detection, paragraph merging)? I.e. what breaks if we
  stop sorting?
- **Q7** How common is this class for the project's real users? The project targets long books, which
  are typically single-column; papers and reports are not. This decides how much the fix is worth.

## Decision plan (do this first, next session)

1. Obtain **two** real files: one OCR'd two-column PDF, one born-digital two-column PDF. Place them
   under a scratch path, not in the corpus.
2. For each, dump the **raw span order** as extracted (before the sort) and the **post-sort order**.
   Compare them. This alone answers Q1, Q2 and H2.
3. Run the real import and read the resulting paragraphs. Record what the user would actually get
   (Q3), and what the quality gate decided (Q4).
4. Only then choose among the options below, and write the real spec for the chosen one.

## Options (deliberately not chosen yet)

- **A — Refuse.** Detect two columns geometrically, stop before any model call, tell the user to
  convert to DOCX in Word/LibreOffice. Cheapest; prevents paid, plausible-looking corruption. Correct
  only if Q3 shows the output is genuinely unusable.
- **B — Stop destroying a correct order.** If H2 holds, preserve the incoming span order (or sort only
  within a detected column band). Potentially the smallest fix with the largest payoff, but Q6 must
  confirm nothing else relies on the sort.
- **C — Real column-aware reading order.** Cluster left edges, order column by column. The honest full
  fix, and the largest: headers spanning both columns, figures, footnotes, page-crossing columns and
  mixed layouts each add failure modes.
- **D — Restore a LibreOffice path for multi-column input only.** Reuses a component that already
  solves this; costs a heavy runtime dependency on the PDF path again and re-opens a contract the
  project deliberately closed.
- **E — Do nothing.** Valid if Q3 shows current output is acceptable. Then F6 is withdrawn and this
  document records why.

Note that A and C share the same prerequisite (detection), so work on A is not wasted if C is chosen
later. B is the only option that could make A unnecessary.

## Non-goals

- Implementing any option before the measurement in `## Decision plan` has run.
- Adding two-column books to the validation corpus as part of this work — the corpus is a
  loss-budget instrument, and a new profile is a separate decision.
- OCR quality, scanned-PDF OCR, or any change to what counts as a usable text layer beyond the
  layout question.
- Per-document tuning of any kind: whatever is chosen must key on layout geometry or source order,
  never on a document's content (Constitution VII).

## Anti-regression (binding on whichever option is chosen)

- Single-column PDFs must be byte-identical in reading order to today. The four corpus books are the
  proof, and a golden/structural comparison must show no drift.
- If detection is added, it must have a **negative control**: a single-column page with an indented
  block, a table, or a wide figure must NOT be classified as two-column.
- If refusal is added, it must fire **before** any model call, so a rejected document costs nothing.
- No option may silently change behaviour for documents that work today.

## Assumptions

- The owner's recollection is treated as evidence, not as noise; H1 exists specifically to explain it
  rather than dismiss it.
- Two real files are enough to choose a direction; they are not enough to claim general correctness,
  and the chosen spec will say so.
