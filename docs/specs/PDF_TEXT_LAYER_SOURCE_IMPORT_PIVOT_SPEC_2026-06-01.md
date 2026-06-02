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

Production hook notes for PR-PDF1 / PR-PDF3:

- PDF import is now text-layer-first by default in both
  `processing_runtime.materialize_uploaded_payload()` and the sync/eager
  `processing_runtime.normalize_uploaded_document()` path.
- LibreOffice `writer_pdf_import` is removed from the runtime PDF fallback path.
  It remains only as historical/diagnostic comparison code until the next cleanup
  removes the remaining helper and tests.
- If the first implementation still outputs generated DOCX bytes, keep
  `source_format="pdf"` and use a distinct `conversion_backend`, for example
  `pdf-text-layer`.
- If a later implementation builds `ParagraphUnit` directly, it must replace
  the DOCX validation/preparation boundary deliberately and include cache-key
  changes so LibreOffice and text-layer preparations do not share stale cache.

Architectural fork to keep visible:

- **Temporary safe proof path:** `PDF text-layer -> ParagraphUnit signals ->
  generated DOCX -> existing DOCX extractor/preparation`.
  This was initially wired behind `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=1`.
  PR-PDF3 promotes it to the default; the env variable no longer routes runtime
  PDF import back to LibreOffice.
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
- PR-PDF1 was justified as the next implementation PR. PR-PDF3 later promoted
  the proven text-layer bridge to default while keeping LibreOffice as
  deprecated fallback.

### PR-PDF1. Text-Layer PDF -> ParagraphUnit Importer

Status: promoted locally as the default generated-DOCX bridge for PDF inputs.
LibreOffice runtime PDF fallback is removed after the PR-PDF3 closeout decision.
This is not the final architecture; direct `PDF text-layer -> ParagraphUnit ->
preparation` remains the preferred future simplification after proof.

Purpose:

- Implement the first production-capable text-layer importer for PDFs with
  selectable text.
- Build `ParagraphUnit` directly from deterministic paragraphs/headings/lists.
- Stop routing PDF runtime through LibreOffice; unsupported text-layer/OCR cases
  should fail with actionable diagnostics instead of silently using the old
  visual-layout importer.

Acceptance:

- Text-layer PDFs try the deterministic text-layer bridge first by default.
- `writer_pdf_import` is not used by the runtime PDF path.
- Page furniture is removed or flagged before translation.
- Heading/list/body roles are source-backed and visible in diagnostics.
- Existing DOCX input path remains unchanged.
- Empty/scanned/unsupported text-layer PDFs must produce explicit unsupported
  diagnostics or use the OCR gate; they must not produce an empty successful
  document.
- Cache keys keep `pdf-text-layer` identity so old LibreOffice materializations
  cannot be reused as current PDF preparations.

Suggested slice order:

1. Build deterministic grouping from `PdfTextSpan` into a neutral source-import
   representation with roles/signals, without touching UI defaults.
   - Local implementation: `src/docxaicorrector/pdf_import/logical_import.py`
   - Current behavior: removes repeated page furniture/page-number spans,
     merges adjacent body spans, emits standard `ParagraphUnit` with
     `layout_origin="pdf_text_layer"`, heading/list/bold/italic/font-size
     evidence, and identity/provenance fields.
2. Add a PDF materialization path that produces an
   extractor-compatible payload or a deliberate `ParagraphUnit` preparation path.
   - Local PR-PDF1a implementation:
     PDF materialization tries the text-layer generated-DOCX bridge first.
   - The legacy `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=0` override is ignored by
     runtime PDF import after PR-PDF3 removal: text-layer remains the only active
     PDF import path.
   - If the text-layer path is unsupported, not promising, empty, or otherwise
     fails, runtime surfaces the diagnostic instead of falling back to
     LibreOffice.
   - Materialized upload cache preserves the original PDF `file_token` while
     keeping the text-layer backend identity.
3. Compare output against the PR-PDF0 baseline document and then remove runtime
   fallback to the old LibreOffice PDF path.

PR-PDF1a local proof:

```bash
PYTHONPATH=src python - <<'PY'
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

Completed PR-PDF1b slice:

- Improve deterministic front matter / TOC grouping in the text-layer importer
  without document-specific literals.
- Add direct comparison metrics for first-block quality, heading inflation, and
  markdown-emphasis leakage before any full validation profile or fallback
  removal.

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
- PR-PDF1 is complete locally as a bridge; PR-PDF3 promotes it to runtime PDF
  path and removes LibreOffice fallback. The direct `PDF text-layer ->
  ParagraphUnit -> preparation` architecture remains a later simplification
  after broader proof.

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

Additional hybrid proofs, 2026-06-01:

```bash
bash scripts/run-pdf-import-backend-comparison.sh \
  --input-pdf tests/sources/Rethinking-money-first-20-pages.pdf \
  --output .run/pdf_text_layer_quality/rethinking-first-20-backend-comparison-hybrid-pr-pdf3.json

bash scripts/run-pdf-import-backend-comparison.sh \
  --input-pdf "tests/sources/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf" \
  --output .run/pdf_text_layer_quality/mazzucato-value-everything-backend-comparison-hybrid-pr-pdf3.json
```

| Document | Backend | Paragraphs | Chars | Headings | Lists | Page-number-like | DOCX media | Extracted image assets |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rethinking first 20 | LibreOffice | 85 | 24307 | 5 | 0 | 0 | 1 | 0 |
| Rethinking first 20 | `pdf-text-layer` hybrid | 56 | 24165 | 19 | 0 | 0 | 1 | 1 |
| Mariana full PDF | LibreOffice | 2778 | 740755 | 27 | 363 | 22 | 34 | 0 |
| Mariana full PDF | `pdf-text-layer` hybrid | 1150 | 743501 | 32 | 379 | 10 | 34 | 42 |

Interpretation:

- The hybrid bridge is not a one-document win. It preserves or improves
  heading/list structure and image asset handoff on both the original Lietaer
  proof family and the full Mariana PDF.
- `markdown_emphasis_marker_count=154` on the Mariana text-layer path is not the
  old false heading/front-matter leakage. It is expected markdown produced by
  the normal DOCX extractor from real bold/italic runs emitted by the bridge.
  It still needs reader/translation-path validation, but it is evidence that
  semantic inline emphasis is now flowing, not a reason to preserve font size or
  source style families.
- Page-number-like leakage is reduced but not eliminated on the Mariana full
  PDF (`22 -> 10`). Promotion should keep a page-furniture quality gate rather
  than claim that all PDFs are solved.

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

Status: closed locally on 2026-06-01. The text-layer bridge is the only runtime
PDF import path for selectable-text PDFs. LibreOffice fallback/legacy override
has been removed from the runtime PDF path; remaining LibreOffice PDF code is
historical diagnostic/deletion cleanup.

Purpose:

- Make text-layer import the default for text PDFs after comparison proof.
- Reclassify post-translation reader cleanup as a safety net, not the primary
  PDF cleanup mechanism.

Closeout, 2026-06-01:

- Implemented locally: text-layer import is the runtime PDF path.
- `DOCXAI_PDF_TEXT_LAYER_IMPORT_ENABLED=0`, `false`, `no`, `off`, `legacy`, and
  `libreoffice` no longer force LibreOffice for PDF runtime import.
- If text-layer quality is not `promising`, generated-DOCX assembly fails, or
  the input class is not yet supported, runtime now surfaces the text-layer/OCR
  diagnostic instead of silently using LibreOffice.
- Remaining LibreOffice PDF helper/test references are deletion-cleanup debt,
  not an active fallback policy.
- Active follow-up is no longer PR-PDF3. Remaining work belongs to:
  - direct `PDF text-layer -> ParagraphUnit -> preparation` simplification;
  - post-materialization quality gate for residual page furniture/page numbers;
  - deletion cleanup for remaining diagnostic LibreOffice PDF helper/tests/docs.

Canonical closeout proof, 2026-06-01:

```bash
DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-chapter-region-core \
DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-simple-reader-cleanup-comparison-only \
DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE=1 \
DOCXAI_REAL_DOCUMENT_FORCED_RUN_ID=20260601T_pdf3_closeout_rethinking_chapter_region \
bash scripts/run-real-document-validation.sh
```

Artifacts:

- Report:
  `tests/artifacts/real_document_pipeline/runs/20260601T_pdf3_closeout_rethinking_chapter_region/lietaer_pdf_chapter_region_report.json`
- Cleaned Markdown:
  `.run/ui_results/20260601_201538_Rethinking-money-chapter-region-pages-10-11-and-156-217.result.md`
- Cleaned DOCX:
  `.run/ui_results/20260601_201538_Rethinking-money-chapter-region-pages-10-11-and-156-217.result.docx`

Observed result:

- Pipeline result: `succeeded`.
- Runtime profile: `structure_recognition_mode=off`,
  `reader_cleanup_enabled=true`, `reader_verifier_enabled=true`,
  `reader_cleanup_chunk_size=8000`, overlap `3/3`,
  `reader_cleanup_global_plan_enabled=false`.
- Preparation: `139` paragraphs, `12` source image assets, `57` jobs,
  `113089` source chars.
- Reader cleanup: `failed_chunk_count=0`, `accepted_cleanup_operation_count=15`,
  `accepted_delete_block_count=0`, `deleted_char_ratio=0.0`.
- Verifier: `cleaned_better`, confidence `high`, raw score `4.0`, cleaned score
  `6.0`, `remaining_issue_count=13`.
- Acceptance diagnostics remain failed:
  `formatting_diagnostics_threshold`, `unmapped_source_threshold`,
  `unmapped_target_threshold`, `false_fragment_headings_present`.
- Final DOCX is openable, but `output_inline_shapes=0` even though preparation
  found `12` image assets. This means source image extraction works, but
  translated/final DOCX image reinsertion is still not product-complete.
- 2026-06-02 interpretation: this makes images release-blocking for the
  text-layer PDF MVP. The next active slice is PR-J2 diagnostic + fix, starting
  with placeholder survival evidence across assembled Markdown, translated
  Markdown, reader-cleaned Markdown, final DOCX text, and
  `reinsert_inline_images()`.
- PR-J2 diagnostic result, 2026-06-02: the same closeout artifact family shows
  `12` image placeholders in raw result Markdown, `0` in reader-cleaned result
  Markdown, and `0` placeholders / `0` inline shapes / `0` media files in the
  final DOCX. Source image extraction is healthy; the failing layer is the
  reader-cleanup -> DOCX-rebuild handoff.
- PR-J2 local fix, 2026-06-02: DOCX rebuild after reader cleanup restores
  missing image placeholder blocks from raw cleanup Markdown into rebuild-only
  Markdown. Reader-facing cleaned Markdown remains free of internal
  `[[DOCX_IMAGE_img_NNN]]` tags. Local artifact proof restores `12/12`
  placeholders for rebuild.
- PR-J2 clean proof, 2026-06-02:
  `20260602T_pr_j2_image_reinsertion_proof` succeeded. Preparation saw `12`
  image assets; final DOCX has `12` inline shapes and `12` media files, with
  `output_contains_placeholder_markup=False`. The previous
  `output_inline_shapes=0` blocker is fixed for the text-layer proof PDF.
- Formatting preservation is partial:
  - final DOCX has `8` heading-styled paragraphs (`Heading 1`/`Heading 2`), so
    heading transfer exists but still collapses some multi-line headings;
  - final DOCX has `0` Word list-style paragraphs, so list formatting is not
    release-ready;
  - final DOCX has only `1` italic run and no bold-run evidence in this proof,
    so inline emphasis preservation remains weak;
  - formatting diagnostics still fail with `83` unmapped source paragraphs and
    `55` unmapped target paragraphs in the stricter restore pass.
- PR-I1 local follow-up, 2026-06-02: formatting lineage hardening has started
  at the handoff that feeds reader-cleanup DOCX rebuild. The rebuild path now
  receives the generated paragraph registry built from the actual final assembly
  entries, so cleanup-derived formatting lineage is no longer based on stale
  state registry entries when an assembly-aware registry is available. A fresh
  proof run is still needed to measure whether the unmapped source/target
  counts improve on the chapter-region PDF.
- PR-I1 proof v2, 2026-06-02:
  `20260602T_pr_i1_formatting_lineage_registry_proof_v2` kept images stable
  (`12/12` final inline shapes/media) and verifier evidence was healthy again
  (`cleaned_better`, high confidence, `4.0 -> 6.0`). Formatting restore mapping
  improved modestly relative to PR-J2 (`mapped_count 67 -> 72` in the latest
  restore diagnostics), but acceptance still failed and
  `reader_cleanup_applied` still reported
  `formatting_lineage_status=skipped` /
  `cleanup_block_registry_count_mismatch`. PR-I1 therefore remains open as a
  lineage-diagnostics/contract slice; PR-I2 formatting application should not
  start until the mismatch owner is explicit.
- PR-I1 proof v4, 2026-06-02:
  `20260602T_pr_i1_formatting_lineage_sparse_alignment_proof_v4` resolved that
  mismatch for the current image-gap case. `reader_cleanup_applied` reports
  `formatting_lineage_status=derived`,
  `alignment_mode=sparse_image_placeholders`, `alignment_gap_count=12`,
  `raw_cleanup_block_count=123`, `generated_registry_count=111`,
  `derived_registry_count=108`, and `applied_operation_count=16`. Images remain
  stable (`12/12` final inline shapes/media) and verifier is healthy
  (`cleaned_better`, high confidence, `4.0 -> 6.0`). Acceptance still fails on
  formatting/unmapped/false-fragment diagnostics, so the next work should not be
  another full proof loop; use a short lineage/rebuild diagnostic harness until
  the next milestone proof is needed.
- PR-I1 root-cause interpretation, 2026-06-02: both remaining failure modes
  share one cause. The formatting registry stitch in
  `_derive_reader_cleanup_generated_paragraph_registry()` and the image
  reinsertion stitch in `_build_docx_rebuild_markdown_after_reader_cleanup()`
  both align cleanup output to source by comparing `normalized_text`, which is
  exactly what reader cleanup rewrites. Any non-image text drift (merge, split,
  inline-noise edit) therefore degrades into `status=skipped` /
  `cleanup_block_registry_count_mismatch` and falls back to a stale registry,
  while image position depends on a fragile text match to a neighbor block.
  `ParagraphUnit.paragraph_id` already carries a stable identity that neither
  stitch consumes. The next active work is PR-I1b: carry that identity through
  cleanup blocks and switch both stitches from text matching to id matching.
  Do not add more cleanup heuristics and do not start the direct
  `ParagraphUnit -> preparation` rewrite to fix this; it is a stitch-key change,
  not an architecture change.

Closeout interpretation:

- PR-PDF3 is closed as a source-import runtime switch away from LibreOffice PDF
  fallback.
- It is not proof that all downstream formatting, image, and cleanup quality is
  release-ready.
- PR-J2 may move before PR-I1 because images are release-blocking. This is not a
  return to LibreOffice and not a reader-cleanup responsibility.
- Do not reintroduce LibreOffice as a PDF fallback while polishing image handoff
  and formatting diagnostics; compare libraries as candidates instead.
- Deletion debt to schedule after image/formatting proof: remove the remaining
  LibreOffice PDF helper and comparison-only tests/docs that still exist solely
  for historical diagnostics. Do not remove legacy `.doc` LibreOffice support in
  that cleanup; `.doc` conversion is a separate input path.

Acceptance:

- Reader cleanup operation count drops materially on benchmark documents.
- Formatting restoration relies more on source evidence and less on post-hoc
  Markdown inference.
- MVP docs clearly separate source-import cleanup from reader cleanup.
- Legacy LibreOffice fallback is removed from runtime PDF import and any
  remaining helper/test references are tracked as deletion cleanup.

### PR-I1b. Identity-Anchored Cleanup Stitch (active local slice)

Status: diagnostic slice 1 and the id-first consumer switch are implemented
locally on 2026-06-02. This is covered by focused lineage/rebuild tests; a
short artifact harness or milestone proof is still needed before claiming
real-document acceptance improvement.

Problem:

- The two post-cleanup stitches that feed DOCX rebuild both key on
  `normalized_text`, the one signal reader cleanup is allowed to mutate:
  - formatting lineage:
    `_derive_reader_cleanup_generated_paragraph_registry()` matches registry
    entries to raw cleanup blocks by normalized text and order. It only
    tolerates extra raw blocks when they are DOCX image placeholders
    (`alignment_mode=sparse_image_placeholders`); any non-image text drift
    returns `status=skipped` / `cleanup_block_registry_count_mismatch` and the
    stale registry is reused.
  - image position:
    `_build_docx_rebuild_markdown_after_reader_cleanup()` reinserts each
    `[[DOCX_IMAGE_img_NNN]]` block relative to a neighbor block found by text
    match, so a cleanup-rewritten neighbor loses the exact insertion anchor.
- `ParagraphUnit.paragraph_id` (plus `source_index` / `logical_index`) already
  provides a stable identity that survives text rewrites, but neither stitch
  consumes it.

Goal:

- Make formatting-lineage and image-position recovery survive ordinary reader
  cleanup text edits by stitching on stable paragraph identity instead of
  mutated text, without adding cleanup heuristics and without starting the
  direct `ParagraphUnit -> preparation` rewrite.

Slice order:

1. Diagnostic-only (no behavior change). Carry `paragraph_id` onto cleanup
   blocks (`build_cleanup_blocks()` / `CleanupBlock`) and log, in
   `reader_cleanup_applied`, how many alignment gaps would resolve by id versus
   by text. This produces evidence with zero risk to reader-facing output.
   Status: implemented locally.
2. Switch both stitches to
   id-first matching, with the current normalized-text match kept only as a
   fallback when an id is missing. Status: implemented locally for formatting
   registry derivation and rebuild-only image placeholder anchoring.
3. Verify with the existing short lineage/rebuild diagnostic harness from PR-I1
   proof v4, not a full-book run. Status: pending.

Acceptance:

- For the chapter-region proof PDF, `formatting_lineage_status=derived` no
  longer degrades to `skipped` on non-image text drift.
- `unmapped_source` / `unmapped_target` counts drop materially versus PR-I1
  proof v4.
- Image inline-shape count stays `12/12` and image position is anchored by id,
  not by neighbor text.
- Reader-facing cleaned Markdown still contains no internal
  `[[DOCX_IMAGE_img_NNN]]` tags.

Non-goals:

- No new reader-cleanup operations or heuristics.
- No document-specific literals.
- No direct `ParagraphUnit -> preparation` migration (tracked separately as the
  post-proof simplification).

Gate to PR-I2:

- PR-I2 formatting application stays blocked until PR-I1b shows the mismatch
  owner is the stitch key, and id-anchored stitching reaches `derived` on text
  drift, not only on the image-only gap case.

Local diagnostic slice 1, 2026-06-02:

- `CleanupBlock` now carries optional `paragraph_id` / `merged_paragraph_ids`
  metadata when the pipeline can derive it from `generated_paragraph_registry`.
- This metadata is intentionally **not** serialized by `CleanupBlock.to_payload()`;
  model prompt shape, reader-facing Markdown, and cleanup operation behavior are
  unchanged.
- `late_phases._build_reader_cleanup_block_identity_metadata()` builds the
  diagnostic sidecar from raw cleanup Markdown and registry entries, reporting
  matched id blocks plus image/text gaps.
- `reader_cleanup_applied` / `reader_cleanup_noop` now log
  `cleanup_identity_*` counters so the next proof can compare id-available
  alignment against text-based lineage alignment.
- Focused test coverage confirms: id metadata does not leak into model payload,
  image-placeholder gaps are counted, non-image gaps remain visible, and the
  existing sparse formatting-lineage behavior is unchanged.

Local id-first consumer switch, 2026-06-02:

- `_derive_reader_cleanup_generated_paragraph_registry()` now accepts cleanup
  block identity metadata and uses `paragraph_id` / `merged_paragraph_ids` to
  align raw cleanup blocks to generated registry entries before falling back to
  normalized-text sparse alignment.
- `_build_docx_rebuild_markdown_after_reader_cleanup()` now accepts the same
  cleanup identity metadata plus the cleanup-derived registry. Missing
  `[[DOCX_IMAGE_img_NNN]]` blocks are reinserted into rebuild-only Markdown
  relative to paragraph identity first, and neighbor text only as fallback.
- Reader-facing cleaned Markdown is unchanged and still contains no internal
  image placeholder markup.
- Focused tests prove the intended text-drift case: raw neighbor text can differ
  from cleaned/registry text while registry alignment and image anchoring still
  succeed by `paragraph_id`.
- Important evidence caveat: the previous PR-I1 proof v4 artifacts do **not**
  contain `cleanup_identity_*` counters, because this diagnostic layer was added
  later. Use a short PR-I1b harness or the next milestone proof for real-document
  identity coverage evidence.

## Stop Rules

- Stop if source-import logic starts duplicating the full DOCX formatting
  restoration system.
- Stop if a rule relies on a literal string from one book.
- Stop if text-layer extraction cannot preserve enough reading order evidence;
  then compare another candidate rather than piling on heuristics.
- Stop before promotion if the new importer improves one document but regresses
  headings/lists/body order on another book-like PDF.
