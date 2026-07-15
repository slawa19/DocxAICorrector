"""Characterization golden for reader_cleanup_mvp.service.

Safety net for the behaviour-preserving decomposition of service.py (spec 032).
Runs fully offline with deterministic fake providers that return canned JSON
keyed on the inspected chunk payload. Snapshots:

- the whole ``result.cleaned_markdown`` and a canonical (elapsed-scrubbed,
  sorted-key) dump of ``result.report_payload`` for three representative
  fixtures (multi-chunk cleanup, reannotation, anchor-repair);
- the four ``build_reader_cleanup*_system_prompt`` output strings;
- ``build_cleanup_blocks`` block ids and text hashes for a fixed input.

Regenerate all goldens with ``UPDATE_READER_CLEANUP_GOLDEN=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from docxaicorrector.reader_cleanup_mvp.service import (
    ReaderCleanupConfig,
    build_cleanup_blocks,
    build_reader_cleanup_global_plan_system_prompt,
    build_reader_cleanup_reannotation_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
    run_reader_cleanup,
    run_reader_cleanup_anchor_repair,
    run_reader_cleanup_reannotation,
)

_GOLDEN_DIR = Path(__file__).parent / "fixtures" / "reader_cleanup_service_characterization"
_UPDATE = os.environ.get("UPDATE_READER_CLEANUP_GOLDEN") == "1"


def _scrub(value: Any) -> Any:
    """Recursively replace non-deterministic ``elapsed_ms`` timings."""
    if isinstance(value, dict):
        return {
            key: ("<elapsed_ms>" if key == "elapsed_ms" else _scrub(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub(item) for item in value]
    return value


def _canonical_json(payload: Any) -> str:
    return json.dumps(_scrub(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _assert_or_update(name: str, actual: str) -> None:
    path = _GOLDEN_DIR / name
    if _UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
        return
    assert path.exists(), f"Missing golden {path}; regenerate with UPDATE_READER_CLEANUP_GOLDEN=1"
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"Golden drift in {name}; regenerate with UPDATE_READER_CLEANUP_GOLDEN=1"


# ---------------------------------------------------------------------------
# Deterministic offline providers
# ---------------------------------------------------------------------------


def _noop_response(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
    return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)


def _delete_page_numbers_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
    """Delete every editable block whose kind is a standalone page number."""
    operations: list[dict[str, Any]] = []
    for block in payload.get("blocks", []):
        if block.get("kind") == "page_number":
            operations.append(
                {
                    "id": block["id"],
                    "text_hash": block["text_hash"],
                    "operation": "delete_block",
                    "reason": "page_number",
                    "confidence": "high",
                    "evidence_before": block["text"],
                    "expected_after_preview": "",
                    "safety_note": "Delete only the exact standalone page number block.",
                }
            )
    return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Fixtures under test
# ---------------------------------------------------------------------------

_MULTI_CHUNK_MARKDOWN = (
    "# Chapter One\n\n"
    "RETHINKING MONEY 12\n\n"
    "The first paragraph of real narrative prose that should be preserved exactly as written here.\n\n"
    "[[DOCX_IMAGE_img_001]]\n\n"
    "Some more narrative content following the image placeholder anchor in the document body.\n\n"
    "Table of Contents\n\n"
    "Introduction ......... 1\n\n"
    "Chapter One ......... 5\n\n"
    "Chapter Two ......... 12\n\n"
    "8\n\n"
    "Another paragraph of prose to push us across a chunk boundary and exercise multi-chunk assembly."
)

_REANNOTATION_MARKDOWN = (
    "Intro\n\n"
    "Economic consequences of wealth concentration Body starts here.\n\n"
    "Outro"
)

_ANCHOR_REPAIR_MARKDOWN = (
    "Intro\n\n"
    "Кооперативная валюта помогла району удержать местную торговлю,\n\n"
    "и жители продолжили обменивать услуги без дополнительных долгов.\n\n"
    "Outro"
)

_BLOCKS_MARKDOWN = "# Heading\n\nPage 1\n\nBody paragraph\n\n[[DOCX_IMAGE_img_001]]\n\n8"


def test_characterization_multi_chunk_cleanup() -> None:
    result = run_reader_cleanup(
        markdown_text=_MULTI_CHUNK_MARKDOWN,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=200, keep_toc=True),
        operation_provider=_delete_page_numbers_provider,
    )
    _assert_or_update("multi_chunk_cleanup.cleaned.md", result.cleaned_markdown)
    _assert_or_update("multi_chunk_cleanup.report.json", _canonical_json(result.report_payload))


def test_characterization_reannotation() -> None:
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target = next(
            block
            for block in payload["blocks"]
            if block["text"] == "Economic consequences of wealth concentration Body starts here."
        )
        return json.dumps(
            {
                "annotations": [
                    {
                        "id": target["id"],
                        "text_hash": target["text_hash"],
                        "role": "heading",
                        "confidence": "high",
                        "reason": "heading_body_boundary",
                        "heading_text": "Economic consequences of wealth concentration",
                        "body_text": "Body starts here.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup_reannotation(
        markdown_text=_REANNOTATION_MARKDOWN,
        config=ReaderCleanupConfig(enabled=True),
        annotation_provider=provider,
    )
    _assert_or_update("reannotation.cleaned.md", result.cleaned_markdown)
    _assert_or_update("reannotation.report.json", _canonical_json(result.report_payload))


def test_characterization_anchor_repair() -> None:
    blocks = build_cleanup_blocks(_ANCHOR_REPAIR_MARKDOWN)
    config = ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000)

    base = run_reader_cleanup(
        markdown_text=_ANCHOR_REPAIR_MARKDOWN,
        config=config,
        operation_provider=_noop_response,
    )

    def anchor_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        second = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first["id"],
                        "text_hash": first["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "fragmented_paragraph",
                        "confidence": "high",
                        "evidence_before": "The anchored block ends with a comma and the adjacent block starts with lowercase continuation prose.",
                        "expected_after_preview": "Кооперативная валюта помогла району удержать местную торговлю, и жители продолжили обменивать услуги без дополнительных долгов.",
                        "safety_note": "Join only the adjacent current payload block using exact next_id and next_text_hash.",
                        "next_id": second["id"],
                        "next_text_hash": second["text_hash"],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup_anchor_repair(
        markdown_text=base.cleaned_markdown,
        config=config,
        base_report_payload=base.report_payload,
        anchor_targets=(
            {
                "anchor_id": "anchor-frag",
                "category": "fragmented_paragraph",
                "block_id": blocks[1].block_id,
                "line_ref": "3",
                "snippet": blocks[1].text,
            },
        ),
        operation_provider=anchor_provider,
    )
    _assert_or_update("anchor_repair.cleaned.md", result.cleaned_markdown)
    _assert_or_update("anchor_repair.report.json", _canonical_json(result.report_payload))


def test_characterization_system_prompts() -> None:
    _assert_or_update("prompt_cleanup.txt", build_reader_cleanup_system_prompt())
    _assert_or_update("prompt_schema_repair.txt", build_reader_cleanup_schema_repair_system_prompt())
    _assert_or_update("prompt_global_plan.txt", build_reader_cleanup_global_plan_system_prompt())
    _assert_or_update("prompt_reannotation.txt", build_reader_cleanup_reannotation_system_prompt())


def test_characterization_build_cleanup_blocks_ids_and_hashes() -> None:
    blocks = build_cleanup_blocks(_BLOCKS_MARKDOWN)
    snapshot = [
        {
            "index": block.index,
            "block_id": block.block_id,
            "text_hash": block.text_hash,
            "kind": block.kind,
            "is_heading": block.is_heading,
            "is_toc_like": block.is_toc_like,
        }
        for block in blocks
    ]
    _assert_or_update("build_cleanup_blocks.json", _canonical_json(snapshot))
