# Feature Specification: Strip source section-break (sectPr) from restored TOC paragraph properties

Date: 2026-07-14
Status: **IMPLEMENTED (2026-07-14).** Narrow, proven bug fix. Verified against the real delivered artifact.
Owner surface: `generation/formatting_transfer.py` — `_sanitize_toc_paragraph_properties_xml` (the TOC-property
restore sanitizer) + `_replace_paragraph_properties_from_xml` (the single pPr graft point).
Companion: the binding minimal-formatting contract (memory `formatting-transfer-contract`: keep structure+emphasis,
DROP geometry). Supersedes the mis-aimed table work: `specs/019` (CLOSED) and `specs/020` (real but unrelated to
this symptom — the delivered DOCX has `w:tbl=0`).
Changelog:
- 2026-07-14 — Created after the director's real translated output of `RESISTANCE…UKRAINE.docx` showed front-matter
  text in NARROW TWO COLUMNS. Two prior diagnoses (tables 019/020) were WRONG — proven by inspecting the REAL
  delivered DOCX `.run/ui_results/20260714_162136_…result.docx`: `w:tbl=0` but **4 `<w:cols w:num="2">` page
  SECTIONS**. Root cause traced + fixed here.

## Root cause (Constitution VIII — proven against the real artifact 2026-07-14)

FineReader-scanned two-column sources store a continuous 2-column section break INSIDE paragraphs
(`<w:pPr>…<w:sectPr><w:cols w:num="2"/></w:sectPr></w:pPr>`; RESISTANCE source has 129 such sections). Extraction
stores each paragraph's ENTIRE pPr XML — including the child `sectPr` — into
`ParagraphUnit.paragraph_properties_xml` (`extraction.py:829-833`). Four of those section-break paragraphs are
tagged `toc_entry`, so `_restore_toc_paragraph_properties_for_mapped_pairs` (`formatting_transfer.py:3233`) copies
their source pPr onto the mapped target TOC paragraph. The restore sanitizer
`_sanitize_toc_paragraph_properties_xml` stripped `{ind, tabs, spacing, jc, pStyle}` but **not `sectPr`**
(`formatting_transfer.py:3225`), so the 2-column section break survived and grafted a narrow 2-column section into
the delivered DOCX.

**Exact-match proof:** the 4 delivered sections have column-spacing `1523, 1523, 1514, 1514`; the 4 RESISTANCE
source paragraphs tagged toc_entry that carry a 2-column `sectPr` are `p1035, p1036, p1049, p1050` with column-spacing
`1523, 1523, 1514, 1514` — an exact match. Both the base render and the reader-cleanup rebuild converge on the same
`preserve_source_paragraph_properties` call (`_rebuild_docx_for_markdown`, `late_phases.py:259` / `:1402`), so both
paths inject identically. The markdown/`.result.md` contains zero `sectPr` — Pandoc/the reference-doc are single-column.

## Scope (implemented)

1. Add `"sectPr"` to `unsafe_geometry_names` in `_sanitize_toc_paragraph_properties_xml` — the TOC restore no longer
   copies a section break. `sectPr` is page geometry (size/margins/columns), which the minimal-formatting contract
   drops.
2. Defensive: `_replace_paragraph_properties_from_xml` (the single graft point) strips any `sectPr` child before
   inserting, so no current or future pPr-copy caller can leak a section into a paragraph's pPr.

## Non-goals

- Do NOT change what content/emphasis/images are restored — only the geometry `sectPr` is dropped from copied pPr.
- Do NOT fix the upstream misclassification of those 4 body-prose paragraphs as `toc_entry` — a separate
  structure-classification issue; the geometry strip neutralizes the delivered symptom regardless of the mistag.
- The document's own single body-final `sectPr` (from Pandoc/the reference-doc) is untouched (it is single-column).

## Anti-regression (verified)

- **Real-data proof:** the 4 RESISTANCE injectors (`p1035/36/49/50`, col-space 1523/1523/1514/1514) now yield NO
  `sectPr` after sanitize (0/0); the defensive graft leaves no `sectPr`.
- **Regression test:** `tests/test_format_restoration.py::test_formatting_contract_strips_source_two_column_section_break_from_toc_paragraph`
  — a TOC source paragraph with a 2-column `sectPr` restores to a target with no `sectPr` and no `w:num="2"` anywhere.
- Full `test_format_restoration.py` green (99 passed); pyright delta 0 (the file's 78 errors are pre-existing).
- Content/emphasis restore behavior unchanged (existing geometry-strip + font tests still pass).

## Verification

- `wsl … python -m pytest tests/test_format_restoration.py -q` → 99 passed; `-k two_column_section` → passes.
- Real-data check: extract RESISTANCE, confirm exactly 4 toc-tagged sectPr injectors, all stripped by the sanitizer.
- Eyes-on (director): restart the app (`restart-project.ps1`), re-run RESISTANCE, confirm the front-matter is a
  single-column flow (no narrow two-column blocks).
