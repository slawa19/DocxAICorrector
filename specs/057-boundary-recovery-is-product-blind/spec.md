# Feature Specification: Boundary recovery merges by the shape of the translation, and one product's repair is the other's defect

**Feature Branch**: `[057-boundary-recovery-is-product-blind]`

**Created**: 2026-08-07

**Date**: 2026-08-07

**Status**: **IMPLEMENTED (2026-08-07) — confirmed by a paid before/after run on the same book.**
`20260806T_fin2_money_translate` (before) against `20260807T_spec057_after` (after), same document
profile, same run profile, same model. All four anti-regressions hold; the figures are in
"Confirmed live" below.

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

## The other product runs a different function, and was already kept apart

This spec was drafted believing one function served both products and that the fix therefore had to
be product-aware. **That is retracted here**, on the code, before it becomes the next reader's
starting point:

| | document | narration |
|---|---|---|
| function | `_recover_adjacent_entries` | `_join_narration_sentence_continuations` |
| module | `pipeline/output_validation.py` | `generation/_generation.py` (added by PR #46) |
| input | the assembled registry entries | `state.narration_chunks`, or the final-registry projection |

PR #46 said so in its own commit message: *"The DOCX path is untouched on purpose: in a document a
paragraph break is structure and the gates check it survives; in the audio it is a pause."* Both
narration entry points were traced: the standalone `audiobook` operation joins `state.narration_chunks`,
filled in `pipeline/block_execution.py:995,1207`; the translate post-process joins
`_project_final_cleanup_narration_chunks` over `final_generated_paragraph_registry`. Neither passes
through `assemble_final_markdown`, and assembly writes nothing back into the registry it reads.

What the two products share is not the mechanism but the **judgement** — and only the document side
still makes it on the shape of the translation. **This makes the fix smaller, not larger.** A
product-aware branch inside `_recover_adjacent_entries` would be dead code on the narration side from
the day it was written.

**The narration counter, corrected.** "19 joins on the same run" was wrong twice: the
`20260806T_fin2_money_translate` run has `narration_artifact: null` — a translate run without the
audiobook post-process produces no narration at all. The 19 is the sum over the four *audiobook* runs
of the same chain (5/5/2/7, read from each run's report). PR #46's offline measurement predicted 34
(5/7/14/8) on the earlier `ab4` run. The gap is not measured: the fin2 chain also carried the 054
back-matter fixes, and Rethinking Money's index rows — the very class PR #46 named as evidence for its
digit guard — no longer reach the narration. Plausible, but reasoning, not a number.

## Decision

**Key the refusal on the SOURCE, not on the translation, and apply it unconditionally.**

Refuse the merge when the **source** left paragraph ends in terminal punctuation. That is 25 of the 80
pairs, decided by a property of the input document rather than by the shape of the model's output — no
heuristic, no word list, nothing to tune.

Unconditionally, because the narration does not run this function. Where the source paragraph is
**unknown** — no `paragraph_id`, or an entry the registry never covered — the refusal cannot be
decided, and the current behaviour stands: a missing signal must not quietly become a new rule.

The remaining 54 stay merged and are **accepted**: separating a caption or a byline from a genuine
continuation needs the source paragraph's role, and half of them do not have one — `Felix U NGER`
arrives `body` while `Ivo ŠLAU S`, the neighbouring line of the same signature block, arrives
`heading`. Constitution VII: no source signal, no repair.

## Non-goals

- **Do not touch the narration side.** Its joins are a measured repair; a change that suppresses them
  trades one product's defect for another's. Nothing in this work reaches it — that is established
  above, not assumed.
- **Do not add a product flag to `_recover_adjacent_entries`.** The first draft of this spec asked for
  one; the call graph says it would never take its other value.
- **Do not try to separate the 54 by text shape.** That is the very rule being removed.
- **Do not chase The Value of Everything's chapter titles.** They arrive `role=body,
  heading_level=None`; Constitution VII already records this exact case as accepted, and spec 055
  measured the obvious remedy and disproved it.
- **Do not rewrite the review harness in production.** It lives in `.run/`; its three defects
  (first-occurrence lookup, unfolded typography, one attempt per paragraph) are recorded here so the
  next measurement does not repeat them.

## Anti-regression

1. **The narration keeps its joins — in every configuration this project runs, but NOT "by
   construction".** That claim was made twice in this spec and an independent review disproved it.
   Standalone `audiobook` is genuinely isolated: it joins `state.narration_chunks`. But `translate`
   has a live bridge — `assemble_final_markdown` entries become the `formatting_registry` passed to
   reader cleanup (`late_phases.py:790`), reader cleanup returns them as
   `final_generated_paragraph_registry` (`:811`), that lands in `docx_phase` (`:817`), reaches
   `_build_narration_text` (`:1080`), and with reader cleanup ON the narration is projected from it
   (`narration_postprocess.py:150-165`). So under `processing_operation=translate` **and**
   `reader_cleanup_enabled` **and** `reader_cleanup_policy != off` **and** audiobook post-process, a
   refusal here changes the narration's INPUT.
   The gate is closed today — reader cleanup is off by default and every run in this corpus used a
   `no-cleanup` profile — and the downstream effect is most likely benign, because the narration then
   applies its OWN join to the two chunks. But "cannot reach it" was wrong, and if reader cleanup is
   ever switched on, `joined_sentence_continuation_count` must be checked, not assumed.
2. **The rule is not disabled, only narrowed.** `denied_merges` (761) and
   `protected_boundary_denials` (575) must not collapse — the rule already refuses far more often than
   it accepts, and a change that makes it refuse everything is not a fix.
3. **Measured per book, before and after**, from the pipeline's own `boundary_recovery_diagnostics`
   rather than from a bespoke harness. `accepted_merges` should fall by about 25 on this book;
   `demoted_false_headings` is a separate counter and should be watched, not assumed. The counters
   survive in each run's report under `translation_quality_report.boundary_recovery` — that is where
   the figures in this spec were re-read from. **But `merge_decisions` there is capped at 20**
   (`pipeline/quality_gate_serializers.py:13`, `limit=20`), so the report holds 20 of this run's 91
   decisions: the counters are complete, the per-pair list is not. Naming the 25 refused pairs needs
   the cap raised or an offline replay.
4. **No text is lost.** Real loss is zero today and must stay zero: the character sequence of the
   document, whitespace-stripped, does not change.

## Confirmed live

A paid run of the same book on the same profile and model, read from the pipeline's own
`translation_quality_report.boundary_recovery` — not from a bespoke harness:

| counter | before | after | delta |
|---|---:|---:|---:|
| `accepted_merges` | 82 | **55** | −27 |
| `source_terminal_denials` | — | **24** | new |
| `denied_merges` | 761 | 765 | +4 |
| `protected_boundary_denials` | 575 | 575 | 0 |
| `demoted_false_headings` | 9 | 9 | 0 |
| `registry_covered_paragraphs` | 1383 | 1383 | 0 |
| `fallback_paragraphs` | 43 | 43 | 0 |
| `paragraph_count_drift` | −82 | −55 | +27 |

The four anti-regressions:

1. **Narration untouched** — a translate run produces no narration artifact, and the join lives in a
   different function on a different input. Nothing to measure, by construction.
2. **The rule was narrowed, not disabled** — `denied_merges` and `protected_boundary_denials` did not
   collapse; the latter is identical to the unit.
3. **`accepted_merges` fell by 27**, of which **24** are named directly by `source_terminal_denials`.
   The spec predicted ~25. The residual 3 is run noise: the model's output differs between runs, so
   three pairs no longer met the translation-shape predicates at all and never reached the refusal.
4. **No text lost.** `source_count` is 1426 in both runs and the delivered document gained 27
   paragraphs (1342 → 1369). The one paragraph that changed mapping status, `p0323`, is **present**
   in the delivered document at target index 313 — «и совершенно справедливо». — it simply stands on
   its own now instead of being welded to the quotation before it.

An independent second route agrees: absorbed source paragraphs (those with no target index of their
own) fall **80 → 53**, with 28 recovered and 1 newly absorbed.

**All four named predictions held on the delivered document:**

| case | predicted | observed |
|---|---|---|
| `docx#205` — subheading welded to its epigraph (`p0213`, `p0214`) | unwelded | unwelded |
| `docx#61` — five-paragraph signature block (`p0063`…`p0066`) | still merged | still merged |
| `p1075+p1076` — the honest repair ending in `;` | still merged | still merged |
| `p0322+p0323` — quotation torn across two source paragraphs | split, accepted cost | split |

**One side effect worth recording:** `p0323` is now the only newly *unmapped* source paragraph
(8 → 9). Its text is delivered, but the formatting mapper no longer ties it to a source id, so it
loses role-aware formatting coverage. One paragraph on one book; not chased.

## What implementation found that this spec did not foresee

**The rule as this spec wrote it refuses NOTHING.** `document/extraction.py:1383-1387` bakes inline
markup straight into `ParagraphUnit.text` — `***…***` / `**…**` / `*…*`, then `<u>`, `<sup>`, `<sub>`
— so a source paragraph does not end in a full stop, it ends in an asterisk. Measured twice
independently, on the 80 pairs of this run:

| tail test on the source paragraph | refusals of 80 |
|---|---|
| last character in `.!?…` | **0** |
| after stripping hanging closing quotes and brackets | **0** |
| after also unwrapping trailing emphasis markers and inline tags | **25** |

The spec's 25 is reachable only through the third row. The unwrap is not a heuristic — it removes
exactly the markup the importer itself added — but it had to be found before the fix could do
anything, and a test that fails without it is committed alongside
(`refuses_merge_when_source_terminal_mark_is_wrapped_in_emphasis_markers`; verified by mutation to
fail when the unwrap is removed, and only it).

**Three of this spec's own figures were wrong.**

- **63 / 143 is off by one.** The visible census is 62 targets absorbing 142 sources; adding the two
  merges whose target itself failed to map (`p0964+p0965` → docx#914, `p1345+p1346` → docx#1270) gives
  **64 / 146**, and 146 − 64 = **82** = `accepted_merges` with no residue. The derived 80 was right.
- **"Nine of the 80 are headings" conflates two counts.** By source role, **six** of the 80 absorbed
  paragraphs are `heading`. The nine are `demoted_false_headings`, a different set.
- **There were two honest repairs, not one.** Besides `p1075+p1076`, `p0322+p0323` is a quotation
  genuinely torn across two source paragraphs — the closing `”` lives in the right half. The rule
  refuses it. That is a real, accepted cost, not a case the source failed to signal.

**What the fix does not reach.** `docx#61` — the five-paragraph signature block this spec leads with —
**stays merged**. Those lines carry no terminal punctuation at all, so the source says nothing about
their boundaries. Of the two defects quoted at the top, the rule repairs `docx#205` (the subheading
welded to its epigraph, both boundaries refused) and leaves `docx#61` untouched.

**And `p1075+p1076` confirms the choice to exclude `:` and `;`.** The one repair the spec named ends
in `;`. Admitting `;` would destroy it, along with five correct merges that are colon lead-ins to
their own continuation («One popular definition of insanity comes to mind:» + the definition).

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

## Known limits of the rule, found by independent review and measured

An independent read of the merged code (Codex, read-only, no ability to measure) raised four points.
All four were then measured by the orchestrator on the 1383 source paragraphs of the run.

| raised | verdict | measured on the book |
|---|---|---|
| the narration IS reachable in `translate` + reader cleanup | **correct, spec was wrong** | see anti-regression 1 |
| ASCII-only whitespace trim misses a trailing NBSP | **correct, latent** | 0 of 1383 paragraphs affected; fixed anyway |
| stripping `_` is not justified by the importer's markup | **correct** | contributes 0 refusals; `_` removed |
| the terminal alphabet has no CJK `。` | **correct, out of scope** | the rule under-fires, which is the safe direction |

Two limits are deliberate and recorded rather than fixed:

- **A trailing footnote marker is not unwrapped.** `unabated.<sup>28</sup>` peels to `unabated.<sup>28`
  and reads as False. The `28` is *text*, not markup; removing it to manufacture a boundary signal is
  exactly what Constitution VII forbids. Moot on this corpus: **0 of 1383** source paragraphs carry an
  inline tag at all — the PDF bridge never sets the run properties that produce them.
- **A literal asterisk is indistinguishable from an emphasis marker.** `Pattern: .*` would peel to
  `Pattern: .` and refuse a merge that should have happened. On this book 5 paragraphs carry an odd
  number of `*`, all of them `* * *` dividers or OCR noise, none a left half of any pair.

## Changelog

- **2026-08-07 (confirmed)** — paid before/after run on the same book closed anti-regression 3.
  `accepted_merges` 82 → 55, `source_terminal_denials` = 24 against ~25 predicted, `denied_merges` and
  `protected_boundary_denials` intact, acceptance passed, no text lost. All four named predictions
  held, including the two the spec expected to *fail*: the signature block stays merged and the second
  honest repair is split. Figures in "Confirmed live".
- **2026-08-07 (implementation)** — the refusal landed in `_recover_adjacent_entries`, keyed on a new
  `FinalAssemblyEntry.source_ends_sentence` filled from `ParagraphUnit.text` at the one construction
  site where the source paragraph is already resolved. Counted separately as `source_terminal_denials`
  so `denied_merges` stays comparable. A merged entry inherits the RIGHT half's signal — taking the
  left's would judge a chain by the paragraph two links back. Eight tests, all through the public
  `assemble_final_markdown`. Three mutations confirmed the tests have teeth: removing the emphasis
  unwrap fails exactly the two markup tests; making the rule always refuse fails the anti-vacuum test;
  inheriting the left's signal fails exactly the chain test. Status stays OPEN: the paid before/after
  run of anti-regression 3 has not been done, and this pipeline has twice shipped a defect that
  survived to a live run under a green test on flat paragraphs.
- **2026-08-07 (same day, before merge)** — the spec's own headline claim retracted after the
  orchestrator read the two call graphs: it is **not** one function serving both products. The
  narration join is `_join_narration_sentence_continuations` in `generation/_generation.py`, PR #46
  wrote "The DOCX path is untouched on purpose", and neither narration entry point passes through
  `assemble_final_markdown`. The decision drops product-awareness and narrows the document rule
  unconditionally. "19 joins on the same run" corrected: that run produced no narration; 19 is the
  four audiobook runs of the chain. The four counters quoted here were re-read from the run's own
  report and match exactly; the per-pair decision list in it is capped at 20.
- **2026-08-07** — spec created after a diagnosis that retracted the two findings it was expected to
  confirm. The headings were never lost and no text was ever lost; the review method was comparing
  against table-of-contents rows and against unfolded typography. What survived measurement is a
  single mechanism that merges by the shape of the translation, destroys 25 real boundaries on one
  book, and is simultaneously a deliberate repair in the narration.
