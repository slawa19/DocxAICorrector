# Feature Specification: PDF text-layer import preserves font size so universal heading form evidence survives

**Feature Branch**: `[049-pdf-import-preserves-font-size]`

**Created**: 2026-07-21

**Status**: **MEASURED — PREMISE DISPROVEN (2026-07-21).** The change was implemented exactly as
specified and works mechanically (sizes are now written and reach the classifier), but a
before/after measurement on two real books shows it recovers ZERO headings and costs one. Its
Success Criteria cannot be satisfied. Per Constitution VIII a criterion that can no longer be
satisfied is a defect in the SPEC, not a gap in the implementation — so this document is kept as
the recorded negative result. See `## Measured outcome`. Recommendation: revert the code change;
keep this spec so the idea is not re-proposed.

**Input**: User description: "Fix the import so a real structural signal exists, instead of inventing a new heading heuristic to recover the subheadings spec 046 demoted."

**Date**: 2026-07-21

**Owner surface**: PDF text-layer → intermediate DOCX serialization, and the downstream paragraph form metadata that depends on it

**Companion**: `specs/046-universal-short-heading-evidence/spec.md` (removed the length-only shortcut this feature makes unnecessary); `docs/reviews/CODE_REVIEW_ROUND10_2026-07-20.md` (F5); round-11 golden audit; `.specify/memory/constitution.md` (Principle VII)

**Changelog**:

- 2026-07-21 — Initial specification. Owner chose "fix the import" over adding a bold-only heading rule, after the round-11 golden audit quantified the residual left by spec 046.

## Problem (verified 2026-07-21 against `c5cdab0`)

Spec 046 correctly removed a rule that promoted any ≤4-word paragraph to a heading purely because it was short — a text-shape rule forbidden by Constitution VII. What that removal exposed is that for PDF-derived documents **no form evidence reaches the classifier at all**, so the surviving universal rule can never fire:

- The PDF importer *computes* per-paragraph font size and stores it: `src/docxaicorrector/pdf_import/logical_import.py:434` sets `font_size_pt=first.font_size_pt` on the emitted `ParagraphUnit` (sizes come from the pdfminer spans it already clusters for its own layout profile).
- That value is **dropped** when the importer serializes to the intermediate working DOCX: `src/docxaicorrector/processing/processing_runtime.py::_append_pdf_text_paragraph_to_docx` writes a paragraph style, and per-run `bold`/`italic`, but never a run font size.
- Extraction then re-reads that DOCX and resolves `font_size_pt` from the runs (`src/docxaicorrector/document/extraction.py:579` via `resolve_effective_paragraph_font_size`), so every PDF-derived paragraph arrives with no usable size.
- The universal form rule in `src/docxaicorrector/document/roles.py:230-246` requires a candidate font size AND at least one context font size before it will consider a promotion (bold/centered only lowers the required delta from 1.5 to 1.0 pt). With no sizes, it exits early for every candidate.

Consequence measured in the round-11 golden audit: across the four real-book fixtures, 43 paragraphs changed from heading to body after spec 046, and roughly 30 of them are genuine intra-chapter subheadings (creatingwealth 18 of 20, mazzucato 6 of 6, money 5 of 6). The fixtures themselves show the source evidence that is being discarded — e.g. `best_source_text_preview: "**Human and societal costs**"` — these lines are typographically distinct in the source, and the importer knew it.

Constitution VII names exactly this situation and its permitted resolutions: *"The honest options are: fix the IMPORT so a real signal exists, or accept. Never guess in the assembler."* This feature takes the first option. It deliberately does **not** add a bold-only promotion rule to the assembler, because that rule was discovered by inspecting four specific books and would need per-book validation to trust; restoring the real signal lets an **already existing, book-independent** rule do the work.

## Measured outcome (2026-07-21) — the premise does not hold

The change was implemented, unit-tested (including the false-positive, threshold and noise
counter-proofs this spec demands) and then measured end-to-end by running the structural
preparation diagnostic twice per book: once with the change in the tree and once with it stashed
out. Everything else was identical.

| Book | headings without the change | with the change |
|---|---|---|
| `mazzucato-pdf-full-benchmark` | 127 | 127 |
| `money-sustainability-pdf-full-heldout` (held out) | 176 | **175** |

Paragraph counts, semantic block counts and gate status were byte-identical in both pairs
(mazzucato 2314/309/pass, money 1435/286/pass). So: **zero headings recovered, one heading lost on
the held-out book.**

Why the premise failed — measured directly from the PDFs' text spans:

| Book | spans | bold spans | dominant sizes |
|---|---|---|---|
| mazzucato | 11399 | **1** | 14.99 (10984), 11.25 (256), 9.0 (130), 20.99 (25) |
| lietaer | 9200 | 117 | 10.97 (6476), 8.47, 8.97, 10.47 |
| creatingwealth | 6305 | 73 | 14.4 (5687), 10.8, 5.76, 20.16 (31) |
| money & sustainability | 5605 | 211 | 14.4 (4026), 10.8, 5.76, 16.56 (69) |

The importer did resolve sizes (all spans carry one) and the serializer did drop them — that half of
the diagnosis was correct. What is not correct is the assumption that the lost subheadings are
typographically distinct in the source. In mazzucato 96% of the book is one size and the whole book
contains a single bold span; in the other books the subheadings are bold at body size, so a size
delta cannot separate them either. The sizes that ARE larger (20.99, 28, 20.16) are chapter titles
the importer already recognised — hence the unchanged heading counts.

The one lost heading on the held-out book is the risk FR-005 was written to catch: restoring sizes
activated front-matter display-title normalisation (`roles.py`, ≥18 pt), previously unreachable on
PDF input, which demoted a competing front-matter heading. The characterisation test predicted this
behaviour; the corpus measurement shows its net effect is negative.

Consequence for the original problem: the ~30 subheadings that spec 046 stopped inventing are NOT
recoverable from source form evidence. Both candidate signals — size and weight — have now been
measured and neither separates them. Under Constitution VII this is an ACCEPTED tail, and it is now
accepted on the basis of measurement rather than assumption.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Subheadings survive a PDF import (Priority: P1)

As a user importing a PDF whose subheadings are typographically distinct from body text, I get those subheadings recognised as headings, because the import preserves the typographic evidence the source actually carries.

**Why this priority**: heading structure drives block boundaries, output formatting, navigation, segmentation and validation. Today every PDF-derived document loses it wherever the source relies on typography rather than an explicit style.

**Independent Test**: import a synthetic PDF-shaped document whose section lines are larger and/or bold relative to their neighbours, and verify those paragraphs carry a heading role after preparation while ordinary body paragraphs do not.

**Acceptance Scenarios**:

1. **Given** a PDF-derived paragraph whose font size exceeds its neighbours by the existing threshold, **When** the document is prepared, **Then** it is recognised as a heading by the existing form rule.
2. **Given** the same document, **When** preparation completes, **Then** paragraphs whose size matches their neighbours remain body regardless of length, capitalisation or leading ordinals.
3. **Given** a PDF whose spans carry no usable size information at all, **When** the document is prepared, **Then** behaviour is unchanged from today (no size, no promotion) and no error is raised.

---

### User Story 2 - No new guessing is introduced (Priority: P1)

As a maintainer, I need this recovery to come entirely from restored source evidence, so that no book-specific or text-shape rule enters the classifier through the back door.

**Why this priority**: the residual being closed was created by removing exactly that kind of rule. Re-introducing one — even a plausible one such as "bold means heading" — would repeat the mistake with a different signal.

**Independent Test**: inspect the diff for any new classification rule; confirm the only behavioural change is that previously-absent form metadata is now populated, and that promotion thresholds are untouched.

**Acceptance Scenarios**:

1. **Given** the change, **When** the promotion rule is examined, **Then** its predicates and thresholds are byte-identical to the pre-change implementation.
2. **Given** a paragraph that is bold but typographically identical in size to its context, **When** it is prepared, **Then** it is promoted only if the existing rule's reduced delta is genuinely met — bold alone does not promote.

---

### User Story 3 - Restored metadata does not silently change other behaviour (Priority: P2)

As a maintainer, I need the newly populated font metadata to have a known, reviewed effect on every consumer that reads it, not just the heading rule.

**Why this priority**: the value moves from "always absent" to "usually present" for a whole document class, so consumers that were effectively dead on PDF input become live at once.

**Independent Test**: enumerate the consumers of paragraph font size, and characterise each one's behaviour on PDF-derived input before and after the change.

**Acceptance Scenarios**:

1. **Given** a PDF-derived document with a large title, **When** front-matter title normalisation runs (its rule requires a size at or above 18 pt, `src/docxaicorrector/document/roles.py:541`), **Then** its new behaviour on PDF input is characterised by a test rather than discovered in production.
2. **Given** a PDF-derived document, **When** stage-0 font-size z-scores are computed (`src/docxaicorrector/document/extraction.py:757` and `:805`), **Then** they are populated and their effect on downstream classification is characterised.

### Edge Cases

- Spans with a missing, zero or implausible size must not produce a run size; the paragraph simply keeps no size, exactly as today.
- Fractional sizes from the extractor (for example 10.98) must not make two visually identical paragraphs differ; a documented normalisation applies before the value is written.
- A document whose body size varies slightly page to page must not turn ordinary paragraphs into headings; the existing rule compares against immediate neighbours, and the normalisation must not amplify noise into a threshold-crossing delta.
- Headings that already arrive with an explicit heading style keep it; restored sizes must not demote or duplicate them.
- Legacy DOC and native DOCX inputs are unaffected — they never pass through this serializer.

## Requirements *(mandatory)*

> **Binding rule for detection/classification (Constitution VII)**: detection MUST key on document region, structural role, or form. This feature adds no detection rule at all; it restores a form value that the source document already carries. No word list, no per-book literal, no text-shape predicate may be introduced by this work.

- **FR-001**: The PDF text-layer serializer MUST write the paragraph's font size onto the runs it creates when the importer resolved a usable size for that paragraph.
- **FR-002**: When no usable size was resolved, the serializer MUST write no size and MUST leave downstream behaviour identical to today.
- **FR-003**: A documented, deterministic normalisation MUST be applied to the size before it is written, so that extractor noise does not create artificial differences between typographically identical paragraphs. The normalisation MUST be uniform across the document and MUST NOT be tuned per document.
- **FR-004**: The existing heading-promotion rule, including its context requirements and its 1.0/1.5 pt thresholds, MUST remain unchanged. This feature MUST NOT add, widen, or re-key any classification rule.
- **FR-005**: Every consumer of paragraph font size that becomes newly live for PDF-derived documents MUST have its resulting behaviour covered by a characterisation test — at minimum the heading-promotion rule, front-matter display-title normalisation, and stage-0 font-size z-scores.
- **FR-006**: Legacy DOC and native DOCX upload paths MUST be behaviourally unchanged.
- **FR-007**: The change MUST NOT introduce new external calls, new preparation stages, new artifacts, or new logging events.
- **FR-008**: Regenerated golden fixtures MUST be reviewed in BOTH directions: recovered real headings are the goal, but any paragraph newly promoted that is not a genuine heading MUST be identified and explained before the fixtures are accepted.

### Key Entities

- **Imported paragraph**: a PDF-derived paragraph carrying text, role, emphasis runs and — after this change — its resolved font size.
- **Intermediate working DOCX**: the synthetic document the importer produces and the rest of the pipeline consumes; it is the only channel through which import-side evidence can reach the classifier.
- **Form evidence**: source-carried typographic metadata (size, weight, alignment) usable for classification without inspecting the words.

## Success Criteria *(mandatory)*

- **SC-001**: For synthetic PDF-shaped inputs, 100% of paragraphs whose source size exceeds their neighbours by the existing threshold are recognised as headings, and 100% of size-matched controls remain body.
- **SC-002**: Zero new classification rules and zero threshold changes appear in the diff; the promotion predicate is unchanged.
- **SC-003**: On the four real-book golden fixtures, the number of genuine subheadings recovered is reported explicitly, and every newly promoted paragraph is classified as genuine or false, with false promotions at zero or individually justified.
- **SC-004**: A book not used while developing the change confirms the same direction of effect, so the result is not an artefact of the fixtures that motivated it.
- **SC-005**: The mazzucato full-book profile's `min_headings` pin (`corpus_registry.toml`) is re-validated against a fresh benchmark run and corrected if the honest count changed.
- **SC-006**: Legacy DOC and native DOCX regression tests are unchanged and green.

## Non-goals

- Adding a bold-only, all-caps, centred-only or any other new promotion rule — the entire point is that restoring the real signal makes a new rule unnecessary. A book-motivated rule would require per-book validation this feature is designed to avoid.
- Changing the promotion thresholds or the context window of the existing rule.
- Recovering headings in documents whose source genuinely carries no typographic distinction — that remains an accepted tail under Constitution VII.
- Two-column PDF reading order and its refusal gate — a separate concern with its own spec; both touch the importer, so they are kept in separate branches.
- Preserving further typographic attributes (colour, letter spacing, kerning) — only the size needed by the existing rule is in scope.
- Re-tuning golden fixtures until the four motivating books look correct. Fixtures are regenerated once and audited; they are evidence, not a target.

## Anti-regression

- **False-positive counter-proof**: a synthetic document whose paragraphs are all the same size, some bold, MUST produce zero promotions. Restoring sizes must not turn emphasis into structure.
- **No-signal counter-proof**: the spec-046 test proving a no-signal short body paragraph stays body MUST remain green and unmodified.
- **Explicit-heading invariant**: a paragraph arriving with an explicit heading style keeps its role and level; restored sizes must not alter it.
- **Threshold invariant**: a paragraph whose size exceeds its neighbours by less than the existing required delta MUST remain body — proving the recovery flows through the existing rule and not around it.
- **Noise invariant**: two paragraphs whose raw extracted sizes differ only by extractor noise MUST normalise to the same value and MUST NOT produce a promotion.
- **Golden audit in both directions**: the regenerated fixtures MUST be diffed for newly promoted paragraphs as carefully as for recovered ones; a promotion that cannot be explained by source typography blocks acceptance.
- **Unaffected paths**: legacy DOC and native DOCX fixtures and tests MUST be unchanged.
- No credit or subtraction rule is introduced, so Constitution VII's anti-vacuum counter-proof requirement is satisfied by the paired promotion/no-promotion cases above.

## Assumptions

- The sizes the importer already resolves are good enough to drive the existing rule; if a corpus shows they are not, the honest response is to improve the importer's size resolution, not to loosen the promotion rule.
- The intermediate working DOCX is the correct place to carry this evidence, consistent with the existing contract that PDF is an input format and not a parallel internal document model.
- Golden fixtures will change; that is expected and is the mechanism by which the effect is reviewed.
- Full verification uses the canonical WSL entry points defined in `AGENTS.md`; the real-document benchmark run needed for SC-004 and SC-005 belongs to implementation, not to specification.
