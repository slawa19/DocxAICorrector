import pytest

import document_pipeline
import document_pipeline_output_validation


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


def test_collect_false_fragment_heading_samples_detects_dangling_question_fragment_heading():
    markdown = "Это обсуждение подводит к вопросу\n\n## Спутники? Ракеты?)\n\nкоторый дальше раскрывается в тексте."

    samples = document_pipeline_output_validation.collect_false_fragment_heading_samples(markdown)

    assert len(samples) == 1
    assert samples[0].reason == "sentence_split_heading_present"


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


def test_run_document_processing_rejects_english_residual_output():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{
            "target_text": "Первый абзац с нормальным содержанием.",
            "context_before": "",
            "context_after": "",
            "target_chars": 36,
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
        generate_markdown_block=lambda **kwargs: "Суд Judgment #1 уже начался.",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert "english_residual_output" in runtime["state"]["last_error"]
    assert runtime["activity"][-1] == "Блок 1: отклонён из-за английских остатков в результате."


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
