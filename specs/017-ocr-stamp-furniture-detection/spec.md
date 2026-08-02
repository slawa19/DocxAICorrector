# Feature Specification: OCR stamp / classification-marker furniture detection

Date: 2026-07-13
Status: IMPLEMENTED (2026-08-02) on branch `feat/017-ocr-stamp-furniture`. Status lines are not authoritative;
see the Changelog below and `git log` for `document/layout_cleanup.py`.
Owner surface: `document/layout_cleanup.py` (furniture detector).

## Problem (verified 2026-07-13; causes re-verified and corrected 2026-08-02 — see Changelog)

An OCR'd classification stamp such as "Secret" / "Секретно" / "Для служебного пользования", repeated across pages,
is NOT recognized as furniture and leaks into the translated output as content. Two causes:
1. It is absent from `BOILERPLATE_TOKENS` (`layout_cleanup.py:34-42` = confidential/draft/copyright/конфиденциально/
   черновик/все права защищены — no secret/classification markers).
2. The generic repeated-artifact path requires `layout_origin == "textbox"` (`layout_cleanup.py:319`); an OCR stamp
   imported as a normal paragraph (`layout_origin == "paragraph"`) never matches even when it repeats ≥3×, so it
   falls through to `uncertain_repeated_artifact` and is kept.
3. Even if flagged, cleanup runs in flag-only mode (`layout_cleanup.py:206-212`, `removed_paragraph_count=0`), so a
   flagged stamp is still not removed and is translated.

The reworked output gate will NOT catch it — a stamp present in source and faithfully carried to output is not a
formatting-TRANSFER discrepancy (the gate's axis), so it is invisible there.

## Likely fix surface (to be specced when scheduled)

- Extend furniture detection with a stamp/classification-marker set (multilingual) and/or a dedicated repeated-stamp
  detector that does not require textbox origin (repeated short uppercase marker across pages).
- Decide flag-vs-remove policy for stamps (removal needs `cleanup_mode="remove"` or a targeted drop, since flag mode
  never deletes) — universal rule only, no per-document literals (Constitution VII); anti-vacuum counter-proof that
  real repeated body text is not eaten.

## Non-goals (for now)

- Not part of `specs/015` (summary simplification) or `specs/016` (drop partial translation). This is a standalone
  content-quality fix to be scheduled separately.

## Anti-regression

This spec is BACKLOG (not implemented); the guards below become mandatory when it is scheduled and built:

- The stamp/classification-marker detector MUST use a universal multilingual rule set only — NO per-document or
  per-book literals (Constitution VII) — pinned by a deny-list test over the furniture-detection module.
- An anti-vacuum counter-proof: real repeated short body text (e.g. a legitimately recurring heading or refrain)
  MUST NOT be removed by the repeated-stamp detector — a fixture test asserting non-removal of a benign repeated line.
- Existing furniture-detection behaviour for the current `BOILERPLATE_TOKENS` / textbox-origin paths MUST stay
  byte-identical for inputs that do not contain a classification stamp (no regression to today's cleanup decisions).

## Changelog

### 2026-08-02 — implemented; the recorded cause was incomplete (Constitution VIII)

The three causes above were re-verified against current code before any edit. Measured on
`tests/sources/book/RESISTANCE FACTORS AND SPECIAL FORCES AREAS UKRAINE.docx` (2069 paragraphs, 167 occurrences of
the "SECRET" stamp), the split is:

| survival path | occurrences | code |
| --- | --- | --- |
| `protected_role_keep` — import mis-promoted the stamp to `role=heading` / `caption` / `toc_entry` | 145 | `layout_cleanup.py:_is_protected`, applied before any repetition analysis |
| `layout_origin != "textbox"` (the cause the spec named) | 5 | the textbox gate in `_repeated_artifact_reason` |
| detected as `repeated_running_header` but only FLAGGED, never removed | 17 | flag-only mode |

So cause 2 accounted for 5 of 167. The dominant blocker was the protected-role gate, which the spec did not mention:
a short all-caps stamp is routinely promoted to a heading at import, and the protection filter then exempts it from
repetition analysis entirely.

**What was built.** A page-cadence furniture detector
(`_collect_page_cadence_furniture_fingerprints` / `_is_page_cadence_candidate`, `layout_cleanup.py`). A normalized
block is furniture when its occurrences (a) number at least `PAGE_FURNITURE_MIN_REPEAT_COUNT`, (b) span at least
`PAGE_FURNITURE_MIN_DOCUMENT_SPAN_RATIO` of the document, and (c) recur with a mean gap no larger than
`PAGE_FURNITURE_MAX_MEAN_PARAGRAPH_GAP` paragraphs. That is page cadence — furniture sits in the same slot on every
page. Section structure that legitimately repeats (a per-chapter heading, a part divider echoed in the TOC) recurs at
chapter cadence, an order of magnitude further apart. The detector is blind to `role` and `layout_origin`, because
which of those an occurrence got is an accident of the converter, not evidence about the block.

A fourth condition bounds the blast radius: a block accounting for more than
`PAGE_FURNITURE_MAX_DOCUMENT_SHARE` (20%) of the document is kept whatever its cadence. Furniture is a thin overlay —
the measured stamp is 8% of its document — whereas a refrain or a recurring speaker label in a play would meet page
cadence trivially and gutting the text is not a decision a heuristic should make silently. That class is NOT in the
corpus, so the bound is a guard, not a measured result; see the residual-risk note below.

**Residual risk (honest, unmeasured).** The corpus contains no play, no libretto and no poem with a refrain. A short
non-sentence block that a book genuinely repeats once every few paragraphs, from the first page to the last, and that
stays under 20% of the document, would be removed. No such block exists in the five books measured, and the 20% bound
caps the damage, but this class has not been tested against a real document. If one shows up, the axis to add is a
position-within-page signal, not a vocabulary.

**No word list was added** (Constitution VII): `BOILERPLATE_TOKENS` is unchanged, and
`test_furniture_detection_carries_no_classification_marker_vocabulary` pins the absence of classification-marker
literals in the module.

**Flag-vs-remove.** Resolved as a targeted drop: page-cadence furniture is removed in BOTH cleanup modes. Flag mode
exists so that UNCERTAIN structure decisions stay visible to AI-first structure recovery; a block recurring once per
page across the whole document is not a structure decision, and flagging alone leaves it translated once per page —
the defect would be unfixed under the default configuration. `LayoutArtifactCleanupReport.removed_page_furniture_count`
records these drops, and the flag-mode branches of `flatten_layout_cleanup_metrics`
(`processing/preparation.py`, `processing/application_flow.py`) and `_build_structural_metrics`
(`validation/structural_checks.py`) add it so the drop is not invisible in metrics.

**Measured effect (5-book corpus, 9328 paragraphs).** One block accepted in total: the "SECRET" stamp, 167/167
occurrences removed (163 `SECRET`, 3 `Secret`, 1 `secret`; 130 paragraph-origin, 37 textbox-origin). All 86 images and
all 86 image placeholders in that document survive. Zero removals in the other four books — behaviour unchanged.

**Accepted tail (no general rule, so not patched).** OCR garble variants of the same stamp that do not reach page
cadence — `^SECRET` (3 occurrences), and the declassification marking `50X1-HUM` (10 occurrences, mean gap 229
paragraphs) — are kept. Catching them needs fuzzy text matching, which is the word-list route this spec forbids.

**Not done, deliberately.** The textbox gate in `_repeated_artifact_reason` was left in place. It accounted for 5 of
167 occurrences, all now covered by the page-cadence rule; widening it to every layout origin would newly flag
part-dividers such as `PART II` at three repeats, a regression with no measured benefit.
