import json
from pathlib import Path

import pytest

from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupConfig,
    ReaderCleanupStageError,
    build_cleanup_blocks,
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


def test_run_reader_cleanup_preserves_already_good_list_formatting_during_polish() -> None:
    markdown = "Intro\n\n- первый пункт\n\n- второй пункт\n\nOutro"

    result = run_reader_cleanup(
        markdown_text=markdown,
        config=ReaderCleanupConfig(enabled=True),
        operation_provider=lambda payload, chunk_index, chunk_count: '{"delete_blocks": [], "warnings": []}',
    )

    assert result.changed is False
    assert result.cleaned_markdown == markdown


def test_run_reader_cleanup_preserves_legitimate_plain_text_heading_like_paragraph() -> None:
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
    assert "reader_cleanup_polish_inline_page_furniture_stripped" not in result.report_payload["warnings"]


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
