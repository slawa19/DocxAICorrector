import json
import os
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

import docxaicorrector.core.model_accounting as model_accounting
import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.output_validation as document_pipeline_output_validation


class AssetStub:
    def __init__(self, image_id: str):
        self.image_id = image_id
        self.placeholder_status = None

    def update_pipeline_metadata(self, **values):
        self.placeholder_status = values.get("placeholder_status")


def _build_runtime_capture():
    return {"state": {}, "finalize": [], "log": [], "status": []}


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _emit_finalize(runtime, stage, detail, progress, terminal_kind=None):
    runtime.setdefault("finalize", []).append((stage, detail, progress, terminal_kind))


def _emit_log(runtime, **payload):
    runtime.setdefault("log", []).append(payload)


def _emit_status(runtime, **payload):
    runtime.setdefault("status", []).append(payload)


def _inspect_placeholder_integrity(markdown_text, image_assets):
    return {asset.image_id: "ok" for asset in image_assets}


def _convert_markdown_to_docx_bytes(markdown_text):
    return b"docx-bytes"


def _reinsert_inline_images(docx_bytes, image_assets):
    return docx_bytes


def test_run_document_processing_fails_on_empty_processed_block():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "   ",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"].endswith("empty_processed_block).")
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["finalize"][-1][3] == "error"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_rejects_heading_only_output_for_body_heavy_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "# Заголовок\n\nЭто полноценный абзац с несколькими словами и знаками препинания.",
            "context_before": "",
            "context_after": "",
            "target_chars": 71,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "# Heading only",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "heading_only_output" in runtime["state"]["last_error"]
    assert runtime["state"].get("latest_docx_bytes") is None
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["finalize"][-1][3] == "error"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_accepts_heading_only_output_for_legitimate_heading_only_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "# Heading only", "context_before": "", "context_after": "", "target_chars": 14, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        # Spec 059 A-I: a heading-only block whose answer is byte-identical to its own
        # source is now ``source_text_fallback``, so this fixture returns the translation it
        # always meant. The subject of the test is unchanged: heading-only OUTPUT is
        # legitimate when the INPUT is heading-only.
        generate_markdown_block=lambda **kwargs: "# Только заголовок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "# Только заголовок"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_uppercase_title_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "РАЗВИТИЕ МЕСТНОЙ ЭКОНОМИКИ С ПОМОЩЬЮ МЕСТНЫХ ВАЛЮТ",
            "context_before": "",
            "context_after": "",
            "target_chars": 50,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Развитие местной экономики с помощью местных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Развитие местной экономики с помощью местных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_table_of_contents_line():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Предисловие Денниса Мидоуза Предисловие Хантера Ловинса Благодарности",
            "context_before": "",
            "context_after": "",
            "target_chars": 69,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Предисловия и благодарности",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Предисловия и благодарности"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_accepts_heading_only_output_for_colon_section_title():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Часть II: Примеры дополнительных валют",
            "context_before": "",
            "context_after": "",
            "target_chars": 38,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Часть II: Примеры дополнительных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Часть II: Примеры дополнительных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"


def test_collect_false_fragment_heading_samples_detects_inline_heading_and_numbered_citation():
    markdown = (
        "Является ли\n\n"
        "## начертание зверя\n\n"
        "на самом деле - квантовая технология?\n\n"
        "## (Матфея 24:36)\n\n"
        "Христос вернётся как вор в ночи."
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert [sample.reason for sample in samples] == [
        "inline_term_heading_present",
        "numbered_citation_heading_present",
    ]
    assert [sample.line for sample in samples] == [3, 7]


def test_collect_false_fragment_heading_samples_preserves_legitimate_boundary_heading():
    markdown = "Введение\n\nТекст раздела.\n\n## Начертание зверя\n\nНовый раздел начинается здесь."

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert samples == []


def test_collect_false_fragment_heading_samples_preserves_toc_backed_section_heading_after_epigraph():
    markdown = (
        "Содержание\n\n"
        "Введение..................................4\n\n"
        "> «И будете ненавидимы всеми...» — Марка 13:13\n\n"
        "## Введение\n\n"
        "Мой дед был убеждён, что Иисус вернётся ещё при его жизни."
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert samples == []


def test_collect_false_fragment_heading_samples_preserves_repeated_boundary_heading_with_intervening_body():
    markdown = (
        "## Начертание зверя\n\n"
        "Первый раздел с полноценным телом текста и отдельным содержанием.\n\n"
        "Ещё один абзац, чтобы повтор был самостоятельной секцией.\n\n"
        "## Начертание зверя\n\n"
        "Второй самостоятельный раздел."
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert samples == []


def test_collect_false_fragment_heading_samples_preserves_repeated_boundary_heading_with_single_body_paragraph():
    markdown = (
        "## Начертание зверя\n\n"
        "Полноценный абзац между двумя секциями с одинаковым заголовком.\n\n"
        "## Начертание зверя\n\n"
        "Второй самостоятельный раздел."
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert samples == []


def test_collect_residual_bullet_glyph_samples_detects_inline_glyphs():
    markdown = "- Есть некий вулкан ... ● пятимесячная атака ...\n\nКитай ... технологическими ● достижениями?"

    samples = document_pipeline_output_validation.collect_residual_bullet_glyph_samples(markdown)

    assert [sample.line for sample in samples] == [1, 3]
    assert all(sample.reason == "residual_bullet_glyphs_present" for sample in samples)


def test_collect_list_fragment_regression_samples_detects_split_bullet_and_dangling_number():
    markdown = (
        "- Сторонники мидтрибулационного взгляда считают, что христиане будут восхищены в середине\n"
        "- Великой скорби.\n\n"
        "- Поразительно ... схеме: 1.\n"
        "2. Бог судит их за грех."
    )

    samples = document_pipeline_output_validation.collect_list_fragment_regression_samples(markdown)

    assert len(samples) == 2
    assert all(sample.reason == "list_fragment_regressions_present" for sample in samples)


def test_collect_list_fragment_regression_samples_detects_body_to_uppercase_bullet_continuation():
    markdown = "Это связано с Седьмой\n- Судной печатью № 1"

    samples = document_pipeline_output_validation.collect_list_fragment_regression_samples(markdown)

    assert len(samples) == 1
    assert samples[0].reason == "list_fragment_regressions_present"


def _paragraph_break_entry(
    *,
    source_index,
    text_preview,
    origin_raw_indexes=None,
    role="body",
    structural_role="toc_entry",
    heading_level=None,
    list_kind=None,
):
    entry = {
        "source_index": source_index,
        "text_preview": text_preview,
        "role": role,
        "structural_role": structural_role,
        "heading_level": heading_level,
        "list_kind": list_kind,
    }
    if origin_raw_indexes is not None:
        entry["origin_raw_indexes"] = origin_raw_indexes
    return entry


def test_collect_paragraph_break_samples_flags_shared_source_mid_sentence_split():
    # (a) A genuine split: two entries share one raw PDF block, the first ends mid-sentence
    # (no terminal punctuation) and the second resumes lowercase → flagged (FR-001).
    registry = [
        _paragraph_break_entry(
            source_index=219,
            origin_raw_indexes=[220],
            text_preview="this pattern has been observed for every one of the large-scale harbour floods and coastal",
        ),
        _paragraph_break_entry(
            source_index=219,
            origin_raw_indexes=[220],
            text_preview="storms of our times.",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert len(samples) == 1
    assert samples[0].source_index == 219
    assert samples[0].text.endswith("coastal")
    assert samples[0].next_text.startswith("storms")


def test_collect_paragraph_break_samples_ignores_boundary_without_shared_source_signal():
    # (b) Same mid-sentence form but the two entries are separate source paragraphs
    # (distinct raw blocks) → NOT flagged. No source signal, no flag (FR-002).
    registry = [
        _paragraph_break_entry(
            source_index=1381,
            origin_raw_indexes=[1431],
            text_preview="tobias marlow: the second taming of the coast (kelbrook",
        ),
        _paragraph_break_entry(
            source_index=1382,
            origin_raw_indexes=[1432],
            text_preview="ansel vardenson, peter kesvik",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert samples == []


def test_collect_paragraph_break_samples_ignores_heading_boundary():
    # (c) A heading→body boundary is structural, not a mid-sentence split → NOT flagged (FR-003).
    registry = [
        _paragraph_break_entry(
            source_index=220,
            origin_raw_indexes=[221],
            text_preview="identifying harbour hazards",
            role="heading",
            structural_role="heading",
            heading_level=2,
        ),
        _paragraph_break_entry(
            source_index=220,
            origin_raw_indexes=[221],
            text_preview="continuation body text after the heading",
            role="body",
            structural_role="body",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert samples == []


def test_collect_paragraph_break_samples_ignores_list_boundary():
    # (d) A list-item boundary is structural, not a mid-sentence split → NOT flagged (FR-003).
    registry = [
        _paragraph_break_entry(
            source_index=119,
            origin_raw_indexes=[119],
            text_preview="proposals for nine different practical harbour lanterns",
            role="list",
            structural_role="list",
            list_kind="unordered",
        ),
        _paragraph_break_entry(
            source_index=119,
            origin_raw_indexes=[119],
            text_preview="to the current coastal network",
            role="list",
            structural_role="list",
            list_kind="unordered",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert samples == []


def test_collect_paragraph_break_samples_treats_trailing_footnote_marker_as_non_terminal():
    # (e) The first fragment ends in a footnote-marker superscript ("…²"): still mid-sentence,
    # so the pair IS flagged (spec 008 edge case).
    registry = [
        _paragraph_break_entry(
            source_index=42,
            origin_raw_indexes=[42],
            text_preview="the argument continues past the marker here.²",
        ),
        _paragraph_break_entry(
            source_index=42,
            origin_raw_indexes=[42],
            text_preview="and finishes on the next line.",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert len(samples) == 1
    assert samples[0].source_index == 42


def test_collect_paragraph_break_samples_scopes_to_main_content_by_region():
    # FR-007: only a split whose FIRST entry sits in the main-content span
    # `[front_matter_boundary … references_region_start)` is flagged. A front-matter split
    # and a back-matter references-region split (same shared-source + mid-sentence form)
    # are excluded by REGION — the same provenance classify_heading_demotions applies, no
    # per-book literal. front_matter_boundary is anchored by the "Chapter 1 — …" body
    # heading; references_region_start by the bare "Notes" back-matter title.
    registry = [
        # Front matter (before the chapter-body heading): a bio split — NOT flagged.
        _paragraph_break_entry(source_index=1, origin_raw_indexes=[1], text_preview="the author is a founding member"),
        _paragraph_break_entry(source_index=1, origin_raw_indexes=[1], text_preview="of several learned societies"),
        # Body-start boundary anchor.
        _paragraph_break_entry(
            source_index=5,
            origin_raw_indexes=[5],
            text_preview="Chapter 1 — The Opening",
            role="heading",
            structural_role="heading",
            heading_level=1,
        ),
        # Main content: a genuine mid-sentence split — FLAGGED.
        _paragraph_break_entry(
            source_index=10,
            origin_raw_indexes=[10],
            text_preview="this clause runs straight into the following line without any",
        ),
        _paragraph_break_entry(
            source_index=10,
            origin_raw_indexes=[10],
            text_preview="terminal punctuation to close it.",
        ),
        # Back-matter references anchor.
        _paragraph_break_entry(source_index=50, origin_raw_indexes=[50], text_preview="Notes"),
        # References region: a split — NOT flagged (>= references_region_start).
        _paragraph_break_entry(
            source_index=55,
            origin_raw_indexes=[55],
            text_preview="a note that continues in the citation list running onto",
        ),
        _paragraph_break_entry(
            source_index=55,
            origin_raw_indexes=[55],
            text_preview="a second physical line of the note.",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert [sample.source_index for sample in samples] == [10]
    assert samples[0].text.endswith("without any")


def test_collect_paragraph_break_samples_excludes_bounded_toc_region():
    # FR-007: a split whose FIRST entry sits inside the bounded TOC region is NOT flagged,
    # while a split outside it is. The TOC region is resolved from the preparation snapshot
    # (bounded_toc_region_count + a "Contents" heading + toc_entry_count) — the SAME
    # provenance classify_heading_demotions uses. first_block_has_body_start=True disables
    # the front-matter boundary so this test isolates the TOC-region path.
    snapshot = {
        "first_block_has_body_start": True,
        "bounded_toc_region_count": 1,
        "toc_entry_count": 3,
        "toc_header_count": 1,
    }
    registry = [
        _paragraph_break_entry(
            source_index=10,
            origin_raw_indexes=[10],
            text_preview="Contents",
            role="heading",
            structural_role="heading",
            heading_level=1,
        ),
        # Inside the bounded TOC region (10 .. 14) — NOT flagged.
        _paragraph_break_entry(source_index=12, origin_raw_indexes=[12], text_preview="a table-of-contents row running onto"),
        _paragraph_break_entry(source_index=12, origin_raw_indexes=[12], text_preview="a wrapped second line here."),
        # Outside the TOC region — FLAGGED (control).
        _paragraph_break_entry(source_index=30, origin_raw_indexes=[30], text_preview="this body sentence spills over onto"),
        _paragraph_break_entry(source_index=30, origin_raw_indexes=[30], text_preview="the following physical line."),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry, snapshot)

    assert [sample.source_index for sample in samples] == [30]


def test_collect_false_fragment_heading_samples_detects_dangling_question_fragment_heading():
    markdown = "Это обсуждение подводит к вопросу\n\n## Спутники? Ракеты?)\n\nкоторый дальше раскрывается в тексте."

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert len(samples) == 1
    assert samples[0].reason == "sentence_split_heading_present"


def test_collect_false_fragment_heading_samples_preserves_heading_after_parenthetical_terminal_sentence():
    markdown = (
        "Крайне спекулятивно — появление звероподобного Антихриста. (Нарождающийся AGI?)\n\n"
        "## Суд над второй печатью (Откровение 6:4):\n\n"
        "Крушение мира и правопорядка."
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert samples == []


def test_normalize_false_fragment_headings_markdown_demotes_deterministic_false_headings():
    markdown = (
        "Христос предупреждает нас\n\n"
        "## (Матфея 24:36)\n\n"
        "что день неизвестен.\n\n"
        "Это обсуждение подводит к вопросу\n\n"
        "## Спутники? Ракеты?)\n\n"
        "который дальше раскрывается в тексте."
    )

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(markdown)

    assert "## (Матфея 24:36)" not in normalized
    assert "## Спутники? Ракеты?)" not in normalized
    assert "(Матфея 24:36)" in normalized
    assert "Спутники? Ракеты?)" in normalized


def test_normalize_false_fragment_headings_markdown_merges_inline_heading_fragment_into_sentence():
    markdown = (
        "Иисус постоянно говорит о том, как важно распознавать знамения, чтобы, если им будет даровано пережить\n\n"
        "## Великую скорбь\n\n"
        "они могли устоять до конца."
    )

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(markdown)

    assert "## Великую скорбь" not in normalized
    assert "пережить Великую скорбь они могли устоять до конца." in normalized


def test_normalize_false_fragment_headings_markdown_preserves_title_like_heading_before_blockquote_continuation():
    markdown = (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано претерпеть\n\n"
        "## Великая скорбь\n\n"
        "> они могли бы с уверенностью устоять до конца."
    )

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(markdown)

    assert "## Великая скорбь" in normalized
    assert "> они могли бы с уверенностью устоять до конца." in normalized


def test_normalize_false_fragment_headings_markdown_preserves_toc_backed_heading_after_epigraph():
    markdown = (
        "Содержание\n\n"
        "Введение..................................4\n\n"
        "> «И будете ненавидимы всеми...» — Марка 13:13\n\n"
        "## Введение\n\n"
        "Основной текст раздела."
    )

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(markdown)

    assert "## Введение" in normalized


def test_normalize_false_fragment_headings_markdown_merges_split_heading_lines():
    markdown = "### О марке\n\n### зверя\n\n/антихристовой сущности"

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(markdown)

    assert "### зверя" not in normalized
    assert "### О марке зверя" in normalized


# Money live defect: a footnote/reference tail with no sentence-terminal punctuation
# followed by three source-backed chapter headings. See
# specs/001-heading-role-preservation/spec.md.
_MONEY_HEADING_DEFECT_MARKDOWN = (
    "См. полный отчёт см. www.example.org/report\n\n"
    "# Глава IV\n\n"
    "## Объяснение нестабильности:\n\n"
    "## Физика сложных потоковых сетей"
)


def _registry_protected_heading_texts(heading_markdown_lines):
    registry = [{"text": line} for line in heading_markdown_lines]
    return {normalized for normalized, _ in late_phases._registry_heading_markdown_lines(registry)}


def test_normalize_false_fragment_headings_markdown_preserves_registry_protected_headings():
    protected = _registry_protected_heading_texts(
        ["# Глава IV", "## Объяснение нестабильности:", "## Физика сложных потоковых сетей"]
    )

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(
        _MONEY_HEADING_DEFECT_MARKDOWN, protected_heading_texts=protected
    )

    assert "# Глава IV" in normalized
    assert "## Объяснение нестабильности:" in normalized
    assert "## Физика сложных потоковых сетей" in normalized


def test_normalize_false_fragment_headings_markdown_demotes_registry_headings_without_protected_set():
    # Anti-regression counter-test (FR-004 + FR-005): with no protected set the
    # source-blind cleanup must still demote/merge these lines, proving the guard
    # does not silently disable the false-fragment cleanup.
    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(
        _MONEY_HEADING_DEFECT_MARKDOWN
    )

    assert "# Глава IV" not in normalized
    assert "## Объяснение нестабильности:" not in normalized
    assert "## Физика сложных потоковых сетей" not in normalized


def test_normalize_false_fragment_headings_markdown_still_demotes_unprotected_heading_beside_protected():
    # The load-bearing anti-regression case (FR-005): a protected set EXISTS and a
    # heading absent from it must still be demoted. Production always supplies a
    # protected set, so "no protected set" alone never proves the cleanup survived.
    markdown = (
        "См. полный отчёт см. www.example.org/report\n\n"
        "# Глава IV\n\n"
        "Начинается основной текст главы, и он завершается точкой.\n\n"
        "продолжение фразы без точки\n\n"
        "## и далее\n\n"
        "хвост"
    )
    protected = _registry_protected_heading_texts(["# Глава IV"])

    normalized = document_pipeline_output_validation.normalize_false_fragment_headings_markdown(
        markdown, protected_heading_texts=protected
    )

    assert "# Глава IV" in normalized
    assert "## и далее" not in normalized


def test_normalize_list_fragment_regressions_markdown_keeps_protected_heading_out_of_the_list():
    # Money live defect, second path: a numbered footnote entry whose text ends in the
    # next ordinal ("… 24.") steals the following chapter heading, turning "# Глава IV"
    # into list item "24. Глава IV". da6789b guarded the entry-level twin of this pass;
    # the markdown-level pass that builds the delivered DOCX was left unguarded.
    markdown = (
        "23. (*http://kelbrookharbourwarden.org*). 42* www.tidegazette.com 24.\n\n"
        "# Глава IV\n\n"
        "## Объяснение нестабильности:"
    )
    protected = _registry_protected_heading_texts(["# Глава IV", "## Объяснение нестабильности:"])

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(
        markdown, protected_heading_texts=protected
    )

    assert "# Глава IV" in normalized
    assert "24. Глава IV" not in normalized


def test_normalize_list_fragment_regressions_markdown_still_repairs_unprotected_carry_over():
    # Anti-regression: with the follower absent from the protected set, the carry-over
    # repair this pass exists for must still fire.
    markdown = "3. первый пункт списка 4.\n\nвторой пункт списка"

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(
        markdown, protected_heading_texts={"глава iv"}
    )

    assert "4. второй пункт списка" in normalized


def test_normalize_inline_fragment_paragraphs_markdown_merges_standalone_term_fragments():
    markdown = (
        "Люди, принявшие\n\n"
        "печать зверя,\n\n"
        "получат мучительные язвы.\n\n"
        "Мы сможем отказаться от\n\n"
        "ближневосточной нефти и газа.\n\n"
        "## Следующий раздел"
    )

    normalized = document_pipeline_output_validation.normalize_inline_fragment_paragraphs_markdown(markdown)

    assert "Люди, принявшие печать зверя, получат мучительные язвы." in normalized
    assert "Мы сможем отказаться от ближневосточной нефти и газа." in normalized
    assert "## Следующий раздел" in normalized


def test_normalize_inline_fragment_paragraphs_markdown_preserves_year_boundary_label():
    markdown = (
        "Людей исключают из мировой экономики, если они не получат начертание зверя.\n\n"
        "Год 5 (примерно между 2030 и 2038)\n\n"
        "Те, кто получил\n\n"
        "начертание зверя\n\n"
        "получат мучительные язвы."
    )

    normalized = document_pipeline_output_validation.normalize_inline_fragment_paragraphs_markdown(markdown)

    assert "начертание зверя получат мучительные язвы." in normalized
    assert "начертание зверя. Год 5" not in normalized
    assert "\n\nГод 5 (примерно между 2030 и 2038)\n\n" in normalized


def test_normalize_inline_fragment_paragraphs_markdown_preserves_structural_phase_label():
    markdown = (
        "Родовые муки становятся всё более мучительными.\n\n"
        "3/3.) Семь судов чаши\n\n"
        "Суд над чашей #1"
    )

    normalized = document_pipeline_output_validation.normalize_inline_fragment_paragraphs_markdown(markdown)

    assert "Родовые муки становятся всё более мучительными. 3/3.)" not in normalized
    assert "\n\n3/3.) Семь судов чаши\n\nСуд над чашей #1" in normalized


def test_normalize_page_placeholder_heading_concats_markdown_splits_placeholder_from_chapter_heading():
    markdown = "This page intentionally left blank Chapter Nine METHODS FOR PORT S"

    normalized = document_pipeline_output_validation.normalize_page_placeholder_heading_concats_markdown(markdown)

    assert normalized == "This page intentionally left blank\n\nChapter Nine METHODS FOR PORT S"


def test_normalize_residual_bullet_glyphs_markdown_rewrites_inline_and_leading_glyphs():
    markdown = (
        "Посттрибулационисты считают, что Иисус придёт в конце ● скорби.\n"
        "● собирают армию в 200 миллионов солдат.\n"
        "- Соединённые Штаты формируют мировую ● культуру и политику?"
    )

    normalized = document_pipeline_output_validation.normalize_residual_bullet_glyphs_markdown(markdown)

    assert "●" not in normalized
    assert "в конце скорби." in normalized
    assert "- собирают армию в 200 миллионов солдат." in normalized
    assert "мировую культуру" in normalized


def test_normalize_residual_bullet_glyphs_markdown_preserves_glyph_welded_in_word():
    markdown = "Сноска 4●5 и таблица 12•34, а также a◦b."

    normalized = document_pipeline_output_validation.normalize_residual_bullet_glyphs_markdown(markdown)

    assert normalized == markdown


def test_normalize_residual_bullet_glyphs_markdown_preserves_leading_bullet_and_separator():
    markdown = "● Первый пункт\nтекст; ● пункт"

    normalized = document_pipeline_output_validation.normalize_residual_bullet_glyphs_markdown(markdown)

    assert "- Первый пункт" in normalized
    assert "текст; пункт" in normalized
    assert "●" not in normalized


def test_normalize_residual_bullet_glyphs_markdown_does_not_invent_list_item_from_lone_glyph():
    markdown = "● "

    normalized = document_pipeline_output_validation.normalize_residual_bullet_glyphs_markdown(markdown)

    assert normalized.strip() != "-"


def test_collect_residual_bullet_glyph_samples_ignores_glyph_welded_in_word():
    markdown = "Сноска 4●5 и таблица 12•34, а также a◦b."

    samples = document_pipeline_output_validation.collect_residual_bullet_glyph_samples(markdown)

    assert samples == []


def test_normalize_list_fragment_regressions_markdown_repairs_intro_and_carryover_markers():
    markdown = (
        "Поразительно, но все петли следуют одной и той же схеме: 1.\n"
        "Духовные существа восстают против Бога.\n"
        "2. Бог судит их за грех.\n"
        "3. Бог спасает остаток верных."
    )

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert "схеме: 1." not in normalized
    assert "схеме:" in normalized
    assert "1. Духовные существа восстают против Бога." in normalized
    assert "2. Бог судит их за грех." in normalized
    assert "3. Бог спасает остаток верных." in normalized


def test_normalize_list_fragment_regressions_markdown_repairs_trailing_next_item_and_heading_target():
    markdown = (
        "5. Держитесь подальше от зла. Таковых удаляйся». 6.\n\n"
        "## Предпримите быстрые шаги, чтобы подготовиться к изоляции:"
    )

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert "Таковых удаляйся». 6." not in normalized
    assert "5. Держитесь подальше от зла. Таковых удаляйся»." in normalized
    assert "6. Предпримите быстрые шаги, чтобы подготовиться к изоляции:" in normalized


def test_normalize_list_fragment_regressions_markdown_preserves_emoji_marker_line_as_body():
    markdown = "Представьте, если этим лидером окажется Дональд Трамп.\n\n😂 2.\n\nВ первой половине"

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert "1. 😂" not in normalized
    assert "\n😂\n" in normalized
    assert "2. В первой половине" in normalized


def test_normalize_list_fragment_regressions_markdown_keeps_prose_ending_in_a_number_intact():
    # 2026-08-03 literary-edit live run, p0106: a body paragraph that merely ENDS in a
    # number was rewritten into list item "64. …" and its own last token "65." was moved
    # into the NEXT paragraph, cutting a sentence in half mid-phrase.
    markdown = (
        "Бывший смотритель, он гребёт здесь уже 18 лет — с тех пор как вышел на пенсию в 65.\n\n"
        "Он тихий человек и говорит, что сел на эти вёсла по просьбе дочери."
    )

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert normalized == markdown
    assert "вышел на пенсию в 65." in normalized
    assert "64. Бывший смотритель" not in normalized
    assert "65. Он тихий человек" not in normalized


def test_normalize_list_fragment_regressions_markdown_keeps_index_entry_ending_in_a_page_number():
    # Same defect in the back-of-book index (p1715 region): the trailing page number is
    # part of the entry, not the ordinal of the next one.
    markdown = (
        "Tidebank, 84–85; ПКО, 162; Марровер (Marrower), 63–64, 91–93, 92.\n\n"
        "Puerto Lanterna, 103–108; мореплавание, 20; отлив (приливный), 51–52."
    )

    normalized = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert normalized == markdown


def test_collect_mixed_script_samples_detects_cyrillic_latin_tokens():
    markdown = "Создавайте кoinonia-сообщества\n\nПрежде чем суперразумa догонит."

    samples = document_pipeline_output_validation.collect_mixed_script_samples(markdown)

    assert len(samples) >= 2
    assert all(sample.reason == "mixed_script_term_present" for sample in samples)
    assert any("oinonia" in sample.text for sample in samples)
    assert any("суперразум" in sample.text for sample in samples)


def test_normalize_mixed_script_markdown_repairs_homoglyphs():
    markdown = "Создавайте общины кoinonia, чтобы поддерживать друг друга.\n\n"
    markdown += "Прежде чем мы суперразумa догонит квантовый скачок."

    normalized = document_pipeline_output_validation.normalize_mixed_script_markdown(markdown)

    assert "кoinonia" not in normalized
    assert "суперразумa" not in normalized
    assert "суперразума" in normalized


def test_normalize_mixed_script_markdown_preserves_legitimate_latin_text():
    markdown = "BMW AG и OpenAI запустили проект."

    normalized = document_pipeline_output_validation.normalize_mixed_script_markdown(markdown)

    assert normalized == markdown


def test_normalize_mixed_script_markdown_preserves_code_span_fence_and_url_tokens():
    markdown = (
        "Смотри `cоd` в примере.\n"
        "```\n"
        "cоd fenced\n"
        "```\n"
        "Ссылка example.cом здесь."
    )

    normalized = document_pipeline_output_validation.normalize_mixed_script_markdown(markdown)

    assert "`cоd`" in normalized
    assert "cоd fenced" in normalized
    assert "example.cом" in normalized


def test_normalize_mixed_script_markdown_repairs_prose_homoglyph_word():
    markdown = "Cовет мудреца."

    normalized = document_pipeline_output_validation.normalize_mixed_script_markdown(markdown)

    assert normalized == "Совет мудреца."


def test_collect_mixed_script_samples_ignores_code_span_fence_and_url_tokens():
    markdown = (
        "Смотри `cоd` в примере.\n"
        "```\n"
        "cоd fenced\n"
        "```\n"
        "Ссылка example.cом здесь."
    )

    samples = document_pipeline_output_validation.collect_mixed_script_samples(markdown)

    assert samples == []


def _make_paragraph_stub(
    paragraph_id: str,
    source_index: int,
    *,
    role: str = "body",
    structural_role: str = "body",
    heading_level=None,
    list_kind=None,
    text: str = "",
):
    class ParagraphStub:
        def __init__(self):
            self.paragraph_id = paragraph_id
            self.source_index = source_index
            self.role = role
            self.structural_role = structural_role
            self.heading_level = heading_level
            self.list_kind = list_kind
            self.boundary_source = "raw"
            self.boundary_confidence = "explicit"
            # ParagraphUnit.text -- the FULL source paragraph. Empty means "source
            # unknown" for spec 057, which is how the older tests below read.
            self.text = text

    return ParagraphStub()


def test_assemble_final_markdown_preserves_partial_registry_uncovered_spans():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Первый абзац исходного блока.\n\nВторой абзац исходного блока.",
            "Passthrough блок без registry.\n\nСохранить как есть.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "p1", "text": "Первый абзац исходного блока."},
            {"block_index": 1, "paragraph_id": "p2", "text": "Второй абзац исходного блока."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("p1", 0),
            _make_paragraph_stub("p2", 1),
        ],
    )

    assert result.final_markdown == (
        "Первый абзац исходного блока.\n\nВторой абзац исходного блока.\n\n"
        "Passthrough блок без registry.\n\nСохранить как есть."
    )
    assert result.diagnostics.registry_covered_paragraphs == 2
    assert result.diagnostics.fallback_paragraphs == 2
    assert result.entries[0].paragraph_id == "p1"
    assert result.entries[0].source_index == 0
    assert result.entries[2].used_fallback is True
    assert result.entries[2].text == "Passthrough блок без registry."


def test_assemble_final_markdown_falls_back_for_inconsistent_registry_span():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Первый абзац.\n\nВторой абзац."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "p1", "text": "Первый абзац."},
        ],
        source_paragraphs=[_make_paragraph_stub("p1", 0)],
    )

    assert result.final_markdown == "Первый абзац.\n\nВторой абзац."
    assert result.diagnostics.inconsistent_registry_blocks == (1,)
    assert result.diagnostics.fallback_paragraphs == 2
    assert all(entry.used_fallback for entry in result.entries)


def test_assemble_final_markdown_preserves_toc_backed_heading_boundary():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["## Введение\n\nОсновной текст раздела."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "toc-heading", "text": "## Введение"},
            {"block_index": 1, "paragraph_id": "body-1", "text": "Основной текст раздела."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("toc-heading", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("body-1", 1),
        ],
    )

    assert result.final_markdown == "## Введение\n\nОсновной текст раздела."
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.protected_boundary_denials >= 1


def test_assemble_final_markdown_preserves_blockquote_boundary_after_heading():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["## Великая скорбь\n\n> они могли бы с уверенностью устоять до конца."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "heading-1", "text": "## Великая скорбь"},
            {"block_index": 1, "paragraph_id": "quote-1", "text": "> они могли бы с уверенностью устоять до конца."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("heading-1", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("quote-1", 1),
        ],
    )

    assert result.final_markdown == "## Великая скорбь\n\n> они могли бы с уверенностью устоять до конца."
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.protected_boundary_denials >= 1


def test_assemble_final_markdown_merges_adjacent_registry_fragments_for_body_only_span():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь"],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "body-right", "text": "Великую скорбь"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-left", 0),
            _make_paragraph_stub("body-right", 1),
        ],
    )

    assert result.final_markdown == (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить Великую скорбь"
    )
    assert result.diagnostics.accepted_merges == 1
    assert len(result.entries) == 1


def test_assemble_final_markdown_refuses_merge_when_source_left_paragraph_ends_in_terminal_punctuation():
    # Spec 057: the same translation pair the test above merges, but the SOURCE left
    # paragraph closes a sentence -- the boundary belongs to the input document.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь"],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "body-right", "text": "Великую скорбь"},
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                "body-left",
                0,
                text="It is vital for Christians to remember the signs.",
            ),
            _make_paragraph_stub("body-right", 1, text="The Great Tribulation"),
        ],
    )

    assert result.final_markdown == (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь"
    )
    assert len(result.entries) == 2
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1
    # The refusal has its own counter and is NOT folded into denied_merges.
    assert result.diagnostics.denied_merges == 0
    assert result.entries[0].source_ends_sentence is True
    denials = [
        decision
        for decision in result.diagnostics.merge_decisions
        if decision.reason == "source_boundary_terminal_punctuation"
    ]
    assert [decision.paragraph_ids for decision in denials] == [("body-left", "body-right")]
    assert denials[0].action == "deny_merge"


def test_assemble_final_markdown_merges_when_source_left_paragraph_has_no_terminal_punctuation():
    # Spec 057: the honest repair -- the source paragraph really was torn mid-sentence,
    # so the pre-existing merge must survive the new refusal untouched.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь"],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "body-right", "text": "Великую скорбь"},
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                "body-left",
                0,
                text="It is vital for Christians to remember the signs, so that if they are granted to live through",
            ),
            _make_paragraph_stub("body-right", 1, text="the Great Tribulation"),
        ],
    )

    assert result.final_markdown == (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить Великую скорбь"
    )
    assert len(result.entries) == 1
    assert result.diagnostics.accepted_merges == 1
    assert result.diagnostics.source_terminal_denials == 0


def test_assemble_final_markdown_keeps_merge_when_source_paragraph_is_unknown():
    # Spec 057 / Constitution VII: a missing signal must not quietly become a new rule.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь"],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "body-right", "text": "Великую скорбь"},
        ],
        source_paragraphs=None,
    )

    assert result.final_markdown == (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить Великую скорбь"
    )
    assert result.diagnostics.accepted_merges == 1
    assert result.diagnostics.source_terminal_denials == 0
    assert result.entries[0].source_ends_sentence is None


def test_assemble_final_markdown_refuses_second_link_of_chain_on_merged_right_source_signal():
    # Spec 057: the merged entry now ENDS where the RIGHT one ended, so the chain's second
    # link must be judged by the SECOND source paragraph, not by the first.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Член Ордена фонарей, президент Северного отделения Ордена фонарей\n\nТобиас МАРЛОУ\n\nУле ШТРАНД"
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "sign-1",
                "text": "Член Ордена фонарей, президент Северного отделения Ордена фонарей",
            },
            {"block_index": 1, "paragraph_id": "sign-2", "text": "Тобиас МАРЛОУ"},
            {"block_index": 1, "paragraph_id": "sign-3", "text": "Уле ШТРАНД"},
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                "sign-1",
                0,
                text="Member of the Order of Lamps, President of the North Chapter of the Order of Lamps",
            ),
            _make_paragraph_stub("sign-2", 1, text="Tobias MARLOW."),
            _make_paragraph_stub("sign-3", 2, text="Ole ŠTRAND"),
        ],
    )

    assert result.final_markdown == (
        "Член Ордена фонарей, президент Северного отделения Ордена фонарей Тобиас МАРЛОУ\n\nУле ШТРАНД"
    )
    assert result.diagnostics.accepted_merges == 1
    assert result.diagnostics.source_terminal_denials == 1
    assert [entry.merged_paragraph_ids for entry in result.entries] == [("sign-1", "sign-2"), ("sign-3",)]
    # The merged entry carries the RIGHT source's signal, which is what denied link two.
    assert result.entries[0].source_ends_sentence is True


def test_assemble_final_markdown_refuses_merge_when_source_terminal_mark_is_behind_a_closing_quote():
    # Spec 057: hanging closing quotes/brackets are trimmed before the last character is
    # read, so a sentence that ends inside a quotation still counts as terminal.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Только ветер ответил ему, «совсем ничего»\n\nи больше никто"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "quote-left", "text": "Только ветер ответил ему, «совсем ничего»"},
            {"block_index": 1, "paragraph_id": "quote-right", "text": "и больше никто"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("quote-left", 0, text="Only the wind answered him, “nothing at all.” "),
            _make_paragraph_stub("quote-right", 1, text="and nobody else"),
        ],
    )

    assert result.final_markdown == "Только ветер ответил ему, «совсем ничего»\n\nи больше никто"
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1


def test_assemble_final_markdown_refuses_merge_when_source_terminal_mark_is_wrapped_in_emphasis_markers():
    # ANTI-NO-OP (spec 057). The importer bakes emphasis into ParagraphUnit.text
    # (document/extraction.py:1383-1387), so the real subheading arrives as
    # "**Why this Ledger, Now?**" -- its LAST character is "*", not "?". Reading the raw
    # last character refuses 0 of the 80 measured merges; this test fails on any
    # implementation that does not unwrap the importer's own markup first.
    # Real pair from the run: docx#205 = p0212+p0213, a chapter subheading welded to its
    # epigraph.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "**Почему этот реестр выходит именно сейчас?**\n\n«Фонарь горит для всех, кого мне не достичь.»"
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "p0212",
                "text": "**Почему этот реестр выходит именно сейчас?**",
            },
            {"block_index": 1, "paragraph_id": "p0213", "text": "«Фонарь горит для всех, кого мне не достичь.»"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("p0212", 0, text="**Why this Ledger, Now?**"),
            _make_paragraph_stub("p0213", 1, text="“My lamp burns for all that I cannot reach.”"),
        ],
    )

    assert result.final_markdown == (
        "**Почему этот реестр выходит именно сейчас?**\n\n«Фонарь горит для всех, кого мне не достичь.»"
    )
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1
    assert result.entries[0].source_ends_sentence is True


def test_assemble_final_markdown_refuses_merge_when_source_tail_is_quote_then_emphasis_marker():
    # Spec 057: the ".”*" tail measured on the run -- the emphasis marker must come off
    # before the closing quote, which is why the unwrap runs to a fixed point.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "*хорошие гавани и хорошие дальние прогнозы.”*\n\nи ничего сверх того"
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "emph-left",
                "text": "*хорошие гавани и хорошие дальние прогнозы.”*",
            },
            {"block_index": 1, "paragraph_id": "emph-right", "text": "и ничего сверх того"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("emph-left", 0, text="*good harbours and good long-range forecasts.”*"),
            _make_paragraph_stub("emph-right", 1, text="and nothing beyond that"),
        ],
    )

    assert result.final_markdown == (
        "*хорошие гавани и хорошие дальние прогнозы.”*\n\nи ничего сверх того"
    )
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1


def test_assemble_final_markdown_source_terminal_refusal_does_not_deny_every_merge_in_one_run():
    # ANTI-VACUUM (Constitution VII): one assembly, both counters non-zero. A rule that
    # refuses everything is not a fix.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\n"
            "Великую скорбь.\n\n"
            "Член Ордена фонарей, президент Северного отделения Ордена фонарей\n\n"
            "Тобиас МАРЛОУ"
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "torn-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "torn-right", "text": "Великую скорбь."},
            {
                "block_index": 1,
                "paragraph_id": "sign-1",
                "text": "Член Ордена фонарей, президент Северного отделения Ордена фонарей",
            },
            {"block_index": 1, "paragraph_id": "sign-2", "text": "Тобиас МАРЛОУ"},
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                "torn-left",
                0,
                text="It is vital for Christians to remember the signs, so that if they are granted to live through",
            ),
            _make_paragraph_stub("torn-right", 1, text="the Great Tribulation."),
            _make_paragraph_stub(
                "sign-1",
                2,
                text="Member of the Order of Lamps, President of the North Chapter of the Order of Lamps.",
            ),
            _make_paragraph_stub("sign-2", 3, text="Tobias MARLOW"),
        ],
    )

    assert result.diagnostics.accepted_merges == 1
    assert result.diagnostics.source_terminal_denials == 1
    assert result.final_markdown == (
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить Великую скорбь.\n\n"
        "Член Ордена фонарей, президент Северного отделения Ордена фонарей\n\n"
        "Тобиас МАРЛОУ"
    )


def test_assemble_final_markdown_refuses_merge_when_source_tail_is_a_closing_inline_tag():
    # Spec 057, gap found by independent review: the importer also emits <u>/<sup>/<sub>
    # (document/extraction.py:1388-1393) and NO test covered them -- deleting the inline-tag
    # branch left all eight earlier tests green.
    #
    # The shape here is the one the branch can actually handle: the importer wraps a WHOLE
    # run, so the closing tag sits directly behind the full stop. A trailing footnote marker
    # (`unabated.<sup>28</sup>`) is deliberately NOT handled -- the `28` is text, not markup,
    # and peeling it off would be removing content to manufacture a signal. On the measured
    # book the question is moot: zero of 1383 source paragraphs carry an inline tag at all,
    # because the PDF bridge does not set the run properties that produce them.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["<u>Ресурсы истощаются.</u>\n\nи это продолжается"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "tag-left", "text": "<u>Ресурсы истощаются.</u>"},
            {"block_index": 1, "paragraph_id": "tag-right", "text": "и это продолжается"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("tag-left", 0, text="<u>Resource depletion continues unabated.</u>"),
            _make_paragraph_stub("tag-right", 1, text="and it goes on"),
        ],
    )

    assert result.final_markdown == "<u>Ресурсы истощаются.</u>\n\nи это продолжается"
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1


def test_assemble_final_markdown_refuses_merge_when_source_role_is_image_placeholder():
    # Spec 058: the flagship shape, 35 of the 40 measured pairs -- a figure caption welded
    # onto the image placeholder. `[[DOCX_IMAGE_...]]` has no terminal punctuation, so the
    # translation-shape predicate calls it unfinished; the SOURCE calls it an image.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["[[DOCX_IMAGE_img_036]]\n\nрисунок 28. прибыльность нефинансового сектора"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "img-1", "text": "[[DOCX_IMAGE_img_036]]"},
            {"block_index": 1, "paragraph_id": "cap-1", "text": "рисунок 28. прибыльность нефинансового сектора"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("img-1", 0, role="image", structural_role="image", text="[[DOCX_IMAGE_img_036]]"),
            _make_paragraph_stub(
                "cap-1",
                1,
                role="caption",
                structural_role="caption",
                text="**Figure 28.** Non-financial sector public company profitability",
            ),
        ],
    )

    assert result.final_markdown == (
        "[[DOCX_IMAGE_img_036]]\n\nрисунок 28. прибыльность нефинансового сектора"
    )
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_role_denials == 1
    assert result.diagnostics.source_terminal_denials == 0
    denials = [
        decision
        for decision in result.diagnostics.merge_decisions
        if decision.reason == "source_boundary_unit_role"
    ]
    assert [decision.paragraph_ids for decision in denials] == [("img-1", "cap-1")]


def test_assemble_final_markdown_refuses_merge_when_the_image_is_the_right_half():
    # Spec 058: the other direction, measured twice -- prose introducing a figure with a
    # colon, and the placeholder welded onto it. The colon means spec 057 does NOT catch
    # this one, so it is the role and only the role that saves the boundary.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["карта этого перехода выглядела бы так:\n\n[[DOCX_IMAGE_img_015]]"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "body-1", "text": "карта этого перехода выглядела бы так:"},
            {"block_index": 1, "paragraph_id": "img-2", "text": "[[DOCX_IMAGE_img_015]]"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-1", 0, text="A harbour chart of this crossing would be as follows:"),
            _make_paragraph_stub("img-2", 1, role="image", structural_role="image", text="[[DOCX_IMAGE_img_015]]"),
        ],
    )

    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_role_denials == 1
    assert result.diagnostics.source_terminal_denials == 0


def test_assemble_final_markdown_source_role_refusal_survives_false_fragment_heading_bypass():
    # Spec 058, the reason the refusal is NOT in _entry_is_protected_boundary: that gate is
    # bypassed unconditionally for a false_fragment_heading
    # (_entries_match_allowed_protected_merge), so a demoted caption would walk straight
    # through it. Here the caption arrives as a markdown heading, which is what triggers
    # the demotion.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["[[DOCX_IMAGE_img_040]]\n\n### рисунок 31. совокупная доходность"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "img-3", "text": "[[DOCX_IMAGE_img_040]]"},
            {"block_index": 1, "paragraph_id": "cap-3", "text": "### рисунок 31. совокупная доходность"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("img-3", 0, role="image", structural_role="image", text="[[DOCX_IMAGE_img_040]]"),
            _make_paragraph_stub(
                "cap-3",
                1,
                role="caption",
                structural_role="caption",
                text="**Figure 31.** Cumulative returns for innovation",
            ),
        ],
    )

    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_role_denials == 1


def test_assemble_final_markdown_source_role_refusal_does_not_deny_every_merge_in_one_run():
    # ANTI-VACUUM: one assembly, a caption boundary refused AND an honest body repair kept.
    # 351 of the 391 measured pairs are body+body and must not move.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "[[DOCX_IMAGE_img_050]]\n\nрисунок 9. схема\n\n"
            "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\n"
            "Великую скорбь"
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "img-9", "text": "[[DOCX_IMAGE_img_050]]"},
            {"block_index": 1, "paragraph_id": "cap-9", "text": "рисунок 9. схема"},
            {
                "block_index": 1,
                "paragraph_id": "torn-left",
                "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "torn-right", "text": "Великую скорбь"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("img-9", 0, role="image", structural_role="image", text="[[DOCX_IMAGE_img_050]]"),
            _make_paragraph_stub("cap-9", 1, role="caption", structural_role="caption", text="**Figure 9.** A diagram"),
            _make_paragraph_stub(
                "torn-left",
                2,
                text="It is vital for Christians to remember the signs, so that if they are granted to live through",
            ),
            _make_paragraph_stub("torn-right", 3, text="the Great Tribulation"),
        ],
    )

    # TWO refusals, not one, and the second is the point: the caption is also stopped from
    # swallowing the body paragraph that follows it. Verified by running it -- without the
    # guard that pair merges, because "Для" matches the continuation-start pattern.
    assert result.diagnostics.source_role_denials == 2
    assert result.diagnostics.accepted_merges == 1
    assert result.final_markdown == (
        "[[DOCX_IMAGE_img_050]]\n\nрисунок 9. схема\n\n"
        "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить Великую скорбь"
    )


def test_assemble_final_markdown_source_role_refusal_reads_structural_role_alone():
    # Spec 058: role and structural_role are filled from two different ParagraphUnit fields
    # and either can carry the signal by itself.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["[[DOCX_IMAGE_img_060]]\n\nподпись к рисунку"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "img-6", "text": "[[DOCX_IMAGE_img_060]]"},
            {"block_index": 1, "paragraph_id": "cap-6", "text": "подпись к рисунку"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("img-6", 0, role="body", structural_role="image", text="[[DOCX_IMAGE_img_060]]"),
            _make_paragraph_stub("cap-6", 1, text="a figure caption"),
        ],
    )

    assert result.diagnostics.source_role_denials == 1


def test_assemble_final_markdown_source_role_refusal_needs_the_role_not_the_placeholder_text():
    # Spec 058 Non-goals: no placeholder regex on the decision path. The same text with NO
    # source role must behave exactly as it does today -- the merge still happens.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["[[DOCX_IMAGE_img_070]]\n\nи продолжение фразы"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "no-role-1", "text": "[[DOCX_IMAGE_img_070]]"},
            {"block_index": 1, "paragraph_id": "no-role-2", "text": "и продолжение фразы"},
        ],
        source_paragraphs=None,
    )

    assert result.diagnostics.source_role_denials == 0
    assert result.diagnostics.accepted_merges == 1


def test_assemble_final_markdown_refuses_merge_when_source_tail_is_non_ascii_whitespace():
    # Spec 057, gap found by independent review: the importer keeps a run's trailing
    # whitespace OUTSIDE the emphasis markers (document/extraction.py:1378-1379), and that
    # whitespace can be a NBSP. An ASCII-only trim reads this as "no terminal punctuation"
    # and destroys a real boundary.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["**Завершено.** \n\nи далее по тексту"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "nbsp-left", "text": "**Завершено.** "},
            {"block_index": 1, "paragraph_id": "nbsp-right", "text": "и далее по тексту"},
        ],
        source_paragraphs=[
            # The tail is U+00A0, built in code because a literal NBSP is invisible here.
            _make_paragraph_stub("nbsp-left", 0, text="**Complete.**" + chr(0x00A0)),
            _make_paragraph_stub("nbsp-right", 1, text="and onward"),
        ],
    )

    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.source_terminal_denials == 1


def test_assemble_final_markdown_preserves_index_page_reference_fragment_boundary():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Harbour Lantern Project, 128– 130\n\n179– 180"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "index-left", "text": "Harbour Lantern Project, 128– 130"},
            {"block_index": 1, "paragraph_id": "index-right", "text": "179– 180"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("index-left", 0),
            _make_paragraph_stub("index-right", 1),
        ],
    )

    assert result.final_markdown == "Harbour Lantern Project, 128– 130\n\n179– 180"
    assert result.diagnostics.accepted_merges == 0
    assert result.diagnostics.protected_boundary_denials >= 1
    assert [entry.merged_paragraph_ids for entry in result.entries] == [("index-left",), ("index-right",)]


def test_assemble_final_markdown_preserves_registry_backed_text_verbatim():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Суд Judgment #1 уже начался."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "body-1", "text": "Суд Judgment #1 уже начался."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-1", 0),
        ],
    )

    assert result.final_markdown == "Суд Judgment #1 уже начался."
    assert result.entries[0].text == "Суд Judgment #1 уже начался."


def test_assemble_final_markdown_normalizes_mixed_script_in_registry_backed_entries():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Прежде чем суперразумa догонит квантовый скачок."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "body-1", "text": "Прежде чем суперразумa догонит квантовый скачок."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-1", 0),
        ],
    )

    assert "суперразумa" not in result.final_markdown
    assert "суперразума" in result.final_markdown
    assert result.entries[0].text == "Прежде чем суперразума догонит квантовый скачок."


def test_assemble_final_markdown_preserves_residual_bullet_glyphs_in_registry_backed_entries_for_late_phase_classification():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Посттрибулационисты считают, что Иисус придёт в конце ● скорби.\n\n● собирают армию в 200 миллионов солдат."
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-1",
                "text": "Посттрибулационисты считают, что Иисус придёт в конце ● скорби.",
            },
            {
                "block_index": 1,
                "paragraph_id": "body-2",
                "text": "● собирают армию в 200 миллионов солдат.",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-1", 0),
            _make_paragraph_stub("body-2", 1),
        ],
    )

    assert "●" in result.final_markdown
    assert "Посттрибулационисты считают, что Иисус придёт в конце ● скорби." in result.final_markdown
    assert "● собирают армию в 200 миллионов солдат." in result.final_markdown
    assert result.entries[0].text == "Посттрибулационисты считают, что Иисус придёт в конце ● скорби."
    assert result.entries[1].text == "● собирают армию в 200 миллионов солдат."


def test_assemble_final_markdown_preserves_heading_boundary_without_running_bullet_display_cleanup():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["## Раздел", "● собирают армию в 200 миллионов солдат."],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "heading-1", "text": "## Раздел"},
            {"block_index": 2, "paragraph_id": "body-1", "text": "● собирают армию в 200 миллионов солдат."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("heading-1", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("body-1", 1),
        ],
    )

    assert result.entries[0].text == "## Раздел"
    assert result.entries[1].text == "● собирают армию в 200 миллионов солдат."
    assert result.final_markdown.startswith("## Раздел\n\n")


def test_assemble_final_markdown_normalizes_registry_backed_intro_and_carryover_list_markers():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Поразительно, но все петли следуют одной и той же схеме: 1.\n\n"
            "Духовные существа восстают против Бога.\n\n"
            "2. Бог судит их за грех.\n\n"
            "3. Бог спасает остаток верных."
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "intro", "text": "Поразительно, но все петли следуют одной и той же схеме: 1."},
            {"block_index": 1, "paragraph_id": "item-1", "text": "Духовные существа восстают против Бога."},
            {"block_index": 1, "paragraph_id": "item-2", "text": "2. Бог судит их за грех."},
            {"block_index": 1, "paragraph_id": "item-3", "text": "3. Бог спасает остаток верных."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("intro", 0),
            _make_paragraph_stub("item-1", 1),
            _make_paragraph_stub("item-2", 2),
            _make_paragraph_stub("item-3", 3),
        ],
    )

    assert "схеме: 1." not in result.final_markdown
    assert "Поразительно, но все петли следуют одной и той же схеме:" in result.final_markdown
    assert "1. Духовные существа восстают против Бога." in result.final_markdown
    assert "2. Бог судит их за грех." in result.final_markdown
    assert "3. Бог спасает остаток верных." in result.final_markdown


def test_assemble_final_markdown_normalizes_registry_backed_number_carryover_chain():
    # Positive control for spec 063 P0. The sources are the real list-fragment shape: every
    # ordinal opens its OWN source paragraph, so no source paragraph contains the number its
    # translation ends in. Until 2026-11-07 the stubs had empty text, which made this chain
    # indistinguishable from a bibliography whose entries end in years -- and the test pinned
    # the defect: "Обвинитель-Противник 2." became "1. …" through an INVENTED "1.". Now the
    # "1." is the intro's own, moved and then read from the live entry; nothing is invented.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Сатана-Дьявол пытается воспроизвести Троицу: 1.\n\n"
            "Обвинитель-Противник 2.\n\n"
            "Звероподобная сущность Антихриста 3.\n\n"
            "Вторая сущность — зверь/лжепророк."
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "intro", "text": "Сатана-Дьявол пытается воспроизвести Троицу: 1."},
            {"block_index": 1, "paragraph_id": "item-1", "text": "Обвинитель-Противник 2."},
            {"block_index": 1, "paragraph_id": "item-2", "text": "Звероподобная сущность Антихриста 3."},
            {"block_index": 1, "paragraph_id": "item-3", "text": "Вторая сущность — зверь/лжепророк."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("intro", 0, text="Satan the Devil tries to imitate the Trinity:"),
            _make_paragraph_stub("item-1", 1, text="1. The Accuser-Adversary"),
            _make_paragraph_stub("item-2", 2, text="2. The beast-like entity of the Antichrist"),
            _make_paragraph_stub("item-3", 3, text="3. The second entity, the beast/false prophet."),
        ],
    )

    assert result.entries[0].text == "Сатана-Дьявол пытается воспроизвести Троицу:"
    assert result.entries[1].text == "1. Обвинитель-Противник"
    assert result.entries[2].text == "2. Звероподобная сущность Антихриста"
    assert result.entries[3].text == "3. Вторая сущность — зверь/лжепророк."
    assert Counter(re.findall(r"\d+", result.final_markdown)) == Counter({"1": 1, "2": 1, "3": 1})


def test_assemble_final_markdown_normalizes_registry_backed_emoji_marker_fragment():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Представьте, если этим лидером окажется Дональд Трамп.\n\n😂 2.\n\nВ первой половине"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "body-1", "text": "Представьте, если этим лидером окажется Дональд Трамп."},
            {"block_index": 1, "paragraph_id": "emoji", "text": "😂 2."},
            {"block_index": 1, "paragraph_id": "body-2", "text": "В первой половине"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-1", 0),
            _make_paragraph_stub("emoji", 1),
            _make_paragraph_stub("body-2", 2),
        ],
    )

    assert result.entries[1].text == "😂"
    assert result.entries[2].text == "2. В первой половине"
    assert "1. 😂" not in result.final_markdown


def test_assemble_final_markdown_normalizes_registry_backed_trailing_next_item_with_heading_target():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "5. Держитесь подальше от зла. Таковых удаляйся». 6.\n\n"
            "## Примите срочные меры, чтобы подготовиться к почти неизбежному полному глобальному экономическому исключению:"
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "item-5",
                "text": "5. Держитесь подальше от зла. Таковых удаляйся». 6.",
            },
            {
                "block_index": 1,
                "paragraph_id": "heading-6",
                "text": "## Примите срочные меры, чтобы подготовиться к почти неизбежному полному глобальному экономическому исключению:",
            },
        ],
        # Positive control for spec 063 P0: "6." opens the NEXT source paragraph and is absent
        # from item-5's own source, so it is a displaced ordinal, not item-5's content.
        source_paragraphs=[
            _make_paragraph_stub("item-5", 0, text="5. Stay away from evil. Avoid such people."),
            _make_paragraph_stub(
                "heading-6",
                1,
                role="heading",
                structural_role="heading",
                heading_level=2,
                text="6. Take urgent steps to prepare for an almost inevitable total global economic exclusion:",
            ),
        ],
    )

    assert result.entries[0].text == "5. Держитесь подальше от зла. Таковых удаляйся»."
    assert result.entries[1].text == "6. Примите срочные меры, чтобы подготовиться к почти неизбежному полному глобальному экономическому исключению:"
    assert "## Примите срочные меры" not in result.final_markdown


def test_assemble_final_markdown_keeps_chapter_heading_after_footnote_hanging_number():
    # A footnote/endnote block ending in a hanging page reference ("… с. 24.")
    # must not fold the following chapter heading into a numbered list item.
    # The left block is not a numbered list item (no leading ordinal), so the
    # trailing number is a page reference, not a list marker.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Подробнее см. Смит, Экономика денег, с. 24.\n\n# Глава IV"
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "footnote", "text": "Подробнее см. Смит, Экономика денег, с. 24."},
            {"block_index": 1, "paragraph_id": "chapter", "text": "# Глава IV"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("footnote", 0, role="footnote", structural_role="footnote"),
            _make_paragraph_stub("chapter", 1, role="heading", structural_role="heading", heading_level=1),
        ],
    )

    assert result.entries[0].text == "Подробнее см. Смит, Экономика денег, с. 24."
    assert result.entries[1].text == "# Глава IV"
    # The heading number was not stolen: no "24. Глава IV" leak, and the left
    # footnote block gained no parasitic leading "23." marker.
    assert "24. Глава IV" not in result.final_markdown
    assert not result.entries[0].text.startswith("23.")


_NUMBER_TOKEN_PATTERN = re.compile(r"\d+")
_STACKED_LEADING_ORDINALS_PATTERN = re.compile(r"^(?:#{1,6}\s+)?\d+[.)]\s+\d+[.)]\s")


def _assemble_single_block(paragraphs):
    """Run the PRODUCTION assembly on one registry-backed block.

    ``paragraphs``: ``(paragraph_id, model_text, source_text, role, heading_level)``. An empty
    ``source_text`` is "source unknown", which is how the older stub tests above read.
    """
    return document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["\n\n".join(paragraph[1] for paragraph in paragraphs)],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": paragraph[0], "text": paragraph[1]} for paragraph in paragraphs
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                paragraph[0],
                position,
                role=paragraph[3],
                structural_role=paragraph[3],
                heading_level=paragraph[4],
                text=paragraph[2],
            )
            for position, paragraph in enumerate(paragraphs)
        ],
    )


def _assert_list_fragment_carry_invariants(paragraphs, result):
    # Spec 063 P0 invariant: the list-fragment carry may MOVE a number token, never CREATE or
    # DELETE one, and never leaves a paragraph opening with two ordinals.
    model_numbers = Counter(_NUMBER_TOKEN_PATTERN.findall("\n".join(paragraph[1] for paragraph in paragraphs)))
    delivered_numbers = Counter(_NUMBER_TOKEN_PATTERN.findall(result.final_markdown))
    assert delivered_numbers == model_numbers
    assert not any(_STACKED_LEADING_ORDINALS_PATTERN.match(entry.text) for entry in result.entries)


def _assert_delivered_unchanged(paragraphs, result):
    assert result.diagnostics.accepted_merges == 0
    assert [entry.text for entry in result.entries] == [paragraph[1] for paragraph in paragraphs]
    _assert_list_fragment_carry_invariants(paragraphs, result)


def test_list_fragment_carry_moves_the_digits_exactly_as_written():
    # Codex acceptance finding 6: the carry parsed "02" to an int and printed "2", so the
    # multiset of number tokens changed. A carry moves the token; it never rewrites it.
    paragraphs = [
        ("item-1", "1. Первый пункт 02.", "", "body", None),
        ("item-2", "Продолжение второго пункта.", "", "body", None),
    ]

    result = _assemble_single_block(paragraphs)

    assert [entry.text for entry in result.entries] == ["1. Первый пункт", "02. Продолжение второго пункта."]
    _assert_list_fragment_carry_invariants(paragraphs, result)


def test_list_fragment_carry_sees_an_ordinal_inside_emphasis_markers():
    # Codex acceptance finding 6: the follower already opens with its ordinal, written
    # inside the bold the importer baked in; carrying would give "2. **2. Второй пункт**".
    paragraphs = [
        ("item-1", "1. Первый пункт 2.", "", "body", None),
        ("item-2", "**2. Второй пункт**", "", "body", None),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)
    assert result.final_markdown == document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(
        "1. Первый пункт 2.\n\n**2. Второй пункт**"
    )


def test_assemble_final_markdown_keeps_a_trailing_year_the_source_owns():
    # Rethinking Money 2026-11-07, delivered.md:3201-3203: the year closing a bibliography
    # entry was cut off and prepended to the NEXT entry ("2010. www…"), and "2009." was
    # invented for the entry that lost it.
    paragraphs = [
        (
            "p1676",
            "“Gallery of Ports in Flood.” Harbour Herald Tides Section, July 19, 2011.",
            "“Gallery of Ports in Flood.” Harbour Herald Tides Section, July 19, 2011.",
            "body",
            None,
        ),
        (
            "p1677",
            "www .theharbourherald .com /galleries /2011 /07 /19 /50 -ports -in -flood -html .",
            "www .theharbourherald .com /galleries /2011 /07 /19 /50 -ports -in -flood -html .",
            "body",
            None,
        ),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


@pytest.mark.parametrize("source_known", [True, False], ids=["source-known", "source-unknown"])
def test_assemble_final_markdown_keeps_every_number_of_a_year_chain(source_known):
    # Rethinking Money p1641-p1643: every entry ends in a year. The pass used to walk a stale
    # copy of the list, so the year carried onto entry N+1 was overwritten when N+1 was
    # processed: 2008 and 1981 vanished from the document.
    paragraphs = [
        (
            "a",
            "Marrow, H. W. *Keeper of His Light.* Port Kelby: Tideway, 2008.",
            "Marrow, H. W. *Keeper of His Light.* Port Kelby: Tideway, 2008.",
            "body",
            None,
        ),
        (
            "b",
            "Varden, Ferrand. *La dinamica del faro.* Kelbra: Il Molo, 1981.",
            "Varden, Ferrand. *La dinamica del faro.* Kelbra: Il Molo, 1981.",
            "body",
            None,
        ),
        (
            "c",
            "Brzostowski, Zbyszek. *The Tide.* Port Kelby: Harbour Books, 2004.",
            "Brzostowski, Zbyszek. *The Tide.* Port Kelby: Harbour Books, 2004.",
            "body",
            None,
        ),
        ("d", "Кассий Марлоу. *Морская история*, кн. 66.", "Cassius Marlow. *Sea History*, book 66.", "body", None),
    ]
    if not source_known:
        paragraphs = [(pid, text, "", role, level) for pid, text, _source, role, level in paragraphs]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


def test_assemble_final_markdown_never_deletes_a_carried_number_in_a_chain():
    # The stale-copy deletion in isolation. Here the sources do NOT contain the trailing
    # numbers, so the first carry is legitimate; the second entry then opens with the moved
    # "2008." and ends in "1981.", which is not 2009, so it must stay as it now reads. The
    # stale walk re-parsed "Gamma delta, 1981." without its new prefix and wrote "1980. Gamma
    # delta," over it: 2008 and 1981 gone, 1980 invented.
    paragraphs = [
        ("a", "Alpha beta, 2008.", "Alpha beta", "body", None),
        ("b", "Gamma delta, 1981.", "Gamma delta", "body", None),
        ("c", "Epsilon zeta.", "Epsilon zeta.", "body", None),
    ]

    result = _assemble_single_block(paragraphs)

    assert [entry.text for entry in result.entries] == [
        "Alpha beta,",
        "2008. Gamma delta, 1981.",
        "Epsilon zeta.",
    ]
    _assert_list_fragment_carry_invariants(paragraphs, result)


def test_assemble_final_markdown_keeps_a_split_endnote_page_number():
    # Value of Everything p1340-p1342: the PDF import split note 4, and its continuation ends
    # in a page number. "7" was carried onto note 5 ("7. 5. П. Марчетти…") and "6." was
    # invented for the continuation.
    paragraphs = [
        (
            "a",
            "4. Т. Марн, «Богатство гавани во внешнем плавании» (1664; Кельбрук:",
            "4. T. Marn, Harbour's Treasure by Forraign Sailing (1664; Kelbrook:",
            "body",
            None,
        ),
        ("c", "Tideway, 1865), с. 7.", "Tideway, 1865), p. 7.", "body", None),
        (
            "b",
            "5. П. Марчетти, *Доход гаваней* (Порт-Келби: University Press, 1957), с. 29.",
            "5. P. Marchetti, The Income of Harbours (Port Kelby: University Press, 1957), p. 29.",
            "body",
            None,
        ),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


def test_assemble_final_markdown_keeps_a_chapter_reference_and_the_heading_after_it():
    # Creating Wealth p1790/p1791: "10. См. главу 11." lost its "11", and the heading after it
    # was demoted to the list item "11. Приложение". The note's own ordinal made the heading
    # guard step aside; the source owning "11" is what tells the two apart.
    paragraphs = [
        ("p1790", "10. См. главу 11.", "10. See Chapter 11.", "body", None),
        ("p1791", "### Приложение", "Appendix", "heading", 3),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)
    assert "### Приложение" in result.final_markdown


@pytest.mark.parametrize("source_known", [True, False], ids=["source-known", "source-unknown"])
def test_assemble_final_markdown_keeps_prose_ending_in_a_number_intact(source_known):
    # 6bc8ff9's own example (2026-08-03 literary-edit p0106), through the production
    # assembly. Its anti-regression test calls only the markdown twin, which runs second:
    # this text still delivered "64. …на пенсию в" + "65. Он тихий человек…".
    paragraphs = [
        (
            "p0106",
            "Бывший смотритель, он гребёт здесь уже 18 лет — с тех пор как вышел на пенсию в 65.",
            "A former lighthouse keeper, he has rowed here for 18 years, since he retired at 65." if source_known else "",
            "body",
            None,
        ),
        (
            "p0107",
            "Он тихий человек и говорит, что сел на эти вёсла по просьбе дочери.",
            "He is a quiet man and says he took up the oars at his daughter's urging." if source_known else "",
            "body",
            None,
        ),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


def test_assemble_final_markdown_keeps_index_entry_ending_in_a_page_number():
    # Registry-pass sibling of the markdown twin's index-entry test: same input.
    paragraphs = [
        ("i1", "Tidebank, 84–85; ПКО, 162; Марровер (Marrower), 63–64, 91–93, 92.", "", "body", None),
        ("i2", "Puerto Lanterna, 103–108; мореплавание, 20; отлив (приливный), 51–52.", "", "body", None),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


def test_assemble_final_markdown_never_stacks_an_ordinal_on_a_numbered_follower():
    # The source is unknown and the note carries its own consecutive ordinal, so only the
    # stacking guard stands between this and "7. 7. Следующая заметка.".
    paragraphs = [
        ("n6", "6. См. главу 7.", "", "body", None),
        ("n7", "7. Следующая заметка.", "", "body", None),
    ]

    result = _assemble_single_block(paragraphs)

    _assert_delivered_unchanged(paragraphs, result)


@pytest.mark.parametrize(
    "markdown",
    [
        "Поразительно, но все петли следуют одной и той же схеме: 1.\n\nДуховные существа восстают.\n\n2. Бог судит их.",
        "Сатана пытается воспроизвести Троицу: 1.\n\nОбвинитель 2.\n\nЗверь 3.\n\nВторая сущность.",
        "Представьте, если этим лидером окажется Дональд Трамп.\n\n😂 2.\n\nВ первой половине",
        "5. Держитесь подальше от зла. 6.\n\nПримите срочные меры.",
        "Бывший смотритель вышел на пенсию в 65.\n\nОн тихий человек.",
        "Harbour Herald Tides Section, July 19, 2011.\n\nwww .theharbourherald .com .",
        "6. См. главу 7.\n\n7. Следующая заметка.",
        "Схема: 1.\n\n1. Уже пронумерованный пункт.",
    ],
    ids=["intro", "intro-chain", "emoji", "own-ordinal", "prose", "year", "stacking", "intro-stacking"],
)
def test_registry_and_markdown_list_fragment_twins_decide_alike_when_the_source_is_unknown(markdown):
    # One carry decision for both twins: with no source to consult, the registry pass that
    # shapes delivery and the markdown pass behind the DOCX must agree line for line.
    paragraphs = [
        (f"p{position}", text, "", "body", None) for position, text in enumerate(markdown.split("\n\n"))
    ]

    result = _assemble_single_block(paragraphs)
    markdown_twin = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(markdown)

    assert result.final_markdown == markdown_twin
    _assert_list_fragment_carry_invariants(paragraphs, result)


def test_assemble_final_markdown_demotes_false_generated_heading_between_blockquote_fragments():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "> Для христиан жизненно важно помнить, понимать и интуитивно улавливать знамения времени, чтобы, если им будет даровано пережить\n\n## Великая скорбь\n\n> они смогут уверенно сказать: Это знамения."
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "quote-left",
                "text": "> Для христиан жизненно важно помнить, понимать и интуитивно улавливать знамения времени, чтобы, если им будет даровано пережить",
            },
            {"block_index": 1, "paragraph_id": "false-heading", "text": "## Великая скорбь"},
            {"block_index": 1, "paragraph_id": "quote-right", "text": "> они смогут уверенно сказать: Это знамения."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("quote-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="body", structural_role="body"),
            _make_paragraph_stub("quote-right", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == (
        "> Для христиан жизненно важно помнить, понимать и интуитивно улавливать знамения времени, "
        "чтобы, если им будет даровано пережить Великая скорбь они смогут уверенно сказать: Это знамения."
    )
    assert len(result.entries) == 1
    assert result.diagnostics.demoted_false_headings == 1
    assert result.diagnostics.accepted_merges == 2
    assert result.entries[0].merged_paragraph_ids == ("quote-left", "false-heading", "quote-right")
    assert any(
        decision.action == "demote_heading" and decision.paragraph_ids == ("false-heading",)
        for decision in result.diagnostics.merge_decisions
    )


def test_assemble_final_markdown_demotes_false_generated_heading_inside_body_phrase():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "На людей, получивших\n\n## начертание зверя\n\nи поклонявшихся его образу, приходят язвы."
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "body-left", "text": "На людей, получивших"},
            {"block_index": 1, "paragraph_id": "false-heading", "text": "## начертание зверя"},
            {
                "block_index": 1,
                "paragraph_id": "body-right",
                "text": "и поклонявшихся его образу, приходят язвы.",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="body", structural_role="body"),
            _make_paragraph_stub("body-right", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == "На людей, получивших начертание зверя и поклонявшихся его образу, приходят язвы."
    assert len(result.entries) == 1
    assert result.diagnostics.demoted_false_headings == 1
    assert result.diagnostics.accepted_merges == 2
    assert result.entries[0].merged_paragraph_ids == ("body-left", "false-heading", "body-right")
    assert any(
        decision.action == "merge" and decision.paragraph_ids == ("body-left", "false-heading", "body-right")
        for decision in result.diagnostics.merge_decisions
    )


def test_assemble_final_markdown_demotes_false_generated_heading_across_adjacent_blocks():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "> Христианам жизненно необходимо помнить знамения времени, чтобы, если им будет дано претерпеть",
            "## Великая скорбь",
            "> они могли бы уверенно сказать: Это знаки.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "quote-left", "text": "> Христианам жизненно необходимо помнить знамения времени, чтобы, если им будет дано претерпеть"},
            {"block_index": 2, "paragraph_id": "false-heading", "text": "## Великая скорбь"},
            {"block_index": 3, "paragraph_id": "quote-right", "text": "> они могли бы уверенно сказать: Это знаки."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("quote-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("quote-right", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == (
        "> Христианам жизненно необходимо помнить знамения времени, чтобы, если им будет дано претерпеть Великая скорбь\n\n"
        "> они могли бы уверенно сказать: Это знаки."
    )
    assert len(result.entries) == 2
    assert result.entries[0].merged_paragraph_ids == ("quote-left", "false-heading")
    assert result.entries[1].text == "> они могли бы уверенно сказать: Это знаки."
    assert result.diagnostics.demoted_false_headings == 1
    assert result.diagnostics.accepted_merges == 1


def test_assemble_final_markdown_merges_blockquote_into_following_body_continuation_across_adjacent_blocks():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "## Великая скорбь\n\n> они могли бы с уверенностью сказать: Это знамения. Всё это происходит не случайно. Таков Божий замысел. Я могу доверять Ему. Он суверенен. С Его Святым Духом",
            "Я смогу выдержать до конца.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "heading-1", "text": "## Великая скорбь"},
            {
                "block_index": 1,
                "paragraph_id": "quote-left",
                "text": "> они могли бы с уверенностью сказать: Это знамения. Всё это происходит не случайно. Таков Божий замысел. Я могу доверять Ему. Он суверенен. С Его Святым Духом",
            },
            {"block_index": 2, "paragraph_id": "body-right", "text": "Я смогу выдержать до конца."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("heading-1", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("quote-left", 1, role="body", structural_role="body"),
            _make_paragraph_stub("body-right", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == (
        "## Великая скорбь\n\n"
        "> они могли бы с уверенностью сказать: Это знамения. Всё это происходит не случайно. "
        "Таков Божий замысел. Я могу доверять Ему. Он суверенен. С Его Святым Духом Я смогу выдержать до конца."
    )
    assert len(result.entries) == 2
    assert result.entries[1].merged_paragraph_ids == ("quote-left", "body-right")
    assert result.diagnostics.accepted_merges == 1


def test_assemble_final_markdown_treats_uppercase_pronoun_clause_as_continuation_after_incomplete_blockquote():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "> С Его Святым Духом",
            "Я смогу выдержать до конца.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "quote-left", "text": "> С Его Святым Духом"},
            {"block_index": 2, "paragraph_id": "body-right", "text": "Я смогу выдержать до конца."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("quote-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("body-right", 1, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == "> С Его Святым Духом Я смогу выдержать до конца."
    assert len(result.entries) == 1
    assert result.entries[0].merged_paragraph_ids == ("quote-left", "body-right")
    assert result.diagnostics.accepted_merges == 1


def test_assemble_final_markdown_demotes_false_generated_heading_with_previous_block_and_same_block_tail_context():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Пожалуй, главный вывод состоит в том, что каждое поколение христиан должно готовиться к возможности пережить",
            "## Великая скорбь\n\n.",
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "Пожалуй, главный вывод состоит в том, что каждое поколение христиан должно готовиться к возможности пережить",
            },
            {"block_index": 2, "paragraph_id": "false-heading", "text": "## Великая скорбь"},
            {"block_index": 2, "paragraph_id": "tail", "text": "."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("tail", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == (
        "Пожалуй, главный вывод состоит в том, что каждое поколение христиан должно готовиться к возможности пережить Великая скорбь."
    )
    assert len(result.entries) == 1
    assert result.entries[0].merged_paragraph_ids == ("body-left", "false-heading", "tail")
    assert result.diagnostics.demoted_false_headings == 1
    assert result.diagnostics.accepted_merges == 2


# Spec 065 (I-4). The shape below is the one that lost a section heading on a paid run: an
# unpunctuated label line closes the previous block; the next block opens with the heading
# and a short dateline. ``_entry_has_previous_block_and_same_block_tail_context`` reads that
# shape as a sentence torn across the block boundary, demotes the heading and welds it to
# the dateline. The same shape is what an index entry the import tagged as a heading looks
# like, so the shape stays as it is; the document's own contents listing decides.
_SPEC_065_LONG_BODY = (
    "Эта работа складывалась в два этапа, и каждый из них оставил в тексте свой след: сначала рабочая "
    "группа, затем отдельная редакция."
)


def _spec_065_heading_case(*, contents_position: int | None, contents_text: str = "**Afterword** *57*"):
    paragraphs = [
        _make_paragraph_stub("label", 10, text="**H**: Annex on tides"),
        _make_paragraph_stub("heading", 11, role="heading", structural_role="heading", heading_level=2, text="Afterword"),
        _make_paragraph_stub("dateline", 12, text="*Geneva, March 2010*"),
        _make_paragraph_stub("body", 13, text="This work took shape in two stages."),
    ]
    if contents_position is not None:
        contents = [
            _make_paragraph_stub("contents-header", 0, role="heading", structural_role="toc_header", heading_level=2, text="Contents"),
            _make_paragraph_stub("contents-entry", 1, structural_role="toc_entry", text=contents_text),
        ]
        paragraphs[contents_position:contents_position] = contents
    return document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "**H**: Приложение о приливах",
            "## Послесловие\n\n*Женева, март 2010 г.*\n\n" + _SPEC_065_LONG_BODY,
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "label", "text": "**H**: Приложение о приливах"},
            {"block_index": 2, "paragraph_id": "heading", "text": "## Послесловие"},
            {"block_index": 2, "paragraph_id": "dateline", "text": "*Женева, март 2010 г.*"},
            {"block_index": 2, "paragraph_id": "body", "text": _SPEC_065_LONG_BODY},
        ],
        source_paragraphs=paragraphs,
    )


def test_assemble_final_markdown_keeps_contents_listed_heading_before_dateline():
    result = _spec_065_heading_case(contents_position=0)

    assert result.final_markdown == (
        "**H**: Приложение о приливах\n\n## Послесловие\n\n*Женева, март 2010 г.*\n\n" + _SPEC_065_LONG_BODY
    )
    assert [entry.paragraph_id for entry in result.entries] == ["label", "heading", "dateline", "body"]
    assert result.entries[1].generated_heading_kind == "real_heading"
    assert result.diagnostics.demoted_false_headings == 0
    assert result.diagnostics.accepted_merges == 0


def test_assemble_final_markdown_still_demotes_the_same_shape_when_contents_do_not_list_it():
    # Counterexample: no contents listing -> today's behaviour, unchanged. This is the path
    # that keeps an index entry the import tagged as a heading out of the heading outline.
    result = _spec_065_heading_case(contents_position=None)

    # Here nothing breaks the chain, so the label line joins too (block 1 and block 2 are
    # adjacent); on the paid run the label had already merged with ITS predecessor.
    assert result.final_markdown == (
        "**H**: Приложение о приливах Послесловие *Женева, март 2010 г.*\n\n" + _SPEC_065_LONG_BODY
    )
    assert result.entries[0].merged_paragraph_ids == ("label", "heading", "dateline")
    assert result.diagnostics.demoted_false_headings == 1


def test_assemble_final_markdown_contents_listing_after_the_heading_does_not_shield_it():
    # Counterexample: front matter BEFORE the contents (a title-page credit line) repeats a
    # contents line without being that section's heading; only a heading standing after its
    # listing is shielded.
    result = _spec_065_heading_case(contents_position=4)

    assert result.entries[0].merged_paragraph_ids == ("label", "heading", "dateline")
    assert result.diagnostics.demoted_false_headings == 1


def test_assemble_final_markdown_contents_listing_does_not_stop_a_torn_body_sentence_from_merging():
    # Counterexample: the shield is for headings only; a body paragraph torn across a block
    # boundary still rejoins its continuation in a document that has a contents listing.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "Ряд исследователей наблюдал этот эффект в течение",
            "нескольких лет подряд.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "left", "text": "Ряд исследователей наблюдал этот эффект в течение"},
            {"block_index": 2, "paragraph_id": "right", "text": "нескольких лет подряд."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("contents-header", 0, role="heading", structural_role="toc_header", heading_level=2, text="Contents"),
            _make_paragraph_stub("contents-entry", 1, structural_role="toc_entry", text="Afterword"),
            _make_paragraph_stub("left", 2, text="Several researchers observed this effect over"),
            _make_paragraph_stub("right", 3, text="several years in a row."),
        ],
    )

    assert result.final_markdown == "Ряд исследователей наблюдал этот эффект в течение нескольких лет подряд."
    assert result.entries[0].merged_paragraph_ids == ("left", "right")


@pytest.mark.parametrize(
    ("contents_text", "heading_text", "listed"),
    [
        ("**Afterword** *57*", "Afterword", True),
        ("*Acknowledgements 249*", "ACKNOWLEDGEMENTS", True),
        ("*Foreword* *ix*", "Foreword", True),
        ("Notes ........ 225", "Notes", True),
        ("Chapter IV", "Chapter IV", True),
        ("Chapter IV", "Chapter", False),
        ("Afterword and Thanks", "Afterword", False),
    ],
)
def test_collect_toc_listed_heading_ids_compares_whole_lines(contents_text, heading_text, listed):
    paragraphs = [
        _make_paragraph_stub("contents-entry", 0, structural_role="toc_entry", text=contents_text),
        _make_paragraph_stub("heading", 1, role="heading", structural_role="heading", heading_level=2, text=heading_text),
        _make_paragraph_stub("body", 2, text=heading_text),
    ]

    result = document_pipeline_output_validation._collect_toc_listed_heading_ids(paragraphs)

    # A body paragraph with the same text is never listed: the shield is for headings.
    assert result == (frozenset({"heading"}) if listed else frozenset())


# Spec 067 FR-002 (A-2). Money and Sustainability's Box 7.1 on the fourth paid run: two header
# cells close one block, the next block opens with a bold label cell the document layer had
# made a heading and a row of page references. ``_entry_has_previous_block_and_same_block_tail
# _context`` read the label as a sentence torn across the block boundary, demoted it, and
# ``adjacent_continuation_recovery`` welded all four into one paragraph (``delivered.md:1861``).
# The import flags all three cells. The text is synthetic, of the same form: two header cells
# in capitals (one torn by the extractor), a bold label ending in a spaced colon, a row of
# names with page references.
def _spec_067_box_case(*, cells: bool):
    paragraphs = [
        _make_paragraph_stub("north", 10, text="NORTH WING"),
        _make_paragraph_stub("south", 11, text="SO UTH WING"),
        _make_paragraph_stub("label", 12, role="heading", structural_role="heading", heading_level=2, text="**Harbour Project s :**"),
        _make_paragraph_stub("row", 13, text="Lanternfield p.142 Harbour Tok ens p.144 Quiet Waters p.151"),
    ]
    for paragraph in paragraphs[:3]:
        setattr(paragraph, "is_pdf_table_cell", cells)
    return document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "СЕВЕРНОЕ КРЫЛО\n\nЮЖНОЕ КРЫЛО",
            "## **Портовые проекты:**\n\nЛантернфилд, с. 142; портовые токены, с. 144",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "north", "text": "СЕВЕРНОЕ КРЫЛО"},
            {"block_index": 1, "paragraph_id": "south", "text": "ЮЖНОЕ КРЫЛО"},
            {"block_index": 2, "paragraph_id": "label", "text": "## **Портовые проекты:**"},
            {"block_index": 2, "paragraph_id": "row", "text": "Лантернфилд, с. 142; портовые токены, с. 144"},
        ],
        source_paragraphs=paragraphs,
    )


def test_assemble_final_markdown_neither_demotes_nor_merges_a_table_cell():
    result = _spec_067_box_case(cells=True)

    assert [entry.paragraph_id for entry in result.entries] == ["north", "south", "label", "row"]
    assert result.final_markdown == (
        "СЕВЕРНОЕ КРЫЛО\n\nЮЖНОЕ КРЫЛО\n\n## **Портовые проекты:**\n\nЛантернфилд, с. 142; портовые токены, с. 144"
    )
    assert [entry.source_is_table_cell for entry in result.entries] == [True, True, True, False]
    assert result.entries[2].generated_heading_kind == "real_heading"
    assert result.diagnostics.demoted_false_headings == 0
    assert result.diagnostics.accepted_merges == 0
    denials = [d for d in result.diagnostics.merge_decisions if d.reason == "source_boundary_table_cell"]
    # The two header cells are the one pair the text predicates would join; once the label is
    # not demoted it is a heading again, and a heading boundary is never a merge candidate.
    assert [d.paragraph_ids for d in denials] == [("north", "south")]
    assert result.diagnostics.source_role_denials == 1


def test_assemble_final_markdown_same_box_without_cell_flags_is_welded_as_before():
    # ANTI-VACUUM: without the flag the shape is demoted and welded exactly as the fourth run
    # delivered it, so the refusal above is the flag's doing.
    result = _spec_067_box_case(cells=False)

    assert result.final_markdown == (
        "СЕВЕРНОЕ КРЫЛО ЮЖНОЕ КРЫЛО **Портовые проекты:** Лантернфилд, с. 142; портовые токены, с. 144"
    )
    assert result.entries[0].merged_paragraph_ids == ("north", "south", "label", "row")
    assert result.diagnostics.demoted_false_headings == 1


def test_assemble_final_markdown_cell_flag_does_not_stop_a_torn_body_sentence_from_merging():
    # Anti-regression 3 of spec 067: a body paragraph torn across a block boundary still rejoins
    # its continuation in a document whose other paragraphs are table cells.
    cell = _make_paragraph_stub("cell", 1, text="NORTH WING")
    setattr(cell, "is_pdf_table_cell", True)
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "СЕВЕРНОЕ КРЫЛО",
            "Ряд исследователей наблюдал этот эффект в течение",
            "нескольких лет подряд.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "cell", "text": "СЕВЕРНОЕ КРЫЛО"},
            {"block_index": 2, "paragraph_id": "left", "text": "Ряд исследователей наблюдал этот эффект в течение"},
            {"block_index": 3, "paragraph_id": "right", "text": "нескольких лет подряд."},
        ],
        source_paragraphs=[
            cell,
            _make_paragraph_stub("left", 2, text="Several researchers observed this effect over"),
            _make_paragraph_stub("right", 3, text="several years in a row."),
        ],
    )

    assert result.final_markdown == (
        "СЕВЕРНОЕ КРЫЛО\n\nРяд исследователей наблюдал этот эффект в течение нескольких лет подряд."
    )
    assert result.entries[1].merged_paragraph_ids == ("left", "right")
    assert result.entries[1].source_is_table_cell is False


def test_assemble_final_markdown_preserves_source_backed_numbered_citation_heading():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "## (Матфея 24:36)",
            "Христос вернётся, как тать в ночи.",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "heading-1", "text": "## (Матфея 24:36)"},
            {"block_index": 2, "paragraph_id": "body-1", "text": "Христос вернётся, как тать в ночи."},
        ],
        source_paragraphs=[
            _make_paragraph_stub("heading-1", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("body-1", 1, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == "## (Матфея 24:36)\n\nХристос вернётся, как тать в ночи."
    assert len(result.entries) == 2
    assert result.entries[0].generated_heading_kind == "real_heading"
    assert result.diagnostics.demoted_false_headings == 0
    assert result.diagnostics.accepted_merges == 0


def test_assemble_final_markdown_demotes_parenthetical_question_tail_across_mixed_block_boundary():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "«Град и огонь, смешанные с кровью», падают на землю. (Кометы? Астероиды?",
            "## Спутники? Ракеты?)\n\nСгорела треть земли, деревьев и травяных покровов.",
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "«Град и огонь, смешанные с кровью», падают на землю. (Кометы? Астероиды?",
            },
            {"block_index": 2, "paragraph_id": "false-heading", "text": "## Спутники? Ракеты?)"},
            {
                "block_index": 2,
                "paragraph_id": "body-right",
                "text": "Сгорела треть земли, деревьев и травяных покровов.",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("body-right", 2, role="body", structural_role="body"),
        ],
    )

    assert result.final_markdown == (
        "«Град и огонь, смешанные с кровью», падают на землю. (Кометы? Астероиды? Спутники? Ракеты?)\n\n"
        "Сгорела треть земли, деревьев и травяных покровов."
    )
    assert len(result.entries) == 2
    assert result.entries[0].merged_paragraph_ids == ("body-left", "false-heading")
    assert result.entries[1].merged_paragraph_ids == ("body-right",)
    assert result.diagnostics.demoted_false_headings == 1
    assert result.diagnostics.accepted_merges == 1


def test_collect_false_fragment_heading_samples_skips_legitimate_major_section_heading():
    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(
        "## Введение\n\nЭто первый абзац раздела."
    )

    assert samples == []


def test_collect_false_fragment_heading_samples_flags_parenthetical_question_tail_heading():
    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(
        "Кометы? Астероиды?\n\n## Спутники? Ракеты?)\n\nТреть земли будет сожжена."
    )

    assert [sample.reason for sample in samples] == ["sentence_split_heading_present"]
    assert samples[0].text == "## Спутники? Ракеты?)"


def test_collect_false_fragment_heading_samples_from_entries_preserves_source_backed_numbered_citation_heading():
    entries = (
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="## (Матфея 24:36)",
            block_index=1,
            paragraph_id="p1",
            source_index=0,
            role="heading",
            structural_role="heading",
            heading_level=2,
            from_registry=True,
            generated_heading_kind="real_heading",
        ),
        document_pipeline_output_validation.FinalAssemblyEntry(
            text="Христос вернётся, как тать в ночи.",
            block_index=2,
            paragraph_id="p2",
            source_index=1,
            role="body",
            structural_role="body",
            from_registry=True,
        ),
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(entries)

    assert samples == []


def test_collect_false_fragment_heading_samples_from_entries_does_not_report_demoted_question_tail():
    assembly_result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "«Град и огонь, смешанные с кровью», падают на землю. (Кометы? Астероиды?",
            "## Спутники? Ракеты?)\n\nСгорела треть земли, деревьев и травяных покровов.",
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "body-left",
                "text": "«Град и огонь, смешанные с кровью», падают на землю. (Кометы? Астероиды?",
            },
            {"block_index": 2, "paragraph_id": "false-heading", "text": "## Спутники? Ракеты?)"},
            {
                "block_index": 2,
                "paragraph_id": "body-right",
                "text": "Сгорела треть земли, деревьев и травяных покровов.",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("body-left", 0, role="body", structural_role="body"),
            _make_paragraph_stub("false-heading", 1, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("body-right", 2, role="body", structural_role="body"),
        ],
    )

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(assembly_result.entries)

    assert samples == []


def test_assemble_final_markdown_dedupes_adjacent_repeated_heading_phrase():
    assembly_result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ",
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "title",
                "text": "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("title", 0, role="heading", structural_role="heading", heading_level=1),
        ],
    )

    assert assembly_result.final_markdown == "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"
    assert assembly_result.entries[0].text == "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"
    assert (
        document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(
            assembly_result.entries
        )
        == []
    )


def test_assemble_final_markdown_dedupes_repeated_short_heading_inside_title_cluster():
    assembly_result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "## ПЕРЕОСМЫСЛИВАЯ",
            "# ДЕНЬГИ",
            "# ПЕРЕОСМЫСЛЕНИЕ",
            "# ДЕНЬГИ",
            "# КАК НОВЫЕ ВАЛЮТЫ ПРЕВРАЩАЮТ ДЕФИЦИТ В ПРОЦВЕТАНИЕ",
            "# Тобиас Марлоу и Эльза Бранд",
        ],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "title-1", "text": "## ПЕРЕОСМЫСЛИВАЯ"},
            {"block_index": 2, "paragraph_id": "title-2", "text": "# ДЕНЬГИ"},
            {"block_index": 3, "paragraph_id": "title-3", "text": "# ПЕРЕОСМЫСЛЕНИЕ"},
            {"block_index": 4, "paragraph_id": "title-4", "text": "# ДЕНЬГИ"},
            {
                "block_index": 5,
                "paragraph_id": "subtitle",
                "text": "# КАК НОВЫЕ ВАЛЮТЫ ПРЕВРАЩАЮТ ДЕФИЦИТ В ПРОЦВЕТАНИЕ",
            },
            {"block_index": 6, "paragraph_id": "authors", "text": "# Тобиас Марлоу и Эльза Бранд"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("title-1", 0, role="heading", structural_role="heading", heading_level=2),
            _make_paragraph_stub("title-2", 1, role="heading", structural_role="heading", heading_level=1),
            _make_paragraph_stub("title-3", 2, role="heading", structural_role="heading", heading_level=1),
            _make_paragraph_stub("title-4", 3, role="heading", structural_role="heading", heading_level=1),
            _make_paragraph_stub("subtitle", 4, role="heading", structural_role="heading", heading_level=1),
            _make_paragraph_stub("authors", 5, role="heading", structural_role="heading", heading_level=1),
        ],
    )

    assert "# ДЕНЬГИ" in assembly_result.final_markdown
    assert assembly_result.final_markdown.count("# ДЕНЬГИ") == 1
    assert [entry.paragraph_id for entry in assembly_result.entries] == [
        "title-1",
        "title-2",
        "title-3",
        "subtitle",
        "authors",
    ]
    assert (
        document_pipeline_output_validation.collect_false_fragment_heading_samples_from_entries(
            assembly_result.entries
        )
        == []
    )


# --- final assembly deletes text: it must leave a number behind ----------------------
# Both points below used to remove text and record NOTHING - no log line, no counter, no
# entry in the assembly diagnostics (which count merges and demotions, not deletions). A
# run could therefore drop a heading and its own summary would not say so. Behaviour is
# unchanged here; only the trace is new, and each counter is proved to MOVE, because a
# counter that is always zero measures nothing.


def _repeated_heading_phrase_assembly():
    return document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "title",
                "text": "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub("title", 0, role="heading", structural_role="heading", heading_level=1),
        ],
    )


def test_halving_a_repeated_heading_phrase_is_counted_in_characters():
    original = "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"

    with model_accounting.run_model_accounting_scope(
        run_id="run-heading-phrase", source_token="token-heading-phrase"
    ) as ledger:
        assembly_result = _repeated_heading_phrase_assembly()
        snapshot = ledger.snapshot()

    # Behaviour unchanged: the same half is still removed.
    assert assembly_result.final_markdown == "## ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"

    removed_chars = len(original) - len(assembly_result.final_markdown)
    assert removed_chars > 0
    assert snapshot["text_removal_event_count"] == 1
    assert snapshot["text_removal_chars"] == removed_chars
    # A shortened heading is not an emptied unit - the entry still carries text.
    assert snapshot["text_removal_emptied_unit_count"] == 0
    assert snapshot["text_removal_site_counts"] == {"repeated_heading_phrase_halved": 1}
    assert snapshot["text_removal_site_chars"] == {"repeated_heading_phrase_halved": removed_chars}


def test_dropping_a_repeated_short_heading_from_a_cluster_is_counted_in_characters():
    dropped_heading = "# ДЕНЬГИ"

    with model_accounting.run_model_accounting_scope(
        run_id="run-heading-cluster", source_token="token-heading-cluster"
    ) as ledger:
        assembly_result = document_pipeline_output_validation.assemble_final_markdown(
            processed_chunks=[
                "## ПЕРЕОСМЫСЛИВАЯ",
                "# ДЕНЬГИ",
                "# ПЕРЕОСМЫСЛЕНИЕ",
                "# ДЕНЬГИ",
            ],
            generated_paragraph_registry=[
                {"block_index": 1, "paragraph_id": "title-1", "text": "## ПЕРЕОСМЫСЛИВАЯ"},
                {"block_index": 2, "paragraph_id": "title-2", "text": "# ДЕНЬГИ"},
                {"block_index": 3, "paragraph_id": "title-3", "text": "# ПЕРЕОСМЫСЛЕНИЕ"},
                {"block_index": 4, "paragraph_id": "title-4", "text": "# ДЕНЬГИ"},
            ],
            source_paragraphs=[
                _make_paragraph_stub("title-1", 0, role="heading", structural_role="heading", heading_level=2),
                _make_paragraph_stub("title-2", 1, role="heading", structural_role="heading", heading_level=1),
                _make_paragraph_stub("title-3", 2, role="heading", structural_role="heading", heading_level=1),
                _make_paragraph_stub("title-4", 3, role="heading", structural_role="heading", heading_level=1),
            ],
        )
        snapshot = ledger.snapshot()

    # Behaviour unchanged: the fourth entry is still the one that goes.
    assert [entry.paragraph_id for entry in assembly_result.entries] == ["title-1", "title-2", "title-3"]

    assert snapshot["text_removal_event_count"] == 1
    assert snapshot["text_removal_chars"] == len(dropped_heading)
    # A whole entry left the document, so it is an emptied unit as well as characters.
    assert snapshot["text_removal_emptied_unit_count"] == 1
    assert snapshot["text_removal_site_counts"] == {"repeated_heading_cluster_dedupe": 1}
    assert snapshot["text_removal_site_chars"] == {"repeated_heading_cluster_dedupe": len(dropped_heading)}


def test_an_assembly_that_deletes_nothing_leaves_the_removal_counters_at_zero():
    """The other half of the anti-vacuum pair: the counters must not drift upward on
    ordinary input, or a non-zero total would stop meaning anything."""

    with model_accounting.run_model_accounting_scope(
        run_id="run-no-removal", source_token="token-no-removal"
    ) as ledger:
        assembly_result = document_pipeline_output_validation.assemble_final_markdown(
            processed_chunks=["# ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ", "Обычный абзац книги."],
            generated_paragraph_registry=[
                {"block_index": 1, "paragraph_id": "title", "text": "# ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ"},
                {"block_index": 2, "paragraph_id": "p1", "text": "Обычный абзац книги."},
            ],
            source_paragraphs=[
                _make_paragraph_stub("title", 0, role="heading", structural_role="heading", heading_level=1),
                _make_paragraph_stub("p1", 1),
            ],
        )
        snapshot = ledger.snapshot()

    assert assembly_result.final_markdown == "# ПЕРЕОСМЫСЛИВАЯ ДЕНЬГИ\n\nОбычный абзац книги."
    assert snapshot["text_removal_event_count"] == 0
    assert snapshot["text_removal_chars"] == 0
    assert snapshot["text_removal_emptied_unit_count"] == 0
    assert snapshot["text_removal_site_counts"] == {}
    assert snapshot["text_removal_site_chars"] == {}


def test_assemble_final_markdown_preserves_controlled_fallback_registry_metadata():
    assembly_result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Evans bibliography entry."],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "p1",
                "text": "Evans bibliography entry.",
                "controlled_fallback": True,
                "controlled_fallback_kind": "english_residual_output",
            }
        ],
        source_paragraphs=[],
    )

    assert assembly_result.entries[0].controlled_fallback is True
    assert assembly_result.entries[0].controlled_fallback_kind == "english_residual_output"
    assert document_pipeline_output_validation.build_generated_paragraph_registry_from_entries(
        assembly_result.entries
    ) == [
        {
            "block_index": 1,
            "paragraph_id": "p1",
            "text": "Evans bibliography entry.",
            "controlled_fallback": True,
            "controlled_fallback_kind": "english_residual_output",
        }
    ]


def test_run_document_processing_accepts_heading_only_output_for_plaintext_banner_input():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "РАСТУЩЕЕ\tМЕСТНЫХ\tЭКОНОМИКИ С\tМЕСТНЫМИ\tВАЛЮТАМИ",
            "context_before": "",
            "context_after": "",
            "target_chars": 46,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## Развитие местных экономик с помощью местных валют",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Развитие местных экономик с помощью местных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


def test_run_document_processing_rejects_bullet_heading_output():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Нормальный абзац с содержанием и несколькими словами.",
            "context_before": "",
            "context_after": "",
            "target_chars": 48,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "## ●",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "bullet_heading_output" in runtime["state"]["last_error"]


def test_run_document_processing_rejects_toc_body_concat_output():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 29",
            "context_before": "",
            "context_after": "",
            "target_chars": 52,
            "context_chars": 0,
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Содержание\n\nЗаключение ........ 29 Марка 13:13 Введение",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "toc_body_concat" in runtime["state"]["last_error"]


def test_english_residue_inside_a_translated_block_is_no_longer_a_controlled_fallback(tmp_path, monkeypatch):
    """Spec 059 FR-A4: the five-word residual detector is REMOVED, and this pins what that
    costs and what it buys.

    This block used to be classified ``english_residual_output`` because the model's answer
    contained the word "Judgment" -- one of five book words the detector keyed on, which
    Constitution VII forbids. The answer is a normal Russian translation that keeps a proper
    noun, exactly the case spec 059 records as a DETECTOR-caused failure no change of model
    could remove (`spec.md:356-359`). It is now delivered as what it is: valid.

    Honest cost, named rather than hidden: a genuinely half-translated answer that is not
    byte-identical to its source is no longer detected either. The measurement counts ZERO
    such answers in 7 233 records (§11), and FR-A3 forbids the only other instrument.
    """
    monkeypatch.chdir(tmp_path)
    runtime = _build_runtime_capture()
    events = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Первый абзац с нормальным содержанием.",
            "context_before": "",
            "context_after": "",
            "target_chars": 36,
            "context_chars": 0,
            "paragraph_ids": ["p1"],
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Суд Judgment #1 уже начался.",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["last_error"] == ""
    assert runtime["state"]["processed_block_markdowns"] == ["Суд Judgment #1 уже начался."]
    # Empty, and that is the point: the registry gained a row only because the block took the
    # controlled-fallback path. A block that passes writes no registry row here (marker mode
    # is off in this fixture), so an empty registry IS the "no controlled fallback" assertion.
    assert runtime["state"]["processed_paragraph_registry"] == []
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert not [entry for entry in runtime["log"] if entry.get("details", "").startswith("controlled_fallback:")]
    assert runtime["state"].get("latest_controlled_block_fallback_artifact") in (None, "")
    assert not any(args[1] == "block_controlled_fallback" for args, _kwargs in events)


# ``expected_narration_excluded`` is the spec-054 invariant, one row per rejection class:
# the narration artifact carries only speakable target-language text, so a block is dropped
# from it exactly when the controlled fallback delivered the block's own SOURCE text —
# ``empty_processed_block`` (which substitutes ``payload.target_text``) and
# ``source_text_fallback`` (which the classifier defines as output == source). The classes
# that keep the model's own output stay in the narration; that is the anti-vacuum half.
@pytest.mark.parametrize(
    ("job", "generated_markdown", "expected_kind", "expected_markdown", "expected_narration_excluded"),
    [
        (
            {
                "target_text": "Исходный абзац сохранён как fallback.",
                "context_before": "",
                "context_after": "",
                "target_chars": 37,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
                # Spec 059 A-II / FR-A8: this row and the ``source_text_fallback`` one below
                # both DELIVER the block's own source, so on a prose block they now fail the
                # run instead of shipping. The subject here is spec 054's narration rule, so
                # the block is apparatus; the prose behaviour is pinned in
                # ``tests/test_spec_059_translation_completeness.py``.
                "paragraph_regions": ["back_matter"],
            },
            "   ",
            "empty_processed_block",
            "Исходный абзац сохранён как fallback.",
            True,
        ),
        # The ``english_residual_output`` row was removed with the five-word detector that
        # produced it (spec 059 FR-A4). The class stays legal in
        # ``CONTROLLED_BLOCK_FAILURE_POLICY`` and in artifacts already on disk; nothing
        # produces it from a word list any more.
        (
            {
                "target_text": (
                    "This source paragraph is long enough to represent a real untranslated fallback. "
                    "It contains several English words and complete sentences, so retaining it byte for "
                    "byte after a translate operation must be visible to reviewers instead of being "
                    "reported as a normal successful translated block."
                ),
                "context_before": "",
                "context_after": "",
                "target_chars": 268,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
                "paragraph_regions": ["back_matter"],
            },
            (
                "This source paragraph is long enough to represent a real untranslated fallback. "
                "It contains several English words and complete sentences, so retaining it byte for "
                "byte after a translate operation must be visible to reviewers instead of being "
                "reported as a normal successful translated block."
            ),
            "source_text_fallback",
            (
                "This source paragraph is long enough to represent a real untranslated fallback. "
                "It contains several English words and complete sentences, so retaining it byte for "
                "byte after a translate operation must be visible to reviewers instead of being "
                "reported as a normal successful translated block."
            ),
            True,
        ),
        (
            {
                "target_text": "# Заголовок\n\nЭто полноценный абзац с несколькими словами и знаками препинания.",
                "context_before": "",
                "context_after": "",
                "target_chars": 71,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
            },
            "# Heading only",
            "heading_only_output",
            "# Heading only",
            False,
        ),
        (
            {
                "target_text": "Этот абзац должен остаться обычным текстом, а не маркером списка.",
                "context_before": "",
                "context_after": "",
                "target_chars": 66,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
            },
            "## ●",
            "bullet_heading_output",
            "## ●",
            False,
        ),
        (
            {
                "target_text": "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 29",
                "context_before": "",
                "context_after": "",
                "target_chars": 54,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
            },
            "Заключение ........ 29 Марка 13:13 Введение",
            "toc_body_concat",
            "Заключение ........ 29 Марка 13:13 Введение",
            False,
        ),
    ],
)
def test_run_document_processing_continues_on_controlled_fallback_classes(
    tmp_path,
    monkeypatch,
    job,
    generated_markdown,
    expected_kind,
    expected_markdown,
    expected_narration_excluded,
):
    monkeypatch.chdir(tmp_path)
    runtime = _build_runtime_capture()
    events = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[job],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        # Spec 059 FR-A5: the narration exclusion this fixture pins is spec 054's rule about
        # SOURCE-LANGUAGE text, so it applies only to a run that changes language. The
        # operation has to be declared: the shipped default is ``edit``, where the rule is
        # correctly off and this fixture would be asserting nothing.
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generated_markdown,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["last_error"] == ""
    assert runtime["state"]["processed_block_markdowns"] == [expected_markdown]
    assert runtime["state"]["processed_paragraph_registry"] == [
        {
            "block_index": 1,
            "paragraph_id": "p1",
            "text": expected_markdown,
            "controlled_fallback": True,
            "controlled_fallback_kind": expected_kind,
            "controlled_fallback_narration_excluded": expected_narration_excluded,
        }
    ]
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert {
        "status": "WARN",
        "details": f"controlled_fallback:{expected_kind}",
    } in [{"status": entry["status"], "details": entry.get("details")} for entry in runtime["log"]]

    artifact_path = Path(runtime["state"]["latest_controlled_block_fallback_artifact"])
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact_path.parent == block_execution.CONTROLLED_BLOCK_FALLBACK_DIR
    assert artifact_payload["output_classification"] == expected_kind
    assert artifact_payload["processed_chunk_preview"] == expected_markdown
    assert any(args[1] == "block_controlled_fallback" for args, _kwargs in events)


def test_run_document_processing_fails_controlled_fallback_when_paragraph_substrate_is_corrupted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runtime = _build_runtime_capture()
    events = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "# Заголовок\n\nЭто полноценный абзац с несколькими словами и знаками препинания.",
            "context_before": "",
            "context_after": "",
            "target_chars": 71,
            "context_chars": 0,
            "paragraph_ids": ["p1", "p2"],
        }],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "# Heading only",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "heading_only_output" in runtime["state"]["last_error"]
    assert "latest_controlled_block_fallback_artifact" not in runtime["state"]
    assert not any(args[1] == "block_controlled_fallback" for args, _kwargs in events)


def test_run_document_processing_continues_when_multiple_controlled_fallback_blocks_are_emitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # The family is RUN_DIR-derived, i.e. shared by the whole session; this test counts
    # every artifact in it, so it needs a directory of its own.
    fallback_dir = tmp_path / "block_fallbacks"
    monkeypatch.setattr(block_execution, "CONTROLLED_BLOCK_FALLBACK_DIR", fallback_dir)
    runtime = _build_runtime_capture()
    events = []
    # Spec 059 FR-A4: the ``english_residual_output`` block ("Суд Judgment #1 уже начался."
    # against an ordinary Russian source) left this fixture with the five-word detector that
    # produced it. The remaining four classes are the ones a classifier still emits.
    generated_outputs = iter([
        "   ",
        "# Heading only",
        "## ●",
        "Заключение ........ 29 Марка 13:13 Введение",
    ])

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "Исходный абзац сохранён как fallback.",
                "context_before": "",
                "context_after": "",
                "target_chars": 37,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
                # Spec 059 A-II / FR-A8: an empty answer substitutes the source, so a prose
                # block here would fail the run. This fixture is about the four fallback
                # classes travelling together, not about completeness.
                "paragraph_regions": ["back_matter"],
            },
            {
                "target_text": "# Заголовок\n\nЭто полноценный абзац с несколькими словами и знаками препинания.",
                "context_before": "",
                "context_after": "",
                "target_chars": 71,
                "context_chars": 0,
                "paragraph_ids": ["p3"],
            },
            {
                "target_text": "Этот абзац должен остаться обычным текстом, а не маркером списка.",
                "context_before": "",
                "context_after": "",
                "target_chars": 66,
                "context_chars": 0,
                "paragraph_ids": ["p4"],
            },
            {
                "target_text": "Содержание\n\nВведение ........ 1\n\nЗаключение ........ 29",
                "context_before": "",
                "context_after": "",
                "target_chars": 54,
                "context_chars": 0,
                "paragraph_ids": ["p5"],
            },
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: events.append((args, kwargs)),
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: next(generated_outputs),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    expected_kinds = [
        "empty_processed_block",
        "heading_only_output",
        "bullet_heading_output",
        "toc_body_concat",
    ]

    assert result == "succeeded"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert [entry["controlled_fallback_kind"] for entry in runtime["state"]["processed_paragraph_registry"]] == expected_kinds
    assert [args[1] for args, _kwargs in events].count("block_controlled_fallback") == 4
    artifact_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(fallback_dir.glob("report_docx_block_*.json"))
    ]
    assert [payload["output_classification"] for payload in artifact_payloads] == expected_kinds


@pytest.mark.parametrize(
    "rejection_kind",
    [
        "missing_provider_client",
        "missing_provider_configuration",
        "missing_source_segment",
        "missing_translated_segment",
        "final_translated_book_incomplete",
        "marker_registry_failure",
        "marker_anchor_failure",
        "invalid_processing_job",
        "corrupted_block",
        "source_extraction_failure",
    ],
)
def test_block_failure_classifier_keeps_hard_fail_classes_out_of_controlled_fallback(rejection_kind):
    payload = SimpleNamespace(
        job_kind="llm",
        paragraph_ids=["p1"],
        target_text="Исходный абзац.",
        target_text_with_markers="Исходный абзац.",
    )

    decision = block_execution.classify_processed_block_failure_decision(
        rejection_kind=rejection_kind,
        payload=payload,
        processed_chunk="Обработанный абзац.",
        build_processed_paragraph_registry_entries_fn=lambda **_kwargs: [
            {"paragraph_id": "p1", "text": "Обработанный абзац."}
        ],
    )

    assert decision == {"decision": "fail", "fallback_kind": rejection_kind}


def test_write_controlled_block_fallback_artifact_prunes_stale_family_by_count(tmp_path, monkeypatch):
    fallback_dir = tmp_path / "block_fallbacks"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(block_execution, "CONTROLLED_BLOCK_FALLBACK_DIR", fallback_dir)
    monkeypatch.setattr(block_execution, "BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT", 1)
    monkeypatch.setattr(block_execution, "BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS", 10_000)

    stale_path = fallback_dir / "report_docx_block_0_deadbeef.json"
    stale_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    artifact_path = block_execution._write_controlled_block_fallback_artifact(
        context=SimpleNamespace(uploaded_filename="report.docx"),
        initialization=SimpleNamespace(job_count=3),
        index=1,
        rejection_kind="english_residual_output",
        target_text="Source text",
        processed_chunk="Processed text",
    )

    assert artifact_path is not None
    new_path = Path(artifact_path)
    assert new_path.exists()
    assert not stale_path.exists()
    remaining = sorted(path.name for path in fallback_dir.glob("*.json"))
    assert remaining == [new_path.name]


def test_write_controlled_block_fallback_artifact_prunes_stale_family_by_age(tmp_path, monkeypatch):
    fallback_dir = tmp_path / "block_fallbacks"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(block_execution, "CONTROLLED_BLOCK_FALLBACK_DIR", fallback_dir)
    monkeypatch.setattr(block_execution, "BLOCK_FALLBACK_ARTIFACTS_MAX_COUNT", 1000)
    monkeypatch.setattr(block_execution, "BLOCK_FALLBACK_ARTIFACTS_MAX_AGE_SECONDS", 60)

    stale_path = fallback_dir / "report_docx_block_0_deadbeef.json"
    stale_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    os.utime(stale_path, (10.0, 10.0))

    artifact_path = block_execution._write_controlled_block_fallback_artifact(
        context=SimpleNamespace(uploaded_filename="report.docx"),
        initialization=SimpleNamespace(job_count=3),
        index=1,
        rejection_kind="english_residual_output",
        target_text="Source text",
        processed_chunk="Processed text",
    )

    assert artifact_path is not None
    assert Path(artifact_path).exists()
    assert not stale_path.exists()


def test_validate_translated_toc_block_accepts_translated_toc_lines():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents\n\nIntroduction ........ 1\n\nPart II ........ 83",
        processed_chunk="Содержание\n\nВведение ........ 1\n\nЧасть II ........ 83",
        structural_roles=["toc_header", "toc_entry", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is True


def test_validate_translated_toc_block_rejects_unchanged_header_and_entries():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
        processed_chunk="Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
        structural_roles=["toc_header", "toc_entry", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is False
    assert toc_result.reason == "unchanged_toc_header"


def test_is_page_reference_like_detects_numbers_and_delimiters_only():
    assert document_pipeline_output_validation._is_page_reference_like("xiv") is True
    assert document_pipeline_output_validation._is_page_reference_like("........") is True
    assert document_pipeline_output_validation._is_page_reference_like("Part II") is False


def test_has_page_reference_suffix_detects_suffix_and_rejects_plain_text():
    assert document_pipeline_output_validation._has_page_reference_suffix("Chapter 1 ........ 12") is True
    assert document_pipeline_output_validation._has_page_reference_suffix("Chapter 1") is False


def test_is_substantive_toc_line_rejects_page_reference_only_lines():
    assert document_pipeline_output_validation._is_substantive_toc_line("12") is False
    assert document_pipeline_output_validation._is_substantive_toc_line("........") is False
    assert document_pipeline_output_validation._is_substantive_toc_line("Introduction ........ 1") is True


def test_is_allowlisted_unchanged_toc_line_accepts_acronym_labels_but_not_contents():
    assert document_pipeline_output_validation._is_allowlisted_unchanged_toc_line("IMF", "IMF") is True
    assert document_pipeline_output_validation._is_allowlisted_unchanged_toc_line("UNESCO", "UNESCO") is True
    assert document_pipeline_output_validation._is_allowlisted_unchanged_toc_line("NASDAQ", "NASDAQ") is True
    assert document_pipeline_output_validation._is_allowlisted_unchanged_toc_line("Part II", "Part II") is False
    assert document_pipeline_output_validation._is_allowlisted_unchanged_toc_line("CONTENTS", "CONTENTS") is False


def test_validate_translated_toc_block_rejects_too_many_unchanged_entries():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Preface\n\nIntroduction ........ 1\n\nConclusion ........ 9\n\nAppendix ........ 14",
        processed_chunk="Предисловие\n\nIntroduction ........ 1\n\nConclusion ........ 9\n\nAppendix ........ 14",
        structural_roles=["toc_header", "toc_entry", "toc_entry", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is False
    assert toc_result.reason == "too_many_unchanged_toc_entries"


def test_validate_translated_toc_block_rejects_lost_page_markers():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents\n\nIntroduction ........ 1\n\nConclusion ........ 9",
        processed_chunk="Содержание\n\nВведение\n\nЗаключение",
        structural_roles=["toc_header", "toc_entry", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is False
    assert toc_result.reason == "lost_toc_page_markers"


def test_validate_translated_toc_block_rejects_empty_toc_block():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents",
        processed_chunk="   ",
        structural_roles=["toc_header"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is False
    assert toc_result.reason == "empty_toc_block"


def test_validate_translated_toc_block_rejects_paragraph_count_drift():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents\n\nIntroduction ........ 1",
        processed_chunk="Содержание",
        structural_roles=["toc_header", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is False
    assert toc_result.reason == "toc_paragraph_count_drift"


def test_validate_translated_toc_block_does_not_reject_when_only_two_substantive_entries_are_unchanged():
    toc_result = document_pipeline_output_validation.validate_translated_toc_block(
        source_text="Contents\n\nIntroduction ........ 1\n\n........\n\nConclusion ........ 9",
        processed_chunk="Содержание\n\nIntroduction ........ 1\n\n........\n\nConclusion ........ 9",
        structural_roles=["toc_header", "toc_entry", "toc_entry", "toc_entry"],
        source_language="en",
        target_language="ru",
    )

    assert toc_result.is_valid is True


def test_has_bullet_heading_output_detects_bullet_only_heading():
    assert document_pipeline_output_validation.has_bullet_heading_output("## ●") is True
    assert document_pipeline_output_validation.has_bullet_heading_output("## Раздел") is False


def test_has_toc_body_concat_signal_detects_toc_entry_merged_with_body():
    assert document_pipeline_output_validation.has_toc_body_concat_signal(
        target_text="Contents\n\nIntroduction ........ 1",
        processed_chunk="Содержание\n\nЗаключение ........ 29 Марка 13:13 Введение",
    ) is True


@pytest.mark.parametrize(
    ("processed_chunk", "expected"),
    [
        ("Содержание\n\nЗаключение ........ 29 Введение", True),
        ("Содержание\n\nЗаключение……29 Введение", True),
        ("Содержание\n\nЗаключение··29 Введение", True),
        ("Содержание\n\nЗаключение  29 Введение", True),
        ("Содержание\n\nЗаключение. 29\n\nВведение", False),
    ],
)
def test_has_toc_body_concat_markdown_handles_representative_leader_variants(processed_chunk, expected):
    assert document_pipeline_output_validation.has_toc_body_concat_markdown(processed_chunk) is expected


def test_has_toc_body_concat_signal_requires_source_toc_markers():
    assert document_pipeline_output_validation.has_toc_body_concat_signal(
        target_text="Обычный абзац без TOC",
        processed_chunk="Заключение........ 29 Введение",
    ) is False


# ``test_has_unexplained_english_residuals_detects_english_word_inside_cyrillic_output``
# lived here and is removed with the detector it covered (spec 059 FR-A4). Its replacement
# checks the OPPOSITE direction -- that the five-word list has not come back --
# in ``tests/test_spec_059_translation_completeness.py``.


# --- Spec 063, Codex acceptance finding 1: a trailing footnote reference ends a sentence --------
#
# FR-005 puts a lost reference back AFTER the sentence's terminal punctuation. Boundary
# recovery read "лавки.²⁰" as an unfinished sentence and welded it to the next paragraph;
# `_source_text_ends_sentence` read "chandlery.²⁰" the same way, so the spec 057 refusal could not
# step in. Replayed on the recorded Rethinking Money run, restoration created four new merges.

# The form of Rethinking Money p0526 / p0527 (block 73 of the 2026-11-07 run) in synthetic
# text: the PDF tears ("in de pen dent", the "fi" ligature split off a word), money
# amounts, two sentences, the reference after the last one.
_RM_P0526_SOURCE = (
    "A case in point: A survey designed to measure the harbour role played by in de pen dent "
    "boatmen on the busy Kelbrook North Quay showed that each $100 paid to a local fi sher "
    "keeps $71 in the Kelbrook harbour, whereas $100 paid at a chain chandlery keeps only $39 in "
    "Kelbrook. And for each square yard used by a local fi sher, the local harbour gain is "
    "$184, against $112 for a chain chandlery.²⁰"
)
_RM_P0526_TRANSLATION = (
    "Показательный пример: обследование, призванное измерить портовую роль независимых "
    "лодочников на оживлённой Северной пристани Келбрука, показало, что каждые 100 долларов, "
    "потраченные у местного рыбака, оставляют 71 доллар в гавани Келбрука, тогда как 100 "
    "долларов, потраченные в сетевой лавке, оставляют в городе лишь 39 долларов. Кроме того, "
    "на каждый квадратный ярд площади, занимаемой местным рыбаком, приходится 184 доллара "
    "портового эффекта, по сравнению со 112 долларами у сетевой лавки."
)
_RM_P0527_SOURCE = (
    "Tidals, by contrast, support coastally based trading, adding to the character and "
    "strength of each harbour."
)
_RM_P0527_TRANSLATION = (
    "Тайдалы, напротив, поддерживают прибрежную торговлю, добавляя своеобразия и силы каждой гавани."
)


def test_restored_footnote_reference_does_not_merge_rm_p0526_into_p0527():
    from docxaicorrector.pipeline.footnote_markers import restore_lost_footnote_markers

    restored = restore_lost_footnote_markers(_RM_P0526_SOURCE, _RM_P0526_TRANSLATION)
    assert restored.text.endswith("у сетевой лавки.²⁰")

    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[f"{restored.text}\n\n{_RM_P0527_TRANSLATION}"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "p0526", "text": restored.text},
            {"block_index": 1, "paragraph_id": "p0527", "text": _RM_P0527_TRANSLATION},
        ],
        source_paragraphs=[
            _make_paragraph_stub("p0526", 0, text=_RM_P0526_SOURCE),
            _make_paragraph_stub("p0527", 1, text=_RM_P0527_SOURCE),
        ],
    )

    assert [entry.merged_paragraph_ids for entry in result.entries] == [("p0526",), ("p0527",)]
    assert result.final_markdown == f"{restored.text}\n\n{_RM_P0527_TRANSLATION}"
    assert result.diagnostics.accepted_merges == 0
    assert result.entries[0].source_ends_sentence is True


def test_heading_after_a_paragraph_ending_in_a_footnote_reference_is_not_demoted():
    # Money and Sustainability p1342 / p1343 / p1344 (blocks 311 / 312 / 312 of the
    # 2026-11-07 run): "Appendices" was demoted and welded to its neighbours because
    # "…зажги его».¹⁷" read as an unfinished sentence across the block boundary.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=[
            "У моряков есть похожая поговорка: если в День бури у тебя в руке фитиль фонаря, зажги его».¹⁷",
            "## Приложения\n\nДальнейшие приложения размещены онлайн по адресу *tid.ly/HBharbourlink*",
        ],
        generated_paragraph_registry=[
            {
                "block_index": 1,
                "paragraph_id": "p1342",
                "text": "У моряков есть похожая поговорка: если в День бури у тебя в руке фитиль фонаря, зажги его».¹⁷",
            },
            {"block_index": 2, "paragraph_id": "p1343", "text": "## Приложения"},
            {
                "block_index": 2,
                "paragraph_id": "p1344",
                "text": "Дальнейшие приложения размещены онлайн по адресу *tid.ly/HBharbourlink*",
            },
        ],
        source_paragraphs=[
            _make_paragraph_stub(
                "p1342",
                0,
                text="Sailors have a similar saying: if you have a lantern wick in your hand on Storm Day, light the wick.”¹⁷",
            ),
            _make_paragraph_stub("p1343", 1, role="heading", structural_role="heading", heading_level=2, text="Appendices"),
            _make_paragraph_stub(
                "p1344", 2, text="The further appendices are posted online at *tid.ly/HBharbourlink*"
            ),
        ],
    )

    assert [entry.merged_paragraph_ids for entry in result.entries] == [("p1342",), ("p1343",), ("p1344",)]
    assert "\n\n## Приложения\n\n" in result.final_markdown
    assert result.diagnostics.demoted_false_headings == 0


@pytest.mark.parametrize(
    ("source_text", "expected"),
    [
        ("…against $112 for a chain chandlery.²⁰", True),
        ("…light the wick.”¹⁷", True),
        ("…for the first time.¹²,¹³", True),
        ("**…the end of the chapter.³⁴**", True),
        # Anti-vacuum: a trailing PLAIN number is not a reference by form.
        ("…against $112 for a chain chandlery.20", False),
        ("…founded in a Kelbrook boathouse in 1976", False),
        ("The area is 40 m²", False),
    ],
)
def test_source_text_ends_sentence_reads_through_trailing_superscript_references(source_text, expected):
    assert document_pipeline_output_validation._source_text_ends_sentence(source_text) is expected


def test_translation_ending_in_a_bare_number_still_reads_as_unfinished():
    # Anti-vacuum for the translation side: only superscript GLYPHS after terminal
    # punctuation close a sentence; "в 1976" and "магазина.20" do not.
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Компания была основана в келбрукском эллинге в 1976\n\nи быстро выросла"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "left", "text": "Компания была основана в келбрукском эллинге в 1976"},
            {"block_index": 1, "paragraph_id": "right", "text": "и быстро выросла"},
        ],
        source_paragraphs=None,
    )

    assert result.final_markdown == "Компания была основана в келбрукском эллинге в 1976 и быстро выросла"
    assert document_pipeline_output_validation._SENTENCE_TERMINAL_PATTERN.search("у сетевой лавки.20") is None
    assert document_pipeline_output_validation._SENTENCE_TERMINAL_PATTERN.search("у сетевой лавки.²⁰") is not None


# --- Spec 063 P0: replay of the list-fragment carry on recorded translate runs ---------------
#
# Opt-in evidence, not a CI test: the recorded run reports (21-98 MB each) and the re-derived
# full-text source paragraphs live OUTSIDE the repository. Point
# ``DOCXAI_TRANSLATE_REPLAY_ROOT`` at a directory holding ``<book>/<report>.json`` and
# ``<book>/source_paragraphs.json`` (the 2026-11-07 four-book translate run); without it, or
# with a book missing, the test skips.
#
# For each book it feeds the run's own ``processed_block_markdowns`` and
# ``processed_paragraph_registry`` into the PRODUCTION ``assemble_final_markdown`` and checks
# that the carry only MOVES number tokens (same multiset of numbers as the same assembly with
# the carry switched off, no new double leading ordinal), and that the never-merged
# paragraphs differ from the model's text in at most the residue the 2026-11-07 diagnosis
# measured for the source-aware rule (1 / 0 / 0 / 3), down from the 10 / 24 / 87 / 100 that
# shipped.
_TRANSLATE_REPLAY_ROOT_ENV = "DOCXAI_TRANSLATE_REPLAY_ROOT"
_TRANSLATE_REPLAY_ROOT = os.environ.get(_TRANSLATE_REPLAY_ROOT_ENV, "").strip()
# (book directory, report file, shipped never-merged drift on 2026-11-07, allowed residue)
_TRANSLATE_REPLAY_BOOKS = [
    ("money_sustainability", "money_sustainability_pdf_full_heldout_report.json", 10, 1),
    ("creating_wealth", "creatingwealth_pdf_full_benchmark_report.json", 24, 0),
    ("rethinking_money", "lietaer_pdf_full_benchmark_report.json", 87, 0),
    ("value_of_everything", "mazzucato_pdf_full_benchmark_report.json", 100, 3),
]


def _never_merged_drift(registry, model_text_by_id):
    return [
        entry["paragraph_id"]
        for entry in registry
        if len(entry.get("merged_paragraph_ids") or []) <= 1
        and model_text_by_id.get(entry["paragraph_id"]) != entry["text"]
    ]


@pytest.mark.skipif(
    not _TRANSLATE_REPLAY_ROOT,
    reason=f"Set {_TRANSLATE_REPLAY_ROOT_ENV} to the recorded translate-run directory to replay the list-fragment carry.",
)
@pytest.mark.parametrize(
    ("book", "report_name", "shipped_drift", "allowed_drift"),
    _TRANSLATE_REPLAY_BOOKS,
    ids=[book[0] for book in _TRANSLATE_REPLAY_BOOKS],
)
def test_list_fragment_carry_replay_on_recorded_translate_runs(monkeypatch, book, report_name, shipped_drift, allowed_drift):
    book_dir = Path(_TRANSLATE_REPLAY_ROOT) / book
    report_path = book_dir / report_name
    source_path = book_dir / "source_paragraphs.json"
    if not report_path.is_file() or not source_path.is_file():
        pytest.skip(f"recorded run for {book} is absent under {book_dir}")

    with report_path.open(encoding="utf-8") as handle:
        state = json.load(handle)["runtime"]["state"]
    with source_path.open(encoding="utf-8") as handle:
        source_records = json.load(handle)["paragraphs"]
    source_paragraphs = [
        SimpleNamespace(**{**record, "boundary_source": None, "boundary_confidence": None}) for record in source_records
    ]
    chunks = state["processed_block_markdowns"]
    processed_registry = state["processed_paragraph_registry"]
    model_text_by_id = {entry["paragraph_id"]: entry.get("text") for entry in processed_registry}
    # The recorded run is the one the diagnosis measured.
    assert len(_never_merged_drift(state["final_generated_paragraph_registry"], model_text_by_id)) == shipped_drift
    del state

    def assemble():
        return document_pipeline_output_validation.assemble_final_markdown(
            processed_chunks=chunks,
            generated_paragraph_registry=processed_registry,
            source_paragraphs=source_paragraphs,
        )

    result = assemble()
    registry = document_pipeline_output_validation.build_generated_paragraph_registry_from_entries(result.entries)
    with monkeypatch.context() as patch:
        patch.setattr(
            document_pipeline_output_validation,
            "_normalize_final_entry_list_fragments",
            lambda entries, source_text_by_id=None: tuple(entries),
        )
        without_carry = assemble()

    drift = _never_merged_drift(registry, model_text_by_id)
    # The markdown twin behind the delivered DOCX, run on this assembly's output with the
    # protected headings the late phase gives it. It has no source to consult.
    display = document_pipeline_output_validation.normalize_list_fragment_regressions_markdown(
        result.final_markdown,
        protected_heading_texts=late_phases._registry_protected_heading_texts(registry),
    )
    print(
        json.dumps(
            {
                "book": book,
                "never_merged_drift_shipped": shipped_drift,
                "never_merged_drift_replayed": len(drift),
                "drift_ids": drift[:10],
                "entries_rewritten_by_carry": sum(
                    1 for left, right in zip(result.entries, without_carry.entries) if left.text != right.text
                ),
                "display_twin_lines_changed": sum(
                    1
                    for left, right in zip(result.final_markdown.splitlines(), display.splitlines())
                    if left != right
                ),
            },
            ensure_ascii=False,
        )
    )

    numbers = Counter(_NUMBER_TOKEN_PATTERN.findall(result.final_markdown))
    numbers_without_carry = Counter(_NUMBER_TOKEN_PATTERN.findall(without_carry.final_markdown))
    assert numbers == numbers_without_carry, {
        "created": dict(numbers - numbers_without_carry),
        "deleted": dict(numbers_without_carry - numbers),
    }
    assert Counter(_NUMBER_TOKEN_PATTERN.findall(display)) == numbers
    stacked = {entry.paragraph_id for entry in result.entries if _STACKED_LEADING_ORDINALS_PATTERN.match(entry.text)}
    stacked_without_carry = {
        entry.paragraph_id
        for entry in without_carry.entries
        if _STACKED_LEADING_ORDINALS_PATTERN.match(entry.text)
    }
    assert stacked <= stacked_without_carry
    assert len(drift) <= allowed_drift


@pytest.mark.skipif(
    not _TRANSLATE_REPLAY_ROOT,
    reason=f"Set {_TRANSLATE_REPLAY_ROOT_ENV} to the recorded translate-run directory to replay FR-005 + assembly.",
)
@pytest.mark.parametrize(
    ("book", "report_name", "shipped_drift", "allowed_drift"),
    _TRANSLATE_REPLAY_BOOKS,
    ids=[book[0] for book in _TRANSLATE_REPLAY_BOOKS],
)
def test_footnote_restoration_then_assembly_replay_moves_no_boundary(book, report_name, shipped_drift, allowed_drift):
    # Codex acceptance finding 1 (spec 063): the replay above assembles the model's text as
    # it was recorded, BEFORE FR-005 existed, so it could not see a restored reference turn a
    # complete paragraph into an "unfinished" one. Here the production restoration runs on
    # every accepted paragraph first, exactly as ``process_single_block`` does, and the
    # assembly must merge and demote exactly what it does without it. Measured before the
    # fix: four new merges on Rethinking Money (p0164+p0165, p0520+p0521, p0526+p0527,
    # p0529+p0530), none on the other three books.
    from docxaicorrector.pipeline.footnote_markers import restore_lost_footnote_markers

    book_dir = Path(_TRANSLATE_REPLAY_ROOT) / book
    report_path = book_dir / report_name
    source_path = book_dir / "source_paragraphs.json"
    if not report_path.is_file() or not source_path.is_file():
        pytest.skip(f"recorded run for {book} is absent under {book_dir}")

    with report_path.open(encoding="utf-8") as handle:
        state = json.load(handle)["runtime"]["state"]
    with source_path.open(encoding="utf-8") as handle:
        source_records = json.load(handle)["paragraphs"]
    source_text_by_id = {record["paragraph_id"]: record["text"] for record in source_records}
    source_paragraphs = [
        SimpleNamespace(**{**record, "boundary_source": None, "boundary_confidence": None}) for record in source_records
    ]
    chunks = list(state["processed_block_markdowns"])
    registry = state["processed_paragraph_registry"]
    del state

    restored_chunks = list(chunks)
    restored_registry = []
    restored_ids = []
    converted_digits: Counter = Counter()
    for entry in registry:
        restored_entry = dict(entry)
        source_text = source_text_by_id.get(entry.get("paragraph_id"))
        text = entry.get("text")
        if source_text is not None and entry.get("paragraph_status", "accepted") == "accepted" and isinstance(text, str):
            outcome = restore_lost_footnote_markers(source_text, text)
            block_position = int(entry["block_index"]) - 1
            if outcome.restored_markers and text in restored_chunks[block_position]:
                restored_chunks[block_position] = restored_chunks[block_position].replace(text, outcome.text, 1)
                restored_entry["text"] = outcome.text
                restored_ids.append(entry["paragraph_id"])
                if "converted" in outcome.placement:
                    converted_digits.update(
                        marker.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
                        for marker in outcome.restored_markers
                    )
        restored_registry.append(restored_entry)
    assert restored_ids, "anti-vacuum: the recorded run must contain paragraphs FR-005 restores"

    def shape(result):
        merges = {entry.merged_paragraph_ids for entry in result.entries if len(entry.merged_paragraph_ids) > 1}
        demoted = {
            decision.paragraph_ids
            for decision in result.diagnostics.merge_decisions
            if decision.action == "demote_heading"
        }
        return merges, demoted

    plain = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=chunks, generated_paragraph_registry=registry, source_paragraphs=source_paragraphs
    )
    restored = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=restored_chunks,
        generated_paragraph_registry=restored_registry,
        source_paragraphs=source_paragraphs,
    )
    plain_merges, plain_demoted = shape(plain)
    restored_merges, restored_demoted = shape(restored)
    print(json.dumps({"book": book, "restored_paragraphs": len(restored_ids), "merges": len(restored_merges)}))

    assert restored_merges == plain_merges, {
        "new": sorted(restored_merges - plain_merges),
        "gone": sorted(plain_merges - restored_merges),
    }
    assert restored_demoted == plain_demoted
    # Restoration creates no plain number. The only plain digits it removes are the model's
    # plain-digit copies of a reference it turned back into the glyph (Money p0458 "»34.").
    plain_numbers = Counter(_NUMBER_TOKEN_PATTERN.findall(plain.final_markdown))
    restored_numbers = Counter(_NUMBER_TOKEN_PATTERN.findall(restored.final_markdown))
    assert not restored_numbers - plain_numbers
    assert not (plain_numbers - restored_numbers) - converted_digits


# --- Spec 065 FR-006: a parenthetical meta-comment about structure, by form -------------------
#
# Synthetic texts only (Constitution VII): the rule reads the form of the answer and what it
# shares with its own source, so no sentence of a corpus book is needed to exercise it.

_META_SOURCE_TAIL = "Grant (Oxford: Harbour Press, 1971), p. 42."


@pytest.mark.parametrize(
    ("answer", "source", "comment"),
    [
        pytest.param(
            "(Продолжение примечания 10)", _META_SOURCE_TAIL, "(Продолжение примечания 10)", id="spans-with-a-number"
        ),
        pytest.param(
            "(Продолжение названия книги): *Harbour Studies* (Oxford: Harbour Press, 1971), с. 42.",
            "*Studies* (Oxford: Harbour Press, 1971), p. 42.",
            "(Продолжение названия книги)",
            id="opens-and-is-followed-by-a-colon",
        ),
        pytest.param(
            "### (Окончание записи 7)", "### Harbour Press, 1971", "(Окончание записи 7)", id="behind-a-heading-prefix"
        ),
        pytest.param("*(См.: запись выше)*", _META_SOURCE_TAIL, "(См.: запись выше)", id="emphasised-with-a-colon"),
    ],
)
def test_structural_meta_comment_is_recognised_by_form(answer: str, source: str, comment: str) -> None:
    assert document_pipeline_output_validation.structural_meta_comment(answer, source) == comment


@pytest.mark.parametrize(
    ("answer", "source"),
    [
        # Anti-regression 3 (spec 065): an author's parenthetical INSIDE a paragraph is prose.
        pytest.param(
            "Он вернулся к рукописи (Продолжение следует в главе 10) и закончил её к утру.",
            "He went back to the manuscript (to be continued in chapter 10) and finished it by morning.",
            id="authors-parenthetical-inside-a-paragraph",
        ),
        # Anti-regression 3: a short parenthetical paragraph that TRANSLATES its source shares
        # the source's number, so it is the author's, not the model's.
        pytest.param("(См. главу 3.)", "See chapter 3.", id="translation-shares-the-number"),
        pytest.param("(Источник: Harbour Press)", "Source: Harbour Press", id="translation-shares-a-name"),
        # The author's own parenthetical paragraph is translated into one.
        pytest.param("(Источник: Всемирный банк.)", "(Source: World Bank.)", id="source-opens-with-a-parenthetical"),
        pytest.param("(Смех.)", "Laughter.", id="no-number-and-no-colon"),
        pytest.param("(продолжение примечания 10)", _META_SOURCE_TAIL, id="lowercase-first-word"),
        pytest.param(
            "(Это замечание автора о совсем другой и долгой истории 10)", _META_SOURCE_TAIL, id="longer-than-a-label"
        ),
        pytest.param("(Продолжение примечания 10) и далее по тексту.", _META_SOURCE_TAIL, id="no-colon-after-an-opener"),
        pytest.param("Грант (Оксфорд: Harbour Press, 1971), с. 42.", _META_SOURCE_TAIL, id="an-ordinary-translation"),
    ],
)
def test_structural_meta_comment_keeps_what_is_not_one(answer: str, source: str) -> None:
    assert document_pipeline_output_validation.structural_meta_comment(answer, source) is None
