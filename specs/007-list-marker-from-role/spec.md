# Feature Specification: Delivered list/heading markers derive from source roles

Date: 2026-07-11
Status: NOT MERGED (2026-07-11). Shelved after verification proved impossible — see the closing note below.
The architecture debt is closed at increments C+B; this residual coupling is accepted and documented.
Owner surface: the delivery structural stage of `runtime_display_markdown`
Companion: `specs/001-heading-role-preservation/spec.md`, `specs/005-hygiene-pass-safety/spec.md`,
`specs/006-gate-on-delivered-markdown/spec.md`. The minimal, contained form of increment A (the full
"rebuild the emitter from entries" is deferred — the audit + role-coverage measurement showed no current
delivered-document defect justifies that risk; this removes the fragile coupling instead).
Changelog:
- 2026-07-11 — Created after the role-coverage measurement: 140 of Money's list entries carry `list_kind` but
  their text uses a `•` glyph, and they render as correct Word lists ONLY because the residual-bullet HYGIENE
  pass converts `•`→`- `. Delivered list structure therefore depends on a text-cleanup pass, not on the source
  role. This removes that coupling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - List structure comes from the source role, not a glyph fixup (Priority: P1)

A source-declared list item is rendered as a list in the delivered DOCX because the assembly knows its
`list_kind`, not because a hygiene pass happened to convert a `•` glyph. If the glyph-conversion were removed,
the list would still render as a list.

**Why this priority:** the delivered document is correct today, but its list structure hangs on a fragile
coupling: 140 of Money's list items (and the equivalent in every book) depend on
`normalize_residual_bullet_glyphs_markdown` turning `•` into `- `. A glyph variant outside that pattern, or a
change to that pass, would silently flatten real lists. Structure must derive from the role.

**Independent Test:** for a delivered markdown built from an entry with `list_kind` whose text starts with `•`,
the line carries a `- ` marker produced by the role-enforcement step — verifiable independently of the
residual-bullet pass.

**Acceptance Scenarios:**

1. **Given** an entry with `list_kind ∈ {unordered, list}` whose text is `• Пункт`, **When** the delivery
   markdown is built, **Then** the line is `- Пункт`, produced from the role.
2. **Given** an entry with `list_kind = ordered` whose text already carries `N.`, **When** the delivery markdown
   is built, **Then** the ordinal marker is preserved (not doubled, not converted to `-`).
3. **Given** an entry with `heading_level = N` whose text lost its `#` marker, **When** the delivery markdown is
   built, **Then** it is LEFT to the existing passes (heading enforcement dropped — see FR-004).
4. **Given** a body glyph inside a word (`4●5`) or a role-less line, **When** the step runs, **Then** it is
   untouched (marker enforcement keys on the entry role, not the glyph).

### Edge Cases

- A line whose entry cannot be resolved (no alignment) — leave it to the existing passes (degrade-safe).
- The fallback path (no assembly entries) — behaviour unchanged.
- An entry with `list_kind` whose text has NO leading glyph and NO marker — enforce `- ` (unordered) from the
  role; do not fabricate an ordinal.

## Verified findings

Verified 2026-07-11 by instrumented Money run (`20260711T_money_hole`). Reverted after measuring.

- **140 list entries carry `list_kind` but their text uses `•`, not a markdown marker.** They render as correct
  Word lists (0 raw glyphs in the delivered DOCX; 212 `Normal`+`numPr` list paragraphs) ONLY because
  `normalize_residual_bullet_glyphs_markdown` (`output_validation.py:1862`) converts a leading `•` to `- `. So the
  delivered list structure depends on a HYGIENE pass, not on `list_kind`.
- **1 heading entry has `heading_level` but no `#` marker** ("A: Основы… B: Изменение климата" — a merged
  appendix tail). It renders as body today. Low-impact, accepted tail — enforcing `#` on it is correct but not
  the motivation.
- **The delivered output does not change.** The glyph-conversion already yields `- ` for all 140 (0 raw bullets
  remain). Deriving the same `- ` from `list_kind` produces byte-identical delivered structure; only the
  provenance moves from the glyph to the role.
- **Entries carry the role; the delivery normalizer does not receive them.**
  `_normalize_final_markdown_for_runtime_display` (`late_phases.py:153`) gets only the reduced
  `generated_paragraph_registry` (text/paragraph_id, no `list_kind`). The full `FinalAssemblyEntry` sequence
  (`assembly_result.entries`, carrying `list_kind`/`heading_level`) is available at the call sites (`:4079` etc.).
- **Alignment is valid only on `final_markdown`.** `_build_source_backed_entry_by_markdown_line`
  (`late_phases.py:1818`) maps non-empty markdown lines to entries by ordinal; the later passes add/remove lines,
  so marker enforcement MUST run FIRST, before the structural/hygiene passes.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): the marker derives from the source-declared `list_kind`/`heading_level`, never from
> the glyph or text shape. Role-less lines are left to the existing passes.

- **FR-001**: The delivery chain gains a FIRST step that enforces structural markers from entry roles, using the
  `final_markdown`→entry alignment (valid before other passes run).
- **FR-002**: For a line whose entry has `list_kind ∈ {unordered, list}`: ensure a `- ` marker. If the text opens
  with a bullet glyph (`•◦‣●`), replace it with `- `; if it has no marker, prepend `- `.
- **FR-003**: For a line whose entry has `list_kind = ordered`: preserve an existing `N.`/`N)` ordinal; do not
  convert it to `-` and do not double it. If it has none, leave it (do not fabricate an ordinal).
- **FR-004 (DROPPED — scope narrowed 2026-07-11):** heading-marker enforcement is NOT done. The one measured
  heading-hole is a merged ambiguous appendix tail; forcing `#` on it would change the delivered document without
  a measured benefit, and no cross-book measurement justifies it (Constitution VII — no source signal, no
  repair). List-only keeps the delivered output byte-identical. Heading enforcement is a separate measured
  decision.
- **FR-005**: Lines with no resolvable entry, or role-less entries, are UNTOUCHED by this step (the existing
  passes still handle them). The fallback path (no entries) is unchanged.
- **FR-006**: The delivered DOCX structure MUST be byte-identical to today's on all four books (this removes a
  coupling, it does not change output). The `assembly_entries` are threaded into the delivery normalizer.

### Key Entities

- **FinalAssemblyEntry** — carries `list_kind`, `heading_level`, `text`, `used_fallback`, ordered.
- **Marker-enforcement step** — a role-keyed transform over the entry-aligned `final_markdown`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four books, the delivered DOCX has the same list/heading paragraph structure as before this
  change (same count of list paragraphs, same headings) — byte-identical structure.
- **SC-002**: With the residual-bullet glyph pass hypothetically disabled (a unit test), a `list_kind` entry with
  `•` text STILL renders `- ` — proving structure now derives from the role, not the glyph.
- **SC-003**: The gate metrics and acceptance verdict are unchanged on all four books (this is delivery-path only;
  `final_markdown` gate input is not modified).
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not rebuilding the emitter from entries** (full increment A) — deferred; no current defect justifies the risk.
- **Not modifying `final_markdown` / the gate input.** This step runs inside the DELIVERY normalizer only, so the
  gate baseline and mapping are untouched.
- **Not removing the residual-bullet / structural passes** — they still handle role-less lines and body glyphs.
- **Not changing thresholds or detectors.**
- A role-less list-looking line with no source `list_kind` is left to the existing passes (Constitution VII — no
  source signal, no role-based enforcement).

## Anti-regression

- **Byte-identical delivered structure:** a 4-book check comparing delivered list/heading paragraph structure
  before/after — MUST match.
- **Ordered lists not corrupted:** a `list_kind=ordered` entry with `N.` keeps its ordinal (not `-`, not doubled).
- **Body glyph untouched:** `4●5` in a body entry is not marker-enforced (FR-004/005 key on role, and body has
  none) — reuses the 005 guard direction.
- **Gate unchanged:** `final_markdown`, `raw_*`, and the acceptance verdict are identical (delivery-only).
- **Degrade-safe:** no assembly entries → behaviour unchanged.
- **Provenance test (SC-002):** the marker is produced by the role step, independently verifiable from the glyph
  pass.

## Assumptions

- `assembly_result.entries` is aligned to non-empty `final_markdown` lines by ordinal (the existing
  `_build_source_backed_entry_by_markdown_line` relies on this).
- Enforcing markers before the other passes preserves today's output because the residual-bullet pass already
  produced the same `- ` downstream (measured: 0 raw bullets in the delivered DOCX).

## Closing note — why this was shelved (2026-07-11)

Verification on a live run proved impossible, and without it the change cannot be merged (Constitution VIII —
verify against the delivered artifact).

- **The translation is non-deterministic.** Two Money runs (`20260711T_money_hole` vs `..._marker`) differ by
  1716 added / 1719 removed markdown lines — all Russian translation variants (e.g. «Денежная и банковская» →
  «Денежно-кредитная и банковская»). The delivered list-paragraph count moved 212→275, but that difference is
  dominated by translation variance, not by this change. So the delivered-document effect of the change cannot be
  measured from live runs.
- **No clean valuable form exists.** Restricting to the glyph→`- ` case is byte-identical to the residual-bullet
  pass that stays — no visible effect, and even byte-identity is not guaranteed because enforcement runs before
  the structural passes, which may behave differently on `-` vs `•`. The value-adding case (a `list_kind` line
  with no marker becoming a `- ` list) IS a real delivered-document change, but its correctness cannot be
  confirmed against the artifact due to the non-determinism above.
- **No current defect motivates it.** The earlier role-coverage measurement showed the delivered document is
  already structurally correct (0 raw bullet glyphs in the delivered DOCX; lists render as `Normal`+`numPr`).

Decision: the two-markdown architecture debt is closed at increments C (`005`, hygiene passes made
non-destructive) and B (`006`, gate measures the delivered markdown). The residual coupling — delivered list
structure produced by the residual-bullet glyph fixup rather than by `list_kind` — is a real but latent
architectural smell with no current defect; it is ACCEPTED and documented here. The unit tests prove the
`enforce_structural_markers_from_entries` helper is correct in isolation, but the branch is NOT merged because
its end-to-end effect on the delivered artifact cannot be verified. Revisit only if a deterministic
translation-replay harness exists, or if a future glyph-pass change actually breaks role-backed lists.
