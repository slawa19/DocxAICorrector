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
    run_reader_cleanup,
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


def test_build_cleanup_blocks_assigns_stable_ids_and_hashes() -> None:
    blocks = build_cleanup_blocks("# Heading\n\nPage 1\n\nBody paragraph")

    assert [block.block_id for block in blocks] == ["b_000000", "b_000001", "b_000002"]
    assert blocks[0].is_heading is True
    assert blocks[1].kind == "page_number"
    assert len({block.text_hash for block in blocks}) == 3


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
    markdown = "Intro\n\n10\n\nOutro"

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


def test_reader_cleanup_schema_repair_prompt_forbids_rewritten_markdown() -> None:
    prompt = build_reader_cleanup_schema_repair_system_prompt()

    assert "Return JSON only with top-level fields cleanup_operations and warnings." in prompt
    assert "Do not return rewritten Markdown, cleaned Markdown, commentary, or extra top-level fields." in prompt
    assert "Repair every invalid cleanup operation item in the response, not only the first broken one." in prompt
    assert "If the original response uses legacy delete_blocks, convert it into cleanup_operations" in prompt
    assert "If pass_name is anchor_repair" in prompt
    assert "If a duplicate_fragment candidate is only similar to nearby prose" in prompt
    assert "Do not widen remove_inline_noise to consume a semantic heading" in prompt


def test_reader_cleanup_system_prompt_mentions_anchor_repair_constraints() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "If the request pass_name is anchor_repair" in prompt
    assert "If one anchored block needs both page-furniture removal and heading/body repair" in prompt
    assert "For fragmented paragraph anchors, use neighbor context" in prompt
    assert "if the number is semantic content inside a sentence" in prompt
    assert "title-case running-header island with connector words or acronyms" in prompt
    assert "Полевой отчет НКО 167" in prompt
    assert "3 Городское управление 201" in prompt
    assert "БЕСПЛАТНЫЕ КЛИНИКИ И «ИТАКСКИЕ ЧАСЫ»" in prompt
    assert "ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР." in prompt
    assert "Стратегии для НКО 167" not in prompt
    assert "3 Управление и мы, граждане 201" not in prompt


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
    assert report_payload["stage_status"] == "failed_preserved_base_result"
    assert report_payload["chunk_results"][0]["repair_attempted"] is True
    assert report_payload["chunk_results"][0]["repair_status"] == "failed"
    assert any("reader_cleanup_schema_repair_failed:1:" in warning for warning in report_payload["warnings"])


def test_run_reader_cleanup_cleanup_operations_delete_block_requires_audit_fields() -> None:
    markdown = "Intro\n\n10\n\nOutro"
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
    assert result.cleaned_markdown == "Intro\n\nOutro"
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


def test_run_reader_cleanup_infers_missing_confidence_for_safe_extraction_artifact_delete() -> None:
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

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nBody paragraph\n\nOutro"
    assert "reader_cleanup_missing_confidence_inferred:b_000001:high" in result.report_payload["warnings"]
    assert result.report_payload["stats"]["accepted_delete_block_count"] == 1


def test_run_reader_cleanup_rejects_incompatible_duplicate_operation_with_explicit_reason() -> None:
    markdown = "Intro\n\n10\n\nBody paragraph\n\nOutro"
    blocks = build_cleanup_blocks(markdown)

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True, max_delete_block_ratio=0.8, max_delete_char_ratio=0.8),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "cleanup_operations": [
                    {
                        "id": blocks[1].block_id,
                        "text_hash": blocks[1].text_hash,
                        "operation": "delete_block",
                        "reason": "page_number",
                        "confidence": "high",
                        "evidence_before": "Standalone page number block.",
                        "expected_after_preview": "",
                        "safety_note": "Only the page number block should be removed.",
                    },
                    {
                        "id": blocks[1].block_id,
                        "text_hash": blocks[1].text_hash,
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
    assert result.cleaned_markdown == "Intro\n\nBody paragraph\n\nOutro"
    assert result.report_payload["stats"]["failed_chunk_count"] == 0
    assert result.report_payload["ignored_delete_blocks"][0]["ignored_reason"] == "duplicate_operation_incompatible"


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
    assert "copy body_substring verbatim as the full body tail after that boundary" in prompt
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
                        "body_substring": "Деньги — это рычаг власти.",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "СТРАТЕГИИ РАЗВИТИЯ\n\nДеньги — это рычаг власти. Второе предложение тоже должно сохраниться." in result.cleaned_markdown


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
    assert report_payload["stage_status"] == "failed_preserved_base_result"
    assert report_payload["changed"] is False
    assert report_payload["failure"]["kind"] == "chunk_failed"
    assert report_payload["stats"]["failed_chunk_count"] == 1
