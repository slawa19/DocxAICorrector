from dotenv import load_dotenv

load_dotenv()

import logging
import time

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
)

from config import ensure_pandoc_available, get_client, load_app_config, load_system_prompt
from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_paragraph_units_from_docx,
)
from generation import convert_markdown_to_docx_bytes, generate_markdown_block
from logger import fail_critical, log_event, present_error
from state import (
    append_log,
    finalize_processing_status,
    init_session_state,
    push_activity,
    reset_run_state,
    set_processing_status,
)
from ui import (
    inject_ui_styles,
    render_live_status,
    render_markdown_preview,
    render_partial_result,
    render_result,
    render_run_log,
    render_sidebar,
)


def main() -> None:
    init_session_state()
    inject_ui_styles()
    log_event(logging.INFO, "app_start", "Приложение инициализировано")
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

    model, chunk_size, max_retries = render_sidebar(app_config)
    uploaded_file = st.file_uploader("Загрузите DOCX-файл", type=["docx"])

    if st.button("Сбросить результаты", use_container_width=True):
        reset_run_state()
        st.rerun()

    if not uploaded_file:
        st.info("Ожидается файл .docx")
        render_run_log()
        render_partial_result()
        return

    try:
        paragraphs = extract_paragraph_units_from_docx(uploaded_file)
        source_text = build_document_text(paragraphs)
        blocks = build_semantic_blocks(paragraphs, max_chars=chunk_size)
        jobs = build_editing_jobs(blocks, max_chars=chunk_size)
        if not jobs:
            fail_critical("no_jobs_built", "Не удалось собрать ни одного блока для обработки.", filename=uploaded_file.name)
        if any(not str(job["target_text"]).strip() for job in jobs):
            fail_critical("empty_target_block", "Обнаружен пустой целевой блок перед отправкой в модель.", filename=uploaded_file.name)
        log_event(
            logging.INFO,
            "document_prepared",
            "Документ подготовлен к обработке",
            filename=uploaded_file.name,
            paragraph_count=len(paragraphs),
            block_count=len(jobs),
            source_chars=len(source_text),
            chunk_size=chunk_size,
        )
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
        st.session_state.latest_docx_bytes and st.session_state.latest_source_name == uploaded_file.name
    )

    status_placeholder = st.empty()
    log_placeholder = st.empty()
    preview_placeholder = st.empty()
    render_live_status(status_placeholder)
    render_run_log(log_placeholder)
    if not has_completed_result:
        render_markdown_preview(preview_placeholder, title="Предпросмотр Markdown")

    render_partial_result()

    if has_completed_result:
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_file.name)

    if st.button("Начать обработку", type="primary", use_container_width=True):
        reset_run_state()
        st.session_state.latest_source_name = uploaded_file.name
        push_activity("Запуск обработки документа.")
        set_processing_status(
            stage="Инициализация",
            detail="Проверяю доступность OpenAI, Pandoc и системного промпта.",
            current_block=0,
            block_count=len(jobs),
            progress=0.0,
            is_running=True,
        )
        render_live_status(status_placeholder)
        render_run_log(log_placeholder)
        render_markdown_preview(preview_placeholder, title="Текущий Markdown")

        try:
            client = get_client()
            ensure_pandoc_available()
            system_prompt = load_system_prompt()
            log_event(
                logging.INFO,
                "processing_started",
                "Запуск обработки документа",
                filename=uploaded_file.name,
                model=model,
                block_count=len(jobs),
                max_retries=max_retries,
            )
            push_activity(f"Инициализация завершена. Модель: {model}.")
        except Exception as exc:
            st.session_state.last_error = present_error(
                "processing_init_failed",
                exc,
                "Ошибка инициализации обработки",
                filename=uploaded_file.name,
                model=model,
            )
            finalize_processing_status("Ошибка инициализации", st.session_state.last_error, 0.0)
            st.error(st.session_state.last_error)
            st.caption(st.session_state.last_log_hint)
            render_live_status(status_placeholder)
            return

        processed_chunks: list[str] = []
        started_at = time.perf_counter()

        for index, job in enumerate(jobs, start=1):
            target_chars = int(job["target_chars"])
            context_chars = int(job["context_chars"])
            set_processing_status(
                stage="Подготовка блока",
                detail=f"Готовлю блок {index} из {len(jobs)} к отправке в OpenAI.",
                current_block=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                progress=(index - 1) / len(jobs),
                is_running=True,
            )
            push_activity(f"Начата обработка блока {index} из {len(jobs)}.")
            render_live_status(status_placeholder)
            render_run_log(log_placeholder)
            render_markdown_preview(preview_placeholder, title="Текущий Markdown")
            log_event(
                logging.INFO,
                "block_started",
                "Начата обработка блока",
                filename=uploaded_file.name,
                block_index=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                model=model,
            )
            try:
                set_processing_status(
                    stage="Ожидание ответа OpenAI",
                    detail=f"Блок {index} отправлен в модель. Приложение работает, ожидаю ответ.",
                    current_block=index,
                    block_count=len(jobs),
                    target_chars=target_chars,
                    context_chars=context_chars,
                    progress=(index - 1) / len(jobs),
                    is_running=True,
                )
                push_activity(f"Блок {index} отправлен в OpenAI.")
                render_live_status(status_placeholder)
                processed_chunk = generate_markdown_block(
                    client=client,
                    model=model,
                    system_prompt=system_prompt,
                    target_text=str(job["target_text"]),
                    context_before=str(job["context_before"]),
                    context_after=str(job["context_after"]),
                    max_retries=max_retries,
                )
            except Exception as exc:
                st.session_state.latest_markdown = "\n\n".join(processed_chunks).strip()
                error_message = present_error(
                    "block_failed",
                    exc,
                    "Ошибка обработки блока",
                    filename=uploaded_file.name,
                    block_index=index,
                    block_count=len(jobs),
                    target_chars=target_chars,
                    context_chars=context_chars,
                    model=model,
                )
                st.session_state.last_error = f"Ошибка на блоке {index}: {error_message}"
                finalize_processing_status("Ошибка обработки", st.session_state.last_error, (index - 1) / len(jobs))
                push_activity(f"Блок {index}: ошибка обработки.")
                append_log(
                    "ERROR",
                    index,
                    len(jobs),
                    target_chars,
                    context_chars,
                    error_message,
                )
                st.error(st.session_state.last_error)
                st.caption(st.session_state.last_log_hint)
                render_live_status(status_placeholder)
                render_run_log(log_placeholder)
                render_markdown_preview(preview_placeholder, title="Текущий Markdown")
                return

            if not processed_chunk.strip():
                critical_message = present_error(
                    "empty_processed_block",
                    RuntimeError("Модель вернула пустой Markdown-блок после успешного вызова."),
                    "Критическая ошибка обработки блока",
                    filename=uploaded_file.name,
                    block_index=index,
                )
                st.session_state.last_error = f"Ошибка на блоке {index}: {critical_message}"
                finalize_processing_status("Критическая ошибка", st.session_state.last_error, (index - 1) / len(jobs))
                push_activity(f"Блок {index}: модель вернула пустой Markdown.")
                append_log("ERROR", index, len(jobs), target_chars, context_chars, critical_message)
                st.error(st.session_state.last_error)
                st.caption(st.session_state.last_log_hint)
                render_live_status(status_placeholder)
                render_run_log(log_placeholder)
                render_markdown_preview(preview_placeholder, title="Текущий Markdown")
                return

            processed_chunks.append(processed_chunk)
            st.session_state.processed_block_markdowns = processed_chunks.copy()
            st.session_state.markdown_preview_block_index = len(processed_chunks)
            st.session_state.latest_markdown = "\n\n".join(processed_chunks).strip()
            append_log(
                "OK",
                index,
                len(jobs),
                target_chars,
                context_chars,
                f"готово за {time.perf_counter() - started_at:.1f} сек. с начала запуска",
            )
            set_processing_status(
                stage="Блок обработан",
                detail=f"Получен ответ для блока {index}. Обновляю промежуточный Markdown.",
                current_block=index,
                block_count=len(jobs),
                target_chars=target_chars,
                context_chars=context_chars,
                progress=index / len(jobs),
                is_running=True,
            )
            push_activity(f"Блок {index} обработан успешно.")
            log_event(
                logging.INFO,
                "block_completed",
                "Блок обработан успешно",
                filename=uploaded_file.name,
                block_index=index,
                block_count=len(jobs),
                target_chars=int(job["target_chars"]),
                context_chars=int(job["context_chars"]),
                output_chars=len(processed_chunk),
            )
            render_live_status(status_placeholder)
            render_run_log(log_placeholder)
            render_markdown_preview(preview_placeholder, title="Текущий Markdown")

        if len(processed_chunks) != len(jobs):
            critical_message = present_error(
                "processed_block_count_mismatch",
                RuntimeError("Количество обработанных блоков не совпало с планом обработки."),
                "Критическая ошибка финализации",
                filename=uploaded_file.name,
                processed_count=len(processed_chunks),
                planned_count=len(jobs),
            )
            st.session_state.last_error = critical_message
            finalize_processing_status("Критическая ошибка", critical_message, len(processed_chunks) / len(jobs))
            push_activity("Обнаружено несоответствие количества обработанных блоков.")
            append_log("ERROR", len(processed_chunks), len(jobs), len(st.session_state.latest_markdown), 0, critical_message)
            st.error(st.session_state.last_error)
            st.caption(st.session_state.last_log_hint)
            render_live_status(status_placeholder)
            render_run_log(log_placeholder)
            render_markdown_preview(preview_placeholder, title="Текущий Markdown")
            return

        final_markdown = "\n\n".join(processed_chunks).strip()
        st.session_state.latest_markdown = final_markdown
        set_processing_status(
            stage="Сборка DOCX",
            detail="Все блоки готовы. Собираю итоговый DOCX из Markdown.",
            current_block=len(jobs),
            block_count=len(jobs),
            target_chars=len(final_markdown),
            context_chars=0,
            progress=1.0,
            is_running=True,
        )
        push_activity("Все блоки готовы. Начата сборка итогового DOCX.")
        render_live_status(status_placeholder)
        render_run_log(log_placeholder)
        render_markdown_preview(preview_placeholder, title="Текущий Markdown")

        try:
            docx_bytes = convert_markdown_to_docx_bytes(final_markdown)
        except Exception as exc:
            error_message = present_error(
                "docx_build_failed",
                exc,
                "Ошибка сборки DOCX",
                filename=uploaded_file.name,
                final_markdown_chars=len(final_markdown),
            )
            st.session_state.last_error = error_message
            finalize_processing_status("Ошибка сборки DOCX", error_message, 1.0)
            push_activity("Ошибка на этапе сборки DOCX.")
            append_log("ERROR", len(jobs), len(jobs), len(final_markdown), 0, error_message)
            st.error(st.session_state.last_error)
            st.caption(st.session_state.last_log_hint)
            render_live_status(status_placeholder)
            render_run_log(log_placeholder)
            render_markdown_preview(preview_placeholder, title="Текущий Markdown")
            return

        if not docx_bytes:
            critical_message = present_error(
                "empty_docx_bytes",
                RuntimeError("Сборка DOCX завершилась без содержимого файла."),
                "Критическая ошибка сборки DOCX",
                filename=uploaded_file.name,
            )
            st.session_state.last_error = critical_message
            finalize_processing_status("Критическая ошибка", critical_message, 1.0)
            push_activity("DOCX собран без содержимого.")
            append_log("ERROR", len(jobs), len(jobs), len(final_markdown), 0, critical_message)
            st.error(st.session_state.last_error)
            st.caption(st.session_state.last_log_hint)
            render_live_status(status_placeholder)
            render_run_log(log_placeholder)
            render_markdown_preview(preview_placeholder, title="Текущий Markdown")
            return

        st.session_state.latest_docx_bytes = docx_bytes
        st.session_state.last_error = ""
        finalize_processing_status(
            "Обработка завершена",
            f"Документ обработан за {time.perf_counter() - started_at:.1f} сек.",
            1.0,
        )
        push_activity("Документ обработан полностью.")
        log_event(
            logging.INFO,
            "processing_completed",
            "Документ обработан полностью",
            filename=uploaded_file.name,
            block_count=len(jobs),
            final_markdown_chars=len(final_markdown),
            elapsed_seconds=round(time.perf_counter() - started_at, 2),
        )
        append_log(
            "DONE",
            len(jobs),
            len(jobs),
            len(final_markdown),
            0,
            f"весь документ обработан за {time.perf_counter() - started_at:.1f} сек.",
        )
        render_live_status(status_placeholder)
        render_run_log(log_placeholder)
        render_result(docx_bytes, final_markdown, uploaded_file.name)


if __name__ == "__main__":
    main()