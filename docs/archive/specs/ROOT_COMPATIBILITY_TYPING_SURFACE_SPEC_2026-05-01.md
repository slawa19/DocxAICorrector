# Root Compatibility Typing Surface Specification

Date: 2026-05-01

Status: planned follow-up after safe architecture refactoring.

## Goal

Tighten the remaining root `.pyi` compatibility stubs so the type surface reflects the intended backward-compatibility contract more precisely, without breaking active root-facade behaviors that are still intentionally supported.

## Why This Exists

The safe architecture refactoring completed the package migration and preserved runtime compatibility, but a subset of root `.pyi` files still rely on:

```python
def __getattr__(name: str) -> Any: ...
```

That fallback is still needed in some places because several root facades intentionally expose compatibility names beyond a plain `from target import *` surface. The clearest current exception is `document.pyi`, whose runtime facade still supports compatibility hooks and monkeypatch targets documented in `src/docxaicorrector/document/_document.py`.

This follow-up must separate:

- true stable backward-compatibility names that deserve explicit stub declarations;
- temporary facade-only names that should remain documented until their runtime seam is retired;
- accidental fallback typing that can be removed safely.

## Scope

- Root `.pyi` files that still expose `def __getattr__(name: str) -> Any: ...`.
- Their matching runtime shims and package implementation modules.
- Tests that rely on root import compatibility or private compatibility names.

Initial high-risk files:

- `document.pyi`
- `document_extraction.pyi`
- `document_relations.pyi`
- `document_pipeline*.pyi`
- `processing_service.pyi`
- `structure_recognition.pyi`
- `structure_validation.pyi`
- `image_*.pyi`

## Non-Goals

- No runtime package migration.
- No removal of root `.py` compatibility wrappers.
- No behavioral change to document processing, UI, validation, or pipeline logic.
- No speculative tightening that is not backed by test or call-site evidence.

## Required Output

For each remaining fallback stub:

1. Classify it as one of:
   - `explicit_contract_ready`
   - `needs_manual_reexports`
   - `active_facade_exception`
2. Replace fallback typing only when the intended surface is fully known.
3. Add or update focused tests so the root stub contract is enforced explicitly.

## Known Active Exception

`document.pyi` is currently an active facade exception.

Reason:

- `src/docxaicorrector/document/_document.py` still carries explicit compatibility overrides and a deadline marker:
  - `EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE = "2026-06-30"`
- The facade exports compatibility names and monkeypatch targets such as:
  - `MAX_DOCX_ARCHIVE_SIZE_BYTES`
  - `MAX_DOCX_COMPRESSION_RATIO`
  - `MAX_DOCX_ENTRY_COUNT`
  - `MAX_DOCX_UNCOMPRESSED_SIZE_BYTES`
  - `_validate_docx_archive`
  - `_read_uploaded_docx_bytes`
  - `_document_extraction`

This file must not be tightened by replacing fallback typing with wildcard exports alone.

## Verification

At minimum:

```bash
bash scripts/test.sh tests/test_root_typing_stubs.py -q
bash scripts/test.sh tests/test_document_extraction.py -q
bash scripts/test.sh tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_processing_service.py -q
bash scripts/test.sh tests/test_structure_validation.py -q
```

Add narrower selectors for each stub family as explicit contracts are introduced.

## Done Criteria

This follow-up is complete when:

1. Every remaining fallback root stub is classified and documented.
2. Any stub moved out of fallback mode has explicit declarations for its supported compatibility surface.
3. `document.pyi` is either still documented as an active compatibility exception or its extraction-compatibility seam has been removed in the same batch.
4. Root typing-stub tests fail on drift for all tightened stubs.
