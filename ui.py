import time
from html import escape

import streamlit as st

from generation import build_markdown_filename, build_output_filename
from logger import format_elapsed
from models import DOCX_COMPARE_VARIANT_MODE_VALUES, ImageMode, get_image_variant_bytes


IMAGE_MODE_LABELS = {
    ImageMode.SAFE.value: "Просто улучшить",
    ImageMode.SEMANTIC_REDRAW_DIRECT.value: "Креативная AI-перерисовка",
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value: "Структурная AI-перерисовка",
    ImageMode.COMPARE_ALL.value: "Сгенерировать 3 варианта",
}

IMAGE_MODE_DESCRIPTIONS = {
    ImageMode.SAFE.value: "Слегка улучшает исходную картинку без смысловой перерисовки.",
    ImageMode.SEMANTIC_REDRAW_DIRECT.value: "Делает creative redraw через vision + generate. Лучше для инфографики, композиции, цвета и сложного оформления.",
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value: "Делает content-conservative redraw в стиле office presentation. Лучше для схем, таблиц и структурных изображений.",
    ImageMode.COMPARE_ALL.value: "Строит safe, креативный и структурный варианты сразу, чтобы выбрать лучший перед итоговым DOCX.",
}

IMAGE_COMPARE_LABELS = {
    "original": "Оригинал",
    ImageMode.SAFE.value: "Просто улучшить",
    ImageMode.SEMANTIC_REDRAW_DIRECT.value: "Креативная AI-перерисовка",
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value: "Структурная AI-перерисовка",
}

IMAGE_MODE_VALUES_BY_LABEL = {label: value for value, label in IMAGE_MODE_LABELS.items()}


def _render_trusted_html(html_markup: str) -> None:
    # This helper is reserved for trusted markup assembled inside this module.
    # Dynamic user-visible values interpolated into HTML must be escaped first.
    st.markdown(html_markup, unsafe_allow_html=True)

_SIDEBAR_DD = 'section[data-testid="stSidebar"] div[data-baseweb="select"]'

# Typography fix for sidebar dropdowns.
# Keep custom typography only for the closed select control.
SIDEBAR_DROPDOWN_CSS = f"""
        /* --- Sidebar dropdown: closed state typography --- */
        {_SIDEBAR_DD},
        {_SIDEBAR_DD} > div,
        {_SIDEBAR_DD} [role="combobox"],
        {_SIDEBAR_DD} input {{
            font-family: var(--sidebar-dropdown-font-family) !important;
            font-size: var(--sidebar-dropdown-font-size) !important;
            font-weight: var(--sidebar-dropdown-font-weight) !important;
            font-style: normal !important;
            line-height: var(--sidebar-dropdown-line-height) !important;
            letter-spacing: var(--sidebar-dropdown-letter-spacing) !important;
            font-synthesis: none !important;
        }}

        {_SIDEBAR_DD} span,
        {_SIDEBAR_DD} p,
        {_SIDEBAR_DD} [data-testid="stMarkdownContainer"],
        {_SIDEBAR_DD} [data-testid="stMarkdownContainer"] p,
        {_SIDEBAR_DD} [data-testid="stMarkdownContainer"] span,
        {_SIDEBAR_DD} [data-testid="stMarkdownContainer"] div {{
            font-family: inherit !important;
            font-size: inherit !important;
            font-weight: inherit !important;
            font-style: inherit !important;
            line-height: inherit !important;
            letter-spacing: inherit !important;
            font-synthesis: inherit !important;
            color: inherit !important;
            margin: 0 !important;
        }}
"""


def inject_ui_styles() -> None:
    _render_trusted_html(
        """
        <style>
        :root {
            --accent-main: #19c6b7;
            --accent-strong: #0ea5a8;
            --accent-soft: rgba(25, 198, 183, 0.14);
            --accent-border: rgba(45, 212, 191, 0.38);
            --text-soft: rgba(226, 232, 240, 0.82);
            --sidebar-dropdown-font-family: "Source Sans Pro", sans-serif;
            --sidebar-dropdown-font-size: 1rem;
            --sidebar-dropdown-font-weight: 400;
            --sidebar-dropdown-line-height: 1.5;
            --sidebar-dropdown-letter-spacing: normal;
        }

        .stApp .main .block-container,
        section.main > div.block-container,
        div[data-testid="stMainBlockContainer"] {
            width: min(100%, 1040px);
            max-width: 1040px;
            margin-left: 0;
            margin-right: auto;
            padding-top: 2rem;
            padding-right: 2rem;
            padding-bottom: 3rem;
            padding-left: 2rem;
        }

        @media (max-width: 768px) {
            .stApp .main .block-container,
            section.main > div.block-container,
            div[data-testid="stMainBlockContainer"] {
                width: 100%;
                max-width: 100%;
                padding-top: 1.25rem;
                padding-right: 1rem;
                padding-bottom: 2rem;
                padding-left: 1rem;
            }
        }

        div[data-testid="stFileUploader"] {
            margin-top: 0.5rem;
            margin-bottom: 1rem;
        }

        .stButton > button,
        .stDownloadButton > button {
            background: linear-gradient(135deg, var(--accent-main), var(--accent-strong)) !important;
            border: 1px solid var(--accent-border) !important;
            color: #052a2b !important;
            font-weight: 700 !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover {
            border-color: var(--accent-main) !important;
            color: #031b1c !important;
        }

        .stButton > button:disabled,
        .stDownloadButton > button:disabled {
            background: rgba(100, 116, 139, 0.22) !important;
            border-color: rgba(148, 163, 184, 0.24) !important;
            color: rgba(203, 213, 225, 0.65) !important;
            box-shadow: none !important;
            cursor: not-allowed !important;
            opacity: 0.55 !important;
        }
        """
        + SIDEBAR_DROPDOWN_CSS
        + """

        div[data-testid="stProgressBar"] > div > div > div > div {
            background: linear-gradient(90deg, var(--accent-main), #67e8f9) !important;
        }

        div[data-baseweb="notification"] {
            background: var(--accent-soft) !important;
            border: 1px solid var(--accent-border) !important;
            border-radius: 14px !important;
        }

        div[data-baseweb="notification"] * {
            color: #d9fffb !important;
        }

        .live-status-card {
            background: linear-gradient(180deg, rgba(10, 18, 28, 0.95), rgba(8, 15, 24, 0.88));
            border: 1px solid var(--accent-border);
            border-radius: 16px;
            padding: 16px 18px;
            margin: 8px 0 14px 0;
            box-shadow: 0 10px 30px rgba(8, 145, 178, 0.12);
        }

        .live-status-title {
            color: #e6fffb;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 4px;
        }

        .live-status-stage {
            color: #99f6e4;
            font-size: 0.95rem;
            margin-bottom: 10px;
        }

        .live-status-meta {
            color: var(--text-soft);
            font-size: 0.88rem;
            line-height: 1.55;
        }

        .activity-feed {
            border: 1px solid rgba(45, 212, 191, 0.22);
            border-radius: 14px;
            padding: 12px 14px;
            background: rgba(15, 23, 42, 0.42);
        }

        .activity-feed-items {
            max-height: 6.2rem;
            overflow-y: auto;
            padding-right: 0.25rem;
        }

        .activity-feed-title {
            color: #d5fffb;
            font-size: 0.92rem;
            font-weight: 600;
            margin-bottom: 8px;
        }

        .activity-feed-item {
            color: var(--text-soft);
            font-size: 0.88rem;
            margin: 4px 0;
        }

        .section-gap-md {
            height: 0.9rem;
        }

        .section-gap-lg {
            height: 1.35rem;
        }
        </style>
        """,
    )


def render_section_gap(size: str = "md") -> None:
    normalized_size = "lg" if size == "lg" else "md"
    _render_trusted_html(f'<div class="section-gap-{normalized_size}"></div>')


def render_sidebar_selectbox(
    label: str,
    options: list[str],
    index: int = 0,
    *,
    help: str | None = None,
    key: str | None = None,
) -> str:
    return st.sidebar.selectbox(label, options, index=index, help=help, key=key)


def render_live_status(target=None) -> None:
    status = st.session_state.processing_status
    activity_feed = st.session_state.activity_feed
    if not status and not activity_feed:
        return

    sink = target if target is not None else st
    with sink.container():
        started_at = status.get("started_at")
        elapsed = format_elapsed(time.time() - started_at) if started_at else "00:00"
        current_block = int(status.get("current_block") or 0)
        block_count = int(status.get("block_count") or 0)
        target_chars = int(status.get("target_chars") or 0)
        context_chars = int(status.get("context_chars") or 0)
        phase = str(status.get("phase") or "processing")
        if phase == "preparing":
            file_size_bytes = int(status.get("file_size_bytes") or 0)
            paragraph_count = int(status.get("paragraph_count") or 0)
            image_count = int(status.get("image_count") or 0)
            source_chars = int(status.get("source_chars") or 0)
            cached = bool(status.get("cached", False))
            progress_percent = int(max(0.0, min(float(status.get("progress") or 0.0), 1.0)) * 100)
            preparing_lines = [
                str(status.get("detail") or "Идет анализ файла."),
                f"Прогресс: {progress_percent}%",
                f"Размер: {file_size_bytes / 1024 / 1024:.2f} MB" if file_size_bytes else "Размер: -",
                f"Абзацы: {paragraph_count}",
                f"Изображения: {image_count}",
                f"Символы: {source_chars}",
                f"Блоки: {block_count}",
                f"Источник: {'cache' if cached else 'DOCX'}",
                f"Этап: {str(status.get('stage') or 'Подготовка документа')} | Прошло: {elapsed}",
            ]
            if activity_feed:
                preparing_lines.append("Бегущие строки:")
                preparing_lines.extend(
                    f"{entry['time']}  {entry['message']}"
                    for entry in activity_feed[-5:]
                )
            items = "".join(f'<div class="activity-feed-item">{escape(line)}</div>' for line in preparing_lines)
            _render_trusted_html(
                f"""
                <div class="activity-feed">
                    <div class="activity-feed-title">Последний анализ файла</div>
                    <div class="activity-feed-items">{items}</div>
                </div>
                """
            )
        else:
            title = "Идет обработка" if status.get("is_running") else "Состояние"
            stage = escape(str(status.get("stage") or "Ожидание"))
            detail = escape(str(status.get("detail") or ""))
            _render_trusted_html(
                f"""
                <div class="live-status-card">
                    <div class="live-status-title">{title}</div>
                    <div class="live-status-stage">{stage}</div>
                    <div class="live-status-meta">{detail}</div>
                </div>
                """
            )
            metric_columns = st.columns(4)
            metric_columns[0].metric("Блок", f"{current_block}/{block_count}" if block_count else "0/0")
            metric_columns[1].metric("Цель", f"{target_chars} симв.")
            metric_columns[2].metric("Контекст", f"{context_chars} симв.")
            metric_columns[3].metric("Прошло", elapsed)
        progress_value = float(status.get("progress") or 0.0)
        if phase != "preparing":
            st.progress(progress_value)
            st.caption("Если текущий блок обрабатывается долго, это нормально: ответ OpenAI может занимать десятки секунд.")

        if activity_feed and phase != "preparing":
            items = "".join(
                f"<div class=\"activity-feed-item\">{escape(entry['time'])}  {escape(entry['message'])}</div>"
                for entry in activity_feed[-5:]
            )
            _render_trusted_html(
                f"""
                <div class="activity-feed">
                    <div class="activity-feed-title">Бегущие строки</div>
                    <div class="activity-feed-items">{items}</div>
                </div>
                """
            )


def render_preparation_summary(summary: dict[str, object] | None, target=None) -> None:
    if not summary:
        return

    sink = target if target is not None else st
    with sink.container():
        file_size_bytes = int(summary.get("file_size_bytes") or 0)
        source_label = "cache" if bool(summary.get("cached", False)) else "DOCX"
        stage = str(summary.get("stage") or "Документ подготовлен")
        elapsed = str(summary.get("elapsed") or "")
        summary_lines = [
            str(summary.get("detail") or "Анализ завершён."),
            f"Размер: {file_size_bytes / 1024 / 1024:.2f} MB" if file_size_bytes else "Размер: -",
            f"Абзацы: {int(summary.get('paragraph_count') or 0)}",
            f"Изображения: {int(summary.get('image_count') or 0)}",
            f"Символы: {int(summary.get('source_chars') or 0)}",
            f"Блоки: {int(summary.get('block_count') or 0)}",
            f"Источник: {source_label}",
            f"Этап: {stage} | Подготовка заняла: {elapsed}" if elapsed else f"Этап: {stage}",
        ]
        items = "".join(f'<div class="activity-feed-item">{escape(line)}</div>' for line in summary_lines)
        _render_trusted_html(
            f"""
            <div class="activity-feed">
                <div class="activity-feed-title">Последний анализ файла</div>
                <div class="activity-feed-items">{items}</div>
            </div>
            """
        )


def render_run_log(target=None) -> None:
    if not st.session_state.run_log:
        return

    sink = target if target is not None else st
    with sink.container():
        with st.expander("Журнал обработки", expanded=True):
            max_block_count = max(
                (entry["block_count"] for entry in st.session_state.run_log if entry["block_count"]),
                default=1,
            )
            completed_steps = sum(1 for entry in st.session_state.run_log if entry["status"] in {"OK", "DONE"})
            progress_value = min(1.0, completed_steps / max_block_count) if max_block_count else 0.0
            st.progress(progress_value)
            status = st.session_state.processing_status
            st.caption(f"Этап: {status['stage']} | {status['detail']}")
            for entry in reversed(st.session_state.run_log):
                st.write(
                    f"[{entry['status']}] Блок {entry['block_index']}/{entry['block_count']} | "
                    f"цель: {entry['target_chars']} симв. | контекст: {entry['context_chars']} симв. | {entry['details']}"
                )
            st.caption(st.session_state.last_log_hint)


def render_image_validation_summary(target=None) -> None:
    summary = st.session_state.get("image_processing_summary", st.session_state.get("image_validation_summary", {}))
    image_assets = list(st.session_state.get("image_assets", []))
    if not summary.get("total_images") and not image_assets:
        return

    total_images = int(summary.get("total_images", len(image_assets)))
    processed_images = int(summary.get("processed_images", len(image_assets)))
    fallback_count = sum(1 for asset in image_assets if str(_asset_value(asset, "final_decision", "")).startswith("fallback_"))
    modified_images = sum(1 for asset in image_assets if _asset_value(asset, "final_variant") in {"safe", "redrawn"})
    original_images = sum(1 for asset in image_assets if _asset_value(asset, "final_variant") == "original")
    fallback_details = [
        asset for asset in image_assets if str(_asset_value(asset, "final_decision", "")).startswith("fallback_")
    ]

    sink = target if target is not None else st
    with sink.container():
        with st.expander("Результаты валидации изображений", expanded=True):
            columns = st.columns(4)
            columns[0].metric("Обработано", f"{processed_images}/{total_images}")
            columns[1].metric("Изменено", modified_images)
            columns[2].metric("Fallbacks", fallback_count or int(summary.get("fallbacks_applied", 0)))
            columns[3].metric("Оригинал оставлен", original_images)

            if fallback_details:
                st.caption("Причины fallback по изображениям:")
                for asset in fallback_details[-5:]:
                    image_id = str(_asset_value(asset, "image_id", "unknown"))
                    final_variant = _asset_value(asset, "final_variant", "original")
                    final_reason = str(_asset_value(asset, "final_reason", "Причина не указана."))
                    st.caption(f"• {image_id}: {final_variant} | {final_reason}")

            validation_errors = summary.get("validation_errors", [])
            if validation_errors:
                st.caption("Ошибки валидации изображений:")
                for error in validation_errors[-5:]:
                    st.caption(f"• {error}")


def _asset_value(asset, field_name: str, default=None):
    if isinstance(asset, dict):
        return asset.get(field_name, default)
    return getattr(asset, field_name, default)


def render_image_compare_selector(target=None) -> dict[str, str]:
    image_assets = list(st.session_state.get("image_assets", []))
    comparable_assets = [asset for asset in image_assets if _asset_value(asset, "comparison_variants", {})]
    if not comparable_assets:
        return {}

    sink = target if target is not None else st
    selections: dict[str, str] = {}
    with sink.container():
        with st.expander("Сравнение вариантов изображений", expanded=True):
            st.caption("Здесь можно сравнить три сгенерированных режима и выбрать, какой вариант попадет в итоговый DOCX.")
            for asset in comparable_assets:
                image_id = str(_asset_value(asset, "image_id", "unknown"))
                st.markdown(f"**{image_id}**")
                columns = st.columns(4)

                original_bytes = _asset_value(asset, "original_bytes")
                if original_bytes:
                    columns[0].image(original_bytes, caption=IMAGE_COMPARE_LABELS["original"], use_container_width=True)

                variant_map = dict(_asset_value(asset, "comparison_variants", {}))
                ordered_modes = list(DOCX_COMPARE_VARIANT_MODE_VALUES)
                for index, mode in enumerate(ordered_modes, start=1):
                    variant = variant_map.get(mode)
                    variant_bytes = get_image_variant_bytes(variant)
                    if variant_bytes:
                        columns[index].image(variant_bytes, caption=IMAGE_COMPARE_LABELS[mode], use_container_width=True)
                    else:
                        columns[index].caption(f"{IMAGE_COMPARE_LABELS[mode]}: недоступно")

                default_choice = _asset_value(asset, "selected_compare_variant") or "original"
                option_values = ["original", *ordered_modes]
                selections[image_id] = st.radio(
                    f"Выбрать вариант для {image_id}",
                    options=option_values,
                    index=option_values.index(default_choice) if default_choice in option_values else 0,
                    format_func=lambda option: IMAGE_COMPARE_LABELS.get(option, option),
                    key=f"compare_choice_{image_id}",
                    horizontal=True,
                )
    return selections


def render_sidebar(config: dict[str, object]) -> tuple[str, int, int, str, bool]:
    st.sidebar.header("Настройки")
    model_options = [*config["model_options"], "custom"]
    default_model = str(config["default_model"])
    default_index = model_options.index(default_model) if default_model in model_options else 0
    selected_model = render_sidebar_selectbox("Модель", model_options, index=default_index, key="sidebar_model")
    custom_model = ""
    if selected_model == "custom":
        custom_model = st.sidebar.text_input("Имя модели", value=default_model).strip()

    model = custom_model or selected_model
    chunk_size = st.sidebar.slider(
        "Размер целевого блока, символов",
        min_value=3000,
        max_value=12000,
        value=int(config["chunk_size"]),
        step=500,
    )
    max_retries = st.sidebar.slider(
        "Количество retry",
        min_value=1,
        max_value=5,
        value=int(config["max_retries"]),
    )
    image_mode_default = str(config.get("image_mode_default", ImageMode.SAFE.value))
    image_mode_options = list(IMAGE_MODE_LABELS.values())
    image_mode_default_label = IMAGE_MODE_LABELS.get(image_mode_default, IMAGE_MODE_LABELS[ImageMode.SAFE.value])
    image_mode_index = image_mode_options.index(image_mode_default_label) if image_mode_default_label in image_mode_options else 0
    selected_image_mode_label = render_sidebar_selectbox(
        "Режим обработки изображений",
        image_mode_options,
        index=image_mode_index,
        key="sidebar_image_mode",
    )
    image_mode = IMAGE_MODE_VALUES_BY_LABEL.get(selected_image_mode_label, ImageMode.SAFE.value)
    st.sidebar.caption(IMAGE_MODE_DESCRIPTIONS.get(image_mode, ""))
    enable_post_redraw_validation = st.sidebar.checkbox(
        "Включить post-check validation",
        value=bool(config.get("enable_post_redraw_validation", True)),
        help="Проверяет AI-перерисовку перед вставкой в DOCX и при проблемах откатывает изображение к safe/original.",
        key="sidebar_enable_post_redraw_validation",
    )
    return model, chunk_size, max_retries, image_mode, enable_post_redraw_validation


def render_markdown_preview(target=None, *, title: str, focus_latest: bool = False) -> None:
    blocks = st.session_state.processed_block_markdowns
    if not blocks:
        return

    sink = target if target is not None else st
    option_count = len(blocks)
    st.session_state.markdown_preview_render_nonce += 1
    widget_key_base = f"markdown_preview_{st.session_state.markdown_preview_render_nonce}"
    if focus_latest and option_count:
        st.session_state.markdown_preview_block_index = option_count
    if st.session_state.markdown_preview_block_index > option_count:
        st.session_state.markdown_preview_block_index = option_count

    with sink.container():
        with st.expander(title, expanded=False):
            st.caption("На экране показывается только один Markdown-блок, чтобы интерфейс не перегружался на больших документах.")
            selected_block = st.selectbox(
                "Показать блок",
                options=list(range(1, option_count + 1)),
                index=max(0, st.session_state.markdown_preview_block_index - 1),
                key=f"{widget_key_base}_select",
            )
            st.session_state.markdown_preview_block_index = selected_block
            st.text_area(
                "Markdown блока",
                value=blocks[selected_block - 1],
                height=320,
                key=f"{widget_key_base}_text",
            )


def render_result(docx_bytes: bytes, markdown_text: str, original_filename: str) -> None:
    render_result_bundle(
        docx_bytes=docx_bytes,
        markdown_text=markdown_text,
        original_filename=original_filename,
        title=None,
        success_message="Документ обработан.",
        preview_title="Предпросмотр Markdown",
    )


def render_result_bundle(
    *,
    docx_bytes: bytes,
    markdown_text: str,
    original_filename: str,
    title: str | None,
    success_message: str | None,
    preview_title: str | None,
) -> None:
    if title:
        st.subheader(title)
    if success_message:
        st.success(success_message)
    st.download_button(
        label="Скачать итоговый DOCX",
        data=docx_bytes,
        file_name=build_output_filename(original_filename),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать итоговый Markdown",
        data=markdown_text.encode("utf-8"),
        file_name=build_markdown_filename(original_filename),
        mime="text/markdown",
        use_container_width=True,
    )
    if preview_title:
        render_markdown_preview(title=preview_title, focus_latest=True)


def render_partial_result() -> None:
    markdown_text = st.session_state.latest_markdown
    if not markdown_text or st.session_state.latest_docx_bytes is not None:
        return

    st.warning("Доступен промежуточный Markdown-результат последнего запуска.")
    render_markdown_preview(title="Текущий Markdown", focus_latest=True)
