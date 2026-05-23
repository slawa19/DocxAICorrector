import json
from pathlib import Path

import pytest

from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupConfig,
    ReaderCleanupStageError,
    build_cleanup_blocks,
    build_reader_cleanup_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    run_reader_cleanup,
    write_reader_cleanup_diagnostics,
)


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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "page_number" if block["text"] == "10" else "repeated_running_header",
                        "confidence": "high",
                    }
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


def test_run_reader_cleanup_repairs_schema_once_and_applies_repaired_operation() -> None:
    target = "150 ПРОЦВЕТАНИЕ Через призму дополнительных валют можно увидеть новые возможности для местной экономики."
    markdown = f"Intro\n\n{target}\n\nOutro"
    repair_calls: list[dict[str, object]] = []

    def operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "noise_substring": "150 ПРОЦВЕТАНИЕ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
        repair_calls.append(payload)
        original_response = payload["original_response"]
        repaired_operation = dict(original_response["cleanup_operations"][0])
        repaired_operation.update(
            {
                "evidence_before": "Page furniture is fused to the semantic paragraph prefix.",
                "expected_after_preview": "Через призму дополнительных валют можно увидеть новые возможности для местной экономики.",
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
        "Intro\n\nЧерез призму дополнительных валют можно увидеть новые возможности для местной экономики.\n\nOutro"
    )
    assert any("reader_cleanup_schema_validation_failed:1:" in warning for warning in result.report_payload["warnings"])
    assert "reader_cleanup_schema_repair_attempted:1" in result.report_payload["warnings"]
    assert "reader_cleanup_schema_repair_succeeded:1" in result.report_payload["warnings"]
    assert result.report_payload["chunk_results"][0]["repair_attempted"] is True
    assert result.report_payload["chunk_results"][0]["repair_status"] == "succeeded"


def test_run_reader_cleanup_repair_failure_is_noop_in_advisory_mode() -> None:
    target = "150 ПРОЦВЕТАНИЕ Через призму дополнительных валют можно увидеть новые возможности для местной экономики."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "noise_substring": "150 ПРОЦВЕТАНИЕ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
        original_response = payload["original_response"]
        repaired_operation = dict(original_response["cleanup_operations"][0])
        repaired_operation["expected_after_preview"] = "Через призму дополнительных валют можно увидеть новые возможности для местной экономики."
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
    target = "150 ПРОЦВЕТАНИЕ Через призму дополнительных валют можно увидеть новые возможности для местной экономики."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "noise_substring": "150 ПРОЦВЕТАНИЕ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    def repair_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
    repair_calls: list[dict[str, object]] = []

    def operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def repair_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
    payloads: list[dict[str, object]] = []

    def anchor_operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def anchor_operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def anchor_operation_provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "extraction_artifact",
                    }
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


def test_run_reader_cleanup_ignores_duplicate_operation_without_failing_chunk() -> None:
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
    assert "reader_cleanup_duplicate_operation_ignored:b_000001" in result.report_payload["warnings"]


def test_run_reader_cleanup_does_not_infer_missing_confidence_for_heading_delete() -> None:
    markdown = "Intro\n\n# Chapter 1\n\nBody paragraph\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: json.dumps(
            {
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "page_furniture_heading",
                    }
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
        operation_provider=lambda payload, chunk_index, chunk_count: (
            '{"delete_blocks": ['
            f'{{"id": "{blocks[0].block_id}", "text_hash": "{blocks[0].text_hash}", "reason": "page_furniture_heading", "confidence": "medium"}},'
            f'{{"id": "{blocks[2].block_id}", "text_hash": "{blocks[2].text_hash}", "reason": "page_number", "confidence": "high"}}'
            '], "warnings": []}'
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "repeated_running_header",
                        "confidence": "high",
                    }
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "page_number",
                        "confidence": "high",
                    }
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "repeated_running_header",
                        "confidence": "high",
                    }
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "repeated_running_header",
                        "confidence": "high",
                    }
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
                "delete_blocks": [
                    {
                        "id": block["id"],
                        "text_hash": block["text_hash"],
                        "reason": "repeated_running_header",
                        "confidence": "high",
                    }
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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


def test_reader_cleanup_prompt_guides_heading_boundary_vs_split_choice() -> None:
    prompt = build_reader_cleanup_system_prompt()

    assert "If non-heading text remains before the heading candidate" in prompt
    assert "Part title after a preceding quote: use split_block, not normalize_heading_boundary" in prompt
    assert "body_substring must point to the full semantic body remainder after that heading" in prompt


def test_run_reader_cleanup_preserves_full_remainder_for_unique_heading_prefix_boundary() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти. Второе предложение тоже должно сохраниться."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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


def test_run_reader_cleanup_rejects_ambiguous_heading_boundary_heading_substring() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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


def test_run_reader_cleanup_applies_split_block_operation_from_exact_substrings() -> None:
    target = "СТРАТЕГИИ РАЗВИТИЯ Деньги — это рычаг власти."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
        "Главное различие между «гевро» и «сивиком» заключается в том, что «гевро» выпускается как долговое обязательство центрального правительства.\n\n"
        "162 ПРОЦВЕТАНИЕ ГРАЖДАНСКИЕ ИНИЦИАТИВЫ Через призму дополнительных валют можно увидеть новые возможности.\n\n"
        "Outro"
    )

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
        block = next(block for block in payload["blocks"] if str(block["text"]).startswith("162 ПРОЦВЕТАНИЕ"))
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
                        "expected_after_preview": "Через призму дополнительных валют можно увидеть новые возможности.",
                        "safety_note": "Only exact page furniture substring is removed; body remains.",
                        "noise_substring": "162 ПРОЦВЕТАНИЕ ГРАЖДАНСКИЕ ИНИЦИАТИВЫ ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert "162 ПРОЦВЕТАНИЕ ГРАЖДАНСКИЕ ИНИЦИАТИВЫ" not in result.cleaned_markdown
    assert "Через призму дополнительных валют" in result.cleaned_markdown


def test_run_reader_cleanup_removes_title_case_running_header_with_page_number_prefix() -> None:
    target = (
        "Стратегии для правительств 145 Ни одно из исключительных достижений Куритибы было бы невозможно без различных систем кооперативных валют."
    )
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "expected_after_preview": "Ни одно из исключительных достижений Куритибы было бы невозможно без различных систем кооперативных валют.",
                        "safety_note": "Only the short running-header prefix with trailing page number should be removed.",
                        "noise_substring": "Стратегии для правительств 145 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == (
        "Intro\n\nНи одно из исключительных достижений Куритибы было бы невозможно без различных систем кооперативных валют.\n\nOutro"
    )


def test_run_reader_cleanup_removes_title_case_running_header_in_middle_of_paragraph() -> None:
    target = "Япония Стратегии для НКО 167 обладает самым быстро стареющим населением в мире."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "expected_after_preview": "Япония обладает самым быстро стареющим населением в мире.",
                        "safety_note": "Remove only the short running-header residue inserted inside the sentence.",
                        "noise_substring": "Стратегии для НКО 167 ",
                    }
                ],
                "warnings": [],
            },
            ensure_ascii=False,
        )

    result = run_reader_cleanup(markdown_text=markdown, config=ReaderCleanupConfig(enabled=True), operation_provider=provider)

    assert result.changed is True
    assert result.cleaned_markdown == "Intro\n\nЯпония обладает самым быстро стареющим населением в мире.\n\nOutro"


def test_run_reader_cleanup_rejects_title_case_running_header_inside_longer_number() -> None:
    target = "Analysis of the United States 2024 report continued after the hearing."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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


def test_run_reader_cleanup_joins_fragmented_paragraph_after_caption_boundary() -> None:
    markdown = (
        "Intro\n\n"
        "Рисунок 4.1: локальная валюта поддерживает торговлю,\n\n"
        "и помогает соседям сохранять покупательную способность.\n\n"
        "Outro"
    )

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
    target = "150 ПРОЦВЕТАНИЕ Через призму дополнительных валют можно увидеть новые возможности."
    markdown = f"Intro\n\n{target}\n\nOutro"

    def provider(payload: dict[str, object], chunk_index: int, chunk_count: int) -> str:
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
                        "noise_substring": "150 ПРОЦВЕТАНИЕ ",
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
