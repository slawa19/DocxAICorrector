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

**This already violates anti-regression 1 of this spec, before a line of new code is written.**

**The mechanism, traced on 2026-08-04 and verified independently by reading the code.** The first
guess — "a short block whose last line ends in a digit, made worse by PR #20's superscripts" — is
**refuted by measurement**: it accounts for 16 of the 72, and stripping the superscript marker changes
the verdict on only 2 of the 55 blocks tagged by the offending path. The real rule is cruder.

`document/extraction.py:968` `_is_toc_candidate_text` is the whole test:

> a line is a table-of-contents entry if it is ≤160 characters, has 1–16 words, and **does not end in
> `.` or `;`**.

No "Contents" header, no dot leaders, no trailing page number, no region — pure shape, which is
precisely what Constitution VII forbids. The Bernice Hill paragraph qualifies because it ends in a
quotation mark. Three consequences make it worse than a mis-tag:

1. **The line break it splits on is invented by the reader.** `extraction.py:891`
   `_build_compact_toc_run_cluster_text` re-renders a paragraph's run clusters as `line1<br/>line2`
   when the source DOCX has no break there; `_normalize_inline_break_paragraphs` (`:713`) then splits
   on that synthetic break and `_expand_inline_break_paragraph` (`:986`) tags both halves. Measured:
   18 of 24 expanded paragraphs in Rethinking Money and 21 of 21 in The Value of Everything come from
   a break that does not exist in the source.
2. **The role is binding, not advisory.** `_apply_or_hint_stage0_toc_role` (`:1030`) with
   `signal_only=False` writes `structural_role` *and demotes a real heading to body*. Verified on all
   190 paragraphs of the 72 blocks: every one carries the binding role, surviving into `post_ai_final`.
3. **Origin separates almost cleanly from the correct path.** Of the 72 blocks, 55 are tagged by this
   unanchored path and 17 by the region-anchored `_annotate_toc_region_candidates` (`:999`, requires a
   "Contents" header paragraph plus ≥2 consecutive candidates after it — the code's
   `look_ahead - index >= 3` counts the header itself, and this line said "≥3 candidates" until it
   was corrected on 2026-08-04). **All 17 mis-classified prose blocks and 11 of
   12 epigraphs come from the unanchored path; 16 of the 19 genuine tables of contents come from the
   anchored one.** Classification of all 72 (blocks/chars): real TOC 19/2 794, index 7/638,
   notes & sources 17/1 811, epigraph or attribution 12/1 110, ordinary prose 17/1 701.

**Blast radius — this is not an audiobook-only defect.** The block set is identical across operations:

| operation | what happens to the mis-tagged prose |
|---|---|
| audiobook | **deleted** — absent from the narration artifact |
| translate | sent to the model under the `toc_translate` prompt variant (`block_execution.py:196`) |
| edit / literary_polish | **`passthrough` — copied verbatim, never sent to the model at all** |

Two further consequences on every operation: the optional ElevenLabs post-pass drops the same blocks
on a translate/edit run, because `narration_include` does not depend on the operation; and a
TOC-routed block on translate is validated with `TOC_PARAGRAPH_COUNT_TOLERANCE = 0`
(`pipeline/toc_block_validation.py:31`) — if the model merges the two lines of what is really one
prose sentence, the block fails, and after `TOC_VALIDATION_RETRY_BUDGET = 2` the **whole run raises**
(`block_execution.py:530`). Reachable by code, not observed live. Finally, `semantic_blocks.py:568`
forces a block boundary at every structural-kind crossing, so Rethinking Money block 28 is a 108-char
island between blocks of 1 395 and 3 325 characters, severed from its own continuation.

**Fix direction (decided, not yet implemented):** stop `_expand_inline_break_paragraph` from writing
the role on its own authority; keep the `<br/>` splitting. The region-anchored pass re-derives 16 of
the 19 genuine TOC blocks, so almost nothing real is lost, and the anti-vacuum counter-proof is
checkable on the corpus rather than only in a fixture. Do **not** tighten the punctuation test — it
would fix 2 of 55 and would be the same shape heuristic in new clothes.

### Finding 3 — what the wrong rule is accidentally getting right, and how little it is

The same mis-tagging is currently the only thing removing any index or endnote material. **Quantified
on 2026-08-04, and it is negligible:** of the 141 516 characters in those regions it removes 24 blocks
/ 2 449 characters — **1.7%**. Rethinking Money's index 2.8%, The Value of Everything's endnotes 2.0%,
its bibliography 0.3%.

Fixing the role therefore returns 55 blocks / 5 378 characters to the narration: 2 737 characters of
prose and epigraph (the win), 2 449 of reference material (the regression), 192 of genuine in-chapter
contents lists. **This is not a reason to sequence the two fixes**, which is what anti-regression 6
originally implied — the expected drop in `excluded_char_share` is simply explained rather than
treated as a failure.

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

- **2026-08-04** — **The synthesised `<br/>` is gone** (same branch `fix/054-toc-role-unanchored`, on
  purpose: shipped alone, either half makes the output worse). `_build_compact_toc_run_cluster_text`
  re-rendered a `role="body"` paragraph's run clusters as `segment<br/>segment` when the source
  carried no break at all, and `_normalize_inline_break_paragraphs` then split the paragraph on the
  invention. It and its two only callees, `_extract_compact_run_clusters` and
  `_is_compact_toc_run_cluster`, are deleted — 63 lines, no remaining consumers. Their thresholds
  (≥2 segments; at exactly 2, ≤20 words total, min ≥3, one ≥4 or a heading signal; otherwise ≤14
  total and each ≤5) were never measured: `897d485` brought `160/16` from a single Mazzucato run,
  `82c6225` brought `2/14/3/4/5` with a fixture built from one observed example, `36a4751` raised 14
  to 20 with a second. Constitution VII, literally: no signal in the source, no repair — a paragraph
  the PDF importer delivered whole now stays whole, and the merged line is an ACCEPTED defect.
  **Measured, offline, on all four books before and after.** The narration decision is unchanged to
  the block: 296/384/304/288 blocks, 59/59/58/104 excluded, `toc_structural_role` 6/7/3/1,
  `reference_region` 10/9/0/61, `excluded_char_share` 7.4%/5.7%/0.4%/16.0% — identical in both runs,
  same block indexes, same texts, with a single 2-character difference (The Value of Everything's TOC
  block 5, 250→248 chars, where two entry pairs merged inside a block that stays excluded). All 17
  genuinely-excluded TOC blocks survive, and the four prose blocks named in Finding 2 are all
  `narration_include=True`, each inside its own continuation (Rethinking Money's Bernice Hill
  sentence arrives as ONE paragraph instead of two halves, inside a 4 831-character block).
  **`<w:br/>` on the PDF path does not exist** — measured, not assumed: the bridge
  `_append_pdf_text_paragraph_to_docx` (`processing/processing_runtime.py:1015`) writes only a style
  name and bold/italic, and with the synthesis removed inline-break expansions on all four PDFs go
  7/7/24/21 → **0/0/0/0**. So 100% of PDF splitting was invented. Paragraph counts fall
  1435→1426, 1836→1829, 2290→2265, 2314→2293. On native DOCX, where real breaks exist, the effect is
  small and the real breaks are untouched: expansions 18→11, 32→32, 11→10, 11→6, 5→4 (Money &
  Sustainability, Creating Wealth, Ukraine, Rethinking Money, The Value of Everything) — Creating
  Wealth does not move at all because all 32 of its splits are genuine `<w:br/>`.
  **Golden fixtures (spec 029) regenerated once, at the end, and the leaf comparison is the point.**
  Three of five are **byte-identical** (Creating Wealth, Rethinking Money, The Value of Everything).
  Two changed: Money & Sustainability `mapped_count` 467→465 and Ukraine 468→465 of 500. Attribution,
  leaf by leaf: **of 106 and 184 source paragraphs whose mapping outcome changed, ZERO have an
  unchanged `paragraph_id`, and zero paragraphs changed `role`, `structural_role` or `heading_level`
  at all.** The harness picks each paragraph's synthetic perturbation from `sha1(paragraph_id)`
  (`tests/test_formatting_mapper_golden.py:57`) and `paragraph_id` is positional, so merging one
  paragraph renumbers 227 / 444 later ones and hands the mapper a different synthetic problem for
  each. The delta is the fixture harness re-rolling itself, not the mapper. The one real content
  change per book is the merge: "Former World Bank economist Herman Daly" + "proposes three
  conditions for a society to be physically sustainable:" become one sentence (an improvement), and
  Ukraine's OCR'd "General Summary Introduction" / "» о" / "Terrain Features" become one line (the
  accepted cost — `Terrain Features` was unmapped before and is inside a mapped paragraph now).
  **Honest negative — the fragmented headings this change was expected to repair are NOT repaired.**
  Creating Wealth's "CREATING / WEALTH", "False Assumption #1: / The Economy is Beyond Our Control"
  and "Demand for / Profitable / Investments" are split by a **real `<w:br/>` in the source DOCX**
  (verified in `word/document.xml`, paragraphs 2, 17, 249, 342, 343), not by the synthesis, so its
  fixture is byte-identical and its `"Heading 2"` count stays 36. On `main` those paragraphs were
  already split — they were merely styled `Normal`, because the role write demoted them. The
  remaining defect is therefore a different one, recorded rather than patched: **splitting a
  `role="heading"` paragraph on a genuine inline break yields N headings where the document has
  one.** `_should_expand_inline_break_paragraph` (`document/extraction.py:887`) admits `heading`,
  and nothing rejoins the halves afterwards. Fixing it means deciding what a break inside a heading
  means, which is a separate decision and is not taken here.
  Two documentation errors corrected in the same commit: `_annotate_toc_region_candidates` requires
  `look_ahead - index >= 3` **counting the header itself**, i.e. a header plus **≥2** entries, not
  "≥3 consecutive candidates" as this spec's Finding 2 and the `_expand_inline_break_paragraph`
  docstring both claimed; and that docstring's "the break is a line boundary the reader observed"
  was false for the synthesised path and is true only now.
- **2026-08-04** — **Finding 4 fixed** on `fix/054-narration-validator-not-a-gate` (PR #33, branched
  from `main` because it touches disjoint files). `_validate_narration_artifact_text`, which raised,
  becomes `_collect_narration_artifact_review_findings`, which returns and never raises: the artifact
  is delivered on both entry points and the residual is published as review data — a WARNING
  `narration_artifact_review_data` event with per-rule counts and at most three truncated samples, the
  review counters on `ui_audiobook_artifact_saved`, and a `result.narration_review_data` notice. This
  is Constitution VII's formatting-coverage precedent applied to the same shape of check. `isbn` and
  `arxiv` were bare word matches, so narrating a sentence *about* publishing failed the run; they are
  now keyed on the identifier's form, mirroring the neighbouring `doi` rule, and measured over the
  corpus the bare word and the new rule both hit 1/0/3/0 per book — no signal lost. Honest caveat:
  `arxiv` never fired on this corpus in either form, so its tightening rests on form-symmetry, not
  evidence. `inline_citation` is left imprecise **by decision** — making it exact would need a list of
  names, cities or publishers, which Constitution VII forbids — and with ~191 hits on one book the
  notice will fire on essentially every real run; if that is noise, the lever is the notice threshold,
  not the rule. `narration_cleanup_projection_unsafe` is a different class and is untouched, including
  its standalone failure branch. Old behaviour was proven before the change rather than assumed: the
  new tests were written first and all four prose sentences returned `failed` on a standalone run.
- **2026-08-04 — OPEN, needs the owner's sign-off: the formatting-mapper golden fixtures were
  regenerated.** This is the one place in this iteration where the yardstick moved rather than the
  code, so it is recorded as a decision rather than folded into the Finding 2 entry.
  `UPDATE_FORMATTING_MAPPER_GOLDEN=1` is documented only in the test's own docstring
  (`tests/test_formatting_mapper_golden.py:17-20`, "after an intentional, reviewed behavior change")
  and **appears in no spec, no doc, and not in `AGENTS.md`** — so the gate authorises its own
  regeneration and "reviewed" is the only guard, naming neither the reviewer nor the evidence
  required. Spec 029 scopes byte-identity to its own optimisation levers (`spec.md:10`, `:41`, `:93`),
  not to a permanent freeze, so the regeneration is formally allowed; whether it is *warranted* is the
  owner's call. Evidence gathered for that call, after a leaf-by-leaf comparison of all five fixtures
  (not counters — the first pass compared counters only, and said so): **exactly one degradation in
  mapping outcome across every regenerated fixture** — the Ukraine OCR document's `p0032` "Terrain
  Features" loses its mapping (`mapped_count` 469→468) because a spurious TOC relation used to carry
  it through a fallback. `bad_pair_count` is 0 before and after on every book; Rethinking Money's
  fixture is byte-identical. Everything else that moved is attribution, not outcome: spurious
  `toc_region` relations disappear, strategies shift off the TOC fallbacks onto exact matching, and
  `style_name` changes `Normal`→`Heading 2` on exactly the paragraphs whose heading role was restored.
  One improvement missed by the first report: on The Value of Everything four fragmented `toc_region`
  relations collapse into one whose members move from the **cover page** (`p0000–p0007`) to the
  **actual table of contents** (`p0012–p0080`). **If the owner reads the 029 gate as a hard freeze
  regardless of cause, the fixtures must be reverted and PR #34 left red until that is resolved.**
  Worth closing regardless of the answer: the regeneration procedure should state what evidence a
  regeneration must carry, in a place that is not the test that authorises it.
- **2026-08-04** — **Finding 2 fixed** on `fix/054-toc-role-unanchored`, branched from
  `fix/054-narration-region-exclusion`. `_expand_inline_break_paragraph`
  (`document/extraction.py:986`) no longer writes a structural role: it splits on the inline break
  and returns, and the `signal_only` parameter is gone with the role write. The splitting, the
  `<br/>` detection and `_annotate_toc_region_candidates` are untouched. Measured offline on all
  four books (`scripts/measure-narration-exclusion.py` equivalent, plus a tagger-origin probe;
  raw output `.run/narration_exclusion/unanchored_before.json` / `unanchored_after.json`):
  `toc_structural_role` exclusions **13/14/25/20 -> 6/7/3/1**, i.e. 72 -> 17 over the corpus, and
  the unanchored tagger now makes **zero** calls while the region-anchored tagger makes exactly
  the same calls as before (28/24/21/8 entries, 1/1/2/1 headers). `excluded_char_share`
  7.50%/5.79%/0.79%/16.05% -> 7.38%/5.67%/0.38%/16.02%; the drop is the 5 378 characters
  Finding 3 predicted, explained rather than a pass. **Anti-vacuum counter-proof on the real
  corpus:** of the 19 genuine table-of-contents blocks / 2 794 characters, **16 / 2 602 are still
  excluded**; the three that are not are the small in-chapter contents lists the trace predicted
  (Money & Sustainability "Doraland p.142 / Wellness Tokens p.144 / Natural Savings p.151" and
  "C3 on a regional or national scale p.155 / TRC on a global scale p.158", The Value of Everything
  "Stories about Value Creation / Where Does Innovation Come From?" — 192 characters in total),
  none of which carries a Contents header or a region. All 17 prose blocks and 11 of the 12
  epigraphs return, including the four named in Finding 2, and each is reunited with its own
  continuation (Rethinking Money block 28's 108-character island is now inside a 4 832-character
  block). Blast radius, measured per operation: on **edit / literary_polish** 55 blocks / 5 378
  characters per corpus stop being `passthrough` and reach the model for the first time
  (7/7/22/19 blocks per book, +666/+668/+2 205/+2 047 characters), while the number of model
  calls *falls* (251->247, 340->334, 262->246, 268->245) because the blocks merge; on
  **translate** `toc_dominant` drops 13/14/25/20 -> 6/7/3/1, so those blocks leave the
  `toc_translate` prompt variant and the `TOC_PARAGRAPH_COUNT_TOLERANCE = 0` validator that can
  fail a whole run. Two consequences recorded rather than patched: the formatting-mapper golden
  fixtures (spec 029) were regenerated for four of five books — no source text changed, but the
  spurious `toc_region` relations disappear (4->2, 15->0, 4->1, 4->0) and 23 real headings across
  three books regain `role="heading"` (Creating Wealth's "False Assumption #1: / The Economy is
  Beyond Our Control", The Value of Everything's "Value in the Eye of the Beholder: The Rise of the
  / Marginalists") against one lost to a cover-title variant; and on the Ukraine document one
  OCR'd body line (`p0032`, "Terrain Features") loses its formatting mapping because a spurious
  TOC relation used to carry it (mapped 469 -> 468 of 500). `structure_repair.py:227` does **not**
  start firing: its call counts are byte-identical before and after on all four books.
- **2026-08-04** — Finding 2 corrected after the mechanism was traced, and Finding 3 quantified. The
  "short line ending in a digit" hypothesis is **refuted** (16 of 72; stripping the superscript
  changes 2 of 55): the real rule is `extraction.py:968` `_is_toc_candidate_text` — ≤160 chars, 1–16
  words, does not end in `.` or `;`. Three aggravating facts recorded: the `<br/>` it splits on is
  synthesised by the reader from run clusters, the role it writes is binding and demotes real
  headings, and the defect reaches translate (TOC prompt variant plus a zero-tolerance validator that
  can fail a whole run) and edit (blocks copied verbatim, never edited) — not only audiobook. Finding
  3 measured at 1.7% of the reference regions, so anti-regression 6 no longer implies an ordering
  between the two fixes. Fix direction chosen: remove the role write from the unanchored path, keep
  the splitting; the region-anchored pass already re-derives 16 of the 19 genuine TOC blocks. Latent
  issue recorded, not firing on this corpus: `structure_repair.py:227` tags look-ahead candidates
  before testing the ≥3 region-length condition, so a rejected region leaves its tags behind.
- **2026-08-04** — **Finding 1 fixed** on `fix/054-narration-region-exclusion`. Both causes were
  structural, so both mechanisms were removed rather than tuned:
  `_resolve_bibliography_tail_indexes` (last-heading anchor + 70% bibliography-like-lines region
  test) is replaced by `_resolve_reference_region_indexes`
  (`document/semantic_blocks.py:540`), which anchors on a bare back-matter section title carried
  by a heading paragraph — reusing the `_BACKMATTER_SECTION_TITLES` lexicon from
  `validation/formatting_coverage.py` that Constitution VII blesses, minus the index titles —
  and bounds the region by outline depth (the next heading at the anchor's level or shallower;
  an unlevelled heading, or an outline that never closes, ends the region early). Measured on
  all four books, before → after excluded characters: Money & Sustainability 0.46% → 7.5%,
  Creating Wealth 0.46% → 5.8%, The Value of Everything 0.42% → 16.1%, **Rethinking Money
  0.79% → 0.79% — an honest negative**: it carries no bare back-matter section title, so no
  region is identified and nothing is cut. The prose blocks named in Finding 2 are unchanged
  (still dropped by the `toc_structural_role` branch, not by the region branch), and the
  `toc_structural_role` and `image_only` counts are identical before and after on all four books,
  so anti-regression 6 holds. Known over-cut, recorded rather than patched: on Money &
  Sustainability the region reaches two blocks of Triarchy Press advertising (blocks 300-301)
  that PDF import placed one outline level below `Bibliography`. Known under-cut: Creating
  Wealth's `Appendix` notes and the whole `Resources` list before its `Notes` heading stay in.
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
