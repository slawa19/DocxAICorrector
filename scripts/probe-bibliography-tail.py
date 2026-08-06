"""Where does the audiobook reference-region exclusion anchor, and how far does it reach?

Spec 054. The rule this probes was rewritten on 2026-08-04. Before: it anchored on the LAST
heading-like block of the document and then required >= 70% "bibliography-like" LINES in the
suffix — which resolved to 0 blocks on 4 of 4 books, because the anchor lands on publisher
back-matter standing BEHIND the bibliography and because a PDF-imported entry wraps over
several lines of which only one carries a year/publisher/URL. After: the region is anchored on
a bare back-matter section title ("Notes", "Bibliography", "Index", ...) sitting at an edge of
its block, and bounded by the next block that has a heading paragraph of its own. The anchor
paragraph is NOT required to carry the heading role (changed 2026-08-06 — Rethinking Money's
NOTES and BIBLIOGRAPHY arrive from import as body paragraphs).

This prints, per book: every anchor found, the region it opens, and the trailing blocks — enough
to tell "the region is not identifiable" apart from "the region is identified but bounded short".

Offline, no LLM. Same invocation as scripts/measure-narration-exclusion.py:
    . .venv/bin/activate && export PYTHONPATH="$PWD/src:$PWD" \
        && python scripts/probe-bibliography-tail.py tests/sources/book/*.pdf --tail 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.core.config import load_app_config
from docxaicorrector.core.constants import DEFAULT_CHUNK_SIZE
from docxaicorrector.document.semantic_blocks import (
    _block_has_heading_paragraph,
    _block_leading_heading_level,
    _block_reference_section_title,
    _iter_block_text_lines,
    _resolve_reference_region_end,
    _resolve_reference_region_indexes,
)
from docxaicorrector.processing.preparation import (
    _build_semantic_blocks_with_optional_boundaries,
    _prepare_document_for_processing,
)

PRODUCTION_STRUCTURE_PHASE = "pre_ai_diagnostic"


def _no_llm_client(*args: object, **kwargs: object) -> object:
    raise AssertionError("probe is offline by contract")


def _app_config_mapping() -> dict[str, Any]:
    app_config = load_app_config()
    if isinstance(app_config, dict):
        return dict(app_config)
    to_dict = getattr(app_config, "to_dict", None)
    return dict(to_dict()) if callable(to_dict) else {}


def probe(source_path: Path, *, chunk_size: int, tail: int) -> None:
    source_bytes = source_path.read_bytes()
    normalized = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
    prepared = _prepare_document_for_processing(
        normalized.filename,
        normalized.content_bytes,
        chunk_size,
        source_format=normalized.source_format,
        conversion_backend=normalized.conversion_backend,
        app_config=_app_config_mapping(),
        processing_operation="audiobook",
        get_client_fn=_no_llm_client,
        client_factory=None,
    )
    # Rebuild the same blocks the job builder saw, so block indexes line up with the jobs.
    from docxaicorrector.document.segments import resolve_segment_hard_boundary_paragraph_ids

    blocks = _build_semantic_blocks_with_optional_boundaries(
        paragraphs=prepared.paragraphs,
        max_chars=chunk_size,
        relations=prepared.relations,
        hard_boundary_paragraph_ids=resolve_segment_hard_boundary_paragraph_ids(prepared.segments),
        structure_phase=PRODUCTION_STRUCTURE_PHASE,
    )

    anchors = [
        (index, title)
        for index, block in enumerate(blocks)
        if (title := _block_reference_section_title(block, structure_phase=PRODUCTION_STRUCTURE_PHASE))
    ]
    region_indexes = _resolve_reference_region_indexes(blocks, structure_phase=PRODUCTION_STRUCTURE_PHASE)

    print(f"\n=== {source_path.name}")
    print(f"blocks={len(blocks)} reference_region_blocks={len(region_indexes)}")
    if not anchors:
        print("no bare back-matter section title anchors the region — nothing excluded (accepted negative)")
    for anchor_index, title in anchors:
        end_index = _resolve_reference_region_end(blocks, anchor_index)
        chars = sum(len(blocks[i].text) for i in range(anchor_index, end_index))
        bound = (
            f"heading block {end_index} (level {_block_leading_heading_level(blocks[end_index])})"
            if end_index < len(blocks)
            else "end of document"
        )
        print(
            f"anchor [{anchor_index}] {title!r} (level {_block_leading_heading_level(blocks[anchor_index])})"
            f" -> region [{anchor_index}..{end_index - 1}] = {end_index - anchor_index} blocks,"
            f" {chars} chars (bounded by {bound})"
        )

    print(f"\nlast {tail} blocks:")
    for index in range(max(0, len(blocks) - tail), len(blocks)):
        block = blocks[index]
        lines = _iter_block_text_lines(block)
        flags = []
        if _block_reference_section_title(block, structure_phase=PRODUCTION_STRUCTURE_PHASE):
            flags.append("ANCHOR")
        if _block_has_heading_paragraph(block):
            flags.append("has_heading")
        if index in region_indexes:
            flags.append("EXCLUDED")
        head = " ⏎ ".join(lines[:2])[:150]
        print(f"  [{index:>4}] {','.join(flags):<28} {head}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--tail", type=int, default=15)
    args = parser.parse_args(argv)
    for source_path in args.sources:
        if not source_path.exists():
            print(f"!! missing: {source_path}")
            continue
        probe(source_path, chunk_size=args.chunk_size, tail=args.tail)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
