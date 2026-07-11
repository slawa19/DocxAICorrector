import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
    return {"state": {}, "finalize": [], "activity": [], "log": [], "status": []}


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _emit_finalize(runtime, stage, detail, progress, terminal_kind=None):
    runtime.setdefault("finalize", []).append((stage, detail, progress, terminal_kind))


def _emit_activity(runtime, message):
    runtime.setdefault("activity", []).append(message)


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
        emit_activity=_emit_activity,
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
        emit_activity=_emit_activity,
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
    assert runtime["activity"][-1] == "Блок 1: отклонён структурно недостаточный Markdown."
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
        emit_activity=_emit_activity,
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

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "# Heading only"
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
        emit_activity=_emit_activity,
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
        emit_activity=_emit_activity,
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
        emit_activity=_emit_activity,
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


def test_collect_false_fragment_heading_samples_detects_inline_heading_and_scripture_reference():
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
        "scripture_reference_heading_present",
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
            text_preview="this scenario has been repeated for every one of the large-scale banking crises and monetary",
        ),
        _paragraph_break_entry(
            source_index=219,
            origin_raw_indexes=[220],
            text_preview="meltdowns of our times.",
        ),
    ]

    samples = document_pipeline_output_validation.collect_paragraph_break_samples(registry)

    assert len(samples) == 1
    assert samples[0].source_index == 219
    assert samples[0].text.endswith("monetary")
    assert samples[0].next_text.startswith("meltdowns")


def test_collect_paragraph_break_samples_ignores_boundary_without_shared_source_signal():
    # (b) Same mid-sentence form but the two entries are separate source paragraphs
    # (distinct raw blocks) → NOT flagged. No source signal, no flag (FR-002).
    registry = [
        _paragraph_break_entry(
            source_index=1381,
            origin_raw_indexes=[1431],
            text_preview="edward abbey: the second rape of the west (chicago",
        ),
        _paragraph_break_entry(
            source_index=1382,
            origin_raw_indexes=[1432],
            text_preview="mani arnarson, atli bjarnason",
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
            text_preview="identifying structural issues",
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
            text_preview="proposals for nine different pragmatic monetary complements",
            role="list",
            structural_role="list",
            list_kind="unordered",
        ),
        _paragraph_break_entry(
            source_index=119,
            origin_raw_indexes=[119],
            text_preview="to the current financial system",
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
        "23. (*http://chicagoinspectorgeneral.org*). 42* www.bloomberg.com 24.\n\n"
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
    markdown = "This page intentionally left blank Chapter Nine STRATEGIES FOR NGO S"

    normalized = document_pipeline_output_validation.normalize_page_placeholder_heading_concats_markdown(markdown)

    assert normalized == "This page intentionally left blank\n\nChapter Nine STRATEGIES FOR NGO S"


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


def test_collect_theology_style_issue_samples_detects_awkward_headings_and_glossary_terms():
    markdown = (
        "## Суд над пятым печатью\n\n"
        "## Четвёртое чашеобразное судилище\n\n"
        "Создавайте кoinonia-сообщества и богословие imago Dei."
    )

    samples = document_pipeline_output_validation.collect_theology_style_issue_samples(markdown)

    reasons = [sample.reason for sample in samples]
    assert "awkward_judgment_heading_present" in reasons
    assert "unresolved_glossary_term_present" in reasons
    assert "mixed_script_term_present" not in reasons


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


def test_assemble_final_markdown_preserves_index_page_reference_fragment_boundary():
    result = document_pipeline_output_validation.assemble_final_markdown(
        processed_chunks=["Local Capital Project, 128– 130\n\n179– 180"],
        generated_paragraph_registry=[
            {"block_index": 1, "paragraph_id": "index-left", "text": "Local Capital Project, 128– 130"},
            {"block_index": 1, "paragraph_id": "index-right", "text": "179– 180"},
        ],
        source_paragraphs=[
            _make_paragraph_stub("index-left", 0),
            _make_paragraph_stub("index-right", 1),
        ],
    )

    assert result.final_markdown == "Local Capital Project, 128– 130\n\n179– 180"
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
            _make_paragraph_stub("intro", 0),
            _make_paragraph_stub("item-1", 1),
            _make_paragraph_stub("item-2", 2),
            _make_paragraph_stub("item-3", 3),
        ],
    )

    assert result.entries[0].text == "Сатана-Дьявол пытается воспроизвести Троицу:"
    assert result.entries[1].text == "1. Обвинитель-Противник"
    assert result.entries[2].text == "2. Звероподобная сущность Антихриста"
    assert result.entries[3].text == "3. Вторая сущность — зверь/лжепророк."


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
        source_paragraphs=[
            _make_paragraph_stub("item-5", 0),
            _make_paragraph_stub("heading-6", 1, role="heading", structural_role="heading", heading_level=2),
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


def test_assemble_final_markdown_preserves_source_backed_scripture_heading():
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


def test_collect_false_fragment_heading_samples_skips_canonical_judgment_heading():
    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(
        "2/3.) Семь трубных судов\n\n## Суд над трубой #1 (Откровение 8:7):\n\nГрад и огонь падают на землю."
    )

    assert samples == []


def test_collect_false_fragment_heading_samples_flags_parenthetical_question_tail_heading():
    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(
        "Кометы? Астероиды?\n\n## Спутники? Ракеты?)\n\nТреть земли будет сожжена."
    )

    assert [sample.reason for sample in samples] == ["sentence_split_heading_present"]
    assert samples[0].text == "## Спутники? Ракеты?)"


def test_collect_false_fragment_heading_samples_from_entries_preserves_source_backed_scripture_heading():
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
            "# Бернар Лиетар и Джеки Данн",
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
            {"block_index": 6, "paragraph_id": "authors", "text": "# Бернар Лиетар и Джеки Данн"},
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
        emit_activity=_emit_activity,
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
        emit_activity=_emit_activity,
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
    assert runtime["activity"][-1] == "Блок 1: отклонён из-за bullet heading в результате."


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
        emit_activity=_emit_activity,
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
    assert runtime["activity"][-1] == "Блок 1: отклонён из-за склейки TOC и body."


def test_run_document_processing_continues_on_english_residual_output_controlled_fallback(tmp_path, monkeypatch):
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
        emit_activity=_emit_activity,
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
    assert runtime["state"]["processed_paragraph_registry"] == [
        {
            "block_index": 1,
            "paragraph_id": "p1",
            "text": "Суд Judgment #1 уже начался.",
            "controlled_fallback": True,
            "controlled_fallback_kind": "english_residual_output",
        }
    ]
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert "Блок 1: сохранён с controlled fallback (english_residual_output)." in runtime["activity"]
    assert {
        "status": "WARN",
        "details": "controlled_fallback:english_residual_output",
    } in [{"status": entry["status"], "details": entry.get("details")} for entry in runtime["log"]]

    artifact_path = Path(runtime["state"]["latest_controlled_block_fallback_artifact"])
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact_path.parent == Path(".run") / "block_fallbacks"
    assert artifact_payload["output_classification"] == "english_residual_output"
    assert artifact_payload["processed_chunk_preview"] == "Суд Judgment #1 уже начался."
    assert any(args[1] == "block_controlled_fallback" for args, _kwargs in events)


@pytest.mark.parametrize(
    ("job", "generated_markdown", "expected_kind", "expected_markdown"),
    [
        (
            {
                "target_text": "Исходный абзац сохранён как fallback.",
                "context_before": "",
                "context_after": "",
                "target_chars": 37,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
            },
            "   ",
            "empty_processed_block",
            "Исходный абзац сохранён как fallback.",
        ),
        (
            {
                "target_text": "Первый абзац с нормальным содержанием.",
                "context_before": "",
                "context_after": "",
                "target_chars": 36,
                "context_chars": 0,
                "paragraph_ids": ["p1"],
            },
            "Суд Judgment #1 уже начался.",
            "english_residual_output",
            "Суд Judgment #1 уже начался.",
        ),
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
        emit_activity=_emit_activity,
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
        }
    ]
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert f"Блок 1: сохранён с controlled fallback ({expected_kind})." in runtime["activity"]
    assert {
        "status": "WARN",
        "details": f"controlled_fallback:{expected_kind}",
    } in [{"status": entry["status"], "details": entry.get("details")} for entry in runtime["log"]]

    artifact_path = Path(runtime["state"]["latest_controlled_block_fallback_artifact"])
    artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact_path.parent == Path(".run") / "block_fallbacks"
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
        emit_activity=_emit_activity,
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
    runtime = _build_runtime_capture()
    events = []
    generated_outputs = iter([
        "   ",
        "Суд Judgment #1 уже начался.",
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
            },
            {
                "target_text": "Первый абзац с нормальным содержанием.",
                "context_before": "",
                "context_after": "",
                "target_chars": 36,
                "context_chars": 0,
                "paragraph_ids": ["p2"],
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
        emit_activity=_emit_activity,
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
        "english_residual_output",
        "heading_only_output",
        "bullet_heading_output",
        "toc_body_concat",
    ]

    assert result == "succeeded"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert [entry["controlled_fallback_kind"] for entry in runtime["state"]["processed_paragraph_registry"]] == expected_kinds
    assert [args[1] for args, _kwargs in events].count("block_controlled_fallback") == 5
    artifact_payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((Path(".run") / "block_fallbacks").glob("report_docx_block_*.json"))
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


def test_has_unexplained_english_residuals_detects_english_word_inside_cyrillic_output():
    assert document_pipeline_output_validation.has_unexplained_english_residuals("Суд Judgment #1 уже начался.") is True
    assert document_pipeline_output_validation.has_unexplained_english_residuals("Полностью русский абзац без остатков.") is False
