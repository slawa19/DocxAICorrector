import json
import time
from pathlib import Path

import pytest
from typing import Any

from docxaicorrector.reader_cleanup_mvp._constants import (
    _ALLOWED_DELETE_REASONS,
    _ALLOWED_OPERATIONS,
    _TOC_MIN_CONTENTS_ENTRY_TOKENS,
    _TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN,
    _TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO,
    _TOC_MIN_PAGE_REFERENCE_TOKENS,
)
from docxaicorrector.reader_cleanup_mvp._report import (
    _extract_docx_image_placeholder_ids,
    _failed_chunk_ratio_exceeds_threshold,
    _image_reconciliation_warnings,
    _reconcile_docx_image_placeholders,
)
from docxaicorrector.reader_cleanup_mvp._utils import _detect_block_kind
from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupConfig,
    ReaderCleanupStageError,
    build_cleanup_blocks,
    build_reader_cleanup_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    resolve_reader_cleanup_config,
    run_reader_cleanup,
    run_reader_cleanup_reannotation,
    write_reader_cleanup_diagnostics,
)


def _delete_block_operation(
    block: Any,
    *,
    reason: str,
    confidence: str | None = "high",
    evidence_before: str | None = None,
    expected_after_preview: str = "",
    safety_note: str | None = None,
) -> dict[str, Any]:
    if isinstance(block, dict):
        block_id = str(block["id"])
        text_hash = str(block["text_hash"])
        text = str(block.get("text") or "")
    else:
        block_id = str(block.block_id)
        text_hash = str(block.text_hash)
        text = str(block.text)
    payload: dict[str, Any] = {
        "id": block_id,
        "text_hash": text_hash,
        "operation": "delete_block",
        "reason": reason,
        "evidence_before": evidence_before or text,
        "expected_after_preview": expected_after_preview,
        "safety_note": safety_note or f"Delete only the exact non-semantic block for reason={reason}.",
    }
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def _unknown_operation_item(
    block: Any,
    *,
    operation: str,
    expected_after_preview: str = "",
    confidence: str = "high",
    reason: str = "role_assignment_correction",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A cleanup_operations item naming an operation this build does not implement."""
    if isinstance(block, dict):
        block_id = str(block["id"])
        text_hash = str(block["text_hash"])
        text = str(block.get("text") or "")
    else:
        block_id = str(block.block_id)
        text_hash = str(block.text_hash)
        text = str(block.text)
    payload = {
        "id": block_id,
        "text_hash": text_hash,
        "operation": operation,
        "reason": reason,
        "confidence": confidence,
        "evidence_before": text,
        "expected_after_preview": expected_after_preview,
        "safety_note": "Change only the local role marker; preserve visible text.",
    }
    payload.update(extra or {})
    return payload


class _FakeAuthError(Exception):
    status_code = 401


def test_build_cleanup_blocks_assigns_stable_ids_and_hashes() -> None:
    blocks = build_cleanup_blocks("# Heading\n\nPage 1\n\nBody paragraph")

    assert [block.block_id for block in blocks] == ["b_000000", "b_000001", "b_000002"]
    assert blocks[0].is_heading is True
    assert blocks[1].kind == "page_number"
    assert len({block.text_hash for block in blocks}) == 3


def test_build_cleanup_blocks_serializes_layout_signals_to_payload() -> None:
    blocks = build_cleanup_blocks(
        "Short heading\n\nBody paragraph",
        block_metadata_by_index={
            0: {
                "paragraph_id": "p1",
                "layout_signals": {
                    "font_size": 14.0,
                    "body_font_size": 10.0,
                    "centered": True,
                    "superscript": False,
                },
            }
        },
    )

    payload = blocks[0].to_payload()

    assert payload["paragraph_id"] == "p1"
    assert payload["layout_signals"] == {
        "standalone_short_line": True,
        "line_count": 1,
        "word_count": 2,
        "looks_like_superscript_marker": False,
        "is_docx_image_anchor": False,
        "docx_image_ids": [],
        "detected_kind": "paragraph",
        "font_size": 14.0,
        "body_font_size": 10.0,
        "centered": True,
        "superscript": False,
    }


def test_resolve_reader_cleanup_config_accepts_overlap_and_string_global_plan_flag() -> None:
    config = resolve_reader_cleanup_config(
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_model": "anthropic:claude-sonnet-4-6",
            "reader_cleanup_chunk_size": 8000,
            "reader_cleanup_overlap_blocks_before": 3,
            "reader_cleanup_overlap_blocks_after": 3,
            "reader_cleanup_global_plan_enabled": "false",
        },
        fallback_model="fallback:model",
    )

    assert config.enabled is True
    assert config.model == "anthropic:claude-sonnet-4-6"
    assert config.chunk_size == 8000
    assert config.overlap_blocks_before == 3
    assert config.overlap_blocks_after == 3
    assert config.global_plan_enabled is False


def test_resolve_reader_cleanup_config_defaults_to_canonical_small_overlap_shape() -> None:
    config = resolve_reader_cleanup_config(
        app_config={"reader_cleanup_enabled": True},
        fallback_model="fallback:model",
    )

    assert config.enabled is True
    assert config.chunk_size == 8000
    assert config.overlap_blocks_before == 3
    assert config.overlap_blocks_after == 3
    assert config.global_plan_enabled is False


def test_resolve_reader_cleanup_config_accepts_allowed_operation_list() -> None:
    config = resolve_reader_cleanup_config(
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_allowed_operations": ["delete_block", "remove_inline_noise", "delete_block", "split_block_typo"],
        },
        fallback_model="fallback:model",
    )

    assert config.allowed_operations == ("delete_block", "remove_inline_noise")


def test_reader_cleanup_allowed_operations_contract_filters_structural_operations() -> None:
    markdown = "Intro\n\nPage 1\n\nHEADING Body text"
    captured_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        captured_payloads.append(payload)
        page_block = next(block for block in payload["blocks"] if block["text"] == "Page 1")
        heading_block = next(block for block in payload["blocks"] if block["text"] == "HEADING Body text")
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(page_block, reason="page_number", confidence="high"),
                    {
                        "id": heading_block["id"],
                        "text_hash": heading_block["text_hash"],
                        "operation": "split_block",
                        "reason": "heading_fused_with_body",
                        "confidence": "high",
                        "evidence_before": "heading fused with body",
                        "expected_after_preview": "HEADING\n\nBody text",
                        "safety_note": "Would be structural repair outside the minimal cleanup budget.",
                        "split_substrings": ["HEADING", "Body text"],
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
            allowed_operations=("delete_block", "remove_inline_noise"),
        ),
        operation_provider=provider,
    )

    assert captured_payloads
    assert captured_payloads[0]["response_contract"]["allowed_operations"] == ["delete_block", "remove_inline_noise"]
    assert captured_payloads[0]["cleanup_settings"]["allowed_operations"] == ["delete_block", "remove_inline_noise"]
    assert result.cleaned_markdown == "Intro\n\nHEADING Body text"
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 1
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1
    ignored_reasons = {
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("operation") == "split_block"
    }
    assert ignored_reasons == {"operation_not_allowed_by_cleanup_contract"}


def test_run_reader_cleanup_rejects_delete_block_for_docx_image_anchor() -> None:
    markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        image_block = next(block for block in payload["blocks"] if block["text"] == "[[DOCX_IMAGE_img_001]]")
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(image_block, reason="extraction_artifact", confidence="high"),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.cleaned_markdown == markdown
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 0
    assert result.report_payload["image_reconciliation"]["before_image_id_count"] == 1
    assert result.report_payload["image_reconciliation"]["after_image_id_count"] == 1
    assert {
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("id") == image_block_id(result.report_payload)
    } == {"docx_image_anchor_protected"}


def image_block_id(report_payload: dict[str, Any]) -> str:
    for entry in report_payload["ignored_cleanup_operations"]:
        if entry.get("raw_text_preview") == "[[DOCX_IMAGE_img_001]]":
            return str(entry["id"])
    return ""


def test_run_reader_cleanup_preserves_image_ids_on_four_replay_books() -> None:
    project_root = Path(__file__).resolve().parents[1]
    markdown_paths = [
        project_root
        / ".run/reader_cleanup_faithful_replay/20260618T124238Z_faithful_reclassify_replay/creating_wealth/creating_wealth.faithful.raw.md",
        project_root
        / ".run/reader_cleanup_faithful_replay/20260618T124238Z_faithful_reclassify_replay/lietaer/lietaer.faithful.raw.md",
        project_root
        / ".run/reader_cleanup_faithful_replay/20260618T124238Z_faithful_reclassify_replay/mazzucato/mazzucato.faithful.raw.md",
        project_root
        / "tests/artifacts/real_document_pipeline/runs/20260618T195903Z_6156_bernardlietaer-moneyandsustainabilitypdffromepub-160516072426/Money_Sustainability_pdf_full_heldout.md",
    ]

    missing = [path for path in markdown_paths if not path.exists()]
    if missing:
        # These faithful-replay corpora live under gitignored .run/ (and large held-out
        # artifacts) and are absent on a clean checkout (CI runs `git clean -fdx`). Skip
        # rather than fail so the image-id-preservation guard stays dormant-but-ready
        # wherever the corpora are present locally.
        pytest.skip(f"reader-cleanup replay corpora not present: {missing[0]}")

    for markdown_path in markdown_paths:
        markdown = markdown_path.read_text(encoding="utf-8")

        def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
            return json.dumps(
                {
                    "cleanup_operations": [
                        _delete_block_operation(block, reason="extraction_artifact", confidence="high")
                        for block in payload["blocks"]
                        if "[[DOCX_IMAGE_" in str(block.get("text") or "")
                    ],
                    "warnings": [],
                },
                ensure_ascii=False,
            )

        result = run_reader_cleanup(
            markdown_text=markdown,
            config=ReaderCleanupConfig(
                enabled=True,
                chunk_size=50000,
                keep_toc=False,
                max_delete_block_ratio=1.0,
                max_delete_char_ratio=1.0,
            ),
            operation_provider=provider,
        )

        image_reconciliation = result.report_payload["image_reconciliation"]
        assert image_reconciliation["before_image_id_count"] == image_reconciliation["after_image_id_count"], markdown_path
        assert image_reconciliation["missing_image_ids"] == [], markdown_path
        assert image_reconciliation["missing_after_repair"] == [], markdown_path
        # Spec 052 item 5 strengthens this from "the ids all came back" to "no image
        # MOVED". Counting ids could be satisfied by pasting a lost anchor at the end of
        # the document, which is exactly what the reconciler used to do: on the real
        # replay of creating_wealth four figures from chapters 2 and 10 were re-appended
        # after the last page while the report stayed green. Comparing the ORDERED anchor
        # sequence cannot be satisfied that way.
        assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == _extract_docx_image_placeholder_ids(
            markdown
        ), markdown_path
        assert image_reconciliation["reinserted_image_ids"] == [], markdown_path
        assert image_reconciliation["cleanup_discarded_for_missing_image_ids"] is False, markdown_path

        # Second adversarial pass on the same real books, and the one that matters now.
        # Deleting anchor blocks was never the route by which images actually moved — that
        # is refused by ``docx_image_anchor_protected`` — so the delete pass above cannot
        # tell whether the reconciler re-appends. The measured route was an ACCEPTED
        # ``normalize_heading_boundary`` cutting a figure block between "[[DOCX_IMAGE_" and
        # "img_014]]", which broke the placeholder and sent the figure to the end of the
        # book. This pass proposes exactly that, on every figure block of every book.
        #
        # What this pass DOES verify, at real-book scale: every one of those operations is
        # rejected by name and no anchor moves. What it does NOT verify is the reconciler's
        # re-append behaviour — the rejection layer answers first, so the reconciler is
        # never reached and a mutation restoring re-append leaves this pass green. The
        # reconciler's own contract is pinned by
        # ``test_reconcile_discards_the_cleanup_when_an_anchor_cannot_be_restored`` and
        # ``test_unattributable_anchor_loss_fails_the_pass_visibly``, which run in CI
        # without the ``.run/`` corpora.
        def boundary_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
            operations = []
            for block in payload["blocks"]:
                text = str(block.get("text") or "")
                if not text.startswith("[[DOCX_IMAGE_") or len(text) <= len("[[DOCX_IMAGE_"):
                    continue
                operations.append(
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading_fused_with_body",
                        "confidence": "high",
                        "evidence_before": text,
                        "expected_after_preview": "[[DOCX_IMAGE_\n\n" + text[len("[[DOCX_IMAGE_") :],
                        "safety_note": "adversarial anchor-splitting boundary",
                        "heading_substring": "[[DOCX_IMAGE_",
                        "body_substring": text[len("[[DOCX_IMAGE_") :],
                    }
                )
            return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)

        boundary_result = run_reader_cleanup(
            markdown_text=markdown,
            config=ReaderCleanupConfig(enabled=True, chunk_size=50000, keep_toc=False),
            operation_provider=boundary_provider,
        )

        assert _extract_docx_image_placeholder_ids(
            boundary_result.cleaned_markdown
        ) == _extract_docx_image_placeholder_ids(markdown), markdown_path
        assert boundary_result.report_payload["image_reconciliation"]["reinserted_image_ids"] == [], markdown_path
        # Say which layer answered, so a change of layer shows up here instead of passing
        # quietly: every anchor-splitting operation is refused, none is accepted.
        assert not [
            entry
            for entry in boundary_result.report_payload["accepted_cleanup_operations"]
            if entry.get("operation") == "normalize_heading_boundary"
        ], markdown_path


_ANCHOR_FIGURE_BLOCK = "[[DOCX_IMAGE_img_014]] РИСУНОК 2.1 Архетип пределы роста"
_PAGE_FURNITURE_BLOCK = "стр. 42"
_ANCHOR_MARKDOWN = (
    "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
    f"{_PAGE_FURNITURE_BLOCK}\n\n"
    f"{_ANCHOR_FIGURE_BLOCK}\n\n"
    "Заключительный абзац достаточной длины."
)


def _anchor_splitting_boundary_operation(block: dict[str, Any], *, split_at: int) -> dict[str, Any]:
    """A ``normalize_heading_boundary`` that cuts an image placeholder in half.

    This is the measured route by which figures actually moved: the placeholder stops
    matching, the id "disappears", and the old reconciler pasted it after the last page.
    """
    text = str(block["text"])
    return {
        "id": block["id"],
        "text_hash": block["text_hash"],
        "operation": "normalize_heading_boundary",
        "reason": "heading_fused_with_body",
        "confidence": "high",
        "evidence_before": text,
        "expected_after_preview": text[:split_at] + "\n\n" + text[split_at:],
        "safety_note": "adversarial anchor-splitting boundary",
        "heading_substring": text[:split_at],
        "body_substring": text[split_at:],
    }


def _page_furniture_delete_operation(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": block["id"],
        "text_hash": block["text_hash"],
        "operation": "delete_block",
        "reason": "page_number",
        "confidence": "high",
        "evidence_before": str(block["text"]),
        "expected_after_preview": "",
        "safety_note": "page furniture",
    }


def _permissive_anchor_config() -> ReaderCleanupConfig:
    return ReaderCleanupConfig(enabled=True, max_delete_block_ratio=1.0, max_delete_char_ratio=1.0)


def test_anchor_breaking_operation_is_rejected_and_the_rest_of_the_cleanup_survives() -> None:
    # Spec 052 item 5, in CI and without the gitignored replay corpora. The operation that
    # breaks a figure anchor is dropped BY NAME; the unrelated page-number deletion in the
    # same response still ships. "Reject the operation that lost it" is only worth anything
    # if the rest of the cleanup survives the rejection.
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        page = next(block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _page_furniture_delete_operation(page),
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_ANCHOR_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=provider,
    )
    report = result.report_payload

    assert result.changed is True
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == _extract_docx_image_placeholder_ids(
        _ANCHOR_MARKDOWN
    )
    assert _PAGE_FURNITURE_BLOCK not in result.cleaned_markdown
    assert report["stage_status"] == "completed"
    assert "failure" not in report
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["delete_block"]
    rejected = [
        entry
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "docx_image_anchor_lost_by_operation"
    ]
    assert [entry["operation"] for entry in rejected] == ["normalize_heading_boundary"]
    assert rejected[0]["lost_docx_image_ids"] == ["img_014"]


def test_anchor_lost_by_an_operation_targeting_a_different_block_is_still_attributed() -> None:
    # Round-9 P1-B. The operation names ``b_000002`` (the fused-heading block); the anchor
    # it destroys lives in ``b_000003``, absorbed through
    # ``_apply_heading_boundary_across_adjacent_block``. Attribution by declared
    # ``block_id``/``next_id`` blamed nobody here (``normalize_heading_boundary`` has no
    # ``next_id`` at all), so the loss was unattributable and the ENTIRE book's cleanup was
    # thrown away. Blame follows the anchors the operation actually destroyed instead.
    heading_block = "Заголовок раздела Текст"
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
        f"{_PAGE_FURNITURE_BLOCK}\n\n"
        f"{heading_block}\n\n"
        "[[DOCX_IMAGE_img_009]]\n\n"
        "Заключительный абзац достаточной длины."
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target = next(block for block in payload["blocks"] if block["text"] == heading_block)
        page = next(block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _page_furniture_delete_operation(page),
                    {
                        "id": target["id"],
                        "text_hash": target["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading_fused_with_body",
                        "confidence": "high",
                        "evidence_before": heading_block,
                        "expected_after_preview": "Заголовок раздела Текст [[DOCX\n\n_IMAGE_img_009]]",
                        "safety_note": "boundary reaching into the next block",
                        "heading_substring": "Заголовок раздела Текст [[DOCX",
                        "body_substring": "_IMAGE_img_009]]",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=_permissive_anchor_config(),
        operation_provider=provider,
    )
    report = result.report_payload

    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_009"]
    assert report["stage_status"] == "completed"
    assert "failure" not in report
    assert report["image_reconciliation"]["cleanup_discarded_for_missing_image_ids"] is False
    rejected = [
        entry
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "docx_image_anchor_lost_by_operation"
    ]
    assert [entry["operation"] for entry in rejected] == ["normalize_heading_boundary"]
    # The operation declared only the fused-heading block (b_000002); the anchor it destroyed
    # lived in b_000003, which it never named. Blame lands on it anyway, because what is
    # measured is the anchor that stopped existing while it ran.
    assert rejected[0]["id"] == "b_000002"
    assert rejected[0]["lost_docx_image_ids"] == ["img_009"]
    # And the unrelated deletion in the same response still ships.
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["delete_block"]
    assert result.changed is True


def test_operation_refused_for_its_own_reason_is_not_blamed_for_a_lost_anchor() -> None:
    # Round-9 P2-2. The join is refused in the first attempt as
    # ``join_next_text_hash_mismatch`` — it never ran, so it cannot have lost anything. The
    # rejection layer used to stamp ``docx_image_anchor_lost_by_operation`` over every
    # index it considered, replacing the real reason with a fabricated one.
    fragment = "Начало фрагмента, который обрывается"
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
        f"{fragment}\n\n"
        f"{_ANCHOR_FIGURE_BLOCK}\n\n"
        "Заключительный абзац достаточной длины."
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        fragment_block = next(block for block in payload["blocks"] if block["text"] == fragment)
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                    {
                        "id": fragment_block["id"],
                        "text_hash": fragment_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "fragmented_paragraph",
                        "confidence": "high",
                        "evidence_before": fragment,
                        "expected_after_preview": f"{fragment} {_ANCHOR_FIGURE_BLOCK}",
                        "safety_note": "join with a stale next-block hash",
                        "next_id": anchor["id"],
                        "next_text_hash": "deadbeefdeadbeef",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=_permissive_anchor_config(),
        operation_provider=provider,
    )
    report = result.report_payload

    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    reasons_by_operation = {
        str(entry["operation"]): str(entry["ignored_reason"]) for entry in report["ignored_cleanup_operations"]
    }
    assert reasons_by_operation["join_fragmented_paragraph"] == "join_next_text_hash_mismatch"
    assert reasons_by_operation["normalize_heading_boundary"] == "docx_image_anchor_lost_by_operation"


_FRAGMENT_BLOCK = "Первая часть фразы продолжается"
_JOINED_WITH_ANCHOR = f"{_FRAGMENT_BLOCK} {_ANCHOR_FIGURE_BLOCK}"
_JOIN_THEN_BOUNDARY_MARKDOWN = (
    "Вступительный абзац достаточной длины, чтобы его сохранить в выдаче целиком.\n\n"
    f"{_FRAGMENT_BLOCK}\n\n"
    f"{_ANCHOR_FIGURE_BLOCK}\n\n"
    "Заключительный абзац достаточной длины, чтобы его сохранить в выдаче."
)


def _join_operation(block: dict[str, Any], next_block: dict[str, Any], *, expected_after_preview: str) -> dict[str, Any]:
    return {
        "id": block["id"],
        "text_hash": block["text_hash"],
        "operation": "join_fragmented_paragraph",
        "reason": "fragmented_paragraph",
        "confidence": "high",
        "evidence_before": str(block["text"]),
        "expected_after_preview": expected_after_preview,
        "safety_note": "Join only the adjacent block using exact next_id and next_text_hash.",
        "next_id": next_block["id"],
        "next_text_hash": next_block["text_hash"],
    }


def _boundary_operation_on_text(block: dict[str, Any], *, text: str, split_at: int) -> dict[str, Any]:
    """A ``normalize_heading_boundary`` whose exact parts describe ``text``, not the block."""
    return {
        "id": block["id"],
        "text_hash": block["text_hash"],
        "operation": "normalize_heading_boundary",
        "reason": "heading_fused_with_body",
        "confidence": "high",
        "evidence_before": text,
        "expected_after_preview": f"{text[:split_at]}\n\n{text[split_at:]}",
        "safety_note": "anchor-splitting boundary on the joined slot",
        "heading_substring": text[:split_at],
        "body_substring": text[split_at:],
    }


def test_a_join_that_carried_an_anchor_safely_is_not_blamed_for_a_later_operations_loss() -> None:
    # Round-10 P1. "Join the fragmented paragraph, then normalize the heading boundary of the
    # joined text" is the sequence the cleanup prompt itself prescribes for
    # ``heading_fused_with_body``, and it happens right next to figure blocks. Attribution by
    # block-id write sets merged the join's two blocks into one provenance set and handed
    # that set to every later write on the slot, so the join — which carried the anchor
    # across intact — was reported as having lost it. The anchor diff cannot smear: the join
    # takes ``[[DOCX_IMAGE_img_014]]`` from one slot and puts the same anchor in another, so
    # nothing stopped existing while it ran.
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        fragment = next(block for block in payload["blocks"] if block["text"] == _FRAGMENT_BLOCK)
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _join_operation(fragment, anchor, expected_after_preview=_JOINED_WITH_ANCHOR),
                    _boundary_operation_on_text(
                        fragment,
                        text=_JOINED_WITH_ANCHOR,
                        split_at=_JOINED_WITH_ANCHOR.index("[[DOCX_IMAGE_") + len("[[DOCX_IMAGE_"),
                    ),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_JOIN_THEN_BOUNDARY_MARKDOWN,
        config=ReaderCleanupConfig(enabled=True, chunk_size=100000),
        operation_provider=provider,
    )
    report = result.report_payload

    # Exactly one operation is blamed, and it is the one that cut the placeholder in half.
    rejected = [
        entry
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "docx_image_anchor_lost_by_operation"
    ]
    assert [entry["operation"] for entry in rejected] == ["normalize_heading_boundary"]
    assert rejected[0]["lost_docx_image_ids"] == ["img_014"]
    # The innocent join keeps its place, so the paragraph is still repaired and delivered.
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["join_fragmented_paragraph"]
    assert result.changed is True
    assert _JOINED_WITH_ANCHOR in result.cleaned_markdown
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    assert report["stage_status"] == "completed"
    assert "reader_cleanup_image_anchor_lost_by_operation:1:rejected_operations=1" in report["warnings"]


def test_smeared_anchor_blame_does_not_escalate_into_discarding_the_whole_cleanup() -> None:
    # Round-10 P1, the consequence that makes it a P1 rather than a reporting wart. A third
    # operation splits the figure block itself; it is inert while the join holds that block's
    # text, and destructive the moment the join is rolled back. Smeared blame rejected the
    # innocent join together with the real culprit, which freed the third operation to run,
    # which lost the anchor again — and an anchor still missing after the rejection retry
    # discards the ENTIRE book's cleanup. Rejecting only the culprit keeps the join, which
    # keeps the third operation inapplicable, which ships the cleanup.
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        fragment = next(block for block in payload["blocks"] if block["text"] == _FRAGMENT_BLOCK)
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _join_operation(fragment, anchor, expected_after_preview=_JOINED_WITH_ANCHOR),
                    _boundary_operation_on_text(
                        fragment,
                        text=_JOINED_WITH_ANCHOR,
                        split_at=_JOINED_WITH_ANCHOR.index("[[DOCX_IMAGE_") + len("[[DOCX_IMAGE_"),
                    ),
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_JOIN_THEN_BOUNDARY_MARKDOWN,
        config=ReaderCleanupConfig(enabled=True, chunk_size=100000),
        operation_provider=provider,
    )
    report = result.report_payload

    assert report["stage_status"] == "completed"
    assert "failure" not in report
    assert result.changed is True
    assert result.cleaned_markdown != _JOIN_THEN_BOUNDARY_MARKDOWN
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["join_fragmented_paragraph"]
    assert [
        entry["id"]
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "docx_image_anchor_lost_by_operation"
    ] == ["b_000001"]


def test_an_operation_that_changed_nothing_is_never_blamed_for_a_lost_anchor() -> None:
    # The invariant the anchor diff must not lose while gaining precision. The boundary
    # operation destroys the anchor; the delete operation in the same response is refused
    # before it can touch a slot. A refused operation writes nothing, so its anchor diff is
    # empty and it keeps its own ignore reason instead of a stamped-on anchor-loss verdict.
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        page = next(block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK)
        stale_delete = _page_furniture_delete_operation(page)
        stale_delete["text_hash"] = "0" * 64
        return json.dumps(
            {
                "cleanup_operations": [
                    stale_delete,
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_ANCHOR_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=provider,
    )
    report = result.report_payload

    reasons_by_operation = {
        str(entry["operation"]): str(entry["ignored_reason"]) for entry in report["ignored_cleanup_operations"]
    }
    assert reasons_by_operation["normalize_heading_boundary"] == "docx_image_anchor_lost_by_operation"
    assert reasons_by_operation["delete_block"] != "docx_image_anchor_lost_by_operation"
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]


_OVERLAP_CAPTION_BLOCK = "[[DOCX_IMAGE_img_014]] Подпись к рисунку продолжается дальше в тексте книги."
_OVERLAP_MARKDOWN = (
    "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
    f"{_OVERLAP_CAPTION_BLOCK}\n\n"
    "Заключительный абзац достаточной длины."
)


def _overlapping_boundary_provider(*, heading: str, body: str):
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(item for item in payload["blocks"] if item["text"] == _OVERLAP_CAPTION_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading_fused_with_body",
                        "confidence": "high",
                        "evidence_before": _OVERLAP_CAPTION_BLOCK,
                        "expected_after_preview": f"{heading}\n\n{body}",
                        "safety_note": "overlapping heading and body substrings",
                        "heading_substring": heading,
                        "body_substring": body,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    return provider


@pytest.mark.parametrize(
    ("heading_end", "body_start"),
    [
        # The two substrings overlap in the middle of the block...
        (40, 10),
        # ...and the degenerate case where the heading is a prefix of the body, which puts
        # the whole image placeholder inside the overlap.
        (40, 0),
    ],
)
def test_overlapping_heading_and_body_substrings_are_refused(heading_end: int, body_start: int) -> None:
    # Round-10 P2-3. ``normalize_heading_boundary`` emits ``heading + "\n\n" + body`` and
    # relied on a "no unaccounted text" guard to prove the two parts covered the block. That
    # guard computed the gap as ``current_text[len(heading):body_start]``, which for an
    # overlap runs backwards and is ALWAYS empty — so it passed vacuously while the shared
    # span was emitted twice. With the image placeholder inside the overlap the run delivered
    # ``['img_014', 'img_014']`` from a source holding one, and reported
    # ``stage_status: completed``: reconciliation fails closed on anchors that go missing,
    # never on anchors that multiply.
    result = run_reader_cleanup(
        markdown_text=_OVERLAP_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=_overlapping_boundary_provider(
            heading=_OVERLAP_CAPTION_BLOCK[:heading_end],
            body=_OVERLAP_CAPTION_BLOCK[body_start:],
        ),
    )
    report = result.report_payload

    assert result.changed is False
    assert result.cleaned_markdown == _OVERLAP_MARKDOWN
    assert [entry["ignored_reason"] for entry in report["ignored_cleanup_operations"]] == [
        "heading_boundary_substrings_overlap"
    ]
    assert report["accepted_cleanup_operations"] == []
    # No anchor multiplied, and no prose was duplicated either.
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    assert report["image_reconciliation"]["extra_image_ids"] == []
    assert result.cleaned_markdown.count("Подпись к рисунку") == 1


def test_unattributable_anchor_loss_fails_the_pass_visibly() -> None:
    # Round-9 P1-A. Two boundary operations target the same figure block: the first applies
    # and breaks the anchor, the second is refused as a same-block sequence violation. Drop
    # the culprit and the second one is now free to apply — and breaks the same anchor
    # again. Nothing can be delivered, so the cleanup is discarded wholesale.
    #
    # That discard used to be invisible: ``stage_status="completed"``, no ``failure``, and
    # the thrown-away operations still counted as ACCEPTED in the stats, in
    # ``accepted_cleanup_operations`` and in ``accepted_delete_block_ids`` — which the
    # lineage-rebuild harness turns into registry deletions for a document whose markdown
    # never changed.
    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        page = next(block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    _page_furniture_delete_operation(page),
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_img_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_ANCHOR_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=provider,
    )
    report = result.report_payload

    assert result.changed is False
    assert result.cleaned_markdown == _ANCHOR_MARKDOWN
    assert report["stage_status"] == "failed"
    assert report["failure"]["kind"] == "docx_image_anchor_lost_cleanup_discarded"
    assert report["failure"]["missing_docx_image_id_count"] == 1
    assert report["failure"]["missing_docx_image_ids"] == ["img_014"]
    assert report["failure"]["discarded_cleanup_operation_count"] == 2
    # Round-10 P3: the failure no longer publishes ``rejected_cleanup_operation_count``. It
    # was unreachable-by-construction zero — ``docx_image_anchor_lost_by_operation`` entries
    # exist only where the rejection SUCCEEDED, and a successful rejection leaves no missing
    # anchor for this branch to discard over.
    assert "rejected_cleanup_operation_count" not in report["failure"]
    # Nothing thrown away is reported as accepted, anywhere.
    assert report["accepted_cleanup_operations"] == []
    assert report["accepted_delete_blocks"] == []
    assert report["stats"]["accepted_cleanup_operation_count"] == 0
    assert report["stats"]["accepted_delete_block_count"] == 0
    assert report["stats"]["deleted_non_whitespace_char_count"] == 0
    assert result.accepted_delete_block_ids == ()
    discarded = [
        entry
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "cleanup_discarded_for_missing_docx_image_anchor"
    ]
    assert sorted(str(entry["operation"]) for entry in discarded) == ["delete_block", "normalize_heading_boundary"]
    assert all(entry["lost_docx_image_ids"] == ["img_014"] for entry in discarded)


_GLOBAL_SAFETY_NOISE_BLOCK = (
    "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
)
_GLOBAL_SAFETY_NOISE_SUBSTRING = "150 РАЗДЕЛ ОТЧЕТА "
_GLOBAL_SAFETY_CLEANED_NOISE_BLOCK = "Через призму рабочего процесса можно увидеть новые возможности для команды."


def _inline_noise_operation(block: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": block["id"],
        "text_hash": block["text_hash"],
        "operation": "remove_inline_noise",
        "reason": "page_furniture_inline",
        "confidence": "high",
        "evidence_before": "Page furniture is fused to the semantic paragraph prefix.",
        "expected_after_preview": _GLOBAL_SAFETY_CLEANED_NOISE_BLOCK,
        "safety_note": "Only the exact non-semantic heading fragment should be removed.",
        "noise_substring": _GLOBAL_SAFETY_NOISE_SUBSTRING,
    }


def test_global_safety_rollback_puts_the_rejected_text_back_in_the_delivered_markdown() -> None:
    # The rollback used to be bookkeeping only. It moved the accepted deletions into the
    # ignore list as ``global_safety_limit_exceeded`` and stripped them from the accepted
    # operations, but never restored the emptied block slots — so as soon as ONE non-delete
    # operation was accepted, the "rejected" blocks were still dropped from the delivered
    # markdown while the report insisted they had been rejected. The recorded lietaer run is
    # exactly this shape: 37 deletions rolled back by the limit, 44 non-delete operations
    # accepted, and all 37 blocks missing from the shipped book.
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить в выдаче.\n\n"
        "стр. 42\n\n"
        "Первый содержательный абзац, который остаётся в книге без изменений.\n\n"
        f"{_GLOBAL_SAFETY_NOISE_BLOCK}\n\n"
        "Второй содержательный абзац, который остаётся в книге без изменений.\n\n"
        "стр. 43\n\n"
        "Заключительный абзац достаточной длины, чтобы его сохранить в выдаче."
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        return json.dumps(
            {
                "cleanup_operations": [
                    *(
                        _page_furniture_delete_operation(block)
                        for block in payload["blocks"]
                        if block["text"] in {"стр. 42", "стр. 43"}
                    ),
                    *(
                        _inline_noise_operation(block)
                        for block in payload["blocks"]
                        if block["text"] == _GLOBAL_SAFETY_NOISE_BLOCK
                    ),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, chunk_size=100000),
        operation_provider=provider,
    )
    report = result.report_payload

    # The report's verdict on the deletions, unchanged: rejected by the global limit.
    assert [
        str(entry["raw_text_preview"])
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "global_safety_limit_exceeded"
    ] == ["стр. 42", "стр. 43"]
    assert report["stats"]["accepted_delete_block_count"] == 0
    assert result.accepted_delete_block_ids == ()
    # ...and the delivered text now agrees with it.
    assert "стр. 42" in result.cleaned_markdown
    assert "стр. 43" in result.cleaned_markdown
    assert len(build_cleanup_blocks(result.cleaned_markdown)) == len(build_cleanup_blocks(markdown))
    # The non-delete operation that made the loss visible still ships.
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["remove_inline_noise"]
    assert _GLOBAL_SAFETY_CLEANED_NOISE_BLOCK in result.cleaned_markdown
    assert _GLOBAL_SAFETY_NOISE_SUBSTRING not in result.cleaned_markdown
    assert result.changed is True


# --------------------------------------------------------------------------------------
# The narrowed default operation set (spec 052, first live run 2026-08-02)
#
# The live run split cleanly by operation: ``normalize_heading_boundary`` +
# ``join_fragmented_paragraph`` removed 18 visible defects against 4 caused, while
# ``remove_inline_noise`` + ``delete_block`` removed 0 against 12 caused — a file name cut
# out of a WHO URL, author surnames cut out of an article title, years cut out of a
# bibliography. The owner narrowed the DEFAULT set to the heading pair; the rest of the
# operations stay in the code and must still work when a config names them explicitly.
# --------------------------------------------------------------------------------------

_NARROWED_HEADING_BLOCK = "TEAM PLAYBOOK Shared ownership keeps delivery predictable."
_NARROWED_FRAGMENT_HEAD = "Первая часть фразы продолжается"
_NARROWED_FRAGMENT_TAIL = "во втором блоке, разорванном при извлечении текста."
_NARROWED_JOINED = f"{_NARROWED_FRAGMENT_HEAD} {_NARROWED_FRAGMENT_TAIL}"
_NARROWED_MARKDOWN = (
    "Вступительный абзац достаточной длины, чтобы его сохранить в выдаче.\n\n"
    "стр. 42\n\n"
    f"{_GLOBAL_SAFETY_NOISE_BLOCK}\n\n"
    f"{_NARROWED_HEADING_BLOCK}\n\n"
    f"{_NARROWED_FRAGMENT_HEAD}\n\n"
    f"{_NARROWED_FRAGMENT_TAIL}\n\n"
    "Заключительный абзац достаточной длины, чтобы его сохранить в выдаче."
)


def _narrowed_set_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
    """One response proposing one operation of each of the four measured kinds."""
    by_text = {str(block["text"]): block for block in payload["blocks"]}
    heading_block = by_text[_NARROWED_HEADING_BLOCK]
    return json.dumps(
        {
            "cleanup_operations": [
                _page_furniture_delete_operation(by_text["стр. 42"]),
                _inline_noise_operation(by_text[_GLOBAL_SAFETY_NOISE_BLOCK]),
                {
                    "id": heading_block["id"],
                    "text_hash": heading_block["text_hash"],
                    "operation": "normalize_heading_boundary",
                    "reason": "page_furniture_heading",
                    "confidence": "high",
                    "evidence_before": "The block fuses the section heading with the body sentence.",
                    "expected_after_preview": "TEAM PLAYBOOK / Shared ownership keeps delivery predictable.",
                    "safety_note": "Keep the exact heading prefix and the exact body remainder.",
                    "heading_substring": "TEAM PLAYBOOK",
                    "body_substring": "Shared ownership keeps delivery predictable.",
                },
                _join_operation(
                    by_text[_NARROWED_FRAGMENT_HEAD],
                    by_text[_NARROWED_FRAGMENT_TAIL],
                    expected_after_preview=_NARROWED_JOINED,
                ),
            ],
            "warnings": [],
        },
        ensure_ascii=False,
    )


def _narrowed_set_app_config(**overrides: object) -> dict[str, object]:
    # Deliberately says nothing about the operation set: the point is what a config that
    # does not mention it gets. The delete ratios are raised so a rejected delete can only
    # be the operation contract, never the global delete-safety limit.
    return {
        "reader_cleanup_enabled": True,
        "reader_cleanup_max_delete_block_ratio": 0.8,
        "reader_cleanup_max_delete_char_ratio": 0.8,
        **overrides,
    }


def test_default_config_narrows_the_cleanup_contract_to_the_two_heading_operations() -> None:
    config = resolve_reader_cleanup_config(
        app_config=_narrowed_set_app_config(),
        fallback_model="fallback:model",
    )

    assert config.allowed_operations == ("normalize_heading_boundary", "join_fragmented_paragraph")


def test_default_config_rejects_inline_noise_and_delete_block_and_keeps_their_text() -> None:
    result = run_reader_cleanup(
        markdown_text=_NARROWED_MARKDOWN,
        config=resolve_reader_cleanup_config(
            app_config=_narrowed_set_app_config(),
            fallback_model="fallback:model",
        ),
        operation_provider=_narrowed_set_provider,
    )
    report = result.report_payload

    reasons_by_operation = {
        str(entry["operation"]): str(entry["ignored_reason"]) for entry in report["ignored_cleanup_operations"]
    }
    assert reasons_by_operation == {
        "delete_block": "operation_not_allowed_by_cleanup_contract",
        "remove_inline_noise": "operation_not_allowed_by_cleanup_contract",
    }
    # The two operations the live run measured as useful are accepted unchanged...
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == [
        "normalize_heading_boundary",
        "join_fragmented_paragraph",
    ]
    assert "TEAM PLAYBOOK\n\nShared ownership keeps delivery predictable." in result.cleaned_markdown
    assert _NARROWED_JOINED in result.cleaned_markdown
    # ...and the text the other two would have removed is still in the delivered book.
    assert "стр. 42" in result.cleaned_markdown
    assert _GLOBAL_SAFETY_NOISE_SUBSTRING in result.cleaned_markdown
    assert report["stats"]["accepted_delete_block_count"] == 0
    # The narrowing is advertised to the model, not only enforced after the fact.
    assert report["cleanup_settings"]["allowed_operations"] == [
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
    ]


def test_explicit_allowed_operations_restore_the_full_set_for_research_runs() -> None:
    """Non-vacuity for the test above, and the escape hatch investigative runs need.

    The very same response is accepted in full once a config (or a validation run profile)
    names the operations: the narrowing is a default, not a removal.
    """
    result = run_reader_cleanup(
        markdown_text=_NARROWED_MARKDOWN,
        config=resolve_reader_cleanup_config(
            app_config=_narrowed_set_app_config(
                reader_cleanup_allowed_operations=sorted(_ALLOWED_OPERATIONS),
            ),
            fallback_model="fallback:model",
        ),
        operation_provider=_narrowed_set_provider,
    )
    report = result.report_payload

    assert sorted(str(entry["operation"]) for entry in report["accepted_cleanup_operations"]) == [
        "delete_block",
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
        "remove_inline_noise",
    ]
    assert report["ignored_cleanup_operations"] == []
    assert "стр. 42" not in result.cleaned_markdown
    assert _GLOBAL_SAFETY_NOISE_SUBSTRING not in result.cleaned_markdown


def test_empty_allowed_operations_still_means_every_operation() -> None:
    # The pass's own convention (``_allowed_operations_for_config``) is unchanged: an empty
    # set is "no contract", i.e. everything. Only the ABSENCE of the key now means the
    # narrowed pair, so a run profile that clears the list still widens rather than mutes.
    config = resolve_reader_cleanup_config(
        app_config=_narrowed_set_app_config(reader_cleanup_allowed_operations=[]),
        fallback_model="fallback:model",
    )

    assert config.allowed_operations == ()


def test_global_safety_rollback_keeps_anchor_loss_blamed_on_the_operation_that_ran() -> None:
    # The rollback re-applies the remainder from scratch, so the write sets it returns are
    # keyed by position in the RETAINED list. ``service._reject_operations_losing_docx_image_anchors``
    # indexes the FULL operation sequence, so they have to be mapped back. Here the two
    # deletions come first, so an unmapped write set would blame a deletion for the anchor
    # the boundary operation destroyed, the boundary operation would run again in the retry,
    # the anchor would still be gone — and the whole book's cleanup would be discarded
    # instead of one operation being dropped.
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
        "стр. 42\n\n"
        f"{_GLOBAL_SAFETY_NOISE_BLOCK}\n\n"
        f"{_ANCHOR_FIGURE_BLOCK}\n\n"
        "стр. 43\n\n"
        "Заключительный абзац достаточной длины."
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        anchor = next(block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK)
        noise = next(block for block in payload["blocks"] if block["text"] == _GLOBAL_SAFETY_NOISE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    *(
                        _page_furniture_delete_operation(block)
                        for block in payload["blocks"]
                        if block["text"] in {"стр. 42", "стр. 43"}
                    ),
                    _inline_noise_operation(noise),
                    _anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, chunk_size=100000),
        operation_provider=provider,
    )
    report = result.report_payload

    # One operation dropped, not the book: the figure keeps its anchor, the deletions the
    # limit rejected are back in the text, and the unrelated inline cleanup still ships.
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    assert report["image_reconciliation"]["cleanup_discarded_for_missing_image_ids"] is False
    assert "стр. 42" in result.cleaned_markdown
    assert "стр. 43" in result.cleaned_markdown
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["remove_inline_noise"]
    assert [
        str(entry["operation"])
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "docx_image_anchor_lost_by_operation"
    ] == ["normalize_heading_boundary"]
    assert [
        str(entry["raw_text_preview"])
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "global_safety_limit_exceeded"
    ] == ["стр. 42", "стр. 43"]


def test_global_safety_rollback_records_carry_the_delete_block_operation_key() -> None:
    # Round-10 P3. These entries were built through ``_serialize_delete_block`` alone, which
    # emits no ``operation`` key — while the line directly beneath them, and every consumer
    # that counts refused deletions, selects ignore entries by
    # ``entry["operation"] == "delete_block"``. The rollback's own records were invisible to
    # the filter written to find them.
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
        "стр. 42\n\n"
        f"{_GLOBAL_SAFETY_NOISE_BLOCK}\n\n"
        "стр. 43\n\n"
        "Заключительный абзац достаточной длины."
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        noise = next(block for block in payload["blocks"] if block["text"] == _GLOBAL_SAFETY_NOISE_BLOCK)
        return json.dumps(
            {
                "cleanup_operations": [
                    *(
                        _page_furniture_delete_operation(block)
                        for block in payload["blocks"]
                        if block["text"] in {"стр. 42", "стр. 43"}
                    ),
                    _inline_noise_operation(noise),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, chunk_size=100000),
        operation_provider=provider,
    )
    rolled_back = [
        entry
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "global_safety_limit_exceeded"
    ]

    assert len(rolled_back) == 2
    assert [entry.get("operation") for entry in rolled_back] == ["delete_block", "delete_block"]
    # ...which is exactly the shape the neighbouring carry-over filter selects on.
    assert [entry for entry in rolled_back if entry.get("operation") == "delete_block"] == rolled_back


def test_anchor_repair_pass_losing_an_anchor_rolls_back_only_itself() -> None:
    # Round-9 P2-1. ``missing_after_repair`` was hardcoded to ``[]``, so the warning branch
    # for a repair-pass anchor loss was unreachable — and because the second reconciliation
    # was taken against the RAW source, the rollback also threw away the first pass, which
    # had lost nothing. Silently. The repair pass now rolls back to the first pass's
    # output, says so, and stops reporting its rolled-back operations as accepted.
    def main_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        page = next((block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK), None)
        if page is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {"cleanup_operations": [_page_furniture_delete_operation(page)], "warnings": []},
            ensure_ascii=False,
        )

    def anchor_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if str(payload.get("pass_name") or "") != "anchor_repair":
            return main_provider(payload, chunk_index, chunk_count)
        anchor = next((block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK), None)
        if anchor is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {
                "cleanup_operations": [_anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_"))],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_ANCHOR_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=main_provider,
        anchor_operation_provider=anchor_provider,
        anchor_targets=[
            {
                "category": "heading_fused_with_body",
                "block_id": "b_000002",
                "anchor_id": "a1",
                "snippet": "РИСУНОК 2.1",
            }
        ],
    )
    report = result.report_payload

    assert result.changed is True
    assert result.cleaned_markdown == _ANCHOR_MARKDOWN.replace(f"{_PAGE_FURNITURE_BLOCK}\n\n", "")
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_014"]
    assert report["image_reconciliation"]["missing_after_repair"] == ["img_014"]
    assert report["image_reconciliation"]["anchor_repair_discarded_for_missing_image_ids"] is True
    assert "reader_cleanup_image_ids_missing_after_reconcile:1" in report["warnings"]
    assert [entry["operation"] for entry in report["accepted_cleanup_operations"]] == ["delete_block"]
    assert report["stats"]["accepted_cleanup_operation_count"] == 1
    assert {
        str(entry["ignored_reason"])
        for entry in report["ignored_cleanup_operations"]
        if entry.get("pass_name") == "anchor_repair" and entry.get("operation") == "normalize_heading_boundary"
    } == {"anchor_repair_discarded_for_missing_docx_image_anchor"}


def test_rolled_back_anchor_repair_pass_is_un_accepted_in_its_own_sub_report_too() -> None:
    # Round-10 P2-1. The rollback fixed the top-level stats and chunk results and left
    # ``passes.anchor_repair_pass`` untouched, so one report asserted both "1 accepted" and
    # "0 accepted" about the same operation. The sub-report is not decoration: the
    # real-document validation harness reads ``passes.anchor_repair_pass.stats.
    # accepted_cleanup_operation_count`` to decide whether the pass ran, so a pass that
    # shipped nothing was recorded as ``anchor_repair_status="runtime_applied"``.
    def main_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        page = next((block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK), None)
        if page is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {"cleanup_operations": [_page_furniture_delete_operation(page)], "warnings": []},
            ensure_ascii=False,
        )

    def anchor_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if str(payload.get("pass_name") or "") != "anchor_repair":
            return main_provider(payload, chunk_index, chunk_count)
        anchor = next((block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK), None)
        if anchor is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {
                "cleanup_operations": [_anchor_splitting_boundary_operation(anchor, split_at=len("[[DOCX_IMAGE_"))],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=_ANCHOR_MARKDOWN,
        config=_permissive_anchor_config(),
        operation_provider=main_provider,
        anchor_operation_provider=anchor_provider,
        anchor_targets=[
            {
                "category": "heading_fused_with_body",
                "block_id": "b_000002",
                "anchor_id": "a1",
                "snippet": "РИСУНОК 2.1",
            }
        ],
    )
    report = result.report_payload
    anchor_repair_pass = report["passes"]["anchor_repair_pass"]

    assert anchor_repair_pass["stats"]["accepted_cleanup_operation_count"] == 0
    assert anchor_repair_pass["stats"]["accepted_delete_block_count"] == 0
    assert anchor_repair_pass["stats"]["ignored_cleanup_operation_count"] == 1
    assert anchor_repair_pass["stats"]["deleted_non_whitespace_char_count"] == 0
    assert anchor_repair_pass["stats"]["deleted_char_ratio"] == 0.0
    assert anchor_repair_pass["discarded_for_missing_docx_image_anchor"] is True
    assert anchor_repair_pass["lost_docx_image_ids"] == ["img_014"]
    assert [entry["accepted_cleanup_operation_count"] for entry in anchor_repair_pass["chunk_results"]] == [0]
    assert [entry["ignored_cleanup_operation_count"] for entry in anchor_repair_pass["chunk_results"]] == [1]
    # The first pass is untouched by the rollback and still ships its own deletion.
    assert report["stats"]["accepted_cleanup_operation_count"] == 1
    # The rollback also publishes the count the owner-facing notice is built from.
    assert report["image_reconciliation"]["anchor_repair_discarded_cleanup_operation_count"] == 1


def test_rolled_back_anchor_repair_delete_block_is_discarded_once_not_twice() -> None:
    # Round-11. An accepted ``delete_block`` is present in the report TWICE by construction:
    # ``_apply`` records the full operation in ``accepted_cleanup_operations`` and ``_parse``
    # records the SAME deletion again, more thinly, in ``accepted_delete_blocks``. The
    # rollback concatenated both lists, so one rolled-back deletion produced two ignore
    # records and inflated everything built from them — the owner-facing
    # "N operation(s) were dropped" notice, ``chunk_results`` and
    # ``passes.anchor_repair_pass.stats`` (which then reported more ignored operations than
    # the pass ever proposed). The duplicate also carried no ``operation`` key, so it was
    # invisible to the ``entry["operation"] == "delete_block"`` filters — the same blind spot
    # the ``global_safety_limit_exceeded`` rollback already had to close.
    page_anchor_block = "стр. 43"
    markdown = (
        "Вступительный абзац достаточной длины, чтобы его сохранить.\n\n"
        f"{_PAGE_FURNITURE_BLOCK}\n\n"
        f"{_ANCHOR_FIGURE_BLOCK}\n\n"
        f"{page_anchor_block}\n\n"
        "Заключительный абзац достаточной длины."
    )

    def main_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        page = next((block for block in payload["blocks"] if block["text"] == _PAGE_FURNITURE_BLOCK), None)
        if page is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {"cleanup_operations": [_page_furniture_delete_operation(page)], "warnings": []},
            ensure_ascii=False,
        )

    def anchor_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if str(payload.get("pass_name") or "") != "anchor_repair":
            return main_provider(payload, chunk_index, chunk_count)
        figure = next((block for block in payload["blocks"] if block["text"] == _ANCHOR_FIGURE_BLOCK), None)
        page = next((block for block in payload["blocks"] if block["text"] == page_anchor_block), None)
        if figure is None or page is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        # Two operations, one of them a deletion, and the other one destroys the figure
        # anchor — so the whole pass is rolled back and BOTH are un-accepted.
        return json.dumps(
            {
                "cleanup_operations": [
                    _page_furniture_delete_operation(page),
                    _anchor_splitting_boundary_operation(figure, split_at=len("[[DOCX_IMAGE_")),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=_permissive_anchor_config(),
        operation_provider=main_provider,
        anchor_operation_provider=anchor_provider,
        # Block ids are those of the post-first-pass document the anchor pass actually sees,
        # i.e. after "стр. 42" was deleted: figure b_000001, "стр. 43" b_000002.
        anchor_targets=[
            {
                "category": "heading_fused_with_body",
                "block_id": "b_000001",
                "anchor_id": "a1",
                "snippet": "РИСУНОК 2.1",
            },
            {
                "category": "fragmented_paragraph",
                "block_id": "b_000002",
                "anchor_id": "a2",
                "snippet": page_anchor_block,
            },
        ],
    )
    report = result.report_payload
    discarded = [
        entry
        for entry in report["ignored_cleanup_operations"]
        if entry.get("ignored_reason") == "anchor_repair_discarded_for_missing_docx_image_anchor"
    ]

    # The pass really did accept two operations and really did lose the anchor.
    assert report["image_reconciliation"]["missing_after_repair"] == ["img_014"]
    assert result.cleaned_markdown == markdown.replace(f"{_PAGE_FURNITURE_BLOCK}\n\n", "")

    # Two operations rolled back => two records, no more and no fewer, and NOTHING lost:
    # the deletion is still there, still identifiable, with its target block id intact.
    assert len(discarded) == 2
    assert sorted(str(entry["operation"]) for entry in discarded) == ["delete_block", "normalize_heading_boundary"]
    assert all("operation" in entry for entry in discarded)
    deleted = next(entry for entry in discarded if entry["operation"] == "delete_block")
    assert deleted["raw_text_preview"] == page_anchor_block
    assert sum(1 for entry in discarded if entry.get("operation") == "delete_block") == 1

    # Every counter fed from that list agrees, including the one the notice is built from.
    assert report["image_reconciliation"]["anchor_repair_discarded_cleanup_operation_count"] == 2
    anchor_chunk_results = [entry for entry in report["chunk_results"] if entry.get("pass_name") == "anchor_repair"]
    assert [entry["ignored_cleanup_operation_count"] for entry in anchor_chunk_results] == [2]
    assert [entry["ignored_delete_block_count"] for entry in anchor_chunk_results] == [2]
    anchor_repair_pass = report["passes"]["anchor_repair_pass"]
    assert anchor_repair_pass["stats"]["ignored_cleanup_operation_count"] == 2
    assert anchor_repair_pass["stats"]["ignored_delete_block_count"] == 2
    # A pass can never ignore more operations than it proposed.
    assert (
        anchor_repair_pass["stats"]["ignored_cleanup_operation_count"]
        <= anchor_repair_pass["stats"]["proposed_cleanup_operation_count"]
    )
    # The first pass is untouched by the rollback and still ships its own deletion.
    assert report["stats"]["accepted_cleanup_operation_count"] == 1


def test_schema_repair_prompt_states_required_fields_for_every_operation() -> None:
    # Round-11. The allowed-operations line was fixed to name
    # ``extract_side_heading_and_reattach_body``, but the line listing each operation's
    # mandatory fields still covered only five of six, so the repair model was told to keep
    # an operation whose schema it had never been given. The cleanup prompt has always named
    # the three fields; the two prompts must state the same contract.
    def _required_fields_line(prompt: str) -> str:
        return next(line for line in prompt.splitlines() if "must include split_substrings" in line)

    repair_line = _required_fields_line(build_reader_cleanup_schema_repair_system_prompt())
    assert repair_line == _required_fields_line(build_reader_cleanup_system_prompt())
    for field in ("pre_body_stub", "heading_substring", "post_body_continuation"):
        assert field in repair_line, field


def test_schema_repair_prompt_names_every_allowed_operation() -> None:
    # Round-10 P3. The line enumerating the allowed operations was edited when
    # ``reclassify_role`` was removed and left listing five of six — the schema-repair model
    # was told ``extract_side_heading_and_reattach_body`` does not exist while the applier
    # accepts it, so a repair pass could legitimately drop a valid operation.
    prompt = build_reader_cleanup_schema_repair_system_prompt()
    allowed_line = next(line for line in prompt.splitlines() if line.startswith("Keep the allowed operations unchanged:"))
    for operation in _ALLOWED_OPERATIONS:
        assert operation in allowed_line, operation


def test_max_failed_chunk_ratio_of_one_is_an_explicit_off_switch() -> None:
    # Round-10 P3. Changing ``>=`` to ``>`` silently turned 1.0 from "abort only when EVERY
    # chunk failed" into an unreachable threshold. That IS what the only caller setting it
    # wants (the research matrix disables the abort on purpose), but leaving it as an
    # arithmetic accident meant nothing said so and nothing tested it. It is now stated.
    def _chunk_results(*, failed: int, total: int) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        for index in range(total):
            results.append({"status": "failed" if index < failed else "completed"})
        return results

    off = ReaderCleanupConfig(enabled=True, max_failed_chunk_ratio=1.0)
    assert _failed_chunk_ratio_exceeds_threshold(chunk_results=_chunk_results(failed=10, total=10), config=off) is False
    assert _failed_chunk_ratio_exceeds_threshold(chunk_results=_chunk_results(failed=9, total=10), config=off) is False
    # Every threshold below the off-switch still aborts a total failure, so "abort when the
    # whole book failed" remains expressible — it is the default behaviour of any real limit.
    for threshold in (0.0, 0.1, 0.5, 0.9):
        config = ReaderCleanupConfig(enabled=True, max_failed_chunk_ratio=threshold)
        assert _failed_chunk_ratio_exceeds_threshold(chunk_results=_chunk_results(failed=10, total=10), config=config) is True


def test_toc_like_does_not_depend_on_block_length() -> None:
    # The rule used to accept "one line of at most 100 characters ending in a number" as a
    # sufficient contents signal, and length was doing all the work: the same sentence was
    # TOC-like at 99 characters and prose at 101. Length is no longer consulted at all — a
    # short line of prose and a long one are classified the same way, and a genuine index
    # line stays TOC-like at any length.
    short_prose = "Он родился в 1990"
    long_prose = short_prose + " " + "и вырос" * 30 + " 1995"
    assert _detect_block_kind(short_prose) == "paragraph"
    assert _detect_block_kind(long_prose) == "paragraph"

    short_index_entry = "Изобилие: в Куритибе, 142; устойчивое, 5–6, 55, 224"
    long_index_entry = short_index_entry + "; и ценность, 80" * 12
    assert _detect_block_kind(short_index_entry) == "toc_like"
    assert _detect_block_kind(long_index_entry) == "toc_like"


def test_reconcile_discards_the_cleanup_when_an_anchor_cannot_be_restored() -> None:
    # The reconciler's own contract, reached directly because the rejection layer answers
    # first in every end-to-end path: a lost anchor is never re-appended anywhere, and the
    # delivered markdown is the source, unchanged.
    raw_markdown = f"Intro paragraph.\n\n{_ANCHOR_FIGURE_BLOCK}\n\nOutro paragraph."
    cleaned_markdown = raw_markdown.replace("[[DOCX_IMAGE_img_014]]", "[[DOCX_IMAGE_\n\nimg_014]]")
    blocks = build_cleanup_blocks(raw_markdown)

    reconciled_markdown, image_reconciliation = _reconcile_docx_image_placeholders(
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        raw_blocks=blocks,
    )

    assert reconciled_markdown == raw_markdown
    assert image_reconciliation["cleanup_discarded_for_missing_image_ids"] is True
    assert image_reconciliation["missing_image_ids"] == ["img_014"]
    assert image_reconciliation["reinserted_image_ids"] == []
    assert image_reconciliation["lost_image_source_block_ids"] == ["b_000001"]
    assert _extract_docx_image_placeholder_ids(reconciled_markdown) == ["img_014"]


def test_run_reader_cleanup_reannotation_applies_heading_body_boundary_with_containment() -> None:
    markdown = "Intro\n\nEconomic consequences of wealth concentration Body starts here.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    target = blocks[1]

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(item for item in payload["blocks"] if item["id"] == target.block_id)
        return json.dumps(
            {
                "annotations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
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
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        annotation_provider=provider,
    )

    assert result.cleaned_markdown == "Intro\n\n## Economic consequences of wealth concentration\n\nBody starts here.\n\nOutro"
    assert result.report_payload["mode"] == "reannotation"
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1


def test_run_reader_cleanup_reannotation_applies_exact_list_items_with_containment() -> None:
    markdown = "Intro\n\n1. first item 2. second item 3. third item\n\nOutro"
    target = build_cleanup_blocks(markdown)[1]

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(item for item in payload["blocks"] if item["id"] == target.block_id)
        return json.dumps(
            {
                "annotations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "role": "list_item",
                        "confidence": "high",
                        "reason": "list_reassembly",
                        "list_items": ["1. first item", "2. second item", "3. third item"],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup_reannotation(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        annotation_provider=provider,
    )

    assert result.cleaned_markdown == "Intro\n\n- first item\n- second item\n- third item\n\nOutro"
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1


def test_run_reader_cleanup_reannotation_applies_exact_trailing_footnote_marker_with_containment() -> None:
    markdown = "Intro\n\nThe sentence ends here.25\n\nOutro"
    target = build_cleanup_blocks(markdown)[1]

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(item for item in payload["blocks"] if item["id"] == target.block_id)
        return json.dumps(
            {
                "annotations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "role": "footnote",
                        "confidence": "high",
                        "reason": "trailing_footnote_marker",
                        "body_text": "The sentence ends here.",
                        "marker_text": "25",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup_reannotation(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        annotation_provider=provider,
    )

    assert result.cleaned_markdown == "Intro\n\nThe sentence ends here.\n\n25\n\nOutro"
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1


def test_run_reader_cleanup_applies_safe_delete_operations() -> None:
    markdown = "Intro\n\nCompany Header\n\n10\n\nBody paragraph\n\nCompany Header\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            chunk_size=25,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: __import__("json").dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        block,
                        reason="page_number" if block["text"] == "10" else "repeated_running_header",
                        confidence="high",
                    )
                    for block in payload["blocks"]
                    if block["text"] in {"Company Header", "10"}
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nBody paragraph\n\nOutro"
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 3


def test_run_reader_cleanup_rejects_standalone_numeric_page_number_without_page_context() -> None:
    markdown = "Intro\n\n8\n\nBody paragraph\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    number_block = next(block for block in blocks if block.text == "8")

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        number_block,
                        reason="page_number",
                        confidence="high",
                        evidence_before="The model guessed this standalone number is a page number.",
                        safety_note="Standalone numeric deletion needs page context.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == (
        "standalone_number_delete_requires_page_context"
    )


def test_run_reader_cleanup_accepts_labeled_page_number_without_standalone_numeric_context() -> None:
    markdown = "Intro\n\nPage 8\n\nBody paragraph\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    page_block = next(block for block in blocks if block.text == "Page 8")

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        page_block,
                        reason="page_number",
                        confidence="high",
                        evidence_before="The line is explicitly labeled as a page number.",
                        safety_note="Labeled page-number furniture can be removed.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nBody paragraph\n\nOutro"
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 1


def test_run_reader_cleanup_preserves_semantic_standalone_list_number() -> None:
    markdown = "Intro\n\n1\n\nThe first principle explains the local currency rules.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    number_block = next(block for block in blocks if block.text == "1")

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        number_block,
                        reason="page_number",
                        confidence="high",
                        evidence_before="The model guessed this list marker is a page number.",
                        safety_note="A standalone semantic list number must be preserved without page context.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == (
        "standalone_number_delete_requires_page_context"
    )


def test_run_reader_cleanup_ignores_toc_blocks_when_keep_toc_is_false() -> None:
    markdown = "Intro\n\nChapter 1........ 12\n\nBody paragraph\n\nOutro"
    captured_block_texts: list[str] = []

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        captured_block_texts.extend(str(block["text"]) for block in payload["blocks"])
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, keep_toc=False),
        operation_provider=operation_provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert "Chapter 1........ 12" not in captured_block_texts
    assert "reader_cleanup_toc_blocks_ignored:1" in result.report_payload["warnings"]


def test_run_reader_cleanup_repairs_legacy_delete_blocks_into_audited_cleanup_operations() -> None:
    markdown = "Intro\n\nCompany Header\n\n10\n\nBody paragraph\n\nCompany Header\n\nOutro"

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        return json.dumps(
            {
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "page_number",
                        "confidence": "high",
                    }
                    for block in payload["blocks"]
                    if block["text"] == "10"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        original_response = payload["original_response"]
        repaired = []
        for item in original_response["delete_blocks"]:
            repaired.append(
                {
                    "id": item["id"],
                    "text_hash": item["text_hash"],
                    "operation": "delete_block",
                    "reason": item["reason"],
                    "confidence": item["confidence"],
                    "evidence_before": "10",
                    "expected_after_preview": "",
                    "safety_note": "Standalone page number block only.",
                }
            )
        return json.dumps({"cleanup_operations": repaired, "warnings": ["legacy repaired"]}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    accepted_operation = result.report_payload["accepted_cleanup_operations"][0]
    assert result.changed is True
    assert accepted_operation["operation"] == "delete_block"
    assert accepted_operation["evidence_before"] == "10"
    assert accepted_operation["expected_after_preview"] == ""
    assert accepted_operation["safety_note"] == "Standalone page number block only."
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_schema_repair_succeeded:1" in result.report_payload["warnings"]


def test_run_reader_cleanup_rejects_invalid_schema_in_advisory_mode() -> None:
    markdown = "Intro\n\nBody paragraph"
    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: '{"delete_blocks": [{"id": "b_000001", "text_hash": "x", "reason": "page_number", "confidence": "high", "extra": true}], "warnings": []}',
    )

    assert result.changed is False
    assert any("reader_cleanup_chunk_failed" in warning for warning in result.report_payload["warnings"])


@pytest.mark.parametrize("policy", ["advisory", "strict"])
def test_run_reader_cleanup_auth_error_raises_in_any_policy(policy: str) -> None:
    markdown = "Intro\n\nBody paragraph"

    with pytest.raises(ReaderCleanupStageError) as exc_info:
        run_reader_cleanup(
            markdown_text=markdown,
            config=ReaderCleanupConfig(enabled=True, policy=policy),
            operation_provider=lambda payload, chunk_index, chunk_count: (_ for _ in ()).throw(
                _FakeAuthError("unauthorized")
            ),
        )

    report_payload = exc_info.value.report_payload
    assert report_payload["stage_status"] == "failed"
    assert report_payload["changed"] is False
    assert report_payload["failure"]["kind"] == "auth_or_credential_error"
    assert report_payload["failure"]["status_code"] == 401
    assert report_payload["stats"]["failed_chunk_count"] == 1
    assert report_payload["chunk_results"][0]["failure_kind"] == "auth_or_credential_error"


def test_run_reader_cleanup_all_chunks_failed_exceeds_default_ratio_gate() -> None:
    markdown = "Intro\n\nPage 1\n\nBody paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=6, overlap_blocks_before=0, overlap_blocks_after=0),
        operation_provider=lambda payload, chunk_index, chunk_count: (_ for _ in ()).throw(TimeoutError("timeout")),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["stage_status"] == "failed"
    assert result.report_payload["failure"]["kind"] == "failed_chunk_ratio_exceeded"
    assert result.report_payload["failure"]["failed_chunk_ratio"] == 1.0
    assert result.report_payload["stats"]["cleanup_chunk_count"] == 3
    assert result.report_payload["stats"]["failed_chunk_count"] == 3
    assert result.report_payload["accepted_cleanup_operations"] == []
    assert any(
        str(warning).startswith("reader_cleanup_failed_chunk_ratio_exceeded:")
        for warning in result.report_payload["warnings"]
    )


def test_run_reader_cleanup_one_third_of_chunks_failing_aborts_the_pass() -> None:
    # Spec 052 item 2. This case used to report ``completed`` / ``changed: True`` and deliver
    # a book cleaned by two chunks out of three. At ``max_failed_chunk_ratio = 1.0`` the abort
    # fired only when EVERY chunk failed, so 106 of 107 failures were silent. One failure in
    # three is a 33% failure rate and must now abort with nothing applied.
    markdown = "Intro\n\nPage 1\n\nBody paragraph"

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if chunk_index == 3:
            raise TimeoutError("timeout")
        operations = [
            _delete_block_operation(block, reason="page_number")
            for block in payload["blocks"]
            if block["text"] == "Page 1"
        ]
        return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            policy="advisory",
            chunk_size=6,
            overlap_blocks_before=0,
            overlap_blocks_after=0,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=operation_provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["stage_status"] == "failed"
    assert result.report_payload["failure"]["kind"] == "failed_chunk_ratio_exceeded"
    assert result.report_payload["failure"]["max_failed_chunk_ratio"] == 0.1
    assert result.report_payload["stats"]["cleanup_chunk_count"] == 3
    assert result.report_payload["stats"]["failed_chunk_count"] == 1
    assert result.report_payload["accepted_delete_blocks"] == []
    assert any(
        warning.startswith("reader_cleanup_failed_chunk_ratio_exceeded:")
        for warning in result.report_payload["warnings"]
    )


def test_run_reader_cleanup_failure_rate_below_the_default_ratio_still_completes() -> None:
    # The other side of spec 052 item 2: 1 unavailable chunk out of 12 is 8.3%, below the
    # 10% default, so the pass still applies what it could and reports ``completed``.
    blocks = ["Intro", *[f"Body paragraph {index}" for index in range(1, 11)], "Page 1", "Outro"]
    markdown = "\n\n".join(blocks)

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if chunk_index == 3:
            raise TimeoutError("timeout")
        operations = [
            _delete_block_operation(block, reason="page_number")
            for block in payload["blocks"]
            if block["text"] == "Page 1"
        ]
        return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            policy="advisory",
            chunk_size=6,
            overlap_blocks_before=0,
            overlap_blocks_after=0,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=operation_provider,
    )

    assert result.report_payload["stats"]["cleanup_chunk_count"] == 13
    assert result.report_payload["stats"]["failed_chunk_count"] == 1
    assert result.report_payload["stage_status"] == "completed"
    assert "failure" not in result.report_payload
    assert result.changed is True
    assert "Page 1" not in result.cleaned_markdown


def test_run_reader_cleanup_failure_rate_exactly_at_the_ratio_still_completes() -> None:
    # Round-9 P2-3. The comparison was ``>=``, so a ten-chunk document that lost exactly one
    # chunk to a transient error hit ``0.1 >= 0.1`` and had its whole cleanup cancelled —
    # while the notice told the owner the rate was "above the allowed 10.0%", which it was
    # not. ``max_failed_chunk_ratio`` is the largest share still tolerated; 10 % of 10
    # chunks is tolerated, and only MORE than that aborts.
    blocks = ["Intro", *[f"Body paragraph {index}" for index in range(1, 8)], "Page 1", "Outro"]
    markdown = "\n\n".join(blocks)

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        if chunk_index == 3:
            raise TimeoutError("timeout")
        operations = [
            _delete_block_operation(block, reason="page_number")
            for block in payload["blocks"]
            if block["text"] == "Page 1"
        ]
        return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)

    config = ReaderCleanupConfig(
        enabled=True,
        policy="advisory",
        chunk_size=6,
        overlap_blocks_before=0,
        overlap_blocks_after=0,
        max_delete_block_ratio=0.8,
        max_delete_char_ratio=0.8,
    )
    result = run_reader_cleanup(markdown_text=markdown, config=config, operation_provider=operation_provider)

    assert result.report_payload["stats"]["cleanup_chunk_count"] == 10
    assert result.report_payload["stats"]["failed_chunk_count"] == 1
    assert config.max_failed_chunk_ratio == 0.1
    assert result.report_payload["stage_status"] == "completed"
    assert "failure" not in result.report_payload
    assert result.changed is True
    assert "Page 1" not in result.cleaned_markdown


def test_run_reader_cleanup_zero_tolerance_ratio_does_not_abort_a_run_without_failures() -> None:
    # The same off-by-one, at the other end: ``max_failed_chunk_ratio = 0.0`` used to make
    # ``0.0 >= 0.0`` true and abort every run, including runs where nothing failed at all.
    markdown = "Intro\n\nPage 1\n\nBody paragraph"

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        operations = [
            _delete_block_operation(block, reason="page_number")
            for block in payload["blocks"]
            if block["text"] == "Page 1"
        ]
        return json.dumps({"cleanup_operations": operations, "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            policy="advisory",
            max_failed_chunk_ratio=0.0,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=operation_provider,
    )

    assert result.report_payload["stats"]["failed_chunk_count"] == 0
    assert result.report_payload["stage_status"] == "completed"
    assert "failure" not in result.report_payload
    assert "Page 1" not in result.cleaned_markdown


def test_run_reader_cleanup_clean_noop_stays_completed() -> None:
    markdown = "Intro\n\nBody paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []},
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["stage_status"] == "completed"
    assert result.report_payload["stats"]["failed_chunk_count"] == 0


def test_reader_cleanup_schema_repair_prompt_forbids_rewritten_markdown() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt()

    assert "Return JSON only with top-level fields cleanup_operations and warnings." in prompt
    assert "Do not wrap it in markdown fences" in prompt
    assert '{"cleanup_operations":[],"warnings":[]}' in prompt
    assert "Do not return rewritten Markdown, cleaned Markdown, commentary, or extra top-level fields." in prompt
    assert "Repair every invalid cleanup operation item in the response, not only the first broken one." in prompt
    assert "If the original response uses legacy delete_blocks, convert it into cleanup_operations" in prompt
    assert "If a duplicate_fragment candidate is only similar to nearby prose" in prompt
    assert "Do not widen remove_inline_noise to consume a semantic heading" in prompt
    assert "noise_substring combines a page-like number with semantic section-title text" in prompt


def test_reader_cleanup_system_prompt_states_the_target_selection_contract() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "Return only a single valid JSON object" in prompt
    assert "Do not wrap it in markdown fences" in prompt
    assert '{"cleanup_operations":[],"warnings":[]}' in prompt
    assert "If one block needs both page-furniture removal and heading/body repair" in prompt
    assert "For fragmented paragraphs, use neighbor context" in prompt
    assert "For inline endnote/page marker artifacts inside prose" in prompt
    assert "exact deleted span in noise_substring" in prompt
    assert "For duplicate semantic heading text repeated inline" in prompt
    assert "Target category duplicate_semantic_heading_text" in prompt
    assert "Target category side_heading_island_candidate" in prompt
    assert "Target category semantic_page_title_deletion_risk" in prompt
    assert "Target category isolated_semantic_heading_numeric_prefix" in prompt
    assert "Target category heading_fused_with_body_candidate" in prompt
    assert "run join_fragmented_paragraph with that exact next block first, then normalize_heading_boundary" in prompt
    assert "Semantic heading islands are not noise" in prompt
    assert "Do not delete semantic heading islands with remove_inline_noise" in prompt
    assert "Semantic section titles and page-heading-like titles are not remove_inline_noise targets" in prompt
    assert "A page-like number adjacent to a semantic title is not permission to delete the title" in prompt
    assert "first try split_block, then normalize_heading_boundary" in prompt
    assert "extract_side_heading_and_reattach_body" in prompt
    assert "pre_body_stub" in prompt
    assert "do not leave a short pre-heading sentence stub" in prompt
    assert "expected_after_preview must be exactly: heading_substring, then a blank line" in prompt
    assert "do not add labels like '[Heading: ...]'" in prompt
    assert "a same-pass follow-up remove_inline_noise on the same original block id is supported" in prompt
    assert "do not remove the title with remove_inline_noise" in prompt
    assert "remove only the exact numeric prefix when safe; never remove the heading text" in prompt
    assert "do not propose remove_inline_noise for that combined span" in prompt
    assert "bad: remove_inline_noise for the whole '15 SHADE PLANTS FOR SMALL GARDENS?'" in prompt
    assert 'bad: remove_inline_noise "Три сорта зимостойких роз"' in prompt
    assert "Good: extract_side_heading_and_reattach_body" in prompt
    assert "page furniture plus an image caption sits between two parts of one sentence" in prompt
    assert "if the number is semantic content inside a sentence" in prompt
    assert "title-case running-header island with connector words or acronyms" in prompt
    assert "Дневник садовода 167" in prompt
    assert "3 Сад круглый год 201" in prompt
    assert "ТЕПЛИЦЫ И «ХОЛОДНЫЕ ПАРНИКИ»" in prompt
    assert "КОМПОСТ И ОРГАНИЧЕСКИЕ УДОБРЕНИЯ." in prompt
    assert "Стратегии для НКО 167" not in prompt
    assert "3 Управление и мы, граждане 201" not in prompt


def test_reader_cleanup_system_prompt_requires_full_heading_body_remainder() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "copy body_substring verbatim as the full semantic body remainder" in prompt
    assert "heading_substring must be the complete exact heading prefix" in prompt
    assert "body_substring must be the entire exact body remainder" in prompt
    assert "including all later sentences in that same block" in prompt
    assert "only copies the first few words instead of the full remaining semantic body text" in prompt
    assert "do not propose normalize_heading_boundary" in prompt
    assert "copying the full exact remainder" in prompt


def test_reader_cleanup_system_prompt_forbids_title_subtitle_as_heading_body() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "Title plus subtitle on one line is not automatically heading/body fusion" in prompt
    assert "short subtitle, subtitle question, or epigraph-like line rather than narrative prose" in prompt
    assert "do not force normalize_heading_boundary unless actual narrative prose starts after them" in prompt
    assert "TOC-like rows are not heading/body prose" in prompt


def test_run_reader_cleanup_ignores_removed_reclassify_role_without_failing_the_chunk() -> None:
    """A model that still remembers the old contract must not cost us the chunk."""
    markdown = "Intro paragraph\n\nTHE MERCANTILISTS: TRADE AND TREASURE\n\nBody paragraph\n\nOutro paragraph"
    repair_calls: list[int] = []

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(chunk_index)
        return json.dumps({"cleanup_operations": [], "warnings": []})

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _unknown_operation_item(
                        block,
                        operation="reclassify_role",
                        expected_after_preview="## THE MERCANTILISTS: TRADE AND TREASURE",
                        reason="semantic_heading",
                        extra={"target_role": "heading"},
                    )
                    for block in payload["blocks"]
                    if block["text"] == "THE MERCANTILISTS: TRADE AND TREASURE"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        repair_provider=repair_provider,
    )

    assert [entry["status"] for entry in result.report_payload["chunk_results"]] == ["completed"]
    assert result.report_payload["stage_status"] == "completed"
    assert result.report_payload["stats"]["failed_chunk_count"] == 0
    assert repair_calls == []
    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["accepted_cleanup_operations"] == []
    ignored = result.report_payload["ignored_cleanup_operations"]
    assert [(entry["operation"], entry["ignored_reason"]) for entry in ignored] == [
        ("reclassify_role", "operation_not_supported")
    ]
    assert ignored[0]["id"] == build_cleanup_blocks(markdown)[1].block_id
    assert any(
        warning.startswith("reader_cleanup_unsupported_operation_ignored:")
        and warning.endswith(":reclassify_role")
        for warning in result.report_payload["warnings"]
    )


def test_run_reader_cleanup_ignores_any_unknown_operation_name_with_a_recorded_reason() -> None:
    markdown = "Intro paragraph\n\nMiddle paragraph\n\nBody paragraph\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _unknown_operation_item(
                        block,
                        operation="rewrite_paragraph",
                        expected_after_preview="A nicer sentence.",
                        reason="page_number",
                        extra={"invented_field": "whatever"},
                    )
                    for block in payload["blocks"]
                    if block["text"] == "Middle paragraph"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert [entry["status"] for entry in result.report_payload["chunk_results"]] == ["completed"]
    assert result.changed is False
    assert result.cleaned_markdown == markdown
    ignored = result.report_payload["ignored_cleanup_operations"]
    assert [(entry["operation"], entry["ignored_reason"]) for entry in ignored] == [
        ("rewrite_paragraph", "operation_not_supported")
    ]


def test_reader_cleanup_contract_advertises_six_operations_without_reclassify_role() -> None:
    markdown = "Intro paragraph\n\nMiddle paragraph\n\nOutro paragraph"
    captured: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        captured.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []})

    run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=provider,
    )

    contract = captured[0]["response_contract"]
    assert contract["allowed_operations"] == [
        "delete_block",
        "extract_side_heading_and_reattach_body",
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
        "remove_inline_noise",
        "split_block",
    ]
    assert "reclassify" not in json.dumps(captured[0], ensure_ascii=False)
    assert "reclassify" not in build_reader_cleanup_system_prompt()
    assert "reclassify" not in build_reader_cleanup_schema_repair_system_prompt()


def test_reader_cleanup_schema_repair_prompt_mentions_fragmented_anchor_join_safety() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt(include_anchor_repair_guidance=True)

    assert "For anchor_repair fragmented_paragraph items" in prompt
    assert "next_id and next_text_hash are copied from an adjacent block in the current request payload" in prompt
    assert "do not convert a non-exact duplicate-looking tail into delete_block duplicate_fragment" in prompt


def test_run_reader_cleanup_retries_empty_non_json_response_once() -> None:
    markdown = "Intro\n\nBody paragraph"
    calls = 0

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            return "   "
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=operation_provider,
    )

    assert calls == 2
    assert result.changed is False
    assert result.report_payload["chunk_results"][0]["retry_attempted"] is True
    assert result.report_payload["chunk_results"][0]["retry_status"] == "succeeded"
    assert "reader_cleanup_non_json_response_retry_succeeded:1" in result.report_payload["warnings"]


def test_run_reader_cleanup_accepts_json_object_wrapped_in_model_prose() -> None:
    markdown = "Intro\n\nBody paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: (
            "I will return the JSON now.\n"
            '{"cleanup_operations":[],"warnings":["kept text"]}\n'
            "Done."
        ),
    )

    assert result.changed is False
    assert result.report_payload["chunk_results"][0]["status"] == "completed"
    assert "kept text" in result.report_payload["warnings"]


def test_run_reader_cleanup_records_failed_empty_response_diagnostics_after_retry() -> None:
    markdown = "Intro\n\nBody paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, model="anthropic:claude-sonnet-4-6", policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: "",
    )

    chunk_result = result.report_payload["chunk_results"][0]
    diagnostics = chunk_result["failure_diagnostics"]
    assert result.report_payload["stats"]["failed_chunk_count"] == 1
    assert chunk_result["retry_attempted"] is True
    assert chunk_result["retry_status"] == "failed"
    assert diagnostics["chunk_index"] == 1
    assert diagnostics["primary_block_id_range"] == {"first": "b_000000", "last": "b_000001"}
    assert diagnostics["cleanup_model_selector"] == "anthropic:claude-sonnet-4-6"
    assert diagnostics["request_payload_char_count"] > 0
    assert diagnostics["raw_response_empty"] is True
    assert diagnostics["raw_response_preview"] == ""
    assert "Expecting value" in diagnostics["parse_error_message"]


def test_run_reader_cleanup_repairs_schema_once_and_applies_repaired_operation() -> None:
    target = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
    markdown = f"Intro\n\n{target}\n\nOutro"
    repair_calls: list[dict[str, Any]] = []

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(payload)
        original_response = payload["original_response"]
        repaired_operation = dict(original_response["cleanup_operations"][0])
        repaired_operation.update(
            {
                "evidence_before": "Page furniture is fused to the semantic paragraph prefix.",
                "expected_after_preview": "Через призму рабочего процесса можно увидеть новые возможности для команды.",
                "safety_note": "Only the non-semantic heading fragment should be removed.",
            }
        )
        return json.dumps({"cleanup_operations": [repaired_operation], "warnings": ["schema repaired"]}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    assert len(repair_calls) == 1
    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\nЧерез призму рабочего процесса можно увидеть новые возможности для команды.\n\nOutro"
    )
    assert any("reader_cleanup_schema_validation_failed:1:" in warning for warning in result.report_payload["warnings"])
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_schema_repair_succeeded:1" in result.report_payload["warnings"]
    assert result.report_payload["chunk_results"][0]["repair_attempted"] is True
    assert result.report_payload["chunk_results"][0]["repair_status"] == "succeeded"


def test_run_reader_cleanup_routes_missing_inline_preview_through_schema_repair() -> None:
    target_noise = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
    target_heading = "ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства."
    markdown = f"Intro\n\n{target_noise}\n\n{target_heading}\n\nOutro"
    repair_calls: list[dict[str, Any]] = []

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        noise_block = next(block for block in payload["blocks"] if block["text"] == target_noise)
        heading_block = next(block for block in payload["blocks"] if block["text"] == target_heading)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": noise_block["id"],
                        "text_hash": noise_block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "Page furniture is fused to the semantic paragraph prefix.",
                        "safety_note": "Only the exact non-semantic heading fragment should be removed.",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА ",
                    },
                    {
                        "id": heading_block["id"],
                        "text_hash": heading_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A sentence-style section heading and the first sentence are fused in one paragraph.",
                        "expected_after_preview": "ОБРАЗОВАНИЕ. / Расходы на образование обычно ложатся на плечи федерального правительства.",
                        "safety_note": "Split only the exact copied heading and exact copied body remainder.",
                        "heading_substring": "ОБРАЗОВАНИЕ.",
                        "body_substring": "Расходы на образование обычно ложатся на плечи федерального правительства.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(payload)
        original_response = payload["original_response"]
        repaired_operations = [dict(operation) for operation in original_response["cleanup_operations"]]
        repaired_operations[0]["expected_after_preview"] = (
            "Через призму рабочего процесса можно увидеть новые возможности для команды."
        )
        return json.dumps({"cleanup_operations": repaired_operations, "warnings": ["schema repaired"]}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    assert len(repair_calls) == 1
    assert result.changed is True
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_schema_repair_succeeded:1" in result.report_payload["warnings"]
    assert not any(
        warning.startswith("reader_cleanup_expected_after_preview_recovered:1:")
        for warning in result.report_payload["warnings"]
    )
    assert "Через призму рабочего процесса можно увидеть новые возможности для команды." in result.cleaned_markdown
    assert "ОБРАЗОВАНИЕ.\n\nРасходы на образование обычно ложатся на плечи федерального правительства." in result.cleaned_markdown
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 2
    recovered_entry = next(
        entry
        for entry in result.report_payload["accepted_cleanup_operations"]
        if entry["operation"] == "remove_inline_noise"
    )
    assert recovered_entry["expected_after_preview"] == "Через призму рабочего процесса можно увидеть новые возможности для команды."


def test_run_reader_cleanup_repair_failure_is_noop_in_advisory_mode() -> None:
    target = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        original_response = payload["original_response"]
        repaired_operation = dict(original_response["cleanup_operations"][0])
        repaired_operation["expected_after_preview"] = "Через призму рабочего процесса можно увидеть новые возможности для команды."
        return json.dumps({"cleanup_operations": [repaired_operation], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert any("reader_cleanup_schema_repair_failed:1:" in warning for warning in result.report_payload["warnings"])
    assert any("reader_cleanup_chunk_failed:1:" in warning for warning in result.report_payload["warnings"])
    assert result.report_payload["chunk_results"][0]["repair_attempted"] is True
    assert result.report_payload["chunk_results"][0]["repair_status"] == "failed"


def test_run_reader_cleanup_repair_failure_stays_fail_closed_in_strict_mode() -> None:
    target = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        return json.dumps({"cleanup_operations": [{"operation": "remove_inline_noise"}], "warnings": []}, ensure_ascii=False)

    with pytest.raises(ReaderCleanupStageError) as exc_info:
        run_reader_cleanup(
            markdown_text=markdown,
            config=ReaderCleanupConfig(enabled=True, policy="strict"),
            operation_provider=operation_provider,
            repair_provider=repair_provider,
    )

    report_payload = exc_info.value.report_payload
    assert report_payload["stage_status"] == "failed"
    assert report_payload["chunk_results"][0]["repair_attempted"] is True
    assert report_payload["chunk_results"][0]["repair_status"] == "failed"
    assert any("reader_cleanup_schema_repair_failed:1:" in warning for warning in report_payload["warnings"])


def test_run_reader_cleanup_cleanup_operations_delete_block_requires_audit_fields() -> None:
    markdown = "Intro\n\nCompany Header\n\n10\n\nBody paragraph\n\nCompany Header\n\nOutro"
    repair_calls: list[dict[str, Any]] = []

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        contract = payload["response_contract"]
        assert "allowed_delete_reasons" in contract
        assert "page_number" in contract["allowed_delete_reasons"]
        assert "page_furniture_inline" in contract["reason_guidance_by_operation"]["remove_inline_noise"]
        block = next(block for block in payload["blocks"] if block["text"] == "10")
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "delete_block",
                        "reason": "page_number",
                        "confidence": "high",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(payload)
        repaired_operation = dict(payload["original_response"]["cleanup_operations"][0])
        repaired_operation.update(
            {
                "evidence_before": "Standalone page number block.",
                "expected_after_preview": "",
                "safety_note": "Only the page number block is deleted.",
            }
        )
        return json.dumps({"cleanup_operations": [repaired_operation], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    assert len(repair_calls) == 1
    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nCompany Header\n\nBody paragraph\n\nCompany Header\n\nOutro"
    assert any("reader_cleanup_schema_validation_failed:1:" in warning for warning in result.report_payload["warnings"])



def test_run_reader_cleanup_anchor_pass_receives_only_selected_windows_and_preserves_anchor_identity() -> None:
    markdown = "Intro\n\nAlpha heading body\n\nMiddle\n\nBeta heading body\n\nTail\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    payloads: list[dict[str, Any]] = []

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, chunk_size=20, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-a",
                "category": "heading_fused_with_body",
                "block_id": blocks[1].block_id,
                "line_ref": "2",
                "snippet": blocks[1].text,
            },
            {
                "anchor_id": "anchor-b",
                "category": "heading_fused_with_body",
                "block_id": blocks[3].block_id,
                "line_ref": "6",
                "snippet": blocks[3].text,
            },
        ),
    )

    assert result.changed is False
    assert payloads
    assert all(len(payload["blocks"]) < len(blocks) for payload in payloads)
    anchor_ids = [
        anchor["anchor_id"]
        for payload in payloads
        for anchor in payload["anchor_targets"]
    ]
    assert anchor_ids == ["anchor-a", "anchor-b"]
    assert result.report_payload["passes"]["anchor_repair_pass"]["selected_anchor_count"] == 2


def test_run_reader_cleanup_anchor_pass_cannot_edit_blocks_outside_editable_window() -> None:
    markdown = "Intro\n\nHeading body\n\nMiddle\n\nOutside target\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        outside_block = blocks[3]
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": outside_block.block_id,
                        "text_hash": outside_block.text_hash,
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": outside_block.text,
                        "expected_after_preview": "target",
                        "safety_note": "invalid out-of-window edit",
                        "noise_substring": "Outside ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-a",
                "category": "heading_fused_with_body",
                "block_id": blocks[1].block_id,
                "line_ref": "2",
                "snippet": blocks[1].text,
            },
        ),
    )

    assert result.changed is False
    assert any("reader_cleanup_anchor_chunk_failed:1:reader_cleanup_block_outside_chunk:" in warning for warning in result.report_payload["warnings"])
    assert result.report_payload["passes"]["anchor_repair_pass"]["stats"]["accepted_cleanup_operation_count"] == 0


def test_run_reader_cleanup_anchor_pass_reanchors_stale_block_id_by_exact_snippet() -> None:
    markdown = "Intro\n\nStale block text\n\n190 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ Потребность в глобальной валюте.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    payloads: list[dict[str, Any]] = []

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        payloads.append(payload)
        target = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": target["id"],
                        "text_hash": target["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": target["text"],
                        "expected_after_preview": "Потребность в глобальной валюте.",
                        "safety_note": "Remove only the exact page number and running header prefix.",
                        "noise_substring": "190 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-page",
                "category": "page_furniture_inline",
                "block_id": blocks[1].block_id,
                "line_ref": "3",
                "snippet": "190 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ Потребность в глобальной валюте",
            },
        ),
    )

    assert result.changed is True
    assert "190 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ" not in result.cleaned_markdown
    assert payloads[0]["anchor_targets"][0]["block_id"] == blocks[2].block_id
    assert any(
        warning.startswith("reader_cleanup_anchor_target_reanchored_by_exact_snippet:1:")
        for warning in result.report_payload["passes"]["anchor_repair_pass"]["warnings"]
    )


def test_run_reader_cleanup_invalid_anchor_pass_response_is_noop_in_advisory_mode() -> None:
    markdown = "Intro\n\nTitle body\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": blocks[1].block_id,
                        "text_hash": blocks[1].text_hash,
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "heading_substring": "Title",
                        "body_substring": "body",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
        anchor_targets=(
            {
                "anchor_id": "anchor-a",
                "category": "heading_fused_with_body",
                "block_id": blocks[1].block_id,
                "line_ref": "2",
                "snippet": blocks[1].text,
            },
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert any("reader_cleanup_anchor_chunk_failed:1:reader_cleanup_operation_missing_required_field:" in warning for warning in result.report_payload["warnings"])


def test_run_reader_cleanup_report_separates_first_pass_and_anchor_pass_stats() -> None:
    markdown = "Intro\n\nКАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target_block = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": target_block["id"],
                        "text_hash": target_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": target_block["text"],
                        "expected_after_preview": "КАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.",
                        "safety_note": "Split the heading from the paragraph body.",
                        "heading_substring": "КАК ЭТО РАБОТАЕТ:",
                        "body_substring": "Местные органы власти могут помочь.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-a",
                "category": "heading_fused_with_body",
                "block_id": blocks[1].block_id,
                "line_ref": "2",
                "snippet": blocks[1].text,
            },
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nКАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.\n\nOutro"
    assert result.report_payload["passes"]["first_pass"]["stats"]["accepted_cleanup_operation_count"] == 0
    assert result.report_payload["passes"]["anchor_repair_pass"]["stats"]["accepted_cleanup_operation_count"] == 1
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1


def test_run_reader_cleanup_anchor_schema_repair_receives_anchor_context_and_applies_fix() -> None:
    markdown = "Intro\n\nКАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    repair_payloads: list[dict[str, Any]] = []

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target_block = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": target_block["id"],
                        "text_hash": target_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "heading_substring": "КАК ЭТО РАБОТАЕТ:",
                        "body_substring": "Местные органы власти могут помочь.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_payloads.append(payload)
        repaired_operation = dict(payload["original_response"]["cleanup_operations"][0])
        repaired_operation.update(
            {
                "evidence_before": "Uppercase heading plus body prose share one block.",
                "expected_after_preview": "КАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.",
                "safety_note": "Keep exact body prose and split only the heading boundary.",
            }
        )
        return json.dumps({"cleanup_operations": [repaired_operation], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory"),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        repair_provider=repair_provider,
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-a",
                "category": "heading_fused_with_body",
                "block_id": blocks[1].block_id,
                "line_ref": "2",
                "snippet": blocks[1].text,
            },
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nКАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.\n\nOutro"
    assert len(repair_payloads) == 1
    assert repair_payloads[0]["pass_name"] == "anchor_repair"
    assert repair_payloads[0]["anchor_targets"][0]["category"] == "heading_fused_with_body"
    assert repair_payloads[0]["anchor_window_block_ids"] == [blocks[0].block_id, blocks[1].block_id, blocks[2].block_id]
    assert repair_payloads[0]["context_before_preview"] == ""
    assert repair_payloads[0]["context_after_preview"] == ""
    assert [block["id"] for block in repair_payloads[0]["blocks"]] == [
        blocks[0].block_id,
        blocks[1].block_id,
        blocks[2].block_id,
    ]
    assert "reader_cleanup_anchor_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_anchor_schema_repair_succeeded:1" in result.report_payload["warnings"]


def test_run_reader_cleanup_fragmented_paragraph_anchor_window_uses_wider_context() -> None:
    markdown = "A\n\nB\n\nCaption fragment,\n\nlowercase continuation\n\nE\n\nF"
    blocks = build_cleanup_blocks(markdown)
    payloads: list[dict[str, Any]] = []

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-frag",
                "category": "fragmented_paragraph",
                "block_id": blocks[2].block_id,
                "line_ref": "5",
                "snippet": blocks[2].text,
            },
        ),
    )

    assert result.changed is False
    assert len(payloads) == 1
    assert [block["id"] for block in payloads[0]["blocks"]] == [
        blocks[0].block_id,
        blocks[1].block_id,
        blocks[2].block_id,
        blocks[3].block_id,
        blocks[4].block_id,
    ]


def test_run_reader_cleanup_anchor_repair_joins_fragmented_paragraph_with_exact_adjacent_hash() -> None:
    markdown = (
        "Intro\n\n"
        "Кооперативная валюта помогла району удержать местную торговлю,\n\n"
        "и жители продолжили обменивать услуги без дополнительных долгов.\n\n"
        "Outro"
    )
    blocks = build_cleanup_blocks(markdown)
    payloads: list[dict[str, Any]] = []

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        payloads.append(payload)
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

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-frag",
                "category": "fragmented_paragraph",
                "block_id": blocks[1].block_id,
                "line_ref": "3",
                "snippet": blocks[1].text,
            },
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Кооперативная валюта помогла району удержать местную торговлю, "
        "и жители продолжили обменивать услуги без дополнительных долгов.\n\n"
        "Outro"
    )
    anchor_pass = result.report_payload["passes"]["anchor_repair_pass"]
    assert anchor_pass["selected_anchor_count"] == 1
    assert anchor_pass["stats"]["accepted_cleanup_operation_count"] == 1
    assert result.report_payload["accepted_cleanup_operations"][-1]["pass_name"] == "anchor_repair"
    assert payloads[0]["anchor_targets"][0]["category"] == "fragmented_paragraph"


def test_run_reader_cleanup_anchor_repair_rejects_non_anchor_block_delete_inside_window() -> None:
    markdown = "Intro\n\n190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ Особый интерес представляет система.\n\nУправление и мы, граждане.\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        non_anchor_block = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": non_anchor_block["id"],
                        "text_hash": non_anchor_block["text_hash"],
                        "operation": "delete_block",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": non_anchor_block["text"],
                        "expected_after_preview": "",
                        "safety_note": "Do not delete neighboring non-anchor blocks during bounded anchor repair.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-page",
                "category": "page_furniture_inline",
                "block_id": blocks[1].block_id,
                "line_ref": "3",
                "snippet": "190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ Особый интерес",
            },
        ),
    )

    assert result.changed is False
    assert result.report_payload["passes"]["anchor_repair_pass"]["stats"]["accepted_delete_block_count"] == 0
    assert result.report_payload["ignored_cleanup_operations"][-1]["ignored_reason"] == (
        "anchor_repair_operation_outside_anchor_targets"
    )


def test_run_reader_cleanup_anchor_repair_rejects_page_furniture_join_instead_of_noise_removal() -> None:
    markdown = (
        "Intro\n\n"
        "190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ Особый интерес представляет система.\n\n"
        "Лидер избирается большинством голосов.\n\n"
        "Outro"
    )
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
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
                        "evidence_before": first["text"],
                        "expected_after_preview": first["text"] + " " + second["text"],
                        "safety_note": "Wrong operation for a page furniture prefix anchor.",
                        "next_id": second["id"],
                        "next_text_hash": second["text_hash"],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-page",
                "category": "page_furniture_inline",
                "block_id": blocks[1].block_id,
                "line_ref": "3",
                "snippet": "190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ Особый интерес",
            },
        ),
    )

    assert result.changed is False
    assert result.report_payload["passes"]["anchor_repair_pass"]["stats"]["accepted_cleanup_operation_count"] == 0
    assert result.report_payload["ignored_cleanup_operations"][-1]["ignored_reason"] == (
        "anchor_repair_page_furniture_requires_remove_inline_noise"
    )


def test_run_reader_cleanup_anchor_repair_removes_page_caption_noise_then_joins_previous_fragment() -> None:
    previous = "Как отмечалось в статье журнала Time: «Один из самых верных признаков того, что вы находитесь в"
    current = (
        "166 ПРОЦВЕТАНИЕ Коста Грамматис со спутником связи Echostar 16 в штаб-квартире Loral "
        "в Пало-Альто, Калифорния. Фото: A Human Right. развивающейся стране, — это мусор под ногами."
    )
    noise = (
        "166 ПРОЦВЕТАНИЕ Коста Грамматис со спутником связи Echostar 16 в штаб-квартире Loral "
        "в Пало-Альто, Калифорния. Фото: A Human Right. "
    )
    markdown = f"Intro\n\n{previous}\n\n{current}\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        previous_block = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        current_block = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": current_block["id"],
                        "text_hash": current_block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": current_block["text"],
                        "expected_after_preview": "развивающейся стране, — это мусор под ногами.",
                        "safety_note": "Remove only the exact page header and image caption span.",
                        "noise_substring": noise,
                    },
                    {
                        "id": previous_block["id"],
                        "text_hash": previous_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "fragmented_paragraph",
                        "confidence": "high",
                        "evidence_before": previous_block["text"],
                        "expected_after_preview": (
                            previous
                            + " развивающейся стране, — это мусор под ногами."
                        ),
                        "safety_note": "After exact page/caption removal, join the unfinished previous sentence to the lowercase continuation.",
                        "next_id": current_block["id"],
                        "next_text_hash": current_block["text_hash"],
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "anchor-page-caption",
                "category": "page_furniture_inline",
                "block_id": blocks[2].block_id,
                "line_ref": "5",
                "snippet": "166 ПРОЦВЕТАНИЕ Коста Грамматис со спутником связи",
            },
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        + previous
        + " развивающейся стране, — это мусор под ногами.\n\n"
        "Outro"
    )
    anchor_pass = result.report_payload["passes"]["anchor_repair_pass"]
    assert anchor_pass["stats"]["accepted_cleanup_operation_count"] == 2
    assert anchor_pass["stats"]["accepted_delete_block_count"] == 0
    assert [entry["operation"] for entry in result.report_payload["accepted_cleanup_operations"][-2:]] == [
        "remove_inline_noise",
        "join_fragmented_paragraph",
    ]


def test_run_reader_cleanup_anchor_repair_reanchors_stale_page_caption_then_joins_next_continuation() -> None:
    current = (
        "10 Он объясняет, что люди могут зарабатывать локальную валюту. "
        "Как отмечалось в статье журнала Time: «Один из самых верных признаков того, что вы находитесь в"
        "Коста Грамматис рядом со спутником связи Echostar 16 в штаб-квартире Loral "
        "в Пало-Альто, Калифорния. Photo credit: A Human Right."
    )
    continuation = (
        "развивающейся стране, — это мусор у вас под ногами. И дело здесь не столько в дурных привычках."
    )
    noise = (
        "Коста Грамматис рядом со спутником связи Echostar 16 в штаб-квартире Loral "
        "в Пало-Альто, Калифорния. Photo credit: A Human Right."
    )
    stale_snippet = (
        "166 ПРОЦВЕТАНИЕ Коста Грамматис со спутником связи Echostar 16 в штаб-квартире Loral "
        "в Пало-Альто, Калифорния. Фото: A Human Right. развивающейся стране, — это мусор под ногами"
    )
    markdown = f"Intro\n\n{current}\n\n{continuation}\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    def anchor_operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        current_block = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        continuation_block = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": current_block["id"],
                        "text_hash": current_block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": noise,
                        "expected_after_preview": current_block["text"].replace(noise, "", 1),
                        "safety_note": "Remove only the exact image caption span after an unfinished sentence.",
                    },
                    {
                        "id": current_block["id"],
                        "text_hash": current_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "fragmented_paragraph",
                        "confidence": "high",
                        "evidence_before": current_block["text"],
                        "expected_after_preview": current_block["text"].replace(noise, "", 1) + " " + continuation,
                        "safety_note": "Join the exact adjacent lowercase continuation after caption removal.",
                        "next_id": continuation_block["id"],
                        "next_text_hash": continuation_block["text_hash"],
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {"cleanup_operations": [], "warnings": []}, ensure_ascii=False
        ),
        anchor_operation_provider=anchor_operation_provider,
        anchor_targets=(
            {
                "anchor_id": "stale-page-caption",
                "category": "page_furniture_inline",
                "block_id": blocks[2].block_id,
                "line_ref": "261",
                "snippet": stale_snippet,
            },
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "10 Он объясняет, что люди могут зарабатывать локальную валюту. "
        "Как отмечалось в статье журнала Time: «Один из самых верных признаков того, что вы находитесь в "
        + continuation
        + "\n\nOutro"
    )
    anchor_pass = result.report_payload["passes"]["anchor_repair_pass"]
    assert anchor_pass["selected_anchors"][0]["block_id"] == blocks[1].block_id
    assert any(
        warning.startswith("reader_cleanup_anchor_target_reanchored_by_page_caption_signal:1:")
        for warning in anchor_pass["warnings"]
    )
    assert "reader_cleanup_exact_fields_recovered:1:b_000001:remove_inline_noise" in anchor_pass["warnings"]
    assert anchor_pass["stats"]["accepted_cleanup_operation_count"] == 2
    assert anchor_pass["stats"]["accepted_delete_block_count"] == 0
    assert [entry["operation"] for entry in result.report_payload["accepted_cleanup_operations"][-2:]] == [
        "remove_inline_noise",
        "join_fragmented_paragraph",
    ]


def test_run_reader_cleanup_rejects_missing_confidence_extraction_artifact_delete_for_image_anchor() -> None:
    markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="extraction_artifact", confidence=None)
                    for block in payload["blocks"]
                    if block["text"] == "[[DOCX_IMAGE_img_001]]"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    # Spec 052 item 4: the anchor is no longer an ``extraction_artifact`` block, so the
    # "safe" confidence inference that used to promote this delete to ``high`` on the
    # strength of the reason matching the kind cannot fire at all. The delete is now
    # refused a step earlier than the ``docx_image_anchor_protected`` validator check,
    # which is exactly the point of giving anchors their own kind.
    assert not any(
        warning.startswith("reader_cleanup_missing_confidence_inferred")
        for warning in result.report_payload["warnings"]
    )
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 0
    assert _extract_docx_image_placeholder_ids(result.cleaned_markdown) == ["img_001"]
    # The item without a confidence never becomes a valid operation now, so the chunk is a
    # schema failure rather than a silently downgraded delete.
    assert any(
        "reader_cleanup_missing_field:confidence" in warning for warning in result.report_payload["warnings"]
    )


def test_image_anchor_blocks_carry_their_own_kind_not_extraction_artifact() -> None:
    # Spec 052 item 4. ``extraction_artifact`` is on the allowed-deletion list while the
    # prompt forbids touching anchors; on the three measured books 100% of the blocks that
    # carried that kind were image anchors (43/43, 55/55, 24/24).
    blocks = build_cleanup_blocks(
        "Intro\n\n[[DOCX_IMAGE_img_001]]\n\n[[DOCX_IMAGE_img_002]]\n[[DOCX_IMAGE_img_003]]\n\n"
        "[[DOCX_IMAGE_img_004]] Рисунок 1. Подпись\n\n<placeholder>\n\nOutro"
    )
    kinds = {block.block_id: block.kind for block in blocks}

    assert kinds["b_000001"] == "docx_image_anchor"
    # A block of several anchors and nothing else is still just anchors.
    assert kinds["b_000002"] == "docx_image_anchor"
    # An anchor fused with a caption is ordinary text, not an anchor block.
    assert kinds["b_000003"] == "paragraph"
    # A genuine extraction artifact keeps its kind — the deletion route is not removed.
    assert kinds["b_000004"] == "extraction_artifact"
    assert "docx_image_anchor" not in _ALLOWED_DELETE_REASONS


def test_run_reader_cleanup_rejects_extraction_artifact_delete_of_image_anchor_on_kind() -> None:
    # Defence in depth (spec 052 item 4): the anchor kind makes the reason incompatible AND
    # the ``docx_image_anchor_protected`` validator still fires. The class of defect this
    # guards once cost 20-37 images per book, so it keeps two independent refusals.
    markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nBody paragraph\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="extraction_artifact", confidence="high")
                    for block in payload["blocks"]
                    if block["text"] == "[[DOCX_IMAGE_img_001]]"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert "[[DOCX_IMAGE_img_001]]" in result.cleaned_markdown
    ignored = [
        entry for entry in result.report_payload["ignored_cleanup_operations"] if entry.get("id") == "b_000001"
    ]
    assert [entry["ignored_reason"] for entry in ignored] == ["docx_image_anchor_protected"]
    assert [entry["kind"] for entry in ignored] == ["docx_image_anchor"]


def test_run_reader_cleanup_rejects_incompatible_duplicate_operation_with_explicit_reason() -> None:
    markdown = "Intro\n\nCompany Header\n\n10\n\nBody paragraph\n\nCompany Header\n\nOutro"
    blocks = build_cleanup_blocks(markdown)
    number_block = next(block for block in blocks if block.text == "10")

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": number_block.block_id,
                        "text_hash": number_block.text_hash,
                        "operation": "delete_block",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "Standalone page number block.",
                        "expected_after_preview": "",
                        "safety_note": "Only the page number block should be removed.",
                    },
                    {
                        "id": number_block.block_id,
                        "text_hash": number_block.text_hash,
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "A second operation incorrectly tries to edit the same removed block.",
                        "expected_after_preview": "Body paragraph",
                        "safety_note": "This should be rejected as an incompatible same-block duplicate.",
                        "noise_substring": "10",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nCompany Header\n\nBody paragraph\n\nCompany Header\n\nOutro"
    assert result.report_payload["stats"]["failed_chunk_count"] == 0
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "duplicate_operation_incompatible"


def test_run_reader_cleanup_reports_heading_boundary_application_diagnostics() -> None:
    markdown = (
        "Intro\n\n"
        "РАБОЧИЙ ЗАГОЛОВОК Нормальный текст начинается здесь.\n\n"
        "Цитата перед заголовком занимает место. СЛОЖНЫЙ ЗАГОЛОВОК Основной текст после заголовка.\n\n"
        "Outro"
    )
    blocks = build_cleanup_blocks(markdown)

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first = next(block for block in payload["blocks"] if block["id"] == blocks[1].block_id)
        second = next(block for block in payload["blocks"] if block["id"] == blocks[2].block_id)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first["id"],
                        "text_hash": first["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "likely_heading_body_patterns",
                        "confidence": "high",
                        "evidence_before": first["text"],
                        "expected_after_preview": "РАБОЧИЙ ЗАГОЛОВОК\n\nНормальный текст начинается здесь.",
                        "safety_note": "Separates exact heading prefix from body.",
                        "heading_substring": "РАБОЧИЙ ЗАГОЛОВОК",
                        "body_substring": "Нормальный текст начинается здесь.",
                    },
                    {
                        "id": second["id"],
                        "text_hash": second["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "likely_heading_body_patterns",
                        "confidence": "high",
                        "evidence_before": second["text"],
                        "expected_after_preview": "СЛОЖНЫЙ ЗАГОЛОВОК\n\nОсновной текст после заголовка.",
                        "safety_note": "This should be diagnosed because semantic text precedes the heading.",
                        "heading_substring": "СЛОЖНЫЙ ЗАГОЛОВОК",
                        "body_substring": "Основной текст после заголовка.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, policy="advisory", chunk_size=1000),
        operation_provider=operation_provider,
    )

    diagnostics = result.report_payload["heading_boundary_application_diagnostics"]
    assert diagnostics["accepted_count"] == 1
    assert diagnostics["ignored_count"] == 1
    assert diagnostics["ignored_reason_counts"] == {"heading_boundary_unaccounted_text": 1}
    assert diagnostics["ignored_examples"][0]["heading_substring"] == "СЛОЖНЫЙ ЗАГОЛОВОК"
    assert diagnostics["ignored_examples"][0]["ignored_reason"] == "heading_boundary_unaccounted_text"


def test_run_reader_cleanup_does_not_infer_missing_confidence_for_heading_delete() -> None:
    markdown = "Intro\n\n# Chapter 1\n\nBody paragraph\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="page_furniture_heading", confidence=None)
                    for block in payload["blocks"]
                    if block["text"] == "# Chapter 1"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert any("reader_cleanup_chunk_failed:1:reader_cleanup_missing_field:confidence" in warning for warning in result.report_payload["warnings"])


def test_run_reader_cleanup_protects_first_last_and_headings() -> None:
    markdown = "# Chapter 1\n\nBody paragraph\n\n10"
    blocks = build_cleanup_blocks(markdown)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(blocks[0], reason="page_furniture_heading", confidence="medium"),
                    _delete_block_operation(blocks[2], reason="page_number", confidence="high"),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.cleaned_markdown == markdown
    ignored = result.report_payload["ignored_delete_blocks"]
    assert {entry["ignored_reason"] for entry in ignored} == {"heading_protected", "protected_block"}


def test_run_reader_cleanup_preserves_footnote_body_like_block() -> None:
    markdown = "Intro\n\n[12] This footnote body explains the citation in full detail.\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="repeated_running_header", confidence="high")
                    for block in payload["blocks"]
                    if block["text"].startswith("[12]")
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    ignored = result.report_payload["ignored_delete_blocks"]
    assert len(ignored) == 1
    assert ignored[0]["kind"] == "footnote_body"
    assert ignored[0]["ignored_reason"] == "footnote_body_protected"


def test_write_reader_cleanup_diagnostics_derives_paths_from_cleaned_artifact_family(tmp_path: Path) -> None:
    cleaned_markdown = tmp_path / "20260522_report.result.md"
    cleaned_markdown.write_text("cleaned", encoding="utf-8")

    artifact_paths = write_reader_cleanup_diagnostics(
        cleaned_artifact_paths={"markdown_path": str(cleaned_markdown)},
        raw_markdown="raw body",
        report_payload={"version": 1, "changed": True},
    )

    raw_markdown_path = Path(artifact_paths["reader_cleanup_raw_markdown_path"])
    report_path = Path(artifact_paths["reader_cleanup_report_path"])

    assert raw_markdown_path.name == "20260522_report.raw.result.md"
    assert report_path.name == "20260522_report.reader_cleanup_report.json"
    assert raw_markdown_path.read_text(encoding="utf-8") == "raw body"


def test_run_reader_cleanup_rejects_normal_paragraph_list_and_blockquote_deletions() -> None:
    markdown = "Intro paragraph\n\n- list item\n\n> quoted text\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="page_number", confidence="high")
                    for block in payload["blocks"]
                    if block["kind"] in {"paragraph", "list", "blockquote"}
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert {entry["ignored_reason"] for entry in result.report_payload["ignored_delete_blocks"]} == {"reason_kind_incompatible"}


def test_run_reader_cleanup_requires_repetition_evidence_for_running_header_reason() -> None:
    markdown = "Intro\n\nSingle header candidate\n\nBody\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="repeated_running_header", confidence="high")
                    for block in payload["blocks"]
                    if block["text"] == "Single header candidate"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    ignored = result.report_payload["ignored_delete_blocks"]
    assert len(ignored) == 1
    assert ignored[0]["ignored_reason"] == "missing_repetition_evidence"


def test_write_reader_cleanup_diagnostics_preserves_exact_raw_input_and_report_hashes(tmp_path: Path) -> None:
    markdown = "\n\nIntro\n\nHeader\n\nHeader\n\nBody\n"
    cleanup_result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="repeated_running_header", confidence="high")
                    for block in payload["blocks"]
                    if block["text"] == "Header"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    artifact_paths = write_reader_cleanup_diagnostics(
        cleaned_artifact_paths={"markdown_path": str(tmp_path / "family.result.md")},
        raw_markdown=cleanup_result.raw_markdown,
        report_payload=cleanup_result.report_payload,
    )

    sidecar_path = Path(artifact_paths["reader_cleanup_raw_markdown_path"])
    report_path = Path(artifact_paths["reader_cleanup_report_path"])

    assert sidecar_path.read_text(encoding="utf-8") == markdown
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    original_blocks = build_cleanup_blocks(markdown)
    accepted_hashes = {entry["text_hash"] for entry in report_payload["accepted_delete_blocks"]}
    expected_hashes = {block.text_hash for block in original_blocks if block.text == "Header"}
    assert accepted_hashes == expected_hashes
    assert {entry["after_state"] for entry in report_payload["accepted_delete_blocks"]} == {"deleted"}


def test_run_reader_cleanup_noop_preserves_whitespace_exactly() -> None:
    markdown = "\n\nIntro\n\n\nBody\n\n"
    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: '{"delete_blocks": [], "warnings": []}',
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown


def test_run_reader_cleanup_reports_chunk_metrics_and_unsupported_drop_back_matter_warning() -> None:
    markdown = "Intro\n\nCompany Header\n\nBody paragraph\n\nCompany Header\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            chunk_size=25,
            drop_back_matter=True,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(block, reason="repeated_running_header", confidence="high")
                    for block in payload["blocks"]
                    if block["text"] == "Company Header"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    stats = result.report_payload["stats"]
    assert "drop_back_matter_unsupported_noop" in result.report_payload["warnings"]
    assert stats["cleanup_chunk_count"] >= 2
    assert stats["proposed_delete_block_count"] == 2
    assert stats["accepted_delete_block_count"] == 2
    assert stats["ignored_delete_block_count"] == 0
    assert all("elapsed_ms" in entry for entry in result.report_payload["chunk_results"])
    assert all("accepted_delete_block_count" in entry for entry in result.report_payload["chunk_results"])


def test_run_reader_cleanup_sends_overlap_as_readonly_context_and_ignores_context_targets() -> None:
    markdown = "Alpha\n\nBeta\n\nGamma"
    seen_overlap_payload = False

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        nonlocal seen_overlap_payload
        if chunk_index != 2:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

        seen_overlap_payload = True
        editable_ids = set(payload["editable_block_ids"])
        context_blocks = list(payload["readonly_context_blocks_before"]) + list(payload["readonly_context_blocks_after"])
        assert {block["text"] for block in context_blocks} == {"Alpha", "Gamma"}
        assert not editable_ids & {block["id"] for block in context_blocks}
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": block["text"],
                        "expected_after_preview": "",
                        "safety_note": "read-only overlap context must not be edited",
                        "noise_substring": block["text"],
                    }
                    for block in context_blocks
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            chunk_size=7,
            overlap_blocks_before=1,
            overlap_blocks_after=1,
        ),
        operation_provider=provider,
    )

    assert seen_overlap_payload is True
    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["cleanup_settings"]["overlap_blocks_before"] == 1
    assert result.report_payload["cleanup_settings"]["overlap_blocks_after"] == 1
    assert result.report_payload["chunk_results"][1]["readonly_context_before_count"] == 1
    assert result.report_payload["chunk_results"][1]["readonly_context_after_count"] == 1
    assert {
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
    } == {"readonly_context_block"}


def test_run_reader_cleanup_applies_split_fused_heading_body_operation() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "Uppercase heading-like prefix is fused to a sentence.",
                        "expected_after_preview": "СТРАТЕГИИ РАЗВИТИЯ / Деньги — это рычаг власти.",
                        "safety_note": "Both parts are exact substrings from the original block.",
                        "heading_substring": "СТРАТЕГИИ РАЗВИТИЯ",
                        "body_substring": "Деньги — это рычаг власти.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "СТРАТЕГИИ РАЗВИТИЯ\n\nДеньги — это рычаг власти." in result.cleaned_markdown
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 1
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 0


def test_run_reader_cleanup_applies_safe_same_block_composed_inline_noise_and_heading_boundary() -> None:
    target = "Обзор для команды 145 КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "A title-case running header plus page number is fused to the heading block.",
                        "expected_after_preview": "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        "safety_note": "Only the exact running-header prefix should be removed first.",
                        "noise_substring": "Обзор для команды 145 ",
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "The remaining block still fuses the heading with the body sentence.",
                        "expected_after_preview": "КАК ЭТО РАБОТАЕТ: / Местные органы власти могут помочь.",
                        "safety_note": "After prefix removal, split the exact heading from the exact body remainder.",
                        "heading_substring": "КАК ЭТО РАБОТАЕТ:",
                        "body_substring": "Местные органы власти могут помочь.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nКАК ЭТО РАБОТАЕТ:\n\nМестные органы власти могут помочь.\n\nOutro"
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 2
    assert result.report_payload["ignored_delete_blocks"] == []


def test_run_reader_cleanup_reorders_same_block_operations_to_canonical_sequence() -> None:
    target = "Workspace notes 14 TEAM PLAYBOOK Shared ownership keeps delivery predictable."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "The remaining heading and body should be separated after the inline prefix is removed.",
                        "expected_after_preview": "TEAM PLAYBOOK / Shared ownership keeps delivery predictable.",
                        "safety_note": "Keep the exact heading prefix and the exact body remainder start.",
                        "heading_substring": "TEAM PLAYBOOK",
                        "body_substring": "Shared ownership keeps delivery predictable.",
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "A title-case running header and page number precede the section heading.",
                        "expected_after_preview": "TEAM PLAYBOOK Shared ownership keeps delivery predictable.",
                        "safety_note": "Remove only the exact non-semantic prefix first.",
                        "noise_substring": "Workspace notes 14 ",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nTEAM PLAYBOOK\n\nShared ownership keeps delivery predictable.\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == ["remove_inline_noise", "normalize_heading_boundary"]
    assert all(entry.get("sequence_decision") == "operation_sequence_reordered" for entry in accepted_operations)


def test_run_reader_cleanup_applies_split_then_post_split_inline_noise_on_same_block() -> None:
    target = "Командная заметка 145 КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "separate running header from semantic content",
                        "confidence": "high",
                        "evidence_before": "The block fuses a title-case running header, a heading, and body prose.",
                        "expected_after_preview": "Командная заметка 145 / КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        "safety_note": "Split the exact running-header fragment away first.",
                        "split_substrings": [
                            "Командная заметка 145",
                            "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        ],
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "After the split, the first fragment is pure running-header furniture.",
                        "expected_after_preview": "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        "safety_note": "Remove only the exact first split fragment, not the semantic heading/body fragment.",
                        "noise_substring": "Командная заметка 145\n\n",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nКАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == ["split_block", "remove_inline_noise"]
    assert result.report_payload["ignored_delete_blocks"] == []


def test_run_reader_cleanup_reports_ignored_reason_when_post_split_noise_target_is_impossible() -> None:
    target = "Командная заметка 145 КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "separate running header from semantic content",
                        "confidence": "high",
                        "evidence_before": "The block fuses a title-case running header, a heading, and body prose.",
                        "expected_after_preview": "Командная заметка 145 / КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        "safety_note": "This split is intentionally impossible because it omits exact source characters.",
                        "split_substrings": [
                            "Командная заметка",
                            "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        ],
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "This second operation should not look partially successful if the split never applied.",
                        "expected_after_preview": "КАК ЭТО РАБОТАЕТ: Местные органы власти могут помочь.",
                        "safety_note": "Executor must report explicit same-block sequencing failure after the rejected split.",
                        "noise_substring": "Командная заметка 145\n\n",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    ignored_operations = result.report_payload["ignored_delete_blocks"]
    assert [entry["ignored_reason"] for entry in ignored_operations] == [
        "split_substrings_not_exact_block_cover",
        "prior_same_block_operation_not_applied",
    ]


def test_run_reader_cleanup_applies_numeric_uppercase_inline_noise_then_heading_boundary() -> None:
    target = "162 ПРОЦВЕТАНИЕ ГРАЖДАНСКОЕ ОБЩЕСТВО И НЕКОММЕРЧЕСКИЙ СЕКТОР Через призму кооперативных валют открывается новая роль."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A page number and uppercase running header precede the semantic section title.",
                        "expected_after_preview": "ГРАЖДАНСКОЕ ОБЩЕСТВО И НЕКОММЕРЧЕСКИЙ СЕКТОР Через призму кооперативных валют открывается новая роль.",
                        "safety_note": "Remove only the exact page-furniture prefix before heading normalization.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ ",
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "After prefix removal, the remaining block still fuses the heading with the body sentence.",
                        "expected_after_preview": "ГРАЖДАНСКОЕ ОБЩЕСТВО И НЕКОММЕРЧЕСКИЙ СЕКТОР / Через призму кооперативных валют открывается новая роль.",
                        "safety_note": "Split the exact heading from the exact body remainder after inline cleanup succeeds.",
                        "heading_substring": "ГРАЖДАНСКОЕ ОБЩЕСТВО И НЕКОММЕРЧЕСКИЙ СЕКТОР",
                        "body_substring": "Через призму кооперативных валют открывается новая роль.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "ГРАЖДАНСКОЕ ОБЩЕСТВО И НЕКОММЕРЧЕСКИЙ СЕКТОР\n\nЧерез призму кооперативных валют открывается новая роль.\n\n"
        "Outro"
    )
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 2
    assert result.report_payload["ignored_delete_blocks"] == []


def test_reader_cleanup_prompt_guides_heading_boundary_vs_split_choice() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "Uppercase heading plus normal narrative prose belongs to normalize_heading_boundary" in prompt
    assert "Uppercase heading with a colon plus narrative prose belongs to normalize_heading_boundary" in prompt
    assert "Heading ending with a period plus narrative prose belongs to normalize_heading_boundary" in prompt
    assert "A short uppercase heading followed by narrative prose may still be a real heading" in prompt
    assert "If non-heading text remains before the heading candidate" in prompt
    assert "Part title after a preceding quote: use split_block, not normalize_heading_boundary" in prompt
    assert "heading_substring and body_substring for normalize_heading_boundary must match the exact post-prefix remainder" in prompt
    assert "Do not return a partial heading tail from the middle or last words of a wrapped heading" in prompt
    assert "copy body_substring verbatim as the full semantic body remainder after that boundary" in prompt
    assert "not just a teaser" in prompt
    assert "expected_after_preview must show the exact post-apply result for that same block" in prompt
    assert "Use normalize_heading_boundary only when the heading is an exact prefix" in prompt
    assert "always propose remove_inline_noise for the exact non-semantic prefix first" in prompt
    assert "Do not use normalize_heading_boundary to remove a numeric running-header prefix" in prompt
    assert "If body_substring is not copied verbatim from the current block text" in prompt
    assert "do not widen remove_inline_noise to consume the semantic heading" in prompt
    assert "Running-header prefix plus semantic heading plus prose" in prompt
    assert "Title-case running header island inside a sentence" in prompt
    assert "Title plus subtitle on one line is not automatically heading/body fusion" in prompt
    assert "Do not treat TOC-like rows, table-like rows, list rows, title+subtitle pairs, title+question pairs, or epigraph-only continuations as heading/body prose" in prompt
    assert "Sentence-style heading fused to prose" in prompt
    assert "ВЕСЕННИЙ УХОД: ПОДГОТОВКА ГРЯДОК К ПОСАДКЕ" in prompt
    assert "САДОВЫЙ ИНВЕНТАРЬ Перед началом сезона" in prompt
    assert "МУЛЬЧИРОВАНИЕ И ПРОПОЛКА. Основные приёмы" in prompt
    assert "4 Посадка рассады 57 5 Полив и подкормка" in prompt
    assert "ГРАЖДАНСКАЯ ВАЛЮТА: ЭКОНОМИЧЕСКИЙ СТИМУЛ БЕЗ ДОЛГОВ" not in prompt
    assert "4 Летучая рыба: новый взгляд на деньги 57 5 Будущее уже наступило" not in prompt
    assert "duplicate_fragment" in prompt


def test_reader_cleanup_schema_repair_prompt_preserves_bounded_title_case_running_header_islands() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt()

    assert "title-case running-header island with connector words or acronyms" in prompt
    assert "keep it as remove_inline_noise" in prompt


def test_reader_cleanup_prompt_does_not_encourage_title_subtitle_or_question_as_body_prose() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "ИТОГИ СЕЗОНА: краткий обзор" in prompt
    assert "ОСЕННИЕ РАБОТЫ Что дальше?" in prompt
    assert "do not force normalize_heading_boundary unless actual narrative prose starts after them" in prompt


def test_run_reader_cleanup_splits_uppercase_heading_with_colon_and_prose() -> None:
    target = (
        "МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ "
        "В пилотном городе результаты общественной программы заслуживают внимания."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "An uppercase heading with a colon is fused to the first narrative sentence.",
                        "expected_after_preview": (
                            "МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ / "
                            "В пилотном городе результаты общественной программы заслуживают внимания."
                        ),
                        "safety_note": "Keep the full uppercase colon heading and the full prose tail exactly.",
                        "heading_substring": "МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ",
                        "body_substring": "В пилотном городе результаты общественной программы заслуживают внимания.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert (
        "МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ\n\n"
        "В пилотном городе результаты общественной программы заслуживают внимания."
    ) in result.cleaned_markdown


def test_run_reader_cleanup_splits_heading_ending_with_period_and_prose() -> None:
    target = (
        "ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ. "
        "Ключевые аспекты городской программы остаются обязательными."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A heading ending with a period is fused to the first prose sentence.",
                        "expected_after_preview": (
                            "ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ. / "
                            "Ключевые аспекты городской программы остаются обязательными."
                        ),
                        "safety_note": "Preserve the full heading including the period and split before the body sentence.",
                        "heading_substring": "ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ.",
                        "body_substring": "Ключевые аспекты городской программы остаются обязательными.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert (
        "ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ.\n\n"
        "Ключевые аспекты городской программы остаются обязательными."
    ) in result.cleaned_markdown


def test_run_reader_cleanup_splits_short_uppercase_heading_with_narrative_prose() -> None:
    target = (
        "РАБОЧАЯ ГРУППА Во время пилотного проекта участники искали устойчивое решение."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A short uppercase heading is fused to a normal narrative sentence.",
                        "expected_after_preview": (
                            "РАБОЧАЯ ГРУППА / Во время пилотного проекта участники искали устойчивое решение."
                        ),
                        "safety_note": "Keep the short uppercase heading and the exact narrative prose tail.",
                        "heading_substring": "РАБОЧАЯ ГРУППА",
                        "body_substring": "Во время пилотного проекта участники искали устойчивое решение.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "РАБОЧАЯ ГРУППА\n\nВо время пилотного проекта участники искали устойчивое решение." in result.cleaned_markdown


def test_run_reader_cleanup_splits_sentence_style_heading_boundary_with_exact_body() -> None:
    target = "ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A sentence-style section heading and the first sentence are fused in one paragraph.",
                        "expected_after_preview": "ОБРАЗОВАНИЕ. / Расходы на образование обычно ложатся на плечи федерального правительства.",
                        "safety_note": "Split only the exact copied heading and exact copied body remainder.",
                        "heading_substring": "ОБРАЗОВАНИЕ.",
                        "body_substring": "Расходы на образование обычно ложатся на плечи федерального правительства.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "ОБРАЗОВАНИЕ.\n\nРасходы на образование обычно ложатся на плечи федерального правительства." in result.cleaned_markdown


def test_run_reader_cleanup_preserves_full_remainder_for_unique_heading_prefix_boundary() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти. Второе предложение тоже должно сохраниться."
    body = "Деньги — это рычаг власти. Второе предложение тоже должно сохраниться."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "Uppercase heading-like prefix is fused to a multi-sentence paragraph.",
                        "expected_after_preview": "СТРАТЕГИИ РАЗВИТИЯ / Деньги — это рычаг власти. Второе предложение тоже должно сохраниться.",
                        "safety_note": "Heading stays exact and the full remainder stays in order.",
                        "heading_substring": "СТРАТЕГИИ РАЗВИТИЯ",
                        "body_substring": body,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "СТРАТЕГИИ РАЗВИТИЯ\n\nДеньги — это рычаг власти. Второе предложение тоже должно сохраниться." in result.cleaned_markdown


def test_run_reader_cleanup_accepts_full_exact_prefix_heading_body_remainder() -> None:
    target = (
        "СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ Во время пилотного проекта команда проверила новую модель. "
        "Второе предложение остается частью того же абзаца."
    )
    body = (
        "Во время пилотного проекта команда проверила новую модель. "
        "Второе предложение остается частью того же абзаца."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A genuine prefix heading is fused to normal narrative prose.",
                        "expected_after_preview": f"СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ\n\n{body}",
                        "safety_note": "Split only the complete exact heading prefix and full exact body remainder.",
                        "heading_substring": "СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ",
                        "body_substring": body,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == f"Intro\n\nСОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ\n\n{body}\n\nOutro"
    assert result.report_payload["ignored_delete_blocks"] == []


def test_run_reader_cleanup_rejects_heading_boundary_when_body_anchor_would_drop_meaningful_prefix() -> None:
    target = "ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The proposed body starts too late and would drop semantic words from the beginning of the sentence.",
                        "expected_after_preview": "ОБРАЗОВАНИЕ. / обычно ложатся на плечи федерального правительства.",
                        "safety_note": "Reject when the body anchor would skip meaningful content from the fused paragraph.",
                        "heading_substring": "ОБРАЗОВАНИЕ.",
                        "body_substring": "обычно ложатся на плечи федерального правительства.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_unaccounted_text"


def test_run_reader_cleanup_rejects_heading_boundary_with_nonexistent_body_text() -> None:
    target = "СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ Во время пилотного проекта команда проверила новую модель."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The proposed body text is not an exact substring from the block.",
                        "expected_after_preview": "СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ / Во время проекта команда проверила новую модель.",
                        "safety_note": "Reject when the body substring is edited instead of copied exactly.",
                        "heading_substring": "СОЦИАЛЬНЫЕ ИНСТРУМЕНТЫ",
                        "body_substring": "Во время проекта команда проверила новую модель.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_substrings_not_found"


def test_run_reader_cleanup_recovers_heading_boundary_fields_from_exact_preview() -> None:
    target = "ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A section heading and the first sentence are fused in one paragraph.",
                        "expected_after_preview": (
                            "ОБРАЗОВАНИЕ.\n\n"
                            "Расходы на образование обычно ложатся на плечи федерального правительства."
                        ),
                        "safety_note": "Recover exact split fields only from the exact preview.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "ОБРАЗОВАНИЕ.\n\nРасходы на образование обычно ложатся на плечи федерального правительства." in result.cleaned_markdown
    assert any(
        warning.startswith("reader_cleanup_exact_fields_recovered:1:")
        and warning.endswith(":normalize_heading_boundary")
        for warning in result.report_payload["warnings"]
    )
    assert result.report_payload["ignored_cleanup_operations"] == []


def test_run_reader_cleanup_rejects_ambiguous_heading_boundary_heading_substring() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The same heading-like phrase appears twice in one block.",
                        "expected_after_preview": "СТРАТЕГИИ РАЗВИТИЯ / Деньги — это рычаг власти.",
                        "safety_note": "Do not split unless the heading boundary is unique.",
                        "heading_substring": "СТРАТЕГИИ РАЗВИТИЯ",
                        "body_substring": "Деньги — это рычаг власти.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_heading_ambiguous"


def test_run_reader_cleanup_rejects_heading_boundary_when_non_heading_text_precedes_heading() -> None:
    target = "«Цитата перед заголовком». 18 ЧАСТЬ ТРЕТЬЯ. ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ В процессе переосмысления денег случались ошибки."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "A quote and footnote marker precede the part title in the same block.",
                        "expected_after_preview": "ЧАСТЬ ТРЕТЬЯ. ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ / В процессе переосмысления денег случались ошибки.",
                        "safety_note": "This should be rejected because non-heading text appears before the heading.",
                        "heading_substring": "ЧАСТЬ ТРЕТЬЯ. ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ",
                        "body_substring": "В процессе переосмысления денег случались ошибки.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_unaccounted_text"


def test_run_reader_cleanup_rejects_heading_boundary_with_nonexistent_heading_text() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The proposed heading text is not exact.",
                        "expected_after_preview": "СТРАТЕГИИ РАЗВИТИЯ / Деньги — это рычаг власти.",
                        "safety_note": "No new heading text may be invented.",
                        "heading_substring": "СТРАТЕГИИ УПРАВЛЕНИЯ",
                        "body_substring": "Деньги — это рычаг власти.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_substrings_not_found"


def test_run_reader_cleanup_accepts_duplicate_fragment_delete_when_tail_matches_nearby_preserved_text() -> None:
    duplicate_tail = "keeps trust visible across the whole team."
    markdown = (
        "Intro\n\n"
        f"Shared planning keeps delivery predictable and {duplicate_tail}\n\n"
        f"{duplicate_tail}\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        duplicate_block = next(block for block in payload["blocks"] if block["text"] == duplicate_tail)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        duplicate_block,
                        reason="duplicate_fragment",
                        confidence="high",
                        evidence_before="This block repeats the tail of the immediately preceding paragraph.",
                        safety_note="Delete only when the full normalized block is already preserved nearby.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.changed is True
    assert result.cleaned_markdown == f"Intro\n\nShared planning keeps delivery predictable and {duplicate_tail}\n\nOutro"
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 1


def test_run_reader_cleanup_accepts_duplicate_fragment_after_nearby_separator_blocks() -> None:
    duplicate_tail = "keeps trust visible across the whole team and preserves the operating context."
    markdown = (
        "Intro\n\n"
        f"Shared planning keeps delivery predictable and {duplicate_tail}\n\n"
        "[IMAGE]\n\n"
        "Figure 12. Planning circle\n\n"
        f"{duplicate_tail}\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        duplicate_block = next(block for block in payload["blocks"] if block["text"] == duplicate_tail)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        duplicate_block,
                        reason="duplicate_fragment",
                        confidence="high",
                        evidence_before="This block repeats the tail of a nearby paragraph across separator blocks.",
                        safety_note="Delete only when the full normalized block is already preserved nearby.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        f"Shared planning keeps delivery predictable and {duplicate_tail}\n\n"
        "[IMAGE]\n\n"
        "Figure 12. Planning circle\n\n"
        "Outro"
    )
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 1


def test_run_reader_cleanup_rejects_duplicate_fragment_delete_when_match_is_ambiguous() -> None:
    duplicate_tail = "keeps trust visible across the whole team."
    markdown = (
        "Intro\n\n"
        f"Shared planning keeps delivery predictable and {duplicate_tail}\n\n"
        f"{duplicate_tail}\n\n"
        f"Retrospectives also {duplicate_tail}\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        duplicate_block = next(block for block in payload["blocks"] if block["text"] == duplicate_tail)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        duplicate_block,
                        reason="duplicate_fragment",
                        confidence="high",
                        evidence_before="This block appears to repeat nearby prose, but the evidence is ambiguous.",
                        safety_note="Reject if more than one nearby preserved block could justify the deletion.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "duplicate_fragment_ambiguous_neighbor_match"


def test_run_reader_cleanup_rejects_duplicate_fragment_delete_with_unique_continuation() -> None:
    duplicate_tail = "keeps trust visible across the whole team and unlocks a fresh escalation path."
    markdown = (
        "Intro\n\n"
        "Shared planning keeps delivery predictable and keeps trust visible across the whole team.\n\n"
        f"{duplicate_tail}\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        duplicate_block = next(block for block in payload["blocks"] if block["text"] == duplicate_tail)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        duplicate_block,
                        reason="duplicate_fragment",
                        confidence="high",
                        evidence_before="The block starts like a duplicate tail but continues with unique semantic content.",
                        safety_note="Reject deletion when the full normalized block is not already preserved nearby.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "duplicate_fragment_unique_continuation"


def test_run_reader_cleanup_applies_split_block_operation_from_exact_substrings() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "heading/body boundary needs block split",
                        "confidence": "high",
                        "evidence_before": "One block contains a heading followed by body prose.",
                        "expected_after_preview": "СТРАТЕГИИ РАЗВИТИЯ / Деньги — это рычаг власти.",
                        "safety_note": "Split covers the original block with exact substrings.",
                        "split_substrings": ["СТРАТЕГИИ РАЗВИТИЯ", "Деньги — это рычаг власти."],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "СТРАТЕГИИ РАЗВИТИЯ\n\nДеньги — это рычаг власти." in result.cleaned_markdown


def test_run_reader_cleanup_removes_inline_page_furniture_from_exact_substring() -> None:
    markdown = (
        "Главное различие между первым и вторым режимом заключается в том, что первый режим включается администратором.\n\n"
        "248 РАЗДЕЛ ДОКУМЕНТА Через призму рабочего процесса можно увидеть новые возможности.\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if str(block["text"]).startswith("248 РАЗДЕЛ ДОКУМЕНТА"))
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "inline page furniture before semantic body",
                        "confidence": "high",
                        "evidence_before": "Page number plus uppercase running header precedes prose.",
                        "expected_after_preview": "Через призму рабочего процесса можно увидеть новые возможности.",
                        "safety_note": "Only exact page furniture substring is removed; body remains.",
                        "noise_substring": "248 РАЗДЕЛ ДОКУМЕНТА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "248 РАЗДЕЛ ДОКУМЕНТА" not in result.cleaned_markdown
    assert "Через призму рабочего процесса" in result.cleaned_markdown


def test_run_reader_cleanup_recovers_inline_page_marker_from_exact_preview() -> None:
    target = "Однако в 1950-х годах 5 эта чеканка была запрещена."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "A standalone page/endnote marker is embedded between two prose tokens.",
                        "expected_after_preview": "Однако в 1950-х годах эта чеканка была запрещена.",
                        "safety_note": "Only the standalone marker is removed; the surrounding prose is preserved.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nОднако в 1950-х годах эта чеканка была запрещена.\n\nOutro"
    assert "reader_cleanup_exact_fields_recovered:1:b_000001:remove_inline_noise" in result.report_payload["warnings"]
    assert result.report_payload["accepted_cleanup_operations"][0]["noise_substring"] == "5 "


def test_run_reader_cleanup_preserves_word_boundary_after_inline_marker_removal() -> None:
    target = "Однако в 1950-х годах 5 эта чеканка была запрещена."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "orphan_footnote_marker",
                        "confidence": "high",
                        "evidence_before": "A standalone page/endnote marker is embedded between two prose tokens.",
                        "expected_after_preview": "Однако в 1950-х годах эта чеканка была запрещена.",
                        "safety_note": "The surrounding words must remain separated by one space.",
                        "noise_substring": " 5 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "годах эта" in result.cleaned_markdown
    assert "годахэта" not in result.cleaned_markdown


def test_run_reader_cleanup_does_not_recover_inline_noise_from_teaser_preview() -> None:
    target = (
        "25 В ответ на экономическую глобализацию и параллельно с ней огромную популярность приобрела "
        "организация валют на местном уровне."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "The response only previews the beginning of the cleaned block.",
                        "expected_after_preview": "В ответ на экономическую глобализацию",
                        "safety_note": "Runtime must not infer a deletion from a teaser preview.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == "noise_substring_not_found"


def test_run_reader_cleanup_recovers_duplicate_inline_heading_from_exact_preview() -> None:
    target = (
        "Во многих странах национальные валюты Национальные валюты будут использоваться еще долгое время."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "duplicate_fragment",
                        "confidence": "high",
                        "evidence_before": "The same heading phrase is repeated inline before the body continues.",
                        "expected_after_preview": "Во многих странах национальные валюты будут использоваться еще долгое время.",
                        "safety_note": "Only the adjacent duplicate phrase is removed; the semantic sentence remains.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\nВо многих странах национальные валюты будут использоваться еще долгое время.\n\nOutro"
    )
    assert result.report_payload["accepted_cleanup_operations"][0]["noise_substring"] == "Национальные валюты "


def test_reader_cleanup_request_targets_duplicate_semantic_heading_for_operation_selection() -> None:
    target = (
        "Во многих странах национальные валюты Национальные валюты будут использоваться еще долгое время."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    duplicate_target = next(
        target for target in targets if target["category"] == "duplicate_semantic_heading_text"
    )
    assert duplicate_target["noise_substring"] == "Национальные валюты "
    assert duplicate_target["expected_after_preview"] == (
        "Во многих странах национальные валюты будут использоваться еще долгое время."
    )
    assert "duplicate_fragment" in seen_payloads[0]["response_contract"]["reason_guidance_by_operation"][
        "remove_inline_noise"
    ]


def test_run_reader_cleanup_rejects_non_adjacent_duplicate_fragment_inline_noise() -> None:
    target = "Во многих странах национальные валюты будут использоваться еще долгое время."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "duplicate_fragment",
                        "confidence": "high",
                        "evidence_before": "A semantic phrase was incorrectly proposed as duplicate inline noise.",
                        "expected_after_preview": "Во многих странах будут использоваться еще долгое время.",
                        "safety_note": "Runtime must reject semantic removal when there is no adjacent duplicate phrase.",
                        "noise_substring": "национальные валюты ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "remove_inline_noise_not_exact_noise_pattern"
    )


def test_reader_cleanup_request_targets_fused_heading_body_for_normalize_boundary() -> None:
    target = (
        "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ "
        "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    fused_target = next(target for target in targets if target["category"] == "heading_fused_with_body_candidate")
    assert fused_target["heading_substring"] == "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ"
    assert fused_target["body_substring"] == (
        "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
    )
    assert fused_target["expected_after_preview"] == (
        "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ\n\n"
        "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
    )


def test_reader_cleanup_request_targets_wrapped_fused_heading_chain() -> None:
    first = "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ"
    second = "И СПРАВЕДЛИВОСТЬ. Авиабизнес отличается жесткой конкуренцией."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    fused_target = next(target for target in targets if target["category"] == "heading_fused_with_body_candidate")
    second_block = next(block for block in seen_payloads[0]["blocks"] if block["text"] == second)
    assert fused_target["next_id"] == second_block["id"]
    assert fused_target["next_text_hash"] == second_block["text_hash"]
    assert fused_target["heading_substring"] == "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ."
    assert fused_target["body_substring"] == "Авиабизнес отличается жесткой конкуренцией."
    assert fused_target["expected_after_preview"] == (
        "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ.\n\n"
        "Авиабизнес отличается жесткой конкуренцией."
    )


def test_reader_cleanup_request_targets_side_heading_island_without_inline_delete_hint() -> None:
    target = (
        "Стало очевидно, что региональная Три мультинациональные валюты экономическая интеграция "
        "может достичь зрелости только тогда, когда единая валюта уравнивает условия."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    side_heading_target = next(target for target in targets if target["category"] == "side_heading_island_candidate")
    assert side_heading_target["heading_candidate"] == "Три мультинациональные валюты"
    assert side_heading_target["id"].startswith("b_")


def test_reader_cleanup_request_targets_semantic_page_title_deletion_risk() -> None:
    target = "Абзац завершается указателем следующего раздела 20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    semantic_title_target = next(
        target for target in targets if target["category"] == "semantic_page_title_deletion_risk"
    )
    assert semantic_title_target["semantic_title_candidate"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert semantic_title_target["page_like_number"] == "20"
    assert semantic_title_target["numeric_prefix"] == "20 "


def test_reader_cleanup_request_targets_isolated_semantic_heading_numeric_prefix() -> None:
    target = "20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    numeric_prefix_target = next(
        target for target in targets if target["category"] == "isolated_semantic_heading_numeric_prefix"
    )
    assert numeric_prefix_target["numeric_prefix"] == "20 "
    assert numeric_prefix_target["semantic_heading_must_remain"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert numeric_prefix_target["expected_after_preview"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"


def test_reader_cleanup_request_targets_one_word_isolated_semantic_heading_numeric_prefix() -> None:
    target = "21 РОТТЕРДАМ."
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    targets = seen_payloads[0]["operation_selection_targets"]
    numeric_prefix_target = next(
        target for target in targets if target["category"] == "isolated_semantic_heading_numeric_prefix"
    )
    assert numeric_prefix_target["numeric_prefix"] == "21 "
    assert numeric_prefix_target["semantic_heading_must_remain"] == "РОТТЕРДАМ."
    assert numeric_prefix_target["expected_after_preview"] == "РОТТЕРДАМ."


_SIDE_HEADING_ISLAND_BLOCK = (
    "Стало очевидно, что региональная {phrase} экономическая интеграция "
    "может достичь зрелости только тогда, когда единая валюта уравнивает условия."
)

_SIDE_HEADING_ISLAND_PHRASES = (
    "Три мультинациональные валюты",
    "Четыре региональные системы",
    "Пять локальных инициатив",
    "Шесть городских экспериментов",
    "Семь кооперативных проектов",
    "Восемь отраслевых площадок",
    "Девять муниципальных программ",
    "Десять партнёрских соглашений",
    "Одиннадцать отраслевых стандартов",
    "Двенадцать финансовых институтов",
)

# Every field a target of a given category may carry. Anything else would be instruction
# prose that is identical for every target of that category and therefore belongs in the
# system prompt, not in the ~1 400 targets a book produces.
_ALLOWED_TARGET_FIELDS_BY_CATEGORY = {
    "duplicate_semantic_heading_text": {"category", "id", "text_hash", "noise_substring", "expected_after_preview"},
    "isolated_semantic_heading_numeric_prefix": {
        "category",
        "id",
        "text_hash",
        "numeric_prefix",
        "semantic_heading_must_remain",
        "expected_after_preview",
    },
    "semantic_page_title_deletion_risk": {
        "category",
        "id",
        "text_hash",
        "semantic_title_candidate",
        "page_like_number",
        "numeric_prefix",
    },
    "heading_fused_with_body_candidate": {
        "category",
        "id",
        "text_hash",
        "next_id",
        "next_text_hash",
        "heading_substring",
        "body_substring",
        "expected_after_preview",
    },
    "side_heading_island_candidate": {"category", "id", "text_hash", "heading_candidate"},
}


def _capture_first_payload(markdown: str, *, config: ReaderCleanupConfig | None = None) -> dict[str, Any]:
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    run_reader_cleanup(
        markdown_text=markdown,
        config=config or ReaderCleanupConfig(enabled=True),
        operation_provider=provider,
    )
    return seen_payloads[0]


def test_operation_selection_targets_carry_only_block_specific_evidence() -> None:
    """The per-category instruction prose belongs in the system prompt, not in every target."""
    markdown = "\n\n".join(
        [
            "Intro",
            "Во многих странах национальные валюты Национальные валюты будут использоваться еще долгое время.",
            "20 НОВЫЕ ФОРМЫ ДЕНЕГ?",
            "Абзац завершается указателем следующего раздела 20 ДРУГИЕ ФОРМЫ ДЕНЕГ?",
            (
                "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ "
                "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
            ),
            _SIDE_HEADING_ISLAND_BLOCK.format(phrase="Три мультинациональные валюты"),
            "Outro",
        ]
    )

    targets = _capture_first_payload(markdown)["operation_selection_targets"]

    seen_categories = {str(target["category"]) for target in targets}
    assert seen_categories == set(_ALLOWED_TARGET_FIELDS_BY_CATEGORY)
    for target in targets:
        allowed = _ALLOWED_TARGET_FIELDS_BY_CATEGORY[str(target["category"])]
        assert set(target) <= allowed, f"{target['category']} carries extra fields: {sorted(set(target) - allowed)}"
    # No target value may be instruction prose: every string a target carries is either a
    # short identifier or an exact substring taken from the block it describes.
    blocks_by_id = {str(block["id"]): str(block["text"]) for block in _capture_first_payload(markdown)["blocks"]}
    for target in targets:
        block_text = blocks_by_id[str(target["id"])]
        for field, value in target.items():
            if field in {"category", "id", "text_hash", "next_id", "next_text_hash", "expected_after_preview"}:
                continue
            assert str(value) in block_text, f"{target['category']}.{field} is not copied from the block"


def test_system_prompt_states_every_rule_removed_from_the_targets() -> None:
    """The trimmed boilerplate must survive as rules, once, in the system prompt."""
    prompt = build_reader_cleanup_system_prompt()
    rules_by_category = {
        line.split(":", 1)[0].removeprefix("Target category ").strip(): line
        for line in prompt.splitlines()
        if line.startswith("Target category ")
    }
    assert set(rules_by_category) == set(_ALLOWED_TARGET_FIELDS_BY_CATEGORY)

    duplicate_rule = rules_by_category["duplicate_semantic_heading_text"]
    assert "remove_inline_noise" in duplicate_rule
    assert "duplicate_fragment" in duplicate_rule
    assert "exact adjacent repeated phrase is still present once" in duplicate_rule

    numeric_rule = rules_by_category["isolated_semantic_heading_numeric_prefix"]
    assert "remove_inline_noise" in numeric_rule
    assert "page_number" in numeric_rule
    assert "Full-heading remove_inline_noise is forbidden" in numeric_rule
    assert "semantic_heading_must_remain" in numeric_rule and "never be removed" in numeric_rule

    title_rule = rules_by_category["semantic_page_title_deletion_risk"]
    assert "forbidden operation" in title_rule
    assert "not enough to classify the title as noise" in title_rule
    assert "skip with a warning" in title_rule
    assert "same-pass follow-up remove_inline_noise on the same original block id" in title_rule
    assert "numeric_prefix" in title_rule and "semantic_title_candidate" in title_rule

    fused_rule = rules_by_category["heading_fused_with_body_candidate"]
    assert "not noise" in fused_rule
    assert "normalize_heading_boundary" in fused_rule
    assert "remove_inline_noise and delete_block are forbidden" in fused_rule
    assert "skip if the exact substrings no longer match" in fused_rule
    assert "next_id and next_text_hash" in fused_rule
    assert "join_fragmented_paragraph with that exact next block first" in fused_rule

    island_rule = rules_by_category["side_heading_island_candidate"]
    assert "Semantic heading islands are not noise" in island_rule
    assert "forbidden default operation" in island_rule
    assert "extract_side_heading_and_reattach_body" in island_rule
    assert "pre_body_stub" in island_rule and "post_body_continuation" in island_rule
    assert "first try split_block, then normalize_heading_boundary" in island_rule
    assert "stub" in island_rule and "orphan" in island_rule
    assert "skip and add a warning" in island_rule
    # The reattach preview shape used to ride along in every island target; it is stated
    # once as part of the operation contract.
    assert (
        "For extract_side_heading_and_reattach_body, expected_after_preview must be exactly: "
        "heading_substring, then a blank line, then pre_body_stub plus one space plus post_body_continuation."
    ) in prompt


def test_operation_selection_targets_are_bounded_by_characters_not_by_a_count_of_twenty() -> None:
    """The old targets[:20] cap starved the tail of every busy chunk."""
    markdown = "\n\n".join(
        ["Intro"]
        + [_SIDE_HEADING_ISLAND_BLOCK.format(phrase=phrase) for phrase in _SIDE_HEADING_ISLAND_PHRASES]
        + ["Outro"]
    )
    payload = _capture_first_payload(markdown)
    targets = payload["operation_selection_targets"]

    assert len(targets) > 20
    # Every block that has a candidate gets one, including the last one in the chunk.
    last_island_block = next(
        block
        for block in reversed(payload["blocks"])
        if _SIDE_HEADING_ISLAND_PHRASES[-1] in str(block["text"])
    )
    assert any(target["id"] == last_island_block["id"] for target in targets)
    # ... and the hints still cannot outweigh the text they annotate.
    assert len(json.dumps(targets, ensure_ascii=False)) <= ReaderCleanupConfig(enabled=True).chunk_size


def test_operation_selection_targets_stop_at_the_configured_character_budget() -> None:
    from docxaicorrector.reader_cleanup_mvp._detectors import _build_operation_selection_targets

    blocks = build_cleanup_blocks(
        "\n\n".join(_SIDE_HEADING_ISLAND_BLOCK.format(phrase=phrase) for phrase in _SIDE_HEADING_ISLAND_PHRASES)
    )
    unlimited = _build_operation_selection_targets(blocks=blocks, char_budget=10**9)
    bounded = _build_operation_selection_targets(blocks=blocks, char_budget=600)

    assert len(bounded) < len(unlimited)
    assert bounded == unlimited[: len(bounded)]
    assert len(json.dumps(bounded, ensure_ascii=False)) <= 600


def test_chunk_request_payload_omits_the_always_empty_global_plan_fields() -> None:
    """global_plan_enabled is false by default, so these lists never carry anything."""
    markdown = "\n\n".join(["Intro", "Повторяющийся колонтитул", "Тело главы", "Повторяющийся колонтитул", "Outro"])

    global_plan = _capture_first_payload(markdown)["global_plan"]

    assert "document_specific_running_headers" not in global_plan
    assert "examples_do_not_delete" not in global_plan
    assert "likely_heading_body_patterns" not in global_plan
    assert "likely_fragmentation_patterns" not in global_plan
    assert not any(value == [] for value in global_plan.values())
    # What the pass actually computed locally still ships.
    assert global_plan["candidate_block_ids"]
    assert global_plan["repeated_noise_patterns"]


def test_anchor_repair_guidance_ships_only_when_the_anchor_pass_is_enabled() -> None:
    """The anchor_repair branch is unreachable unless a caller supplies anchor_targets."""
    anchor_only_cleanup_rules = (
        "If the request pass_name is anchor_repair, operate only inside the listed anchor_targets",
        "For anchor_repair, every returned operation still needs full audit fields",
        "For anchor_repair fragmented_paragraph targets, first inspect only adjacent payload blocks",
        "For anchor_repair join_fragmented_paragraph, copy next_id and next_text_hash exactly",
        "For anchor_repair fragmented_paragraph targets, do not propose delete_block duplicate_fragment",
        "do not combine split_block and join_fragmented_paragraph on the same evidence",
        "For anchor_repair page_furniture_inline targets, first propose remove_inline_noise",
        "- Anchor fragmented paragraph through caption/page boundary",
        "- Anchor fragmented paragraph that looks like a duplicate tail",
        "- Anchor fragmented paragraph with page furniture between prose",
        "- Anchor page furniture plus caption between sentence parts",
    )
    anchor_only_repair_rules = (
        "If pass_name is anchor_repair, keep the repaired response limited to anchor_targets",
        "For anchor_repair fragmented_paragraph items, keep a join_fragmented_paragraph operation only when",
        "For anchor_repair fragmented_paragraph items, do not convert a non-exact duplicate-looking tail",
        "For anchor_repair page_furniture_inline items, keep join_fragmented_paragraph only as a follow-up",
    )

    production_prompt = build_reader_cleanup_system_prompt()
    production_repair_prompt = build_reader_cleanup_schema_repair_system_prompt()
    anchor_prompt = build_reader_cleanup_system_prompt(include_anchor_repair_guidance=True)
    anchor_repair_prompt = build_reader_cleanup_schema_repair_system_prompt(include_anchor_repair_guidance=True)

    for rule in anchor_only_cleanup_rules:
        assert rule not in production_prompt
        assert rule in anchor_prompt
    for rule in anchor_only_repair_rules:
        assert rule not in production_repair_prompt
        assert rule in anchor_repair_prompt
    assert "anchor_repair" not in production_prompt
    assert anchor_prompt.startswith(production_prompt)
    assert anchor_repair_prompt.startswith(production_repair_prompt)


def test_reader_cleanup_request_does_not_target_numbered_list_as_semantic_heading_prefix() -> None:
    target = "20. НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert not any(
        target["category"] == "isolated_semantic_heading_numeric_prefix"
        for target in seen_payloads[0]["operation_selection_targets"]
    )


def test_run_reader_cleanup_rejects_side_heading_island_remove_inline_noise() -> None:
    target = (
        "Стало очевидно, что региональная Три мультинациональные валюты экономическая интеграция "
        "может достичь зрелости только тогда, когда единая валюта уравнивает условия."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A semantic side-heading island was incorrectly proposed as noise.",
                        "expected_after_preview": (
                            "Стало очевидно, что региональная экономическая интеграция "
                            "может достичь зрелости только тогда, когда единая валюта уравнивает условия."
                        ),
                        "safety_note": "Runtime must reject deleting semantic heading island text.",
                        "noise_substring": "Три мультинациональные валюты ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "remove_inline_noise_not_exact_noise_pattern"
    )


def test_run_reader_cleanup_extracts_side_heading_and_reattaches_sentence_body() -> None:
    target = (
        "Стало очевидно, что региональная Три мультинациональные валюты экономическая интеграция "
        "может достичь зрелости."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "A semantic side-heading island interrupts one sentence.",
                        "expected_after_preview": (
                            "Три мультинациональные валюты\n\n"
                            "Стало очевидно, что региональная экономическая интеграция может достичь зрелости."
                        ),
                        "safety_note": "Preserve heading text and reattach the pre-heading stub to the continuation.",
                        "pre_body_stub": "Стало очевидно, что региональная",
                        "heading_substring": "Три мультинациональные валюты",
                        "post_body_continuation": "экономическая интеграция может достичь зрелости.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Три мультинациональные валюты\n\n"
        "Стало очевидно, что региональная экономическая интеграция может достичь зрелости.\n\n"
        "Outro"
    )
    assert result.report_payload["accepted_cleanup_operations"][0]["operation"] == (
        "extract_side_heading_and_reattach_body"
    )


def test_run_reader_cleanup_rejects_side_heading_reattach_for_heading_stack_without_pre_stub() -> None:
    target = (
        "Авиационные бонусные программы Частные международные расчетные единицы стали первым масштабным "
        "применением международных корпоративных расчетных единиц."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "A heading stack has no pre-heading sentence stub to reattach.",
                        "expected_after_preview": (
                            "Частные международные расчетные единицы\n\n"
                            "Авиационные бонусные программы стали первым масштабным применением международных "
                            "корпоративных расчетных единиц."
                        ),
                        "safety_note": "Runtime should reject this shape as ambiguous rather than inventing continuity.",
                        "pre_body_stub": "",
                        "heading_substring": "Частные международные расчетные единицы",
                        "post_body_continuation": (
                            "стали первым масштабным применением международных корпоративных расчетных единиц."
                        ),
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_missing_exact_parts"
    )


def test_run_reader_cleanup_rejects_dash_led_prose_side_heading_reattach() -> None:
    target = "Вирджиния и Вашингтон — предприняли шаги по созданию кооперативной валюты."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "A dash-led prose phrase was incorrectly treated as a heading island.",
                        "expected_after_preview": (
                            "Вашингтон\n\nВирджиния и — предприняли шаги по созданию кооперативной валюты."
                        ),
                        "safety_note": "Dash-led prose must not be repaired as a side-heading island.",
                        "pre_body_stub": "Вирджиния и",
                        "heading_substring": "Вашингтон",
                        "post_body_continuation": "— предприняли шаги по созданию кооперативной валюты.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_post_body_not_continuation"
    )


def test_run_reader_cleanup_rejects_capitalized_normal_prose_side_heading_reattach() -> None:
    target = "Мы увидели Зеленая Команда решила помочь соседям и открыла общий фонд."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "A capitalized prose phrase was incorrectly treated as a heading island.",
                        "expected_after_preview": "Зеленая Команда решила\n\nМы увидели помочь соседям и открыла общий фонд.",
                        "safety_note": "Normal prose should remain unchanged.",
                        "pre_body_stub": "Мы увидели",
                        "heading_substring": "Зеленая Команда решила",
                        "post_body_continuation": "помочь соседям и открыла общий фонд.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_heading_not_plausible"
    )


def test_run_reader_cleanup_rejects_digit_side_heading_reattach() -> None:
    target = "Стало очевидно, что региональная Три 2026 валюты экономическая интеграция созрела."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "A digit-bearing candidate is not a safe semantic side heading.",
                        "expected_after_preview": (
                            "Три 2026 валюты\n\nСтало очевидно, что региональная экономическая интеграция созрела."
                        ),
                        "safety_note": "Digit-bearing side-heading candidates are rejected for this bounded operation.",
                        "pre_body_stub": "Стало очевидно, что региональная",
                        "heading_substring": "Три 2026 валюты",
                        "post_body_continuation": "экономическая интеграция созрела.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_heading_contains_digits"
    )


def test_run_reader_cleanup_rejects_side_heading_reattach_with_ambiguous_substrings() -> None:
    target = (
        "Стало очевидно, что региональная Три мультинациональные валюты экономическая интеграция "
        "и Три мультинациональные валюты зрелая система."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "The same heading candidate appears twice.",
                        "expected_after_preview": (
                            "Три мультинациональные валюты\n\n"
                            "Стало очевидно, что региональная экономическая интеграция и зрелая система."
                        ),
                        "safety_note": "Ambiguous repeated heading substrings must fail closed.",
                        "pre_body_stub": "Стало очевидно, что региональная",
                        "heading_substring": "Три мультинациональные валюты",
                        "post_body_continuation": "экономическая интеграция и Три мультинациональные валюты зрелая система.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_substring_ambiguous"
    )


def test_run_reader_cleanup_rejects_side_heading_reattach_preview_that_drops_text() -> None:
    target = (
        "Стало очевидно, что региональная Три мультинациональные валюты экономическая интеграция "
        "может достичь зрелости."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "extract_side_heading_and_reattach_body",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "The preview drops part of the body continuation.",
                        "expected_after_preview": (
                            "Три мультинациональные валюты\n\n"
                            "Стало очевидно, что региональная экономическая интеграция."
                        ),
                        "safety_note": "Expected preview must preserve every semantic character.",
                        "pre_body_stub": "Стало очевидно, что региональная",
                        "heading_substring": "Три мультинациональные валюты",
                        "post_body_continuation": "экономическая интеграция может достичь зрелости.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_cleanup_operations"][0]["ignored_reason"] == (
        "side_heading_reattach_expected_after_preview_mismatch"
    )


def test_reader_cleanup_request_does_not_target_leading_dash_as_side_heading_island() -> None:
    target = (
        "— Эти монеты чеканились в Китае и использовались в качестве торговых жетонов, "
        "подобно тому как коренные народы использовали торговые бусины."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"
    seen_payloads: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        seen_payloads.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert not any(
        target["category"] == "side_heading_island_candidate"
        for target in seen_payloads[0]["operation_selection_targets"]
    )


def test_run_reader_cleanup_removes_numeric_uppercase_running_header_prefix() -> None:
    target = (
        "150 ПРОЦВЕТАНИЕ Эдгар Камперс, директор нидерландской организации Qoin, "
        "с 1998 года работает в сфере устойчивого экономического развития."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A page number and all-caps running header are fused to the paragraph start.",
                        "expected_after_preview": "Эдгар Камперс, директор нидерландской организации Qoin, с 1998 года работает в сфере устойчивого экономического развития.",
                        "safety_note": "Only the exact non-semantic page furniture prefix should be removed.",
                        "noise_substring": "150 ПРОЦВЕТАНИЕ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Эдгар Камперс, директор нидерландской организации Qoin, с 1998 года работает в сфере устойчивого экономического развития.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_removes_two_number_numeric_uppercase_running_header_prefix() -> None:
    target = (
        "187 188 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ Джон Стивен Лансинг, профессор Института Санта-Фе, "
        "исследует связь между экологией и общественной собственностью."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "Two page numbers and an uppercase running header are fused to the paragraph start.",
                        "expected_after_preview": "Джон Стивен Лансинг, профессор Института Санта-Фе, исследует связь между экологией и общественной собственностью.",
                        "safety_note": "Only the exact two-number running-header prefix should be removed.",
                        "noise_substring": "187 188 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Джон Стивен Лансинг, профессор Института Санта-Фе, исследует связь между экологией и общественной собственностью.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_removes_numeric_uppercase_running_header_prefix_with_terminal_punctuation() -> None:
    target = (
        "162 ПРОЦВЕТАНИЕ. Эта бывшая шахтерская деревня с населением около 1895 человек оказалась в ловушке постиндустриальной депрессии."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A page number and uppercase running header with terminal punctuation precede the paragraph.",
                        "expected_after_preview": "Эта бывшая шахтерская деревня с населением около 1895 человек оказалась в ловушке постиндустриальной депрессии.",
                        "safety_note": "Remove only the exact punctuated running-header prefix proposed by the model.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ. ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Эта бывшая шахтерская деревня с населением около 1895 человек оказалась в ловушке постиндустриальной депрессии.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_removes_two_number_numeric_uppercase_running_header_prefix_with_terminal_punctuation() -> None:
    target = (
        "187 188 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ. Джон Стивен Лансинг, профессор Института Санта-Фе, исследует связь между экологией и общественной собственностью."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "Two page numbers and a punctuated uppercase running header precede the paragraph.",
                        "expected_after_preview": "Джон Стивен Лансинг, профессор Института Санта-Фе, исследует связь между экологией и общественной собственностью.",
                        "safety_note": "Remove only the exact punctuated two-number prefix proposed by the model.",
                        "noise_substring": "187 188 ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ. ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Джон Стивен Лансинг, профессор Института Санта-Фе, исследует связь между экологией и общественной собственностью.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_rejects_broad_numeric_prefix_noise_that_would_delete_semantic_heading() -> None:
    target = (
        "162 ПРОЦВЕТАНИЕ: ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР "
        "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A numeric prefix is followed by a semantic heading and body in the same block.",
                        "expected_after_preview": "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль.",
                        "safety_note": "This must be rejected because the proposed noise substring consumes the semantic heading, not only the numeric running-header prefix.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ: ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_applies_numeric_prefix_then_exact_heading_boundary_for_semantic_heading() -> None:
    target = (
        "162 ПРОЦВЕТАНИЕ: ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР "
        "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "Only the numeric running-header prefix should be removed first.",
                        "expected_after_preview": "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль.",
                        "safety_note": "Remove only the exact numeric prefix and short running-header token.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ: ",
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "After prefix removal, the remaining semantic heading is still fused with the body prose.",
                        "expected_after_preview": "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР / Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль.",
                        "safety_note": "Keep the semantic heading and the exact body remainder as separate exact operations.",
                        "heading_substring": "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР",
                        "body_substring": "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР\n\n"
        "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль.\n\n"
        "Outro"
    )
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == ["remove_inline_noise", "normalize_heading_boundary"]


def test_run_reader_cleanup_recovers_heading_boundary_from_exact_preview_with_teaser_body() -> None:
    target = (
        "162 ПРОЦВЕТАНИЕ ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР "
        "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль. "
        "Традиционно эти структуры испытывают нехватку ресурсов."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "Only the numeric running-header prefix should be removed first.",
                        "expected_after_preview": (
                            "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР Через призму..."
                        ),
                        "safety_note": "Remove only the exact page-furniture prefix.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ ",
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": (
                            "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР Через призму..."
                        ),
                        "expected_after_preview": (
                            "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР\n\n"
                            "Через призму..."
                        ),
                        "safety_note": "Recover exact substrings only from the current block text.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР\n\n"
        "Через призму кооперативных валют становится очевидно, что для НКО открывается новая роль. "
        "Традиционно эти структуры испытывают нехватку ресурсов.\n\n"
        "Outro"
    )
    assert any(
        warning.endswith(":normalize_heading_boundary")
        for warning in result.report_payload["warnings"]
        if warning.startswith("reader_cleanup_exact_fields_recovered:")
    )
    accepted_heading = next(
        entry
        for entry in result.report_payload["accepted_cleanup_operations"]
        if entry["operation"] == "normalize_heading_boundary"
    )
    assert accepted_heading["body_substring"].endswith("Традиционно эти структуры испытывают нехватку ресурсов.")


def test_run_reader_cleanup_normalizes_heading_boundary_after_safe_joined_heading_tail() -> None:
    first = "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ"
    second = (
        "И СПРАВЕДЛИВОСТЬ. Авиабизнес отличается жесткой конкуренцией. "
        "Сотрудничество помогает избежать сбоев."
    )
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        second_block = next(block for block in payload["blocks"] if block["text"] == second)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": first,
                        "expected_after_preview": (
                            "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ. "
                            "Авиабизнес отличается жесткой конкуренцией..."
                        ),
                        "safety_note": "Join only adjacent exact-hash heading fragments.",
                        "next_id": second_block["id"],
                        "next_text_hash": second_block["text_hash"],
                    },
                    {
                        "id": second_block["id"],
                        "text_hash": second_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": second,
                        "expected_after_preview": (
                            "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ.\n\n"
                            "Авиабизнес отличается жесткой конкуренцией. Сотрудничество помогает избежать сбоев."
                        ),
                        "safety_note": "Normalize the exact joined heading/body boundary after the safe join.",
                        "heading_substring": "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ.",
                        "body_substring": (
                            "Авиабизнес отличается жесткой конкуренцией. Сотрудничество помогает избежать сбоев."
                        ),
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ.\n\n"
        "Авиабизнес отличается жесткой конкуренцией. Сотрудничество помогает избежать сбоев.\n\n"
        "Outro"
    )
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == [
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
    ]
    assert accepted_operations[-1]["after_state"] == "heading_boundary_normalized_after_join"


def test_run_reader_cleanup_reorders_same_block_join_before_heading_boundary() -> None:
    first = "ПЛАН ДОСТУПА К ИНТЕРНЕТУ"
    second = "Вдохновившись региональным опытом, команда начала пилотный проект."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        second_block = next(block for block in payload["blocks"] if block["text"] == second)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The heading/body boundary is visible only after joining the fragmented body tail.",
                        "expected_after_preview": f"{first}\n\n{second}",
                        "safety_note": "Normalize only after the adjacent body tail is joined; preserve all semantic heading text.",
                        "heading_substring": first,
                        "body_substring": second,
                    },
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "paragraph fragmented after page boundary",
                        "confidence": "high",
                        "evidence_before": "The next adjacent block is the body tail for the same heading/body site.",
                        "expected_after_preview": f"{first} {second}",
                        "safety_note": "Join only adjacent exact-hash blocks before normalizing the heading boundary.",
                        "next_id": second_block["id"],
                        "next_text_hash": second_block["text_hash"],
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == f"Intro\n\n{first}\n\n{second}\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == [
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
    ]
    assert all(entry.get("sequence_decision") == "operation_sequence_reordered" for entry in accepted_operations)
    assert accepted_operations[-1]["after_state"] == "heading_boundary_normalized"
    assert first in result.cleaned_markdown


def test_run_reader_cleanup_defers_heading_chain_until_next_block_noise_cleanup() -> None:
    first = "ПЛАН ДОСТУПА К ИНТЕРНЕТУ"
    second = "203 Вдохновившись региональным опытом, команда начала пилотный проект."
    body = "Вдохновившись региональным опытом, команда начала пилотный проект."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        second_block = next(block for block in payload["blocks"] if block["text"] == second)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The heading/body boundary is visible only after joining the cleaned adjacent body tail.",
                        "expected_after_preview": f"{first}\n\n{body}",
                        "safety_note": "Normalize only after the adjacent body tail is cleaned and joined.",
                        "heading_substring": first,
                        "body_substring": body,
                    },
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "paragraph fragmented after page boundary",
                        "confidence": "high",
                        "evidence_before": "The next adjacent block is the body tail for the same heading/body site.",
                        "expected_after_preview": f"{first} {body}",
                        "safety_note": "Join only after the page-like prefix in the adjacent block is removed.",
                        "next_id": second_block["id"],
                        "next_text_hash": second_block["text_hash"],
                    },
                    {
                        "id": second_block["id"],
                        "text_hash": second_block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "A page-like number prefixes the body tail.",
                        "expected_after_preview": body,
                        "safety_note": "Remove only the exact numeric prefix.",
                        "noise_substring": "203 ",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == f"Intro\n\n{first}\n\n{body}\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert [entry["operation"] for entry in accepted_operations] == [
        "remove_inline_noise",
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
    ]
    assert accepted_operations[-1]["after_state"] == "heading_boundary_normalized"


def test_run_reader_cleanup_skips_same_block_heading_boundary_when_prior_join_fails() -> None:
    first = "ПЛАН ДОСТУПА К ИНТЕРНЕТУ"
    second = "Вдохновившись региональным опытом, команда начала пилотный проект."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        second_block = next(block for block in payload["blocks"] if block["text"] == second)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "paragraph fragmented after page boundary",
                        "confidence": "high",
                        "evidence_before": "The next adjacent block is the body tail for the same heading/body site.",
                        "expected_after_preview": f"{first} {second}",
                        "safety_note": "This join must fail because the hash is stale.",
                        "next_id": second_block["id"],
                        "next_text_hash": "stale-hash",
                    },
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The heading/body boundary depends on the prior join.",
                        "expected_after_preview": f"{first}\n\n{second}",
                        "safety_note": "Do not apply if the prior join did not apply.",
                        "heading_substring": first,
                        "body_substring": second,
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    ignored_operations = result.report_payload["ignored_delete_blocks"]
    assert [entry["ignored_reason"] for entry in ignored_operations] == [
        "join_next_text_hash_mismatch",
        "prior_same_block_operation_not_applied",
    ]


def test_run_reader_cleanup_normalizes_standalone_heading_with_adjacent_body() -> None:
    heading = "ДЕМОКРАТИЯ, ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ"
    body = "Ключевые аспекты проекта требуют регулярной отчетности."
    markdown = f"Intro\n\n{heading}\n\n{body}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        heading_block = next(block for block in payload["blocks"] if block["text"] == heading)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": heading_block["id"],
                        "text_hash": heading_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The heading is separated from the body by a stale block boundary.",
                        "expected_after_preview": f"{heading}\n\n{body}",
                        "safety_note": "Apply only when the adjacent block starts with the exact body.",
                        "heading_substring": heading,
                        "body_substring": body,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == f"Intro\n\n{heading}\n\n{body}\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert accepted_operations[-1]["after_state"] == "heading_boundary_normalized_across_adjacent_block"


def test_run_reader_cleanup_normalizes_split_heading_with_adjacent_body_tail() -> None:
    first = "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ"
    second = "И СПРАВЕДЛИВОСТЬ. Авиабизнес отличается жесткой конкуренцией."
    heading = "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ."
    body = "Авиабизнес отличается жесткой конкуренцией."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "The heading begins in this block and continues into the adjacent body block.",
                        "expected_after_preview": f"{heading}\n\n{body}",
                        "safety_note": "Do not apply unless the current block is the exact heading prefix.",
                        "heading_substring": heading,
                        "body_substring": body,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == f"Intro\n\n{heading}\n\n{body}\n\nOutro"
    accepted_operations = result.report_payload["accepted_cleanup_operations"]
    assert accepted_operations[-1]["after_state"] == "heading_boundary_normalized_across_adjacent_block"


def test_run_reader_cleanup_rejects_adjacent_heading_boundary_with_unaccounted_prefix_prose() -> None:
    first = "Предыдущая мысль завершается перед заголовком ДЕМОКРАТИЯ"
    second = "Ключевые аспекты проекта требуют регулярной отчетности."
    markdown = f"Intro\n\n{first}\n\n{second}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        first_block = next(block for block in payload["blocks"] if block["text"] == first)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first_block["id"],
                        "text_hash": first_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A heading-like tail appears after prose, then the body starts in the next block.",
                        "expected_after_preview": "ДЕМОКРАТИЯ\n\nКлючевые аспекты проекта требуют регулярной отчетности.",
                        "safety_note": "Reject because prose appears before the heading candidate.",
                        "heading_substring": "ДЕМОКРАТИЯ",
                        "body_substring": second,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "heading_boundary_substrings_not_found"


def test_run_reader_cleanup_rejects_duplicate_fragment_when_nearby_tail_is_similar_but_not_exact() -> None:
    candidate_block = "но это потребует скоординированных шагов со стороны местных сообществ."
    markdown = (
        "Intro\n\n"
        "Это поможет запустить локальную валюту быстрее, но это потребует скоординированных шагов со стороны местного сообщества.\n\n"
        f"{candidate_block}\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        duplicate_block = next(block for block in payload["blocks"] if block["text"] == candidate_block)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(
                        duplicate_block,
                        reason="duplicate_fragment",
                        confidence="high",
                        evidence_before="The candidate tail looks similar to nearby prose but is not an exact normalized duplicate.",
                        safety_note="Delete only when the full candidate block is already preserved nearby as exact normalized text.",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=provider,
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "duplicate_fragment_unique_continuation"


def test_run_reader_cleanup_removes_numeric_uppercase_running_header_inside_sentence() -> None:
    target = "В-третьих, в системе безубыточного инвестирования 194 RETHINKING MONEY средства направляются в первую очередь тем предприятиям, которые создают общественную пользу."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "A page number and uppercase running header interrupt the sentence mid-stream.",
                        "expected_after_preview": "В-третьих, в системе безубыточного инвестирования средства направляются в первую очередь тем предприятиям, которые создают общественную пользу.",
                        "safety_note": "Only the exact page-furniture substring inside the sentence should be removed.",
                        "noise_substring": "194 RETHINKING MONEY ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "В-третьих, в системе безубыточного инвестирования средства направляются в первую очередь тем предприятиям, которые создают общественную пользу.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_rejects_semantic_numeric_uppercase_inline_noise() -> None:
    target = "12 ФАКТОРОВ УСПЕХА Экономика устойчивого роста требует терпения и дисциплины."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A numeric uppercase prefix was proposed as inline noise.",
                        "expected_after_preview": "Экономика устойчивого роста требует терпения и дисциплины.",
                        "safety_note": "This must be rejected because the numbered uppercase phrase is semantic heading text, not generic page furniture.",
                        "noise_substring": "12 ФАКТОРОВ УСПЕХА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_rejects_trailing_semantic_page_title_inline_noise() -> None:
    target = "Абзац завершается указателем следующего раздела 20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A page-like number plus semantic title was incorrectly proposed as noise.",
                        "expected_after_preview": "Абзац завершается указателем следующего раздела",
                        "safety_note": "Runtime must reject semantic title deletion even when a page-like number is attached.",
                        "noise_substring": "20 НОВЫЕ ФОРМЫ ДЕНЕГ?",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == (
        "remove_inline_noise_not_exact_noise_pattern"
    )


def test_run_reader_cleanup_removes_only_numeric_prefix_from_isolated_semantic_heading() -> None:
    target = "20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "An isolated semantic heading has a page-like numeric prefix.",
                        "expected_after_preview": "НОВЫЕ ФОРМЫ ДЕНЕГ?",
                        "safety_note": "Remove only the exact numeric prefix and preserve the heading text.",
                        "noise_substring": "20 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nНОВЫЕ ФОРМЫ ДЕНЕГ?\n\nOutro"
    assert result.report_payload["accepted_cleanup_operations"][0]["noise_substring"] == "20 "


def test_run_reader_cleanup_applies_split_then_numeric_prefix_cleanup_on_same_block() -> None:
    target = "Предыдущий абзац завершился. 20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "heading_fused_with_body",
                        "confidence": "high",
                        "evidence_before": "A semantic heading with numeric prefix is appended to the previous paragraph.",
                        "expected_after_preview": "Предыдущий абзац завершился.\n\n20 НОВЫЕ ФОРМЫ ДЕНЕГ?",
                        "safety_note": "Split preserves both paragraph and heading text.",
                        "split_substrings": [
                            "Предыдущий абзац завершился.",
                            "20 НОВЫЕ ФОРМЫ ДЕНЕГ?",
                        ],
                    },
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "After structural split, only the numeric prefix should be removed from the heading substring.",
                        "expected_after_preview": "НОВЫЕ ФОРМЫ ДЕНЕГ?",
                        "safety_note": "Remove only the exact numeric prefix and keep the semantic heading.",
                        "noise_substring": "20 ",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nПредыдущий абзац завершился.\n\nНОВЫЕ ФОРМЫ ДЕНЕГ?\n\nOutro"
    assert [entry["operation"] for entry in result.report_payload["accepted_cleanup_operations"]] == [
        "split_block",
        "remove_inline_noise",
    ]


def test_run_reader_cleanup_rejects_full_isolated_semantic_heading_inline_noise() -> None:
    target = "20 НОВЫЕ ФОРМЫ ДЕНЕГ?"
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "The whole semantic title was incorrectly proposed as noise.",
                        "expected_after_preview": "НОВЫЕ ФОРМЫ ДЕНЕГ?",
                        "safety_note": "Runtime must reject full semantic heading deletion.",
                        "noise_substring": "20 НОВЫЕ ФОРМЫ ДЕНЕГ?",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == (
        "remove_inline_noise_not_exact_noise_pattern"
    )


def test_run_reader_cleanup_rejects_semantic_two_number_numeric_uppercase_inline_noise() -> None:
    target = "12 13 ФАКТОРОВ УСПЕХА Экономика устойчивого роста требует терпения и дисциплины."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "A two-number uppercase prefix was proposed as inline noise.",
                        "expected_after_preview": "Экономика устойчивого роста требует терпения и дисциплины.",
                        "safety_note": "This must still be rejected because the numbered uppercase phrase is semantic heading text, not page furniture.",
                        "noise_substring": "12 13 ФАКТОРОВ УСПЕХА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_rejects_semantic_numeric_uppercase_inline_noise_with_terminal_punctuation() -> None:
    target = "12 ФАКТОРОВ УСПЕХА. Экономика устойчивого роста требует терпения и дисциплины."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A punctuated numeric uppercase heading was proposed as inline noise.",
                        "expected_after_preview": "Экономика устойчивого роста требует терпения и дисциплины.",
                        "safety_note": "This must still be rejected because the numbered uppercase phrase is semantic heading text, not page furniture.",
                        "noise_substring": "12 ФАКТОРОВ УСПЕХА. ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_removes_title_case_running_header_with_page_number_prefix() -> None:
    target = (
        "Обзор для команды 145 Ни одно из улучшений рабочего процесса не было бы возможно без стабильной обратной связи."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "repeated_running_header",
                        "confidence": "high",
                        "evidence_before": "Title-case running header and page number are fused to the paragraph start.",
                        "expected_after_preview": "Ни одно из улучшений рабочего процесса не было бы возможно без стабильной обратной связи.",
                        "safety_note": "Only the short running-header prefix with trailing page number should be removed.",
                        "noise_substring": "Обзор для команды 145 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\nНи одно из улучшений рабочего процесса не было бы возможно без стабильной обратной связи.\n\nOutro"
    )


def test_run_reader_cleanup_removes_title_case_running_header_in_middle_of_paragraph() -> None:
    target = "Проект Обзор для команды 167 требует регулярного обновления документации."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_heading",
                        "confidence": "high",
                        "evidence_before": "Title-case running header plus page number interrupts a sentence after the country name.",
                        "expected_after_preview": "Проект требует регулярного обновления документации.",
                        "safety_note": "Remove only the short running-header residue inserted inside the sentence.",
                        "noise_substring": "Обзор для команды 167 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nПроект требует регулярного обновления документации.\n\nOutro"


def test_run_reader_cleanup_rejects_title_case_running_header_inside_longer_number() -> None:
    target = "Analysis of the United States 2024 report continued after the hearing."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A short title-case header plus page number was proposed from inside the sentence.",
                        "expected_after_preview": "Analysis of the 24 report continued after the hearing.",
                        "safety_note": "This should be rejected because the substring ends inside a longer year token.",
                        "noise_substring": "United States 20",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_rejects_ambiguous_inline_noise_substring() -> None:
    target = "В 4 городах выпускались жетоны, и 4 использовались в качестве page marker."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A bare numeric page marker appears inside a paragraph.",
                        "expected_after_preview": "Only the inline page marker should be removed.",
                        "safety_note": "The substring is ambiguous because the same marker text appears in semantic prose.",
                        "noise_substring": "4 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_substring_ambiguous"


def test_run_reader_cleanup_removes_title_case_running_header_with_acronym_suffix_inside_sentence() -> None:
    target = (
        "Как отмечалось в рабочем отчете, Полевой отчет НКО 167 развивающейся организации "
        "часто приходится решать проблему мусора при ограниченном бюджете."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A title-case running header with an acronym and trailing page number interrupts the sentence.",
                        "expected_after_preview": (
                            "Как отмечалось в рабочем отчете, развивающейся организации часто приходится решать "
                            "проблему мусора при ограниченном бюджете."
                        ),
                        "safety_note": "Remove only the exact running-header substring bounded inside the sentence.",
                        "noise_substring": "Полевой отчет НКО 167 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "Как отмечалось в рабочем отчете, развивающейся организации часто приходится решать проблему мусора при ограниченном бюджете.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_removes_title_case_running_header_with_leading_number_and_connectors() -> None:
    target = (
        "В итоговом обзоре 3 Городское управление 201 особенно важно сохранить прозрачность "
        "и подотчетность для всех участников процесса."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A page number, title-case running header, and trailing page number interrupt the sentence.",
                        "expected_after_preview": (
                            "В итоговом обзоре особенно важно сохранить прозрачность и подотчетность "
                            "для всех участников процесса."
                        ),
                        "safety_note": "Remove only the exact non-semantic inline running-header island.",
                        "noise_substring": "3 Городское управление 201 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\n"
        "В итоговом обзоре особенно важно сохранить прозрачность и подотчетность для всех участников процесса.\n\n"
        "Outro"
    )


def test_run_reader_cleanup_joins_fragmented_paragraph_after_caption_boundary() -> None:
    markdown = (
        "Intro\n\n"
        "Рисунок 4.1: локальная валюта поддерживает торговлю,\n\n"
        "и помогает соседям сохранять покупательную способность.\n\n"
        "Outro"
    )

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        blocks = payload["blocks"]
        first = next(block for block in blocks if str(block["text"]).startswith("Рисунок 4.1"))
        second = next(block for block in blocks if str(block["text"]).startswith("и помогает"))
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": first["id"],
                        "text_hash": first["text_hash"],
                        "operation": "join_fragmented_paragraph",
                        "reason": "paragraph fragmented after caption/page boundary",
                        "confidence": "high",
                        "evidence_before": "First block ends with comma and next block starts lowercase.",
                        "expected_after_preview": "Рисунок 4.1: ... и помогает соседям...",
                        "safety_note": "Only adjacent exact-hash blocks are joined.",
                        "next_id": second["id"],
                        "next_text_hash": second["text_hash"],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "торговлю, и помогает соседям" in result.cleaned_markdown


def test_run_reader_cleanup_rejects_non_exact_split_operation() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "heading/body boundary needs block split",
                        "confidence": "high",
                        "evidence_before": "One block contains heading and body prose.",
                        "expected_after_preview": "СТРАТЕГИИ / Деньги...",
                        "safety_note": "This intentionally proposes a non-exact split.",
                        "split_substrings": ["СТРАТЕГИИ", "Деньги — это рычаг власти."],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "split_substrings_not_exact_block_cover"


def test_run_reader_cleanup_rejects_inline_noise_that_would_delete_semantic_body() -> None:
    target = "Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "unsafe semantic deletion attempt",
                        "confidence": "high",
                        "evidence_before": "The proposed noise substring is actually the full semantic sentence.",
                        "expected_after_preview": "The block would become empty, so this must be rejected.",
                        "safety_note": "Code must reject because no semantic body would remain.",
                        "noise_substring": target,
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_rejects_inline_noise_substring_with_semantic_words() -> None:
    target = "— Эти монеты чеканились в Китае и 4 использовались в качестве торговых жетонов."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A numeric marker appears inside the sentence.",
                        "expected_after_preview": "— Эти монеты чеканились в Китае и использовались в качестве торговых жетонов.",
                        "safety_note": "Only the non-semantic marker should be removed.",
                        "noise_substring": "— Эти монеты чеканились в Китае и 4 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "remove_inline_noise_not_exact_noise_pattern"


def test_run_reader_cleanup_rejects_non_delete_operation_missing_required_evidence_fields() -> None:
    target = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert any(
        "reader_cleanup_chunk_failed:1:reader_cleanup_operation_missing_required_field:" in warning
        for warning in result.report_payload["warnings"]
    )


def test_run_reader_cleanup_ignores_missing_preview_when_safe_preview_cannot_be_recovered() -> None:
    target_noise = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности для команды."
    target_heading = "ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства."
    markdown = f"Intro\n\n{target_noise}\n\n{target_heading}\n\nOutro"
    repair_calls: list[dict[str, Any]] = []

    def operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        noise_block = next(block for block in payload["blocks"] if block["text"] == target_noise)
        heading_block = next(block for block in payload["blocks"] if block["text"] == target_heading)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": noise_block["id"],
                        "text_hash": noise_block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "The model identified a broad prefix but did not provide a safe preview.",
                        "safety_note": "Do not apply unless the exact inline noise pattern is safe.",
                        "noise_substring": "150 РАЗДЕЛ ОТЧЕТА Через ",
                    },
                    {
                        "id": heading_block["id"],
                        "text_hash": heading_block["text_hash"],
                        "operation": "normalize_heading_boundary",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "A sentence-style section heading and the first sentence are fused in one paragraph.",
                        "expected_after_preview": "ОБРАЗОВАНИЕ. / Расходы на образование обычно ложатся на плечи федерального правительства.",
                        "safety_note": "Split only the exact copied heading and exact copied body remainder.",
                        "heading_substring": "ОБРАЗОВАНИЕ.",
                        "body_substring": "Расходы на образование обычно ложатся на плечи федерального правительства.",
                    },
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(payload)
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )

    assert len(repair_calls) == 1
    assert result.changed is False
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_schema_repair_succeeded:1" in result.report_payload["warnings"]
    assert not any(
        warning.startswith("reader_cleanup_expected_after_preview_ignored:1:")
        for warning in result.report_payload["warnings"]
    )
    assert not any("reader_cleanup_chunk_failed:1:" in warning for warning in result.report_payload["warnings"])
    assert result.report_payload["stats"]["accepted_cleanup_operation_count"] == 0
    assert result.report_payload["stats"]["ignored_cleanup_operation_count"] == 0
    assert result.report_payload["ignored_cleanup_operations"] == []
    assert result.cleaned_markdown == markdown


def test_run_reader_cleanup_recovers_split_block_preview_when_parts_have_multi_space_gap() -> None:
    target = "ЗАГОЛОВОК  Первое предложение основного текста."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(b for b in payload["blocks"] if b["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "heading fused with body prose",
                        "confidence": "high",
                        "evidence_before": "Uppercase heading is fused with prose via double space.",
                        "safety_note": "Split at exact boundary.",
                        "split_substrings": ["ЗАГОЛОВОК", "Первое предложение основного текста."],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "ЗАГОЛОВОК\n\nПервое предложение основного текста." in result.cleaned_markdown
    assert any(
        warning.startswith("reader_cleanup_expected_after_preview_recovered:")
        for warning in result.report_payload["warnings"]
    )


def test_run_reader_cleanup_rejects_split_block_preview_recovery_when_parts_out_of_order() -> None:
    target = "Первое предложение. Второе предложение."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(b for b in payload["blocks"] if b["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "split_block",
                        "reason": "split into semantic units",
                        "confidence": "high",
                        "evidence_before": "Two sentences incorrectly fused.",
                        "safety_note": "Split at sentence boundary.",
                        "split_substrings": ["Второе предложение.", "Первое предложение."],
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown


def test_run_reader_cleanup_rejects_missing_critical_exact_match_field_without_silent_apply() -> None:
    target = "150 РАЗДЕЛ ОТЧЕТА Через призму рабочего процесса можно увидеть новые возможности."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if block["text"] == target)
        return json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "operation": "remove_inline_noise",
                        "reason": "page_furniture_inline",
                        "confidence": "high",
                        "evidence_before": "A non-semantic heading fragment should be removed from the paragraph prefix.",
                        "expected_after_preview": "Через призму рабочего процесса можно увидеть новые возможности.",
                        "safety_note": "Do not apply without the exact removable substring.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is False
    assert result.cleaned_markdown == markdown
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "noise_substring_not_found"


def test_run_reader_cleanup_preserves_already_good_list_formatting_without_operations() -> None:
    markdown = "Intro\n\n- первый пункт\n\n- второй пункт\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: '{"delete_blocks": [], "warnings": []}',
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown


def test_run_reader_cleanup_preserves_legitimate_plain_text_heading_like_paragraph_without_operations() -> None:
    markdown = (
        "Intro\n\n"
        "12 ФАКТОРОВ УСПЕХА Экономика устойчивого роста требует терпения, дисциплины и долгого горизонта планирования.\n\n"
        "Outro"
    )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: '{"delete_blocks": [], "warnings": []}',
    )

    assert result.cleaned_markdown == markdown
    assert result.changed is False


def test_run_reader_cleanup_strict_failure_raises_with_reviewable_report() -> None:
    markdown = "Intro\n\nBody paragraph\n\nOutro"

    with pytest.raises(ReaderCleanupStageError) as exc_info:
        run_reader_cleanup(
            markdown_text=markdown,
            config=ReaderCleanupConfig(enabled=True, policy="strict"),
            operation_provider=lambda payload, chunk_index, chunk_count: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    report_payload = exc_info.value.report_payload
    assert exc_info.value.raw_markdown == markdown
    assert report_payload["stage_status"] == "failed"
    assert report_payload["changed"] is False
    assert report_payload["failure"]["kind"] == "chunk_failed"
    assert report_payload["stats"]["failed_chunk_count"] == 1


def _normalize_heading_boundary_operation(
    block: Any,
    *,
    heading_substring: str,
    body_substring: str,
) -> dict[str, Any]:
    return {
        "id": str(block["id"]),
        "text_hash": str(block["text_hash"]),
        "operation": "normalize_heading_boundary",
        "reason": "heading_fused_with_body",
        "confidence": "high",
        "evidence_before": str(block["text"]),
        "expected_after_preview": f"{heading_substring}\n\n{body_substring}",
        "safety_note": "separate the heading from the body it is fused with",
        "heading_substring": heading_substring,
        "body_substring": body_substring,
    }


def test_run_reader_cleanup_rejects_the_operation_that_breaks_an_image_anchor() -> None:
    # Spec 052 item 5, reproducing the defect measured on the real replay books: four
    # accepted ``normalize_heading_boundary`` operations on creating_wealth (and one on
    # mazzucato) cut a figure block between "[[DOCX_IMAGE_" and "img_014]]". The anchor
    # stopped parsing, and the reconciler pasted the figure at the END of the document --
    # a chapter-2 diagram landing after the last page, with a green report.
    figure_block = "[[DOCX_IMAGE_img_014]] РИСУНОК 2.1. Архетип «Пределы роста»"
    markdown = f"Intro\n\n{figure_block}\n\nBody paragraph\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target = next(block for block in payload["blocks"] if block["text"] == figure_block)
        return json.dumps(
            {
                "cleanup_operations": [
                    _normalize_heading_boundary_operation(
                        target,
                        heading_substring="[[DOCX_IMAGE_",
                        body_substring="img_014]] РИСУНОК 2.1. Архетип «Пределы роста»",
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=provider,
    )

    # The operation is rejected by name, not patched up afterwards.
    assert [
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("operation") == "normalize_heading_boundary"
    ] == ["docx_image_anchor_lost_by_operation"]
    assert result.report_payload["accepted_cleanup_operations"] == []
    assert any(
        warning.startswith("reader_cleanup_image_anchor_lost_by_operation:")
        for warning in result.report_payload["warnings"]
    )
    # The anchor is intact and still in its own place -- not appended after "Outro".
    assert figure_block in result.cleaned_markdown
    assert result.cleaned_markdown.strip().endswith("Outro")
    assert result.report_payload["image_reconciliation"]["missing_image_ids"] == []
    assert result.report_payload["image_reconciliation"]["reinserted_image_ids"] == []


def test_run_reader_cleanup_keeps_unrelated_operations_when_rejecting_an_anchor_breaker() -> None:
    # Rejection is targeted: only the operation that lost the anchor is dropped. A clean
    # operation elsewhere in the document still applies.
    figure_block = "[[DOCX_IMAGE_img_014]] РИСУНОК 2.1. Архетип «Пределы роста»"
    fused_block = "ЗАГОЛОВОК РАЗДЕЛА Дальше идёт обычный текст параграфа без картинок."
    markdown = f"Intro\n\n{figure_block}\n\n{fused_block}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        figure_target = next(block for block in payload["blocks"] if block["text"] == figure_block)
        fused_target = next(block for block in payload["blocks"] if block["text"] == fused_block)
        return json.dumps(
            {
                "cleanup_operations": [
                    _normalize_heading_boundary_operation(
                        figure_target,
                        heading_substring="[[DOCX_IMAGE_",
                        body_substring="img_014]] РИСУНОК 2.1. Архетип «Пределы роста»",
                    ),
                    _normalize_heading_boundary_operation(
                        fused_target,
                        heading_substring="ЗАГОЛОВОК РАЗДЕЛА",
                        body_substring="Дальше идёт обычный текст параграфа без картинок.",
                    ),
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=provider,
    )

    assert [entry["id"] for entry in result.report_payload["accepted_cleanup_operations"]] == ["b_000002"]
    assert [
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("id") == "b_000001"
    ] == ["docx_image_anchor_lost_by_operation"]
    assert figure_block in result.cleaned_markdown
    assert "ЗАГОЛОВОК РАЗДЕЛА\n\nДальше идёт обычный текст" in result.cleaned_markdown


def test_reconcile_docx_image_placeholders_discards_cleanup_instead_of_appending() -> None:
    # Spec 052 item 5, the backstop: when an anchor is still missing after the responsible
    # operation could not be identified, the cleanup is discarded wholesale. It is never
    # "repaired" by pasting the anchor somewhere it did not come from.
    raw_markdown = "Intro\n\n[[DOCX_IMAGE_img_001]]\n\nChapter three body\n\nBibliography"
    cleaned_markdown = "Intro\n\nChapter three body\n\nBibliography"
    raw_blocks = build_cleanup_blocks(raw_markdown)

    reconciled, diagnostics = _reconcile_docx_image_placeholders(
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        raw_blocks=raw_blocks,
    )

    assert reconciled == raw_markdown
    assert not reconciled.strip().endswith("[[DOCX_IMAGE_img_001]]")
    assert diagnostics["cleanup_discarded_for_missing_image_ids"] is True
    assert diagnostics["missing_image_ids"] == ["img_001"]
    assert diagnostics["reinserted_image_ids"] == []
    assert diagnostics["missing_after_repair"] == []
    assert diagnostics["lost_image_source_block_ids"] == ["b_000001"]
    assert _image_reconciliation_warnings(diagnostics) == ["reader_cleanup_image_ids_lost_cleanup_discarded:1"]


@pytest.mark.parametrize(
    "prose",
    [
        # SHORT prose is the case the previous anti-regression missed: it only exercised a
        # 180-character paragraph, which passed for the one reason that had nothing to do
        # with the rule — it was over the 100-character cap. Every line below is under the
        # cap and was ``toc_like``, i.e. immune to the entire pass, until this fix.
        "In 1990 value was 5 and in 2000 rose to 10",
        "Between 1990 and 2000 revenue grew to 10",
        "Между 1990 и 2000 выручка выросла до 10",
        "Он родился в 1990",
        "Стоимость выросла до 10",
        "К 2000 году выручка достигла 10",
        "Компания открыла филиалы в Москве и Твери, а выручка выросла до 10",
        "Стартовая зарплата составляла менее 11",
        "The chapter closes on page 42",
        "Глава 1",
        # A decimal comma is not index punctuation: the page-reference pattern requires a
        # SPACE after the comma, which is the only thing keeping this line out.
        "Он заплатил 0,72 доллара в 1990 г.",
        # A comma-separated list of YEARS is the false positive the three-digit cap on a
        # page reference pays for: widen it to four digits and this sentence is immune.
        "Кризисы 1929, 1987, 2008, 2020 и 2023 годов изменили мировую экономику",
        # ...and the long shapes the previous test did cover, kept so the fix cannot be
        # rolled back to "long is prose, short is contents".
        (
            "Джеффри Фрид, автор бестселлера и классического труда в области образования, "
            "определил особенности стиля обучения современных студентов и показал, почему "
            "школьная система перестала отвечать их потребностям уже к 2000"
        ),
    ],
)
def test_toc_like_no_longer_captures_prose_that_merely_ends_in_a_number(prose: str) -> None:
    # A ``toc_like`` block is withheld from the model entirely, so a false positive here is
    # not a cosmetic mislabel — it is the pass silently doing nothing on that paragraph.
    assert _detect_block_kind(prose) == "paragraph"


def test_toc_like_no_longer_captures_prose_containing_an_ellipsis() -> None:
    # The other leaking branch: ``\.{3,}`` fired on an ellipsis typed as three periods, so
    # lietaer b_000006 -- 3 481 characters of jacket endorsements -- was "TOC-like" too.
    prose = (
        "«Лиетар и Данн объясняют, как и почему наша денежная система не может "
        "сбалансировать спрос и предложение, подрывает демократию и вознаграждает "
        "неустойчивый, разрушительный рост... Не умаляя того, что деньги дают нам "
        "сегодня, они проводят экскурсию по целому ряду реальных альтернатив»."
    )

    assert _detect_block_kind(prose) == "paragraph"


@pytest.mark.parametrize(
    ("block_id", "contents_line"),
    [
        # lietaer's real table of contents, verbatim — including the line that crosses the
        # roman→arabic pagination seam and so carries only two page references.
        ("b_000020", "Предисловие ix Введение: от дефицита к процветанию в рамках одного поколения 1"),
        (
            "b_000022",
            "1 Крах денег: конкурентное общество 11 2 Миф о деньгах: что это такое на самом деле 23 "
            "3 Судьба хуже долга: скрытые последствия процентов 37",
        ),
        ("b_000024", "4 Летучие рыбы: новый взгляд на деньги 57 5 Будущее уже наступило, но распределено неравномерно..."),
        (
            "b_000025",
            "Пока что! 73 6 Стратегии для банковской сферы 95 7 Стратегии для бизнеса и предпринимателей 119 "
            "8 Стратегии для государственных органов 141 9 Стратегии для НКО 159",
        ),
        # ...and its subject index: the head, a bare page-reference column continued across
        # a page break, and the dense multi-entry runs — including the three blocks the
        # recorded lietaer run proposed operations on, which must stay refused.
        ("b_001723", "**ПРЕДМЕТНЫЙ УКАЗАТЕЛЬ** Изобилие: в Куритибе, 142; устойчивое, 5–6, 55, 224; и ценность, 80"),
        ("b_001789", "99, 102"),
        ("b_001809", "179– 180"),
        (
            "b_001763",
            "Демократия: на Бали, 187–188, 190–191; гражданское общество и, 147–148; концентрация богатства "
            "и, 21–22, 52–53; в принципиальном обществе, 193–194; регио и, 191; социальный капитал и, 46.",
        ),
        (
            "b_001828",
            "Рационализм, 217; эпоха Просвещения, 15, 29–30; рынки как проявление, 4; "
            "сберегательно-кредитная система, 112; сберегательные баллы, 110 Реализм, 30 Саваяка Фукуси, 166–167",
        ),
        (
            "b_001792",
            "Экологически чистые продукты, 152, 186; Гринвошинг, 198; Валовой внутренний продукт "
            "(ВВП), 34–35, 131, 146; Валовое национальное счастье, 131",
        ),
        # A dotted leader terminated by a page number — the classic contents entry.
        ("synthetic", "Введение: от дефицита к процветанию ......... 12"),
    ],
)
def test_toc_like_still_captures_genuine_contents_and_index_lines(block_id: str, contents_line: str) -> None:
    # The rule must keep contents/index material out of the model's hands: every line here
    # is taken verbatim from lietaer's contents and subject index (the one exception is
    # labelled synthetic), and each one is measured ``toc_like``.
    assert _detect_block_kind(contents_line) == "toc_like", block_id


@pytest.mark.parametrize(
    ("leader", "line"),
    [
        # The four leader spellings the pattern has to keep, including the two the
        # per-branch lookbehind exists for.
        ("dots", "Введение: от дефицита к процветанию ......... 12"),
        ("three dots, the minimum", "Глава 1 ... 7"),
        ("ellipsis characters", "Введение …… 12"),
        # A dot run beginning immediately after an ellipsis CHARACTER. A single shared
        # `(?<![.…])` guard would reject this line; the per-branch lookbehind keeps it.
        ("an ellipsis character then dots", "Раздел…...4"),
        ("no space before the page number", "Итоги.......1234"),
    ],
)
def test_toc_leader_is_recognised_in_every_spelling_that_used_to_be_recognised(
    leader: str, line: str
) -> None:
    assert _detect_block_kind(line) == "toc_like", leader


def test_toc_leader_pattern_stays_linear_on_a_pathological_run_of_dots() -> None:
    """A dotted OCR artefact must not stall block building before a token is spent.

    The leader alternation used to be an unanchored `(?:\\.{3,}|…{2,})`, which restarts at
    every offset of a dot run and rescans the remainder from each: quadratic. Measured on
    the pre-fix pattern, one block of dots cost 0.0092 s at 1 000, 0.96 s at 10 000, 8.3 s
    at 30 000 and **92.9 s at 100 000** — and `build_cleanup_blocks` classifies every block
    of the book, so a single artefact of this shape hangs the pass for minutes with no LLM
    call in sight. The same sizes cost 0.0001 / 0.0005 / 0.0015 / 0.0052 s after the fix.

    The sizes are graded smallest-first on purpose: a regression fails on the 10 000 case
    within a second instead of making the suite sit through the 100 000 one.
    """
    budget_seconds = 0.5
    for dot_count in (10_000, 30_000, 100_000):
        artefact = "." * dot_count
        started = time.perf_counter()
        kind = _detect_block_kind(artefact)
        elapsed = time.perf_counter() - started
        assert elapsed < budget_seconds, (
            f"classifying a block of {dot_count} dots took {elapsed:.3f} s, over the "
            f"{budget_seconds} s budget. The leader pattern has gone superlinear again — "
            "it must not be searched unanchored inside its own run."
        )
        # Behaviour, not just speed: a bare run of dots carries no page number, so it was
        # never a contents entry and must not become one.
        assert kind != "toc_like", dot_count


def _run_with_delete_of_the_contents_line(
    *, keep_toc: bool, contents_line: str
) -> tuple[list[dict[str, Any]], Any]:
    markdown = f"Обычный абзац, который ничем не примечателен.\n\n{contents_line}\n\nPage 1"
    captured: list[dict[str, Any]] = []

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        captured.append(payload)
        target = next(
            (block for block in payload["blocks"] if block["text"] == contents_line), None
        )
        if target is None:
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        return json.dumps(
            {
                "cleanup_operations": [
                    _delete_block_operation(target, reason="page_number", confidence="high")
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(
            enabled=True,
            keep_toc=keep_toc,
            max_delete_block_ratio=0.8,
            max_delete_char_ratio=0.8,
        ),
        operation_provider=provider,
    )
    return captured, result


def test_toc_like_blocks_are_sent_to_the_model_and_protected_only_at_validation() -> None:
    """`keep_toc=True` buys immunity, NOT a smaller request — and the tools must say so.

    `_select_cleanup_blocks` returns every block when `keep_toc` is true (the default),
    so `toc_like` blocks are serialised into the payload and paid for in tokens;
    `_build_protected_block_ids` then refuses any operation that targets them. The
    replay tool used to comment its `toc_like_block_count` as "the size of the pass's
    blind spot", naming a saving that is not made. This pins the real behaviour so the
    wording cannot drift back.
    """
    contents_line = "Введение: от дефицита к процветанию ......... 12"
    assert _detect_block_kind(contents_line) == "toc_like"

    captured, result = _run_with_delete_of_the_contents_line(
        keep_toc=True, contents_line=contents_line
    )

    assert captured, "the pass made no request at all"
    assert any(block["text"] == contents_line for block in captured[0]["blocks"]), (
        "a toc_like block was withheld from the payload under keep_toc=True. If that is "
        "now intended, the replay tool's toc_like_blocks_sent_to_model field and spec 052 "
        "both describe the opposite."
    )
    # Immunity, not exclusion: the model asked for the delete and the validator refused it.
    assert contents_line in result.cleaned_markdown
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 0


def test_keep_toc_false_is_what_actually_withholds_toc_blocks_from_the_model() -> None:
    """The other half of the contract, so the test above cannot pass for a trivial reason."""
    contents_line = "Введение: от дефицита к процветанию ......... 12"

    captured, result = _run_with_delete_of_the_contents_line(
        keep_toc=False, contents_line=contents_line
    )

    assert captured, "the pass made no request at all"
    assert not any(block["text"] == contents_line for block in captured[0]["blocks"])
    assert contents_line in result.cleaned_markdown


@pytest.mark.parametrize(
    ("what_it_would_have_been", "not_contents"),
    [
        # Each line below is a measured near-miss from the three books: it carries numbers
        # in almost the right place, and one specific narrowing in the rule is the only
        # thing keeping it out. Loosen that spelling and the block silently goes immune.
        ("a notes-section chapter header", "Глава 1"),
        ("a publisher address", "235 Montgomery Street, Suite 650"),
        ("an endnote continued mid-sentence", "3. “$22,350 a Year for a Family of Four or $10,890 for an Individual in the 48"),
        ("a citation ending in a date", "52. Дж. Сакс, «Лекарство, которое разоряет Америку», Huffington Post, 16"),
        ("a citation ending in a page", "29. Р. Райх, «Экономист Джон Мейнард Кейнс», журнал TIME, 29"),
        ("an ellipsis followed by a number mid-sentence", "Нужно всего три вещи... 50 долларов, пульс и умение поставить свою подпись"),
        ("a bibliography year after a comma", "14. Forbes, 2017."),
        ("a journal volume and page range", "Business Review, 89 (2011), стр. 62–77."),
        ("Russian decimal commas", "0,72 в 1990 г.; 1,11 в 2000 г. и 0,39 в 2001 г. В США он составлял 0 в 1999 г."),
        ("endnote superscripts glued to a full stop", "Первая версия появилась в 1953 году.12 СНС позиционирует себя как база.13 Она определяет счетоводство.14 ВВП это мера.15"),
        ("currency amounts before a capitalised unit", "Таким образом, на счет Лизы зачисляется 10 L15, а со счета Энн списывается 10 L15. Ей нужно 30 L15."),
        (
            # lietaer b_000091, trimmed: three comma-introduced numbers, but 26 words —
            # the density ratio is the only thing keeping this paragraph out.
            "a statistics-heavy paragraph",
            "Половина живет в семьях, возглавляемых супружеской парой; 49 процентов живут в пригородах. "
            "Почти половина — белые нелатиноамериканского происхождения, 18 процентов — чернокожие, "
            "26 процентов — латиноамериканцы.",
        ),
        ("a title in an italian bibliography entry", "Rivoluzione francese,” Rivista di Storia Economica 1, no. 1 (Турин, 1936)."),
        ("a figure-step list", "(на этапах 1d, 2a, 2b, 2c и 4a) обозначают операционный жизненный цикл обращения Terra."),
        ("a dateline", "ДУБЛИН, ИРЛАНДИЯ, 5 АВГУСТА 2020 Г."),
        ("a URL ending in digits", "BBC, 10 апреля 2017 г.: http://www.bbc.co.uk/news/business-39548313"),
    ],
)
def test_toc_like_rejects_the_measured_near_misses(what_it_would_have_been: str, not_contents: str) -> None:
    assert _detect_block_kind(not_contents) != "toc_like", what_it_would_have_been


def test_toc_like_thresholds_are_driven_by_their_constants() -> None:
    # Every threshold the rule turns on, exercised on both sides so a change to any of the
    # constants has to be a deliberate one.

    # An index run needs the minimum number of page references, whatever its length.
    references = "; понятие, 55" * (_TOC_MIN_PAGE_REFERENCE_TOKENS - 1)
    assert _detect_block_kind("Начало раздела и его продолжение" + references) == "paragraph"
    assert _detect_block_kind("Начало раздела и его продолжение" + references + "; понятие, 55") == "toc_like"

    # ...and they must be dense against the word count: the same references diluted by
    # enough prose read as a paragraph that happens to cite pages, not as an index.
    diluted = " слово" * (int(_TOC_MIN_PAGE_REFERENCE_TOKENS / _TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO) + 1)
    assert (
        _detect_block_kind("Начало раздела и его продолжение" + references + "; понятие, 55" + diluted)
        == "paragraph"
    )

    # A contents run needs the minimum number of bare page numbers at entry boundaries.
    entries = "".join(f" Раздел {10 + index}" for index in range(_TOC_MIN_CONTENTS_ENTRY_TOKENS - 1))
    assert _detect_block_kind("Оглавление" + entries) == "paragraph"
    assert _detect_block_kind("Оглавление" + entries + " Раздел 99") == "toc_like"


def test_toc_like_reads_a_roman_page_number_by_its_form_and_position_only() -> None:
    # lietaer b_000020 is the contents line that crosses the front-matter pagination seam:
    # it carries exactly two page references, one roman and one arabic, so it is one short
    # of the bare-number count and is recognised only if the roman one reads as a page.
    seam_line = "Предисловие ix Введение: от дефицита к процветанию в рамках одного поколения 1"
    assert _detect_block_kind(seam_line) == "toc_like"
    assert _TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN < _TOC_MIN_CONTENTS_ENTRY_TOKENS

    # Nothing lexical decides that a token is a numeral — no list of words, no list of
    # numerals. MAGNITUDE does: front matter stops short of its hundredth page, so a numeral
    # spelled with the hundreds or thousands symbols is not a front-matter page number at
    # all. That is what keeps lietaer b_001398's Italian title out ("di" is 501), where the
    # previous spelling of this rule needed a hand-kept list of look-alike words.
    assert _detect_block_kind("Rivoluzione francese,” Rivista di Storia Economica 1, no. 1 (Турин, 1936).") == "paragraph"
    assert _detect_block_kind("Предисловие mix Введение: от дефицита 1") == "paragraph"  # mix = 1009
    assert _detect_block_kind("Предисловие ci Введение: от дефицита 1") == "paragraph"  # ci = 101
    assert _detect_block_kind("Предисловие i Введение: от дефицита 1") == "paragraph"  # one letter is no shape

    # ...and POSITION does the rest: the numeral counts only where an arabic page number
    # would count — at an entry boundary — and only in a block an arabic page number already
    # paginates. It can corroborate a contents run; it can never establish one.
    assert _detect_block_kind("Мы использовали vi чтобы открыть Файл 12") == "paragraph"
    assert _detect_block_kind("Предисловие ix Введение к теме") == "paragraph"


def test_toc_narrowing_frees_prose_for_operations_that_immunity_used_to_block() -> None:
    # Effect, not mechanism: a paragraph of prose ending in a number used to be refused with
    # ``toc_protected``. It is now an ordinary block and a lawful operation applies to it.
    prose_block = (
        "ЗАКЛЮЧЕНИЕ ГЛАВЫ Экономика устойчивого роста требует терпения и долгого горизонта "
        "планирования, а первые результаты такой политики проявляются не раньше чем через 10"
    )
    markdown = f"Intro\n\n{prose_block}\n\nOutro"

    def provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        target = next(block for block in payload["blocks"] if block["text"] == prose_block)
        return json.dumps(
            {
                "cleanup_operations": [
                    _normalize_heading_boundary_operation(
                        target,
                        heading_substring="ЗАКЛЮЧЕНИЕ ГЛАВЫ",
                        body_substring=(
                            "Экономика устойчивого роста требует терпения и долгого горизонта "
                            "планирования, а первые результаты такой политики проявляются не раньше чем через 10"
                        ),
                    )
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=provider,
    )

    assert "toc_protected" not in {
        str(entry.get("ignored_reason")) for entry in result.report_payload["ignored_cleanup_operations"]
    }
    assert [entry["operation"] for entry in result.report_payload["accepted_cleanup_operations"]] == [
        "normalize_heading_boundary"
    ]
