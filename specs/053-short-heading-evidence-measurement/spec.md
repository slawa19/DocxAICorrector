# Feature Specification: Do the headings lost by spec 046 carry any other real evidence? — a measurement

**Feature Branch**: `[053-short-heading-evidence-measurement]`

**Created**: 2026-07-31

**Status**: **NEEDS DECISION — measured, but the signal is not on the path that matters.** No code was
written and none is proposed yet. A discriminating, source-backed rule does exist (95% precision /
74% recall on the measured corpus) — but the measurement ran on externally converted DOCX, and on the
production PDF path the signal it depends on is thrown away before any rule could read it.
Implementing the rule as measured would repeat spec 049's mistake exactly. Deliberately **not** filed
as `MEASURED` (which in this repo means "implemented, measured, disproven, reverted" — that was 049):
nothing was implemented here, and a decision is still owed on whether to run the follow-up measurement
in `## What to do next`.

**Date**: 2026-07-31

**Owner surface**: `document/roles.py::promote_short_standalone_headings`, PDF text-layer import
serialization

**Companion**: `specs/046-universal-short-heading-evidence/spec.md` (removed the length-only rule);
`specs/049-pdf-import-preserves-font-size/spec.md` (the cautionary precedent — same trap, one step
earlier)

## The question

Spec 046 removed heading promotion based on text length alone — correct under Constitution VII, which
forbids reconstructing structure from "a leading ordinal, capitalisation, length, position". What
remains requires `font_size_pt` to exceed the neighbours'. Spec 049 then tried to feed font size
through PDF import, measured it, and got zero headings back.

So: do the paragraphs that were demoted carry **any other real, observable signal** in the source —
one that would make a lawful rule possible?

## Method

The exact set of demoted paragraphs was taken from the spec 046 merge commit (`67d682e`): 46 removed
`"role": "heading"` lines in the golden fixtures, which resolve to **43 distinct paragraphs** once the
duplicate residual/sample entries are folded by `paragraph_id`.

Features were snapshotted at exactly the point where `promote_short_standalone_headings` runs, for all
five books, by intercepting the call — so every measured attribute is one a rule could actually read.
The population the rule can even reach (short, standalone, both neighbours body prose, non-epigraph)
is **248 candidates**, hand-labelled by context into **158 genuine headings / 90 junk**; within the 43
demoted, **30 genuine / 13 junk**.

Two control groups, because a frequency without a control is meaningless: the 90 junk items inside the
same gated population (the only fair control — a rule never sees anything else), and 1 110 arbitrary
short body paragraphs.

## Result

| Signal | 30 lost headings | Control: 90 junk in-population | Discriminates? |
|---|---|---|---|
| **Gap before > book median AND > gap after** | **80%** | **2%** | **yes — strongest** |
| **Centered while neighbours are not** | 53% | 3% | yes |
| **Bold while neighbours are not** | 17% | 3% | yes |
| Italic while neighbours are not | 17% | 0% | yes, but rare |
| Font size > neighbours (any delta) | **0%** | 7% | **no** |
| Font size ≥ neighbours + 1.5 (today's rule) | **0%** | 2% | effectively a no-op |
| ALL-CAPS | 3% | 11% | **inverted — an anti-signal** |
| Style name differs from neighbours | 0% | 25% | **inverted** |

Two results are worth stating plainly. **Font size — the one signal the surviving rule depends on, and
the one spec 049 tried to rescue — discriminates nothing**: not one of the 30 lost headings had a font
larger than its neighbours. And **ALL-CAPS is an anti-signal**: it is three times more common in junk
(page furniture, security stamps) than in real headings, so a prompt or rule that treats capitalisation
as heading evidence is actively wrong, not merely unlawful.

The candidate rule — *promote if (gap-before exceeds the book's median paragraph gap and exceeds the
gap after) or (bold/italic/centered while both neighbours are not), and not ALL-CAPS* — scores
**95.1% precision at 74.1% recall** over the 248 candidates (117 true, 6 false). It recovers 28 of the
30 genuine lost headings with zero false positives among the 13 junk ones. For comparison: the removed
length-only rule was 63.7% precision at 100% recall; today's font-size rule reaches 5.7% recall.

## Why this must not be implemented as measured

**The measurement did not run on the production path, and on the production path the winning signal
does not exist.**

The golden fixtures open pre-converted `tests/sources/book/*.docx` — an external LibreOffice conversion
of the PDFs, which preserves `w:spacing`, `w:jc` and font sizes. The project's own PDF importer does
not. `_append_pdf_text_paragraph_to_docx` (`processing/processing_runtime.py:1015`) writes a style, the
text, and per-run `bold`/`italic` — and nothing else. No vertical spacing, no alignment, no font size.

So on a real PDF upload, of the five discriminating features only bold and italic survive:
**98% precision at 32% recall** instead of 74%. Building the rule on a signal the production importer
discards is precisely the error spec 049 made one layer down.

**The near miss.** The PDF importer already computes this data and then destroys it.
`pdf_import/logical_import.py:833-838` derives `previous_gap` and `next_gap` **separately** — exactly
the asymmetry that turned out to be the strongest discriminator — and line 839 immediately collapses
them into `isolation_units = (previous_gap + next_gap) / body_leading`, a **sum**, which cannot express
"large gap above, small gap below". `indent_units` (`:832`) is computed too. Both feed a scoring
formula (`:863-864`) and neither is ever written to the intermediate DOCX.

**The signal is also book-dependent, and one book has none at all.** Recall by book:
money-sustainability 44/44, the_value_of_everything 11/12, rethinking_money 3/3,
creatingwealth 59/95, and **resistance (an OCR'd scan) 0/4 with 3 false positives**. In
`creatingwealth`, dozens of genuine subheadings (`Legal Tender`, `Fluxus Bucks`, `Retirees`) carry
**byte-identical** paragraph properties and font to the surrounding prose — 14 pt, `Style2`, left,
`after=0`. Nothing observable separates them from body text. The only thing that does is the shape of
the text itself, which is exactly what spec 046 outlawed.

## The same root cause starves the reader-cleanup route

`specs/052-reader-cleanup-first-production-run/spec.md` identifies a lawful way to restore headings
during reader cleanup: the pass already receives `layout_signals` per block (font size versus body,
indent, alignment, centered, superscript), and an unused prompt is built on them.

Those signals are read from the formatting registry, which is derived from the **same intermediate
DOCX**. So on PDF input they are as empty as `font_size_pt` is here — one serializer, two starved
consumers. Neither heading route can work on PDF books until that serializer carries more than
bold/italic.

## What to do next — measure once more, then decide

Do **not** implement the rule yet. One cheap, offline, no-LLM check decides everything:

**Can the PDF importer carry vertical gap (before and after, separately — not their sum), alignment
and indent into the intermediate DOCX as `w:spacing` / `w:jc`, and do those values, once there, still
discriminate?** The upstream data demonstrably exists (`logical_import.py:833-838`); the question is
whether it survives paragraph assembly with enough fidelity to reproduce the 80%/2% split measured on
the LibreOffice conversions.

- If yes: the rule is worth building, at roughly 74% recall and 95% precision, and it lawfully unblocks
  the reader-cleanup route as well.
- If no: the honest answer is that on PDF input no discriminating signal exists beyond bold and italic
  (32% recall), and the remaining options are to accept that as the PDF ceiling or to use DOCX input
  when structure matters — which is already the recorded decision.

Either way the result is worth recording, exactly as spec 049's negative result was.

## Limits of this measurement

Stated so nobody over-reads it:

- **The production PDF→DOCX path was not measured end to end.** The conclusion about it is read from
  the serializer's code, not from its output. That is the same kind of inference this spec warns
  against, and it is why the next step is a measurement rather than an implementation.
- **The heading/junk labelling is manual**, by context ±2 paragraphs, not verified against the original
  PDFs by eye. `creatingwealth` supplies ~60% of the total recall, so its labelling carries the most
  weight; ambiguous cases were labelled conservatively.
- At this point in the pipeline `font_size_z_score`, `style_cluster_id`, `position_fraction`,
  `page_number`, `vertical_gap_before_pt` and `heuristic_role_hint` are `None` for all 248 candidates,
  and `is_repeated_across_pages` / `is_likely_page_number` / `is_isolated_marker` / `toc_pattern_hint`
  are `False` for all of them — none of these carried information where the rule runs.
- `keepNext` is present in the paragraph properties but was `0` for both headings and body in every
  case checked; the converter does not set it.
