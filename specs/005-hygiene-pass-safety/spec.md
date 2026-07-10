# Feature Specification: Make the delivery hygiene passes non-destructive

Date: 2026-07-10
Status: Implemented (2026-07-10). Money live: no corruption, counts stable, passes. Guard is monotonic-safe.
Owner surface: the display-hygiene passes that build the delivered DOCX (`runtime_display_markdown`)
Companion: `specs/001-heading-role-preservation/spec.md`, `specs/003-list-fragment-detector/spec.md`;
`docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md`. First increment of the two-markdown
convergence (increment C of the architecture audit; increments B "gate on delivered markdown" and A "build DOCX
from entries" follow separately).
Changelog:
- 2026-07-10 — Created from the two-markdown architecture audit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The delivered document is not corrupted by cleanup (Priority: P1)

The DOCX the user receives is built by running text-cleanup passes over the assembled markdown. Those passes must
repair OCR/model artifacts WITHOUT damaging real content: they must not delete a glyph that is part of a word,
invent a list item from a sentence, or rewrite the letters of a URL or a code token.

**Why this priority:** these passes run on the delivered artifact with no gate visibility (the gate reads a
different markdown). A silent data corruption in the user's document is worse than a formatting nit.

**Independent Test:** feed each pass a body string containing an inline glyph / a code token / a URL; the content
survives unchanged.

**Acceptance Scenarios:**

1. **Given** body text `4●5` (a glyph between two alphanumerics), **When** the residual-bullet pass runs,
   **Then** it is left as `4●5` — the glyph is data, not a bullet.
2. **Given** a real leading bullet `● Первый пункт`, **When** the pass runs, **Then** it still becomes `- Первый
   пункт` (the legitimate repair is preserved).
3. **Given** an inline code token or URL containing mixed Latin/Cyrillic look-alikes, **When** the mixed-script
   pass runs, **Then** it is left unchanged; a genuine prose homoglyph word (`Cовет`) is still normalized.

### Edge Cases

- A glyph at line start in a NON-list context (a sentence that happens to open with `●`).
- A fenced code block spanning multiple lines.
- A token that is both a homoglyph candidate and inside backticks.
- A page-placeholder concat pass over a line that is legitimate body text.

## Verified findings

Verified 2026-07-10 by reading the passes. Live confirmation is a success criterion (Constitution VIII).

- **The residual-bullet pass deletes a glyph anywhere in a line.** `normalize_residual_bullet_glyphs_markdown`
  (`src/docxaicorrector/pipeline/output_validation.py:1850`) ends with
  `re.sub(r"\s*[●•◦‣]\s*", " ", updated)` (`:1865`), which turns `4●5` into `4 5`. Its first sub
  `re.sub(r"^(\s*)[●•◦‣]\s+", r"\1- ", updated)` (`:1862`) can also invent a `- ` list item from a body line that
  merely opens with a glyph.
- **The mixed-script pass rewrites any mixed token, everywhere.** `normalize_mixed_script_markdown` (`:1940`)
  applies `_HOMOGLYPH_TABLE` to every token matching `_CYRILLIC_LATIN_MIXED_TOKEN_PATTERN` (`:40`) across all
  text, with no exemption for inline code, fenced blocks, or URL/email tokens. A deliberately-Latin identifier or
  a URL with a look-alike letter is silently corrupted.
- **These passes are source-blind and build the delivered DOCX.** They run inside
  `_normalize_final_markdown_for_runtime_display` (`late_phases.py:153`), whose output is fed to
  `convert_markdown_to_docx_bytes` (`late_phases.py:4107`). The gate reads a different markdown, so this
  corruption is invisible to acceptance.
- **The detectors must stay consistent with the passes.** `collect_residual_bullet_glyph_samples` (`:1949`) and
  `collect_mixed_script_samples` (`:2000`) report what the passes would repair; a case a pass now leaves alone
  must not be reported as an unrepaired defect.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): the guards key on textual STRUCTURE (glyph flanked by word characters; code/URL
> span), not on per-book literals. No word lists. A genuine repair is preserved; only the destructive over-reach
> is removed.

- **FR-001**: `normalize_residual_bullet_glyphs_markdown` MUST NOT alter a glyph flanked on both sides by
  alphanumeric characters (`\w[●•◦‣]\w` — e.g. `4●5`, `a◦b`).
- **FR-002**: The leading-glyph→`- ` conversion MUST fire only for a plausible list item: glyph at line start
  followed by whitespace and content, not a mid-sentence or numbered-continuation line.
- **FR-003**: `normalize_mixed_script_markdown` MUST NOT rewrite tokens inside inline code spans (`` `…` ``),
  fenced code blocks (```` ``` ````), or URL/email-like tokens (containing `://`, `www.`, `@`, or a domain dot).
- **FR-004**: `normalize_page_placeholder_heading_concats_markdown` MUST leave a line unchanged when the matched
  region is legitimate body text (no over-split). Audit and guard if the same over-reach class exists.
- **FR-005**: The detectors `collect_residual_bullet_glyph_samples` and `collect_mixed_script_samples` MUST be
  reconciled with the guarded passes: a case the pass now leaves unchanged is NOT reported as an unrepaired
  defect (no phantom review items).
- **FR-006 (no behaviour drift)**: Cases the passes correctly repair today — a genuine leading bullet, a genuine
  homoglyph prose word — MUST still be repaired.

### Key Entities

- **Hygiene pass** — a pure `str → str` markdown transform in the delivery chain.
- **Protected content** — a glyph inside a word; a code span; a URL/email token.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On all four books, the delivered `runtime_display_markdown` contains zero `\w[●•◦‣]\w`-class
  corruptions (a glyph that was between two word characters replaced by a space) — verified by diffing the
  markdown before and after the residual-bullet pass on a live run.
- **SC-002**: On all four books, zero code/URL tokens are altered by the mixed-script pass (diff code/URL tokens
  before/after; count MUST be 0).
- **SC-003**: `residual_bullet_glyph_count` and `mixed_script_term_count` in the produced report do not rise (the
  guards remove wrong repairs, they do not create new residue).
- **SC-004**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not converging the two markdowns yet.** This increment only stops the delivery passes from corrupting
  content. Gating on the delivered markdown (increment B) and building the DOCX from entries (increment A) are
  separate specs.
- **Not touching the structural passes** `normalize_false_fragment_headings_markdown` /
  `normalize_list_fragment_regressions_markdown` — already source-aware (specs 001/003).
- **Not changing thresholds, detectors' gating, or the report structure.**
- A mixed-script token that is genuinely ambiguous (prose vs identifier, no code/URL marker) is left to the
  existing homoglyph behaviour — not guessed further (Constitution VII).

## Anti-regression

- **`4●5` / `12•34` / `a◦b` MUST survive unchanged** — guards the `:1865` catch-all sub.
- **`● Первый пункт` and `текст; ● пункт` MUST still normalize** to `- Первый пункт` / clean separators (FR-006).
- **An inline code span / fenced block / URL MUST pass mixed-script unchanged**; a prose `Cовет` MUST still become
  `Совет` (FR-006).
- **A body line opening with a glyph in a non-list context MUST NOT become a list item** (FR-002).
- **Detector/pass consistency:** `collect_residual_bullet_glyph_samples("4●5")` returns empty (FR-005).
- **Verify on all four books by reading the delivered markdown** (Constitution VIII), and capture entry
  role-coverage numbers (`entries_with_role/heading_level/list_kind`, `used_fallback` count) in the same run — a
  prerequisite measurement for later increment A.

## Assumptions

- The three passes are pure `str → str` functions with the callers in `late_phases.py` (`:137-150`); guarding
  them changes only their output, not the chain.
- Code/URL detection by span markers (backticks, fences) and token shape (`://`, `www.`, `@`, domain dot) is
  sufficient; the passes need not parse full markdown.
