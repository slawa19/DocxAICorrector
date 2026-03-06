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