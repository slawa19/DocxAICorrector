"""Why does the bibliography-tail exclusion never fire? Probe the anchor, not the region.

`_resolve_bibliography_tail_indexes` anchors on the LAST heading-like block in the document and
only then looks for a bibliography-like suffix. This prints, per book: where that anchor lands,
what follows it, and which of the trailing blocks would individually read as bibliography-like —
enough to tell "the region is not identifiable" apart from "the anchor is in the wrong place".

Offline, no LLM. Same invocation as scripts/measure-narration-exclusion.py.
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
    _is_bibliography_like_block,
    _is_bibliography_like_line,
    _is_heading_like_block,
    _iter_block_text_lines,
    _resolve_bibliography_tail_indexes,
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

    heading_like = [
        index for index, block in enumerate(blocks) if _is_heading_like_block(block, structure_phase=PRODUCTION_STRUCTURE_PHASE)
    ]
    last_heading = heading_like[-1] if heading_like else -1
    tail_indexes = _resolve_bibliography_tail_indexes(blocks, structure_phase=PRODUCTION_STRUCTURE_PHASE)

    print(f"\n=== {source_path.name}")
    print(f"blocks={len(blocks)} heading_like_blocks={len(heading_like)} last_heading_like_index={last_heading}")
    print(f"blocks after the anchor: {len(blocks) - 1 - last_heading if last_heading >= 0 else 'n/a'}")
    print(f"resolved bibliography tail: {len(tail_indexes)} blocks")

    print(f"\nlast {tail} blocks — bib-like share per block:")
    for index in range(max(0, len(blocks) - tail), len(blocks)):
        block = blocks[index]
        lines = _iter_block_text_lines(block)
        matches = sum(1 for line in lines if _is_bibliography_like_line(line))
        share = matches / len(lines) if lines else 0.0
        flags = []
        if index == last_heading:
            flags.append("ANCHOR")
        if index in heading_like:
            flags.append("heading_like")
        if _is_bibliography_like_block(block):
            flags.append("BIB_BLOCK")
        if index in tail_indexes:
            flags.append("excluded")
        head = " ⏎ ".join(lines[:2])[:150]
        print(f"  [{index:>4}] bib={share:>5.0%} ({matches}/{len(lines)}) {','.join(flags):<28} {head}")


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
