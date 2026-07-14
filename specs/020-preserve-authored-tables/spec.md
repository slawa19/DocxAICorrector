# Feature Specification: Preserve authored tables; flatten only scan-origin (OCR) tables

Date: 2026-07-14
Status: DRAFT — approved scope, pre-implementation. Two-part import/render fix: (1) make genuine tables SURVIVE the
render into the output DOCX (they are currently dropped for every input), and (2) flatten tables to linear text ONLY
for scan-origin (OCR) documents, so authored data tables are kept (canon: keep STRUCTURE) while scanned column-layout
"tables" are dropped (canon: drop GEOMETRY).
Owner surface: the table renderer (`document/tables.py` `render_table_html`/`build_raw_table`), the markdown→DOCX
render (`generation/_generation.py` `convert_markdown_to_docx_bytes` ~:1118, Pandoc call ~:1145), and a new
document-level scan-origin classifier (likely `document/extraction.py` / a small provenance helper).
Companion: `specs/019-flatten-ocr-layout-tables/spec.md` (CLOSED — superseded by this; 019 assumed the render kept
tables, it does not); the binding minimal-formatting contract (memory `formatting-transfer-contract`); the
GLOBAL_PLAN typography-scope decision ("DOCX input preserves tables natively" — that intent was never actually
delivered because the render drops them).
Changelog:
- 2026-07-14 — Created after the director noted that flattening a well-formatted table from a CLEAN DOCX is wrong.
  Orchestrator-verified: the render (`Pandoc format="markdown+raw_html+…"`) drops ALL `<table>` structure to text
  for every input, so **authored data tables are already being lost** — e.g. `Mazzucato (clean, authored)` has 3
  legitimate tables that never reach the output DOCX. Meanwhile `RESISTANCE (OCR scan)` has 3 tables + **129
  multi-column sections + 86 images** (scanned two-column pages). The right discriminator is document-level
  PROVENANCE (scan vs authored), not per-table form.

## Verified findings (Constitution VIII — verified 2026-07-14)

- Render drops tables: Pandoc `format="markdown+raw_html+superscript+subscript"` (`_generation.py:1145`) turns
  `<table>/<tr>/<td>` into dropped `RawBlock`, keeping only cell text as `<w:p>`. Reproduced: real render of the
  current sources → output `w:tbl=0`, single `w:cols` (from the fresh single-column `_build_reference_docx`).
  Cross-checked persisted outputs (mazzucato, rethinking-money): `w:tbl=0`. So NO table survives, for ANY input.
- Provenance signals (measured on the source `word/document.xml`):
  | Source | tables | `w:cols num≥2` | media (images) |
  | --- | --- | --- | --- |
  | RESISTANCE (OCR scan) | 3 | **129** | **86** |
  | Mazzucato (clean, authored) | 3 | **0** | 0 |
  | Lietaer (clean, authored) | 0 | 2 | 0 |
  Multi-column-section density (`w:cols num≥2`) cleanly separates scan (129) from authored (0–2). It is structural
  (not content, not per-book — Constitution VII) and survives a re-save in Word (RESISTANCE was re-saved; the 129
  sections remained). Table borders are useless here (0 on all). App metadata is unreliable (re-save overwrote it).
- Table emission: `document/tables.py::render_table_html` (~:26) emits raw `<table>` HTML (the form the render
  drops); the pipe-table/grid-table markdown form WOULD survive Pandoc's markdown reader.

## Scope

### Part 1 — Make genuine tables survive the render (fix the latent defect)
When a table is to be KEPT (see Part 2), emit it as a **Pandoc-markdown table** (pipe table for simple short-cell
tables; grid table when cells need multi-line/block content) instead of raw `<table>` HTML, so it renders as a real
Word `w:tbl` in the output. Keep it minimal-formatting: a plain bordered/gridded table, no source column widths /
colors / fonts (drop geometry, keep the tabular STRUCTURE + cell text + inline emphasis). The DATA-table render is
the ONLY behavioral change for clean documents.

### Part 2 — Flatten tables only for scan-origin documents
Add a document-level **scan-origin** classifier keyed on structural provenance (universal, no per-book literals, no
content match):
- **Primary signal:** multi-column-section density — count `w:cols` sections with `w:num≥2`; a document with many
  (well above authored norms; RESISTANCE=129 vs authored 0–2) is scan-origin. Use an absolute + ratio threshold
  pinned by the counter-proofs (must classify RESISTANCE=scan, Mazzucato/Lietaer=authored).
- **Optional supporting signal:** high image-per-page / full-page-image density.
When the document is **scan-origin**, FLATTEN all its tables into linear body paragraphs (cells in reading order,
`<br/>`→line boundaries, empty cells skipped), preserving text + emphasis — the same flatten behavior 019 designed.
When the document is **authored**, KEEP tables (Part 1 emits them as real tables). (Optional, later: even in an
authored doc, a per-table prose-column form check could flatten a stray layout table — NON-GOAL for this pass;
default authored = keep.)

## Non-goals

- No per-book literals; scan-origin is decided by structural provenance (multi-column density / images), never by
  document text or filename.
- Do NOT preserve source table GEOMETRY (column widths, colors, borders styling, fonts) — keep only the tabular
  structure + cell text + emphasis (minimal-formatting canon).
- Do NOT fix OCR text garbage inside cells (SECRET/50X1-HUM, dot-leaders) — that is `specs/017`.
- Do NOT attempt per-table LAYOUT-vs-DATA classification inside authored docs in this pass (default authored=keep).
- Do NOT change emphasis/image/heading handling.

## Anti-regression

- **Authored tables PRESERVED (the fix, counter-proof):** rendering `Mazzucato` (clean) yields an output DOCX with
  `w:tbl > 0` — its 3 authored tables appear as real Word tables (they are lost today). REQUIRED test.
- **Scan tables FLATTENED (counter-proof + conservation):** `RESISTANCE` (scan-origin) yields output `w:tbl=0`; all
  its table cell text is present in the flattened body stream (no data loss). REQUIRED test.
- **Scan-origin classifier counter-proofs:** RESISTANCE → scan; Mazzucato & Lietaer → authored (pinned by the
  measured 129 vs 0–2). A synthetic authored doc with a couple of column sections stays authored (anti-vacuum:
  don't over-trigger scan-origin on a normal 2-column magazine layout — bias to authored; document the accepted
  tail).
- **Prose books unchanged:** Lietaer (no tables) output is byte-comparable to before (no tables introduced/removed).
- Coverage/quality-gate accounting that special-cases `role=="table"` stays consistent (kept tables remain
  role=table; flattened become role=body) — no vacuous credit, no gate regressions.
- Full suite green (typecheck measured on a CLEAN checkout, baseline 244); pyright delta 0.

## Verification (Constitution I/II/VIII)

- Offline no-LLM renders: `Mazzucato` source → output `w:tbl≥3` (authored tables survive); `RESISTANCE` source →
  output `w:tbl=0` + table-text conserved; `Lietaer` → unchanged.
- Scan-origin classifier unit tests over the three sources' provenance signals (129/0/2) + a synthetic authored
  two-column doc (stays authored).
- `wsl.exe … bash scripts/test.sh` full suite green; pyright delta 0.
- Eyes-on (optional): re-run a clean DOCX with a real table and confirm the output shows a proper table; re-run
  RESISTANCE and confirm single-column flow (no narrow-column tables).

## Rollout

Implement via the delivery loop on a branch off `main`; orchestrator verifies (Mazzucato-preserve + RESISTANCE-flatten
+ conservation counter-proofs, scan-origin classifier tests, full `scripts/test.sh`, pyright delta 0) before merge.
Given Part 1 changes table rendering for all inputs, run the corpus renders (offline) as part of verification.
