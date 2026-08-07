# Feature Specification: The merge destroys boundaries the source marks with a ROLE — and only one half of that is ours to fix

**Feature Branch**: `[058-merge-destroys-role-marked-boundary]`

**Created**: 2026-08-07

**Date**: 2026-08-07

**Status**: **IMPLEMENTED (2026-08-07) — confirmed by a paid before/after run on the two books where
the rule applies.** Creating Wealth and The Value of Everything, same document and run profile, same
model. The other two books were predicted to gain nothing and were not paid for. Measured on four
books; every census number below is offline, cross-read against each run's own
`translation_quality_report.boundary_recovery`.

**Owner surface**: `pipeline/output_validation.py` — `_recover_adjacent_entries` (the merge
acceptance branch), `_entry_has_source_unit_role`, `_SOURCE_UNIT_ROLES`. NOT
`_entry_is_protected_boundary` — see Decision for why the obvious place is the wrong one.

**Companion**: `specs/057-boundary-recovery-is-product-blind/spec.md` — the same mechanism, the other
signal. Spec 057 refused merges where the source marks the boundary with **punctuation**; this one is
about the boundaries the source marks with a **role**.

## Why this exists

Spec 057 shipped, was confirmed by a paid run, and repaid **25 boundaries out of 391 across the whole
corpus — 24 of them on a single book.** The owner asked the right question: is this turning into
per-book work? The rule itself is not — it reads the source on every book and is correctly silent
where the source says nothing (61% / 63% / 53% / 80% of paragraphs close a sentence on the four books;
the source text of the left paragraph was missing **0 times out of 391**). But its *payout* was
book-shaped, and the corpus-wide defect was left almost untouched.

So the residue was measured properly, and it is not shapeless.

## The census

391 source paragraphs are absorbed into a preceding paragraph across the four books (a paragraph is
"absorbed" when it reaches the delivered document with no target index of its own). By the role the
**source** gives them:

| role in the source | count | share |
|---|---:|---:|
| `body` | 319 | 81% |
| `caption` | 38 | 9% |
| `heading` | 32 | 8% |
| `image` | 2 | 0% |

**72 of 391 carry a structural role in the source and were welded into the paragraph before them.**
Unlike the punctuation signal, this one is present on **all four books**: 7 / 27 / 19 / 19.

And what they were absorbed *into* separates the problem cleanly in two:

| absorbed | → anchor | count |
|---|---|---:|
| `caption` | **`image`** | **33** |
| `heading` | `body` | 32 |
| `caption` | `body` | 5 |
| `image` | `body` | 2 |

## Half A — a figure caption welded onto the image placeholder. 35 cases, and it is not ambiguous

(`role_confidence` is quoted below as evidence about the SOURCE DATA. It is not available to the
code — `FinalAssemblyEntry` does not carry the field — and the rule must not grow a condition on it.)

Quoted from the census, `value_of_everything`:

> `p0843` `role=caption`, `role_confidence=explicit`, `boundary_source=raw/explicit`
> TEXT: `**Figure 28.** Non-financial sector public company profitability (GMO)³²`
> ANCHOR: `p0842` `role=image` → `[[DOCX_IMAGE_img_036]]`

An image placeholder is not prose. It cannot be a sentence that runs on, and nothing can legitimately
continue it. Yet `_left_entry_looks_incomplete` sees `[[DOCX_IMAGE_img_036]]`, finds no terminal
punctuation, and calls it unfinished — the same translation-shape judgement spec 057 was about, with
the same result.

Both sides carry an **explicit** source role. This is the cleanest signal in the whole area:
33 captions welded onto an image, plus 2 images welded into body, on two books (Creating Wealth 20,
The Value of Everything 19; the counts overlap the table above by role).

## Half B — the absorbed headings are mostly the IMPORTER's mistake, not this stage's

32 headings are absorbed, and the instinct is to protect them. **Measured, that instinct is wrong.**
By source heading level: **28 of 32 are level 3**, 2 are level 2, 2 are level 1.

The level-3 population, quoted:

> `p0447` `### H aving, Doing Being` — anchor `p0446` `M otivation`
> `p0453` `### Linear N on-linear, Cyclical` — anchor `p0452` `Caus ality`
> `p1242` `### 6 months - 1 year Broad cros s s ection of the public` — anchor `p1241` `Vis ioning`

Those are **two-column table rows**, the second cell mis-roled `heading` by the importer. Others in the
same population are a signature line (`### Ivo ŠLAU S`), a quotation fragment
(`### And so they should.”`) and an index row (`### Civics at the city or regional level p.173`).

Only the level-1 and level-2 cases are genuine section headings welded into the body:
`## Appendices`, `## Acknowledgements` — **4 of 32**.

**Protecting `role=heading` wholesale would protect the importer's errors and freeze 28 mis-roles into
the delivered document.** The defect is real, but it is owned by the import stage, which is where the
role was invented. Reconstructing "is this really a heading?" here would be re-deciding structure from
the shape of the text — the exact move Constitution VII forbids and spec 057 was written to remove.

## Decision

**Implement Half A only. Record Half B, do not build it here.**

Refuse the merge when either side's **source role** is `image` or `caption`. Both are properties of
the input document, already carried on the entry (`FinalAssemblyEntry.role` / `structural_role`,
filled from `ParagraphUnit`). No word list, no threshold, no per-book literal, nothing read off the
translation.

**Where the refusal goes matters, and the obvious place is the wrong one.** The first draft of this
spec said "add the roles to `_entry_is_protected_boundary`". An independent review disproved that, and
the code confirms it on two counts:

- **The protection is bypassable.** `_entries_match_allowed_protected_merge:1283` returns True
  unconditionally when either side carries `generated_heading_kind == "false_fragment_heading"`. A
  caption demoted a moment earlier walks straight through any protection added to
  `_entry_is_protected_boundary`. This is the same demotion that strips protection from real headings
  in Half B.
- **The counter would measure the wrong thing.** `protected_boundary_denials` is incremented at the
  eligibility gate (`:1394`), *before* `_left_entry_looks_incomplete` /
  `_right_entry_looks_like_continuation` are ever consulted. A counter there counts every adjacency
  involving a caption or an image — not the merges actually prevented — and could never be compared
  with the 39 predicted below.

So the refusal goes at the **same choke point spec 057 already proved**, immediately before
`_merge_entry_pair`, after both shape predicates have fired. Nothing can bypass it, and the counter
means "boundaries saved". The order inside that branch is fixed and the counters are mutually
exclusive:

```
translation predicates satisfied
  → source-terminal refusal (spec 057)   → source_terminal_denials
  → source role is image or caption      → source_role_denials
  → merge                                → accepted_merges
```

Terminal first, so spec 057's confirmed counter keeps its meaning and no pair lands in two counters.
Measured: exactly one pair on the corpus (`p0242+p0243`) is caught by both.

Half B is handed to a future spec. It is **two** defects, not one, and only the first is the
importer's: the level-3 heading role is given to table cells and signature lines at import; and,
separately, this assembler is allowed to override a genuine source heading on continuation context
(`:663`), turn it into a `false_fragment_heading` (`:1156`), and merge it (`:1283`). The four real
section headings among the 32 are destroyed by that second path, not by the importer. Cleaning the
import signal first, then deciding whether a trustworthy source heading may be demoted at all, is the
right order. This spec touches neither.

## Anti-vacuum, done BEFORE the rule was written

Anti-regression 1 below demands this as pre-work, so it was done first. Every merged pair on the four
books was classified by the roles of BOTH halves:

| left role | right role | pairs | guard refuses? |
|---|---|---:|---|
| `body` | `body` | 287 | no |
| `image` | `caption` | **35** | **yes** |
| `body` | `heading` | 32 | no |
| `heading` | `body` | 32 | no |
| `body` | `image` | **2** | **yes** |
| `heading` | `caption` | **2** | **yes** |
| `body` | `caption` | **1** | **yes** |

**40 pairs, not the ~35 first estimated.** Per book: Money & Sustainability 1, Creating Wealth 20,
Rethinking Money **0**, The Value of Everything 19.

**One of the 40 is already refused by spec 057** (`p0242+p0243`, whose left half ends in a full stop),
so the incremental effect is **39 new refusals: 0 / 20 / 0 / 19.** Money & Sustainability gains nothing
here. That single overlap is why the two refusals must be ordered rather than both incremented.

**Not one of the 40 is a genuine repair, and this is exhaustive, not a sample.** 35 are the identical
image-placeholder-plus-`Figure N.` shape; the other 5 were read individually, all of them:

> `p0261(body) + p0262(image)`: «…would be as follows:» + `[[DOCX_IMAGE_img_015]]` — prose introducing
> a figure, with the figure's placeholder welded into it. And the very next pair,
> `p0262(image) + p0263(caption)`, welds the caption on too: a three-way chain.

> `p0458(heading) + p0459(caption)`: `### Trans cendent God Immanent Divinity` + `Figure 4.1.
> Competition and Cooperation` — two unrelated units.

351 of 391 pairs are untouched, so `accepted_merges` cannot collapse (anti-regression 2 holds by
construction).

**Rethinking Money gains nothing — 0 of its 229.** The book with by far the most destroyed boundaries
is not helped by this rule at all. That is stated here rather than discovered later: this spec repays
40 of 391 corpus-wide, and the 229 on one book remain open.

## Confirmed live

Two paid runs, the two books the census said the rule applies to. Read from the pipeline's own
counters and, independently, from the delivered documents' source→target mapping.

| | Creating Wealth | The Value of Everything |
|---|---:|---:|
| `source_role_denials` | **18** | **18** |
| `accepted_merges` | 56 → 35 | 30 → 11 |
| `source_terminal_denials` | 0 → 0 | 0 → 0 |
| `denied_merges` | 904 → 906 | 1350 → 1352 |
| `protected_boundary_denials` | 862 → 864 | 913 → 913 |
| `demoted_false_headings` | 11 → 11 | 0 → 0 |
| `registry_covered_paragraphs` | 1519 → 1519 | 1277 → 1277 |
| `paragraph_count_drift` | −56 → −35 | −30 → −11 |

**The class the rule targets is gone, completely.** The independent census of absorbed source
paragraphs, by role:

| | before | after |
|---|---|---|
| Creating Wealth | `caption` 19, `image` 1, `heading` 7, `body` 26 | `heading` 6, `body` 25 |
| The Value of Everything | `caption` 18, `image` 1, `body` 10 | `body` 10 |

**Zero captions and zero images absorbed** — 20 and 19, exactly the prediction. What remains absorbed
is only `body` and `heading`, which is precisely what this spec said it does not address.

**Why the counter reads 18 and not 20 or 19.** `source_role_denials` counts merges prevented at the
acceptance point. Two pairs on Creating Wealth and one on The Value of Everything were not merge
candidates in this run at all — the model's output differs between runs and the shape predicates read
it — so nothing had to be refused for those boundaries to survive. The end state is the prediction;
the counter is a floor on it.

The other anti-regressions:

- **Narrowed, not disabled.** `denied_merges` +2 / +2, `protected_boundary_denials` +2 / 0,
  `demoted_false_headings` unchanged, `registry_covered_paragraphs` and `fallback_paragraphs`
  identical. `accepted_merges` is still 35 and 11.
- **No text lost.** `source_count` identical on both books (1829, 2295); delivered paragraphs +21 and
  +19; delivered characters grew (539006 → 540398, 763960 → 767785); `mapped_count` rose on both. A
  merge refusal can only split a paragraph — it has no path to delete text.
- **Acceptance did not degrade.** Both books were already failing, and the failed-check lists are
  *identical* before and after: `list_fragment_regressions_present, key_headings_preserved` and
  `false_fragment_headings_present, key_headings_preserved`. Nothing new was introduced.
- **The narration did not lose joins.** 5 → 6 and 7 → 9. Both went up. These are standalone audiobook
  runs, which do not consume assembly output at all, so this is the model's variation, not an effect.

**A limit this run exposed.** Among the newly unmapped paragraphs is `p1488`, whose text is
`figure a.1. cycles of economic activity` — a figure caption the importer roled `heading`, not
`caption`. Captions that arrive with the wrong role are outside this rule by construction, and that is
the same import-signal problem Half B is about.

## Non-goals

- **Do not protect `role=heading` here.** 28 of the 32 are import mis-roles; protecting them entrenches
  them. Named, measured, and deliberately left.
- **Do not re-derive a caption or an image from the shape of the text.** The role either arrives from
  the source or it does not exist. No `Figure \d+` pattern and **no placeholder regex anywhere on the
  decision path** — not as a substitute for the role and not as a second reading of it. An earlier
  draft allowed the latter; a review pointed out that `role == "image" and PLACEHOLDER_RE.match(text)`
  puts the shape of the text back into the decision, which is the whole thing being removed. The
  production path needs no regex at all.
- **Do not condition on `role_confidence`.** The census shows these roles arrive `explicit`, and that
  is evidence about the source data — but `FinalAssemblyEntry` does not carry the field, and it must
  not be added for this. The role is the signal.
- **Do not touch spec 057's punctuation refusal.** It is confirmed and closed.
- **Do not chase the 319 body→body absorptions.** Neither punctuation nor role says anything about
  them; on current signals that residue is not addressable, and saying so is the honest answer.
- **Do not use `accepted_merges` deltas as a measure of anything.** Measured: Rethinking Money moved
  196 → 235 between two runs of the same book with **one** refusal in between, because the model's
  output differs and the merge predicates read it. Only source-keyed counters mean anything here.

## Anti-regression

1. **Anti-vacuum — DONE, before a line of code.** See the section above: 40 pairs, all four shapes
   read with both halves quoted, none a genuine repair. If a fifth shape appears on a future book, it
   gets the same treatment before the rule is widened.
2. **The rule is narrowed, not disabled.** `accepted_merges` must stay non-zero on every book, and
   `denied_merges` must not collapse.
3. **The refusals are attributable.** The new denials must be countable on their own — a decision
   `reason` that names the role, not an unlabelled increment of `protected_boundary_denials`, which
   already carries 575–913 per book and would hide the effect entirely.
4. **Measured per book from the pipeline's own counters, before and after**, on all four books.
   Expected: `source_role_denials` = **39** — 0 / 20 / 0 / 19 — and `source_terminal_denials` unchanged
   from spec 057's confirmed run. Zero on Rethinking Money is the predicted result, not a failure; if
   the run shows refusals there, the rule is doing something this census did not predict and must be
   re-read before merge.
5. **No text lost, by the exact invariant spec 057 used** — the whitespace-stripped character sequence
   of the delivered document does not change. `source_count` unchanged and a rising paragraph count are
   necessary but NOT sufficient, and a review was right to say so: both can hold while a character
   moves.
6. **The narration is checked, not assumed.** Spec 057 learned this the hard way: under `translate` +
   reader cleanup + audiobook post-process, assembly entries reach the narration input through
   `late_phases.py:790`. Reader cleanup is off by default, but the claim must not be made "by
   construction" again.

## What is not established

- **Whether the 5 `caption`→`body` and 2 `image`→`body` cases behave like the 33.** They are counted,
  not inspected.
- **Whether any legitimate merge has a caption on one side.** That is anti-regression 1 and it is
  *pre-work*, not verification-after.
- **Half B's true split.** "28 of 32 are level 3, and the level-3 samples read as table cells" is a
  sample plus a proxy, not a classification of all 32.
- **Generalisation beyond four books.** Two of the four have figures at all.

## Changelog

- **2026-08-07 (confirmed)** — paid before/after on the two books the census pointed at. The targeted
  class is eliminated: zero captions and zero images absorbed, against 20 and 19 before, exactly the
  prediction. `source_role_denials` reads 18 and 18 because it counts merges prevented and three of
  those boundaries were not merge candidates this run. No text lost, acceptance unchanged, narration
  joins up not down. The two books predicted to gain nothing were not paid for.

- **2026-08-07 (review)** — an independent read-only review returned BUILD WITH CORRECTIONS, and the
  corrections were checked against the code before being accepted. The refusal moved out of
  `_entry_is_protected_boundary` — which is bypassable through the `false_fragment_heading` branch at
  `:1283`, and whose counter fires before the shape predicates and would have measured adjacencies
  instead of saved boundaries — and onto the choke point spec 057 already proved, ordered after the
  terminal refusal so the two counters stay mutually exclusive. The placeholder-regex loophole in
  Non-goals was closed outright. Half B was split into two defects: the importer's polluted level-3
  role, and this assembler's own override of genuine source headings, which is what destroys the four
  real ones. The anti-vacuum was made exhaustive rather than a sample of ten, and the overlap with
  spec 057 measured: 40 pairs, 1 already refused, **39 new**.
- **2026-08-07** — spec created after spec 057 shipped and repaid 25 of 391 boundaries corpus-wide. The
  residue was measured by source role rather than guessed at: 72 of the 391 absorbed paragraphs carry a
  structural role in the source, on all four books. The census then split the target in two, and the
  half that looked most obvious — protect the headings — turned out to be 28/32 importer mis-roles and
  is deliberately NOT built here.
