import logging

from dotenv import load_dotenv

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
)

from constants import ENV_PATH
from application_flow import (
    derive_app_idle_view_state,
    has_resettable_state,
    prepare_run_context,
    prepare_run_context_for_background,
    resolve_effective_uploaded_file,
)
from compare_panel import render_compare_all_apply_panel
from config import load_app_config
from app_runtime import (
    build_preparation_request_marker,
    build_uploaded_file_selection_marker,
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
    get_current_result_bundle,
    resolve_uploaded_filename,
)
from processing_service import get_processing_service
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

load_dotenv(dotenv_path=ENV_PATH)


def _start_background_processing(
    *,
    uploaded_filename: str,
    uploaded_token: str,
    source_bytes: bytes,
    jobs: list[dict[str, str | int]],
    image_assets: list,
    image_mode: str,
    app_config: dict[str, object],
    model: str,
    max_retries: int,
) -> None:
    start_background_processing(
        worker_target=get_processing_service().run_processing_worker,
        uploaded_filename=uploaded_filename,
        uploaded_token=uploaded_token,
        source_bytes=source_bytes,
        jobs=jobs,
        image_assets=image_assets,
        image_mode=image_mode,
        app_config=app_config,
        model=model,
        max_retries=max_retries,
    )


def _start_background_preparation(
    *,
    uploaded_file,
    upload_marker: str,
    chunk_size: int,
    image_mode: str,
    enable_post_redraw_validation: bool,
) -> None:
    start_background_preparation(
        worker_target=prepare_run_context_for_background,
        uploaded_file=uploaded_file,
        upload_marker=upload_marker,
        chunk_size=chunk_size,
        image_mode=image_mode,
        enable_post_redraw_validation=enable_post_redraw_validation,
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
    }


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
        app_config = load_app_config()
    except Exception as exc:
        user_message = present_error("config_load_failed", exc, "Ошибка загрузки конфигурации")
        st.error(f"Ошибка загрузки конфигурации: {user_message}")
        return

    model, chunk_size, max_retries, image_mode, enable_post_redraw_validation = render_sidebar(app_config)
    app_config = dict(app_config)
    app_config["enable_post_redraw_validation"] = enable_post_redraw_validation
    processing_active = _processing_worker_is_active()
    preparation_active = _preparation_worker_is_active()
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

            stop_requested = st.session_state.get("processing_stop_requested", False)
            stop_disabled = not _processing_worker_is_active() or stop_requested
            if st.button("Стоп", use_container_width=True, disabled=stop_disabled, key="processing_stop_button"):
                push_activity("Остановлено. Завершение текущего шага...")
                _request_processing_stop()
                st.rerun()
            if stop_requested and _processing_worker_is_active():
                st.caption("Остановлено. Завершение текущего шага...")
            elif not stop_disabled:
                st.caption("Останавливает обработку после текущего шага.")
            else:
                st.caption("Обработка завершена. Обновляю экран результата.")

            if not _processing_worker_is_active():
                st.rerun()

        render_processing_panel()
        return

    uploaded_widget_file = st.file_uploader("Загрузите DOCX-файл", type=["docx"])

    if preparation_active:
        @st.fragment(run_every=1)
        def render_preparation_panel() -> None:
            _drain_preparation_events()
            render_live_status()
            if not _preparation_worker_is_active():
                st.rerun()

        render_preparation_panel()
        return

    if uploaded_widget_file is not None:
        upload_marker = build_uploaded_file_selection_marker(uploaded_widget_file)
        preparation_request_marker = build_preparation_request_marker(uploaded_widget_file, chunk_size=chunk_size)
        prepared_request_marker = str(st.session_state.get("preparation_input_marker", ""))
        preparation_failed_marker = str(st.session_state.get("preparation_failed_marker", ""))
        prepared_run_context = st.session_state.get("prepared_run_context")
        if (preparation_request_marker != prepared_request_marker or prepared_run_context is None) and preparation_failed_marker != preparation_request_marker:
            _start_background_preparation(
                uploaded_file=uploaded_widget_file,
                upload_marker=preparation_request_marker,
                chunk_size=chunk_size,
                image_mode=image_mode,
                enable_post_redraw_validation=enable_post_redraw_validation,
            )
            st.rerun()
        if preparation_failed_marker == preparation_request_marker and prepared_run_context is None:
            if st.session_state.last_error:
                st.error(st.session_state.last_error)
            render_live_status()
            return

    uploaded_file = resolve_effective_uploaded_file(
        uploaded_file=uploaded_widget_file,
        current_result=current_result,
        session_state=st.session_state,
    )

    prepared_run_context = None
    if uploaded_widget_file is not None:
        current_preparation_request_marker = build_preparation_request_marker(uploaded_widget_file, chunk_size=chunk_size)
        if str(st.session_state.get("preparation_input_marker", "")) == current_preparation_request_marker:
            prepared_run_context = st.session_state.get("prepared_run_context")
        if prepared_run_context is None:
            return

    if has_resettable_state(current_result=current_result, session_state=st.session_state):
        if st.button("Сбросить результаты", use_container_width=True):
            reset_run_state(keep_restart_source=False)
            st.rerun()
    idle_view_state = derive_app_idle_view_state(
        current_result=current_result,
        uploaded_file=uploaded_file,
        session_state=st.session_state,
    )

    if idle_view_state != IdleViewState.FILE_SELECTED:
        if idle_view_state == IdleViewState.COMPLETED:
            render_result_bundle(
                docx_bytes=current_result["docx_bytes"],
                markdown_text=str(current_result["markdown_text"]),
                original_filename=str(current_result["source_name"]),
                title="Последний результат",
                success_message=None,
                preview_title="Предпросмотр Markdown",
            )
        elif idle_view_state == IdleViewState.RESTARTABLE:
            st.info("Можно изменить настройки и запустить обработку заново без повторной загрузки файла.")
        else:
            st.info("Ожидается файл .docx")
        render_run_log()
        render_image_validation_summary()
        render_partial_result()
        return

    if prepared_run_context is None:
        try:
            prepared_run_context = prepare_run_context(
                uploaded_file=uploaded_file,
                chunk_size=chunk_size,
                image_mode=image_mode,
                enable_post_redraw_validation=enable_post_redraw_validation,
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

    render_preparation_summary(st.session_state.get("latest_preparation_summary"))
    render_section_gap("lg")
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
    render_partial_result()
    render_run_log()
    render_image_validation_summary()

    render_compare_all_apply_panel(
        latest_image_mode=st.session_state.latest_image_mode,
        image_assets=st.session_state.image_assets,
        render_section_gap=render_section_gap,
    )

    if has_completed_result:
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_filename)

    render_section_gap("lg")
    start_col, stop_col = st.columns(2)
    if start_col.button("Начать обработку", type="primary", use_container_width=True):
        _start_background_processing(
            uploaded_filename=uploaded_filename,
            uploaded_token=uploaded_file_token,
            source_bytes=uploaded_file_bytes,
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
