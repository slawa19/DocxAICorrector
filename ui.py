import time
from collections.abc import Mapping
from pathlib import Path
import hashlib
import re
from typing import Any

import streamlit as st

from application_flow import flatten_normalization_metrics
from config import get_text_model_default, get_text_model_options
from logger import format_elapsed
from message_formatting import derive_live_status_title_and_severity, humanize_reason, humanize_variant
from models import ImageMode
from state import (
    get_activity_feed,
    get_image_assets,
    get_image_processing_summary,
    get_latest_docx_bytes,
    get_latest_narration_text,
    get_processed_block_markdowns,
    get_processing_status,
    get_run_log,
)


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
TEXT_OPERATION_LABELS = {
    "edit": "Литературное редактирование",
    "translate": "Перевод",
    "audiobook": "Подготовка аудиокниги (ElevenLabs)",
}
TEXT_OPERATION_VALUES_BY_LABEL = {label: value for value, label in TEXT_OPERATION_LABELS.items()}
TEXT_SETTING_WIDGET_KEYS = {
    "processing_operation": "sidebar_text_operation",
    "source_language": "sidebar_source_language",
    "target_language": "sidebar_target_language",
}
_FEED_ID_SANITIZER = re.compile(r"[^a-zA-Z0-9_-]+")
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_img_\d+\]\]")



def _mdpreview_key(title: str, suffix: str) -> str:
    """Stable widget key for a markdown preview component, derived from the panel title."""
    digest = hashlib.sha1(title.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"mdpreview_{digest}_{suffix}"


def _build_output_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.docx"


def _build_markdown_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.md"


def _build_narration_filename(filename: str) -> str:
    return f"{Path(filename).stem}.tts.txt"


def _resolve_result_download_labels(
    *,
    original_filename: str,
    narration_text: str | None,
    processing_operation: str = "edit",
    audiobook_postprocess_enabled: bool = False,
) -> tuple[str, str, str | None]:
    operation = str(processing_operation or "edit").strip().lower() or "edit"

    if narration_text is not None and operation == "audiobook":
        return (
            "Markdown (для инспекции)",
            "DOCX (для инспекции)",
            "Текст для ElevenLabs (.txt)",
        )

    if operation == "translate":
        markdown_label = "Переведённый Markdown"
        docx_label = "Переведённый DOCX"
    else:
        markdown_label = "Отредактированный Markdown"
        docx_label = "Отредактированный DOCX"

    narration_label = "Текст для ElevenLabs (.txt)" if narration_text is not None and audiobook_postprocess_enabled else None
    return markdown_label, docx_label, narration_label


def _render_trusted_html(html_markup: str) -> None:
    # This helper is reserved for trusted markup assembled inside this module.
    # Dynamic user-visible values interpolated into HTML must be escaped first.
    st.markdown(html_markup, unsafe_allow_html=True)


def _get_sink(target=None):
    return target if target is not None else st


def _resolve_render_target(target, *required_methods: str):
    if target is not None and all(hasattr(target, method_name) for method_name in required_methods):
        return target
    return st


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


def render_intro_layout_styles() -> None:
    """Constrain main block container width on the idle/upload screen.

    Keeps content pressed to the sidebar while preventing it from stretching
    across very wide viewports.  The container naturally fills all available
    space (100% of stMain); the cap only activates when stMain exceeds
    1100px — i.e. viewport > ~1400px with sidebar open.
    Effective text width at cap: 1100 − 160 (Streamlit padding) = 940px.
    """
    _render_trusted_html(
        """
        <style>
        .stMain {
            align-items: flex-start !important;
        }
        [data-testid="stMainBlockContainer"] {
            max-width: 1100px;
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


def _build_normalization_caption(metrics_source) -> str:
    metrics = {
        "raw_paragraph_count": _to_int(getattr(metrics_source, "raw_paragraph_count", None), default=_to_int(metrics_source.get("raw_paragraph_count") if isinstance(metrics_source, Mapping) else None, default=0)),
        "logical_paragraph_count": _to_int(getattr(metrics_source, "logical_paragraph_count", None), default=_to_int(metrics_source.get("logical_paragraph_count") if isinstance(metrics_source, Mapping) else None, default=0)),
        "merged_group_count": _to_int(getattr(metrics_source, "merged_group_count", None), default=_to_int(metrics_source.get("merged_group_count") if isinstance(metrics_source, Mapping) else None, default=0)),
        "merged_raw_paragraph_count": _to_int(getattr(metrics_source, "merged_raw_paragraph_count", None), default=_to_int(metrics_source.get("merged_raw_paragraph_count") if isinstance(metrics_source, Mapping) else None, default=0)),
    }
    if not any(metrics.values()):
        metrics = flatten_normalization_metrics(metrics_source)
    merged_group_count = int(metrics.get("merged_group_count", 0) or 0)
    merged_raw_paragraph_count = int(metrics.get("merged_raw_paragraph_count", 0) or 0)
    if merged_group_count <= 0 and merged_raw_paragraph_count <= 0:
        return ""
    raw_paragraph_count = int(metrics.get("raw_paragraph_count", 0) or 0)
    logical_paragraph_count = int(metrics.get("logical_paragraph_count", 0) or 0)
    return (
        "Нормализация абзацев: "
        f"сырьевых {raw_paragraph_count} -> логических {logical_paragraph_count} | "
        f"слияний: {merged_group_count} групп, {merged_raw_paragraph_count} абзацев"
    )


def render_sidebar_selectbox(
    label: str,
    options: list[str],
    index: int = 0,
    *,
    help: str | None = None,
    key: str | None = None,
    disabled: bool = False,
) -> str:
    if disabled:
        return st.sidebar.selectbox(label, options, index=index, help=help, key=key, disabled=True)
    return st.sidebar.selectbox(label, options, index=index, help=help, key=key)


def get_text_setting_widget_keys() -> dict[str, str]:
    return dict(TEXT_SETTING_WIDGET_KEYS)


def _supported_language_options(config: Mapping[str, Any]) -> list[Any]:
    raw_languages = config.get("supported_languages", ())
    return [language for language in raw_languages if hasattr(language, "code") and hasattr(language, "label")]


def get_language_label_maps(config: Mapping[str, Any]) -> tuple[list[str], dict[str, str], dict[str, str]]:
    language_options = _supported_language_options(config)
    language_labels = [language.label for language in language_options]
    code_by_label = {language.label: language.code for language in language_options}
    label_by_code = {language.code: language.label for language in language_options}
    return language_labels, code_by_label, label_by_code


def get_text_operation_label(operation_code: str) -> str:
    return TEXT_OPERATION_LABELS.get(operation_code, TEXT_OPERATION_LABELS["edit"])


def get_target_language_label(config: Mapping[str, Any], language_code: str) -> str:
    language_labels, _, label_by_code = get_language_label_maps(config)
    if not language_labels:
        return language_code
    return label_by_code.get(language_code, language_labels[0])


def get_source_language_widget_value(config: Mapping[str, Any], language_code: str) -> str:
    language_labels, _, label_by_code = get_language_label_maps(config)
    if language_code == "auto":
        return "Авто"
    if not language_labels:
        return language_code
    return label_by_code.get(language_code, language_labels[0])


def resolve_source_language_from_widget_state(config: Mapping[str, Any]) -> str:
    widget_value = st.session_state.get(TEXT_SETTING_WIDGET_KEYS["source_language"])
    if widget_value == "Авто":
        return "auto"
    _, code_by_label, _ = get_language_label_maps(config)
    if isinstance(widget_value, str) and widget_value in code_by_label:
        return code_by_label[widget_value]
    return str(config.get("source_language_default", "en"))


def render_live_status(target=None) -> None:
    status = get_processing_status()
    activity_feed = get_activity_feed()
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
            normalization_caption = _build_normalization_caption(status)
            meta_lines = [
                f"Прогресс: {progress_percent}% | Источник: {'cache' if cached else 'DOCX'} | Прошло: {elapsed}",
                (
                    f"Размер: {file_size_bytes / 1024 / 1024:.2f} MB | Абзацы: {paragraph_count} | "
                    f"Изображения: {image_count} | Символы: {source_chars} | Блоки: {block_count}"
                ),
            ]
            if normalization_caption:
                meta_lines.append(normalization_caption)
            title, severity = derive_live_status_title_and_severity(status)
            _render_status_panel(
                sink=sink,
                title=title,
                stage=stage,
                detail=detail,
                meta_lines=meta_lines,
                info_level=severity,
            )
            progress_api = _resolve_render_target(target, "progress")
            progress_api.progress(progress_value)
        else:
            title, severity = derive_live_status_title_and_severity(status)
            stage = str(status.get("stage") or "Ожидание")
            detail = str(status.get("detail") or "")
            _render_status_panel(
                sink=sink,
                title=title,
                stage=stage,
                detail=detail,
                meta_lines=[],
                info_level=severity,
            )
            metric_api = _resolve_render_target(target, "columns")
            metric_columns = metric_api.columns(4)
            metric_columns[0].metric("Блок", f"{current_block}/{block_count}" if block_count else "0/0")
            metric_columns[1].metric("Цель", f"{target_chars} симв.")
            metric_columns[2].metric("Контекст", f"{context_chars} симв.")
            metric_columns[3].metric("Прошло", elapsed)
            progress_value = max(0.0, min(float(status.get("progress") or 0.0), 1.0))
            progress_api = _resolve_render_target(target, "progress")
            progress_api.progress(progress_value)


def render_preparation_summary(summary: dict[str, Any] | None, target=None) -> None:
    if not summary:
        return

    sink = _get_sink(target)
    with sink.container():
        file_size_bytes = _to_int(summary.get("file_size_bytes"), default=0)
        source_label = "cache" if bool(summary.get("cached", False)) else "DOCX"
        elapsed = str(summary.get("elapsed") or "")
        paragraph_count = _to_int(summary.get("paragraph_count"), default=0)
        image_count = _to_int(summary.get("image_count"), default=0)
        source_chars = _to_int(summary.get("source_chars"), default=0)
        block_count = _to_int(summary.get("block_count"), default=0)
        ai_classified = _to_int(summary.get("ai_classified"), default=0)
        ai_headings = _to_int(summary.get("ai_headings"), default=0)
        ai_role_changes = _to_int(summary.get("ai_role_changes"), default=0)
        ai_heading_promotions = _to_int(summary.get("ai_heading_promotions"), default=0)
        ai_heading_demotions = _to_int(summary.get("ai_heading_demotions"), default=0)
        ai_structural_role_changes = _to_int(summary.get("ai_structural_role_changes"), default=0)
        normalization_caption = _build_normalization_caption(summary)
        elapsed_fragment = f" | Подготовка: {elapsed}" if elapsed else ""
        stage = str(summary.get("stage") or "Документ подготовлен")
        secondary_stage_line = str(summary.get("secondary_stage_line") or "").strip()
        raw_status_notes = summary.get("status_notes", [])
        status_notes = [str(note).strip() for note in raw_status_notes if str(note).strip()] if isinstance(raw_status_notes, list) else []
        if secondary_stage_line:
            status_notes.insert(0, secondary_stage_line)
        detail = str(summary.get("detail") or "")
        meta_lines = [
            f"Источник: {source_label}{elapsed_fragment}",
            (
                f"{file_size_bytes / 1024 / 1024:.2f} MB | {paragraph_count} абзацев | "
                f"{image_count} изображений | {source_chars} символов | {block_count} блоков"
            ),
        ]
        if ai_classified:
            meta_lines.append(f"Распознано AI: {ai_classified} | Заголовков: {ai_headings}")
        if ai_role_changes or ai_heading_promotions or ai_heading_demotions or ai_structural_role_changes:
            meta_lines.append(
                "Расхождения с эвристикой: "
                f"ролей {ai_role_changes} | +заголовков {ai_heading_promotions} | "
                f"-заголовков {ai_heading_demotions} | структурных ролей {ai_structural_role_changes}"
            )
        if normalization_caption:
            meta_lines.append(normalization_caption)
        _render_status_panel(
            sink=sink,
            title=stage,
            stage="",
            detail=detail,
            meta_lines=status_notes + meta_lines,
        )


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


def _get_list_of_str(config: Mapping[str, Any], key: str) -> list[str]:
    value = config[key]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def render_run_log(target=None) -> None:
    run_log = get_run_log()

    if not run_log:
        return

    sink = target if target is not None else st

    @st.fragment
    def render_run_log_fragment() -> None:
        with sink.container():
            with st.expander("Журнал обработки", expanded=True):
                for entry in run_log:
                    message = str(entry.get("message") or "")
                    if not message and entry.get("kind") == "block":
                        message = (
                            f"[{entry['status']}] Блок {entry['block_index']}/{entry['block_count']} | "
                            f"цель: {entry['target_chars']} симв. | контекст: {entry['context_chars']} симв. | {entry['details']}"
                        )
                    if message:
                        st.write(message)

    render_run_log_fragment()


def render_image_validation_summary(target=None) -> None:
    summary = get_image_processing_summary()
    image_assets = get_image_assets()
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
                columns[2].metric("Откаты", fallback_count or int(summary.get("fallbacks_applied", 0)))
                columns[3].metric("Оригинал оставлен", original_images)

                if fallback_details:
                    st.caption("Причины отката:")
                    for asset in fallback_details[-5:]:
                        image_id = str(_asset_value(asset, "image_id", "unknown"))
                        final_variant = humanize_variant(str(_asset_value(asset, "final_variant", "original")))
                        final_reason = humanize_reason(str(_asset_value(asset, "final_reason", "Причина не указана.")))
                        st.caption(f"• {image_id}: оставлен {final_variant} — {final_reason}")

                validation_errors = summary.get("validation_errors", [])
                if validation_errors:
                    st.caption("Ошибки валидации:")
                    for error in validation_errors[-5:]:
                        st.caption(f"• {error}")

    render_image_validation_fragment()


def _asset_value(asset, field_name: str, default=None):
    if isinstance(asset, dict):
        return asset.get(field_name, default)
    return getattr(asset, field_name, default)


def render_sidebar(config: Mapping[str, Any]) -> tuple[str, int, int, str, bool, str, str, str, bool, bool]:
    st.sidebar.header("Настройки")
    operation_default = str(config.get("processing_operation_default", "edit"))
    operation_options = list(TEXT_OPERATION_LABELS.values())
    operation_default_label = TEXT_OPERATION_LABELS.get(operation_default, TEXT_OPERATION_LABELS["edit"])
    operation_index = operation_options.index(operation_default_label) if operation_default_label in operation_options else 0
    selected_operation_label = render_sidebar_selectbox(
        "Режим обработки текста",
        operation_options,
        index=operation_index,
        help=(
            "Литературное редактирование улучшает уже готовый текст на выбранном языке. "
            "Перевод используйте для текста, который ещё не на целевом языке. "
            "Если текст уже переведён, обычно лучше выбрать литературное редактирование."
        ),
        key="sidebar_text_operation",
    )
    processing_operation = TEXT_OPERATION_VALUES_BY_LABEL.get(selected_operation_label, "edit")

    language_labels, code_by_label, label_by_code = get_language_label_maps(config)
    default_target_code = str(config.get("target_language_default", "ru"))
    default_target_label = label_by_code.get(default_target_code, language_labels[0] if language_labels else default_target_code)
    target_index = language_labels.index(default_target_label) if default_target_label in language_labels else 0
    selected_target_label = render_sidebar_selectbox(
        "Целевой язык",
        language_labels,
        index=target_index,
        key="sidebar_target_language",
    )
    target_language = code_by_label.get(selected_target_label, default_target_code)

    source_language = resolve_source_language_from_widget_state(config)
    if processing_operation in {"translate", "audiobook"}:
        source_options = ["Авто", *language_labels]
        source_default_label = "Авто" if source_language == "auto" else label_by_code.get(source_language, source_options[0])
        source_index = source_options.index(source_default_label) if source_default_label in source_options else 0
        selected_source_label = render_sidebar_selectbox(
            "Язык оригинала",
            source_options,
            index=source_index,
            help="Используйте 'Авто' только как best-effort режим. Для уже переведённого текста обычно лучше выбрать литературное редактирование.",
            key="sidebar_source_language",
        )
        source_language = "auto" if selected_source_label == "Авто" else code_by_label.get(selected_source_label, source_language)
        if processing_operation == "translate" and source_language != "auto" and source_language == target_language:
            st.sidebar.warning(
                "Исходный и целевой язык совпадают. Если нужен только стилистический апгрейд, обычно лучше выбрать литературное редактирование."
            )

    translation_second_pass_enabled = False
    if processing_operation == "translate":
        translation_second_pass_enabled = st.sidebar.checkbox(
            "Дополнительный литературный проход после перевода",
            value=bool(config.get("translation_second_pass_default", False)),
            help=(
                "Делает второй проход только по уже переведённому тексту. "
                "Обычно улучшает стиль, но увеличивает время и стоимость обработки."
            ),
            key="sidebar_translation_second_pass",
        )
    audiobook_postprocess_enabled = False
    if processing_operation in {"edit", "translate"}:
        audiobook_postprocess_enabled = st.sidebar.checkbox(
            "Подготовить для ElevenLabs аудиокниги",
            value=bool(config.get("audiobook_postprocess_default", False)),
            help="Готовит отдельный narration text для ElevenLabs без изменения основного DOCX/Markdown результата.",
            key="sidebar_audiobook_postprocess",
        )

    model_options = [*get_text_model_options(config), "custom"]
    default_model = get_text_model_default(config)
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
    if processing_operation == "audiobook":
        image_mode = ImageMode.NO_CHANGE.value
        selected_image_mode_label = render_sidebar_selectbox(
            "Режим обработки изображений",
            [IMAGE_MODE_LABELS[ImageMode.NO_CHANGE.value]],
            index=0,
            key="sidebar_image_mode",
            disabled=True,
        )
        st.sidebar.caption("Для режима аудиокниги изображения всегда оставляются без изменений.")
    else:
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
    return (
        model,
        chunk_size,
        max_retries,
        image_mode,
        keep_all_image_variants,
        processing_operation,
        source_language,
        target_language,
        translation_second_pass_enabled,
        audiobook_postprocess_enabled,
    )


def render_markdown_preview(
    target=None,
    *,
    title: str,
    focus_latest: bool = False,
) -> None:
    blocks = _meaningful_markdown_blocks(get_processed_block_markdowns())
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

    select_widget_key = _mdpreview_key(title, "selectbox")
    textarea_key = _mdpreview_key(title, "textarea")

    with sink.container():
        st.selectbox(
            "Markdown",
            options=list(range(1, option_count + 1)),
            index=current_selection - 1,
            format_func=lambda n: f"{n} / {option_count}",
            key=select_widget_key,
            help="На экране показывается только один Markdown-блок, чтобы интерфейс не перегружался на больших документах.",
        )
        chosen = st.session_state.get(select_widget_key, current_selection)
        if isinstance(chosen, int) and 1 <= chosen <= option_count:
            st.session_state[selected_key] = chosen
        else:
            chosen = current_selection
        st.session_state[textarea_key] = blocks[chosen - 1]
        st.text_area(
            "Markdown",
            value=blocks[chosen - 1],
            height=300,
            disabled=True,
            label_visibility="collapsed",
            key=textarea_key,
        )


def render_result(
    docx_bytes: bytes | None,
    markdown_text: str,
    original_filename: str,
    narration_text: str | None = None,
    processing_operation: str = "edit",
    audiobook_postprocess_enabled: bool = False,
) -> None:
    render_result_bundle(
        docx_bytes=docx_bytes,
        markdown_text=markdown_text,
        original_filename=original_filename,
        narration_text=narration_text,
        processing_operation=processing_operation,
        audiobook_postprocess_enabled=audiobook_postprocess_enabled,
        success_message="Документ обработан.",
    )


def render_result_bundle(
    *,
    docx_bytes: bytes | None,
    markdown_text: str,
    original_filename: str,
    narration_text: str | None = None,
    processing_operation: str = "edit",
    audiobook_postprocess_enabled: bool = False,
    success_message: str | None = None,
) -> None:
    if success_message:
        st.success(success_message)
    markdown_label, docx_label, narration_label = _resolve_result_download_labels(
        original_filename=original_filename,
        narration_text=narration_text,
        processing_operation=processing_operation,
        audiobook_postprocess_enabled=audiobook_postprocess_enabled,
    )
    if narration_text is not None:
        col_tts, col_md, col_docx = st.columns(3)
        col_tts.download_button(
            label=narration_label or "Текст для ElevenLabs (.txt)",
            data=narration_text.encode("utf-8"),
            file_name=_build_narration_filename(original_filename),
            mime="text/plain",
            on_click="ignore",
            type="primary",
            use_container_width=True,
        )
        col_md.download_button(
            label=markdown_label,
            data=markdown_text.encode("utf-8"),
            file_name=_build_markdown_filename(original_filename),
            mime="text/markdown",
            on_click="ignore",
            type="primary",
            use_container_width=True,
        )
        if docx_bytes is not None:
            col_docx.download_button(
                label=docx_label,
                data=docx_bytes,
                file_name=_build_output_filename(original_filename),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                on_click="ignore",
                type="primary",
                use_container_width=True,
            )
        return

    col_docx, col_md = st.columns(2)
    if docx_bytes is not None:
        col_docx.download_button(
            label=docx_label,
            data=docx_bytes,
            file_name=_build_output_filename(original_filename),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            on_click="ignore",
            type="primary",
            use_container_width=True,
        )
    col_md.download_button(
        label=markdown_label,
        data=markdown_text.encode("utf-8"),
        file_name=_build_markdown_filename(original_filename),
        mime="text/markdown",
        on_click="ignore",
        type="primary",
        use_container_width=True,
    )


def render_partial_result() -> None:
    if get_latest_docx_bytes() is not None or get_latest_narration_text() is not None:
        return

    if not _meaningful_markdown_blocks(get_processed_block_markdowns()):
        return

    st.warning("Доступен промежуточный Markdown-результат последнего запуска.")
    render_markdown_preview(
        title="Текущий Markdown",
        focus_latest=True,
    )
