# Feature Specification: Boundary recovery merges by the shape of the translation, and one product's repair is the other's defect

**Feature Branch**: `[057-boundary-recovery-is-product-blind]`

**Created**: 2026-08-07

**Date**: 2026-08-07

**Status**: **READY — measured 2026-08-07, not started.** Everything below is measured on the
`20260806T_fin2_money_translate` run and re-verified against the delivered DOCX by the orchestrator.

**Owner surface**: `pipeline/output_validation.py` — `_recover_adjacent_entries`,
`_left_entry_looks_incomplete`, `_right_entry_looks_like_continuation`, `_entry_is_protected_boundary`

**Companion**: `specs/054-audiobook-mode-review-and-run/spec.md` (the narration side of the same
mechanism, where it is a repair)

## First, two things this spec is NOT about, because the committed material says otherwise

`artifacts/audiobook_final_run/final_package.md` sections 2.2 and 2.3 are **wrong**, and this spec
opens by retracting them, because they are in the repository and would otherwise be the next reader's
starting point.

**"19 headings lost, all five chapter titles as `Body Text`, `## Благодарности` in the text" — false.**
Verified directly in the delivered `.docx`: all **nine** chapter titles carry `Heading 1` at
paragraphs 204, 249, 364, 478, 624, 774, 888, 1081, 1226. Of 1344 paragraphs, **zero** begin with a
markdown hash. The review harness compared each heading against the **first occurrence of its text in
the file** — and the first occurrence is the table-of-contents row, which legitimately carries
`Body Text`. Twelve of twenty-one "lost headings" were that artefact. The `## Благодарности` quote was
the `translated` field of the raw model answer read in place of `target_text`, which holds
`Благодарности` beside it.

The role is not lost anywhere. Traced end to end for `p0211` on current code: `logical_import` gives
`role=heading, level=1, style=Heading 1` at 23.76 pt; the bridge writes `Heading 1`; extraction reads
`heading/1`; the model is asked with `# Chapter I` and answers `# Глава I`; the registry keeps
`heading/1`; the document has `<Heading 1> Глава I`. Measured offline on all four books, heading roles
survive the bridge essentially one-to-one — 175/250/175/128 at preparation against 170/248/167/131 at
import.

**"Up to 74 touches, real text loss among them" — false in both directions.** Real loss is **zero**:
of the 33 "broken or missing", 23 stand as their own paragraph and failed only on typographic quotes,
6 were merges already counted, and 4 are a captured retry attempt that is not the one delivered — all
four texts are present in the document, worded differently. Meanwhile the merge count was **understated**:
63 document paragraphs absorbed 143 source paragraphs, i.e. **80 lost boundaries**, not 41.

The pipeline's own diagnostics agree with the corrected numbers by an independent route:
`accepted_merges=82` against 80 measured, `demoted_false_headings=9` against 9 measured.

## What is actually wrong

`_recover_adjacent_entries` (`pipeline/output_validation.py:1279-1349`) merges two adjacent registry
entries when `_left_entry_looks_incomplete` (`:1228` — no terminal punctuation) and
`_right_entry_looks_like_continuation` (`:1241` — starts lowercase, or with a quote or a dash).

Both predicates read **the shape of the translated text**. Constitution VII forbids exactly that as a
basis for reconstructing structure — and here it is used to **destroy** structure, with the guard
(`_entry_is_protected_boundary`, `:1174`) removed beforehand by a heading demotion at `:1292`.

Measured on one book, 1426 source paragraphs:

| | pairs |
|---|---|
| **a real boundary destroyed** — the SOURCE left paragraph ends in terminal punctuation | **25** |
| left without terminal punctuation, right opens a new unit (captions, bylines, appendix labels) | 54 |
| **a genuine repair** — the source paragraph really was torn mid-sentence | **1** |

Nine of the 80 are headings, demoted first and merged second. Examples, quoted from the delivered
document:

> `docx#205` = `p0212+p0213+p0214`: «Почему этот отчет выходит именно сейчас? "Сердце болит обо всем,
> что мне не спасти. Столько всего разрушено."» — a chapter subheading welded to its epigraph.

> `docx#61` = `p0062…p0066`, five paragraphs: «Член Римского клуба, президент отделения Римского клуба
> в ЕС Феликс УНГЕР Иво ШЛАУС Президент Европейской академии наук и искусств…» — a page of signatures
> collapsed into one line.

> `docx#1018` = `p1075+p1076` — the single honest repair on the whole book.

## And the same rule is a repair in the other product

In the narration, joining two adjacent paragraphs is what PR #46 does deliberately: 19 joins on the
same run, counted and reported as a fix, because a sentence torn across a paragraph boundary becomes a
wrong pause in TTS. **One function serves both products and the sign of its action is opposite in
each.** That, and not the merging itself, is the defect.

## Decision

**Make the merge product-aware, and key the refusal on the SOURCE, not on the translation.**

In document-producing operations, refuse the merge when the **source** left paragraph ends in terminal
punctuation. That is 25 of the 80 pairs, decided by a property of the input document rather than by
the shape of the model's output — no heuristic, no word list, nothing to tune.

The remaining 54 stay merged and are **accepted**: separating a caption or a byline from a genuine
continuation needs the source paragraph's role, and half of them do not have one — `Felix U NGER`
arrives `body` while `Ivo ŠLAU S`, the neighbouring line of the same signature block, arrives
`heading`. Constitution VII: no source signal, no repair.

## Non-goals

- **Do not touch the narration side.** Its 19 joins are a measured repair; a change that suppresses
  them trades one product's defect for another's.
- **Do not try to separate the 54 by text shape.** That is the very rule being removed.
- **Do not chase The Value of Everything's chapter titles.** They arrive `role=body,
  heading_level=None`; Constitution VII already records this exact case as accepted, and spec 055
  measured the obvious remedy and disproved it.
- **Do not rewrite the review harness in production.** It lives in `.run/`; its three defects
  (first-occurrence lookup, unfolded typography, one attempt per paragraph) are recorded here so the
  next measurement does not repeat them.

## Anti-regression

1. **The narration keeps its joins.** The audiobook run's join counter must not fall.
2. **The rule is not disabled, only narrowed.** `denied_merges` (761) and
   `protected_boundary_denials` (575) must not collapse — the rule already refuses far more often than
   it accepts, and a change that makes it refuse everything is not a fix.
3. **Measured per book, before and after**, from the pipeline's own `boundary_recovery_diagnostics`
   rather than from a bespoke harness. `accepted_merges` should fall by about 25 on this book;
   `demoted_false_headings` is a separate counter and should be watched, not assumed.
4. **No text is lost.** Real loss is zero today and must stay zero: the character sequence of the
   document, whitespace-stripped, does not change.

## What is not established

- **Only one book has ever been run in document mode.** Whether 80 merges per book generalises is
  unknown. The rule keys on the translation rather than the source, so book-specific behaviour is not
  expected — but that is reasoning, not a number.
- **The 25 "real boundaries destroyed" were classified mechanically** (terminal punctuation in the
  source) and spot-checked on 8 of 25.
- **Attribution of the 80 merges between the two call sites** is incomplete: the raw model answer
  accounts for 1, the runtime display cleanup for 14, and the rest falls to `assemble_final_markdown`,
  which cannot be replayed offline without `processed_chunks`.
- **Side finding, opposite sign, not part of this work:** four table-of-contents rows («Глава VI»–«IX»,
  document paragraphs 28/30/32/34) carry `Heading 1`. Extraction demotes I–V to `toc_entry` and stops.
  Four touches, one book.

## Changelog

- **2026-08-07** — spec created after a diagnosis that retracted the two findings it was expected to
  confirm. The headings were never lost and no text was ever lost; the review method was comparing
  against table-of-contents rows and against unfolded typography. What survived measurement is a
  single mechanism that merges by the shape of the translation, destroys 25 real boundaries on one
  book, and is simultaneously a deliberate repair in the narration.
