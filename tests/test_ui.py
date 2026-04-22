from contextlib import nullcontext

import pytest

import ui
from conftest import SessionState as SessionState  # noqa: F811


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


class FakeTarget:
    def container(self):
        return nullcontext()


class FakeLiveStatusTarget(FakeTarget):
    def __init__(self):
        self.info_calls = []
        self.warning_calls = []
        self.error_calls = []
        self.write_calls = []
        self.caption_calls = []
        self.progress_calls = []
        self.columns_calls = []

    def info(self, text):
        self.info_calls.append(text)

    def warning(self, text):
        self.warning_calls.append(text)

    def error(self, text):
        self.error_calls.append(text)

    def write(self, text):
        self.write_calls.append(text)

    def caption(self, text):
        self.caption_calls.append(text)

    def progress(self, value):
        self.progress_calls.append(value)

    def columns(self, count):
        cols = [FakeMetricTarget() for _ in range(count)]
        self.columns_calls.append(cols)
        return cols


class FakeMetricTarget:
    def __init__(self):
        self.calls = []

    def metric(self, label, value):
        self.calls.append((label, value))


class FakeProgressBar:
    def __init__(self):
        self.values = []

    def __call__(self, value):
        self.values.append(value)


def test_render_activity_feed_reverses_dom_order_for_css_autoscroll(monkeypatch):
    captions = []

    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui._render_activity_feed(
        title="События",
        lines=["10:00:00  Первое сообщение.", "10:00:02  Последнее сообщение."],
        feed_id="processing-journal-feed",
        auto_scroll=True,
    )

    assert captions == [
        "События",
        "10:00:02  Последнее сообщение.",
        "10:00:00  Первое сообщение.",
    ]


def _patch_markdown_preview_widgets(monkeypatch, session_state):
    """Patch Streamlit widgets used by render_markdown_preview; return captured calls."""
    selectbox_calls = []
    text_area_calls = []

    def fake_selectbox(label, *, options=None, index=0, key=None, help=None, **kwargs):
        selectbox_calls.append({"label": label, "options": options, "index": index, "key": key, "help": help})
        chosen = options[index] if options else None
        session_state[key] = chosen
        return chosen

    def fake_text_area(label, *, value="", height=None, disabled=False, label_visibility=None, key=None, **kwargs):
        text_area_calls.append({"label": label, "value": value, "key": key, "disabled": disabled})
        return value

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "selectbox", fake_selectbox)
    monkeypatch.setattr(ui.st, "text_area", fake_text_area)

    return selectbox_calls, text_area_calls


def test_render_markdown_preview_uses_stable_key_per_title(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["one", "two"],
    )
    selectbox_calls, _ = _patch_markdown_preview_widgets(monkeypatch, session_state)

    target = FakeTarget()
    ui.render_markdown_preview(target, title="Preview A")
    ui.render_markdown_preview(target, title="Preview B")

    assert len(selectbox_calls) == 2
    key_a = selectbox_calls[0]["key"]
    key_b = selectbox_calls[1]["key"]
    assert key_a != key_b

    selectbox_calls.clear()
    ui.render_markdown_preview(target, title="Preview A")
    assert selectbox_calls[0]["key"] == key_a


def test_render_markdown_preview_focuses_latest_block_when_requested(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["one", "[[DOCX_IMAGE_img_001]]", "three"],
    )
    selectbox_calls, text_area_calls = _patch_markdown_preview_widgets(monkeypatch, session_state)

    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert session_state[select_key] == 2
    assert selectbox_calls[0]["index"] == 1  # 0-based index for block 2


def test_render_markdown_preview_keeps_user_selection_when_focus_latest_requested(monkeypatch):
    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    last_count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "[[DOCX_IMAGE_img_001]]"],
        **{select_key: 1, last_count_key: 2},
    )
    selectbox_calls, _ = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert session_state[select_key] == 1
    assert selectbox_calls[0]["index"] == 0  # 0-based index for block 1


def test_render_markdown_preview_persists_new_user_selection(monkeypatch):
    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    last_count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "three"],
        **{select_key: 3, last_count_key: 3},
    )
    selectbox_calls, text_area_calls = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown")

    assert session_state[select_key] == 3
    assert selectbox_calls[0]["options"] == [1, 2, 3]
    assert selectbox_calls[0]["help"] is not None
    assert text_area_calls[0]["value"] == "three"
    assert text_area_calls[0]["disabled"] is True


def test_render_markdown_preview_keeps_manual_selection_when_new_block_arrives(monkeypatch):
    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    last_count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "[[DOCX_IMAGE_img_001]]"],
        **{select_key: 2, last_count_key: 2},
    )
    selectbox_calls, _ = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert session_state[select_key] == 2
    assert selectbox_calls[0]["index"] == 1  # 0-based index for block 2


def test_render_markdown_preview_autofollows_latest_when_user_keeps_latest_selected(monkeypatch):
    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    last_count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "three"],
        **{select_key: 2, last_count_key: 2},
    )
    selectbox_calls, _ = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert session_state[select_key] == 3
    assert selectbox_calls[0]["index"] == 2  # 0-based index for block 3


def test_render_markdown_preview_filters_placeholder_only_blocks_from_options(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["one", "[[DOCX_IMAGE_img_001]]", "two"],
    )
    selectbox_calls, text_area_calls = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert selectbox_calls[0]["options"] == [1, 2]
    assert selectbox_calls[0]["index"] == 1  # 0-based index for block 2 (latest)
    assert text_area_calls[0]["value"] == "two"


def test_render_markdown_preview_hides_placeholder_only_content(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["[[DOCX_IMAGE_img_001]]", "   "],
    )
    selectbox_calls, _ = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert selectbox_calls == []


def test_render_sidebar_returns_image_settings(monkeypatch):
    config = {
        "models": type(
            "Models",
            (),
            {
                "text": type("TextModels", (), {"default": "gpt-5-mini", "options": ("gpt-5.4", "gpt-5-mini")})(),
            },
        )(),
        "chunk_size": 6000,
        "max_retries": 3,
        "processing_operation_default": "edit",
        "source_language_default": "en",
        "target_language_default": "ru",
        "supported_languages": [
            type("Lang", (), {"code": "ru", "label": "Русский"})(),
            type("Lang", (), {"code": "en", "label": "English"})(),
        ],
        "image_mode_default": "semantic_redraw_direct",
        "keep_all_image_variants": False,
    }

    sidebar_calls = []
    sidebar_warnings = []
    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: sidebar_calls.append(("header", text)))
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: sidebar_calls.append(("caption", text)))
    monkeypatch.setattr(ui.st.sidebar, "warning", lambda text: sidebar_warnings.append(text))

    def fake_selectbox(label, options, index=0, format_func=None, help=None, key=None):
        sidebar_calls.append(("selectbox", label, help, tuple(options), format_func))
        if label == "Режим обработки изображений":
            return ui.IMAGE_MODE_LABELS["semantic_redraw_direct"]
        return options[index]

    monkeypatch.setattr(ui.st.sidebar, "selectbox", fake_selectbox)
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    checkbox_calls = []
    monkeypatch.setattr(
        ui.st.sidebar,
        "checkbox",
        lambda label, value, key=None, help=None: checkbox_calls.append((label, value, key, help)) or value,
    )

    result = ui.render_sidebar(config)

    assert result == ("gpt-5-mini", 6000, 3, "semantic_redraw_direct", False, "edit", "en", "ru", False)
    assert sidebar_calls == [
        ("header", "Настройки"),
        (
            "selectbox",
            "Режим обработки текста",
            "Литературное редактирование улучшает уже готовый текст на выбранном языке. Перевод используйте для текста, который ещё не на целевом языке. Если текст уже переведён, обычно лучше выбрать литературное редактирование.",
            tuple(ui.TEXT_OPERATION_LABELS.values()),
            None,
        ),
        (
            "selectbox",
            "Целевой язык",
            None,
            ("Русский", "English"),
            None,
        ),
        ("selectbox", "Модель", None, ("gpt-5.4", "gpt-5-mini", "custom"), None),
        (
            "selectbox",
            "Режим обработки изображений",
            None,
            tuple(ui.IMAGE_MODE_LABELS.values()),
            None,
        ),
        ("caption", ui.IMAGE_MODE_DESCRIPTIONS["semantic_redraw_direct"]),
    ]
    assert checkbox_calls == [
        (
            "Сохранять все варианты изображений",
            False,
            "sidebar_keep_all_image_variants",
            "Сохраняет все сгенерированные варианты изображений для последующего сравнения.",
        )
    ]
    assert sidebar_warnings == []


def test_render_sidebar_warns_when_translate_source_matches_target(monkeypatch):
    config = {
        "models": type(
            "Models",
            (),
            {
                "text": type("TextModels", (), {"default": "gpt-5-mini", "options": ("gpt-5.4", "gpt-5-mini")})(),
            },
        )(),
        "chunk_size": 6000,
        "max_retries": 3,
        "processing_operation_default": "translate",
        "source_language_default": "en",
        "target_language_default": "en",
        "supported_languages": [
            type("Lang", (), {"code": "ru", "label": "Русский"})(),
            type("Lang", (), {"code": "en", "label": "English"})(),
        ],
        "image_mode_default": "semantic_redraw_direct",
        "keep_all_image_variants": False,
    }

    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: None)
    warnings = []
    monkeypatch.setattr(ui.st.sidebar, "warning", lambda text: warnings.append(text))

    def fake_selectbox(label, options, index=0, format_func=None, help=None, key=None):
        if label == "Режим обработки текста":
            return ui.TEXT_OPERATION_LABELS["translate"]
        if label == "Целевой язык":
            return "English"
        if label == "Язык оригинала":
            return "English"
        if label == "Режим обработки изображений":
            return ui.IMAGE_MODE_LABELS["semantic_redraw_direct"]
        return options[index]

    monkeypatch.setattr(ui.st.sidebar, "selectbox", fake_selectbox)
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    checkbox_calls = []
    monkeypatch.setattr(
        ui.st.sidebar,
        "checkbox",
        lambda label, value, key=None, help=None: checkbox_calls.append((label, value, key, help)) or value,
    )

    result = ui.render_sidebar(config)

    assert result == ("gpt-5-mini", 6000, 3, "semantic_redraw_direct", False, "translate", "en", "en", False)
    assert checkbox_calls == [
        (
            "Дополнительный литературный проход после перевода",
            False,
            "sidebar_translation_second_pass",
            "Делает второй проход только по уже переведённому тексту. Обычно улучшает стиль, но увеличивает время и стоимость обработки.",
        ),
        (
            "Сохранять все варианты изображений",
            False,
            "sidebar_keep_all_image_variants",
            "Сохраняет все сгенерированные варианты изображений для последующего сравнения.",
        ),
    ]
    assert warnings == [
        "Исходный и целевой язык совпадают. Если нужен только стилистический апгрейд, обычно лучше выбрать литературное редактирование."
    ]


def test_render_sidebar_translate_mode_does_not_add_extra_caption(monkeypatch):
    config = {
        "models": type(
            "Models",
            (),
            {
                "text": type("TextModels", (), {"default": "gpt-5-mini", "options": ("gpt-5.4", "gpt-5-mini")})(),
            },
        )(),
        "chunk_size": 6000,
        "max_retries": 3,
        "processing_operation_default": "translate",
        "source_language_default": "en",
        "target_language_default": "ru",
        "supported_languages": [
            type("Lang", (), {"code": "ru", "label": "Русский"})(),
            type("Lang", (), {"code": "en", "label": "English"})(),
        ],
        "image_mode_default": "safe",
        "keep_all_image_variants": False,
    }

    captions = []
    selectbox_calls = []
    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: captions.append(text))
    monkeypatch.setattr(ui.st.sidebar, "warning", lambda text: None)

    def fake_selectbox(label, options, index=0, format_func=None, help=None, key=None):
        selectbox_calls.append((label, help))
        if label == "Режим обработки текста":
            return ui.TEXT_OPERATION_LABELS["translate"]
        if label == "Целевой язык":
            return "Русский"
        if label == "Язык оригинала":
            return "Авто"
        return options[index]

    monkeypatch.setattr(ui.st.sidebar, "selectbox", fake_selectbox)
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    checkbox_calls = []
    monkeypatch.setattr(
        ui.st.sidebar,
        "checkbox",
        lambda label, value, key=None, help=None: checkbox_calls.append((label, value, key, help)) or value,
    )

    ui.render_sidebar(config)

    assert captions == [ui.IMAGE_MODE_DESCRIPTIONS["safe"]]
    assert checkbox_calls[0][0] == "Дополнительный литературный проход после перевода"
    assert selectbox_calls[0][1] == (
        "Литературное редактирование улучшает уже готовый текст на выбранном языке. "
        "Перевод используйте для текста, который ещё не на целевом языке. "
        "Если текст уже переведён, обычно лучше выбрать литературное редактирование."
    )


def test_render_sidebar_preserves_hidden_source_language_value(monkeypatch):
    config = {
        "models": type(
            "Models",
            (),
            {
                "text": type("TextModels", (), {"default": "gpt-5-mini", "options": ("gpt-5.4", "gpt-5-mini")})(),
            },
        )(),
        "chunk_size": 6000,
        "max_retries": 3,
        "processing_operation_default": "edit",
        "source_language_default": "en",
        "target_language_default": "ru",
        "supported_languages": [
            type("Lang", (), {"code": "ru", "label": "Русский"})(),
            type("Lang", (), {"code": "en", "label": "English"})(),
        ],
        "image_mode_default": "safe",
        "keep_all_image_variants": False,
    }
    session_state = SessionState(sidebar_source_language="Авто")

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "warning", lambda text: None)
    monkeypatch.setattr(
        ui.st.sidebar,
        "selectbox",
        lambda label, options, index=0, format_func=None, help=None, key=None: options[index],
    )
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    monkeypatch.setattr(ui.st.sidebar, "checkbox", lambda label, value, key=None, help=None: value)

    result = ui.render_sidebar(config)

    assert result[6] == "auto"


def test_render_sidebar_does_not_add_recommendation_apply_button(monkeypatch):
    config = {
        "models": type(
            "Models",
            (),
            {
                "text": type("TextModels", (), {"default": "gpt-5-mini", "options": ("gpt-5.4", "gpt-5-mini")})(),
            },
        )(),
        "chunk_size": 6000,
        "max_retries": 3,
        "processing_operation_default": "edit",
        "source_language_default": "en",
        "target_language_default": "ru",
        "supported_languages": [
            type("Lang", (), {"code": "ru", "label": "Русский"})(),
            type("Lang", (), {"code": "en", "label": "English"})(),
        ],
        "image_mode_default": "safe",
        "keep_all_image_variants": False,
    }
    button_calls = []

    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: None)
    monkeypatch.setattr(ui.st.sidebar, "warning", lambda text: None)
    monkeypatch.setattr(
        ui.st.sidebar,
        "selectbox",
        lambda label, options, index=0, format_func=None, help=None, key=None: options[index],
    )
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    monkeypatch.setattr(ui.st.sidebar, "checkbox", lambda label, value, key=None, help=None: value)
    monkeypatch.setattr(ui.st.sidebar, "button", lambda *args, **kwargs: button_calls.append((args, kwargs)) or False)

    ui.render_sidebar(config)

    assert button_calls == []


def test_inject_ui_styles_does_not_inject_custom_css(monkeypatch):
    injected = []

    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html: injected.append((text, unsafe_allow_html)))

    ui.inject_ui_styles()

    assert injected == []


def test_render_file_uploader_state_styles_hides_dropzone_when_file_selected(monkeypatch):
    injected = []

    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: injected.append((text, unsafe_allow_html)))

    ui.render_file_uploader_state_styles(has_uploaded_file=True)

    assert len(injected) == 1
    css = injected[0][0]
    assert '[data-testid="stFileUploaderDropzone"]' in css
    assert 'display: none !important;' in css


def test_render_file_uploader_state_styles_does_nothing_without_file(monkeypatch):
    injected = []

    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: injected.append((text, unsafe_allow_html)))

    ui.render_file_uploader_state_styles(has_uploaded_file=False)

    assert injected == []


class FakeImageColumn:
    def __init__(self):
        self.images = []
        self.captions = []

    def image(self, payload, caption=None, use_container_width=None):
        self.images.append((payload, caption, use_container_width))

    def caption(self, text):
        self.captions.append(text)


def test_render_image_validation_summary_shows_metrics(monkeypatch):
    session_state = SessionState(
        image_processing_summary={
            "total_images": 2,
            "processed_images": 2,
            "images_validated": 2,
            "validation_passed": 1,
            "fallbacks_applied": 1,
            "validation_errors": ["img-2: validator_exception:RuntimeError"],
        },
        image_assets=[
            {
                "image_id": "img-1",
                "final_variant": "redrawn",
                "final_decision": "accept",
                "final_reason": "Validator подтвердил semantic redraw.",
            },
            {
                "image_id": "img-2",
                "final_variant": "original",
                "final_decision": "fallback_original",
                "final_reason": "candidate_image_unreadable",
            },
        ],
    )
    metrics = [FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget()]
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", lambda fn: fn)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_image_validation_summary(FakeTarget())

    assert metrics[0].calls == [("Обработано", "2/2")]
    assert metrics[1].calls == [("Изменено", 1)]
    assert metrics[2].calls == [("Откаты", 1)]
    assert metrics[3].calls == [("Оригинал оставлен", 1)]
    assert captions == [
        "Причины отката:",
        "• img-2: оставлен оригинал — изображение-кандидат не читается",
        "Ошибки валидации:",
        "• img-2: validator_exception:RuntimeError",
    ]


def test_render_live_status_shows_cache_source_for_preparation(monkeypatch):
    session_state = SessionState(
        processing_status={
            "is_running": True,
            "phase": "preparing",
            "stage": "Подготовка документа",
            "detail": "Использую кэш подготовки для текущего файла.",
            "file_size_bytes": 1048576,
            "paragraph_count": 12,
            "image_count": 2,
            "source_chars": 5000,
            "block_count": 4,
            "raw_paragraph_count": 15,
            "logical_paragraph_count": 12,
            "merged_group_count": 2,
            "merged_raw_paragraph_count": 5,
            "cached": True,
            "progress": 0.9,
            "started_at": None,
        },
        activity_feed=[{"time": "10:00:00", "message": "[Анализ] Разбор DOCX: Ищу абзацы."}],
    )
    info_calls = []
    writes = []
    captions = []
    progress_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "progress", lambda value: progress_calls.append(value))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_live_status(FakeTarget())

    assert info_calls == ["Идет анализ файла"]
    assert writes == ["Использую кэш подготовки для текущего файла."]
    assert any("Прогресс: 90%" in text for text in captions)
    assert any("Размер: 1.00 MB" in text for text in captions)
    assert any("Источник: cache" in text for text in captions)
    assert any("Нормализация абзацев: сырьевых 15 -> логических 12 | слияний: 2 групп, 5 абзацев" in text for text in captions)
    assert progress_calls == [0.9]


def test_render_preparation_summary_uses_stage_and_detail(monkeypatch):
    session_state = SessionState()
    info_calls = []
    writes = []
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_preparation_summary(
        {
            "stage": "Документ подготовлен",
            "detail": "",
            "file_size_bytes": 1048576,
            "paragraph_count": 12,
            "image_count": 2,
            "source_chars": 5000,
            "block_count": 4,
            "cached": True,
            "elapsed": "1.2 c",
            "raw_paragraph_count": 15,
            "logical_paragraph_count": 12,
            "merged_group_count": 2,
            "merged_raw_paragraph_count": 5,
        },
        FakeTarget(),
    )

    assert info_calls == ["Документ подготовлен"]
    assert writes == []
    assert any("Источник: cache | Подготовка: 1.2 c" in text for text in captions)
    assert any("1.00 MB | 12 абзацев | 2 изображений | 5000 символов | 4 блоков" in text for text in captions)
    assert any("Нормализация абзацев: сырьевых 15 -> логических 12 | слияний: 2 групп, 5 абзацев" in text for text in captions)


def test_render_preparation_summary_adds_ai_classification_line_when_available(monkeypatch):
    session_state = SessionState()
    info_calls = []
    writes = []
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_preparation_summary(
        {
            "stage": "Документ подготовлен",
            "detail": "Можно запускать обработку.",
            "file_size_bytes": 1024,
            "paragraph_count": 5,
            "image_count": 0,
            "source_chars": 120,
            "block_count": 2,
            "cached": False,
            "ai_classified": 3,
            "ai_headings": 1,
        },
        FakeTarget(),
    )

    assert info_calls == ["Документ подготовлен"]
    assert writes == ["Можно запускать обработку."]
    assert any("Распознано AI: 3 | Заголовков: 1" in text for text in captions)


def test_render_preparation_summary_adds_divergence_line_when_available(monkeypatch):
    session_state = SessionState()
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: None)
    monkeypatch.setattr(ui.st, "write", lambda text: None)
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_preparation_summary(
        {
            "stage": "Документ подготовлен",
            "detail": "Можно запускать обработку.",
            "file_size_bytes": 1024,
            "paragraph_count": 5,
            "image_count": 0,
            "source_chars": 120,
            "block_count": 2,
            "cached": False,
            "ai_classified": 3,
            "ai_headings": 1,
            "ai_role_changes": 2,
            "ai_heading_promotions": 1,
            "ai_heading_demotions": 1,
            "ai_structural_role_changes": 1,
        },
        FakeTarget(),
    )

    assert any(
        "Расхождения с эвристикой: ролей 2 | +заголовков 1 | -заголовков 1 | структурных ролей 1" in text
        for text in captions
    )


def test_render_preparation_summary_places_secondary_stage_line_inside_info_block(monkeypatch):
    session_state = SessionState()
    info_calls = []
    writes = []
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: info_calls.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_preparation_summary(
        {
            "stage": "Документ подготовлен",
            "secondary_stage_line": "После анализа файла приложение скорректировало текстовые настройки: режим: изменено с Литературное редактирование на Перевод.",
            "detail": "Можно запускать обработку.",
            "file_size_bytes": 1024,
            "paragraph_count": 5,
            "image_count": 0,
            "source_chars": 120,
            "block_count": 2,
            "cached": False,
        },
        FakeTarget(),
    )

    assert info_calls == ["Документ подготовлен"]
    assert writes == ["Можно запускать обработку."]
    assert any(
        "После анализа файла приложение скорректировало текстовые настройки: режим: изменено с Литературное редактирование на Перевод."
        in text
        for text in captions
    )
    assert any("Источник: DOCX" in text for text in captions)


def test_render_preparation_summary_renders_all_status_notes_before_meta(monkeypatch):
    session_state = SessionState()
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: None)
    monkeypatch.setattr(ui.st, "write", lambda text: None)
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_preparation_summary(
        {
            "stage": "Документ подготовлен",
            "detail": "",
            "file_size_bytes": 1024,
            "paragraph_count": 5,
            "image_count": 0,
            "source_chars": 120,
            "block_count": 2,
            "cached": False,
            "status_notes": [
                "Структура: auto-режим, эскалация в AI не потребовалась; структурный риск не найден.",
                "После анализа файла приложение скорректировало текстовые настройки.",
            ],
        },
        FakeTarget(),
    )

    assert captions[0] == "Структура: auto-режим, эскалация в AI не потребовалась; структурный риск не найден."
    assert captions[1] == "После анализа файла приложение скорректировало текстовые настройки."
    assert any("Источник: DOCX" in text for text in captions)


def test_render_live_status_shows_preparation_failure_title(monkeypatch):
    session_state = SessionState(
        processing_status={
            "is_running": False,
            "phase": "preparing",
            "stage": "Ошибка подготовки",
            "detail": "boom",
            "file_size_bytes": 0,
            "paragraph_count": 0,
            "image_count": 0,
            "source_chars": 0,
            "block_count": 0,
            "cached": False,
            "progress": 1.0,
            "started_at": None,
        },
        activity_feed=[],
    )
    error_calls = []
    writes = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "info", lambda text: (_ for _ in ()).throw(AssertionError(f"st.info should not be called for error, got: {text}")))
    monkeypatch.setattr(ui.st, "error", lambda text: error_calls.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.st, "progress", lambda *args, **kwargs: None)

    ui.render_live_status(FakeTarget())

    assert error_calls == ["Ошибка подготовки файла"]
    assert writes == ["boom"]


def test_render_live_status_uses_target_columns_progress_and_clamps_processing_progress(monkeypatch):
    session_state = SessionState(
        processing_status={
            "is_running": True,
            "phase": "processing",
            "stage": "Обработка блока",
            "detail": "Идет работа.",
            "current_block": 2,
            "block_count": 5,
            "target_chars": 100,
            "context_chars": 25,
            "progress": 1.7,
            "started_at": None,
        },
        activity_feed=[],
    )
    target = FakeLiveStatusTarget()

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "columns", lambda n: (_ for _ in ()).throw(AssertionError("st.columns should not be used")))
    monkeypatch.setattr(ui.st, "progress", lambda value: (_ for _ in ()).throw(AssertionError("st.progress should not be used")))

    ui.render_live_status(target)

    assert target.info_calls == ["Идет обработка"]
    assert target.progress_calls == [1.0]
    assert len(target.columns_calls) == 1
    assert target.columns_calls[0][0].calls == [("Блок", "2/5")]


def test_render_live_status_uses_target_warning_for_stopped_processing(monkeypatch):
    session_state = SessionState(
        processing_status={
            "is_running": False,
            "phase": "processing",
            "stage": "Нейтральный статус",
            "detail": "Пользователь остановил выполнение.",
            "progress": 1.0,
            "terminal_kind": "stopped",
            "started_at": None,
        },
        activity_feed=[],
    )
    target = FakeLiveStatusTarget()

    monkeypatch.setattr(ui.st, "session_state", session_state)

    ui.render_live_status(target)

    assert target.warning_calls == ["Обработка остановлена"]
    assert target.write_calls == ["Пользователь остановил выполнение."]


def test_render_live_status_uses_target_error_for_failed_processing(monkeypatch):
    session_state = SessionState(
        processing_status={
            "is_running": False,
            "phase": "processing",
            "stage": "Нейтральный статус",
            "detail": "boom",
            "progress": 1.0,
            "terminal_kind": "error",
            "started_at": None,
        },
        activity_feed=[],
    )
    target = FakeLiveStatusTarget()

    monkeypatch.setattr(ui.st, "session_state", session_state)

    ui.render_live_status(target)

    assert target.error_calls == ["Ошибка обработки"]
    assert target.write_calls == ["boom"]


def test_render_partial_result_shows_preview_instead_of_download(monkeypatch):
    session_state = SessionState(
        latest_markdown="chunk-1",
        processed_block_markdowns=["chunk-1"],
        latest_docx_bytes=None,
    )
    warnings = []
    previews = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "warning", lambda text: warnings.append(text))
    monkeypatch.setattr(
        ui,
        "render_markdown_preview",
        lambda *args, **kwargs: previews.append((kwargs.get("title"), kwargs.get("focus_latest"))),
    )

    ui.render_partial_result()

    assert warnings == ["Доступен промежуточный Markdown-результат последнего запуска."]
    assert previews == [("Текущий Markdown", True)]


def test_render_partial_result_hides_placeholder_only_preview(monkeypatch):
    session_state = SessionState(
        latest_markdown="[[DOCX_IMAGE_img_001]]",
        processed_block_markdowns=["[[DOCX_IMAGE_img_001]]"],
        latest_docx_bytes=None,
    )
    warnings = []
    previews = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "warning", lambda text: warnings.append(text))
    monkeypatch.setattr(ui, "render_markdown_preview", lambda *args, **kwargs: previews.append(kwargs.get("title")))

    ui.render_partial_result()

    assert warnings == []
    assert previews == []


def test_render_partial_result_enables_autofollow_for_live_preview(monkeypatch):
    session_state = SessionState(
        latest_markdown="chunk-1\n\nchunk-2\n\n[[DOCX_IMAGE_img_001]]",
        processed_block_markdowns=["chunk-1", "chunk-2", "[[DOCX_IMAGE_img_001]]"],
        latest_docx_bytes=None,
    )
    warnings = []
    preview_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "warning", lambda text: warnings.append(text))
    monkeypatch.setattr(
        ui,
        "render_markdown_preview",
        lambda *args, **kwargs: preview_calls.append((kwargs.get("title"), kwargs.get("focus_latest"))),
    )

    ui.render_partial_result()

    assert warnings == ["Доступен промежуточный Markdown-результат последнего запуска."]
    assert preview_calls == [("Текущий Markdown", True)]


def test_render_partial_result_does_not_override_user_selected_block(monkeypatch):
    select_key = ui._mdpreview_key("Текущий Markdown", "selected")
    last_count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        latest_markdown="chunk-1\n\nchunk-2\n\n[[DOCX_IMAGE_img_001]]",
        processed_block_markdowns=["chunk-1", "chunk-2", "[[DOCX_IMAGE_img_001]]"],
        latest_docx_bytes=None,
        **{select_key: 1, last_count_key: 2},
    )
    warnings = []
    preview_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "warning", lambda text: warnings.append(text))
    monkeypatch.setattr(
        ui,
        "render_markdown_preview",
        lambda *args, **kwargs: preview_calls.append((kwargs.get("title"), kwargs.get("focus_latest"))),
    )

    ui.render_partial_result()

    assert warnings == ["Доступен промежуточный Markdown-результат последнего запуска."]
    assert preview_calls == [("Текущий Markdown", True)]
    assert session_state[select_key] == 1


def test_render_markdown_preview_uses_only_selected_and_count_keys(monkeypatch):
    selected_key = ui._mdpreview_key("Текущий Markdown", "selected")
    count_key = ui._mdpreview_key("Текущий Markdown", "count")
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "three"],
    )
    _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown")

    assert session_state[selected_key] == 1
    assert session_state[count_key] == 3
    assert ui._mdpreview_key("Текущий Markdown", "follow_latest") not in session_state
    assert ui._mdpreview_key("Текущий Markdown", "last_count") not in session_state
    assert ui._mdpreview_key("Текущий Markdown", "select") not in session_state


def test_render_run_log_shows_entries_in_chronological_order(monkeypatch):
    session_state = SessionState(
        run_log=[
            {"kind": "block", "status": "OK", "block_index": 1, "block_count": 3, "target_chars": 10, "context_chars": 2, "details": "first", "message": "[OK] Блок 1/3 | цель: 10 симв. | контекст: 2 симв. | first"},
            {"kind": "block", "status": "OK", "block_index": 2, "block_count": 3, "target_chars": 12, "context_chars": 3, "details": "second", "message": "[OK] Блок 2/3 | цель: 12 симв. | контекст: 3 симв. | second"},
        ],
        activity_feed=[{"time": "10:00:00", "message": "Блок 2 отправлен в OpenAI."}],
        processing_status={"stage": "Блок обработан", "detail": "Последний блок готов.", "progress": 0.1, "phase": "processing"},
        last_log_hint="hint",
    )
    writes = []
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", lambda fn: fn)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))

    ui.render_run_log(FakeTarget())

    assert captions == []
    assert writes[0].endswith("first")
    assert writes[1].endswith("second")


def test_render_run_log_shows_image_entries(monkeypatch):
    session_state = SessionState(
        run_log=[
            {"kind": "image", "status": "IMG WARN", "message": "[IMG WARN] Изображение img-2 | оставлен оригинал | ошибка валидации"},
        ],
        activity_feed=[],
        processing_status={"phase": "processing"},
    )
    writes = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", lambda fn: fn)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))

    ui.render_run_log(FakeTarget())

    assert writes == ["[IMG WARN] Изображение img-2 | оставлен оригинал | ошибка валидации"]


def test_render_run_log_ignores_processing_activity_without_block_entries(monkeypatch):
    session_state = SessionState(
        run_log=[],
        activity_feed=[{"time": "10:00:00", "message": "Запуск обработки документа."}],
        processing_status={"stage": "Инициализация", "detail": "Проверяю окружение.", "progress": 0.0, "phase": "processing"},
        last_log_hint="hint",
    )
    writes = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", lambda fn: fn)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))

    ui.render_run_log(FakeTarget())

    assert writes == []


def test_render_run_log_skips_activity_feed_when_run_log_empty(monkeypatch):
    session_state = SessionState(
        run_log=[],
        activity_feed=[{"time": "10:00:00", "message": "[Анализ] Разбор DOCX: Ищу абзацы."}],
        processing_status={"stage": "Подготовка документа", "detail": "Идет анализ файла.", "progress": 0.9, "phase": "preparing"},
        last_log_hint="hint",
    )
    fragment_calls = []

    def fake_fragment(fn):
        fragment_calls.append(fn.__name__)
        return fn

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", fake_fragment)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())

    ui.render_run_log(FakeTarget())

    assert fragment_calls == []


def test_render_result_bundle_uses_manual_preview_mode(monkeypatch):
    download_calls = []

    monkeypatch.setattr(ui.st, "session_state", SessionState())
    monkeypatch.setattr(ui.st, "success", lambda *args, **kwargs: None)

    class FakeColumn:
        def __init__(self):
            self.calls = []
        def download_button(self, *args, **kwargs):
            self.calls.append(kwargs)

    cols = [FakeColumn(), FakeColumn()]
    monkeypatch.setattr(ui.st, "columns", lambda n: cols)

    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        success_message="Документ обработан.",
    )

    assert len(cols[0].calls) == 1
    assert len(cols[1].calls) == 1
    assert all(call.get("on_click") == "ignore" for call in cols[0].calls + cols[1].calls)


def test_render_result_bundle_shows_downloads_in_columns(monkeypatch):
    success_calls = []

    monkeypatch.setattr(ui.st, "session_state", SessionState())
    monkeypatch.setattr(ui.st, "success", lambda msg: success_calls.append(msg))

    class FakeColumn:
        def __init__(self):
            self.calls = []
        def download_button(self, *args, **kwargs):
            self.calls.append(kwargs)

    cols = [FakeColumn(), FakeColumn()]
    monkeypatch.setattr(ui.st, "columns", lambda n: cols)

    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        success_message="Документ обработан.",
    )

    assert success_calls == ["Документ обработан."]
    assert len(cols[0].calls) == 1
    assert len(cols[1].calls) == 1
    assert "DOCX" in cols[0].calls[0]["label"]
    assert cols[0].calls[0]["type"] == "primary"
    assert "Markdown" in cols[1].calls[0]["label"]


def test_render_markdown_preview_renders_native_widgets(monkeypatch):
    session_state = SessionState(processed_block_markdowns=["one"])
    selectbox_calls, text_area_calls = _patch_markdown_preview_widgets(monkeypatch, session_state)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown")

    assert len(selectbox_calls) == 1
    assert len(text_area_calls) == 1
    assert text_area_calls[0]["disabled"] is True
    assert text_area_calls[0]["value"] == "one"


def test_render_run_log_renders_inside_fragment(monkeypatch):
    session_state = SessionState(
        run_log=[{"status": "OK", "block_index": 1, "block_count": 1, "target_chars": 10, "context_chars": 2, "details": "done"}],
        activity_feed=[],
        processing_status={"phase": "processing"},
    )
    fragment_calls = []

    def fake_fragment(fn):
        fragment_calls.append(fn.__name__)
        return fn

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", fake_fragment)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "write", lambda *args, **kwargs: None)

    ui.render_run_log(FakeTarget())

    assert fragment_calls == ["render_run_log_fragment"]


def test_render_image_validation_summary_renders_inside_fragment(monkeypatch):
    session_state = SessionState(
        image_processing_summary={"total_images": 1, "processed_images": 1, "fallbacks_applied": 0, "validation_errors": []},
        image_assets=[{"image_id": "img-1", "final_variant": "original", "final_decision": "accept"}],
    )
    fragment_calls = []
    metrics = [FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget()]

    def fake_fragment(fn):
        fragment_calls.append(fn.__name__)
        return fn

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "fragment", fake_fragment)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "caption", lambda *args, **kwargs: None)

    ui.render_image_validation_summary(FakeTarget())

    assert fragment_calls == ["render_image_validation_fragment"]
