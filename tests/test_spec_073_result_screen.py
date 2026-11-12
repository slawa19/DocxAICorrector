"""Spec 073 WP-K: the book-file button on the audiobook result screen (FR-008).

Rendered with a recording double of ``st``; the bundles are constructed, the state/bundle
transport is tested elsewhere (``contracts/result-and-screen.md`` section 3).
"""

import ast
import json
from pathlib import Path
from typing import Any

import pytest

import docxaicorrector.ui._ui as ui
from docxaicorrector.ui.i18n import t

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_UI_DIR = Path(ui.__file__).resolve().parent
_BOOK_JSON = '{"schema": "invented-form", "items": []}'


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def caption(self, text, *args, **kwargs) -> None:
        self.events.append(("caption", text))

    def columns(self, n, *args, **kwargs):
        count = n if isinstance(n, int) else len(n)
        self.events.append(("columns", count))
        return [_Column(self) for _ in range(count)]

    @property
    def buttons(self) -> list[dict]:
        return [event[1] for event in self.events if event[0] == "button"]

    @property
    def captions(self) -> list[str]:
        return [event[1] for event in self.events if event[0] == "caption"]

    @property
    def column_counts(self) -> list[int]:
        return [event[1] for event in self.events if event[0] == "columns"]


class _Column:
    def __init__(self, recorder: Recorder) -> None:
        self._recorder = recorder

    def download_button(self, *args, **kwargs) -> None:
        self._recorder.events.append(("button", kwargs))

    def button(self, *args, **kwargs) -> bool:
        # Spec 075: the "Open in studio" button shares the narration row; it is not a download.
        self._recorder.events.append(("action_button", kwargs))
        return False


@pytest.fixture
def recorder(monkeypatch, make_session_state) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(ui.st, "session_state", make_session_state())
    monkeypatch.setattr(ui.st, "columns", rec.columns)
    monkeypatch.setattr(ui.st, "caption", rec.caption)
    monkeypatch.setattr(ui.st, "success", lambda *a, **k: None)
    monkeypatch.setattr(ui.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(ui.st, "error", lambda *a, **k: None)
    monkeypatch.setattr(ui.st, "download_button", lambda *a, **k: rec.events.append(("button", k)))
    return rec


def _exports(**overrides) -> dict:
    base: dict[str, Any] = {
        "docx_bytes": b"tts-docx",
        "pdf_bytes": b"%PDF-tts",
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": None,
        "book_json": _BOOK_JSON,
    }
    base.update(overrides)
    return base


def _render(narration_exports, **overrides) -> None:
    kwargs: dict[str, Any] = dict(
        docx_bytes=b"review-docx",
        markdown_text="markdown",
        original_filename="My Book.docx",
        narration_text="narration",
        processing_operation="audiobook",
        narration_exports=narration_exports,
    )
    kwargs.update(overrides)
    ui.render_result_bundle(**kwargs)


def _names(buttons: list[dict]) -> list[str]:
    return [b["file_name"] for b in buttons]


def test_audiobook_all_formats_book_file_is_last_in_the_narration_row(recorder):
    _render(_exports())

    # Spec 075 FR-004: the narration row gained "Open in studio" (a fifth, non-download cell).
    assert recorder.column_counts == [5, 2]
    assert _names(recorder.buttons) == [
        "My Book.tts.docx",
        "My Book.tts.pdf",
        "My Book.tts.txt",
        "My Book.narration.json",
        "My Book_edited.docx",
        "My Book_edited.md",
    ]
    book = recorder.buttons[3]
    assert book["label"] == t("result.narration_book")
    assert book["label"] != "result.narration_book"
    assert book["mime"] == "application/json"
    assert book["type"] == "secondary"
    assert book["width"] == "stretch"
    assert book["on_click"] == "ignore"
    assert book["data"] == _BOOK_JSON.encode("utf-8")


def test_book_file_data_is_utf8_of_the_text(recorder):
    text = '{"title": "Квазибург"}'
    _render(_exports(book_json=text))

    assert recorder.buttons[3]["data"] == text.encode("utf-8")


@pytest.mark.parametrize("missing", [None, ""])
def test_no_book_json_keeps_the_three_buttons_and_no_reason_line(recorder, missing):
    _render(_exports(book_json=missing))

    assert recorder.column_counts == [3, 2]
    assert not any(n.endswith(".narration.json") for n in _names(recorder.buttons))
    assert recorder.captions == [t("result.narration_section_title"), t("result.review_section_title")]


def test_bundle_without_the_key_is_the_072_screen(recorder):
    exports = _exports()
    del exports["book_json"]
    _render(exports)

    assert recorder.column_counts == [3, 2]
    assert not any(n.endswith(".narration.json") for n in _names(recorder.buttons))


def test_blocked_delivery_uses_the_blocked_label(recorder):
    _render(
        _exports(),
        delivery_disposition={"status": "blocked", "explanation": "blocked", "message_key": ""},
    )

    book = recorder.buttons[3]
    assert book["file_name"] == "My Book.narration.json"
    assert book["label"] == t("result.blocked_download_narration_book")
    assert book["label"] != "result.blocked_download_narration_book"
    assert all(b["type"] == "secondary" for b in recorder.buttons)


@pytest.mark.parametrize("operation", ["edit", "translate"])
def test_translate_and_edit_never_get_a_book_button(recorder, operation):
    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="My Book.docx",
        narration_text="narration" if operation == "translate" else None,
        processing_operation=operation,
        narration_exports=_exports(),
    )

    assert not any(n.endswith(".narration.json") for n in _names(recorder.buttons))


def test_book_file_name_uses_the_source_stem():
    assert ui._build_narration_book_filename("path/My Book.v2.docx") == "My Book.v2.narration.json"


@pytest.mark.parametrize("catalog", ["ru.json", "en.json"])
def test_book_keys_are_in_both_catalogs(catalog):
    data = json.loads((_UI_DIR / "locales" / catalog).read_text(encoding="utf-8"))

    for key in ("result.narration_book", "result.blocked_download_narration_book"):
        assert str(data.get(key, "")).strip(), f"{key} missing from {catalog}"


def test_ui_package_never_uses_use_container_width():
    offenders = []
    for path in sorted(_UI_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "use_container_width":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
