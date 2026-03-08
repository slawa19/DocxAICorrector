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


def test_render_sidebar_returns_image_settings(monkeypatch):
    config = {
        "model_options": ["gpt-5.4", "gpt-5-mini"],
        "default_model": "gpt-5-mini",
        "chunk_size": 6000,
        "max_retries": 3,
        "image_mode_default": "semantic_redraw_direct",
        "enable_post_redraw_validation": False,
    }

    sidebar_calls = []
    monkeypatch.setattr(ui.st.sidebar, "header", lambda text: sidebar_calls.append(("header", text)))
    monkeypatch.setattr(
        ui.st.sidebar,
        "selectbox",
        lambda label, options, index=0: "semantic_redraw_direct" if label == "Режим обработки изображений" else options[index],
    )
    monkeypatch.setattr(ui.st.sidebar, "text_input", lambda *args, **kwargs: "")
    monkeypatch.setattr(ui.st.sidebar, "slider", lambda label, **kwargs: kwargs["value"])
    monkeypatch.setattr(ui.st.sidebar, "checkbox", lambda label, value: value)

    result = ui.render_sidebar(config)

    assert result == ("gpt-5-mini", 6000, 3, "semantic_redraw_direct", False)
    assert sidebar_calls == [("header", "Настройки")]


def test_render_image_validation_summary_shows_metrics(monkeypatch):
    session_state = SessionState(
        image_processing_summary={
            "total_images": 2,
            "processed_images": 2,
            "images_validated": 2,
            "validation_passed": 1,
            "fallbacks_applied": 1,
            "validation_errors": ["img-2: validator_exception:RuntimeError"],
        }
    )
    metrics = [FakeMetricTarget(), FakeMetricTarget(), FakeMetricTarget()]
    captions = []

    monkeypatch.setattr(ui.st, "session_state", session_state)
    monkeypatch.setattr(ui.st, "expander", lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(ui.st, "columns", lambda n: metrics)
    monkeypatch.setattr(ui.st, "caption", lambda text: captions.append(text))

    ui.render_image_validation_summary(FakeTarget())

    assert metrics[0].calls == [("Проверено", "2/2")]
    assert metrics[1].calls == [("Принято", 1)]
    assert metrics[2].calls == [("Fallbacks", 1)]
    assert captions == [
        "Ошибки валидации изображений:",
        "• img-2: validator_exception:RuntimeError",
    ]
