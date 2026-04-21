# DOCX Formatting Hardening Spec

> Status: implemented on 2026-03-13. The `Current State` and `Weak areas that remain` sections below describe the pre-hardening baseline that this implementation pass was addressing.

## Goal

Improve the final edited DOCX so it is cleanly structured and visually coherent without trying to preserve the full source style zoo.

Primary target outcomes:

1. headings and subheadings survive reliably as semantic structure;
2. tables survive as actual tables instead of disappearing into plain text;
3. image captions remain attached and readable;
4. final DOCX uses a consistent, intentional formatting baseline.

## Current State

The pipeline currently does the following well enough:

1. extracts body paragraphs and inline images;
2. preserves numbered and bulleted lists with nesting;
3. preserves some inline semantics such as bold, italic, underline, sup/sub, hyperlinks, tabs;
4. restores selected paragraph XML after Pandoc conversion.

Weak areas that remain:

1. heading detection is style-name driven and too shallow;
2. tables are ignored because extraction iterates only over `document.paragraphs`;
3. captions are not treated as a first-class semantic unit;
4. final DOCX formatting is mostly an accident of Pandoc defaults plus partial source XML restoration.

## Non-Goals

This work does not aim to:

1. clone all source fonts, colors, custom styles, or section quirks;
2. preserve comments, footnotes, endnotes, headers, footers, or tracked changes;
3. become a lossless DOCX round-tripper.

## Scope

### 1. Stronger Heading Semantics

Introduce explicit heading levels instead of a flat `heading` role.

Sources for heading classification, ordered by confidence:

1. style names: `Title`, `Heading 1..6`, localized heading names;
2. `w:outlineLvl` from paragraph XML;
3. conservative heuristics for likely headings when style metadata is weak.

Planned model changes:

1. extend `ParagraphUnit` with `heading_level: int | None`;
2. render headings to markdown using `#`, `##`, `###`;
3. keep heading blocks isolated in semantic chunking;
4. attach a short following paragraph to a heading when appropriate, as already done today.

Heuristic guardrails:

1. do not classify long multi-sentence paragraphs as headings;
2. do not classify paragraphs ending with typical sentence punctuation unless strongly indicated by style/XML;
3. prefer false negatives over false positives.

### 2. Table Support

Switch extraction from `document.paragraphs` to ordered block iteration over document body children so both paragraphs and tables are preserved in reading order.

Planned extraction changes:

1. add an ordered block iterator for `w:p` and `w:tbl`;
2. represent a table as a semantic unit in the text stream;
3. render tables to Pandoc-friendly markup.

Preferred rendering strategy:

1. simple rectangular tables: markdown pipe tables when safe;
2. complex tables, merged cells, or ambiguous shapes: raw HTML tables.

Minimal preserved semantics for tables:

1. row order;
2. cell text;
3. empty cells;
4. caption proximity;
5. basic header-row detection when obvious.

Chunking rules for tables:

1. treat a table as an atomic block;
2. do not merge unrelated body paragraphs into the same chunk when a table is present;
3. keep caption paragraphs adjacent to their table block.

### 3. Caption Handling

Introduce a semantic caption role for image/table captions.

Detection sources:

1. style name `Caption` and localized variants;
2. short paragraph immediately following an image-only paragraph or table block;
3. conservative lexical hints such as `Рис.`, `Рисунок`, `Figure`, `Таблица`, `Table`.

Behavior:

1. preserve caption text as its own paragraph in markdown;
2. keep caption in the same semantic block as the adjacent image/table when possible;
3. apply a consistent caption style in the final DOCX post-processing pass.

### 4. Clean Final DOCX Styling

Add a dedicated output styling pass instead of relying only on Pandoc defaults.

Planned approach:

1. generate DOCX through Pandoc using a controlled reference DOCX;
2. apply a final normalization pass with `python-docx` after build;
3. keep existing paragraph XML restoration, but layer semantic style normalization on top where needed.

Formatting baseline to enforce:

1. consistent `Heading 1/2/3` hierarchy;
2. readable body text style;
3. normalized paragraph spacing for body, headings, captions, lists;
4. centered image paragraphs when image-only;
5. caption style for caption paragraphs;
6. table style for Pandoc-generated tables where feasible.

Important constraint:

Semantic normalization should win over accidental source style noise, but must not break list numbering, image placement, or table structure.

## Proposed Code Touchpoints

### document.py

1. replace paragraph-only traversal with ordered block traversal;
2. add heading-level detection from style and XML;
3. add table extraction/rendering helpers;
4. add caption detection helpers;
5. update semantic block builder to treat tables and captions carefully.

### models.py

1. extend `ParagraphUnit` with heading/caption/table semantics as needed;
2. keep rendered markdown logic inside model helpers where practical.

### generation.py

1. add optional Pandoc `reference-doc` usage;
2. keep conversion surface minimal and testable.

### document_pipeline.py

1. add final output normalization pass after Pandoc conversion and before image reinsertion or immediately after, depending on interaction details.

### tests

Add regression coverage for:

1. heading extraction from style and `outlineLvl`;
2. title and subheading rendering to markdown;
3. ordered paragraph/table traversal;
4. markdown or HTML table rendering;
5. caption detection near images/tables;
6. final output normalization for headings, body, captions, and images.

## Suggested Implementation Order

1. heading-level model and rendering;
2. ordered block traversal and table extraction;
3. caption semantics;
4. reference DOCX generation and output normalization pass;
5. tests and sample-DOCX regressions.

## Risks

1. heading heuristics may create false positives if too aggressive;
2. HTML table rendering may expand markdown size and affect chunking;
3. final style normalization can conflict with restored paragraph XML if precedence is not carefully chosen;
4. paragraph-count-based source-to-output mapping becomes weaker when tables or captions collapse/expand during editing.

## Acceptance Criteria

1. sample documents retain headings, lists, images, and readable structure;
2. tables appear in final DOCX as tables, not flattened text;
3. captions stay adjacent and formatted consistently;
4. final DOCX has consistent heading/body/caption spacing and does not look like raw Pandoc output;
5. focused regression tests cover these behaviors and pass.
