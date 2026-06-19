import json
from pathlib import Path

import pytest
from typing import Any

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


def _reclassify_role_operation(
    block: Any,
    *,
    target_role: str,
    expected_after_preview: str,
    confidence: str = "high",
    reason: str = "role_assignment_correction",
) -> dict[str, Any]:
    if isinstance(block, dict):
        block_id = str(block["id"])
        text_hash = str(block["text_hash"])
        text = str(block.get("text") or "")
    else:
        block_id = str(block.block_id)
        text_hash = str(block.text_hash)
        text = str(block.text)
    return {
        "id": block_id,
        "text_hash": text_hash,
        "operation": "reclassify_role",
        "reason": reason,
        "confidence": confidence,
        "evidence_before": text,
        "expected_after_preview": expected_after_preview,
        "safety_note": "Change only the local role marker; preserve visible text.",
        "target_role": target_role,
    }


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
    assert config.max_reclassify_block_ratio == 0.05


def test_resolve_reader_cleanup_config_accepts_reclassify_cap() -> None:
    config = resolve_reader_cleanup_config(
        app_config={
            "reader_cleanup_enabled": True,
            "reader_cleanup_max_reclassify_block_ratio": 0.12,
        },
        fallback_model="fallback:model",
    )

    assert config.max_reclassify_block_ratio == 0.12


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


def test_run_reader_cleanup_partial_chunk_failure_below_default_ratio_stays_completed() -> None:
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

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nBody paragraph"
    assert result.report_payload["stage_status"] == "completed"
    assert result.report_payload["stats"]["cleanup_chunk_count"] == 3
    assert result.report_payload["stats"]["failed_chunk_count"] == 1
    assert result.report_payload["accepted_delete_blocks"][0]["raw_text_preview"] == "Page 1"


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
    assert "If pass_name is anchor_repair" in prompt
    assert "If a duplicate_fragment candidate is only similar to nearby prose" in prompt
    assert "Do not widen remove_inline_noise to consume a semantic heading" in prompt
    assert "noise_substring combines a page-like number with semantic section-title text" in prompt


def test_reader_cleanup_system_prompt_mentions_anchor_repair_constraints() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "Return only a single valid JSON object" in prompt
    assert "Do not wrap it in markdown fences" in prompt
    assert '{"cleanup_operations":[],"warnings":[]}' in prompt
    assert "If the request pass_name is anchor_repair" in prompt
    assert "If one anchored block needs both page-furniture removal and heading/body repair" in prompt
    assert "For fragmented paragraph anchors, use neighbor context" in prompt
    assert "For anchor_repair fragmented_paragraph targets, first inspect only adjacent payload blocks" in prompt
    assert "copy next_id and next_text_hash exactly from the current payload block list" in prompt
    assert "exact normalized text already preserved in one nearby payload block" in prompt
    assert "For anchor_repair page_furniture_inline targets, first propose remove_inline_noise" in prompt
    assert "do not use join_fragmented_paragraph or delete_block as a substitute for that cleanup" in prompt
    assert "For inline endnote/page marker artifacts inside prose" in prompt
    assert "exact deleted span in noise_substring" in prompt
    assert "reclassify_role" in prompt
    assert "target_role as one of heading, body, attribution, caption" in prompt
    assert "Do not assign heading_level, hierarchy, anchors, or cross-chunk structure" in prompt
    assert "ALL-CAPS short text after a heading may be attribution" in prompt
    assert "Figure/Table/Рис./Таблица/Источник lines are caption" in prompt
    assert "For duplicate semantic heading text repeated inline" in prompt
    assert "operation_selection_targets lists a duplicate_semantic_heading_text candidate" in prompt
    assert "operation_selection_targets lists a side_heading_island_candidate" in prompt
    assert "operation_selection_targets lists a semantic_page_title_deletion_risk candidate" in prompt
    assert "operation_selection_targets lists an isolated_semantic_heading_numeric_prefix candidate" in prompt
    assert "operation_selection_targets lists a heading_fused_with_body_candidate" in prompt
    assert "join_fragmented_paragraph then normalize_heading_boundary chain" in prompt
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
    assert "add a separate same-block follow-up remove_inline_noise for only the exact numeric prefix in the same pass" in prompt
    assert "do not remove the title with remove_inline_noise" in prompt
    assert "remove only the exact numeric prefix when safe; never remove the heading text" in prompt
    assert "do not propose remove_inline_noise for that combined span" in prompt
    assert "bad: remove_inline_noise for the whole '20 NEW FORMS OF MONEY?'" in prompt
    assert 'bad: remove_inline_noise "Три мультинациональные валюты"' in prompt
    assert "Good: extract_side_heading_and_reattach_body" in prompt
    assert "page furniture plus an image caption sits between two parts of one sentence" in prompt
    assert "if the number is semantic content inside a sentence" in prompt
    assert "title-case running-header island with connector words or acronyms" in prompt
    assert "Полевой отчет НКО 167" in prompt
    assert "3 Городское управление 201" in prompt
    assert "БЕСПЛАТНЫЕ КЛИНИКИ И «ИТАКСКИЕ ЧАСЫ»" in prompt
    assert "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР." in prompt
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


def test_run_reader_cleanup_reclassifies_body_subheading_to_markdown_heading() -> None:
    markdown = "Intro paragraph\n\nTHE MERCANTILISTS: TRADE AND TREASURE\n\nBody paragraph\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_reclassify_block_ratio=0.5),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _reclassify_role_operation(
                        block,
                        target_role="heading",
                        expected_after_preview="## THE MERCANTILISTS: TRADE AND TREASURE",
                        reason="semantic_heading",
                    )
                    for block in payload["blocks"]
                    if block["text"] == "THE MERCANTILISTS: TRADE AND TREASURE"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro paragraph\n\n## THE MERCANTILISTS: TRADE AND TREASURE\n\nBody paragraph\n\nOutro paragraph"
    )
    assert build_cleanup_blocks(result.cleaned_markdown)[1].is_heading is True
    accepted = result.report_payload["accepted_cleanup_operations"]
    assert accepted[0]["operation"] == "reclassify_role"
    assert accepted[0]["target_role"] == "heading"
    assert accepted[0]["after_state"] == "role_reclassified_to_heading"


def test_run_reader_cleanup_reclassifies_heading_attribution_to_body_markdown() -> None:
    markdown = "Intro paragraph\n\n# VIRGIL\n\nQuoted paragraph body.\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_reclassify_block_ratio=0.5),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _reclassify_role_operation(
                        block,
                        target_role="attribution",
                        expected_after_preview="VIRGIL",
                        reason="semantic_attribution",
                    )
                    for block in payload["blocks"]
                    if block["text"] == "# VIRGIL"
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown == "Intro paragraph\n\nVIRGIL\n\nQuoted paragraph body.\n\nOutro paragraph"
    assert build_cleanup_blocks(result.cleaned_markdown)[1].is_heading is False
    accepted = result.report_payload["accepted_cleanup_operations"]
    assert accepted[0]["target_role"] == "attribution"
    assert accepted[0]["after_state"] == "role_reclassified_to_attribution"


def test_run_reader_cleanup_reclassifies_heading_caption_to_body_markdown() -> None:
    markdown = "Intro paragraph\n\n# FIGURE 1. Productive and unproductive investment\n\nBody paragraph\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_reclassify_block_ratio=0.5),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _reclassify_role_operation(
                        block,
                        target_role="caption",
                        expected_after_preview="FIGURE 1. Productive and unproductive investment",
                        reason="semantic_caption",
                    )
                    for block in payload["blocks"]
                    if block["text"].startswith("# FIGURE 1.")
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert "# FIGURE" not in result.cleaned_markdown
    accepted = result.report_payload["accepted_cleanup_operations"]
    assert accepted[0]["target_role"] == "caption"


def test_run_reader_cleanup_rejects_invalid_reclassify_direction() -> None:
    markdown = "Intro paragraph\n\nFIGURE 1. Productive and unproductive investment\n\nBody paragraph\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_reclassify_block_ratio=0.5),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _reclassify_role_operation(
                        block,
                        target_role="caption",
                        expected_after_preview="FIGURE 1. Productive and unproductive investment",
                        reason="semantic_caption",
                    )
                    for block in payload["blocks"]
                    if block["text"].startswith("FIGURE 1.")
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is False
    ignored = result.report_payload["ignored_cleanup_operations"]
    assert ignored[0]["ignored_reason"] == "reclassify_source_role_incompatible"
    assert ignored[0]["target_role"] == "caption"


def test_run_reader_cleanup_caps_reclassify_role_operations() -> None:
    markdown = "Intro paragraph\n\nFIRST MISSED SUBHEADING\n\nSECOND MISSED SUBHEADING\n\nBody paragraph\n\nOutro paragraph"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_reclassify_block_ratio=0.3),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    _reclassify_role_operation(
                        block,
                        target_role="heading",
                        expected_after_preview=f"## {block['text']}",
                        reason="semantic_heading",
                    )
                    for block in payload["blocks"]
                    if str(block["text"]).endswith("MISSED SUBHEADING")
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        ),
    )

    assert result.changed is True
    assert result.cleaned_markdown.count("## ") == 1
    assert result.report_payload["stats"]["accepted_reclassify_role_count"] == 1
    ignored = result.report_payload["ignored_cleanup_operations"]
    assert ignored[0]["ignored_reason"] == "reclassify_global_safety_limit_exceeded"
    assert ignored[0]["target_role"] == "heading"


def test_reader_cleanup_schema_repair_prompt_mentions_fragmented_anchor_join_safety() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt()

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
    assert "reader_cleanup_missing_confidence_inferred:b_000001:high" in result.report_payload["warnings"]
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 0
    assert result.report_payload["image_reconciliation"]["before_image_id_count"] == 1
    assert result.report_payload["image_reconciliation"]["after_image_id_count"] == 1
    assert {
        entry["ignored_reason"]
        for entry in result.report_payload["ignored_cleanup_operations"]
        if entry.get("id") == "b_000001"
    } == {"docx_image_anchor_protected"}


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
    assert "МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ" in prompt
    assert "РАБОЧАЯ ГРУППА Во время пилотного проекта" in prompt
    assert "ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ. Ключевые аспекты" in prompt
    assert "4 Практический раздел 57 5 Следующая глава" in prompt
    assert "ГРАЖДАНСКАЯ ВАЛЮТА: ЭКОНОМИЧЕСКИЙ СТИМУЛ БЕЗ ДОЛГОВ" not in prompt
    assert "4 Летучая рыба: новый взгляд на деньги 57 5 Будущее уже наступило" not in prompt
    assert "duplicate_fragment" in prompt


def test_reader_cleanup_schema_repair_prompt_preserves_bounded_title_case_running_header_islands() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt()

    assert "title-case running-header island with connector words or acronyms" in prompt
    assert "keep it as remove_inline_noise" in prompt


def test_reader_cleanup_prompt_does_not_encourage_title_subtitle_or_question_as_body_prose() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "ОТЧЕТ И ВЫВОДЫ: краткий обзор" in prompt
    assert "ГОРОДСКОЕ УПРАВЛЕНИЕ Что дальше?" in prompt
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
    assert duplicate_target["operation_hint"] == "remove_inline_noise"
    assert duplicate_target["reason_hint"] == "duplicate_fragment"
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
    assert fused_target["preferred_operation"] == "normalize_heading_boundary"
    assert fused_target["reason_hint"] == "heading_fused_with_body"
    assert fused_target["heading_substring"] == "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ"
    assert fused_target["body_substring"] == (
        "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
    )
    assert fused_target["expected_after_preview"] == (
        "ПЯТЬ МИЛЛИАРДОВ ЛЮДЕЙ НЕ ИМЕЮТ ДОСТУПА К ИНТЕРНЕТУ\n\n"
        "Вдохновившись примером Куритибы, предприниматель задумал создать новую валюту."
    )
    assert fused_target["forbidden_operations"] == ["remove_inline_noise", "delete_block"]
    assert "not noise" in fused_target["safety_note"]


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
    assert fused_target["preferred_operation_chain"] == [
        "join_fragmented_paragraph",
        "normalize_heading_boundary",
    ]
    assert fused_target["next_id"] == second_block["id"]
    assert fused_target["next_text_hash"] == second_block["text_hash"]
    assert fused_target["heading_substring"] == "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ."
    assert fused_target["body_substring"] == "Авиабизнес отличается жесткой конкуренцией."
    assert fused_target["expected_after_preview"] == (
        "ВАЛЮТА, ОБЪЕДИНЯЮЩАЯ ЭФФЕКТИВНОСТЬ И СПРАВЕДЛИВОСТЬ.\n\n"
        "Авиабизнес отличается жесткой конкуренцией."
    )
    assert fused_target["forbidden_operations"] == ["remove_inline_noise", "delete_block"]


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
    assert side_heading_target["operation_hint"] == (
        "preserve_heading_text_with_split_block_or_normalize_heading_boundary"
    )
    assert side_heading_target["preferred_operation_order"] == ["split_block", "normalize_heading_boundary"]
    assert side_heading_target["reattach_operation_hint"] == "extract_side_heading_and_reattach_body"
    assert side_heading_target["forbidden_default_operation"] == "remove_inline_noise"
    assert "pre-heading stub or orphan post-heading continuation" in side_heading_target[
        "stub_continuation_risk"
    ]
    assert side_heading_target["reattach_expected_after_preview_shape"] == (
        "heading_substring + blank line + pre_body_stub + space + post_body_continuation; "
        "no labels and no body-first preview."
    )
    assert "Semantic heading islands are not noise" in side_heading_target["safety_note"]
    assert "Do not delete with remove_inline_noise" in side_heading_target["safety_note"]
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
    assert semantic_title_target["forbidden_operation"] == "remove_inline_noise"
    assert semantic_title_target["operation_hint"] == "preserve_title_with_exact_structural_operation_or_skip"
    assert semantic_title_target["after_structural_split_followup_operation"] == "remove_inline_noise"
    assert semantic_title_target["same_pass_followup_supported"] is True
    assert semantic_title_target["followup_targets_same_original_block_id"] is True
    assert semantic_title_target["after_structural_split_noise_substring"] == "20 "
    assert semantic_title_target["semantic_heading_must_remain_after_followup"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert semantic_title_target["after_structural_split_expected_after_preview"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert "Do not delete the title with remove_inline_noise" in semantic_title_target["safety_note"]


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
    assert numeric_prefix_target["preferred_operation"] == "remove_inline_noise"
    assert numeric_prefix_target["reason_hint"] == "page_number"
    assert numeric_prefix_target["forbidden_operation"] == "full-heading remove_inline_noise"
    assert numeric_prefix_target["numeric_prefix"] == "20 "
    assert numeric_prefix_target["semantic_heading_must_remain"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert numeric_prefix_target["expected_after_preview"] == "НОВЫЕ ФОРМЫ ДЕНЕГ?"
    assert "never remove the semantic heading text" in numeric_prefix_target["safety_note"]


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
