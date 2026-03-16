import logging
import threading
import time
from typing import cast

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
    initial_sidebar_state="expanded",
)

from constants import APP_READY_PATH, MAX_DOCX_ARCHIVE_SIZE_BYTES
from config import load_app_config
from app_runtime import (
    build_preparation_request_marker,
    drain_preparation_events as _drain_preparation_events,
    drain_processing_events as _drain_processing_events,
    preparation_worker_is_active as _preparation_worker_is_active,
    processing_worker_is_active as _processing_worker_is_active,
    request_processing_stop as _request_processing_stop,
    start_background_preparation,
    start_background_processing,
)
from logger import fail_critical, log_event, present_error
from processing_runtime import (
    freeze_uploaded_file,
    get_current_result_bundle,
    resolve_uploaded_filename,
)
from state import (
    init_session_state,
    push_activity,
    reset_run_state,
    set_processing_status,
)
from ui import (
    inject_ui_styles,
    render_image_validation_summary,
    render_live_status,
    render_partial_result,
    render_preparation_summary,
    render_result,
    render_result_bundle,
    render_run_log,
    render_section_gap,
    render_sidebar,
)
from workflow_state import IdleViewState, ProcessingOutcome

PERSISTED_SOURCE_TTL_SECONDS = 12 * 60 * 60
_CLEANUP_THREAD_LOCK = threading.Lock()
_CLEANUP_THREAD_STARTED = False


@st.cache_resource
def _cached_load_app_config():
    return load_app_config()


def _schedule_stale_persisted_sources_cleanup() -> None:
    global _CLEANUP_THREAD_STARTED
    if st.session_state.get("persisted_source_cleanup_done", False):
        return
    with _CLEANUP_THREAD_LOCK:
        if _CLEANUP_THREAD_STARTED:
            return
        _CLEANUP_THREAD_STARTED = True

    def worker() -> None:
        from restart_store import cleanup_stale_persisted_sources

        try:
            cleanup_stale_persisted_sources(max_age_seconds=PERSISTED_SOURCE_TTL_SECONDS)
        finally:
            with _CLEANUP_THREAD_LOCK:
                global _CLEANUP_THREAD_STARTED
                _CLEANUP_THREAD_STARTED = False

    threading.Thread(target=worker, daemon=True, name="persisted-source-cleanup").start()
    st.session_state.persisted_source_cleanup_done = True


def _mark_app_ready() -> None:
    APP_READY_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_READY_PATH.write_text(f"{time.time():.6f}\n", encoding="utf-8")


def _is_uploaded_file_too_large(uploaded_file) -> bool:
    file_size = getattr(uploaded_file, "size", None)
    return isinstance(file_size, int) and file_size > MAX_DOCX_ARCHIVE_SIZE_BYTES


def _start_background_processing(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    source_bytes: bytes,
    jobs: list[dict[str, str | int]],
    source_paragraphs: list,
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    def worker_entrypoint(*, runtime, uploaded_filename, jobs, source_paragraphs, image_assets, image_mode, app_config, model, max_retries) -> None:
        from processing_service import get_processing_service

        get_processing_service().run_processing_worker(
            runtime=runtime,
            uploaded_filename=uploaded_filename,
            jobs=jobs,
            source_paragraphs=source_paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
        )

    start_background_processing(
        worker_target=worker_entrypoint,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        source_bytes=source_bytes,
        jobs=jobs,
        source_paragraphs=source_paragraphs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
    )


def _start_background_preparation(
    *,
    uploaded_payload,
    upload_marker: str,
    chunk_size: int,
    image_mode: str,
    keep_all_image_variants: bool,
) -> None:
    from application_flow import prepare_run_context_for_background

    start_background_preparation(
        worker_target=prepare_run_context_for_background,
        uploaded_payload=uploaded_payload,
        upload_marker=upload_marker,
        chunk_size=chunk_size,
        image_mode=image_mode,
        keep_all_image_variants=keep_all_image_variants,
    )


def _store_preparation_summary(*, prepared_run_context) -> None:
    elapsed_seconds = float(getattr(prepared_run_context, "preparation_elapsed_seconds", 0.0) or 0.0)
    elapsed = f"{elapsed_seconds:.1f} c" if elapsed_seconds > 0 else ""
    st.session_state.latest_preparation_summary = {
        "stage": str(getattr(prepared_run_context, "preparation_stage", "Документ подготовлен")),
        "detail": str(getattr(prepared_run_context, "preparation_detail", "Анализ завершён. Можно запускать обработку.")),
        "file_size_bytes": len(prepared_run_context.uploaded_file_bytes),
        "paragraph_count": len(prepared_run_context.paragraphs),
        "image_count": len(prepared_run_context.image_assets),
        "source_chars": len(prepared_run_context.source_text),
        "block_count": len(prepared_run_context.jobs),
        "cached": bool(getattr(prepared_run_context, "preparation_cached", False)),
        "elapsed": elapsed,
        "progress": 1.0,
    }


def _render_processing_controls(*, can_start: bool, is_processing: bool) -> str | None:
    stop_requested = bool(st.session_state.get("processing_stop_requested", False))
    start_col, stop_col = st.columns(2)

    if start_col.button(
        "Обработка запущена" if is_processing else "Начать обработку",
        type="primary",
        use_container_width=True,
        disabled=(not can_start) or is_processing,
        key="start_processing_button",
    ):
        return "start"

    if stop_col.button(
        "Останавливаю..." if stop_requested else "Стоп",
        use_container_width=True,
        disabled=(not is_processing) or stop_requested,
        key="stop_processing_button",
    ):
        return "stop"

    return None


def main() -> None:
    init_session_state()
    _drain_processing_events()
    _drain_preparation_events()
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
        app_config = _cached_load_app_config()
    except Exception as exc:
        user_message = present_error("config_load_failed", exc, "Ошибка загрузки конфигурации")
        st.error(f"Ошибка загрузки конфигурации: {user_message}")
        return

    model, chunk_size, max_retries, image_mode, keep_all_image_variants = render_sidebar(app_config)
    app_config = dict(app_config)
    app_config["keep_all_image_variants"] = keep_all_image_variants

    processing_active = _processing_worker_is_active()
    preparation_active = _preparation_worker_is_active()
    current_result = get_current_result_bundle()

    if processing_active:
        @st.fragment(run_every=2)
        def render_processing_panel() -> None:
            _drain_processing_events()
            render_live_status()
            render_run_log()
            render_image_validation_summary()
            render_partial_result()
            render_section_gap("lg")
            _mark_app_ready()
            _schedule_stale_persisted_sources_cleanup()

            action = _render_processing_controls(can_start=False, is_processing=_processing_worker_is_active())
            if action == "stop":
                push_activity("Остановлено. Завершение текущего шага...")
                _request_processing_stop()
                st.rerun()

            if not _processing_worker_is_active():
                st.rerun()

        render_processing_panel()
        return

    uploaded_widget_file = st.file_uploader("Загрузите DOCX-файл", type=["docx"])

    @st.fragment(run_every=1)
    def render_preparation_panel() -> None:
        _drain_preparation_events()
        render_live_status()
        render_run_log()
        _mark_app_ready()
        _schedule_stale_persisted_sources_cleanup()
        if not _preparation_worker_is_active():
            st.rerun()

    if uploaded_widget_file is not None and _is_uploaded_file_too_large(uploaded_widget_file):
        st.error(
            f"Размер DOCX превышает допустимый предел {MAX_DOCX_ARCHIVE_SIZE_BYTES // (1024 * 1024)} МБ. Загрузите файл меньшего размера."
        )
        render_run_log()
        _mark_app_ready()
        _schedule_stale_persisted_sources_cleanup()
        return

    if preparation_active:
        render_preparation_panel()
        return

    if (
        uploaded_widget_file is None
        and current_result is None
        and not st.session_state.get("restart_source")
        and not st.session_state.get("completed_source")
    ):
        render_run_log()
        render_image_validation_summary()
        render_partial_result()
        _mark_app_ready()
        _schedule_stale_persisted_sources_cleanup()
        return

    uploaded_widget_payload = None
    if uploaded_widget_file is not None:
        uploaded_widget_payload = freeze_uploaded_file(uploaded_widget_file)
        preparation_request_marker = build_preparation_request_marker(uploaded_widget_payload, chunk_size=chunk_size)
        prepared_request_marker = str(st.session_state.get("preparation_input_marker", ""))
        preparation_failed_marker = str(st.session_state.get("preparation_failed_marker", ""))
        prepared_run_context = st.session_state.get("prepared_run_context")
        if (preparation_request_marker != prepared_request_marker or prepared_run_context is None) and preparation_failed_marker != preparation_request_marker:
            _start_background_preparation(
                uploaded_payload=uploaded_widget_payload,
                upload_marker=preparation_request_marker,
                chunk_size=chunk_size,
                image_mode=image_mode,
                keep_all_image_variants=keep_all_image_variants,
            )
            render_preparation_panel()
            return
        if preparation_failed_marker == preparation_request_marker and prepared_run_context is None:
            if st.session_state.last_error:
                st.error(st.session_state.last_error)
            render_live_status()
            render_run_log()
            _mark_app_ready()
            _schedule_stale_persisted_sources_cleanup()
            return

    from application_flow import (
        SessionStateLike,
        derive_app_idle_view_state,
        has_resettable_state,
        prepare_run_context,
        resolve_effective_uploaded_file,
    )

    session_state = cast(SessionStateLike, st.session_state)

    uploaded_file = resolve_effective_uploaded_file(
        uploaded_file=uploaded_widget_file,
        current_result=current_result,
        session_state=session_state,
    )

    prepared_run_context = None
    if uploaded_widget_payload is not None:
        current_preparation_request_marker = build_preparation_request_marker(uploaded_widget_payload, chunk_size=chunk_size)
        if str(st.session_state.get("preparation_input_marker", "")) == current_preparation_request_marker:
            prepared_run_context = st.session_state.get("prepared_run_context")
        if prepared_run_context is None:
            st.warning(
                "Подготовка файла еще не завершилась или состояние подготовки было сброшено. Подождите несколько секунд. "
                "Если экран не обновляется, загрузите файл повторно."
            )
            render_live_status()
            render_run_log()
            _mark_app_ready()
            _schedule_stale_persisted_sources_cleanup()
            return

    if has_resettable_state(current_result=current_result, session_state=session_state):
        if st.button("Сбросить результаты", use_container_width=True):
            reset_run_state(keep_restart_source=False)
            st.rerun()
    idle_view_state = derive_app_idle_view_state(
        current_result=current_result,
        uploaded_file=uploaded_file,
        session_state=session_state,
    )

    if idle_view_state != IdleViewState.FILE_SELECTED:
        if idle_view_state == IdleViewState.COMPLETED:
            if current_result is None:
                st.error("Результат обработки недоступен в текущей сессии.")
                _mark_app_ready()
                _schedule_stale_persisted_sources_cleanup()
                return
            completed_result = cast(dict[str, object], current_result)
            render_result_bundle(
                docx_bytes=cast(bytes, completed_result["docx_bytes"]),
                markdown_text=str(completed_result["markdown_text"]),
                original_filename=str(completed_result["source_name"]),
                title="Последний результат",
                success_message=None,
                preview_title="Предпросмотр Markdown",
            )
        elif idle_view_state == IdleViewState.RESTARTABLE:
            st.info("Можно изменить настройки и запустить обработку заново без повторной загрузки файла.")
        render_run_log()
        render_image_validation_summary()
        render_partial_result()
        _mark_app_ready()
        _schedule_stale_persisted_sources_cleanup()
        return

    if prepared_run_context is None:
        try:
            prepared_run_context = prepare_run_context(
                uploaded_file=uploaded_file,
                chunk_size=chunk_size,
                image_mode=image_mode,
                keep_all_image_variants=keep_all_image_variants,
                session_state=st.session_state,
                reset_run_state_fn=reset_run_state,
                fail_critical_fn=fail_critical,
                log_event_fn=log_event,
            )
        except Exception as exc:
            user_message = present_error(
                "document_read_failed",
                exc,
                "Ошибка чтения документа",
                filename=resolve_uploaded_filename(uploaded_file),
            )
            st.error(f"Ошибка чтения документа: {user_message}")
            return

    uploaded_filename = prepared_run_context.uploaded_filename
    uploaded_file_bytes = prepared_run_context.uploaded_file_bytes
    uploaded_file_token = prepared_run_context.uploaded_file_token
    paragraphs = prepared_run_context.paragraphs
    image_assets = prepared_run_context.image_assets
    jobs = prepared_run_context.jobs
    source_text = prepared_run_context.source_text

    if current_result is None and st.session_state.get("processing_outcome") == ProcessingOutcome.STOPPED.value:
        st.warning(
            f"Обработка файла «{uploaded_filename}» была остановлена. Можно изменить настройки и запустить заново без повторной загрузки."
        )

    _store_preparation_summary(prepared_run_context=prepared_run_context)
    if not processing_active:
        set_processing_status(
            stage="Документ подготовлен",
            detail=f"Собрано {len(jobs)} блоков. Можно запускать обработку.",
            current_block=0,
            block_count=len(jobs),
            file_size_bytes=len(uploaded_file_bytes),
            paragraph_count=len(paragraphs),
            image_count=len(image_assets),
            source_chars=len(source_text),
            cached=bool(getattr(prepared_run_context, "preparation_cached", False)),
            progress=1.0,
            is_running=False,
            phase="preparing",
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
    render_preparation_summary(st.session_state.get("latest_preparation_summary"))
    render_partial_result()
    render_run_log()
    render_image_validation_summary()

    from compare_panel import render_compare_all_apply_panel

    render_compare_all_apply_panel(
        latest_image_mode=st.session_state.latest_image_mode,
        image_assets=st.session_state.image_assets,
        render_section_gap=render_section_gap,
    )

    if has_completed_result:
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_filename)

    render_section_gap("lg")
    _mark_app_ready()
    _schedule_stale_persisted_sources_cleanup()
    action = _render_processing_controls(can_start=True, is_processing=False)
    if action == "start":
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
            jobs=jobs,
            source_paragraphs=paragraphs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
        )
        st.rerun()


if __name__ == "__main__":
    main()
