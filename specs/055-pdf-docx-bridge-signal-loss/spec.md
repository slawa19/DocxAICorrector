# Feature Specification: The PDF→DOCX bridge throws away what the importer measured

**Feature Branch**: `[055-pdf-docx-bridge-signal-loss]`

**Created**: 2026-08-05

**Date**: 2026-08-05

**Status**: **READY — measured, not started.** Everything below was measured on 2026-08-04 during the
spec 054 iteration and independently re-verified by the orchestrator. No code has been written.

**Owner surface**: `processing/processing_runtime.py` — `_append_pdf_text_paragraph_to_docx`,
`_pdf_text_layer_docx_style`

**Companion**: `specs/054-audiobook-mode-review-and-run/spec.md` (the iteration that found this while
looking for something else)

## Why this is not another rule fix

For months this project has been finding, one at a time, rules in `document/extraction.py` that
reconstruct structure from the *shape of the text* — a line's length, its word count, what character
it ends in. Each one was real, each was removed or narrowed, and each time the next one appeared.

The reason they keep appearing is upstream of all of them.

`pdf_import/logical_import.py` reads a PDF and measures the real thing: font-size clusters, Otsu
thresholds, line-width percentiles, page geometry. It assigns roles from that evidence. Then
`_append_pdf_text_paragraph_to_docx` (`processing/processing_runtime.py:1015`, verified 2026-08-04)
writes the intermediate DOCX using **a style name and bold/italic, and nothing else**. No font size,
no alignment, no spacing, no geometry. And `_pdf_text_layer_docx_style` (`:1132`) maps **only**
`heading` and `list` to a style — every other role, `toc_entry` and captions and footnotes included,
returns `None` and lands as plain `Normal`.

Then `document/extraction.py` reads that impoverished DOCX and **guesses the structure again**, blind.
Two independent structure classifiers on one document, and the second one has had its evidence taken
away. That is why it guesses from text shape: there is nothing else left to guess from.

## Measured

Same book as a native DOCX and as a PDF, so the difference is the bridge and nothing else
(2026-08-04, offline, no LLM):

| signal | Rethinking Money `.docx` | the same book as `.pdf` |
|---|---|---|
| `paragraph_alignment` populated | 1997 / 1997 | **0 / 2290** |
| `vertical_gap_before_pt` populated | 1997 / 1997 | **0 / 2290** |
| `font_size_pt` populated | 1997, 28 distinct values | 36, **2** distinct values |
| `paragraph_properties_xml` distinct | 501 | **4** |

`paragraph_alignment` and `vertical_gap_before_pt` are **0 of 7875 paragraphs across all four PDF
books**. The Value of Everything shows the same collapse (1760/1763 → 15/2314).

### Three rules are therefore dead, not weak

| rule | on native DOCX | on 4 PDF books |
|---|---|---|
| `promote_short_standalone_headings` (`document/roles.py:202`) | 2 and 1 applications | **0 on 4/4** |
| `normalize_front_matter_display_title` (`roles.py:255`, needs `font_size_pt >= 18`) | fires | **0 on 4/4** |
| every branch requiring `paragraph_alignment == "center"` (`roles.py:421`, `structure_repair.py:582`, `segments.py:970`) | reachable | **unreachable** |

This is the third and fourth instance of the pattern the project keeps re-discovering — a rule that
exists and never fires. Here the cause is common to all of them and is one function.

## What this work is

**Carry the signals the importer already measured across the bridge.** Font size per run, paragraph
alignment, space-before — written from the values `logical_import` computed, into the intermediate
DOCX, so that `extraction.py` reads evidence instead of inventing it.

This is not a new heuristic. Constitution VII names this exact remedy: *"The honest options are: fix
the IMPORT so a real signal exists, or accept."* Everything to date has been the second option.

## Non-goals

- **No tagged-PDF structure.** Codex proposed it four times; not one of the four corpus books is
  tagged. It is a proposal that requires data the owner does not have, like the two-column question.
- **No two-column handling** (spec 050, deferred by the owner with no date).
- **No new detector, anywhere.** If a signal arrives and a downstream rule still cannot use it, the
  honest outcome is to record that, not to write a cleverer rule.
- **No change to the native DOCX path.** It already carries these signals; it is the control group,
  and it must stay byte-identical.
- **Do not "improve" the roles the bridge drops** beyond carrying what already exists. Whether
  `toc_entry` and caption roles should survive the bridge as styles is a separate question with its
  own blast radius; measure it, propose it, do not fold it in.

## The honest uncertainty

Reviving three dead rules will change output on every PDF book, and **the direction is not known**.
`promote_short_standalone_headings` has never run on this corpus, so nobody has seen what it does to
these books. It may promote headings correctly; it may promote noise. Spec 049 is the cautionary
precedent: an obvious remedy was implemented, measured, disproved and reverted.

So this work is **measure-first, and the measurement is the deliverable**. Carrying the signals and
observing what the dead rules then do is the experiment. Whether to keep each revived rule is decided
after, per rule, on numbers — and "this rule is worse with real evidence than it was dead" is a
permitted and expected outcome.

## Anti-regression

1. **The native DOCX path does not change.** Its paragraph counts, roles and golden fixtures stay
   byte-identical. If they move, the change leaked into the wrong path.
2. **Every revived rule is measured separately**, on all four PDF books, before/after, with the
   blocks it touches quoted. A rule that fires is not thereby correct.
3. **No rule is credited by a unit test alone.** The counter-proof is the corpus, per Constitution
   VII's anti-vacuum requirement and the discipline that caught three vacuous passes in spec 054.
4. **The golden gate is usable again and must be used** — `_stable_perturb_key` was made
   content-addressed on 2026-08-04 (PR #36) precisely because this work merges and splits paragraphs
   and the gate could not see that class of change. Its regeneration evidence contract applies:
   argue per source paragraph keyed on text; `mapped_count` is not evidence.
5. **The prose blocks recovered in spec 054 stay recovered** — Rethinking Money's Bernice Hill and
   "not generally known" paragraphs, Money & Sustainability's banking-crises paragraph, The Value of
   Everything's "deeply ingrained ideas" paragraph.

## Plan

1. Measure what `logical_import` currently holds per paragraph and which of those values the bridge
   could write but does not. The census script from the 2026-08-04 import review is the starting
   point.
2. Carry them. One function, plus whatever `_pdf_text_layer_docx_style` needs to stop returning
   `None` for roles it could express.
3. Re-measure the three dead rules. Per rule: does it fire, on what, and is the result right —
   quoted, not counted.
4. Decide per rule: keep, narrow, or delete. A rule that only ever fired because it was dead is a
   rule to delete.
5. Re-measure the downstream shape heuristics that exist *because* the evidence was missing. Some
   should become deletable. That is the real prize, and it is not claimable in advance.

## Changelog

- **2026-08-05** — spec created from measurements taken during spec 054 on 2026-08-04: the bridge
  census across four PDF books and their native DOCX twins, the three dead rules, and the role
  mapping that keeps two roles of the several `logical_import` assigns. Not started.
