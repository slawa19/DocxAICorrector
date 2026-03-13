from contextlib import nullcontext

import ui


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class FakeTarget:
    def container(self):
        return nullcontext()


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


def test_render_markdown_preview_uses_unique_widget_keys_on_repeat(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["one", "two"],
        markdown_preview_block_index=1,
        markdown_preview_render_nonce=0,
    )
    select_keys = []
    text_keys = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ui.st,
        "selectbox",
        lambda label, options, index, key: select_keys.append(key) or options[index],
    )
    monkeypatch.setattr(
        ui.st,
        "text_area",
        lambda label, value, height, key: text_keys.append(key),
    )

    target = FakeTarget()
    ui.render_markdown_preview(target, title="Текущий Markdown")
    ui.render_markdown_preview(target, title="Текущий Markdown")

    assert select_keys == ["markdown_preview_1_select", "markdown_preview_2_select"]
    assert text_keys == ["markdown_preview_1_text", "markdown_preview_2_text"]
    assert session_state.markdown_preview_render_nonce == 2


def test_render_markdown_preview_focuses_latest_block_when_requested(monkeypatch):
    session_state = SessionState(
        processed_block_markdowns=["one", "two", "three"],
        markdown_preview_block_index=1,
        markdown_preview_render_nonce=0,
    )
    select_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ui.st,
        "selectbox",
        lambda label, options, index, key: select_calls.append((tuple(options), index, key)) or options[index],
    )
    monkeypatch.setattr(ui.st, "text_area", lambda *args, **kwargs: None)

    ui.render_markdown_preview(FakeTarget(), title="Текущий Markdown", focus_latest=True)

    assert session_state.markdown_preview_block_index == 3
    assert select_calls == [((1, 2, 3), 2, "markdown_preview_1_select")]


def test_render_sidebar_returns_image_settings(monkeypatch):
    config = {
        "model_options": ["gpt-5.4", "gpt-5-mini"],
        "default_model": "gpt-5-mini",
        "chunk_size": 6000,
        "max_retries": 3,
        "image_mode_default": "semantic_redraw_direct",
        "keep_all_image_variants": False,
    }

    sidebar_calls = []
    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: sidebar_calls.append(("header", text)))
    monkeypatch.setattr(ui.st.sidebar, "caption", lambda text: sidebar_calls.append(("caption", text)))

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

    assert result == ("gpt-5-mini", 6000, 3, "semantic_redraw_direct", False)
    assert sidebar_calls == [
        ("header", "Настройки"),
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


def test_inject_ui_styles_normalizes_selectbox_typography(monkeypatch):
    injected = []

    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html: injected.append((text, unsafe_allow_html)))

    ui.inject_ui_styles()

    assert injected == [(injected[0][0], True)]
    css = injected[0][0]
    assert 'section[data-testid="stSidebar"] div[data-baseweb="select"] [data-testid="stMarkdownContainer"] p' in css
    assert 'font-weight: var(--sidebar-dropdown-font-weight) !important;' in css
    assert 'color: inherit !important;' in css


class FakeImageColumn:
    def __init__(self):
        self.images = []
        self.captions = []

    def image(self, payload, caption=None, use_container_width=None):
        self.images.append((payload, caption, use_container_width))

    def caption(self, text):
        self.captions.append(text)


def test_render_image_compare_selector_returns_current_selections(monkeypatch):
    session_state = SessionState(
        image_assets=[
            {
                "image_id": "img_001",
                "original_bytes": b"orig",
                "selected_compare_variant": "semantic_redraw_direct",
                "comparison_variants": {
                    "safe": {"bytes": b"safe"},
                    "semantic_redraw_direct": {"bytes": b"direct"},
                    "semantic_redraw_structured": {"bytes": b"structured"},
                },
            }
        ]
    )
    markdowns = []
    columns = [FakeImageColumn(), FakeImageColumn(), FakeImageColumn(), FakeImageColumn()]
    radio_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "caption", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.st, "markdown", lambda text: markdowns.append(text))
    monkeypatch.setattr(ui.st, "columns", lambda n: columns)
    monkeypatch.setattr(
        ui.st,
        "radio",
        lambda label, options, index, format_func, key, horizontal: radio_calls.append((label, tuple(options), index, key)) or options[index],
    )

    selections = ui.render_image_compare_selector(FakeTarget())

    assert markdowns == ["**img_001**"]
    assert columns[0].images[0][1] == ui.IMAGE_COMPARE_LABELS["original"]
    assert columns[1].images[0][1] == ui.IMAGE_COMPARE_LABELS["safe"]
    assert columns[2].images[0][1] == ui.IMAGE_COMPARE_LABELS["semantic_redraw_direct"]
    assert columns[3].images[0][1] == ui.IMAGE_COMPARE_LABELS["semantic_redraw_structured"]
    assert radio_calls == [(
        "Выбрать вариант для img_001",
        ("original", "safe", "semantic_redraw_direct", "semantic_redraw_structured"),
        2,
        "compare_choice_img_001",
    )]
    assert selections == {"img_001": "semantic_redraw_direct"}


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
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_image_validation_summary(FakeTarget())

    assert metrics[0].calls == [("Обработано", "2/2")]
    assert metrics[1].calls == [("Изменено", 1)]
    assert metrics[2].calls == [("Fallbacks", 1)]
    assert metrics[3].calls == [("Оригинал оставлен", 1)]
    assert captions == [
        "Причины fallback по изображениям:",
        "• img-2: original | candidate_image_unreadable",
        "Ошибки валидации изображений:",
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
            "cached": True,
            "progress": 0.9,
            "started_at": None,
        },
        activity_feed=[{"time": "10:00:00", "message": "[Анализ] Разбор DOCX: Ищу абзацы."}],
    )
    markdowns = []
    captions = []
    progress_calls = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: markdowns.append(text))
    monkeypatch.setattr(ui.st, "progress", lambda value: progress_calls.append(value))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_live_status(FakeTarget())

    assert any("Идет анализ файла" in text for text in markdowns)
    assert any("Использую кэш подготовки для текущего файла." in text for text in markdowns)
    assert any("Прогресс: 90%" in text for text in markdowns)
    assert any("Размер: 1.00 MB" in text for text in markdowns)
    assert any("Источник: cache" in text for text in markdowns)
    assert progress_calls == [0.9]
    assert captions == []


def test_render_partial_result_shows_preview_instead_of_download(monkeypatch):
    session_state = SessionState(
        latest_markdown="chunk-1",
        latest_docx_bytes=None,
    )
    warnings = []
    previews = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "warning", lambda text: warnings.append(text))
    monkeypatch.setattr(ui, "render_markdown_preview", lambda *args, **kwargs: previews.append(kwargs.get("title")))

    ui.render_partial_result()

    assert warnings == ["Доступен промежуточный Markdown-результат последнего запуска."]
    assert previews == ["Текущий Markdown"]


def test_render_run_log_shows_entries_in_chronological_order(monkeypatch):
    session_state = SessionState(
        run_log=[
            {"status": "OK", "block_index": 1, "block_count": 3, "target_chars": 10, "context_chars": 2, "details": "first"},
            {"status": "OK", "block_index": 2, "block_count": 3, "target_chars": 12, "context_chars": 3, "details": "second"},
        ],
        activity_feed=[{"time": "10:00:00", "message": "Блок 2 отправлен в OpenAI."}],
        processing_status={"stage": "Блок обработан", "detail": "Последний блок готов.", "progress": 0.1, "phase": "processing"},
        last_log_hint="hint",
    )
    writes = []
    captions = []
    progress_calls = []
    markdowns = []
    metrics = [FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget()]

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "progress", lambda value: progress_calls.append(value))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))
    monkeypatch.setattr(ui.st, "write", lambda text: writes.append(text))
    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: markdowns.append(text))
    monkeypatch.setattr(ui, "_scroll_activity_feed_to_latest", lambda feed_id: None)

    ui.render_run_log(FakeTarget())

    assert progress_calls == [2 / 3]
    assert any("События" in text for text in markdowns)
    assert any("10:00:00  Блок 2 отправлен в OpenAI." in text for text in markdowns)
    assert writes[0].endswith("first")
    assert writes[1].endswith("second")


def test_render_run_log_uses_processing_activity_without_block_entries(monkeypatch):
    session_state = SessionState(
        run_log=[],
        activity_feed=[{"time": "10:00:00", "message": "Запуск обработки документа."}],
        processing_status={"stage": "Инициализация", "detail": "Проверяю окружение.", "progress": 0.0, "phase": "processing"},
        last_log_hint="hint",
    )
    progress_calls = []
    markdowns = []
    captions = []
    metrics = [FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget()]

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "progress", lambda value: progress_calls.append(value))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))
    monkeypatch.setattr(ui.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: markdowns.append(text))
    monkeypatch.setattr(ui, "_scroll_activity_feed_to_latest", lambda feed_id: None)

    ui.render_run_log(FakeTarget())

    assert progress_calls == [0.0]
    assert captions[0] == "Этап: Инициализация | Проверяю окружение."
    assert metrics[0].calls == [("Блок", "0/0")]
    assert metrics[1].calls == [("Цель", "0 симв.")]
    assert metrics[2].calls == [("Контекст", "0 симв.")]
    assert metrics[3].calls == [("Прошло", "00:00")]
    assert any("Запуск обработки документа." in text for text in markdowns)


def test_render_run_log_shows_preparation_activity_in_single_journal(monkeypatch):
    session_state = SessionState(
        run_log=[],
        activity_feed=[{"time": "10:00:00", "message": "[Анализ] Разбор DOCX: Ищу абзацы."}],
        processing_status={"stage": "Подготовка документа", "detail": "Идет анализ файла.", "progress": 0.9, "phase": "preparing"},
        last_log_hint="hint",
    )
    progress_calls = []
    markdowns = []
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "progress", lambda value: progress_calls.append(value))
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))
    monkeypatch.setattr(ui.st, "write", lambda *args, **kwargs: None)
    monkeypatch.setattr(ui.st, "markdown", lambda text, unsafe_allow_html=True: markdowns.append(text))
    monkeypatch.setattr(ui, "_scroll_activity_feed_to_latest", lambda feed_id: None)

    ui.render_run_log(FakeTarget())

    assert progress_calls == [0.9]
    assert captions[0] == "Этап: Подготовка документа | Идет анализ файла."
    assert any("События" in text for text in markdowns)
    assert any("10:00:00  [Анализ] Разбор DOCX: Ищу абзацы." in text for text in markdowns)
