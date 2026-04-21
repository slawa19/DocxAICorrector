from io import BytesIO

import document_pipeline


class AssetStub:
    def __init__(self, image_id: str):
        self.image_id = image_id
        self.placeholder_status = None

    def update_pipeline_metadata(self, **values):
        self.placeholder_status = values.get("placeholder_status")


class PlannedJobs:
    def __init__(self, jobs, *, planned_len: int):
        self._jobs = list(jobs)
        self._planned_len = planned_len

    def __iter__(self):
        return iter(self._jobs)

    def __len__(self):
        return self._planned_len


class ParagraphStub:
    role = "body"


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


def _run_processing(runtime, **overrides):
    params = {
        "uploaded_file": "report.docx",
        "jobs": [{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        "source_paragraphs": [],
        "image_assets": [],
        "image_mode": "safe",
        "app_config": {},
        "model": "gpt-5.4",
        "max_retries": 1,
        "on_progress": lambda **kwargs: None,
        "runtime": runtime,
        "resolve_uploaded_filename": lambda uploaded_file: str(uploaded_file),
        "get_client": lambda: object(),
        "ensure_pandoc_available": lambda: None,
        "load_system_prompt": lambda **_kw: "system",
        "log_event": lambda *args, **kwargs: None,
        "present_error": lambda code, exc, title, **kwargs: f"{title}: {exc}",
        "emit_state": _emit_state,
        "emit_finalize": _emit_finalize,
        "emit_activity": _emit_activity,
        "emit_log": _emit_log,
        "emit_status": _emit_status,
        "should_stop_processing": lambda runtime: False,
        "generate_markdown_block": lambda **kwargs: "Обработанный блок",
        "process_document_images": lambda **kwargs: [],
        "inspect_placeholder_integrity": _inspect_placeholder_integrity,
        "convert_markdown_to_docx_bytes": _convert_markdown_to_docx_bytes,
        "preserve_source_paragraph_properties": lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        "normalize_semantic_output_docx": lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        "reinsert_inline_images": _reinsert_inline_images,
        "write_ui_result_artifacts": lambda **kwargs: {"markdown_path": "/tmp/final.result.md", "docx_path": "/tmp/final.result.docx"},
    }
    params.update(overrides)
    return document_pipeline.run_document_processing(**params)


def test_run_document_processing_fails_on_empty_processing_plan():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[],
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
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["processed_block_markdowns"] == []
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка подготовки обработки: План обработки документа пуст."
    assert runtime["finalize"][-1] == (
        "Ошибка подготовки обработки",
        "Ошибка подготовки обработки: План обработки документа пуст.",
        0.0,
        "error",
    )
    assert runtime["activity"][-1] == "Обработка документа остановлена: не найдено ни одного блока для обработки."
    assert runtime["log"][-1]["status"] == "ERROR"
    assert runtime["log"][-1]["block_count"] == 0


def test_run_document_processing_fails_on_initialization_and_clears_stale_runtime_state():
    runtime = _build_runtime_capture()
    runtime["state"].update(
        {
            "latest_docx_bytes": b"stale-docx",
            "latest_markdown": "stale-markdown",
            "processed_block_markdowns": ["stale-block"],
        }
    )

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
        ensure_pandoc_available=lambda **_kw: (_ for _ in ()).throw(RuntimeError("pandoc is unavailable")),
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["processed_block_markdowns"] == []
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка инициализации обработки: pandoc is unavailable"
    assert runtime["finalize"][-1] == (
        "Ошибка инициализации",
        "Ошибка инициализации обработки: pandoc is unavailable",
        0.0,
        "error",
    )


def test_run_document_processing_fails_when_process_document_images_raises():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
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
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("image pipeline exploded")),
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка обработки изображений: image pipeline exploded"
    assert runtime["finalize"][-1] == (
        "Ошибка обработки изображений",
        "Ошибка обработки изображений: image pipeline exploded",
        1.0,
        "error",
    )
    assert runtime["activity"][-1] == "Ошибка на этапе обработки изображений документа."
    assert runtime["log"][-1]["status"] == "ERROR"
    assert runtime["log"][-1]["block_index"] == 1


def test_run_document_processing_fails_when_process_document_images_returns_none():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
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
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: None,
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"] == (
        "Ошибка обработки изображений: Пайплайн обработки изображений вернул None вместо коллекции ассетов."
    )
    assert runtime["finalize"][-1][0] == "Ошибка обработки изображений"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_placeholder_integrity_check_raises():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=[AssetStub("img_001")],
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
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [AssetStub("img_001")],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: (_ for _ in ()).throw(RuntimeError("placeholder integrity exploded")),
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["last_error"] == "Ошибка обработки изображений: placeholder integrity exploded"
    assert runtime["finalize"][-1][0] == "Ошибка обработки изображений"
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_on_invalid_job_shape():
    runtime = _build_runtime_capture()
    runtime["state"]["latest_docx_bytes"] = b"stale-docx"

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "context_chars": 0}],
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
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == ""
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка на блоке 1: Ошибка подготовки блока: 'target_chars'"
    assert runtime["finalize"][-1] == (
        "Ошибка подготовки блока",
        "Ошибка на блоке 1: Ошибка подготовки блока: 'target_chars'",
        0.0,
        "error",
    )
    assert runtime["activity"][-1] == "Блок 1: некорректный план обработки."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_on_none_target_text_without_stringifying_none():
    runtime = _build_runtime_capture()

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": None, "context_before": "", "context_after": "", "target_chars": 0, "context_chars": 0}],
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
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"] == "Ошибка на блоке 1: Ошибка подготовки блока: target_text is None"


def test_run_document_processing_fails_on_missing_placeholder_status_entries():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=image_assets,
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
        generate_markdown_block=lambda **kwargs: "[[DOCX_IMAGE_img_001]]",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["state"]["last_error"].startswith("Критическая ошибка подготовки изображений")


def test_run_document_processing_preserves_passthrough_image_block_without_openai_call():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]
    generate_calls = []
    inspected_markdowns = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"job_kind": "llm", "target_text": "Вступление", "context_before": "", "context_after": "", "target_chars": 10, "context_chars": 0},
            {"job_kind": "passthrough", "target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0},
            {"job_kind": "llm", "target_text": "Основной текст", "context_before": "", "context_after": "", "target_chars": 14, "context_chars": 0},
        ],
        source_paragraphs=[],
        image_assets=image_assets,
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
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs["target_text"]) or f"ok:{kwargs['target_text']}",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: inspected_markdowns.append(markdown_text) or {asset.image_id: "ok" for asset in image_assets},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls == ["Вступление", "Основной текст"]
    assert inspected_markdowns == ["ok:Вступление\n\n[[DOCX_IMAGE_img_001]]\n\nok:Основной текст"]
    assert runtime["state"]["latest_markdown"] == "ok:Вступление\n\n[[DOCX_IMAGE_img_001]]\n\nok:Основной текст"


def test_run_document_processing_passthrough_only_does_not_require_system_prompt():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]
    generate_calls = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"job_kind": "passthrough", "target_text": "[[DOCX_IMAGE_img_001]]", "context_before": "", "context_after": "", "target_chars": 21, "context_chars": 0},
        ],
        source_paragraphs=[],
        image_assets=image_assets,
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: (_ for _ in ()).throw(RuntimeError("prompt exploded")),
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: generate_calls.append(kwargs["target_text"]) or "unexpected",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {asset.image_id: "ok" for asset in image_assets},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "succeeded"
    assert generate_calls == []
    assert runtime["state"]["latest_markdown"] == "[[DOCX_IMAGE_img_001]]"


def test_run_document_processing_detects_processed_block_count_mismatch():
    runtime = _build_runtime_capture()
    jobs = PlannedJobs(
        [{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        planned_len=2,
    )

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=jobs,
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
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=_inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=_convert_markdown_to_docx_bytes,
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=_reinsert_inline_images,
    )

    assert result == "failed"
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["activity"][-1] == "Обнаружено несоответствие количества обработанных блоков."


def test_run_document_processing_fails_when_convert_markdown_to_docx_bytes_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        convert_markdown_to_docx_bytes=lambda markdown_text: (_ for _ in ()).throw(RuntimeError("convert exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: convert exploded"
    assert runtime["finalize"][-1] == ("Ошибка сборки DOCX", "Ошибка сборки DOCX: convert exploded", 1.0, "error")
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_preserve_source_paragraph_properties_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        source_paragraphs=[ParagraphStub()],
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: (_ for _ in ()).throw(RuntimeError("preserve exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: preserve exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_normalize_semantic_output_docx_raises():
    runtime = _build_runtime_capture()

    result = _run_processing(
        runtime,
        source_paragraphs=[ParagraphStub()],
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: (_ for _ in ()).throw(RuntimeError("normalize exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: normalize exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"


def test_run_document_processing_fails_when_reinsert_inline_images_raises():
    runtime = _build_runtime_capture()
    image_assets = [AssetStub("img_001")]

    result = _run_processing(
        runtime,
        image_assets=image_assets,
        process_document_images=lambda **kwargs: image_assets,
        reinsert_inline_images=lambda docx_bytes, processed_assets: (_ for _ in ()).throw(RuntimeError("reinsert exploded")),
    )

    assert result == "failed"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["state"]["latest_docx_bytes"] is None
    assert runtime["state"]["last_error"] == "Ошибка сборки DOCX: reinsert exploded"
    assert runtime["finalize"][-1][0] == "Ошибка сборки DOCX"
    assert runtime["activity"][-1] == "Ошибка на этапе сборки DOCX."
    assert runtime["log"][-1]["status"] == "ERROR"