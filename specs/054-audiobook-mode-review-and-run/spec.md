# Feature Specification: Audiobook mode — review it, run it once, and stop making the listener's editor work

**Feature Branch**: `[054-audiobook-mode-review-and-run]`

**Created**: 2026-08-04

**Status**: **READY — approved by the owner on 2026-08-04, not started.** Deliberately scheduled as
its own session so it gets a clean context. This spec is the brief: everything below is what the next
session would otherwise have to rediscover.

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

## Plan

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
   it resembled a bibliography entry.
2. A block the prompt legitimately empties does not come back as a placeholder in the artifact.
3. Both entry points behave the same: what the standalone operation drops, the optional post-pass
   drops too.
4. The measured manual-editing count on the corpus book does not increase.
