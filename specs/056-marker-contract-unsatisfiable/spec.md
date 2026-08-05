# Feature Specification: The paragraph-marker contract has no legal answer for a paragraph the prompt orders deleted

**Feature Branch**: `[056-marker-contract-unsatisfiable]`

**Created**: 2026-08-05

**Date**: 2026-08-05

**Status**: **READY — diagnosed and measured 2026-08-04/05, not started.** All numbers below come from
the first audiobook run (`20260804T_money_audiobook_first_run`) and were re-verified against live code
by the orchestrator.

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

## Decisions

Four changes, in this order. The ordering is the point: the first one makes the others measurable
without paying for a run.

**D. Keep the rejected answer.** Call the existing `write_marker_diagnostics_artifact` on the
controlled-fallback path too, with the retention the neighbouring `block_fallbacks` directory already
uses. Zero behaviour change; it is the precondition for offline replay, the technique that measured
PR #37 without a second run.

**A. Rejoin a split paragraph instead of rejecting the block.** Replace the `paragraph_split_detected`
raise with collapsing the chunk's internal blank lines. A break *inside* one chunk cannot move text
across a marker; identity, order and count stay enforced by `marker_order_or_identity`, and emptiness
by `empty_marker_chunk`. The check never had grounds to read `\n\n` as loss. Removes 46.7% of the
dumped characters.

**C. Tell the model what it violated on the first retry**, by routing the diagnosis that
`_build_marker_recovery_user_prompt` already renders into the retry loop, exactly as
`_inject_context_leakage_retry_warning` already does for its own error class. This fixes the economics,
not the defect: it raises the chance the coin lands well.

**B. Give the model a legal way to say "there is nothing to speak here."** A reserved token that
`_split_marker_preserved_markdown` accepts as a valid chunk; the caller then decides — for audiobook
the paragraph is absent from the narration, for edit/translate its source text is restored, which is
what `restore_collapsed_marker_paragraphs` already does for the softer case. This is what actually
resolves the contradiction.

**The trap in B, named so nobody walks into it:** do not make the token conditional on the paragraph
"looking like" a footnote. Constitution VII puts footnotes out of scope for detection outright, and
keying on the literal word `Footnotes` is precisely the per-book literal it forbids. **The token is
accepted unconditionally; the safety is observability, not guessing** — count every use, publish it as
review data, and treat "the model flagged the entire block" as a failure rather than a cleanup.

## Non-goals

- **Not fixing the import here.** Three of the six failures exist because a whole boxed quotation
  arrives as one 4 095-character paragraph. That is spec 055, and it is blocked behind its own
  prerequisite; this spec makes the pipeline survive that input rather than depending on it changing.
- **No prompt tuning as persuasion.** Rule 20 already forbids lists and 116 bullet glyphs reached the
  artifact anyway. The user-prompt change in B is a contract extension — a legal answer that does not
  exist today — not a stronger request.
- **No detector keyed on what a paragraph looks like**, for the reason stated above.
- **No change to `marker_order_or_identity`, `markers_missing` or `unexpected_prefix`.** Those three
  checks catch real loss and stay exactly as they are.

## Anti-regression

1. **Text is never lost silently.** After A, the visible character count of a rejoined chunk equals
   the model's output — a deterministic property, checkable without a model.
2. **B does not become a licence to delete prose.** Every use of the token is counted and published;
   a block where the model flags every paragraph is a failure, not a cleanup. The counter-proof is the
   corpus, not a fixture: 20 paragraphs in this book contain no alphabetic word, and that is the upper
   bound of unarguably honest uses.
3. **Anti-regression 2 of spec 054 still holds** — a block the prompt legitimately empties does not
   come back as a placeholder in the artifact.
4. **Measured on the corpus, before and after**, by the owner's own metric from spec 054: the share of
   source-language characters in the narration artifact.
5. **The three untouched marker checks keep firing** — proven by test, not by assertion.

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

- **2026-08-05** — spec created from the 2026-08-04 diagnosis. The premise it started from was wrong
  in a useful way: the saved fallback artifacts do **not** contain the model's answer — their
  `processed_chunk_preview` equals `target_text_preview` by construction — and the failure codes had to
  be recovered from a rotated log instead. That gap became decision D.
