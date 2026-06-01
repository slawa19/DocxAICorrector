# PDF Text-Layer Source Import Pivot Spec

Date: 2026-06-01

## Goal

Reduce reader-cleanup and formatting-restoration effort by moving most PDF
cleanup before translation.

Current production path treats PDF as:

```text
PDF -> LibreOffice writer_pdf_import -> DOCX -> ParagraphUnit -> translation
```

This keeps the application inside the existing DOCX-centric pipeline, but it
also imports visual PDF layout as document structure. The result is expensive
post-translation cleanup: page furniture, repeated headers, page numbers,
heading/body fusion, fragmented paragraphs, and formatting lineage loss.

Target direction:

```text
text-layer PDF
  -> deterministic text-layer extraction
  -> page furniture removal
  -> logical paragraphs/headings/lists/captions
  -> ParagraphUnit
  -> existing translation pipeline
  -> minimal reader cleanup safety net
  -> DOCX formatting transfer
```

## Decision

Use a **permissive text-layer-first source importer** as the preferred direction
for text PDFs.

- Primary extraction candidates: `pdfminer.six` / `pdfplumber`.
- OCR fallback for scanned PDFs: `OCRmyPDF + Tesseract`, deferred to PR-PDF2.
- Do not use FineReader in production SaaS/public service.
- Do not make `PyMuPDF` the default dependency unless licensing is explicitly
  accepted or commercial licensing is chosen.
- Do not replace production PDF import until quality evidence proves the new
  importer is better on real book-like documents.

## Architecture Fit

The new importer should produce existing internal objects, not a second document
model:

```text
PDF spans/geometry/font signals
  -> PdfTextSpan / source-import diagnostics
  -> ParagraphUnit(role, heading_level, is_bold, is_italic, font_size_pt, ...)
  -> existing preparation and translation pipeline
```

Formatting signals should be preserved at source-import time where possible:

- font size -> heading/body/caption evidence;
- bold/italic flags -> `ParagraphUnit.is_bold` / `is_italic`;
- indentation and markers -> list evidence;
- repeated page-zone text -> page furniture diagnostics/removal;
- line geometry -> paragraph merge/split evidence.

Coordinate contract:

- Internal `PdfTextSpan.top` / `bottom` coordinates are top-origin.
- Extractors that return bottom-origin PDF coordinates, including pdfminer, must
  normalize through page height before page-zone or furniture decisions.
- A span with missing page height may still be scored with conservative
  absolute top/bottom thresholds, but it is only PR-PDF0 diagnostic evidence,
  not PR-PDF1 promotion evidence.

Production hook notes for PR-PDF1:

- Safest first hook is `processing_runtime.materialize_uploaded_payload()` for
  `fmt == "pdf"`, with a feature-flagged text-layer branch that preserves the
  existing downstream contract.
- The sync/eager path in `processing_runtime.normalize_uploaded_document()` must
  be mirrored, otherwise some PDF inputs will still use LibreOffice.
- If the first implementation still outputs generated DOCX bytes, keep
  `source_format="pdf"` and use a distinct `conversion_backend`, for example
  `pdf-text-layer`.
- If a later implementation builds `ParagraphUnit` directly, it must replace
  the DOCX validation/preparation boundary deliberately and include cache-key
  changes so LibreOffice and text-layer preparations do not share stale cache.

Architectural fork to keep visible:

- **Temporary safe proof path:** `PDF text-layer -> ParagraphUnit signals ->
  generated DOCX -> existing DOCX extractor/preparation`.
  This is what PR-PDF1a wires behind `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=1`.
  It proves source cleanup and preserves existing downstream contracts, but it
  necessarily serializes back through DOCX.
- **Target architecture after proof:** `PDF text-layer -> ParagraphUnit ->
  preparation` without generated DOCX as an intermediate. This should become
  the preferred architecture if PR-PDF1a proves quality, because it avoids a
  second format conversion and keeps source geometry/provenance richer.
- Do not confuse PR-PDF1a proof success with final architecture approval. The
  safe path is a working bridge, not the endpoint.

## PR Backlog

### PR-PDF0. Source Import Quality Gate

Status: implemented locally; real probe completed.

Purpose:

- Add benchmark-only/permissive quality metrics for text-layer PDF import.
- Compare current LibreOffice PDF import against deterministic text-layer
  extraction before changing production behavior.
- Produce evidence that answers: "Does text-layer source cleanup remove enough
  PDF noise to stop post-translation cleanup micro-tuning?"

Scope:

- Add a small text-layer quality analyzer that accepts extracted spans and
  reports:
  - visible text chars;
  - body text chars and body text ratio;
  - repeated page furniture chars and ratio;
  - page furniture candidates;
  - page number candidates;
  - heading candidates;
  - bold/italic signal availability;
  - body span count after deterministic furniture filtering.
- Keep optional PDF extraction dependency isolated. Missing PDF extraction
  libraries must report `unsupported`, not break production tests.
- Add focused unit tests for the metrics and page-furniture classification.

Non-goals:

- No production PDF import replacement.
- No UI changes.
- No OCR integration.
- No AI cleanup changes.
- No document-specific strings or regexes.

Exit:

- `PR-PDF0` module and tests exist.
- A next-session operator can run the quality gate on the user PDF or a frozen
  real-document PDF and compare it against current LibreOffice artifacts.

Canonical probe command:

```bash
bash scripts/run-pdf-text-layer-quality-probe.sh \
  --input-pdf tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf \
  --output .run/pdf_text_layer_quality/lietaer-chapter-region-pr-pdf0.json
```

If optional PDF dependencies are not installed, the command must write an
`unsupported` diagnostic instead of breaking production runtime.

Real probe evidence, 2026-06-01:

- PDF: `tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf`
- Report: `.run/pdf_text_layer_quality/lietaer-chapter-region-pr-pdf0.json`
- Result:
  - `status=ok`
  - `decision=promising`
  - `page_count=64`
  - `span_count=1902`
  - `visible_text_chars=95179`
  - `body_text_chars=94052`
  - `body_text_ratio=0.9882`
  - `repeated_page_furniture_text_chars=943`
  - `repeated_page_furniture_text_ratio=0.0099`
  - `page_number_span_count=61`
  - `heading_candidate_count=17`
  - `list_candidate_count=19`
  - `bold_span_count=1`
  - `italic_span_count=2`
  - `median_font_size=10.9669`
  - `largest_font_size=35.8915`

LibreOffice baseline evidence for the same profile:

- Completed run:
  `tests/artifacts/real_document_pipeline/runs/20260530T071434Z_968_Rethinking-money-chapter-region-pages-10-11-and-156-217/`
- Source cleanup evidence:
  - `preparation.paragraph_count=336`
  - `preparation.source_chars=114460`
  - `source_cleanup_evidence.cleaned_paragraph_count=336`
  - `source_cleanup_evidence.removed_paragraph_count=0`
  - `source_cleanup_evidence.flagged_page_number_count=1`
  - `source_cleanup_evidence.flagged_repeated_artifact_count=2`
- Output quick extraction:
  - DOCX nonempty paragraphs: `328`
  - MD blankline blocks: `326`
  - pure page-number-like lines: `1`
  - bullet lines: `10`
  - ordered-list lines: `15`

Interpretation:

- The PDF is not a scanned/empty case; it has a dense selectable text layer.
- Deterministic text-layer extraction sees far more page-zone page-number
  candidates than the current LibreOffice cleanup evidence flags (`61` vs `1`),
  while preserving almost all text as body (`body_text_ratio=0.9882`).
- PR-PDF1 is justified as the next implementation PR, but promotion must remain
  feature-flagged until it proves paragraph order, headings, lists, and final
  DOCX output against the LibreOffice baseline.

### PR-PDF1. Text-Layer PDF -> ParagraphUnit Importer

Status: completed locally as a feature-flagged generated-DOCX bridge; not
promoted as default and not final architecture.

Purpose:

- Implement the first production-capable text-layer importer for PDFs with
  selectable text.
- Build `ParagraphUnit` directly from deterministic paragraphs/headings/lists.
- Keep LibreOffice PDF import as fallback behind a config/feature flag until
  real-document proof is green.

Acceptance:

- Text-layer PDFs bypass `writer_pdf_import` only when enabled by explicit
  config/feature flag.
- Page furniture is removed or flagged before translation.
- Heading/list/body roles are source-backed and visible in diagnostics.
- Existing DOCX input path remains unchanged.
- Empty/scanned/unsupported text-layer PDFs fall back to the current LibreOffice
  path or explicit unsupported diagnostics; they must not produce an empty
  successful document.
- Cache keys include import backend/config so text-layer and LibreOffice
  preparations cannot reuse stale artifacts.

Suggested slice order:

1. Build deterministic grouping from `PdfTextSpan` into a neutral source-import
   representation with roles/signals, without touching UI defaults.
   - Local implementation: `src/docxaicorrector/pdf_import/logical_import.py`
   - Current behavior: removes repeated page furniture/page-number spans,
     merges adjacent body spans, emits standard `ParagraphUnit` with
     `layout_origin="pdf_text_layer"`, heading/list/bold/italic/font-size
     evidence, and identity/provenance fields.
2. Add a feature-flagged PDF materialization path that produces an
   extractor-compatible payload or a deliberate `ParagraphUnit` preparation path.
   - Local PR-PDF1a implementation:
     `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=1` makes PDF materialization try the
     text-layer generated-DOCX bridge first.
   - If the text-layer path is unsupported, not promising, empty, or otherwise
     fails, runtime falls back to current LibreOffice import.
   - Materialized upload cache separates the text-layer backend from the
     LibreOffice backend, while preserving the original PDF `file_token`.
   - Default remains unchanged: without the env flag, PDF import still uses
     LibreOffice `writer_pdf_import`.
3. Compare output against the PR-PDF0 baseline document before any default
   promotion.

PR-PDF1a local proof:

```bash
DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=1 PYTHONPATH=src python - <<'PY'
from pathlib import Path
from docxaicorrector.processing.processing_runtime import build_in_memory_uploaded_file, freeze_uploaded_file_lightweight, materialize_uploaded_payload
from docxaicorrector.document.extraction import validate_docx_source_bytes, extract_paragraph_units_from_docx
pdf = Path("tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf")
uploaded = build_in_memory_uploaded_file(source_name=pdf.name, source_bytes=pdf.read_bytes())
payload = freeze_uploaded_file_lightweight(uploaded)
materialized = materialize_uploaded_payload(payload)
validate_docx_source_bytes(materialized.content_bytes)
paragraphs = extract_paragraph_units_from_docx(build_in_memory_uploaded_file(source_name=materialized.filename, source_bytes=materialized.content_bytes))
print(materialized.conversion_backend, len(paragraphs))
PY
```

Observed result: `conversion_backend=pdf-text-layer`, generated DOCX validates,
and extraction returns `140` paragraphs on the chapter-region proof PDF.

PR-PDF1a backend comparison proof, 2026-06-01:

```bash
bash scripts/run-pdf-import-backend-comparison.sh \
  --input-pdf tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf \
  --output .run/pdf_text_layer_quality/lietaer-chapter-region-backend-comparison-pr-pdf1a.json
```

Observed metrics:

| Backend | DOCX bytes | Paragraphs | Chars | Headings | Lists | Page-number-like paragraphs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LibreOffice `writer_pdf_import` | 825641 | 336 | 113790 | 7 | 19 | 1 |
| `pdf-text-layer` generated-DOCX bridge | 81256 | 140 | 113418 | 18 | 19 | 0 |

Interpretation:

- The bridge is functionally viable: generated DOCX validates, downstream DOCX
  extraction works, and the text-layer path preserves roughly the same readable
  character volume with fewer paragraphs and no page-number-like paragraph
  leakage.
- The bridge also exposes a real PR-PDF1b boundary: front matter / TOC grouping
  is not yet reliable. In the proof, `CONTENTS` and the following contents lines
  can become large heading-style blocks, and DOCX roundtripping can surface bold
  run markup as `***...***` after extraction.
- This is not a reason to return to reader-cleanup micro-tuning. It is evidence
  that the safe bridge is useful for proofing, while the target architecture
  should still move toward direct `PDF text-layer -> ParagraphUnit ->
  preparation` once the import quality is proven.

Next safe PR-PDF1b slice:

- Keep the env flag off by default.
- Improve deterministic front matter / TOC grouping in the text-layer importer
  without document-specific literals.
- Add direct comparison metrics for first-block quality, heading inflation, and
  markdown-emphasis leakage before any full validation profile or default
  promotion.

PR-PDF1 completion proof, 2026-06-01:

- Implementation:
  - TOC-like trailing-page entries are emitted as bounded `toc_entry`
    structural paragraphs instead of being merged into a giant body/front-matter
    blob.
  - Generated-DOCX bridge no longer writes direct false bold/italic run
    formatting, and it avoids direct run bold/italic on generated Word heading
    paragraphs. Heading role is carried by Word paragraph style instead.
  - Backend comparison now reports `markdown_emphasis_marker_count` so bridge
    formatting leakage is visible in proof artifacts.
  - Generic intentionally/deliberately blank-page notices are skipped as source
    page furniture before translation.
- Proof artifact:
  `.run/pdf_text_layer_quality/lietaer-chapter-region-backend-comparison-pr-pdf1-complete-local.json`
- Observed metrics:

| Backend | Paragraphs | Chars | Headings | Lists | Page-number-like paragraphs | Markdown emphasis markers |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LibreOffice `writer_pdf_import` | 336 | 113790 | 7 | 19 | 1 | 0 |
| `pdf-text-layer` generated-DOCX bridge | 124 | 112514 | 16 | 19 | 0 | 0 |

Interpretation:

- The PR-PDF1a giant TOC/front-matter blob is fixed. The first text-layer
  blocks are now bounded: `CONTENTS`, `Foreword ix ...`, `Generation 1`,
  `PART ONE SCARCITY`, and individual chapter TOC entries.
- The previous `***CONTENTS***` / all-front-matter markdown-bold leakage is
  fixed, and generic intentionally blank page notices are filtered before
  translation.
- PR-PDF1 is complete locally as a feature-flagged bridge. Promotion and the
  direct `PDF text-layer -> ParagraphUnit -> preparation` architecture remain
  PR-PDF3+ work after broader proof.

Formatting and image evidence, 2026-06-01:

```bash
bash scripts/run-pdf-import-backend-comparison.sh \
  --input-pdf tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf \
  --output .run/pdf_text_layer_quality/lietaer-chapter-region-format-image-comparison-pr-pdf1.json
```

Observed formatting/image metrics:

| Backend | Heading paragraphs | List paragraphs | Bold paragraphs | Italic paragraphs | DOCX media | Extracted image assets |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| LibreOffice `writer_pdf_import` | 7 | 19 | 1 | 10 | 12 | 0 |
| `pdf-text-layer` generated-DOCX bridge | 16 | 19 | 0 | 0 | 0 | 0 |

Source PDF image scan:

- `LTImage=12`
- `LTFigure=12`

Interpretation:

- Heading and list formatting transfer is materially better in the text-layer
  bridge than in the LibreOffice baseline for this proof document: generated
  DOCX uses real `Heading 1` / `Heading 2` / `List Bullet` paragraph styles
  instead of one giant LibreOffice `Normal` paragraph with positioned shapes.
- Body bold/italic is not strongly proven by this fixture. The importer has
  unit coverage for preserving span-level bold/italic on body/list paragraphs,
  but the real chapter-region PDF mostly exposes heading bold and blank-page
  italic notices; those notices are now intentionally removed as furniture.
- Images are **not preserved** by the text-layer bridge. The source PDF has 12
  image objects. LibreOffice imports 12 media files, but they arrive as anchored
  drawing/VML-like shapes and the existing DOCX extractor emits `0` image
  assets/placeholders. The text-layer bridge emits `0` images because it only
  serializes text ParagraphUnits.
- Therefore image preservation is an explicit PR-J / source-image handoff item,
  not part of reader cleanup and not solved by PR-PDF1.

Hybrid minimal-formatting contract, 2026-06-01:

- Preserve semantic structure and product-relevant inline signals, not source
  visual styling.
- In scope: headings/subheadings, body paragraph order, ordered/unordered list
  intent, tables as readable structures, images and captions, blockquotes, and
  safe inline emphasis (`bold`, `italic`, plus already-supported underline,
  superscript/subscript, hyperlinks, and line breaks where lineage exists).
- Out of scope by default: font size, source fonts, colors, custom style names,
  local style hierarchy, tab stops, source indents/spacing, broad paragraph XML
  replay, exact PDF visual layout, headers/footers, true Word TOC fields, and
  correct translated page numbers.
- This follows the archived minimal-formatting policy in
  `docs/archive/specs/TOC_TRANSLATION_AND_MINIMAL_FORMATTING_SPEC_2026-04-21.md`
  and `docs/archive/specs/DOCX_FORMATTING_HARDENING_SPEC_2026-03-13.md`.

Hybrid image handoff proof, 2026-06-01:

```bash
bash scripts/run-pdf-import-backend-comparison.sh \
  --input-pdf tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf \
  --output .run/pdf_text_layer_quality/lietaer-chapter-region-format-image-comparison-hybrid-pr-j.json
```

Observed metrics after the text-layer bridge started inserting PDF image
objects into the generated DOCX as normal inline Word images:

| Backend | Heading paragraphs | List paragraphs | DOCX media | DOCX drawings | Extracted image assets |
| --- | ---: | ---: | ---: | ---: | ---: |
| LibreOffice `writer_pdf_import` | 7 | 19 | 12 | 2098 | 0 |
| `pdf-text-layer` hybrid bridge | 16 | 19 | 12 | 12 | 12 |

Interpretation:

- PDF-origin images now enter the existing image pipeline through the same
  DOCX extractor contract as normal DOCX uploads: generated DOCX contains
  inline pictures, extraction emits `[[DOCX_IMAGE_img_NNN]]` placeholders and
  `ImageAsset` objects, and downstream late phases/reinsertion do not need a
  PDF-specific image path.
- Unsupported embedded image encodings are best-effort: the bridge first tries
  original image bytes, then transcodes via Pillow to PNG when `python-docx`
  cannot consume the PDF stream directly. If both fail, text import continues
  without failing the document.
- This closes PR-J1 evidence and the practical PR-J2 bridge path for text-layer
  PDFs. It does not yet prove image quality on scanned/OCR PDFs.
- Span-level `bold`/`italic` text-layer signals are now written as separate
  DOCX runs when adjacent PDF spans merge into one logical paragraph. The real
  chapter-region proof still reports `0` body bold/italic paragraphs because
  this fixture mostly exposes heading bold and intentionally removed blank-page
  italic notices, so broader inline-emphasis quality remains a corpus proof
  item rather than a font-size/style-zoo requirement.

### PR-PDF2. OCR Fallback

Status: deferred for now; partial local plumbing exists behind explicit OCR env
flags, but scanned PDFs are not critical for the current MVP proof.

Purpose:

- For scanned PDFs, run `OCRmyPDF + Tesseract` to create a text-layer PDF, then
  feed the same text-layer importer.

Acceptance:

- Scanned PDF detection is explicit.
- Missing OCR tools produce actionable unsupported diagnostics.
- OCR language selection is configurable.

Local implementation, 2026-06-01:

- OCR fallback is only considered when text-layer import is explicitly enabled
  and the first text-layer quality decision is not `promising`.
- OCR is additionally gated by `DOCXAI_PDF_OCR_IMPORT_ENABLED=1`.
- OCR languages are read from `DOCXAI_PDF_OCR_LANGUAGES`, defaulting to
  `eng+rus`.
- Missing `ocrmypdf` or `tesseract` raises actionable diagnostics such as
  `pdf_ocr_import_unavailable:ocrmypdf`; the outer optional PDF import wrapper
  can then fall back to LibreOffice.
- System dependencies are declared in `system-requirements.apt`:
  `ocrmypdf`, `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-rus`.

### PR-PDF3. Production Promotion / Cleanup Reduction

Purpose:

- Make text-layer import the default for text PDFs only after comparison proof.
- Reclassify post-translation reader cleanup as a safety net, not the primary
  PDF cleanup mechanism.

Acceptance:

- Reader cleanup operation count drops materially on benchmark documents.
- Formatting restoration relies more on source evidence and less on post-hoc
  Markdown inference.
- MVP docs clearly separate source-import cleanup from reader cleanup.

## Stop Rules

- Stop if source-import logic starts duplicating the full DOCX formatting
  restoration system.
- Stop if a rule relies on a literal string from one book.
- Stop if text-layer extraction cannot preserve enough reading order evidence;
  then compare another candidate rather than piling on heuristics.
- Stop before promotion if the new importer improves one document but regresses
  headings/lists/body order on another book-like PDF.
