# Feature Specification: Audiobook mode — review it, run it once, and stop making the listener's editor work

**Feature Branch**: `[054-audiobook-mode-review-and-run]`

**Created**: 2026-08-04

**Status**: **IN PROGRESS — step 0 (measure before writing) done on 2026-08-04**, findings recorded
below in "Measured first, before any code". Approved by the owner on 2026-08-04 and deliberately
scheduled as its own session so it gets a clean context. This spec is the brief: everything below is
what the next session would otherwise have to rediscover. Per Constitution 2.0.0 this is the
**spec-only tier** — defect-driven remediation inside existing modules, no new module or contract.

**Date**: 2026-08-04

**Owner surface**: `processing_operation = "audiobook"`, the optional narration post-pass,
`resources/prompts/operation_audiobook.txt`, `pipeline/narration_postprocess.py`

**Companion**: `specs/052-reader-cleanup-first-production-run/spec.md` (the same shape of iteration —
review, one run, eyes-on, decide)

## Why

Audiobook mode has never been systematically reviewed and has never been run end to end on a real
book. Everything known about it so far surfaced as collateral while fixing other things.

The goal is not "make the audio nicer". It is **to reduce the manual editing a human has to do after
the run** — the same yardstick that settled the reader-cleanup question: count what a person would
have to fix by hand, before and after.

## What the owner asked for

**Drop the table of contents, the footnotes and the sources sections outright — but only where they
are clearly identifiable.** Nobody listens to a bibliography. This is different from every other
operation, where those regions are passed through untouched: for audio they should not be in the
output at all.

"Clearly identifiable" is the constraint that keeps this honest. If a region cannot be recognised
without guessing, leave it in rather than cut prose by mistake.

## Start here: the shared decision point already exists, and two of the three regions are already in it

Checked on 2026-08-04, and it makes this task much smaller than it looks. **Do not extract a module
and do not try to reconcile the two entry points** — the decision is already factored out above both
of them.

`document/semantic_blocks.py:520` `_resolve_narration_include` decides, once per block in the document
layer, whether a block belongs in the narration at all. Both paths honour it by construction: the main
generation loop skips excluded blocks when filling `state.narration_chunks`
(`pipeline/block_execution.py:849`), and the optional post-pass reads the same flag off the job
(`pipeline/narration_postprocess.py:77`). Assembly and validation are called once each, in the shared
delivery path (`late_phases.py:1074`, `:1149`). There is nothing here that can drift.

Two of the three regions the owner named are already excluded by that function:

```python
if all(_is_toc_structural_role(p, ...) for p in block.paragraphs):
    return False          # table of contents, by structural role
...
if block_index in bibliography_tail_indexes:
    return False          # the sources tail, by region
```

**Footnotes are not in the list.** That looks like the actual missing piece.

**But verify effect before writing anything.** Twice on 2026-08-02…03 this project found a rule that
existed and never fired: `promote_short_standalone_headings` was a complete no-op on PDF books because
the signal it keys on is never written, and the footnote-marker rule fired on exactly one book of four
because it only read the tail of a line. So the first question of the run is not "is there a rule" but
**how many blocks does it actually exclude** — `excluded_narration_block_count` already counts them,
per run.

Real duplication does exist, but elsewhere and harmlessly: the post-pass has its own chunk grouping,
model resolution and call loop. That is plumbing, not the decision, and a change to *what gets
dropped* does not touch it. The two loops differ for a legitimate reason — one runs inside the main
generation pass with markers, retries and paragraph restore; the other just regroups finished chunks.
Leave them alone.

## The gap this points at

`operation_audiobook.txt` rule 1 already tells the model to remove footnote markers, citations, DOI,
ISBN and raw URLs. But the model sees **one block at a time**, so the instruction is per-block
hygiene. Handed a whole bibliography entry as a block, the honest thing for it to return is nothing —
and a block that comes back empty or near-empty is exactly the shape that produced the literal
`(Пусто)` placeholders in the literary-edit run (spec 052 / PR #25).

So the likely answer is **region exclusion before the model is called**, not a better prompt. Which is
the same decision already open for reference material generally (see `docs/WHERE_WE_ARE.md`) — with
one difference that makes audiobook the easy case: here there is no argument about whether to keep
the region, only about whether it can be identified.

## What the next session needs to know

Context that is expensive to rediscover, all verified during the 2026-08-02…04 work:

- **Two entry points, not one.** The narration artifact is produced both by
  `processing_operation = "audiobook"` (standalone, replaces the result) and by an optional post-pass
  on translate/edit (the ElevenLabs checkbox). A defect can therefore show up on a translate run.
  `audiobook_postprocess_enabled` defaults to false.
- **The narration validator changed on 2026-08-03** (PR #29): its rule rejecting every Unicode
  superscript digit was removed, because a mathematical exponent `x²` was failing the whole artifact.
  Removing footnote markers is the prompt's job, not a glyph gate's. Do not reinstate the gate
  without reading that reasoning.
- **Marker-mode paragraph restore applies here too.** `is_marker_mode_enabled` depends on config, not
  on the operation, so the restore logic in `generation/_generation.py` runs for audiobook as well. It
  now restores a shrunken paragraph only when an absorbing neighbour is identified — which matters
  here precisely because the audiobook prompt *legitimately* empties some paragraphs.
- **Footnote markers now arrive as Unicode superscripts** from PDF import (PR #20), where before they
  were welded digits. That changes what the prompt is actually looking at.
- **Cost is now measured** (PR #26/#28): a run reports its real tokens and provider-reported cost. Use
  it — the reader-cleanup verdict turned on cost against benefit, and this one should too.

## Measured first, before any code (2026-08-04)

The spec's own instruction — *ask how many blocks the rule actually excludes before writing anything* —
was carried out. Two offline, LLM-free measurements over the four-book corpus, reproducing the
production decision exactly (same preparation, same structure phase `pre_ai_diagnostic`, same block
indexes): `scripts/measure-narration-exclusion.py` and `scripts/probe-bibliography-tail.py`. Raw
output: `.run/narration_exclusion/measure.json`, `measure_rest.json`, `toc_excluded.json`.

| book | blocks | excluded | % of chars | by reason |
|---|---|---|---|---|
| Money & Sustainability | 307 | 56 | 0.46% | image 43, toc 13 |
| Rethinking Money | 342 | 80 | 0.79% | image 55, toc 25 |
| The Value of Everything | 330 | 62 | 0.42% | image 42, toc 20 |
| Creating Wealth | 397 | 57 | 0.46% | image 43, toc 14 |

**The exclusion removes less than 1% of the text on every book, and the only two branches that ever
fire are `image_only` and `toc_structural_role`.** The owner's requirement is therefore unmet on two
of the three regions, and met on the third by a rule that is firing for the wrong reason.

### Finding 1 — the bibliography-tail exclusion has never fired, for two independent reasons

`bibliography_tail` = **0 blocks on 4 of 4 books**. This is the third instance in three days of a rule
that exists and never fires. Both causes are structural, not tuning:

**1a. The anchor overshoots the region it is meant to precede.**
`document/semantic_blocks.py:503` `_resolve_bibliography_tail_indexes` anchors on the **last**
heading-like block in the document and only looks *after* it. On a real book the last heading-like
block is always publisher back-matter that sits *behind* the bibliography, so nothing is left to
exclude (measured 2026-08-04):

| book | last heading-like block | blocks after it |
|---|---|---|
| Money & Sustainability | 304 — "Thought leaders in Design and Systems Thinking…" (Triarchy Press ad) | 2 |
| Creating Wealth | 395 — "20 Pounds of HAPs, VOCs…" (New Society environmental statement) | 1 |
| Rethinking Money | 341 — "Join the BK Community" | 0 |
| The Value of Everything | 329 — "Acknowledgements" | 0 |

The Value of Everything is the clearest case: block **319 is literally the heading `Bibliography`**,
blocks 320–328 are its entries, and block 329 `Acknowledgements` is the anchor. The region is right
there, correctly ordered, and the anchor steps straight over it.

**1b. Even with a correct start index, the region test cannot pass.**
`_is_bibliography_like_region` (`:487`) requires ≥ `TOC_DOMINANCE_THRESHOLD` = 0.7 of the region's
**lines** to be bibliography-like, and `_is_bibliography_like_line` (`:454`) only matches a leading
ordinal, a URL/DOI/ISBN token, or a references heading. A PDF-imported bibliography entry wraps over
several lines and only one of them carries the year, publisher or URL. The genuine bibliography of
The Value of Everything (blocks 320–328) measures **9–21% bib-like lines**, nowhere near 0.7. So even
if 1a were fixed alone, the tail would still resolve to zero. Both must be addressed, or the fix will
pass its unit test and change nothing on a book.

Why the existing tests did not catch this: `tests/test_document_structure_blocks.py:256` and `:303`
build the region out of one-line synthetic paragraphs (`"[1] Smith, 2009. DOI:10.1000/xyz"`) where
every line is bibliography-like by construction. They prove the arithmetic, not the behaviour. Any fix
here needs a fixture whose lines look like real imported text — this is Constitution VIII in its
concrete form.

### Finding 2 — real body prose is already being dropped from the narration, silently

The `toc_structural_role` branch fires on 13–25 blocks per book, and the dump of all 72
(`.run/narration_exclusion/toc_excluded.json`) shows the branch is doing three different jobs at once:
genuine tables of contents, index and endnote entries — and **ordinary mid-chapter prose**. Verified
samples, each carrying effective structural role `toc_entry` and therefore excluded from the artifact:

- Rethinking Money block 28 — "Jungian psychologist Bernice Hill has categorized four levels of what
  she calls "sacred wounds of money."¹⁶"
- Rethinking Money block 90 — "This distinction should be understood. And it's not generally known or
  appreciated by most people."²⁶"
- Money & Sustainability block 56 — "This scenario has been repeated for every one of the large-scale
  banking crises and monetary meltdowns of our times.²"
- The Value of Everything block 13 — "What if it stemmed purely from a set of deeply ingrained ideas?
  What new stories might we tell?"
- Plus epigraphs and their attributions (Yeats, Coleridge, Einstein 1932) across three books.

Roughly 20 of the 72 are unambiguous body prose; the rest divide into real TOC, index and endnote
entries. **This already violates anti-regression 1 of this spec, before a line of new code is
written**, and it is the audiobook-side twin of the defect Codex found on 2026-08-01: a TOC heuristic
that immunised any short line ending in a number. The pattern in the samples is visible — a short
standalone block whose last line ends in a digit — and PR #20 made it worse by turning footnote
markers into trailing Unicode superscripts. **Where the role is actually assigned is not yet
established and must be traced in code before anything is changed** (`_is_toc_structural_role`,
`semantic_blocks.py:397`, is only the consumer; the roles arrive from
`get_effective_structural_role`).

### Finding 3 — what the wrong rule is accidentally getting right

The same mis-tagging is currently the *only* thing removing endnote and index material: The Value of
Everything blocks 245–312 (endnotes, each ending in a URL) and Rethinking Money blocks 278–333 (index
entries) are excluded as `toc_entry`, partially and by accident — only those blocks that happen to end
in a digit. So fixing Finding 2 in isolation will make the audiobook *worse* by restoring index and
endnote text to the narration. Findings 2 and 3 must land together, or the region exclusion must land
first.

### Finding 4 — the artifact validator is all-or-nothing over the whole book, and it trips on prose

Found during the step-1 code review, verified by running the live patterns on 2026-08-04.

`_validate_narration_artifact_text` (`pipeline/narration_postprocess.py:121`) is applied **once, to the
joined narration text of the entire book** (`late_phases.py:1149`). On a standalone audiobook run a
single match anywhere takes the `else` branch at `late_phases.py:1183`: `latest_docx_bytes=None` and
`emit_failed_result` — **the whole artifact is lost after the full LLM spend**, over one sentence.
There is no per-chunk fallback, no retry, no "drop the offending chunk". On edit/translate the base
result is preserved and the narration is simply omitted (`:1158`), which is the sane half.

Four of the six patterns match ordinary prose. Run against the live patterns:

| sentence | verdict |
|---|---|
| «В Веймарской республике (Германия, 1923) деньги обесценивались ежедневно.» | fails `inline_citation` |
| «Это случилось в тот год (Берлин, 1923 год), когда цены удваивались.» | fails `inline_citation` |
| «Издательство присвоило книге ISBN и отправило её в печать.» | fails `isbn` |
| «Он опубликовал препринт на arXiv, и через неделю о нём говорили все.» | fails `arxiv` |

`isbn` and `arxiv` are bare word matches (`\bisbn\b`), so *mentioning* either concept in narrated prose
fails the run. `inline_citation` matches any parenthesis holding a capitalised word, a comma and a
year — the normal way to write a place and a date in a book about monetary history, which is three of
the four books in this corpus.

Scale on real material (imported text of the four books, `.run/footnote_import_measure/*.raw.md`):
**4 / 65 / 196 / 178 `inline_citation` matches per book**, plus 3 and 1 `isbn`. Most are bibliographic
in shape (`(New York: Doubleday Currency, 1994)`) and sit in the very regions Finding 1 is about, but
the sample also contains true inline citations in body text (`(Doran, 2009)`, `(Thomson Reuters,
2011)`). So today the model must strip every one of ~200 constructions, one block at a time, with zero
misses, or the run returns nothing.

This is the same defect class as the Unicode-superscript rule removed on 2026-08-03 (PR #29), and the
comment that replaced it states the principle already: *removing reference markers is the prompt's
job, not a glyph gate's.* The region exclusion of Finding 1 removes most of the exposure by taking the
material out before the model sees it; what is left is the question of whether a deterministic gate
should be able to destroy a paid run at all, or should surface the violation as review data the way
formatting coverage does. **That last part is an owner decision, recorded here, not taken.**

### What this changes about the plan

The missing piece is not "add footnotes to the list". It is that the region-detection half of
`_resolve_narration_include` does not work on real documents at all, while the role half is
over-firing on prose. The nearest working precedent in this repository is the region family in
`validation/formatting_coverage.py` (`_resolve_references_region_start`, `_resolve_bounded_toc_region`),
which Constitution VII names explicitly and whose generic structural-anchor lexicon it blesses as an
accepted, extensible residual rather than a per-book literal. Start there rather than tuning the
thresholds in `semantic_blocks.py`.

**Index is deliberately not in scope.** The owner named the table of contents, footnotes and sources.
Rethinking Money's tail is an index and reads terribly aloud, but adding it is an owner decision, not
an inference — recorded here so it is not lost.

## Plan

0. **Measure before writing — DONE 2026-08-04**, see the section above. It changed the task: the work
   is not adding footnotes to a working rule, it is a region rule that has never fired plus a role
   rule that drops prose.
1. **Code review of the mode**, the way spec 052 was reviewed: what the pass can and cannot do, where
   the two entry points diverge, what is dead, what is unreachable from the UI.
2. **One run on a real book**, with the cost recorded.
3. **Eyes-on the result** — the owner reads it, and the material is prepared for that, not summarised
   away. `artifacts/literary_edit_first_run/comparison_paragraphs.md` is the format that worked:
   before and after, quoted, random sample with a fixed seed plus both extremes.
4. **Count the manual post-editing** a person would still have to do, by class, and decide from that.

## Non-goals

- No formula parsing, no math recognition.
- No new detector for a region that cannot be identified without guessing — Constitution VII applies
  here exactly as everywhere else: region, structural role or form, never a word list or a string
  taken from one book.
- No third narration mode, no per-block tuning knobs.
- Do not chase edge cases. The owner has been explicit about this twice; the measure of success is
  the manual editing removed, not the defects enumerated.

## Anti-regression (mandatory, once implemented)

1. A region that cannot be identified is kept, not cut — a prose paragraph never disappears because
   it resembled a bibliography entry. **Already violated by current code, see Finding 2**: the named
   prose blocks must be present in the narration after the fix, asserted per book.
2. A block the prompt legitimately empties does not come back as a placeholder in the artifact.
3. Both entry points behave the same: what the standalone operation drops, the optional post-pass
   drops too.
4. The measured manual-editing count on the corpus book does not increase.
5. **No fix is credited by a unit test alone.** Every change to the exclusion is measured with
   `scripts/measure-narration-exclusion.py` on all four books, before and after, and the numbers are
   recorded. A synthetic fixture whose every line is bibliography-like proves the arithmetic and
   nothing else — that is exactly how Finding 1 stayed invisible (Constitution VIII).
6. Fixing the over-firing role rule (Finding 2) must not silently restore the index and endnote text
   it is currently removing by accident (Finding 3): the net excluded-character share per book is
   reported before and after, and a drop in it is a finding, not a pass.

## Changelog

- **2026-08-04** — step 0 executed and the findings written up. Three findings recorded: the
  bibliography-tail exclusion has never fired on any book (anchor overshoots the region, and the
  region test cannot pass on real wrapped text); real body prose is already dropped from the
  narration via an over-firing `toc_entry` role; and that same mis-tagging is the only thing currently
  removing index and endnote material. Status moved READY → IN PROGRESS. Anti-regression items 5 and 6
  added. Measurement tools added to the repository:
  `scripts/measure-narration-exclusion.py`, `scripts/probe-bibliography-tail.py`.
- **2026-08-04** — Finding 4 added from the step-1 code review: the artifact validator gates the whole
  book on a single match, kills a standalone run outright, and four of its six patterns fire on
  ordinary prose (verified by running the live patterns; ~200 matches per book in the corpus). Whether
  a deterministic gate may destroy a paid run is raised as an owner decision, not decided.
