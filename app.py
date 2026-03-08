from dotenv import load_dotenv

import logging
import time

import streamlit as st

st.set_page_config(
    page_title="AI DOCX Editor",
    layout="wide",
)

from constants import ENV_PATH
from config import get_client, load_app_config, load_system_prompt
from document import (
    build_document_text,
    build_editing_jobs,
    build_semantic_blocks,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
    reinsert_inline_images,
)
from generation import convert_markdown_to_docx_bytes, ensure_pandoc_available, generate_markdown_block
from image_analysis import analyze_image
from image_generation import generate_image_candidate
from image_validation import process_image_asset
from logger import fail_critical, log_event, present_error
from state import (
    append_image_log,
    append_log,
    finalize_processing_status,
    init_session_state,
    push_activity,
    reset_run_state,
    set_processing_status,
)
from ui import (
    inject_ui_styles,
    render_image_validation_summary,
    render_live_status,
    render_markdown_preview,
    render_partial_result,
    render_result,
    render_run_log,
    render_section_gap,
    render_sidebar,
)

load_dotenv(dotenv_path=ENV_PATH)


def process_document_images(
    *,
    image_assets,
    image_mode: str,
    config: dict[str, object],
    on_progress,
) -> list:
    if not image_assets:
        st.session_state.image_assets = []
        return []

    processed_assets = []
    st.session_state.image_assets = []
    st.session_state.image_validation_failures = []
    total_images = len(image_assets)
    for index, asset in enumerate(image_assets, start=1):
        set_processing_status(
            stage="Обработка изображений",
            detail=f"Обрабатываю изображение {index} из {total_images}.",
            current_block=index,
            block_count=total_images,
            progress=index / max(total_images, 1),
            is_running=True,
        )
        push_activity(f"Начата обработка изображения {index} из {total_images}.")
        on_progress(preview_title="Текущий Markdown")
        analysis = None
        try:
            analysis = analyze_image(
                asset.original_bytes,
                model=str(config.get("validation_model", "")),
                mime_type=asset.mime_type,
            )
            asset.analysis_result = analysis
            asset.prompt_key = analysis.prompt_key
            asset.render_strategy = analysis.render_strategy

            if image_mode == "safe" or not analysis.semantic_redraw_allowed:
                asset.safe_bytes = generate_image_candidate(asset.original_bytes, analysis, mode="safe")
                asset.validation_status = "skipped"
                asset.final_decision = "accept"
                asset.final_variant = "safe" if asset.safe_bytes else "original"
                asset.final_reason = "Изображение обработано в safe-mode."
            else:
                asset.safe_bytes = generate_image_candidate(asset.original_bytes, analysis, mode="safe")
                asset.redrawn_bytes = generate_image_candidate(asset.original_bytes, analysis, mode=image_mode)
                candidate_analysis = analyze_image(
                    asset.redrawn_bytes,
                    model=str(config.get("validation_model", "")),
                    mime_type=asset.mime_type,
                )
                asset = process_image_asset(
                    asset,
                    image_mode=image_mode,
                    config=config,
                    candidate_analysis=candidate_analysis,
                )

            validation_result = asset.validation_result if hasattr(asset, "validation_result") else None
            confidence = (
                float(getattr(validation_result, "validator_confidence", 0.0))
                if validation_result is not None
                else float(getattr(analysis, "confidence", 0.0))
            )
            append_image_log(
                image_id=asset.image_id,
                status="validated" if asset.validation_status in {"passed", "failed"} else asset.validation_status,
                decision=asset.final_decision or "accept",
                confidence=confidence,
                missing_labels=(
                    list(getattr(validation_result, "missing_labels", [])) if validation_result is not None else []
                ),
                suspicious_reasons=(
                    list(getattr(validation_result, "suspicious_reasons", [])) if validation_result is not None else []
                ),
            )
            processed_assets.append(asset)
            push_activity(
                f"Изображение {asset.image_id}: {asset.final_variant or 'original'} | {asset.final_decision or 'accept'}."
            )
        except Exception as exc:
            asset.validation_status = "error"
            asset.final_decision = "fallback_original"
            asset.final_variant = "original"
            asset.final_reason = f"image_processing_exception:{exc.__class__.__name__}"
            append_image_log(
                image_id=asset.image_id,
                status="error",
                decision=asset.final_decision,
                confidence=float(getattr(analysis, "confidence", 0.0)) if analysis is not None else 0.0,
                suspicious_reasons=[asset.final_reason],
            )
            log_event(
                logging.ERROR,
                "image_processing_failed",
                "Обработка изображения завершилась ошибкой, применен fallback на оригинал.",
                **asset.to_log_context(),
            )
            processed_assets.append(asset)

    st.session_state.image_assets = processed_assets
    return processed_assets


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
) -> bool:
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
            image_count=len(image_assets),
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
        return False

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
            on_progress(preview_title="Текущий Markdown")
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
            return False

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
            return False

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
        on_progress(preview_title="Текущий Markdown")

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
        return False

    final_markdown = "\n\n".join(processed_chunks).strip()
    st.session_state.latest_markdown = final_markdown
    processed_image_assets = process_document_images(
        image_assets=image_assets,
        image_mode=image_mode,
        config=app_config,
        on_progress=on_progress,
    )
    placeholder_integrity = inspect_placeholder_integrity(final_markdown, processed_image_assets)
    for image_id, placeholder_status in placeholder_integrity.items():
        if placeholder_status == "ok":
            continue
        log_event(
            logging.WARNING,
            "image_placeholder_mismatch",
            "Обнаружено нарушение контракта image placeholder.",
            filename=uploaded_file.name,
            image_id=image_id,
            placeholder_status=placeholder_status,
        )
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
    on_progress(preview_title="Текущий Markdown")

    try:
        docx_bytes = convert_markdown_to_docx_bytes(final_markdown)
        if processed_image_assets:
            docx_bytes = reinsert_inline_images(docx_bytes, processed_image_assets)
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
        return False

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
        return False

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
    return True


def main() -> None:
    init_session_state()
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
        paragraphs, image_assets = extract_document_content_from_docx(uploaded_file)
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
            image_count=len(image_assets),
            source_chars=len(source_text),
            chunk_size=chunk_size,
            image_mode=image_mode,
            enable_post_redraw_validation=enable_post_redraw_validation,
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
    image_validation_placeholder = st.empty()

    def refresh_processing_ui(*, preview_title: str | None = None) -> None:
        render_live_status(status_placeholder)
        render_run_log(log_placeholder)
        render_image_validation_summary(image_validation_placeholder)
        if preview_title:
            render_markdown_preview(preview_placeholder, title=preview_title)

    def stop_with_terminal_error(message: str, *, preview_title: str | None = "Текущий Markdown") -> None:
        st.error(message)
        st.caption(st.session_state.last_log_hint)
        refresh_processing_ui(preview_title=preview_title)

    refresh_processing_ui(preview_title="Предпросмотр Markdown" if not has_completed_result else None)

    render_partial_result()

    if has_completed_result:
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_file.name)

    render_section_gap("lg")
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
        refresh_processing_ui(preview_title="Текущий Markdown")

        processing_succeeded = run_document_processing(
            uploaded_file=uploaded_file,
            jobs=jobs,
            image_assets=image_assets,
            image_mode=image_mode,
            app_config=app_config,
            model=model,
            max_retries=max_retries,
            on_progress=refresh_processing_ui,
        )
        if not processing_succeeded:
            stop_with_terminal_error(st.session_state.last_error)
            return

        refresh_processing_ui()
        render_result(st.session_state.latest_docx_bytes, st.session_state.latest_markdown, uploaded_file.name)


if __name__ == "__main__":
    main()
