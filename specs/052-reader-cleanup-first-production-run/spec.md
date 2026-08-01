# Feature Specification: Reader cleanup — what to fix before its first production run

**Feature Branch**: `[052-reader-cleanup-first-production-run]`

**Created**: 2026-07-31

**Status**: **IMPLEMENTED (2026-07-31) — all nine items landed; the pass is ready for its first
production run, which has NOT been done yet.** The reader-cleanup pass had never run in the
production UI: its toggle was dead until spec 047 fixed it, so every real-world execution so far has
been an offline replay. This spec records what the pass actually is, what it cannot be, and the
defects that had to be fixed before spending a book on it.

Implementation took **three rounds of fixes and three adversarial review passes**, and each round
found real defects in the previous one — see `## What the review rounds found` below. The most
consequential result was not on the original list: the forensic work traced the long-standing
image-anchor P0 (Lietaer losing 37 of 55 images "with zero logged operations") to its actual root
cause and fixed it. Verified on the final tree: full suite **2356+ passed / 0 failed**, canonical
pyright gate at baseline, canonical real-document quality gate green, and the three-book offline
replay byte-identical apart from the changes each fix explains.

**Still owed before the run itself:** agree the success criteria in `## Define success before
spending the book`, and re-enable `DOCX_AI_READER_CLEANUP_ENABLED` (set to `false` on 2026-07-31 so
the pass could not switch itself on as a side effect of merging).

**Date**: 2026-07-31

**Owner surface**: `reader_cleanup_mvp/*`, `pipeline/reader_cleanup_postprocess.py`,
`pipeline/reader_cleanup_rebuild.py`, the delivered DOCX

**Companion**: `specs/047-reader-cleanup-production-parity/spec.md` (made the toggle real);
`specs/051-round12-premerge-remediation/spec.md` (the diagnostics-evidence gate this pass depends on)

## The finding that changes the goal

**This pass cannot rewrite wording. Not "does not by default" — cannot, by construction.**

The owner's stated goal is maximum readability: remove residual garbage, *polish phrasing where
needed*, tidy formatting. The first two are in scope. The third is not, and no prompt can add it.

Every one of the operations either deletes a block or rearranges text the source already contains,
and each is verified against the original characters before it is applied (references re-checked
2026-08-01 against the implemented tree):

- `split_block` requires its substrings to cover the block exactly, with no remainder — the branch is
  at `reader_cleanup_mvp/_apply.py:520-531`, the guard `_ordered_substrings_cover_text` at
  `_apply.py:667`.
- `extract_side_heading_and_reattach_body` compares the character multiset before and after — the
  `Counter` comparison is at `_apply.py:660-663`, inside `_apply_side_heading_reattach_to_text`
  (`_apply.py:616`).
- `remove_inline_noise` deletes one exact substring (`_validate.py:23`) and demands ≥20 non-space
  characters survive (`_apply.py:545`).

There was a seventh operation, `reclassify_role`, and it too refused to change visible text — it
rejected itself through `reclassify_would_change_visible_text`. It was removed outright by item 9
below, so neither the operation nor that function exists any more; the argument stands on the six
that remain.

The model does emit a free-text field, `expected_after_preview` — but it is only ever used as a
cross-check that the model and the code agree; a mismatch **rejects** the operation
(`_apply.py:657-659`). The delivered text is always computed by code from the original. There is no
path by which a sentence the model wrote reaches the document.

So the honest framing is: this pass is a **structural janitor**, not an editor. Asking it to polish
prose would require a different pass that does not exist — one that accepts model-authored text,
which is a much larger and riskier thing to build (it would need its own faithfulness gate, because
nothing would then guarantee the translation still says what the source said). **That is not
proposed here.** The decision to want it or not is the owner's, and it should be taken separately,
with eyes open, not smuggled in as "improve the prompt".

## What the pass can actually do

**Six operations** — `_ALLOWED_OPERATIONS` in `reader_cleanup_mvp/_constants.py:35-42`, advertised to
the model at `_prompts.py:37`: delete a block; remove an exact inline noise substring; split a block;
join a fragmented paragraph with the next one; separate a heading fused to its body
(`normalize_heading_boundary`); and pull a side-heading out of a sentence and reattach the remainder.

A seventh, `reclassify_role`, flipped a block's role marker. It was removed by item 9; the reasoning
is in `## The owner's heading hypothesis`.

Measured on the three real replay runs already in `.run/reader_cleanup_faithful_replay/`. These are
**pre-removal** numbers — they are what the seven-operation pass did, and they are kept because they
are the evidence the removal decision rests on:

| Book | Proposed | Accepted | Characters deleted | `reclassify_role` accepted |
|---|---|---|---|---|
| creating_wealth | 39 | 34 | 440 of 569 000 (0.09%) | 1 |
| lietaer | 111 | 44 | 0 | 2 |
| mazzucato | 16 | 12 | 110 of 804 000 (0.014%) | 0 |

Lietaer is worth reading twice: the model proposed 49 deletions, they exceeded
`max_delete_block_ratio` (default `0.03`, `_config.py:50`), and the code rolled back **every deletion
at once**. The report still said "44 accepted" — but not one character was removed. The safety limit
worked exactly as designed; the reporting made it invisible.

**Fixed since.** The rollback no longer patches the outcome after the fact: `_apply.py:192` now hands
control to `_reapply_without_delete_operations` (`_apply.py:226`), which re-applies the surviving
operation set from scratch, so a rejected deletion is genuinely rejected in the report as well as in
the text. This is the same fix that finally closed the image-anchor P0 — see `## What the review
rounds found`.

## What it costs

Chunking is by characters, 8 000 per chunk (`_DEFAULT_CLEANUP_CHUNK_SIZE`, `_constants.py:181`), with
3 read-only blocks of context on each side. Measured on the real books, before the payload fixes
below:

| Book | Blocks | Requests | Payload characters | ≈ input tokens |
|---|---|---|---|---|
| creating_wealth | 1 672 | 75 | 2.77 M | ~1.11 M |
| lietaer | 1 898 | 70 | 2.73 M | ~1.09 M |
| mazzucato | 2 099 | 107 | 4.01 M | ~1.60 M |

The payload was **~5× the size of the book itself**, and the largest single component was not the
text: `operation_selection_targets` was 36.4% of it, of which 89% was boilerplate — 1 403 of 1 419
targets were `side_heading_island_candidate`, each carrying the same ~1 000 characters of
`safety_note` / `stub_continuation_risk` / `reattach_expected_after_preview_shape` prose. The same
paragraph of instruction, repeated a thousand times, instead of once in the system prompt. Meanwhile a
flat `targets[:20]` cap truncated 28% of chunks, so blocks near the end of a chunk systematically got
no hints at all.

**Both are fixed (items 3 and 7).** `_build_side_heading_island_targets` (`_detectors.py:321-350`) now
emits only `category`, `id`, `text_hash` and `heading_candidate`; the three boilerplate fields no
longer exist anywhere in the package, and the safety rules are stated once in the system prompt. The
flat cap is gone too: `_build_operation_selection_targets` (`_detectors.py:23-36`) fills a serialized
character budget instead (`_OPERATION_SELECTION_TARGETS_CHAR_BUDGET`, `_detectors.py:16`), so
truncation is driven by payload size rather than by an arbitrary count.

**Model resolution was a trap, and that is fixed too (item 1).** `config.toml` set
`reader_cleanup_model = "anthropic:claude-sonnet-4-6"`, the code default was consulted only when that
was empty (`_config.py:25`), and `.env.example` shipped the value blank — so an operator who enabled
the pass by copying the example silently got Sonnet, at many times the cost of the Haiku the three
replay runs actually used. Today `src/docxaicorrector/resources/config.toml:74`, the code default
(`READER_CLEANUP_DEFAULT_SELECTOR`, `_constants.py:13`), `.env:43` and `.env.example:43` all name
`openrouter:anthropic/claude-haiku-4.5`. Copying the example now gets you the model the measurements
were made with.

## The owner's heading hypothesis

**Verdict: technically real, useless in practice, and — as the prompt was written at the time — a
Constitution VII violation. The section is written in the past tense because the operation it analyses
was removed by item 9; the analysis is kept because it is the reason for that removal.**

*It worked mechanically.* `reclassify_role` with `target_role="heading"` rewrote the block as
`## text`, and because the changed path rebuilds the DOCX by running pandoc over the whole markdown
(`_rebuild_docx_for_markdown`, `pipeline/reader_cleanup_rebuild.py:92`), that `##` became a genuine
Word `Heading 2`. The `## ` prefixing survives today only in the dormant reannotation path
(`_apply.py:411`, `:415`).

*It was useless in practice.* The level was hardcoded to H2 with no hierarchy; multi-line blocks were
refused; only `paragraph` and `blockquote` were eligible; and the observed yield was 1, 2 and 0
accepted reclassifications per book.

*Two delivery holes would have made a run inconclusive even if the model got it right.* The registry
derivation handles `delete_block`, `join_fragmented_paragraph` and the text operations, and let
`reclassify_role` fall through to `skipped_operations` — so the registry entry still read `Заголовок`
while the markdown now read `## Заголовок`. Text matching does not strip heading markers, so that
entry lost its paragraph indexes and its formatting degraded. Worse, the new heading was not in the
protected set of `normalize_false_fragment_headings_markdown` (the check is at
`pipeline/output_validation.py:1779`), so display hygiene could merge it straight back into the
previous paragraph — silently. A correctly restored heading could therefore disappear before delivery,
and the hypothesis would have been buried by a delivery defect rather than judged on its merits. Both
holes are moot now: no operation creates headings. The generic unknown-operation fall-through remains
at `reader_cleanup_rebuild.py:730`, and nothing reaches it any more.

*The constitutional problem, stated plainly.* Constitution VII forbids reconstructing structure from
the shape of the text — "a leading ordinal, capitalisation, length, position", and "no source signal,
no repair". The production prompt instructed exactly that: *"ALL-CAPS short text after a heading may be
attribution"*, *"a short topic-introducing line may be heading when the surrounding prose shows it
starts a new topic"*. That is capitalisation, length and position — three of the four named
prohibitions. Those lines went with the operation: there is no longer any occurrence of `ALL-CAPS` or
`attribution` in `_prompts.py`. (An unrelated ALL-CAPS rule still lives in a different pass,
`src/docxaicorrector/resources/prompts/structure_recognition_system.txt:41`, and is out of scope here.)

*But the lawful version is already half-built, and nobody wired it up.* Real layout evidence from the
source — `font_size` versus `body_font_size`, `left_indent`, `first_line_indent`, `alignment`,
`centered`, `superscript` — is already extracted
(`_reader_cleanup_layout_signals_from_registry_entry`, `reader_cleanup_rebuild.py:369`), already
attached to each block (`_blocks.py:42`) and already serialised into the payload (`_models.py:67-68`).
**The production prompt never mentions it once.** A second, unused prompt
(`build_reader_cleanup_reannotation_system_prompt`, `_prompts.py:171-193`) is built entirely on those
signals and carries the right default: *"Never infer heading/list/footnote from text alone when
layout/context evidence is weak; default to body."* (`_prompts.py:183`). Its entry point
`run_reader_cleanup_reannotation` (`reader_cleanup_mvp/service.py:875`) is referenced only by the
package exports and tests — the pipeline never calls it.

So heading restoration by *reading a source signal* is constitutional and reachable. Heading
restoration by *guessing from text shape* is neither, and it is what was wired up.

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

**Consequence — settled by the owner on 2026-07-31: item 8 is dropped and `reclassify_role` is removed
outright (item 9).** Restoring headings during reader cleanup is blocked by the same serializer that
blocks the import-stage rule — one root cause, two starved consumers — and the owner has accepted that
as the ceiling of PDF input (spec 053). With no layout evidence reaching the model on PDF books, the
operation's only remaining basis would be the text-shape guessing Constitution VII forbids, and its
observed yield is 0–2 per book. So it is disabled rather than reasoned about.

**And then the owner asked the better question: why switch it off rather than remove it?** That is the
right call, and it makes the change smaller rather than larger.

Disabling would have needed new code of its own: `reader_cleanup_allowed_operations` is read from
`app_config` (`_config.py:70`) and an empty value means *allow everything*
(`_allowed_operations_for_config`, `_detectors.py:19-20`), but the key exists nowhere in the
production config model — `core/config.py:296-304` carries `reader_cleanup_default`, `_model`,
`_verifier_model`, `_chunk_size`, `_overlap_*`, `_global_plan_enabled` and `_max_failed_chunk_ratio`,
and no `_allowed_operations`. Only a validation run profile can set it (`validation/profiles.py:100`).
So a production run cannot restrict the operation set at all, and honouring the decision by
configuration would have meant **adding a config key whose only purpose is to keep a disabled feature
alive**.

Removal is cleaner on every axis: no new config surface; no flag someone flips in six months to
resurrect behaviour the Constitution forbids; ~58 mentions across 10 files in
`reader_cleanup_mvp/` deleted, including nine lines of prompt that shipped in every one of the ~107
requests per book. Nothing outside the package depended on it — the `reclassify` hits in
`document/roles.py:306` and `document/extraction.py` are `reclassify_adjacent_captions`, an unrelated
function that is still in use, and no gate or acceptance check read the operation's report fields.

**The capability is not being lost, only the unlawful implementation of it.** The evidence-based
design already exists in the unused reannotation path (`_prompts.py:171-193`), which decides roles
from `layout_signals` and defaults to body when the evidence is weak. That stays (see "Explicitly not
fixed"). If heading work is ever revived — on DOCX input, where the signals actually survive — it
should start from there, not from an operation that reasons about capitalisation.

## Fixed before the first run

All nine items below landed on 2026-07-31 (item 8 as a deliberate drop). They are kept in their
original ranked form, because the ranking — effect per unit of work — is the reasoning, and because
each item names the defect it removed. Present-tense descriptions of a defect below mean "this is what
the code did before the item landed".

Ranked by effect per unit of work. Each is justified statically or from existing artifacts — none of
them needs the run to have happened.

1. **Pin the model explicitly.** The config named Sonnet, `.env.example` shipped the key blank, and
   the code default was reached only when the config was empty — so copying the example bought a
   several-times-more-expensive model without saying so.
   *Landed:* config, code default, `.env` and `.env.example` all name
   `openrouter:anthropic/claude-haiku-4.5` (`resources/config.toml:74`, `_constants.py:13`,
   `.env.example:43`).
2. **Lower `max_failed_chunk_ratio` from 1.0 to ~0.1.** At 1.0, 106 of 107 chunks could fail and the
   run would still report `completed` / `changed: true` with no signal. The first run must be honest
   about partial execution, or its result cannot be interpreted.
   *Landed:* `_DEFAULT_MAX_FAILED_CHUNK_RATIO = 0.1` (`_constants.py:187`), read at `_config.py:55-58`,
   mirrored in `resources/config.toml:82` and `core/config.py:304`. Breaching it now emits
   `reader_cleanup_failed_chunk_ratio_exceeded`.
3. **Move the target boilerplate into the system prompt.** Keep `category`, `id`, `text_hash` and the
   actual substrings per target; state the safety rules once. Cuts roughly a third of the pass's cost
   with no behavioural change — the model reads the same rules, just not 1 403 times.
   *Landed:* `_build_side_heading_island_targets` (`_detectors.py:321-350`) emits four fields; the
   `safety_note` / `stub_continuation_risk` / `reattach_expected_after_preview_shape` prose is gone
   from the package.
4. **Stop classifying image anchors as `extraction_artifact`.** `_EXTRACTION_ARTIFACT_PATTERN` matched
   `[[DOCX_IMAGE_*]]`, so every image anchor carried a `kind` on the allowed-deletion list while the
   prompt told the model not to touch them. The validator caught it, but this is the exact
   contradiction that once cost 20–37 images per book; it should not survive on one check.
   *Landed:* the pattern is at `_constants.py:101-104` and anchors now carry their own
   `_DOCX_IMAGE_ANCHOR_KIND = "docx_image_anchor"` (`_constants.py:111`), which is on no deletion list.
   The validator's second line of defence remains (`_validate.py:358`).
5. **Do not re-append lost image anchors at the end of the document.** The reconciliation step restored
   a dropped anchor by pasting it at the end — the count reconciled while a chapter-3 figure landed
   after the bibliography. Reject the operation that lost it instead.
   *Landed:* `_reconcile_docx_image_placeholders` (`_report.py:157`) now discards the whole cleanup and
   returns the untouched markdown (`_report.py:196-212`), reporting
   `reader_cleanup_image_anchor_lost_cleanup_discarded`. Nothing is ever re-appended.
6. **Narrow `_TOC_LIKE_PATTERN`.** `\s\d{1,4}\s*$` made any paragraph ending in a number "TOC-like"
   and immune to every operation: 0.5–4.1% of blocks, up to 60% of them real prose.
   *Landed:* `_constants.py:90-92` — both branches require a page number, a bare trailing number counts
   only when the whole line is within `_TOC_ENTRY_MAX_CHARS = 100` (`_constants.py:89`), plus a density
   rule (`_constants.py:97-100`).
7. **Stop sending dead instructions.** The `anchor_repair` branch is unreachable in production yet
   occupied ~10 lines of every one of the 107 prompts, and the empty `global_plan` fields shipped on
   every request.
   *Landed:* `build_reader_cleanup_system_prompt` takes `include_anchor_repair_guidance: bool = False`
   (`_prompts.py:30`) and the guidance is an opt-in constant; the plan is compacted by
   `_compact_global_plan_for_payload` (`_planning.py:125`, used at `_planning.py:219`).
8. ~~Handle `reclassify_role` in the registry derivation and protect restored headings.~~
   **DROPPED** by the owner decision of 2026-07-31 — see the heading section above. Heading
   restoration is out of scope; the operation was removed instead.
9. **Remove `reclassify_role` outright** — the operation, its validation and apply branches, its
   prompt lines, its `max_reclassify_block_ratio` config and its tests. This subsumed the
   role-inference rules in the production prompt, the ones that taught the model that ALL-CAPS suggests
   a heading — spec 053 measured capitalisation as an **anti**-signal, three times commoner in junk
   than in real headings.
   *Landed:* `_ALLOWED_OPERATIONS` lists six (`_constants.py:35-42`); `max_reclassify_block_ratio` and
   `reclassify_would_change_visible_text` are gone from `src/` and `tests/`; an unknown operation name
   is recorded as ignored rather than failing its chunk (`_parse.py:607`), because a model that has
   seen the old contract may still emit it. `tests/test_reader_cleanup_mvp.py` keeps
   `reclassify_role` as a removed-operation fixture: it asserts the name is ignored with
   `operation_not_supported` and that the advertised contract names six operations.

Removing item 9's predecessor (a config key to disable the operation) was deliberate: it would have
been new surface whose only purpose was to keep a disabled feature alive.

## Non-goals

- **Not a prose editor, and not the first step towards one.** A pass that accepts model-authored
  sentences is a different thing with a different risk profile: it would need its own faithfulness
  gate, because nothing would then guarantee the translation still says what the source says. Wanting
  it is a legitimate owner decision; it must be taken deliberately, not smuggled in as "improve the
  prompt".
- **Not heading restoration.** Dropped by the owner on 2026-07-31 once spec 053 showed the layout
  evidence never reaches the model on PDF input. The dormant reannotation path is preserved but not
  wired up here.
- **No new configuration surface.** Specifically no `reader_cleanup_allowed_operations` key in the
  production config model: a flag whose only purpose is to keep a removed feature switchable is worse
  than the removal.
- **No re-tuning of chunk size, overlap or prompt wording before the first run.** The three replay runs
  are the only baseline that exists; changing the inputs now would destroy the comparison the run is
  supposed to provide.
- **No change to what the pass costs beyond removing waste.** Items 3 and 7 delete duplicated payload;
  they do not trade quality for tokens, and the accepted-operation sets on the replay books must stay
  byte-identical.
- **Not the run itself.** This spec ends where the run begins. The success criteria are proposed here
  and still have to be agreed.

## Explicitly not fixed before the run

These are real, and deliberately left alone until there is a real result to look at: the
`expected_after_preview` divergence (6 cases in 56 operations across three books); the ≤12-character
silent loss in `normalize_heading_boundary`, whose threshold was tuned against a specific regression
(`_apply_heading_boundary_to_text`, `_apply.py:725`; the two `> 12` guards at `_apply.py:758` and
`:762`); the duplicated `ignored_delete_blocks` in the report; and the chunk size and overlap —
changing 8 000 / 3+3 now would throw away the only baseline the three replay runs give us.

Two items on the original list belonged to `reclassify_role` and are moot after item 9: the hardcoded
`##` with no heading hierarchy, and the indistinguishability of `attribution`, `caption` and `body`.
They now apply only to the dormant reannotation path, which no production run reaches. Noted rather
than deleted, because whoever revives that path will meet both.

**Do not delete the dead reannotation path** (`reader_cleanup_mvp/service.py:875`,
`_apply_reannotation_decisions` at `_apply.py:319-384`, with its helpers through `_apply.py:480`, and
`_prompts.py:171-193`). It is the only evidence-based part of the package and is the most likely
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

## What the review rounds found

Recorded because the pattern is the point: every round found a real defect in the previous one, and
the full test suite was green throughout — none of these paths had coverage.

**The image-anchor P0 finally has its real root cause.** The June record says Lietaer lost 37 of 55
image IDs "with **zero** logged operations referencing them", and the loss was attributed to
unaudited block reconstruction. It was not. In `_apply_cleanup_operations`, `delete_block` sets its
slot to `None`; when `_violates_global_safety` then rolls the deletions back, they are moved into
`ignored` — **but the slots were never restored**. With at least one non-delete operation accepted,
the text is still delivered without them. That is exactly why no accepted operation referenced the
lost anchors: the report called them *rejected*. Verified directly against the recorded run
artifacts: all 37 `global_safety_limit_exceeded` entries are image anchors, and all 37 reference IDs
absent from the delivered markdown (55 → 18). The rollback now re-applies the surviving operation set
from scratch, so the rejection is real rather than bookkeeping.

**Round 1 review — two P1s in the original nine items.** (a) The fail-closed discard added by item 5
threw the entire paid pass away *silently*: `stage_status` stayed `completed`, the report still
counted the discarded operations as accepted, and no notice reached the user — the owner would have
been unable to tell "found nothing" from "threw everything away". (b) Attribution of *which*
operation lost an anchor matched only the operation's declared ids, while two apply branches write to
a neighbouring slot, so the real culprit escaped and the whole book's cleanup was discarded instead.

**Round 2 review — one P1 in the round-1 fix.** The write-set introduced to fix (b) accumulated block
provenance and assigned the union back to every touched slot, so after a `join` both slots carried
both ids and a legitimate join was blamed alongside the real culprit — in a three-operation
configuration escalating to a whole-book discard. Notably this is the exact shape the prompt itself
prescribes (`join_fragmented_paragraph` then `normalize_heading_boundary`), next to figure blocks.
Replaced with a direct causal test: an operation is blamed for anchor X only if X was present in the
slots it wrote before and absent after. The provenance map is gone entirely.

**Round 3 review — no P1 or P2.** Three diagnostic-only P3s (a delete counted twice on the
anchor-repair rollback, a docstring describing the wrong document, and the schema-repair prompt naming
an operation without its required fields), all closed. That convergence is why the rounds stopped.

## Anti-regression

1. A chunk failure rate above the configured ratio fails the pass visibly; it must not report
   `completed`.
2. Image anchors are never labelled with a deletion-eligible `kind`, and a lost anchor rejects its
   operation rather than being re-appended elsewhere.
3. A paragraph of prose ending in a number is not `toc_like`, while a genuine TOC line still is.
4. Trimming the target boilerplate does not change which operations are accepted on the three replay
   books — byte-identical accepted-operation sets.
5. The pass advertises six operations, never seven; a response still naming `reclassify_role` is
   ignored with a recorded reason rather than failing its chunk; and the three replay books produce
   the same accepted-operation sets as before, minus the 1/2/0 reclassifications.
6. A rejected deletion is rejected in the report as well as in the text: the rollback re-applies the
   surviving operation set from scratch, so "accepted" counts can never describe operations whose
   effect was thrown away.

## Changelog

- **2026-07-31** — written, implemented over three rounds of fixes and three adversarial reviews, and
  merged to `main`.
- **2026-08-01** — brought into line with the code it describes, after an external review found the
  text still written as if nothing had been implemented. The pass has **six** operations, not seven;
  `reclassify_role`, `reclassify_would_change_visible_text` and `max_reclassify_block_ratio` no longer
  exist, and every statement about them is now in the past tense. All `file:line` citations were
  re-checked against the implemented tree and corrected — the implementation moved line numbers
  throughout `reader_cleanup_mvp/`, so most were off, and several pointed at code that had been
  deleted. Nine defect descriptions that items 1-7 had already fixed were still written as open
  problems; each now says what landed. Added the `## Non-goals` section the spec format contract
  requires and dropped "(mandatory, once implemented)" from the anti-regression heading, since it is
  implemented. **The reasoning was not touched** — in particular the argument for removing
  `reclassify_role`, which is the most valuable part of this spec, is preserved word for word apart
  from tense. No `plan.md` or `tasks.md` was written: the work is done, and reconstructing a plan
  afterwards is forbidden by Principle III of the constitution.
