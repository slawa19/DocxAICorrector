import logging

from dotenv import load_dotenv

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
)

from constants import ENV_PATH
from compare_apply import apply_selected_compare_variants as apply_selected_compare_variants_impl
from compare_panel import render_compare_all_apply_panel
from config import get_client, load_app_config, load_system_prompt
from app_runtime import (
    BackgroundRuntime,
    drain_processing_events as _drain_processing_events,
    emit_activity as _emit_or_apply_activity,
    emit_finalize as _emit_or_apply_finalize,
    emit_image_log as _emit_or_apply_image_log,
    emit_image_reset as _emit_or_apply_image_reset,
    emit_log as _emit_or_apply_log,
    emit_state as _emit_or_apply_state,
    emit_status as _emit_or_apply_status,
    processing_worker_is_active as _processing_worker_is_active,
    request_processing_stop as _request_processing_stop,
    start_background_processing,
)
from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
    reinsert_inline_images,
)
from document_pipeline import run_document_processing as run_document_processing_impl
from generation import convert_markdown_to_docx_bytes, ensure_pandoc_available, generate_markdown_block
from image_analysis import analyze_image
from image_generation import (
    ImageModelCallBudget,
    ImageModelCallBudgetExceeded,
    detect_image_mime_type,
    generate_image_candidate,
)
from image_pipeline import process_document_images as process_document_images_impl
from image_validation import validate_redraw_result
from logger import fail_critical, log_event, present_error
from processing_runtime import (
    get_current_result_bundle,
    build_uploaded_file_token,
    get_previous_result_bundle,
    resolve_uploaded_filename,
    should_stop_processing,
)
from state import (
    append_image_log,
    init_session_state,
    push_activity,
    reset_run_state,
    set_processing_status,
)
from ui import (
    inject_ui_styles,
    render_image_compare_selector,
    render_image_validation_summary,
    render_live_status,
    render_markdown_preview,
    render_partial_result,
    render_result,
    render_result_bundle,
    render_run_log,
    render_section_gap,
    render_sidebar,
)

load_dotenv(dotenv_path=ENV_PATH)


def _should_stop_processing(runtime: BackgroundRuntime | None) -> bool:
    return should_stop_processing(runtime)


def _resolve_uploaded_filename(uploaded_file) -> str:
    return resolve_uploaded_filename(uploaded_file)


def _start_background_processing(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    start_background_processing(
        worker_target=_run_processing_worker,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        jobs=jobs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
    )


def _run_processing_worker(
    *,
    runtime: BackgroundRuntime,
    uploaded_filename: str,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    outcome = "failed"
    try:
        outcome = run_document_processing(
            uploaded_file=uploaded_filename,
            jobs=jobs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            on_progress=lambda **kwargs: None,
            runtime=runtime,
        )
    except Exception as exc:
        error_message = present_error(
            "processing_worker_crashed",
            exc,
            "Критическая ошибка фоновой обработки",
            filename=uploaded_filename,
            block_count=len(jobs),
        )
        runtime.emit("set_state", values={"last_error": error_message})
        runtime.emit("finalize_processing_status", stage="Критическая ошибка", detail=error_message, progress=1.0)
        runtime.emit("push_activity", message="Фоновый worker аварийно завершился; runtime-state принудительно очищается.")
        runtime.emit(
            "append_log",
            payload={
                "status": "ERROR",
                "block_index": 0,
                "block_count": len(jobs),
                "target_chars": 0,
                "context_chars": 0,
                "details": error_message,
            },
        )
    finally:
        runtime.emit("worker_complete", outcome=outcome)


def build_start_button_label(*, has_current_result: bool, has_previous_result: bool) -> str:
    if has_current_result:
        return "Запустить заново"
    if has_previous_result:
        return "Начать обработку нового файла"
    return "Начать обработку"


def _sync_selected_file_context(uploaded_file_token: str) -> None:
    previous_token = st.session_state.get("selected_source_token", "")
    if not previous_token or previous_token == uploaded_file_token:
        st.session_state.selected_source_token = uploaded_file_token
        return

    current_result = get_current_result_bundle()
    if current_result and current_result["source_token"] != uploaded_file_token:
        st.session_state.previous_result = current_result

    reset_run_state(keep_previous_result=True)
    st.session_state.selected_source_token = uploaded_file_token


def _build_prepared_source_key(uploaded_file_token: str, chunk_size: int) -> str:
    return f"{uploaded_file_token}:{chunk_size}"


def _should_log_document_prepared(prepared_source_key: str) -> bool:
    return st.session_state.get("prepared_source_key", "") != prepared_source_key


def _apply_selected_compare_variants() -> None:
    apply_selected_compare_variants_impl(
        st.session_state,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        reinsert_inline_images=reinsert_inline_images,
    )


def process_document_images(
    *,
    image_assets,
    image_mode: str,
    config: dict[str, object],
    on_progress,
    runtime: BackgroundRuntime | None = None,
    client=None,
) -> list:
    return process_document_images_impl(
        image_assets=image_assets,
        image_mode=image_mode,
        config=config,
        on_progress=on_progress,
        runtime=runtime,
        client=client,
        emit_state=_emit_or_apply_state,
        emit_image_reset=_emit_or_apply_image_reset,
        emit_finalize=_emit_or_apply_finalize,
        emit_activity=_emit_or_apply_activity,
        emit_status=_emit_or_apply_status,
        emit_image_log=_emit_or_apply_image_log,
        should_stop=_should_stop_processing,
        analyze_image_fn=analyze_image,
        generate_image_candidate_fn=generate_image_candidate,
        validate_redraw_result_fn=validate_redraw_result,
        get_client_fn=get_client,
        log_event_fn=log_event,
        detect_image_mime_type_fn=detect_image_mime_type,
        image_model_call_budget_cls=ImageModelCallBudget,
        image_model_call_budget_exceeded_cls=ImageModelCallBudgetExceeded,
    )


def run_document_processing(
    *,
    uploaded_file,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
    on_progress,
    runtime: BackgroundRuntime | None = None,
) -> str:
    return run_document_processing_impl(
        uploaded_file=uploaded_file,
        jobs=jobs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
        on_progress=on_progress,
        runtime=runtime,
        resolve_uploaded_filename=_resolve_uploaded_filename,
        get_client=get_client,
        ensure_pandoc_available=ensure_pandoc_available,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=present_error,
        emit_state=_emit_or_apply_state,
        emit_finalize=_emit_or_apply_finalize,
        emit_activity=_emit_or_apply_activity,
        emit_log=_emit_or_apply_log,
        emit_status=_emit_or_apply_status,
        should_stop_processing=_should_stop_processing,
        generate_markdown_block=generate_markdown_block,
        process_document_images=process_document_images,
        inspect_placeholder_integrity=inspect_placeholder_integrity,
        convert_markdown_to_docx_bytes=convert_markdown_to_docx_bytes,
        reinsert_inline_images=reinsert_inline_images,
    )


def main() -> None:
    init_session_state()
    _drain_processing_events()
    inject_ui_styles()
    if not st.session_state.app_start_logged:
        log_event(logging.INFO, "app_start", "Приложение инициализировано")
        st.session_state.app_start_logged = True
    st.title("AI-редактор DOCX через Markdown")
    st.write(
        "Загрузите DOCX, приложение соберет смысловые блоки из нескольких абзацев, "
        "добавит соседний контекст для модели и соберет новый DOCX."
    )

    try:
        app_config = load_app_config()
    except Exception as exc:
        user_message = present_error("config_load_failed", exc, "Ошибка загрузки конфигурации")
        st.error(f"Ошибка загрузки конфигурации: {user_message}")
        return

    model, chunk_size, max_retries, image_mode, enable_post_redraw_validation = render_sidebar(app_config)
    app_config = dict(app_config)
    app_config["enable_post_redraw_validation"] = enable_post_redraw_validation
    processing_active = _processing_worker_is_active()
    current_result = get_current_result_bundle()

    if processing_active:
        st.info(f"Идет обработка файла: {st.session_state.latest_source_name}")

        @st.fragment(run_every=1)
        def render_processing_panel() -> None:
            _drain_processing_events()
            render_live_status()
            render_run_log()
            render_image_validation_summary()
            render_partial_result()
            render_section_gap("lg")

            stop_disabled = not _processing_worker_is_active()
            if st.button("Стоп", use_container_width=True, disabled=stop_disabled, key="processing_stop_button"):
                _request_processing_stop()
                st.rerun()
            st.caption(
                "Останавливает обработку после текущего шага."
                if not stop_disabled
                else "Обработка завершена. Обновляю экран результата."
            )

            if not _processing_worker_is_active():
                st.rerun()

        render_processing_panel()
        return

    uploaded_file = st.file_uploader("Загрузите DOCX-файл", type=["docx"])

    if current_result or st.session_state.get("previous_result"):
        if st.button("Сбросить результаты", use_container_width=True):
            reset_run_state(keep_previous_result=False)
            st.rerun()

    if not uploaded_file:
        if current_result:
            render_result_bundle(
                docx_bytes=current_result["docx_bytes"],
                markdown_text=str(current_result["markdown_text"]),
                original_filename=str(current_result["source_name"]),
                title="Последний результат",
                success_message=None,
                preview_title="Предпросмотр Markdown",
            )
        else:
            st.info("Ожидается файл .docx")
        render_run_log()
        render_image_validation_summary()
        render_partial_result()
        return

    uploaded_file_token = build_uploaded_file_token(uploaded_file)
    _sync_selected_file_context(uploaded_file_token)

    prepared_source_key = _build_prepared_source_key(uploaded_file_token, chunk_size)
    try:
        paragraphs, image_assets = extract_document_content_from_docx(uploaded_file)
        source_text = build_document_text(paragraphs)
        blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size)
        jobs = build_editing_jobs(blocks, max_chars=chunk_size)
        if not jobs:
            fail_critical("no_jobs_built", "Не удалось собрать ни одного блока для обработки.", filename=uploaded_file.name)
        if any(not str(job["target_text"]).strip() for job in jobs):
            fail_critical("empty_target_block", "Обнаружен пустой целевой блок перед отправкой в модель.", filename=uploaded_file.name)
        if _should_log_document_prepared(prepared_source_key):
            log_event(
                logging.INFO,
                "document_prepared",
                "Документ подготовлен к обработке",
                filename=uploaded_file.name,
                paragraph_count=len(paragraphs),
                block_count=len(jobs),
                image_count=len(image_assets),
                source_chars=len(source_text),
                chunk_size=chunk_size,
                image_mode=image_mode,
                enable_post_redraw_validation=enable_post_redraw_validation,
            )
            st.session_state.prepared_source_key = prepared_source_key
    except Exception as exc:
        user_message = present_error(
            "document_read_failed",
            exc,
            "Ошибка чтения документа",
            filename=uploaded_file.name,
        )
        st.error(f"Ошибка чтения документа: {user_message}")
        return

    st.caption(
        f"Символов: {len(source_text)} | Абзацев: {len(paragraphs)} | Блоков: {len(jobs)}"
    )
    if not processing_active:
        set_processing_status(
            stage="Документ подготовлен",
            detail=f"Собрано {len(jobs)} блоков. Можно запускать обработку.",
            current_block=0,
            block_count=len(jobs),
            progress=0.0,
            is_running=False,
        )
    if not st.session_state.activity_feed:
        push_activity(f"Документ разобран на {len(jobs)} блоков.")

    if len(jobs) == 1:
        st.info("Документ помещается в один блок. Для длинных файлов обработка пойдет по блокам с соседним контекстом.")

    if st.session_state.last_error:
        st.error(st.session_state.last_error)
        st.caption(st.session_state.last_log_hint)

    has_completed_result = bool(
        st.session_state.latest_docx_bytes and st.session_state.latest_source_token == uploaded_file_token
    )
    previous_result = get_previous_result_bundle(uploaded_file_token)
    has_previous_result = previous_result is not None

    render_partial_result()
    render_run_log()
    render_image_validation_summary()

    render_compare_all_apply_panel(
        has_completed_result=has_completed_result,
        latest_image_mode=st.session_state.latest_image_mode,
        uploaded_filename=uploaded_file.name,
        render_section_gap=render_section_gap,
        render_image_compare_selector=render_image_compare_selector,
        apply_selected_compare_variants=_apply_selected_compare_variants,
        present_error=present_error,
    )

    if has_completed_result:
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_file.name)
    elif has_previous_result:
        st.info(
            f"Загружен новый файл: {uploaded_file.name}. Предыдущий результат для файла "
            f"{previous_result['source_name']} сохранен ниже и не будет потерян до следующего сброса."
        )
        render_result_bundle(
            docx_bytes=previous_result["docx_bytes"],
            markdown_text=str(previous_result["markdown_text"]),
            original_filename=str(previous_result["source_name"]),
            title="Предыдущий результат",
            success_message=None,
            preview_title=None,
        )

    render_section_gap("lg")
    start_col, stop_col = st.columns(2)
    start_label = build_start_button_label(
        has_current_result=has_completed_result,
        has_previous_result=has_previous_result,
    )
    if start_col.button(start_label, type="primary", use_container_width=True):
        _start_background_processing(
            uploaded_filename=uploaded_file.name,
            uploaded_token=uploaded_file_token,
            jobs=jobs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
        )
        st.rerun()

    stop_col.button("Стоп", use_container_width=True, disabled=True, key="idle_stop_button")

    start_col.caption(
        "Запускает обработку выбранного файла."
    )
    stop_col.caption(
        "Недоступно, пока обработка не запущена."
    )


if __name__ == "__main__":
    main()
