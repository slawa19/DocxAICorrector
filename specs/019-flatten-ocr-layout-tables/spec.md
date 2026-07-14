# Feature Specification: Flatten OCR layout-tables into linear paragraph flow (drop scan geometry)

Date: 2026-07-14
Status: **CLOSED — NOT NEEDED (2026-07-14).** Diagnosis reversed during implementation. The render path already
drops ALL table structure to single-column text (Pandoc `format="markdown+raw_html+superscript+subscript"`,
`generation/_generation.py:1145`, drops `<table>/<tr>/<td>` → cell text becomes ordinary `<w:p>`; the fresh
single-column `_build_reference_docx` means source `w:cols` never carry over). Verified (orchestrator, no-LLM
reproduction of the real render on the current source): `fulldoc_current.docx` has `w:tbl=0`, single `w:cols`, no
`w:num≥2` — a clean single-column, table-free DOCX. The narrow two-column screenshot is **structurally impossible**
from this render path and did NOT reproduce (the source was rewritten 2026-07-14 11:14, after the screenshot; the
failed run's output was never persisted). A LAYOUT-vs-DATA table classifier therefore has no effect on the
delivered DOCX. NOT IMPLEMENTED; kept as lineage. Original (superseded) intent below.
Owner surface: the DOCX table extraction (`document/extraction.py` `_build_raw_table` / the `role="table"` block)
and the table renderer (`document/tables.py` `render_table_html` / `build_raw_table`).
Companion: `specs/017-ocr-stamp-furniture-detection/spec.md` (sibling OCR-import defect — that one is garbage
TOKENS, this one is garbage GEOMETRY); the binding minimal-formatting contract (memory `formatting-transfer-contract`).
Changelog:
- 2026-07-14 — Created after a director eyes-on the final DOCX of `RESISTANCE FACTORS … UKRAINE.docx` (OCR→DOCX of
  a scanned two-column CIA document) showed text squeezed into narrow two-column tables wrapping character-by-
  character. Root cause (orchestrator-verified): the source encodes its scanned page layout as tables (3 `w:tbl`,
  144 `w:tr`) + 129 multi-column sections; the pipeline preserves all tables (`extraction.py:604-606` role="table"
  → `render_table_html` `<table>` HTML → Pandoc renders a Word table with "Table Grid"). The `w:cols` sections do
  NOT reach the output (assembly is single-column), so the tables alone produce the narrow-column output. Preserving
  scan-LAYOUT tables violates the minimal-formatting contract (geometry must be dropped).

## Verified findings (Constitution VIII — verified 2026-07-14)

- Source `RESISTANCE…docx`: `w:tbl`=3, `w:tr`=144, multi-col sections (`w:cols w:num>=2`)=129 — a scanned
  two-column page reconstructed by OCR as tables + column sections.
- Table path: `document/extraction.py` builds `RawTable` and emits `role="table"` / `structural_role="table"`
  paragraphs (`:532` `_build_raw_table`, `:604-606`); `document/tables.py::render_table_html` (`:26`) serializes to
  `<table>` with `<th>` when `has_header = len(rows)>1 and all(cell.strip() for cell in rows[0])` (`:47`), cells as
  `<td>` with `<br/>`-joined prose (`:65-76`); the raw `<table>` HTML rides through the content stream and Pandoc
  (`markdown+raw_html`, "Table Grid" style `_generation.py:1272`) renders it as a Word table in the output.
- The output assembly carries NO `w:cols`/section geometry (grep empty) — Pandoc output is single-column — so the
  narrow columns come solely from the transferred tables, NOT from the source column sections.
- `role=="table"` paragraphs are already excluded from some coverage accounting (`formatting_transfer.py:2826,2909`);
  flattening changes their role to body, which must remain consistent with that accounting.

## Scope

1. **Classify each extracted table as LAYOUT vs DATA — by FORM, universally (Constitution VII, no per-book literals):**
   - **LAYOUT (flatten):** cells dominated by PROSE — long / sentence-like / multi-line (`<br/>`) text — with no
     short-label header row (row 0 is not a set of short distinct labels), typically few columns (a page-column
     reconstruction). Keyed on cell text FORM (length / sentence-ness / header-ness), never on document content.
   - **DATA (keep):** a header row of short non-empty labels and/or short/numeric cell values — a real tabular
     structure. Rendered unchanged as `<table>`.
2. **Flatten layout tables** into sequential body paragraphs in natural document reading order (cells in order),
   preserving each cell's text + inline emphasis, dropping the table geometry. The flattened paragraphs enter the
   normal content stream as `role="body"` so they translate and render as linear prose (single column). Empty
   cells are skipped; a cell's internal `<br/>` line-breaks become paragraph/line boundaries.
3. **Keep genuine data tables** exactly as today (`role="table"` → `<table>` → Pandoc table).

## Non-goals

- Do NOT touch the source `w:cols` multi-column sections — they do not reach the output.
- Do NOT attempt perfect two-column page reading-order reconstruction (column-major vs row-major). The affected
  content is low-value OCR front-matter/TOC; the win is dropping the narrow-table GEOMETRY so text flows. Cells are
  flattened in document order; downstream structure/merge passes handle further merging.
- Do NOT fix OCR token garbage (SECRET/50X1-HUM stamps) — that is `specs/017`.
- No per-book literals; no reliance on "input came from OCR" as the trigger — the rule is table-FORM only.

## Anti-regression

- **Genuine data tables are PRESERVED (anti-vacuum counter-proof):** a synthetic small table with a short-label
  header row + short/numeric cells is classified DATA and still renders as a `<table>`. This is the mandatory
  counter-proof that the flatten rule does not eat real tables.
- **No data loss on flatten:** every non-empty cell's text appears in the flattened paragraph stream (a
  text-conservation assertion over the RESISTANCE tables — all cell text present after flattening).
- On `RESISTANCE…docx`: the 3 tables classify LAYOUT and flatten — the output no longer contains `<table>` markup
  for them; their text becomes body paragraphs. Images and other content unaffected (69/86 images intact).
- Coverage/accounting that special-cases `role=="table"` (`formatting_transfer.py:2826,2909`) stays consistent —
  flattened paragraphs are `role="body"` and counted like any body prose; no vacuous credit introduced.
- Full suite green; pyright delta 0; no change to the DATA-table render path.

## Verification (Constitution I/II/VIII)

- Offline no-LLM: run `extract_document_content_from_docx` (or the prep entry) on `RESISTANCE…docx`; assert the 3
  tables are classified LAYOUT and produce body paragraphs (no `role="table"` for them / no `<table>` in the
  assembled content for them), and that all their cell text is present (conservation).
- Synthetic DATA table (header + short cells) → classified DATA → still a `<table>` (counter-proof).
- `wsl.exe … bash scripts/test.sh` — full suite green (measure typecheck on a CLEAN checkout: baseline 244).
- pyright delta 0.
- Eyes-on (optional): re-run the document and confirm the narrow two-column blocks are gone (readable single flow).

## Rollout

Implement via the delivery loop on a branch off `main`; orchestrator verifies (offline RESISTANCE flatten +
conservation, the DATA-table counter-proof, full `scripts/test.sh`, pyright delta 0) before merge.
