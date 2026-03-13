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


def _build_runtime_capture():
    return {"state": {}, "finalize": [], "activity": [], "log": [], "status": []}


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _emit_finalize(runtime, stage, detail, progress):
    runtime.setdefault("finalize", []).append((stage, detail, progress))


def _emit_activity(runtime, message):
    runtime.setdefault("activity", []).append(message)


def _emit_log(runtime, **payload):
    runtime.setdefault("log", []).append(payload)


def _emit_status(runtime, **payload):
    runtime.setdefault("status", []).append(payload)


def test_run_document_processing_happy_path_updates_runtime_state():
    runtime = _build_runtime_capture()
    progress_calls = []
    image_assets = [AssetStub("img_001")]

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        image_assets=image_assets,
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        on_progress=lambda **kwargs: progress_calls.append(kwargs),
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: image_assets,
        inspect_placeholder_integrity=lambda markdown_text, assets: {},
        convert_markdown_to_docx_bytes=lambda markdown: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, assets: b"final-docx",
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_docx_bytes"] == b"final-docx"
    assert runtime["state"]["latest_markdown"] == "Обработанный блок"
    assert runtime["finalize"][-1][0] == "Обработка завершена"
    assert runtime["log"][-1]["status"] == "DONE"
    assert len(progress_calls) == 3


def test_run_document_processing_applies_semantic_output_normalization_before_image_reinsertion():
    runtime = _build_runtime_capture()
    call_order = []

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[object()],
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: "Обработанный блок",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, assets: {},
        convert_markdown_to_docx_bytes=lambda markdown: call_order.append("convert") or b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: call_order.append("preserve") or docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: call_order.append("normalize") or docx_bytes,
        reinsert_inline_images=lambda docx_bytes, assets: call_order.append("reinsert") or docx_bytes,
    )

    assert result == "succeeded"
    assert call_order == ["convert", "preserve", "normalize"]


def test_run_document_processing_stops_before_second_block():
    runtime = _build_runtime_capture()
    stop_checks = {"count": 0}

    def should_stop(runtime):
        stop_checks["count"] += 1
        return stop_checks["count"] >= 2

    result = document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {"target_text": "block-1", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
            {"target_text": "block-2", "context_before": "", "context_after": "", "target_chars": 7, "context_chars": 0},
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
        load_system_prompt=lambda: "system",
        log_event=lambda *args, **kwargs: None,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_activity=_emit_activity,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=should_stop,
        generate_markdown_block=lambda **kwargs: "ok",
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, assets: {},
        convert_markdown_to_docx_bytes=lambda markdown: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, assets: docx_bytes,
    )

    assert result == "stopped"
    assert runtime["finalize"][-1][0] == "Остановлено пользователем"
    assert runtime["log"][-1]["status"] == "STOP"


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
        load_system_prompt=lambda: "system",
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
        inspect_placeholder_integrity=lambda markdown_text, assets: {},
        convert_markdown_to_docx_bytes=lambda markdown: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, assets: docx_bytes,
    )

    assert result == "failed"
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["log"][-1]["status"] == "ERROR"


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
        load_system_prompt=lambda: "system",
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
        inspect_placeholder_integrity=lambda markdown_text, assets: {},
        convert_markdown_to_docx_bytes=lambda markdown: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs: docx_bytes,
        normalize_semantic_output_docx=lambda docx_bytes, paragraphs: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, assets: docx_bytes,
    )

    assert result == "failed"
    assert runtime["finalize"][-1][0] == "Критическая ошибка"
    assert runtime["activity"][-1] == "Обнаружено несоответствие количества обработанных блоков."