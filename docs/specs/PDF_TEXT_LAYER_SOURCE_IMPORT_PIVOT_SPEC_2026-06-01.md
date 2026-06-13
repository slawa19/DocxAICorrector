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
   proof v4, not a full-book run. Status: harness implemented; old proof v4
   is blocked by missing cleanup-time generated registry, so the next proof must
   use the new lineage artifact written by runtime.

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

Local slice 3 harness / artifact retention, 2026-06-02:

- Added
  `scripts/run-reader-cleanup-lineage-rebuild-harness.py`.
  It runs without LLM/full validation and checks raw cleanup Markdown, cleaned
  Markdown, cleanup report, registry/identity metadata, formatting lineage, and
  rebuild-only image placeholder restoration.
- Running the harness against old PR-I1 proof v4 produced
  `status=blocked`, not a code failure:
  - raw cleanup blocks: `123`;
  - raw image placeholders: `12`;
  - cleaned image placeholders: `0`;
  - runtime `processed_paragraph_registry`: `127` entries but only `1`
    cleanup block id match before text order diverges;
  - formatting-diagnostics reconstruction: `82` id-mapped target entries out
    of `111`, leaving `29` text gaps;
  - both attempts still restore rebuild-only image placeholders to `12`, but
    neither can prove real-artifact id-first formatting lineage.
- Root cause: old proof artifacts did not persist the cleanup-time
  `generated_paragraph_registry` / identity sidecar needed by PR-I1b. This is an
  artifact-retention gap, not a reason to add cleanup heuristics.
- Runtime now writes `.run/reader_cleanup_lineage/*.json` artifacts containing
  raw/cleaned Markdown, cleanup report, active formatting registry,
  `cleanup_identity_*`, and cleanup-derived formatting registry/lineage. Future
  PR-I1b proof should run the harness with `--lineage-artifact <path>` and must
  pass before PR-I1c starts.

PR-I1b slice 3 proof, 2026-06-02:

- Canonical comparison-only proof run:
  `20260602T_pr_i1b_identity_lineage_artifact_proof`.
- Source/profile:
  `lietaer-pdf-chapter-region-core` with
  `ui-parity-translate-simple-reader-cleanup-comparison-only`.
- Lineage artifact:
  `.run/reader_cleanup_lineage/Rethinking-money-chapter-region-pages-10-11-and-156-217.docx_1780413624541.json`.
- Harness command:
  `python scripts/run-reader-cleanup-lineage-rebuild-harness.py --lineage-artifact <path>`.
- Harness result: `status=passed`.
- Key proof metrics:
  - raw cleanup blocks: `123`;
  - active formatting registry entries: `111`;
  - id-matched cleanup blocks: `111`;
  - image gaps: `12`;
  - text gaps: `0`;
  - cleanup formatting lineage: `derived`;
  - alignment mode: `identity_sparse_image_placeholders`;
  - derived registry entries: `108`;
  - applied cleanup lineage operations: `12`;
  - reader-facing cleaned Markdown image placeholders: `0`;
  - rebuild-only Markdown image placeholders restored: `12`.
- The real-document comparison-only run itself is not an acceptance pass
  (`acceptance_diagnostic=failed`), because formatting diagnostics/unmapped
  thresholds and false fragment headings remain. For PR-I1b, the stitch proof is
  green: id-first lineage and rebuild-only image placeholder restoration are
  stable enough to unblock PR-I1c.

### PR-I1c. Reader Cleanup Mutation Budget (measurement complete, decision caveated)

Status: measurement infrastructure completed locally, with verifier-validity
caveat. PR-I1b slice 3 passed on
`20260602T_pr_i1b_identity_lineage_artifact_proof`, then PR-I1c ran the planned
current/minimal/no-op comparison. The runs are useful evidence, but they did
not prove a same-basis A/B winner because the LLM verifier produced a completed
verdict only for `current`.

Problem:

- After the text-layer source importer, most PDF noise (page furniture, repeated
  headers, page numbers) is supposed to be removed before translation. Yet
  post-translation reader cleanup is still the large, heavily mutating component
  it was when it was the primary cleaner.
- Cleanup's text mutation is the documented root cause of the lineage/image/
  formatting stitch failures (PR-I1 root-cause interpretation). The more it
  mutates, the more downstream repair it forces.
- At the same time, mutation is not pure cost: prior closeout evidence and the
  `current` PR-I1c run show that the canonical cleanup path performs real
  bounded structural cleanup with no body deletion. Cutting cleanup blindly to
  delete-only could regress useful reader polish, but PR-I1c did not prove
  `current > minimal` as a measured A/B result.

Goal:

- Decide, with evidence, the smallest cleanup mutation contract that preserves
  useful reader polish while minimizing downstream stitch repair. Produce one
  measured fork, then make exactly one final contract switch. Do not ship a
  "try minimal for a while" intermediate.

A/B measurement (one run, three measured variants on the same frozen PDF
`tests/sources/Rethinking-money-chapter-region-pages-10-11-and-156-217.pdf`):

1. `current` cleanup (full mutating contract, today's behavior).
2. `minimal` cleanup (safe page/image/furniture deletion only; no merge/split/
   inline-noise/heading rewrites).
3. `no-op` cleanup (disabled), as the floor reference.

Implementation note:

- `minimal` is now a real profile-level contract, not a manual convention:
  `reader_cleanup_allowed_operations = ["delete_block", "remove_inline_noise"]`.
  The allowed operation list is serialized into cleanup payloads and enforced at
  runtime; disallowed operations become ignored diagnostics with
  `operation_not_allowed_by_cleanup_contract`.
- `no-op` is a real comparison-only profile using `reader_cleanup_enabled=false`
  and `reader_cleanup_policy="off"`.

PR-I1c A/B proof, 2026-06-02:

| Variant | Run id | Cleanup result | Images | Reader verifier | Reader delta | Notes |
|---|---|---:|---:|---|---:|---|
| `current` | `20260602T_pr_i1b_identity_lineage_artifact_proof` | `12` accepted ops (`join_fragmented_paragraph=3`, `normalize_heading_boundary=9`), `0` delete blocks, `deleted_char_ratio=0.0` | `12/12` | `cleaned_better`, high, `20` remaining issues | `+1.0` | Only variant with a completed LLM verdict; this is secondary evidence, not a measured A/B win. |
| `minimal` | `20260602T_pr_i1c_minimal_cleanup_budget_proof` | `0` accepted ops, `0` delete blocks, `deleted_char_ratio=0.0` | `12/12` | `failed` / `unclear`, low, `16` remaining issues | `0.0` | Safe but effectively no cleanup on this artifact; lower reproducible issue inventory is a signal, not proof of better cleanup. |
| `no-op` | `20260602T_pr_i1c_noop_cleanup_budget_proof` | cleanup skipped | `12/12` | `not_run` / `unclear`, low, `23` remaining issues | `0.0` | Floor reference; no raw/cleaned cleanup pair for verifier. |

A/B artifact:

- `.run/diagnostics/pr_i1c_reader_cleanup_mutation_budget_ab.json`.

Interim decision:

- Keep the current canonical small-overlap cleanup contract as the working
  cleanup contract for now, as a heuristic engineering decision rather than an
  A/B-proven superiority claim:
  `8000`, overlap `3/3`, `global_plan=false`, `policy=advisory`, no
  operation allow-list, existing safety caps
  (`max_delete_block_ratio=0.03`, `max_delete_char_ratio=0.05`,
  `max_consecutive_deleted_blocks=3`, `max_deleted_block_chars=300`).
- Rationale: `current` performs real bounded cleanup (`12` accepted structural
  operations, `deleted_char_ratio=0.0`, images `12/12`), while `minimal` made
  no accepted cleanup operations on this artifact. However, do **not** claim
  `current > minimal` was measured: the one reproducible issue-inventory signal
  is `minimal=16`, `current=20`, `no-op=23`.
- Do **not** promote `minimal` on this run either: it preserved safety but did
  not demonstrate that it can clean; it mostly demonstrates that a no-mutation
  contract is safe on this artifact.
- PR-I2/PR-CLEANUP0 must not start from the old "A/B proved the final contract"
  wording. They may proceed only after this caveat is accepted as the explicit
  basis, or after a valid same-basis A/B / variance proof is added.
- PR-I1c-ACCEPT, 2026-06-02: the project explicitly accepts the caveated
  heuristic basis. `current` remains the working cleanup contract because it
  performs bounded structural cleanup with flat safety metrics, not because it
  won a same-basis A/B. LLM verdicts are secondary evidence; deterministic
  pre-audit / mandatory issue inventory is the primary reproducible signal.
  This acceptance removes the PR-I2 gate without changing cleanup code.

Metrics to capture per variant:

- deterministic verifier pre-audit / mandatory issue inventory as the primary
  reproducible cleanup-quality signal;
- LLM reader verifier score/verdict only as secondary explanatory evidence
  (the completed-review `remaining_issue_count` can include model-supplied
  issues merged with deterministic pre-audit findings);
- final DOCX inline shapes (must stay `12/12`);
- `formatting_lineage_status` (must reach `derived`, not `skipped`);
- `unmapped_source` / `unmapped_target` counts;
- semantic-deletion check: `deleted_char_ratio` and no body-content loss.

Decision rule (single final cut, no shipped intermediate):

- If `minimal` is approximately as good as `current` on reader quality and
  better on lineage/stitch, make `minimal` the **final** production cleanup
  default and freeze the mutation budget as an explicit number/flag set.
- If `current` is clearly better on reader quality, keep it, but cap the
  mutation budget (e.g. `deleted_char_ratio` ceiling plus disabling whichever
  operation classes showed no reader-quality contribution in the A/B).
- Either branch is final. The three variants are measurements, not three
  releases.

Acceptance:

- One A/B artifact (single JSON/table, same shape as the existing proof
  artifacts in this spec) records all three variants with the metrics above.
- A single working cleanup contract is written into this spec with its mutation
  budget and an explicit evidence class: measured, heuristic, or blocked.
- Images stay `12/12` and `formatting_lineage_status=derived` under the selected
  contract.
- No semantic body deletion in the selected contract.

Non-goals:

- **No shipped intermediate cleanup default.** The A/B selects one contract that
  is immediately final; do not release `minimal` "to try" and re-decide later.
- No new reader-cleanup operations or heuristics.
- No document-specific literals.
- No formatting application (that is PR-I2, layered on top of the selected
  contract).

Gate to PR-I2:

- Satisfied by PR-I1c-ACCEPT, 2026-06-02, as an explicit heuristic acceptance,
  not as an A/B proof. PR-I2 formatting transfer can start over the current
  canonical small-overlap cleanup contract. Do not cite the LLM verdict as
  objective evidence that `current` beat `minimal`.

### PR-I1c verifier-validity caveat and next-agent handoff (2026-06-02)

Status: accepted as heuristic basis on 2026-06-02. The PR-I1c "keep current"
decision is recorded above, but the evidence it rests on is weaker than it
looks. A next agent must read this before using the A/B table as proof; PR-I2
may start only because the caveat is explicitly accepted, not because the A/B
proved superiority.

What is actually broken in the A/B comparison:

- The reader verifier is **harness-only**. It lives exclusively in
  `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`. In `src/`
  the `reader_verifier_*` config fields gate nothing. So its verdict is
  development evidence, not a production gate.
- The verifier has two independent parts with very different reliability:
  1. A deterministic regex pre-audit
     (`_run_reader_verifier_pre_audit()`, ~L1975) that produces the mandatory
     issue inventory. This is reproducible and comparable across variants. Use
     this as the primary cleanup-quality signal.
  2. An LLM-as-judge (`_build_reader_verifier_system_prompt()`, ~L2434) that
     emits `overall_verdict` plus `reader_quality_score_raw/_cleaned`. The
     prompt gives **no numeric scale and no rubric**, so the model invents the
     numbers. They are non-deterministic (the same PDF produced `+2.0` in the
     PR-PDF3 closeout and `+1.0` in this A/B). Do not treat this verdict or its
     delta as an objective metric.
- The LLM judge only runs when a raw/cleaned artifact pair exists. See the
  precondition at ~L3182: missing pair returns `verifier_status="not_run"`,
  `verifier_reason="base_artifacts_missing"`, and a hardcoded
  `overall_verdict="unclear"` / scores `0.0` / `confidence="low"`.
- Consequence for the A/B: the judge produced a real verdict **only for
  `current`** (`completed`). `minimal` came back `failed`/`unclear` and `no-op`
  came back `not_run`/`unclear`. So "only `current` has a proven reader-quality
  gain" really means "only `current` got any verdict at all" — it is a missing-
  data artifact, not a head-to-head win.
- The one reproducible issue-inventory signal points the other way:
  `minimal=16` < `current=20`. By the trustworthy floor signal, `minimal` looks
  slightly cleaner, not worse. Caveat: `minimal` made `0` cleanup operations on
  this artifact, so 16-vs-20 may be coincidental rather than earned. Also note:
  when the LLM review completes, final `remaining_issue_count` can include
  model-supplied issues merged with deterministic pre-audit findings, so do not
  describe every completed-run count as purely regex-derived.

Honest framing of the current decision:

- `current` was not proven superior by the A/B. The A/B is structurally
  unable to answer "which of three cleanup variants is best", because the LLM
  judge only answers "is cleaned better than raw?" for one variant at a time and
  needs a raw/cleaned pair the other two variants never produced.
- A defensible reason to keep `current` does exist, but it is heuristic, not
  measured: `current` performs real cleanup (12 accepted ops, no body deletion,
  `deleted_char_ratio=0.0`, images `12/12`), while `minimal` effectively does
  nothing on this artifact. "Safe because it changes nothing" is not the same as
  "cleans better".

What the next agent should do (pick one; do not silently keep the broken claim):

1. Reframe the decision honestly in this spec (smallest, lowest-risk step).
   Change the PR-I1c decision wording from "proven gain / do not promote
   minimal" to: keep `current` as a heuristic choice (it cleans without content
   loss; minimal does not clean on this artifact), explicitly marked
   `not proven by A/B`, and demote the LLM verdict/score to secondary
   explanatory evidence. Make deterministic pre-audit / mandatory issue
   inventory the primary cleanup-quality metric of record.
2. Fix the A/B so the judge runs on all three variants (only if a real measured
   comparison is wanted). For every variant feed the same raw artifact plus that
   variant's cleaned artifact; for `no-op` set `cleaned == raw` so the judge
   returns "no change" instead of `not_run`; investigate why `minimal` returned
   `failed` and give it a valid pair. Only then are the three verdicts on one
   basis.
3. Measure judge variance (supports option 1). Run `current` 3-5 times on the
   same frozen PDF and record the spread of `cleaned_score` / delta. If the
   spread is wide (we already have `+2.0` vs `+1.0`), that confirms the LLM
   score must not drive the decision.

Recommended path: option 1 + option 3. Treat the deterministic issue inventory
as primary, fold the LLM verdict to a labeled secondary signal, and re-word the
PR-I1c decision as a heuristic "keep current" rather than a measured win.

Resolution: option 1 is now complete and option 3 has one follow-up current
probe. The remaining action is PR-I2 diagnostic work, not another cleanup
heuristic.

Follow-up current variance probe, 2026-06-02:

- Run id:
  `20260602T_pr_i1c_current_verifier_variance_proof`.
- Source/profile:
  `lietaer-pdf-chapter-region-core` /
  `ui-parity-translate-simple-reader-cleanup-comparison-only`.
- Command caveat: this was a **single** current run. It was launched with
  `DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE=3`, but the harness records
  `repeat_count=3` without repeat orchestration (`repeat_runs` absent). Do not
  count it as three independent repeats.
- Result:
  - pipeline result: `succeeded`, comparison-only acceptance diagnostic:
    `failed` on formatting/unmapped/false-fragment checks;
  - images: `12/12`;
  - cleanup: `failed_chunk_count=0`, `accepted_cleanup_operation_count=15`
    (`normalize_heading_boundary=12`, `join_fragmented_paragraph=3`),
    `accepted_delete_block_count=0`, `deleted_char_ratio=0.0`;
  - verifier: `completed`, `cleaned_better`, high,
    score `5.0 -> 6.0` (`+1.0`), `remaining_issue_count=10`,
    high severity issues `6`.
- Interpretation: this strengthens, rather than weakens, the caveat. The same
  current profile now has at least two materially different verifier inventories
  on the same frozen PDF (`20` in PR-I1c A/B vs `10` in this follow-up) while
  keeping safety flat. Treat the LLM score/verdict as secondary and volatile;
  do not use it as the sole reason to delete or promote cleanup surface.

Hard constraints for the next agent:

- Do not present the LLM verdict (`cleaned_better`, PR-I1c `4.0 -> 5.0`,
  older closeout `4.0 -> 6.0`) as an objective metric anywhere in this spec.
- Do not claim `current > minimal` was measured; the A/B cannot support that.
- Do not add reader-cleanup operations or heuristics to "fix" the comparison.
- Do not start PR-I2 or PR-CLEANUP0 deletion on the assumption that the
  contract choice is fully proven; the contract is acceptable to proceed on, but
  the justification in the spec must be corrected first.

### PR-I2. Formatting Preservation Implementation (active)

Status: active next after PR-I1c-ACCEPT. The cleanup contract is accepted as a
working heuristic, images are stable at `12/12`, and id-first cleanup stitch is
green. PR-I2 should focus on formatting transfer/diagnostics, not new cleanup
operations.

First diagnostic slice, 2026-06-02:

- Source run:
  `20260602T_pr_i1c_current_verifier_variance_proof`.
- Diagnostic artifact:
  `.run/diagnostics/pr_i2_unmapped_formatting_diagnostic.json`.
- Acceptance blockers from the run:
  - `formatting_diagnostics_threshold`: `56` unmapped source paragraphs vs
    threshold `12`;
  - `unmapped_source_threshold`: `56` vs allowed `12`;
  - `unmapped_target_threshold`: `48` vs allowed `6`;
  - `false_fragment_headings_present`: `15`.
- Formatting diagnostics show two restore passes:
  - pass 0: `source_count=139`, `target_count=111`, `mapped_count=81`,
    `unmapped_source=42`, `unmapped_target=30`, with unmapped source roles:
    `image=4`, `heading=13`, `body=15`, `list=10`;
  - pass 1: `source_count=139`, `target_count=123`, `mapped_count=75`,
    `unmapped_source=56`, `unmapped_target=48`, with unmapped source roles:
    `body=33`, `heading=12`, `list=11`.
- Read-only code/report review confirmed the problem is conservative formatting
  alignment, not missing lineage:
  - worst pass mapping strategy distribution is approximately
    `paragraph_id_registry=62`, `image_anchor=12`,
    `paragraph_id_registry_similarity=1`;
  - accepted split targets are `0`;
  - therefore PR-I2 must teach formatting transfer to classify/apply lineage
    across translated output shape changes such as TOC compaction, heading/body
    fusion, image+heading fusion, source-paragraph merge, and target-paragraph
    split.
- Sample failure shape:
  - source TOC/list-like entries remain separate (`10 truth and consequences`,
    `11 governance and we, the citizens`, `notes`, `bibliography`);
  - target combines several of them into one paragraph
    (`10 истина и последствия... 11 управление... 12 ...`);
  - body paragraphs and headings also drift between source paragraph units and
    translated target paragraphs.
- `false_fragment_headings_present` is currently sourced from
  `legacy_markdown`; samples include normal chapter/section heading lines such
  as `## Глава восьмая`, `# СТРАТЕГИИ ДЛЯ`, `# ПРАВИТЕЛЬСТВА`,
  `# ПЕРЕОСМЫСЛЕНИЕ`, `# ДЕНЬГИ`. First PR-I2 work must classify whether this
  is a real output defect or a stale legacy gate after text-layer import.
- PR-I2 heading-span source fix, 2026-06-03:
  - Local implementation in `src/docxaicorrector/pdf_import/logical_import.py`
    merges adjacent same-font heading spans before emitting `ParagraphUnit`
    headings. This fixes real split-heading source defects such as
    `STRATEGIES FOR` + `GOVERNMENTS`, while preserving separate headings with
    different font sizes.
  - Focused tests cover merge and non-merge cases in
    `tests/test_pdf_text_layer_logical_import.py`.
  - Comparison-only proof run:
    `20260603T_pr_i2_heading_span_merge_proof`.
  - Diagnostic delta artifact:
    `.run/diagnostics/pr_i2_heading_span_merge_proof_delta.json`.
  - Result vs `20260602T_pr_i1c_current_verifier_variance_proof`:
    `false_fragment_heading_count 15 -> 11`,
    worst `unmapped_source 56 -> 53`,
    worst `unmapped_target 48 -> 47`,
    worst heading-role unmapped `12 -> 8`,
    images stayed `12/12`,
    cleanup stayed safe (`failed_chunk_count=0`, `deleted_char_ratio=0.0`).
  - Caveat: the run remains comparison-only non-acceptance evidence:
    formatting/unmapped/false-fragment checks still fail, and the reader
    verifier returned `execution_failed`. The fix is accepted as a source
    quality improvement, not as PR-I2 completion.
- PR-I2 false-fragment gate narrowing, 2026-06-03:
  - Local implementation in `src/docxaicorrector/pipeline/late_phases.py`
    keeps `false_fragment_headings_present` on entry-aware assembly evidence
    whenever any source-backed registry entry exists, even if the assembly also
    contains fallback entries. The previous whole-document fallback to
    `legacy_markdown` made one fallback block invalidate source-backed heading
    evidence for the entire gate.
  - This does not mutate Markdown/DOCX and does not add cleanup heuristics. It
    only prevents stale line-based markdown checks from flagging source-backed
    chapter/section headings after text-layer import.
  - Focused test:
    `tests/test_document_pipeline.py::test_build_translation_quality_report_keeps_entry_authority_with_mixed_fallback_entries`.
- PR-I2 TOC/list aggregation coverage, 2026-06-03:
  - Local implementation in
    `src/docxaicorrector/generation/formatting_transfer.py` recognizes
    high-confidence source entries aggregated into an already mapped target
    paragraph for bounded TOC/list cases. These source entries are counted as
    covered in formatting diagnostics instead of remaining unmapped.
  - This is still diagnostic/lineage coverage, not broad style guessing: it
    requires generated registry text to be present inside the mapped target and
    is limited to TOC/list-shaped source paragraphs.
  - Focused test:
    `tests/test_format_restoration.py::test_mapping_treats_toc_entries_aggregated_into_mapped_target_as_covered`.
- PR-I2 comparison proof attempt, 2026-06-03:
  - Attempted proof labels:
    `20260603T_pr_i2_gate_aggregation_proof` and
    `20260603T_pr_i2_gate_aggregation_proof_v2`.
  - Both runs failed before DOCX rebuild / formatting diagnostics on translation
    block 36 with persistent `empty_response`.
  - Therefore there is no valid delta yet for the gate narrowing or TOC/list
    aggregation coverage on the full chapter-region profile:
    `translation_quality_report_path=None`, `formatting_diagnostics_count=0`,
    `docx_path=None`, and `reader_verifier_status=not_run`.
  - Treat this as a proof-path reliability blocker, not as evidence against the
    PR-I2 formatting changes. Do not launch another identical run until the
    block-36 empty-response path is stabilized, cached, or retried through a
    known-good model/run profile.
- PR-R0 translation empty-response reliability, 2026-06-12:
  - Completed locally as reliability prerequisite for product proof.
  - Local implementation in `src/docxaicorrector/generation/_generation.py`
    makes recovery-time blank markdown explicit: if the post-retry recovery call
    returns an empty string without raising, it is converted into
    `empty_response` so the existing controlled source-block fallback can keep
    the pipeline moving and log `markdown_empty_response_source_fallback`.
  - Focused tests in `tests/test_generation.py` cover persistent empty response,
    blank recovery output, and incomplete response fallback.
  - Proof `20260612T_pr_r0_empty_response_recovery_proof` completed the
    chapter-region comparison profile after the previous block-36 reliability
    failures. It produced final raw/cleaned Markdown plus DOCX artifacts,
    `output_docx_openable=True`, `output_inline_shapes=12`,
    `output_contains_placeholder_markup=False`, `reader_cleanup_failed_chunk_count=0`,
    and verifier `cleaned_better` / high confidence.
  - The proof reclassifies the active blocker: translation reliability no longer
    prevents inspection. Remaining failure is product formatting/mapping:
    comparison-only acceptance failed only
    `formatting_diagnostics_threshold`, `unmapped_source_threshold`, and
    `unmapped_target_threshold` (`52` worst unmapped source vs threshold `12`,
    `48` unmapped target vs threshold `6`). PR-I2 should continue from these
    mapping diagnostics; do not launch another identical reliability proof.
  - Manual verifier audit, 2026-06-12: do not treat verifier output as ground
    truth without artifact inspection. Confirmed real reader-visible defects in
    the proof output include numbered headings fused with body text (`10. КАК
    ЭТО РАБОТАЕТ...`, `11. РЕШЕНИЕ КРИЗИСА...`), paragraph continuations after
    image/caption boundaries, and one large untranslated English source fallback
    block. Confirmed verifier/report noise includes negated safety summaries
    being counted as risks (`No false deletions...`, `No regressions...`) and at
    least one stale line reference for an embedded-heading finding. The
    validation harness now hardens the reader-verifier prompt/parser so absence
    statements in `possible_false_deletions` / `readability_regressions` become
    empty lists instead of false safety risks.
  - Verifier contract clarification, 2026-06-13: the LLM reader verifier is
    advisory-only and must not be a source of acceptance truth. In
    `20260612T_pr_i2a_aggregation_coverage_proof` it returned
    `verifier_status=failed`, `overall_verdict=unclear`,
    `cleaned_audit_verdict=unclear`, and `confidence=low`, while the pipeline
    and deterministic diagnostics still produced usable proof evidence. This
    matches earlier evidence where verifier execution failed or gave high
    confidence to a weaker result. Gate truth is deterministic:
    `unmapped_*`, `accepted_aggregated_*`, image counts, false-fragment counts,
    and explicit artifact inspection. Verifier output may contribute issue
    categories and anchors, but its verdict/confidence must not pass or fail a
    PR.
- PR-I2a aggregation-coverage restore, 2026-06-12:
  - Active slice name: **Aggregation-Coverage Final Formatting Restore**.
  - Corrected diagnosis: id-first matching is already implemented and dominates
    the proof (`paragraph_id_registry=62`, `image_anchor=12` in the final pass).
    The remaining `52/48` mapping failure is not primarily missing identity; it
    is N-to-1 / 1-to-N granularity drift after translation and reader cleanup.
  - The current mapper accepted `0` aggregated sources in the PR-R0 proof even
    though cleanup lineage already had `merged_paragraph_ids` for TOC/front
    matter groups such as `p0015 -> p0015..p0024`. Those sources were therefore
    reported as unmapped even when the target paragraph visibly contained the
    combined generated text.
  - Local implementation in
    `src/docxaicorrector/generation/formatting_transfer.py` adds a bounded
    registry-aggregation anchor mapping: if a generated registry entry has
    `merged_paragraph_ids` and its generated text is contained in one nearby
    target paragraph with high coverage, that target can be mapped as
    `paragraph_id_registry_aggregation_anchor`. The merged ids are then emitted
    as `accepted_aggregated_sources` and counted as covered diagnostics instead
    of raw unmapped source loss.
  - Gate wiring follow-up in `src/docxaicorrector/validation/structural.py`:
    `accepted_aggregated_sources` now contributes to unit-aware effective
    coverage. Its source units are removed from
    `structure_unit_unmapped_source_count`, and accepted aggregation target
    indexes can remove corresponding units from
    `structure_unit_unmapped_target_count`. `late_phases.py` carries
    `accepted_aggregated_source_unit_count` and
    `accepted_aggregated_target_index_count` into the translation quality report
    so real-document acceptance sees the same effective coverage as formatting
    diagnostics.
  - Legacy-path wiring follow-up: chapter-region currently reports
    `unmapped_source_count_basis=legacy_paragraph`, so topology-only subtraction
    would be unreachable. The same accepted aggregation coverage now applies
    before the topology early-return as `accepted_aggregation_legacy`: raw
    counts remain visible, but `structure_unit_unmapped_*` carries the
    aggregation-adjusted effective counts and the real-document acceptance
    runner treats that basis like topology-unit effective coverage.
  - This is lineage/diagnostic coverage, not cleanup or style guessing. It does
    not add reader-cleanup operations, does not mutate validation/verifier, and
    does not infer formatting from plain cleaned Markdown.
  - Focused tests:
    `tests/test_format_restoration.py::test_mapping_treats_toc_entries_aggregated_into_mapped_target_as_covered`
    and
    `tests/test_format_restoration.py::test_mapping_accepts_registry_aggregate_anchor_when_target_has_extra_context`;
    gate wiring test:
    `tests/test_real_document_validation_corpus.py::test_derive_unit_aware_unmapped_fields_counts_accepted_aggregation_as_effective_coverage`;
    legacy-path gate tests:
    `tests/test_real_document_validation_corpus.py::test_derive_unit_aware_unmapped_fields_applies_accepted_aggregation_without_topology_projection`
    and
    `tests/test_real_document_pipeline_validation.py::test_evaluate_lietaer_acceptance_prefers_accepted_aggregation_legacy_basis_over_raw_counts`.
  - PR-I2a proof, 2026-06-12:
    `20260612T_pr_i2a_aggregation_coverage_proof` completed the chapter-region
    comparison profile. Pipeline result was `succeeded`; reader/output
    artifacts were produced; final formatting diagnostics still failed
    `formatting_diagnostics_threshold`, `unmapped_source_threshold`, and
    `unmapped_target_threshold`.
  - Observed metrics:
    - pre-cleanup restore pass: `mapped=83`, `unmapped_source=36`,
      `unmapped_target=28`, `accepted_aggregated_sources_count=16`;
    - post-cleanup/final restore pass: `mapped=80`, `unmapped_source=38`,
      `unmapped_target=42`, `accepted_aggregated_sources_count=17`;
    - final-pass mapping strategies included `image_anchor=12`,
      `paragraph_id_registry=66`, `paragraph_id_registry_similarity=1`, and
      `paragraph_id_registry_aggregation_anchor=1`.
  - Interpretation correction: the proof did **not** activate
    `accepted_aggregation_legacy` as the authoritative basis. The accepted
    aggregated ids mostly described source components that were no longer in
    `unmapped_source_ids`; therefore legacy subtraction had nothing to remove
    on this document. This is not the previous "topology-only branch not
    reached" bug; it is a sharper finding that TOC/front-matter aggregation is
    now mostly covered before the legacy gate, while the remaining gate failure
    is dominated by residual body/list/heading N-to-M drift.
  - Attribution correction: the observed improvement (`52 -> 38/36` source
    unmapped depending on acceptance/report view) came from matcher-side
    coverage such as `paragraph_id_registry_aggregation_anchor`, not from the
    legacy-basis subtraction path. Keep the subtraction code as a safety net for
    future payloads where accepted ids still intersect unmapped ids, but do not
    credit it for this proof.
  - PR-I2a result: partial improvement and useful diagnostics, but not PR-I2
    closeout. Compared with the PR-R0 proof baseline (`52` source / `48`
    target worst unmapped), final source unmapped improved to `38`, but target
    unmapped stayed high at `42`, and both remain above thresholds (`12` and
    `6`). Do not repeat this same proof expecting the gate to turn green; the
    next slice must attack residual body/list/heading granularity coverage or
    narrow the gate semantics to distinguish real formatting loss from
    intentionally shared/aggregated targets.
  - PR-I2a follow-up local slice, 2026-06-12: bounded shared-target coverage for
    `image + adjacent heading` paragraphs. If a source image placeholder maps
    to a target paragraph that also contains the generated text for the next
    source heading, the image source maps as `image_anchor_contained` and the
    heading is recorded as `accepted_aggregated_sources` with kind
    `image_heading_shared_target`. This does not promote the mixed target to a
    Word heading and does not cover arbitrary body text; it only prevents a
    proven adjacent heading from being counted as lost when the rebuild path
    emits `[[DOCX_IMAGE_img_NNN]] Chapter...` as one paragraph.
  - Scope correction: `image_anchor_contained` /
    `image_heading_shared_target` is a narrow fallback for already-blended
    rebuild targets, not the main PR-I2 direction. Do not grow this into a
    family of text-containment heuristics. The next main slice should move
    upstream: carry explicit cleanup/assembly split-merge relations and
    `origin_paragraph_ids` into final formatting restore so N-to-M coverage is
    based on recorded structural facts rather than substring thresholds.
  - Commit hygiene: `tests/artifacts/real_document_pipeline/run_lietaer_validation.py`
    currently contains both PR-I2a acceptance-basis wiring and verifier
    hardening. Stage it by hunk: basis handling for
    `accepted_aggregation_legacy` belongs to PR-I2a; verifier prompt/parser
    changes belong to the separate verifier-hardening workstream.

First implementation target:

1. Enrich formatting diagnostics enough to explain unmapped source/target with
   previews, role, paragraph id, mapping strategy, and whether the failure is
   TOC/list aggregation, heading split/merge, image placeholder gap, or body
   paragraph drift.
   - Status: local diagnostic payload enrichment added. Runtime formatting
     diagnostics now include `mapping_strategy_counts`,
     `unmapped_source_role_counts`, `unmapped_source_samples`, and
     `unmapped_target_samples`.
2. Only then apply formatting transfer for high-confidence mapped paragraphs:
   headings/subheadings, list styling/numbering, bold/italic/emphasis,
   superscript/subscript, hyperlinks, and line/page breaks only where source
   evidence exists.
   - Status: first bounded coverage for TOC/list target aggregation is local;
     it reduces unmapped-source noise when source entries are visibly contained
     in an already mapped target paragraph. Style application for those
     aggregated targets remains a separate guarded step.
3. Reclassify or narrow the stale `false_fragment_headings_present` gate if the
   samples are valid text-layer headings rather than reader-breaking fragments.

Next implementation plan after PR-I2a:

1. **PR-I2b. Relation/Residual Diagnostic Probe**
   - Goal: do **not** implement new coverage yet. Prove what the remaining
     `38/42` actually is after PR-I2a and prevent another matcher-side slice
     from chasing the wrong layer.
   - Current empirical facts from the PR-I2a proof/review:
     `relation_ids=0/135`, so relation-backed formatting restore has no recorded
     structural facts to consume today; and the residual source failures are
     mostly single-origin lost matches (`29/38`) rather than true N-to-M
     aggregation (`9/38`).
   - Diagnostic sub-slice:
     - report `relation_id_populated_count` / total source units;
     - split residual unmapped sources into `single_origin_lost_match`,
       `true_aggregate_unmapped`, `image_or_placeholder_accounted_elsewhere`,
       and `real_uncovered`;
     - report whether each single-origin source still has a stable
       `paragraph_id` / generated-registry entry and whether the target miss is
       caused by text reshaping, cleanup rewrite, or missing target text;
     - trace id survival across the handoff stages for the residual
       single-origin failures:
       source `paragraph_id` -> translation marker/generated registry ->
       cleanup block identity (`paragraph_id` / `merged_paragraph_ids`) ->
       rebuilt Markdown/DOCX restore diagnostics. The probe must name the first
       stage where the hard id is no longer available, so PR-I2c knows where to
       insert the rebuild-only sidecar rather than guessing;
     - keep `image_anchor_contained` / `image_heading_shared_target` as narrow
       fallback diagnostics only.
   - Expected result: likely negative for relation-backed coverage. That is a
     valid PR-I2b outcome because it proves the next fix belongs upstream in the
     cleanup/rebuild handoff, not in another substring matcher.
   - Acceptance: no style application changes, no new substring thresholds, no
     verifier gate, no document-specific literals, and a clear residual table
     that can drive PR-I2c.
   - Local implementation, 2026-06-13:
     `formatting_transfer.py` now emits diagnostic-only
     `relation_identity_population` and
     `unmapped_source_residual_diagnostics` in restore diagnostics. The residual
     diagnostics classify unmapped sources into `single_origin_lost_match`,
     `true_aggregate_unmapped`, `image_or_placeholder_accounted_elsewhere`, and
     `real_uncovered`, and record `first_missing_identity_stage` for sampled
     sources. This does not change mapping, style application, DOCX rebuild, or
     acceptance thresholds.
   - Focused test:
     `tests/test_format_restoration.py::test_formatting_diagnostics_classify_residual_unmapped_identity_gaps`.
   - Next proof readout: inspect the latest restore diagnostics from the
     chapter-region profile and verify whether `relation_id_populated_count`
     remains near zero and whether `single_origin_lost_match` dominates the
     residual. If yes, proceed to PR-I2c; if true aggregates dominate instead,
     revisit relation population before hard-id work.
   - PR-I2b proof, 2026-06-13:
     `20260613T_pr_i2b_residual_probe` completed the chapter-region
     comparison-only profile. It produced two restore diagnostics:
     - pre-cleanup restore diagnostics: `source=135`, `target=111`,
       `mapped=84`, `unmapped_source=28`, `unmapped_target=27`,
       `relation_id_populated_count=0/135`, residual
       `single_origin_lost_match=18`, `true_aggregate_unmapped=10`,
       `first_missing_identity_stage=rebuilt_docx_restore_match_missing` for
       all residual samples;
     - post-cleanup/final restore diagnostics: `source=135`, `target=123`,
       `mapped=76`, `unmapped_source=41`, `unmapped_target=47`,
       `relation_id_populated_count=0/135`, residual
       `single_origin_lost_match=30`, `true_aggregate_unmapped=11`,
       `first_missing_identity_stage=rebuilt_docx_restore_match_missing` for
       all residual samples.
     Acceptance still fails only deterministic formatting thresholds:
     `formatting_diagnostics_threshold=41`, `unmapped_source_threshold=41 > 12`,
     `unmapped_target_threshold=47 > 6`.
   - PR-I2b decision: the diagnostic probe confirms the plan correction.
     Relation-backed restore cannot be the next main fix because relation facts
     are empty (`0/135`), and the final-pass residual is dominated by
     single-origin lost matches (`30/41`) whose source id and generated-registry
     entry exist but are not available as hard keys in rebuilt DOCX restore.
     Proceed to PR-I2c.
2. **PR-I2c. Ordered Rebuild-Text Sidecar For Restore**
   - Goal: improve the reader-cleanup rebuild handoff by carrying rebuild-only
     target paragraph indexes from ordered exact-text alignment inside the
     cleaned/generated Markdown domain.
   - Architectural caveat: this is not a true embedded paragraph-id marker
     through rebuild. The final restore consumes a sidecar key, but the sidecar
     binding is still established by ordered normalized-text equality between
     generated-registry text and rebuilt Markdown blocks. A future true id-marker
     path must carry `paragraph_id` through rebuild without text equality.
   - Scope:
     - preserve `paragraph_id` / source identity for cleanup blocks and rebuilt
       Markdown/DOCX paragraphs on a rebuild-only sidecar path;
     - extend the existing identity infrastructure
       (`_build_reader_cleanup_block_identity_metadata`,
       cleanup-block `paragraph_id`, `merged_paragraph_ids`, generated registry)
       instead of introducing a parallel id system;
     - define split/merge propagation explicitly: split operations carry the
       parent id into child identity metadata, while merge operations carry an
       ordered `origin_paragraph_ids` / `merged_paragraph_ids` list;
     - keep reader-facing Markdown and final DOCX free of visible internal
       markers;
     - support cleanup disabled, cleanup noop, and cleanup changed paths;
     - target the dominant residual first: single-origin lost matches.
   - Non-goals: do not add cleanup operations, do not tune the LLM prompt, do
     not infer identities with broad containment rules, and do not apply styles
     to mixed/shared targets until relation facts are explicit.
   - Acceptance: single-origin lost-match count drops materially, images remain
     `12/12`, final DOCX remains openable, deterministic unmapped metrics
     improve, mapping strategy shifts from text-derived recovery toward
     id-key recovery for the formerly unmapped single-origin set, and there are
     zero new false matches among the already mapped source paragraphs.
   - Follow-up for true aggregates: populate explicit relation facts during
     assembly/cleanup before attempting relation-backed formatting coverage.
   - Local implementation, 2026-06-13:
     `_rebuild_docx_for_markdown` now builds a rebuild-only formatting registry
     by attaching exact ordered `target_paragraph_indexes` to generated registry
     entries before formatting restore. `formatting_transfer.py` uses those
     indexes as `paragraph_id_rebuild_key` before later text-based matching,
     only when a primary paragraph id has exactly one valid, still-free target
     index. The sidecar is not written to reader-facing Markdown, not sent to
     the model, and not persisted into the final DOCX.
   - Post-review hardening, 2026-06-13:
     the ordered alignment now uses a local candidate pointer and commits the
     shared `search_start_index` only after a full multi-block entry match, so a
     partial failed entry cannot cascade-skip later registry entries. Restore
     diagnostics also report `rebuild_key_mapping_quality`, a diagnostic-only
     false-map check for suspicious rebuild-key role/style mismatches.
   - Focused tests:
     `tests/test_format_restoration.py::test_formatting_diagnostics_use_rebuild_identity_key_before_text_matching`;
     `tests/test_document_pipeline.py::test_rebuild_identity_formatting_registry_attaches_target_indexes_without_visible_markers`;
     `tests/test_document_pipeline.py::test_rebuild_docx_for_markdown_prefers_cleanup_formatting_registry_override`.
   - PR-I2c proof, 2026-06-13:
     `20260613T_pr_i2c_rebuild_identity_key_proof` completed the chapter-region
     comparison-only profile after adding an advisory reader-verifier timeout.
     The timeout fix is harness-only: if the LLM verifier stalls, the deterministic
     report still finishes with `reader_verifier_status=failed` and
     `verifier_reason=execution_timeout`; verifier output remains advisory and is
     not an acceptance gate.
   - Proof result:
     - final restore diagnostics improved from PR-I2b `mapped=76`,
       `unmapped_source=41`, `unmapped_target=47` to PR-I2c `mapped=89`,
       `unmapped_source=29`, `unmapped_target=36`;
     - final `mapping_strategy_counts` now include
       `paragraph_id_rebuild_key=73`, proving the rebuild sidecar path is
       reached by the real document path rather than only by unit tests;
     - residual final unmapped source categories shifted from
       `single_origin_lost_match=30`, `true_aggregate_unmapped=11` to
       `single_origin_lost_match=25`, `true_aggregate_unmapped=3`,
       `real_uncovered=1`;
     - images remain stable through the run (`12/12` image anchors in restore
       strategy and final DOCX image reinsertion remains available);
     - acceptance still fails deterministic formatting gates:
       `formatting_diagnostics_threshold=29`, `unmapped_source_threshold=29 > 12`,
       `unmapped_target_threshold=36 > 6`.
   - PR-I2c decision: the ordered rebuild-text sidecar is the correct layer for
     this partial improvement and should be kept, but it does not close PR-I2 and
     should not be described as eliminating text-determinism. The remaining
     blocker is mixed residual coverage: single-origin targets that still lack
     rebuild-key coverage, true aggregate relations that need explicit relation
     facts, and target-side over-fragment / merge cases. Do not add more
     text-containment matching as the next step.
     Continue with PR-I2d, the closable-vs-dissolved residual classifier, which
     decides whether the embedded id-marker (PR-I2e) is worth building before any
     style application (PR-I2f).
3. **PR-I2d. Closable-vs-Dissolved Residual Classifier (diagnostic-only)**
   - Rationale: PR-I2c proved the rebuild sidecar reaches the real path
     (`paragraph_id_rebuild_key=73`) but left `single_origin_lost_match=25`,
     `true_aggregate_unmapped=3`, `real_uncovered=1` and still fails thresholds
     (`29 > 12`, `36 > 6`). More ordered text-alignment will not move these: by
     definition they are where in-domain text equality already failed. The next
     dollar of work must go into a true embedded `paragraph_id` marker — but that
     is an expensive layer (carry id through cleanup split/merge -> invisible
     attribute in rebuild -> read back at restore), and part of the residual may
     have no 1:1 target at all. Do not start the marker before classifying.
   - Goal: split the residual (`25` single-origin + `3` aggregate + `1`
     real_uncovered) into three actionable classes, diagnostic-only, no style
     application, no new substring thresholds, no mapping change:
     - `target_exists_text_align_missed`: a corresponding target paragraph exists
       (e.g. `target_candidate_indexes_containing_registry_text` is non-empty)
       but ordered text equality missed it. **Closable by a true embedded
       id-marker.** This is the only class that justifies the marker.
     - `target_occupied_by_mapped_neighbor`: registry text is present, but only
       in a target already mapped to a neighboring source. This is not
       marker-closable as a new 1:1 target.
     - `target_absent_or_unproven`: no free target candidate and no bounded
       mapped-neighbor evidence. This remains unproven absence until I2g or a
       future full proof provides stronger coverage evidence.
     - `true_aggregate_relation_gap`: needs explicit relation facts populated
       upstream first (`relation_ids=0/135` today), not a new matcher.
   - Decision gate (the whole point of I2d): only begin the embedded-id-marker
     work if `target_exists_text_align_missed` is a material fraction of the
     residual. If the residual is dominated by `dissolved`, the marker is wasted
     effort and the honest next step is a documented product limitation plus
     relation population for the aggregates.
   - Acceptance: a residual classification table in restore diagnostics, no DOCX
     behavior change, no style application, no verifier gate, no document-specific
     literals.
   - Local implementation, 2026-06-13:
     restore diagnostics now include
     `unmapped_source_residual_diagnostics.residual_closability_diagnostics`.
     The live diagnostic classifies the full unmapped source set and reports the
     embedded-marker upper bound as the count of
     `target_exists_text_align_missed`. The helper
     `scripts/classify-formatting-residuals.py` can classify an existing report
     without rerunning the pipeline; for old I2c reports this is explicitly
     `sample_based` because those artifacts saved only residual samples.
     Post-review hardening refined the marker upper bound to count only
     candidates on unmapped/free target paragraphs; candidates already occupied
     by mapped targets are not marker-closable. Running the helper on
     `tests/artifacts/real_document_pipeline/lietaer_pdf_chapter_region_report.json`
     selected the final restore diagnostics and produced the current
     sample-based split: `target_exists_text_align_missed=7`,
     `target_absent_or_unproven=14`, `true_aggregate_relation_gap=3`,
     `real_uncovered=1`; `embedded_marker_upper_bound_count=7`.
4. **PR-I2g. Role-Aware Effective Formatting Coverage Diagnostic**
   - Rationale: content survival is not the same as formatting survival. A body
     paragraph dissolved into a neighboring body target can be format-neutral,
     but a heading/list dissolved into a body target is still a formatting loss.
   - Goal: add diagnostic-only effective counts that separate raw unmapped
     source count from role-aware formatting coverage:
     - use containment only as evidence/measurement, never as a new mapping or
       style-application rule;
     - count `proven_dissolved` only when registry text is contained in an
       already mapped neighboring target within a bounded source window;
     - credit only format-neutral cases, currently body source -> body target;
     - keep heading/list/caption/toc dissolved into body as formatting loss even
       when text survived.
   - Local implementation, 2026-06-13:
     live diagnostics now include
     `unmapped_source_residual_diagnostics.effective_formatting_coverage_diagnostics`
     with `evidence_basis=registry_text_contained_in_already_mapped_neighbor_target`,
     `source_neighbor_window=3`, role-credit rule text, per-class counts, and
     `format_neutral_creditable_count`. The offline helper reports the same
     sample-based effective counts for old reports. On the current I2c report,
     sample-based effective credit is `0`; the old artifact has no proven
     body->body neighbor containment in saved samples.
   - Acceptance: no DOCX behavior change, no mapping change, no style
     application; a future proof run can answer whether the deterministic gate
     is failing because of real formatting loss or because it still expects 1:1
     body mappings after legitimate N-to-M translation.
5. **PR-I2h. Fuzzy Coverage Evidence Collector (measurement-only)**
   - Rationale: exact containment is a weak evidence collector for translated
     text. `target_absent_or_unproven` can mean "content lost", but it can also
     mean "content survived after paraphrase/boundary shift and exact substring
     failed". Do not run a full LLM proof just to rediscover this limitation.
   - Goal: strengthen coverage measurement without changing mapping, styling, or
     DOCX output:
     - keep exact containment as strongest evidence;
     - add token-overlap / sequence-similarity evidence between registry text and
       already mapped neighboring targets;
     - keep the bounded source-neighbor window and role-aware credit from I2g;
     - never use fuzzy evidence to assign `paragraph_id_rebuild_key` or apply
       formatting.
   - Local implementation, 2026-06-13:
     live diagnostics and `scripts/classify-formatting-residuals.py` now use
     `registry_text_exact_or_fuzzy_overlap_in_already_mapped_neighbor_target`.
     The fuzzy rule requires exact containment, or token overlap `>=0.62` with
     at least `4` common tokens, or token overlap `>=0.8` with at least `2`
     common tokens, or sequence ratio `>=0.75` for longer text. Evidence samples
     record `evidence_type`, score, token overlap, sequence ratio, and token
     counts. Focused tests prove body->body fuzzy evidence is creditable while
     heading->body fuzzy evidence remains formatting loss.
   - Current old-report replay:
     running the helper on
     `tests/artifacts/real_document_pipeline/lietaer_pdf_chapter_region_report.json`
     still reports `format_neutral_creditable_count=0` and
     `embedded_marker_upper_bound_count=7`. This is sample/preview-based for the
     old artifact, so it is a conservative offline signal rather than a full
     proof. The next expensive proof should wait until behavior or gate semantics
     changes, not merely to collect deterministic diagnostics.
6. **PR-I2e. True Embedded Id-Marker (only if PR-I2d/I2g/I2h justify it)**
   - Conditional on PR-I2d showing a material `target_exists_text_align_missed`
     fraction after excluding occupied targets, and on PR-I2g/I2h showing that
     marker work is more valuable than role-aware gate semantics/relation
     population.
     Carry `paragraph_id` through cleanup split/merge into the rebuild as an
     invisible attribute and read it back at restore, removing text equality from
     the binding (the thing PR-I2c did *not* do). Reuse the existing cleanup
     identity infrastructure; do not add a parallel id system.
7. **PR-I2f. Formatting Application On Proven Relations**
   - Start only after identity/relations are reliable (PR-I2e and/or explicit
     relation facts for true aggregates).
   - Apply heading/list/caption/run styling only where the relation is
     unambiguous and the target is not a mixed paragraph that a single Word style
     would corrupt.
8. **PR-CLEANUP0**
   - Keep blocked until PR-I2b/PR-I2c/PR-I2d/PR-I2g/PR-I2h/PR-I2e/PR-I2f define which runtime
     surfaces are actually unused. Verifier config can be marked validation-only,
     but do not delete proof harnesses or safety guards while formatting restore
     is still moving.
   - Status: real split-heading continuation defects are partially reduced by
     the source fix above. Remaining samples still include legitimate chapter/
     section headings, so the gate now prefers unit-aware evidence when
     source-backed entries are available, even in mixed fallback assemblies.

Non-goals:

- No new reader-cleanup operations.
- No document-specific literals.
- No guessing styles from cleaned Markdown without source paragraph evidence.
- No broad rewrite of final assembly.

### PR-CLEANUP0. Dormant Runtime Surface Removal (after PR-I1c)

Status: not started. Unblocked by PR-I1c-ACCEPT only for deprecation/cleanup
planning, not for aggressive deletion. Do not delete runtime cleanup surface
from the claim that PR-I1c fully proved the contract; it did not. Remove or
deprecate only surfaces unused by the explicitly accepted working contract, and
prefer PR-I2 first because formatting preservation is the active product
blocker.

Problem:

- Several cleanup-adjacent surfaces are effectively dormant in the shipping
  configuration but still carry runtime cost, code surface, and false "feature
  exists" signals:
  - global plan pass (`reader_cleanup_global_plan_enabled` default `false`,
    advisory-only, extra LLM call);
  - anchor repair pass (`reader_cleanup_anchor_targets` default empty, extra LLM
    pass plus a separate chunk builder);
  - `reader_verifier_*` runtime config (`reader_verifier_enabled` /
    `reader_verifier_model`): the scoring logic lives only in the validation/
    replay harness under `tests/artifacts/real_document_pipeline/`, not in
    `src/`. In runtime these fields gate nothing.

Goal:

- Remove dormant runtime surface only after the selected cleanup contract is
  accepted with explicit evidence class, so the runtime cleanup component
  matches its real responsibility.

Slice order (deprecate before delete; no abrupt removal):

1. Mark `reader_verifier_*` runtime config as validation-only / deprecated
   (documentation + config comment), keeping the harness behavior unchanged.
   Do not delete the config surface in the same slice.
2. After the PR-I1c caveat is resolved and a cleanup contract is accepted,
   remove from the **runtime** path whatever the contract does not use:
   - global plan pass, if unused by the selected contract;
   - anchor repair pass, if unused by the selected contract;
   - the deprecated `reader_verifier_*` runtime config fields.
   Keep global plan / anchor repair / verifier available in the replay/
   validation harness if they still have diagnostic value there.
3. Remove genuinely unreachable cleanup operations in the engine only if the
   selected contract excludes them and tests confirm they are unreachable in
   runtime.

Acceptance:

- Runtime cleanup config surface contains only fields that actually gate runtime
  behavior under the selected contract.
- `reader_verifier_*` is either removed from runtime or clearly documented as
  validation-only, with no runtime code implying it gates production output.
- Removed passes remain available in the validation/replay harness where they
  still provide evidence.
- Full pytest suite stays green via the canonical path.

Non-goals:

- No removal of safety gates (`max_delete_*`, protected-block guards); those are
  cheap and protect against content loss.
- No removal of legacy `.doc` LibreOffice support; that is a separate input
  path.
- No engine-wide refactor of the first-pass cleanup beyond removing operations
  the selected contract provably excludes.

## Stop Rules

- Stop if source-import logic starts duplicating the full DOCX formatting
  restoration system.
- Stop if a rule relies on a literal string from one book.
- Stop if text-layer extraction cannot preserve enough reading order evidence;
  then compare another candidate rather than piling on heuristics.
- Stop before promotion if the new importer improves one document but regresses
  headings/lists/body order on another book-like PDF.
