# Feature Specification: Reader cleanup — what to fix before its first production run

**Feature Branch**: `[052-reader-cleanup-first-production-run]`

**Created**: 2026-07-31

**Status**: **PROPOSED — awaiting a go/no-go decision on scope.** The reader-cleanup pass has never
run in the production UI: its toggle was dead until spec 047 fixed it, so every real-world execution
so far has been an offline replay. Before the owner spends a full book on it, this spec records what
the pass actually is, what it cannot be, and the short list of defects worth fixing first. Nothing
here is implemented yet.

**Date**: 2026-07-31

**Owner surface**: `reader_cleanup_mvp/*`, `pipeline/reader_cleanup_postprocess.py`,
`pipeline/reader_cleanup_rebuild.py`, the delivered DOCX

**Companion**: `specs/047-reader-cleanup-production-parity/spec.md` (made the toggle real);
`specs/051-round12-premerge-remediation/spec.md` (the diagnostics-evidence gate this pass depends on)

## The finding that changes the goal

**This pass cannot rewrite wording. Not "does not by default" — cannot, by construction.**

The owner's stated goal is maximum readability: remove residual garbage, *polish phrasing where
needed*, tidy formatting. The first two are in scope. The third is not, and no prompt can add it.

Every one of the seven operations either deletes a block or rearranges text the source already
contains, and each is verified against the original characters before it is applied:

- `reclassify_role` rejects itself outright if the visible text would change —
  `reclassify_would_change_visible_text` (`reader_cleanup_mvp/_apply.py:653`).
- `split_block` requires its substrings to cover the block exactly, with no remainder
  (`_apply.py:391`).
- `extract_side_heading_and_reattach_body` compares the character multiset before and after
  (`_apply.py:536`).
- `remove_inline_noise` deletes one exact substring and demands ≥20 non-space characters survive
  (`_validate.py:24`).

The model does emit a free-text field, `expected_after_preview` — but it is only ever used as a
cross-check that the model and the code agree; a mismatch **rejects** the operation
(`_apply.py:647`). The delivered text is always computed by code from the original. There is no path
by which a sentence the model wrote reaches the document.

So the honest framing is: this pass is a **structural janitor**, not an editor. Asking it to polish
prose would require a different pass that does not exist — one that accepts model-authored text,
which is a much larger and riskier thing to build (it would need its own faithfulness gate, because
nothing would then guarantee the translation still says what the source said). **That is not
proposed here.** The decision to want it or not is the owner's, and it should be taken separately,
with eyes open, not smuggled in as "improve the prompt".

## What the pass can actually do

Seven operations (`reader_cleanup_mvp/_constants.py:32`): delete a block; remove an exact inline
noise substring; split a block; join a fragmented paragraph with the next one; separate a heading
fused to its body; pull a side-heading out of a sentence and reattach the remainder; and flip a
block's role marker.

Measured on the three real replay runs already in `.run/reader_cleanup_faithful_replay/`:

| Book | Proposed | Accepted | Characters deleted | `reclassify_role` accepted |
|---|---|---|---|---|
| creating_wealth | 39 | 34 | 440 of 569 000 (0.09%) | 1 |
| lietaer | 111 | 44 | 0 | 2 |
| mazzucato | 16 | 12 | 110 of 804 000 (0.014%) | 0 |

Lietaer is worth reading twice: the model proposed 49 deletions, they exceeded
`max_delete_block_ratio = 0.03`, and the code rolled back **every deletion at once**
(`_apply.py:162`). The report still says "44 accepted" — but not one character was removed. The
safety limit worked exactly as designed; the reporting makes it invisible.

## What it costs

Chunking is by characters, 8 000 per chunk (`_constants.py:149`), with 3 read-only blocks of context
on each side. Measured on the real books:

| Book | Blocks | Requests | Payload characters | ≈ input tokens |
|---|---|---|---|---|
| creating_wealth | 1 672 | 75 | 2.77 M | ~1.11 M |
| lietaer | 1 898 | 70 | 2.73 M | ~1.09 M |
| mazzucato | 2 099 | 107 | 4.01 M | ~1.60 M |

The payload is **~5× the size of the book itself**, and the largest single component is not the text:
`operation_selection_targets` is 36.4% of it, of which 89% is boilerplate — 1 403 of 1 419 targets are
`side_heading_island_candidate`, each carrying the same ~1 000 characters of `safety_note` /
`stub_continuation_risk` / `reattach_expected_after_preview_shape` prose
(`_detectors.py:341-353`). The same paragraph of instruction, repeated a thousand times, instead of
once in the system prompt. Meanwhile `targets[:20]` (`_detectors.py:32`) truncates 28% of chunks, so
blocks near the end of a chunk systematically get no hints at all.

**Model resolution is a trap.** `config.toml:66` sets `reader_cleanup_model =
"anthropic:claude-sonnet-4-6"`, and the code default is only consulted when that is empty
(`_config.py:24`). The repository `.env` overrides it to `openrouter:anthropic/claude-haiku-4.5` —
which is what all three replay runs actually used — but `.env.example:39` ships the value **empty**.
An operator who enables the pass by copying the example gets Sonnet, at many times the cost, without
being told.

## The owner's heading hypothesis

**Verdict: technically real, currently useless, and — as the prompt is written today — a Constitution
VII violation. All three are fixable, but not by prompt wording alone.**

*It works mechanically.* `reclassify_role` with `target_role="heading"` rewrites the block as `## text`
(`_apply.py:658`), and because the changed path rebuilds the DOCX by running pandoc over the whole
markdown (`reader_cleanup_rebuild.py:88`), that `##` becomes a genuine Word `Heading 2`.

*It is useless in practice.* The level is hardcoded to H2 (`_constants.py:43`) with no hierarchy;
multi-line blocks are refused (`_apply.py:642`); only `paragraph` and `blockquote` are eligible
(`_validate.py:427`); and the observed yield is 1, 2 and 0 accepted reclassifications per book.

*Two delivery holes would make a run inconclusive even if the model got it right.* The registry
derivation handles `delete_block`, `join_fragmented_paragraph` and the four text operations, and
lets `reclassify_role` fall through to `skipped_operations`
(`reader_cleanup_rebuild.py:726`) — so the registry entry still reads `Заголовок` while the markdown
now reads `## Заголовок`. Text matching does not strip heading markers, so that entry loses its
paragraph indexes and its formatting degrades. Worse, the new heading is not in the protected set of
`normalize_false_fragment_headings_markdown` (`output_validation.py:1779`), so display hygiene can
merge it straight back into the previous paragraph — silently. A correctly restored heading can
therefore disappear before delivery, and the hypothesis would be buried by a delivery defect rather
than judged on its merits.

*The constitutional problem, stated plainly.* Constitution VII forbids reconstructing structure from
the shape of the text — "a leading ordinal, capitalisation, length, position", and "no source signal,
no repair". The production prompt instructs exactly that: *"ALL-CAPS short text after a heading may be
attribution"*, *"a short topic-introducing line may be heading when the surrounding prose shows it
starts a new topic"* (`_prompts.py:19`). That is capitalisation, length and position — three of the
four named prohibitions.

*But the lawful version is already half-built, and nobody wired it up.* Real layout evidence from the
source — `font_size` versus `body_font_size`, `left_indent`, `first_line_indent`, `alignment`,
`centered`, `superscript` — is already extracted (`reader_cleanup_rebuild.py:365`), already attached
to each block (`_blocks.py:42`) and already serialised into the payload (`_models.py:67`).
**The production prompt never mentions it once.** A second, unused prompt
(`_prompts.py:156-178`) is built entirely on those signals and carries the right default: *"Never
infer heading/list/footnote from text alone when layout/context evidence is weak; default to body."*
Its entry point `run_reader_cleanup_reannotation` (`service.py:474`) is referenced only by the
package exports and tests — the pipeline never calls it.

So heading restoration by *reading a source signal* is constitutional and reachable. Heading
restoration by *guessing from text shape* is neither, and is what is wired up today.

### Measured: on PDF books the layout signal is not there

That measurement has now run — `specs/053-short-heading-evidence-measurement/spec.md`. The short
version, and it is decisive for this spec:

The `layout_signals` this pass receives are read from the formatting registry, which is derived from
the **intermediate DOCX**. For a PDF upload that DOCX is written by
`_append_pdf_text_paragraph_to_docx` (`processing/processing_runtime.py:1015`), which emits a style,
the text and per-run `bold`/`italic` — **no spacing, no alignment, no font size**. So on PDF books the
lawful, evidence-based route is starved at the source: the prompt could ask for layout evidence all it
likes, and the payload would carry almost none.

Spec 053 also measured which signals actually discriminate, and the answer reframes the problem: font
size discriminates **nothing** (0 of 30 lost headings had a font larger than their neighbours), while
vertical gap asymmetry does (80% versus 2% in the control). ALL-CAPS is an **anti**-signal — three
times more common in junk than in real headings — so the current prompt's "ALL-CAPS short text may be
attribution" rule is not merely unlawful, it points the wrong way.

**Consequence — settled by the owner on 2026-07-31: item 8 is dropped and `reclassify_role` is switched
off for the run.** Restoring headings during reader cleanup is blocked by the same serializer that
blocks the import-stage rule — one root cause, two starved consumers — and the owner has accepted that
as the ceiling of PDF input (spec 053). With no layout evidence reaching the model on PDF books, the
operation's only remaining basis would be the text-shape guessing Constitution VII forbids, and its
observed yield is 0–2 per book. So it is disabled rather than reasoned about.

**This turns out to need a small code change, which is item 9.** `reader_cleanup_allowed_operations`
is read from `app_config` (`_config.py:70`) and an empty value means *allow everything*
(`_detectors.py:11`) — but the key exists nowhere in the production config model (`core/config.py`
carries `reader_cleanup_default`, `_model`, `_chunk_size`, `_overlap_*`, `_global_plan_enabled`,
`_max_failed_chunk_ratio`, and no `_allowed_operations`). Only a validation run profile can set it
(`validation/profiles.py:100`). So today a production run **cannot** restrict the operation set at all.
The mechanism exists; it is simply not wired to the path we intend to run on.

## Proposed: fix before the first run

Ranked by effect per unit of work. Each is justified statically or from existing artifacts — none of
them needs the run to have happened.

1. **Pin the model explicitly.** Fill `DOCX_AI_READER_CLEANUP_MODEL` in `.env.example`, or make
   `config.toml:66` a deliberate choice. (~5 lines.) Otherwise the first production run silently
   costs several times what the replays did.
2. **Lower `max_failed_chunk_ratio` from 1.0 to ~0.1** (`_config.py:57`). At 1.0, 106 of 107 chunks
   can fail and the run still reports `completed` / `changed: true` with no signal. The first run must
   be honest about partial execution, or its result cannot be interpreted. (1 line.)
3. **Move the target boilerplate into the system prompt.** Keep `category`, `id`, `text_hash` and the
   actual substrings per target; state the safety rules once. (~40 lines.) Cuts roughly a third of the
   pass's cost with no behavioural change — the model reads the same rules, just not 1 403 times.
4. **Stop classifying image anchors as `extraction_artifact`.** `_EXTRACTION_ARTIFACT_PATTERN`
   (`_constants.py:76`) matches `[[DOCX_IMAGE_*]]`, so every image anchor is labelled with a `kind`
   that is on the allowed-deletion list, while the prompt tells the model not to touch them. The
   validator currently catches it (`_validate.py:369`), but this is the exact contradiction that once
   cost 20–37 images per book; it should not survive on one check. (~5 lines + test.)
5. **Do not re-append lost image anchors at the end of the document.** `_report.py:166` restores a
   dropped anchor by pasting it at the end — the count reconciles while a chapter-3 figure lands after
   the bibliography. Reject the operation that lost it instead. (~20 lines.)
6. **Narrow `_TOC_LIKE_PATTERN`** (`_constants.py:75`). `\s\d{1,4}\s*$` makes any paragraph ending in
   a number "TOC-like" and immune to every operation: 0.5–4.1% of blocks, up to 60% of them real prose.
   (~3 lines + test.)
7. **Stop sending dead instructions.** The `anchor_repair` branch is unreachable in production yet
   occupies ~10 lines of every one of the 107 prompts, and the empty `global_plan` fields ship on every
   request. (~15 lines.)
8. ~~Handle `reclassify_role` in the registry derivation and protect restored headings.~~
   **DROPPED** by the owner decision of 2026-07-31 — see the heading section above. Heading
   restoration is out of scope; the operation is disabled instead.
9. **Expose `reader_cleanup_allowed_operations` in the production config** so the run can actually be
   restricted to the six janitorial operations, and set it to exclude `reclassify_role`. (~10 lines
   in `core/config.py` + `config_loader_layers.py`, plus a test that an excluded operation is
   rejected end to end.) Without this the previous item cannot be honoured — production has no way to
   turn a single operation off.

Also drop the role-inference rules from the production prompt (`_prompts.py:19`), which are now dead
weight in every one of the ~107 requests and, worse, teach the model that ALL-CAPS suggests a heading
role — spec 053 measured capitalisation as an **anti**-signal, three times commoner in junk than in
real headings. (~5 lines.)

## Explicitly not fixed before the run

These are real, and deliberately left alone until there is a real result to look at: the
`expected_after_preview` divergence (6 cases in 56 operations across three books); the ≤12-character
silent loss in `normalize_heading_boundary` (`_apply.py:624`) whose threshold was tuned against a
specific regression; the hardcoded `##` and missing heading hierarchy; the fact that `attribution`,
`caption` and `body` are indistinguishable (`_apply.py:664`); the duplicated `ignored_delete_blocks`
in the report; and the chunk size and overlap — changing 8 000 / 3+3 now would throw away the only
baseline the three replay runs give us.

**Do not delete the dead reannotation path** (`service.py:474`, `_apply.py:185-327`,
`_prompts.py:156-178`). It is the only evidence-based part of the package and is the most likely
foundation for lawful heading restoration.

## Define success before spending the book

The most likely outcome, judging by all three replays, is: the pass runs, costs on the order of a
million input tokens, applies between 12 and 44 operations, and produces a document that looks
essentially unchanged. That is not a failure — but if "success" is not defined in advance, the run
cannot be interpreted, and the temptation will be to tune the prompt until something happens.

Proposed criteria, to be agreed before the run:

- **Honesty:** zero failed chunks, or a visible failure. No silent partial cleanup.
- **Safety:** no image lost or relocated; no text lost beyond what the operations account for; every
  rejected operation explains itself.
- **Effect:** count the defects the owner can actually see — fused headings, broken list items,
  footnote markers glued to body text, page furniture in the prose — before and after, by eye, on the
  same book. Operation counts are not evidence of readability.
- **Cost:** measured tokens and money for one book, against the eyes-on improvement. If the pass costs
  a million tokens to fix four paragraphs, that is a finding, not a disappointment.

## Anti-regression (mandatory, once implemented)

1. A chunk failure rate above the configured ratio fails the pass visibly; it must not report
   `completed`.
2. Image anchors are never labelled with a deletion-eligible `kind`, and a lost anchor rejects its
   operation rather than being re-appended elsewhere.
3. A paragraph of prose ending in a number is not `toc_like`, while a genuine TOC line still is.
4. Trimming the target boilerplate does not change which operations are accepted on the three replay
   books — byte-identical accepted-operation sets.
5. If item 8 lands: a restored heading survives to the delivered DOCX as a real heading style, and its
   registry entry keeps its paragraph indexes.
