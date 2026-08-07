# Feature Specification: The merge destroys boundaries the source marks with a ROLE — and only one half of that is ours to fix

**Feature Branch**: `[058-merge-destroys-role-marked-boundary]`

**Created**: 2026-08-07

**Date**: 2026-08-07

**Status**: **READY — measured 2026-08-07 on four books, not started.** Every number below is an
offline census of the four delivered runs of 2026-08-07, cross-read against each run's own
`translation_quality_report.boundary_recovery`.

**Owner surface**: `pipeline/output_validation.py` — `_entry_is_protected_boundary`,
`_entries_can_participate_in_merge`

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

1. An entry whose **source role is `image`** is a protected boundary. Nothing merges into it and it
   merges into nothing.
2. An entry whose **source role is `caption`** is a protected boundary, for the same reason: the source
   states it is a unit.

Both are properties of the input document, already carried on the entry (`FinalAssemblyEntry.role` /
`structural_role`, filled from `ParagraphUnit`). No word list, no threshold, no per-book literal, and
nothing read off the translation.

Half B is handed to a future spec against the **import** stage: the level-3 heading role is being given
to table cells and signature lines, and that is where it must be fixed. This spec does not touch it.

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

**Not one of the 40 is a genuine repair.** All four shapes were read with both halves quoted:

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

## Non-goals

- **Do not protect `role=heading` here.** 28 of the 32 are import mis-roles; protecting them entrenches
  them. Named, measured, and deliberately left.
- **Do not re-derive a caption or an image from the shape of the text.** The role either arrives from
  the source or it does not exist. No `Figure \d+` pattern, no placeholder-looking regex as a
  *substitute* for the role — matching the placeholder token is acceptable only as a second reading of
  a role that is already there.
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
   Expected: **40** boundaries recovered — 1 / 20 / 0 / 19. Zero on Rethinking Money is the predicted
   result, not a failure; if the run instead shows refusals there, the rule is doing something this
   census did not predict and must be re-read before merge.
5. **No text lost.** `source_count` unchanged per book; delivered paragraph count rises by about the
   number of refusals.
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

- **2026-08-07** — spec created after spec 057 shipped and repaid 25 of 391 boundaries corpus-wide. The
  residue was measured by source role rather than guessed at: 72 of the 391 absorbed paragraphs carry a
  structural role in the source, on all four books. The census then split the target in two, and the
  half that looked most obvious — protect the headings — turned out to be 28/32 importer mis-roles and
  is deliberately NOT built here.
