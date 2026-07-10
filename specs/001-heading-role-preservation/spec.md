# Feature Specification: Preserve source-backed heading roles in the produced DOCX

Date: 2026-07-10
Status: Implemented (2026-07-10). Verified on all four books against the produced DOCX.
Owner surface: final DOCX assembly (`runtime_display_markdown` → `convert_markdown_to_docx_bytes`)
Companion: `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` (its 2026-07-10 Changelog
retraction is the origin of this spec); `docs/specs/GLOBAL_PLAN_2026-06-16.md`
Changelog:
- 2026-07-10 — Created after four fresh full-tier runs showed chapter headings demoted in every book.
- 2026-07-10 — Implemented and verified on all four books. TWO demotion paths existed, not one: the
  false-fragment pass AND `normalize_list_fragment_regressions_markdown` (the markdown twin of the entry-level
  pass `da6789b` guarded). The first fix alone made acceptance PASS while the DOCX still rendered
  `24. Глава IV` — the green-gate-over-broken-document trap this spec warns about. Verified against the DOCX.

## Result (2026-07-10, verified on the produced artifacts)

| Book | Acceptance before → after | Loss-counted paragraphs | of which headings | bad pairs |
|---|---|---|---|---|
| Money | fail → **pass** | 17 → 2 | 13 → 1 | 0 → 0 |
| Lietaer | fail → **pass** | 25 → 2 | 16 → 2 | 0 → 0 |
| Mazzucato | fail → fail (`list_fragment_regressions_present`, 5 before and after — unrelated) | 2 → 0 | 2 → 0 | 0 → 0 |
| CreatingWealth | fail → **pass** | 20 → 7 | 10 → 4 | 0 → 0 |

Money's six chapter openings are `Heading 1` with no `numPr`. No threshold was changed. Suite 1856 passed;
pyright ratchet unchanged at 244.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Chapter headings survive into the delivered document (Priority: P1)

A translator opens the produced DOCX. Every heading that carried a heading role in the source document is a
heading in the output, with a style weight consistent with its source level. It is not body text, and it is not
a numbered list item.

**Why this priority:** heading transfer with correct style weight is the project's first stated quality
priority. Everything else in the document is navigable only if the headings are right.

**Independent Test:** run any book full-tier; open the DOCX; assert every source-declared chapter heading
carries a `Heading N` style and no `numPr`.

**Acceptance Scenarios:**

1. **Given** a source chapter heading preceded by a footnote/reference tail that ends without sentence-terminal
   punctuation, **When** the document is assembled, **Then** the heading is rendered as a heading, not folded
   into the preceding line.
2. **Given** a chapter title split across two source paragraphs (a number line and a title line, or two title
   lines), **When** the document is assembled, **Then** both survive as headings and neither is absorbed into a
   neighbouring paragraph.
3. **Given** a heading-looking line invented by the translation model with NO source heading role, **When** the
   document is assembled, **Then** the existing false-fragment cleanup still demotes/merges it as before.

### Edge Cases

- A protected heading immediately follows another protected heading (Money: `# Глава IV`, `## Объяснение
  нестабильности:`, `## Физика сложных потоковых сетей`). None may be merged into another.
- A model-invented fragment sits directly after a protected heading. Merging the fragment INTO the real heading
  remains allowed — that is the cleanup's intended repair.
- The generated-paragraph registry is unavailable (fallback markdown paths). Behaviour must be exactly today's.

## Verified findings

All claims verified 2026-07-10 against fresh full-tier runs (`20260710T_money_verify`,
`20260710T_lietaer_verify2`, `20260710T_mazzucato_verify2`, `20260710T_creatingwealth_verify2`). Saved fixtures
were NOT used (Constitution VIII).

- **The gate validates a different document than the user receives.** Quality/report logic reads
  `final_markdown` (source-aware). The DOCX is rebuilt from `runtime_display_markdown`
  (`src/docxaicorrector/pipeline/late_phases.py:1080`), produced by
  `_normalize_final_markdown_for_runtime_display` (`late_phases.py:139`). Same run, Money:
  `false_fragment_heading_count = 0` next to `raw_false_fragment_heading_count = 52`.
- **The demoting pass is source-blind.** `normalize_false_fragment_headings_markdown`
  (`src/docxaicorrector/pipeline/output_validation.py:1682`) is a pure text/regex pass. It receives no registry
  and cannot distinguish a real chapter heading from a model-invented fragment. Its call site comment
  (`late_phases.py:126`) calls the pass "display-only"; `late_phases.py:1080` makes it the delivered document.
- **The trigger is the preceding line, not the heading.** `_is_continuation_like_previous_line`
  (`output_validation.py:345`) returns True whenever the previous line lacks sentence-terminal punctuation. A
  short heading (≤ `_INLINE_HEADING_FRAGMENT_MAX_WORDS`) after such a line is demoted and merged
  (`output_validation.py:1740-1748`).
- **Live evidence, Money** (`Money_Sustainability_pdf_full_heldout.md`): lines `950: 24. Глава IV Объяснение
  нестабильности: Физика сложных потоковых сетей`, `1232: 16. Глава V`, `1536: 30. Глава VI …`,
  `1763: 3. Глава VII …`. Chapters VIII/IX follow prose sentences and survive as `# Глава VIII` / `# Глава IX`.
  In the DOCX: `para#484/625/777/891` are `Normal` with `numPr`; `para#1101/1249` are `Heading 1`.
- **Not per-book.** Lietaer: 16 of 25 loss-counted paragraphs are source headings, in adjacent pairs
  (`[187 body "the myth of money"] + [188 heading "what it really is"]`). CreatingWealth: `[183 "crash and"] +
  [184 "burn economics"]`; the body chapter opening is absent as a heading. Mazzucato: chapter 7 is folded into
  the next sentence (`7 Извлечение стоимости через инновационную экономику Во-первых, инвест…`).
- **The gate cannot see it.** `classify_heading_demotions` compares MAPPED pairs only; these headings have
  `mapped_target_index = None`, so it reports 0. They surface on the unmapped-source axis and are what fails
  acceptance (Money 17 vs 16; CreatingWealth 20 vs 16; Lietaer 25 vs 12).
- **The needed data is already at the call site.** `_registry_heading_markdown_lines`
  (`late_phases.py:153`) already derives heading lines from the generated-paragraph registry, and both display
  call sites (`late_phases.py:3526`, `:3856`) already hold `assembly_registry or state.generated_paragraph_registry`.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII, item 8): detection keys on the source-declared heading role carried by the
> registry. No word lists, no signal counts, no literal taken from one book.

- **FR-001**: `normalize_false_fragment_headings_markdown` MUST accept an optional collection of protected
  heading texts derived from the generated-paragraph registry.
- **FR-002**: The pass MUST NOT demote a heading line whose normalized text matches a protected heading.
- **FR-003**: The pass MUST NOT merge a protected heading into a preceding line, nor absorb a protected heading
  as the trailing line of a merge.
- **FR-004**: When no registry is supplied, behaviour MUST be byte-identical to today's.
- **FR-005**: Heading lines with no source heading signal MUST continue to be demoted and merged exactly as
  today (the cleanup's intended repair of model-invented fragments).
- **FR-006**: The call-site comment claiming the pass is "display-only" MUST be corrected: its output is the
  delivered DOCX.

### Key Entities

- **Generated paragraph registry** — per-paragraph records carrying the source-declared `role`,
  `structural_role`, `heading_level`, and the generated markdown text.
- **Protected heading** — a registry entry whose generated text is a markdown heading line and whose source
  paragraph carried a heading signal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In a fresh Money run, chapters IV, V, VI, VII render as `Heading N` in the DOCX with no `numPr`;
  the output markdown contains no `24. Глава IV`-style line.
- **SC-002**: Money's effective unmapped-source count drops from 17 to ≤16, so `unmapped_source_threshold` and
  `formatting_diagnostics_threshold` pass without changing any threshold.
- **SC-003**: The full test suite stays green; `tests/test_document_pipeline_output_validation.py` passes
  unchanged (its cases pass no registry, exercising FR-004).
- **SC-004**: A model-invented heading fragment with no source heading role is still demoted (counter-test).

## Non-goals

- **Not fixing the mapping recovery.** Once the target is a merged `Normal` paragraph, `formatting_transfer`
  cannot re-attach the role. This spec removes the cause; it does not add a recovery path.
- **Not changing the acceptance thresholds**, not restoring the removed attribution word list, not touching any
  detector. Acceptance is expected to pass as a consequence of the fix, not by relaxing a gate.
- **Not unifying `final_markdown` and `runtime_display_markdown`.** The deeper architectural defect — the gate
  measuring a different artifact than the one delivered — is recorded in the companion spec and left for a
  separate decision.
- **Not repairing the source-side split of a chapter title into two paragraphs.** That is PDF import shape; the
  two paragraphs may remain two headings. Verified 2026-07-10 on Lietaer: the first line arrives `role=body`, so
  it stays body text and only the second line becomes a heading. Faithful, not pretty.
- **Not repairing headings the source never declared** (Constitution VII, "No source signal, no repair").
  Mazzucato's chapter 7 arrives from PDF import as `role=body, heading_level=None`; it renders as body text and
  that is ACCEPTED. Promoting it would require guessing from a leading ordinal — the exact per-book heuristic the
  constitution forbids. The honest alternatives are an import fix or acceptance, never a guess in the assembler.
- **TOC and footnotes stay out of scope.** A demoted heading inside the bounded TOC region is accepted.
- Any residual heading defect for which no general, registry-keyed rule exists is **ACCEPTED, not patched**
  (Constitution VII).

## Anti-regression

- **The false-fragment cleanup must keep working.** A heading line absent from the registry (model-invented)
  must still be demoted and merged. Counter-test required: without it, this change silently disables the
  cleanup and reintroduces the fragment headings it was written to remove.
- **No registry ⇒ no change.** Existing tests in `tests/test_document_pipeline_output_validation.py` call the
  normalizer with plain markdown and must pass untouched.
- **Protected headings must not be merged into each other.** Money's three consecutive chapter-IV heading lines
  are the counter-example; assert all three survive.
- **`raw_false_fragment_heading_count` must not be used to judge success.** It is computed on the source-aware
  `final_markdown`. Success is measured on the produced DOCX (Constitution VIII).
- Verify on all four books before closing; a fix that helps Money and harms another book is not a fix.

## Assumptions

- The generated-paragraph registry entries for a source heading carry the heading markdown (`# …`) as their
  generated text. Verified for Money entries `p0509`/`p0510`/`p0511` (`generated_text = "# Глава IV"`, etc.).
- `_normalize_heading_match_text` normalization is sufficient to match a registry heading against its markdown
  line after translation, since both sides come from the same generated text.
