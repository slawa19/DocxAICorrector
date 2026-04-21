import document_pipeline


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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Часть II: Примеры дополнительных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"


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
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_markdown"] == "## Развитие местных экономик с помощью местных валют"
    assert runtime["state"]["latest_docx_bytes"] == b"docx-bytes"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"