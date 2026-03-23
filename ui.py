import time
from collections.abc import Mapping
from html import escape
import json
from pathlib import Path
import hashlib
import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from logger import format_elapsed
from models import ImageMode


IMAGE_MODE_LABELS = {
    ImageMode.NO_CHANGE.value: "Без изменения",
    ImageMode.SAFE.value: "Просто улучшить",
    ImageMode.SEMANTIC_REDRAW_DIRECT.value: "Креативная AI-перерисовка",
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value: "Структурная AI-перерисовка",
    ImageMode.COMPARE_ALL.value: "Сгенерировать 3 варианта",
}

IMAGE_MODE_DESCRIPTIONS = {
    ImageMode.NO_CHANGE.value: "Оставляет все изображения как есть, без какой-либо обработки.",
    ImageMode.SAFE.value: "Слегка улучшает исходную картинку без смысловой перерисовки.",
    ImageMode.SEMANTIC_REDRAW_DIRECT.value: "Делает creative redraw через vision + generate. Лучше для инфографики, композиции, цвета и сложного оформления.",
    ImageMode.SEMANTIC_REDRAW_STRUCTURED.value: "Делает content-conservative redraw в стиле office presentation. Лучше для схем, таблиц и структурных изображений.",
    ImageMode.COMPARE_ALL.value: "Строит safe, креативный и структурный варианты сразу, чтобы выбрать лучший перед итоговым DOCX.",
}

IMAGE_MODE_VALUES_BY_LABEL = {label: value for value, label in IMAGE_MODE_LABELS.items()}
_FEED_ID_SANITIZER = re.compile(r"[^a-zA-Z0-9_-]+")
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_img_\d+\]\]")
_MARKDOWN_PREVIEW_THEME_CSS = """
    <style>
    :root {{
        color-scheme: dark;
    }}
    html, body {{
        margin: 0;
        padding: 0;
        background: transparent;
    }}
    body {{
        color: CanvasText;
    }}
    .md-preview-shell {{
        display: grid;
        gap: 0.75rem;
        padding: 0.25rem 0.125rem 0.5rem 0.125rem;
    }}
    .md-preview-caption {{
        line-height: 1.5;
    }}
    .md-preview-label {{
        display: block;
        font-weight: 600;
    }}
    .md-preview-select,
    .md-preview-text {{
        width: 100%;
        box-sizing: border-box;
    }}
    .md-preview-select {{
        min-height: 2.5rem;
    }}
    .md-preview-text {{
        min-height: 20rem;
        resize: vertical;
        white-space: pre-wrap;
    }}
    </style>
"""


def _mdpreview_key(title: str, suffix: str) -> str:
    """Stable widget key for a markdown preview component, derived from the panel title."""
    digest = hashlib.sha1(title.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"mdpreview_{digest}_{suffix}"


def _build_output_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.docx"


def _build_markdown_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.md"


def _render_trusted_html(html_markup: str) -> None:
    # This helper is reserved for trusted markup assembled inside this module.
    # Dynamic user-visible values interpolated into HTML must be escaped first.
    st.markdown(html_markup, unsafe_allow_html=True)


def _get_sink(target=None):
    return target if target is not None else st


def render_file_uploader_state_styles(*, has_uploaded_file: bool) -> None:
    if not has_uploaded_file:
        return

    _render_trusted_html(
        """
        <style>
        div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
            display: none !important;
        }

        div[data-testid="stFileUploader"] {
            margin-bottom: 0 !important;
        }
        </style>
        """
    )


def _build_feed_id(prefix: str) -> str:
    nonce = int(time.time() * 1000)
    safe_prefix = _FEED_ID_SANITIZER.sub("-", prefix).strip("-") or "feed"
    return f"{safe_prefix}-{nonce}"


def _strip_docx_image_placeholders(markdown_text: str) -> str:
    return _DOCX_IMAGE_PLACEHOLDER_PATTERN.sub("", markdown_text).strip()


def _meaningful_markdown_blocks(blocks: list[str]) -> list[str]:
    return [block for block in blocks if _strip_docx_image_placeholders(block)]


def _build_markdown_preview_script(*, blocks_json: str, initial_selection: int, safe_storage_key: str) -> str:
    return f"""
    <script>
    (() => {{
        const blocks = {blocks_json};
        const storageKey = "{safe_storage_key}";
        const select = document.getElementById("md-preview-select-{safe_storage_key}");
        const textarea = document.getElementById("md-preview-text-{safe_storage_key}");
        if (!select || !textarea || !Array.isArray(blocks) || blocks.length === 0) {{
            return;
        }}

        const updateTextarea = (selectedIndex) => {{
            const resolvedIndex = Math.max(1, Math.min(selectedIndex, blocks.length));
            textarea.value = blocks[resolvedIndex - 1] || "";
            textarea.scrollTop = 0;
            select.value = String(resolvedIndex);
            try {{
                window.localStorage.setItem(storageKey, String(resolvedIndex));
            }} catch (error) {{
            }}
        }};

        try {{
            const persistedIndex = Number.parseInt(window.localStorage.getItem(storageKey) || "", 10);
            if (Number.isFinite(persistedIndex)) {{
                updateTextarea(persistedIndex);
            }} else {{
                updateTextarea(Number.parseInt(select.value, 10) || {initial_selection});
            }}
        }} catch (error) {{
            updateTextarea(Number.parseInt(select.value, 10) || {initial_selection});
        }}

        select.addEventListener("change", (event) => {{
            const nextIndex = Number.parseInt(event.target.value, 10) || 1;
            updateTextarea(nextIndex);
        }});
    }})();
    </script>
    """


def _build_markdown_preview_markup(*, options_markup: str, initial_block: str, safe_storage_key: str) -> str:
    return f"""
    <div class="md-preview-shell">
        <div class="md-preview-caption">На экране показывается только один Markdown-блок, чтобы интерфейс не перегружался на больших документах.</div>
        <label class="md-preview-label" for="md-preview-select-{safe_storage_key}">Показать блок</label>
        <select id="md-preview-select-{safe_storage_key}" class="md-preview-select">{options_markup}</select>
        <label class="md-preview-label" for="md-preview-text-{safe_storage_key}">Markdown блока</label>
        <textarea id="md-preview-text-{safe_storage_key}" class="md-preview-text" readonly>{initial_block}</textarea>
    </div>
    """


def _build_markdown_preview_html(*, blocks: list[str], initial_selection: int, storage_key: str) -> str:
    options_markup = "".join(
        f'<option value="{index}"{" selected" if index == initial_selection else ""}>{index}</option>'
        for index in range(1, len(blocks) + 1)
    )
    blocks_json = json.dumps(blocks, ensure_ascii=False)
    initial_block = escape(blocks[initial_selection - 1])
    safe_storage_key = escape(storage_key)
    return (
        _build_markdown_preview_markup(
            options_markup=options_markup,
            initial_block=initial_block,
            safe_storage_key=safe_storage_key,
        )
        + _build_markdown_preview_script(
            blocks_json=blocks_json,
            initial_selection=initial_selection,
            safe_storage_key=safe_storage_key,
        )
        + _MARKDOWN_PREVIEW_THEME_CSS
    )


def _render_activity_feed(*, title: str, lines: list[str], feed_id: str | None = None, auto_scroll: bool = False) -> None:
    if not lines:
        return

    st.caption(title)
    for line in reversed(lines):
        st.caption(line)

def inject_ui_styles() -> None:
    return None


def render_section_gap(size: str = "md") -> None:
    gap_lines = 2 if size == "lg" else 1
    for _ in range(gap_lines):
        st.write("")


def _render_status_panel(*, sink, title: str, stage: str, detail: str, meta_lines: list[str], info_level: str = "info") -> None:
    render_api = sink if hasattr(sink, info_level) and hasattr(sink, "caption") and hasattr(sink, "write") else st
    panel = getattr(render_api, info_level)
    panel(title)
    if stage:
        render_api.caption(stage)
    if detail:
        render_api.write(detail)
    for meta_line in meta_lines:
        render_api.caption(meta_line)


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

    sink = _get_sink(target)
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
            progress_value = max(0.0, min(float(status.get("progress") or 0.0), 1.0))
            progress_percent = int(progress_value * 100)
            stage = str(status.get("stage") or "Подготовка документа")
            detail = str(status.get("detail") or "Идет анализ файла.")
            title = "Идет анализ файла" if status.get("is_running") else "Анализ файла завершён"
            _render_status_panel(
                sink=sink,
                title=title,
                stage=stage,
                detail=detail,
                meta_lines=[
                    f"Прогресс: {progress_percent}% | Источник: {'cache' if cached else 'DOCX'} | Прошло: {elapsed}",
                    (
                        f"Размер: {file_size_bytes / 1024 / 1024:.2f} MB | Абзацы: {paragraph_count} | "
                        f"Изображения: {image_count} | Символы: {source_chars} | Блоки: {block_count}"
                    ),
                ],
            )
            st.progress(progress_value)
        else:
            title = "Идет обработка" if status.get("is_running") else "Состояние"
            stage = str(status.get("stage") or "Ожидание")
            detail = str(status.get("detail") or "")
            _render_status_panel(
                sink=sink,
                title=title,
                stage=stage,
                detail=detail,
                meta_lines=[],
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


def render_preparation_summary(summary: dict[str, object] | None, target=None) -> None:
    if not summary:
        return

    sink = _get_sink(target)
    with sink.container():
        progress_value = max(0.0, min(_to_float(summary.get("progress"), default=0.0), 1.0))
        progress_percent = int(progress_value * 100)
        file_size_bytes = _to_int(summary.get("file_size_bytes"), default=0)
        source_label = "cache" if bool(summary.get("cached", False)) else "DOCX"
        stage = str(summary.get("stage") or "Документ подготовлен")
        elapsed = str(summary.get("elapsed") or "")
        paragraph_count = _to_int(summary.get("paragraph_count"), default=0)
        image_count = _to_int(summary.get("image_count"), default=0)
        source_chars = _to_int(summary.get("source_chars"), default=0)
        block_count = _to_int(summary.get("block_count"), default=0)
        elapsed_fragment = f" | Подготовка заняла: {elapsed}" if elapsed else ""
        _render_status_panel(
            sink=sink,
            title="Анализ файла завершён",
            stage=stage,
            detail=str(summary.get("detail") or "Анализ завершён."),
            meta_lines=[
                f"Прогресс: {progress_percent}% | Источник: {source_label}{elapsed_fragment}",
                (
                    f"Размер: {file_size_bytes / 1024 / 1024:.2f} MB | Абзацы: {paragraph_count} | "
                    f"Изображения: {image_count} | Символы: {source_chars} | Блоки: {block_count}"
                ),
            ],
        )
        st.progress(progress_value)


def _to_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _to_float(value: Any, *, default: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _get_list_of_str(config: Mapping[str, object], key: str) -> list[str]:
    value = config[key]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def render_run_log(target=None) -> None:
    run_log = list(st.session_state.get("run_log", []))
    activity_feed = list(st.session_state.get("activity_feed", []))
    status = dict(st.session_state.get("processing_status", {}))
    phase = str(status.get("phase") or "processing")
    show_processing_activity = bool(activity_feed) and phase != "preparing"

    if not run_log and not show_processing_activity:
        return

    sink = target if target is not None else st

    @st.fragment
    def render_run_log_fragment() -> None:
        with sink.container():
            with st.expander("Журнал обработки", expanded=True):
                if show_processing_activity:
                    _render_activity_feed(
                        title="События",
                        lines=[f"{entry['time']}  {entry['message']}" for entry in activity_feed],
                        feed_id="processing-journal-feed",
                        auto_scroll=True,
                    )
                for entry in run_log:
                    st.write(
                        f"[{entry['status']}] Блок {entry['block_index']}/{entry['block_count']} | "
                        f"цель: {entry['target_chars']} симв. | контекст: {entry['context_chars']} симв. | {entry['details']}"
                    )

    render_run_log_fragment()


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

    @st.fragment
    def render_image_validation_fragment() -> None:
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

    render_image_validation_fragment()


def _asset_value(asset, field_name: str, default=None):
    if isinstance(asset, dict):
        return asset.get(field_name, default)
    return getattr(asset, field_name, default)


def render_sidebar(config: Mapping[str, object]) -> tuple[str, int, int, str, bool]:
    st.sidebar.header("Настройки")
    model_options = [*_get_list_of_str(config, "model_options"), "custom"]
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
        value=_to_int(config["chunk_size"], default=6000),
        step=500,
    )
    max_retries = st.sidebar.slider(
        "Количество retry",
        min_value=1,
        max_value=5,
        value=_to_int(config["max_retries"], default=3),
    )
    image_mode_default = str(config.get("image_mode_default", ImageMode.NO_CHANGE.value))
    image_mode_options = list(IMAGE_MODE_LABELS.values())
    image_mode_default_label = IMAGE_MODE_LABELS.get(image_mode_default, IMAGE_MODE_LABELS[ImageMode.NO_CHANGE.value])
    image_mode_index = image_mode_options.index(image_mode_default_label) if image_mode_default_label in image_mode_options else 0
    selected_image_mode_label = render_sidebar_selectbox(
        "Режим обработки изображений",
        image_mode_options,
        index=image_mode_index,
        key="sidebar_image_mode",
    )
    image_mode = IMAGE_MODE_VALUES_BY_LABEL.get(selected_image_mode_label, ImageMode.NO_CHANGE.value)
    st.sidebar.caption(IMAGE_MODE_DESCRIPTIONS.get(image_mode, ""))
    keep_all_image_variants = st.sidebar.checkbox(
        "Сохранять все варианты изображений",
        value=bool(config.get("keep_all_image_variants", False)),
        help="Сохраняет все сгенерированные варианты изображений для последующего сравнения.",
        key="sidebar_keep_all_image_variants",
    )
    return model, chunk_size, max_retries, image_mode, keep_all_image_variants


def render_markdown_preview(
    target=None,
    *,
    title: str,
    focus_latest: bool = False,
) -> None:
    blocks = _meaningful_markdown_blocks(list(st.session_state.get("processed_block_markdowns", [])))
    if not blocks:
        return

    sink = target if target is not None else st
    option_count = len(blocks)

    selected_key = _mdpreview_key(title, "selected")
    last_count_key = _mdpreview_key(title, "count")

    last_known_count = int(st.session_state.get(last_count_key, 0))
    new_block_arrived = option_count > last_known_count
    current_selection = st.session_state.get(selected_key)
    if not isinstance(current_selection, int) or not (1 <= current_selection <= option_count):
        current_selection = option_count if focus_latest else 1
    elif focus_latest and new_block_arrived and current_selection == last_known_count:
        current_selection = option_count

    st.session_state[selected_key] = current_selection
    st.session_state[last_count_key] = option_count

    with sink.container():
        with st.expander(title, expanded=False):
            components.html(
                _build_markdown_preview_html(
                    blocks=blocks,
                    initial_selection=current_selection,
                    storage_key=_mdpreview_key(title, "client_selected"),
                ),
                height=460,
                scrolling=False,
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
    latest_result_notice = st.session_state.get("latest_result_notice")
    if isinstance(latest_result_notice, dict):
        notice_level = str(latest_result_notice.get("level") or "").strip().lower()
        notice_message = str(latest_result_notice.get("message") or "").strip()
        if notice_message and notice_level == "info":
            st.info(notice_message)
    st.download_button(
        label="Скачать итоговый DOCX",
        data=docx_bytes,
        file_name=_build_output_filename(original_filename),
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        on_click="ignore",
        use_container_width=True,
    )
    st.download_button(
        label="Скачать итоговый Markdown",
        data=markdown_text.encode("utf-8"),
        file_name=_build_markdown_filename(original_filename),
        mime="text/markdown",
        on_click="ignore",
        use_container_width=True,
    )
    if preview_title:
        render_markdown_preview(title=preview_title)


def render_partial_result() -> None:
    if st.session_state.latest_docx_bytes is not None:
        return

    if not _meaningful_markdown_blocks(list(st.session_state.get("processed_block_markdowns", []))):
        return

    st.warning("Доступен промежуточный Markdown-результат последнего запуска.")
    render_markdown_preview(
        title="Текущий Markdown",
        focus_latest=True,
    )
