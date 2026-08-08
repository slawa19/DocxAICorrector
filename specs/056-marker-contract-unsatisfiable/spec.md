# Feature Specification: The paragraph-marker contract has no legal answer for a paragraph the prompt orders deleted

**Feature Branch**: `[056-marker-contract-unsatisfiable]`

**Created**: 2026-08-05

**Date**: 2026-08-05

**Status**: **IN PROGRESS (2026-08-05) — the change landed in `main` via PR #41 (`5393db2`), one
decision is still unbuilt.** This line said "not started" until 2026-08-07, two days after the work
landed; the same drift that spec 055 had just been corrected for. Not `PARTIALLY IMPLEMENTED`: that
status means the remainder was carried into a *later* spec, and here it was not — C′ is still owed by
this one. What is in `main`: **E**, the typed per-paragraph disposition (`1faeb06`), and
**D′**, capturing the rejected answer inside the attempt loop (`816a0eb`), plus three P0 fixes from the
review of that work (`cbe0084`, `c4dfce8`, `730cf0f`). What is NOT in `main`: **C′** — no commit
references it, and `_build_marker_recovery_user_prompt` was last changed by `6bc8ff9`, which predates
PR #41. **A** stays withdrawn and **B** stays deferred behind E, as the second pass decided.

All numbers below come from the first audiobook run (`20260804T_money_audiobook_first_run`) and were
re-verified against live code by the orchestrator. They describe the state **before** E landed; the
Changelog records what the review corrected.

**Owner surface**: `generation/_generation.py` — `_split_marker_preserved_markdown`,
`_build_marker_preserving_user_prompt`, the retry loop; `pipeline/support.py` —
`write_marker_diagnostics_artifact`

**Companion**: `specs/054-audiobook-mode-review-and-run/spec.md` (the run that exposed it);
`specs/055-pdf-docx-bridge-signal-loss/spec.md` (the import-side cause of half of it)

## The contradiction, quoted

Three instructions, all live, that cannot all be satisfied:

1. `resources/prompts/operation_audiobook.txt` rule 1 — *"Удаляйте footnote markers, bibliographic
   citations, DOI, ISBN, arXiv IDs, raw URLs … и прочий ненарративный мусор."* A paragraph consisting
   **entirely** of that has, honestly, nothing left.
2. `_generation.py:272-275` — *"Never answer with a placeholder, a stub, a dash, or a note about what
   you did (for example \"(Пусто)\", \"(Empty)\", \"(see above)\")."* So the model may not say so.
3. `_generation.py:363` — `if not chunk: raise MarkerValidationError("empty_marker_chunk")`. So the
   model may not return nothing either.

**Emptiness is forbidden and a stub is forbidden. There is no third answer.** Whatever the model does
with such a paragraph, the whole block is rejected.

The second failure mode is the same shape. `_generation.py:269` forbids splitting one marker into
several paragraphs, and `:370` enforces it — `if "\n\n" in chunk: raise paragraph_split_detected` —
while the audiobook system prompt's rules 5 and 11 *require* breaking a long sentence into two or
three spoken ones. The model obeys the system prompt; where it puts the line break is sampling.

This is a defect in the contract, not in the model.

## Measured, first audiobook run, 296 blocks / 237 sent to the model

| | |
|---|---|
| blocks needing at least one retry | **19 of 237 (8.0%)** |
| marker retries spent | **34** (plus 13 `recovery_after_exhausted_retries`) |
| blocks that failed outright | **6** → `source_text_fallback` → the block's own English source in the output |
| source characters dumped into the artifact | **20 725** — split mode 9 676 (46.7%), empty mode 11 049 (53.3%) |

Per-block failure codes, recovered from the rotated run log and matched to blocks by an exact,
unique `target_chars` fingerprint:

| block | code | what is in it |
|---|---|---|
| 118 | `paragraph_split_detected` | one 4 095-char quotation the importer welded into a single paragraph |
| 164 | `paragraph_split_detected` | `Box 5.4` plus its whole parable as one paragraph (2 177 chars) |
| 185 | `paragraph_split_detected` | `Box 6.1` plus the whole case study as one paragraph (3 282 chars) |
| 174 | `empty_marker_chunk` | contains `"Footnotes 1 Quoted in Naomi Klein… 2 See Appendix A…"`, 1 378 chars, 100% reference apparatus |
| 214 | `empty_marker_chunk` | contains paragraphs whose entire text is `"10"` and `"13"` |
| 274 | `empty_marker_chunk` | contains a paragraph whose entire text is `"14"` |

### The model is not failing consistently — it is guessing

Across the whole book, 20 paragraphs contain no alphabetic word at all (a bare footnote number). What
came back for them, from the recorded pairs:

```
'30'   -> '30'              1 attempt      'the number, echoed'
'44'   -> '44'              2 attempts
'23'   -> '[short pause]'   2 attempts     'replaced with a tag'
'17'   -> ''                3 attempts
'10'   -> ''                3 attempts     -> block 214 failed
'13'   -> ''                3 attempts     -> block 214 failed
'14'   -> ''                3 attempts     -> block 274 failed
```

Same shape, three different behaviours. That is why a retry sometimes rescues a block and sometimes
does not — the contract leaves the model no correct move, so the outcome is sampling.

The same impulse at scale: block 103's `"Footnotes 1 Source: Speech made in New York…"` came back as
the single word `"Примечания"` — a length ratio of 0.05 — and **passed**, because it was one character
short of empty.

### Which paragraphs are at risk — a source-side property, not a mode-side one

| longest paragraph in block | blocks | retried |
|---|---|---|
| 0–1 000 | 181 | 3.3% |
| 1 000–2 000 | 40 | 17.5% |
| 2 000–3 000 | 10 | 20.0% |
| **3 000+** | **6** | **66.7%** |

All three `paragraph_split_detected` failures are in the 16 blocks (6.8% of the book) holding a
paragraph of 2 000 characters or more — paragraphs the importer welded together, which is spec 055's
territory. A block containing a bare-number paragraph retries at 50% against a base rate of 8.0%.

### The retry budget is mostly spent saying the same thing again

`request_kwargs` is built once before the loop (`:1193-1210`) and, on a marker error, **is not changed
between attempts** — only the incomplete-response and context-leakage branches modify it. The model is
never told what it violated until the retry budget is exhausted and `_recover_from_persistent_empty_
response` builds an informed prompt (`_build_marker_recovery_user_prompt`, `:292-327`) that already
carries the error code, the expected ids, the found ids and a preview of the bad answer.

Measured on this run: the uninformed resend rescued **6 of 19 blocks (31.6%)**; the informed recovery
prompt rescued **7 of 13 (53.8%)**. Roughly 28 of 34 resends told the model nothing new, and they were
spent on the largest blocks (median 3 877 chars against 1 424).

### And the evidence was not kept

`write_marker_diagnostics_artifact` (`pipeline/support.py:93`) already records `raw_response_preview`,
but it is only called from `handle_block_generation_failure` — the path where a block *raises*. On a
controlled fallback `generate_markdown_block` returns normally, so nothing is written. **A $0.53 run
left no record of what the model actually answered**, and every proposal below therefore has to be
measured by paying for another run.

### A third failure mechanism, and the log never recorded it

`artifacts/audiobook_first_run/mechanical_checks.json` records `llm_blocks_with_marker_mismatch: 4` —
`marker_order_or_identity`, not empty and not split. Calls 199/200/201 expected `['p0957','p0958']`
and got `['p0958']`; call 250 dropped `p1207`. **The dropped `p0957` is a heading** — `##
**NGO Initiative s :**` — and it is `absent_from_artifact`, never returned at all.

So the model does not only empty a paragraph; it sometimes deletes the paragraph **together with its
marker**. This is the one mechanism of the three where content is genuinely lost rather than reverted
to English. It also attributes one of the six previously unattributed retried blocks (call 252).

The retained logs record only the six final codes, so this was invisible until the run capture was
read instead.

### The few-shot example teaches both violations as correct

`resources/prompts/example_audiobook.txt`, loaded into the audiobook system prompt (`core/config.py:213`,
`:1414`), demonstrates:

- a **three-paragraph** source (`References` / `[1] Smith, 2009. DOI:10.1000/xyz` / `В 1930-х гг. …`)
  producing a **one-paragraph** result — two paragraphs deleted outright, presented as the desired
  behaviour;
- a two-paragraph source producing three paragraphs, the heading split into its own, labelled
  **«Корректный результат»**.

The model is shown both forbidden shapes as the target, then punished for producing them. A
demonstration outweighs a rule in the same prompt.

**And this corrects the framing above.** Rules 5 and 11 order splitting into *spoken sentences* —
separated by spaces, which produce no blank line, which `:370` does not reject. **Rules 5/11 are not in
conflict with the validator.** The instruction that actually demands a paragraph break is the example.
A remedy aimed at the rules would have missed.

## Decisions

**The four decisions in the first draft of this spec are withdrawn or reordered.** Three of them were
justified by claims that do not survive inspection; they are kept below with the refutation, because a
spec that quietly drops its own reasoning teaches nothing.

### E — a typed per-paragraph disposition. This is the change.

`_split_marker_preserved_markdown` returns a list of strings, so a block is all-or-nothing: any single
bad paragraph discards every good one in it. Replace it with a per-paragraph record —
`{paragraph_id, text, status}` where status is `accepted | omitted | source_restored | retry_required` —
and consume those records in `build_processed_paragraph_registry_entries` instead of re-splitting the
joined string on `"\n\n"`.

A missing, duplicated or reordered marker stays block-fatal: that is the check which detects real loss.
But **an exact marker sequence now preserves every valid chunk**, and the failure is expressed per
paragraph.

Two remedies follow directly, and between them they cover all three failure mechanisms without a
reserved token and without weakening any check:

- **per-paragraph fallback** — one paragraph reverts to its source (or, for audiobook, is simply
  absent), instead of nine good translations being thrown away with it;
- **targeted retry** — re-ask for the offending paragraph rather than resending a 4 000-character
  block unchanged.

On the worked example this is decisive. Block 274 holds ten paragraphs; the whole block was discarded
because paragraph `p1336`, whose entire text is `14`, came back empty. Under E, nine paragraphs keep
their translation and one is recorded as omitted.

### D′ — capture the rejected answer inside the attempt loop. First, because everything else needs it.

The first draft said "call the existing `write_marker_diagnostics_artifact` from the controlled-fallback
path". **That cannot work:** `generate_markdown_block` catches the recovery exception and returns a
plain string (`_generation.py:1304-1318`), so the call site has neither the rejected answer nor the
exception. The capture has to live inside the attempt loop, with its own schema and its own directory —
the existing writer truncates to 1 000/600 characters, keeps only the last exception, and writes into
the formatting-diagnostics feed consumed by `formatting_diagnostics_feedback.py`, so reusing it is not
the "zero behaviour change" the draft claimed.

Without this, every remedy here is measurable only by paying for another book.

### C′ — put the diagnosis in the first retry, keeping the context

Sound, with one correction. Reusing `_build_marker_recovery_user_prompt` wholesale would **drop the
surrounding context** — it builds a target-only prompt — and would repeat the same impossible
"exactly one non-empty paragraph, never a stub" contract. Prepend the diagnosis to the existing
request instead.

And the evidence for it is weaker than the draft claimed: the measured 31.6% → 53.8% improvement
confounds two changes at once, informedness **and** context removal. Attributing all of it to
informedness is unsupported.

Measured correction to the draft: **all 34** marker retries resent a byte-identical request, not
"roughly 28" — grouping the per-call accounting by identical prompt-token count yields exactly 19
groups and 34 resends.

### A — collapsing a split paragraph: WITHDRAWN as justified

The draft said *"the check never had grounds to read `\n\n` as loss"*. That is wrong twice.

It does have grounds: `build_processed_paragraph_registry_entries` (`pipeline/block_execution.py:560`)
splits the answer on `"\n\n"` and raises `paragraph_marker_registry_mismatch` on a count mismatch. The
check's remedy was too blunt; its grounds were sound.

And the safety claim — "a break inside one chunk cannot move text across a marker" — is false, because
the model can place text **before** a marker:

```
[[DOCX_PARA_p1]]
Перевод первого абзаца.

## Безопасность
[[DOCX_PARA_p2]]
[short pause]
```

Marker identity and order are exact, both chunks are non-empty, and `p2`'s source is under
`_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS = 40` so restoration is skipped. **`p1` has taken `p2`'s
heading.** Every remaining check passes. Today that answer is caught by `paragraph_split_detected`; the
draft would have traded a detected failure for a silent corruption.

**Under E the question changes shape** and is decided with the counterexample in hand: with a single
marker there is no neighbour to steal from and `unexpected_prefix` already forbids a leading fragment,
so the collapse is provably safe; with two or more markers the attribution is genuinely ambiguous. If
no safe rule exists for the multi-marker case, that is an accepted outcome to record, not to paper
over.

### B — a reserved "nothing to speak here" token: DEFERRED behind E

Two of the draft's premises are false. `restore_collapsed_marker_paragraphs` restores **only when an
absorbing neighbour grew** (`_generation.py:438-453`); a reserved token has no absorber by
construction, so it would survive verbatim into translate and edit output. And "the caller then
decides" has no interface to decide with — the generator takes no `operation` argument and returns an
untyped joined string.

E supplies exactly that interface. After E, a token may prove unnecessary: `omitted` is already the
status the token was invented to express.

### Carrying the import `footnote` role across the bridge — smaller than it looked

`pdf_import/logical_import.py:546` assigns `role = "footnote"`, and the bridge drops it
(`processing_runtime.py:1132`). It is tempting to conclude the whole `empty_marker_chunk` class
dissolves at the root. **Measured, it does not.**

The role is assigned by `_looks_like_superscript_footnote_marker` — it is the **bare marker digit, never
the footnote body**:

| book | import paragraphs | `role=footnote` units | their total characters |
|---|---:|---:|---:|
| Money & Sustainability | 1 435 | 21 | **36** |
| The Value of Everything | 2 345 | 13 | **23** |
| Creating Wealth | 1 793 | **0** | 0 |
| Rethinking Money | 2 643 | **0** | 0 |

Those units are literally `'1' '17' '18' … '10' '13' '14'` — including the `'10'`, `'13'` and `'14'`
that sank blocks 214 and 274. So carrying the role would dissolve **two of the three** empty-chunk
failures by structural role, with no new detector. It does **not** touch block 174 — the 1 378-character
`"Footnotes 1 Quoted in Naomi Klein…"` — because footnote *bodies* are classified `body`. And it buys
nothing at all on two of the four books.

The value is not the 36 characters; it is that 15 blocks stop carrying a poison pill. Recorded as a
candidate for spec 055, not as this spec's remedy. **Constitution VII tension, named rather than
assumed:** VII puts footnotes out of scope for *detection*, and carrying an already-measured import role
is not new detection — but it is close enough to the line that it is an owner decision, not an
inference.

### Two defects found on the way, neither of them this spec's subject

**The acceptance gate is mis-parameterised, and that — not the six blocks — is why the run failed.**
Three relaxations in `run_lietaer_validation.py` (`:3908`, `:5056`, `:5100`) are gated on the literal
`processing_operation == "translate"`: fuzzy heading matching, the source-heading filter, and
`word_numbering_passed`. An audiobook run also produces Russian from English and receives none of them,
so the gate demanded **English** headings from a Russian narration. It is keyed on an operation *name*
instead of the capability "the output language differs from the source".

**The source-fallback classifier cannot see short blocks.** `is_source_text_fallback_output` requires
the answer to equal the source **and** be ≥120 characters **and** contain ≥12 English words
(`output_validation.py:123-124`, `:287-295`). A shorter block whose answer equals its source is
classified `valid`, is never routed through the rejection path, and therefore never meets the
narration exclusion shipped on 2026-08-04. Measured share of LLM blocks outside the classifier's
reach: **43/237, 98/325, 54/246, 13/184** — 18% to 30% per book. It did not bite on the 2026-08-04 run
(all six fallbacks were long enough), so this is reachability, not an observed incident.

## Non-goals

- **Not fixing the import here.** Three of the six failures exist because a whole boxed quotation
  arrives as one 4 095-character paragraph. That is spec 055; this spec makes the pipeline survive
  that input rather than depending on it changing.
- **No prompt tuning as persuasion.** Rule 20 already forbids lists and 116 bullet glyphs reached the
  artifact anyway. The example file is a different matter — it is a demonstration that contradicts the
  contract, and correcting a wrong example is not persuasion.
- **No detector keyed on what a paragraph looks like.**
- **No change to `marker_order_or_identity`, `markers_missing` or `unexpected_prefix`.** Those three
  catch real loss — the third mechanism above is precisely one of them working — and they stay.
- **Not making the audiobook marker-free.** It was evaluated: a standalone audiobook run is not
  TTS-only — `pipeline/setup.py:389-448` unconditionally builds the DOCX, restores formatting and runs
  the gates, and `late_phases.py:568-585` requires both artifacts. Dropping markers would also give up
  the only loss detector, making every future defect an accepted tail by construction.

## Anti-regression

1. **A missing, duplicated or reordered marker still fails the block.** Proven by test, not asserted.
2. **No remedy may convert a detected failure into an undetected one.** The counterexample above is the
   standing test case: after any change, `p1` must not be able to absorb `p2`'s heading unnoticed.
3. **Text is never lost silently.** Under per-paragraph disposition, every paragraph carries a status,
   and the counts are published — accepted, omitted, source-restored — per run.
4. **Both entry points behave the same** (spec 054 anti-regression 3). This is currently **not met**:
   `FinalAssemblyEntry` carries no `controlled_fallback_narration_excluded` field, so the flag shipped
   on 2026-08-04 cannot survive the registry round-trip used by the translate + reader-cleanup
   projection.
5. **Measured on the corpus before and after**, by the owner's metric from spec 054: the share of
   source-language characters in the narration artifact.
6. **D′ lands before anything that changes behaviour**, or the changes erase the evidence of their own
   failure modes from future runs.

## What is not established

- **The model's actual answers for the six blocks.** They were never saved (that is D). Every claim
  about *which* paragraph emptied is inferred from the error code plus the source shape; for blocks 214
  and 274 the inference is near-forced, for 174 plausible, and for the three split failures the
  location of the break is unknowable from what exists.
- **Whether translate runs suffer the same rate.** Retry accounting shipped on 2026-08-03, after every
  earlier full-book run, and fallback artifacts are pruned at 7 days. The claim that an earlier
  translate run had zero source-text fallbacks could be neither confirmed nor refuted. What *is*
  established from code: the marker contract does not depend on the operation at all
  (`pipeline/job_parsing.py:95-96`), so the difference between modes lives entirely in the system
  prompt — and audiobook is the only prompt in the repository that orders the model both to delete
  content and to re-segment it.
- **Six of the nineteen retried blocks** (111, 117, 139, 196, 204, 252) are unattributed; only their
  final outcome was logged.
- **One book, one model, one run.** The long-paragraph signal must transfer by construction; the
  bare-number one probably does; neither is measured on the other three books.

## Changelog

- **2026-08-08 — C′ WILL NOT BE BUILT. Owner decision, recorded here so the question cannot come back
  through this spec's side.** C′ (`:203-212`) proposed telling the model what it violated from the
  FIRST retry. It was sound, and it is now unnecessary. The degradation ladder shipped instead
  (`054e405`, PR #68, `generation/_generation.py:2236`): a block whose marker contract fails is asked
  again PARAGRAPH BY PARAGRAPH with `marker_mode=False`, where the failure class is unreachable by
  construction. On the paid run of 2026-08-08 (Money & Sustainability, audiobook, markers on) the
  ladder fired on **one** block, cost **three** model calls against the run's 307
  (`artifacts/audiobook_final_run/money_sustainability/run_summary.txt:31`) and left **zero**
  unrescued paragraphs — source substitutions went 2 → 0 and the 5 581 characters dropped from the
  narration went to 0 (`:45`, `:47`, `:52-53`; the after-numbers are recorded in
  `docs/WHERE_WE_ARE.md:228-235`). C′ would reduce how OFTEN a block reaches the ladder — that is,
  it would economise on a line item already measured at **0,98 % of the run's calls** — while adding
  another layer of instructions to the retry loop, which is the exact place where this spec found
  three live instructions that cannot all be satisfied (`:30-40`). Over-engineering. Its own evidence
  was already deflated here: the 31.6% → 53.8% figure confounds informedness with context removal
  (`:210-212`). **The status line above was NOT touched, and it is now arguably stale**: it reads
  `IN PROGRESS … one decision is still unbuilt`, which is literally true (C′ is unbuilt) but implies
  work is owed, and none is. Rewriting a status is the kind of change this repository has been burned
  by in both directions, so it is left as an **owner decision** rather than made silently by the
  agent who wrote this entry. Full reasoning and the run numbers:
  `specs/059-verdict-never-reaches-the-screen/spec.md`, section A-8.

- **2026-08-05 (second pass, after an independent chain review)** — three of the four decisions
  are withdrawn or reordered, and the reasoning that justified them is refuted in place rather than
  deleted. **A** would have traded a detected failure for a silent corruption: the registry really does
  split on `

`, and a model can place text before a marker, so `p1` can absorb `p2`'s heading with
  every remaining check passing. **D** could not work where it was placed — the call site holds neither
  the rejected answer nor the exception. **B**'s two premises were false. **C** survives with its
  evidence deflated: the 31.6% -> 53.8% figure confounds informedness with context removal, and all 34
  retries (not ~28) resent an identical request. Added: a **third failure mechanism**
  (`marker_order_or_identity`, 4 occurrences, one heading lost outright) that the retained logs never
  recorded; the **few-shot example** teaching both violations as correct, which also shows rules 5/11
  are *not* in conflict with the validator; the acceptance gate keyed on the literal `"translate"`;
  and the source-fallback classifier's blindness to 18-30% of blocks per book. The replacement is
  **E**, a typed per-paragraph disposition, which the review converged on independently and which
  covers all three mechanisms without a token and without weakening a check.

- **2026-08-05** — spec created from the 2026-08-04 diagnosis. The premise it started from was wrong
  in a useful way: the saved fallback artifacts do **not** contain the model's answer — their
  `processed_chunk_preview` equals `target_text_preview` by construction — and the failure codes had to
  be recovered from a rotated log instead. That gap became decision D.
