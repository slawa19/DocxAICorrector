# Feature Specification: Detect broken (mid-sentence-split) paragraphs

Date: 2026-07-11
Status: ACTIVE forward spec
Owner surface: `translation_quality_report` — a new advisory paragraph-break metric
Companion: `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md`; a follow-up REPAIR spec (009)
will act on this signal. This spec is DETECTION ONLY — it changes no delivered bytes.
Changelog:
- 2026-07-11 — Created from the paragraph-break universality audit.
- 2026-07-11 — FR-007 implemented (region scoping). Re-measure over the four saved reports
  corrected one example: Money "doraland p.142 ‖ wellness tokens p.144" (source_index 958/965)
  is NOT back-matter — it is a MID-BOOK "NGO/government initiatives" resource directory tagged
  `toc_entry`, sitting inside the main-content span (body-start boundary 144 … bibliography 1380),
  so region scoping does NOT exclude it and it stays flagged. It is an accepted in-body advisory
  false-positive of the same class as the contributor bios (repair 009 excludes it); forcing it
  out would need an "index/page-ref-form" text heuristic, which Constitution VII forbids. The
  genuinely-back-matter cases — Money front-matter bios (62/66) and Lietaer INDEX entries
  (>= 1801) — ARE excluded by region, and the Money flagship (219) stays flagged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Broken paragraphs become visible (Priority: P1 for this feature; overall priority 4)

The report flags where one source paragraph was split into two mid-sentence, so the priority-4 defect
("no broken paragraphs or lines") is finally reported instead of silently passing.

**Why this priority:** ~11 genuine mid-sentence splits per corpus (flagship Money: "…банковских кризисов и
денежных" ‖ "крахов нашего времени.") are reported by NO gate axis today. Detection is the prerequisite for any
repair and is safe (a report number, not a document change).

**Independent Test:** run the detector over a saved report's `source_registry`; it flags the adjacent pairs that
share one source paragraph with a mid-sentence boundary, and does NOT flag genuinely-separate paragraphs.

**Acceptance Scenarios:**

1. **Given** two adjacent `source_registry` entries sharing `origin_raw_indexes`, where the first `text_preview`
   ends without sentence-terminal punctuation and the second starts lowercase/continuation, **When** the detector
   runs, **Then** the pair is flagged as a likely paragraph break.
2. **Given** two adjacent entries that do NOT share `origin_raw_indexes` (genuinely separate source paragraphs —
   a bibliography/index boundary), **When** the detector runs, **Then** they are NOT flagged (no source signal).
3. **Given** a heading/list entry boundary, **When** the detector runs, **Then** it is NOT flagged (structural
   boundary, not a split).

### Edge Cases

- Multi-line bio / credential / attribution blocks (e.g. "member of the club of rome" ‖ "president of the
  cor-eu chapter") that share one raw block but are legitimately separate lines — these WILL be flagged by the
  form∩identity rule (a known false-positive class for detection). Detection is advisory, so a few false flags
  are acceptable; the REPAIR spec (009) must exclude them. Report them honestly, do not tune them away per-book.
- The first fragment ends in a footnote-marker digit ("…²") — still non-terminal for prose purposes.

## Verified findings

Verified 2026-07-11 against saved reports (deterministic — no live run needed). Constitution VIII satisfied by
reading the saved artifact.

- **The split is a PDF-import mis-tag; the signal survives.** One raw PDF block becomes two `ParagraphUnit`s both
  tagged `toc_entry`, and every merge stage skips `toc_entry` by design (`logical_import.py:372/387`,
  `output_validation.py:1151`). Both halves share `source_index` AND `origin_raw_indexes` in the saved
  `source_registry` — the universal signal that they are one paragraph. Verified on Money `source_index=219,
  raw=[220]`: "…large-scale banking crises and monetary" ‖ "meltdowns of our times.".
- **`source_registry` carries the needed fields:** `origin_raw_indexes`, `source_index`, `text_preview`,
  `structural_role`, `role`, `heading_level`, `list_kind`, `paragraph_id`.
- **Measured scale (four delivered markdowns):** ~26 form candidates; 19 share one source paragraph; ~11
  unambiguous prose splits; ~4 genuinely-separate (bibliography/index) correctly excluded by the identity key.
- **Known false-positive class:** contributor bios / epigraph attributions also share a raw block and have a
  non-terminal + lowercase boundary (Money `source_index=62`, `66`). The form∩identity rule flags them. Detection
  reports them; repair (009) must exclude them via the already-detected structural roles (attribution/caption).

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): the detector keys on structural provenance (`origin_raw_indexes`/`source_index`
> shared) ∩ language-general form (non-terminal boundary + lowercase/continuation start). NO word lists, NO
> per-book literals. A boundary with no shared-source signal is NOT flagged ("no source signal, no repair").

- **FR-001**: A new `collect_paragraph_break_samples(source_registry)` detector flags an adjacent ordered pair
  when: they share `origin_raw_indexes` (or `source_index` when raw indexes are absent), AND the first entry's
  `text_preview` ends without sentence-terminal punctuation (`.!?…:»")` and closing quotes/brackets), AND the
  second entry's `text_preview` starts with a lowercase letter or a continuation particle.
- **FR-002**: A pair whose entries do NOT share the source-paragraph signal is NEVER flagged (FR — no source
  signal).
- **FR-003**: A pair where either entry is a heading (`heading_level`/`role==heading`) or a list
  (`list_kind`) is NOT flagged (structural boundary).
- **FR-004**: The detector emits a `paragraph_break_count` and capped `paragraph_break_samples` (source + next
  text previews, source_index) into `translation_quality_report`.
- **FR-005**: The metric is ADVISORY — it does NOT hard-fail acceptance (mirror `advisory_only`, spec 004/006).
- **FR-006**: Detection changes NO delivered bytes and does NOT modify `final_markdown` or the DOCX assembly.
- **FR-007 (main-content scope — added 2026-07-11 after first measurement):** the detector MUST be scoped to the
  main-content span `[front_matter_boundary … references_region_start)`, excluding the bounded TOC region — reusing
  the SAME region provenance as `classify_heading_demotions` (`_resolve_source_front_matter_boundary`,
  `_resolve_references_region_start`, `_resolve_bounded_toc_region` in `validation/formatting_coverage.py`). First
  measurement without scoping flagged front-matter and back-matter noise — front-matter contributor bios and
  back-of-book INDEX entries ("high-powered money, 40" ‖ "hitler, adolf, 180", source_index >= 1801) — which are
  out of scope (front-matter/TOC/references/index are deliberately excluded). Region scoping removes those
  universally (by region, not by literal). Note (verified 2026-07-11): a page-ref line that sits INSIDE the
  main-content span — Money's mid-book "NGO initiatives" directory ("doraland p.142" ‖ "wellness tokens p.144",
  source_index 958/965), tagged `toc_entry` but not in any bounded front-matter/TOC/references region — is NOT
  region-excludable and stays flagged as an accepted in-body advisory false-positive (repair 009 excludes it, like
  the bios); it is NOT suppressed by an index/page-ref text heuristic (Constitution VII).

### Key Entities

- **source_registry entry** — carries `origin_raw_indexes`, `source_index`, `text_preview`, roles.
- **Paragraph-break sample** — `{source_index, text, next_text}` for the flagged pair.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On the four saved reports, the detector flags the known genuine splits (incl. the Money flagship)
  and does NOT flag the bibliography/index boundaries that are genuinely separate source paragraphs.
- **SC-002**: The advisory check never enters real `failed_checks` on any of the four books.
- **SC-003**: The detector is deterministic on the saved `source_registry` — a unit test over a fixture asserts
  exact flagged pairs (verifiable without a live run).
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not repairing (merging) the paragraphs** — that is spec 009, a delivered-byte change with its own
  verification and the bio/attribution exclusion.
- **Not fixing the PDF-import mis-tag** (`_looks_like_toc_entry`) — that is a deeper import change; detection
  works from the resulting diagnostics regardless.
- **Not hard-gating on the count** — advisory only; a book with broken paragraphs still passes acceptance (the
  count informs the review report / UI).
- The bio/attribution false-positive class is REPORTED, not suppressed per-book (Constitution VII); repair excludes it.

## Anti-regression

- **No source signal, no flag:** a bibliography boundary (separate source paragraphs) is never flagged — a
  counter-test asserts it.
- **Structural boundaries safe:** a heading→body or list boundary is never flagged.
- **Advisory only:** a test asserts the check is never in real `failed_checks` even with a nonzero count.
- **Deterministic:** verify on all four SAVED reports (no live run); the flagged set is stable and matches the
  measured genuine splits.

## Assumptions

- `origin_raw_indexes` is a faithful "same raw PDF block" signal (the audit confirmed both split halves share it).
- Ordering of `source_registry` follows `source_index`, so "adjacent" = consecutive by `source_index`.
