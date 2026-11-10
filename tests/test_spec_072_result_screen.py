"""Spec 072 WP-G: the audiobook result screen (FR-009, SC-007).

The screen is rendered from the bundle shape fixed in ``contracts/state-bundle.md`` and a
recording double of ``st``; the bundles below are constructed, the state/bundle transport is
tested elsewhere.
"""

import ast
import json
import re
from typing import Any
from pathlib import Path

import pytest

import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as ui
from docxaicorrector.ui import i18n
from docxaicorrector.ui.i18n import t

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_UI_DIR = Path(ui.__file__).resolve().parent


class Recorder:
    """Records ``st.caption``, ``st.columns`` and every download button in render order."""

    def __init__(self) -> None:
        self.events: list[tuple] = []

    def caption(self, text, *args, **kwargs) -> None:
        self.events.append(("caption", text))

    def columns(self, n, *args, **kwargs):
        self.events.append(("columns", n if isinstance(n, int) else len(n)))
        return [_Column(self) for _ in range(n if isinstance(n, int) else len(n))]

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


@pytest.fixture
def recorder(monkeypatch, make_session_state) -> Recorder:
    rec = Recorder()
    monkeypatch.setattr(ui.st, "session_state", make_session_state())
    monkeypatch.setattr(ui.st, "columns", rec.columns)
    monkeypatch.setattr(ui.st, "caption", rec.caption)
    monkeypatch.setattr(ui.st, "success", lambda *a, **k: None)
    monkeypatch.setattr(ui.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(ui.st, "download_button", lambda *a, **k: rec.events.append(("button", k)))
    return rec


def _exports(**overrides) -> dict:
    base = {
        "docx_bytes": b"tts-docx",
        "pdf_bytes": b"%PDF-tts",
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": None,
    }
    base.update(overrides)
    return base


def _render_audiobook(narration_exports, **overrides) -> None:
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


def _shape(buttons: list[dict]) -> list[tuple]:
    return [(b["label"], b["file_name"], b["mime"], b.get("type"), b.get("width")) for b in buttons]


# -- T-G1: translate / edit are unchanged (green before and after the change) -------------------

@pytest.mark.parametrize(
    ("operation", "docx_label", "md_label"),
    [
        ("edit", "Отредактированный DOCX", "Отредактированный Markdown"),
        ("translate", "Переведённый DOCX", "Переведённый Markdown"),
    ],
)
def test_translate_and_edit_screens_are_unchanged(recorder, operation, docx_label, md_label):
    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="My Book.docx",
        narration_text=None,
        processing_operation=operation,
    )

    assert recorder.column_counts == [2]
    assert recorder.captions == []
    assert _shape(recorder.buttons) == [
        (docx_label, "My Book_edited.docx", DOCX_MIME, "primary", "stretch"),
        (md_label, "My Book_edited.md", "text/markdown", "primary", "stretch"),
    ]


def test_translate_with_narration_text_keeps_three_button_row(recorder):
    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="My Book.docx",
        narration_text="narration",
        processing_operation="translate",
    )

    assert recorder.column_counts == [3]
    assert recorder.captions == []
    assert _shape(recorder.buttons) == [
        ("Переведённый DOCX", "My Book_edited.docx", DOCX_MIME, "primary", "stretch"),
        ("Текст для ElevenLabs (.txt)", "My Book.tts.txt", "text/plain", "primary", "stretch"),
        ("Переведённый Markdown", "My Book_edited.md", "text/markdown", "primary", "stretch"),
    ]


# -- T-G2: audiobook, every format built ----------------------------------------------------------

def test_audiobook_all_formats_two_rows_in_order(recorder):
    _render_audiobook(_exports())

    assert recorder.events[0] == ("caption", t("result.narration_section_title"))
    assert [e for e in recorder.events if e[0] != "button"] == [
        ("caption", t("result.narration_section_title")),
        ("columns", 3),
        ("caption", t("result.review_section_title")),
        ("columns", 2),
    ]
    assert _shape(recorder.buttons) == [
        (t("result.narration_docx"), "My Book.tts.docx", DOCX_MIME, "primary", "stretch"),
        (t("result.narration_pdf"), "My Book.tts.pdf", "application/pdf", "secondary", "stretch"),
        (t("result.narration_elevenlabs"), "My Book.tts.txt", "text/plain", "secondary", "stretch"),
        (t("result.docx_inspection"), "My Book_edited.docx", DOCX_MIME, "secondary", "stretch"),
        (t("result.markdown_inspection"), "My Book_edited.md", "text/markdown", "secondary", "stretch"),
    ]
    assert all(b["on_click"] == "ignore" for b in recorder.buttons)
    assert [b["data"] for b in recorder.buttons] == [
        b"tts-docx",
        b"%PDF-tts",
        b"narration",
        b"review-docx",
        b"markdown",
    ]


def test_audiobook_labels_are_distinct_and_localised(recorder):
    _render_audiobook(_exports())

    labels = [b["label"] for b in recorder.buttons]
    assert len(set(labels)) == 5
    for key in ("result.narration_docx", "result.narration_pdf", "result.narration_section_title"):
        assert t(key) != key, f"{key} is missing from the ru catalog"


# -- T-G3: a format that was not built has no button and a reason line ---------------------------

def test_audiobook_without_pdf_shows_two_buttons_and_reason(recorder):
    _render_audiobook(_exports(pdf_bytes=None, pdf_unavailable_reason="timeout"))

    assert recorder.column_counts == [2, 2]
    assert [b["file_name"] for b in recorder.buttons[:2]] == ["My Book.tts.docx", "My Book.tts.txt"]
    assert not any(b["file_name"].endswith(".tts.pdf") for b in recorder.buttons)
    assert t("result.narration_pdf_unavailable.timeout") in recorder.captions
    assert t("result.narration_pdf_unavailable.timeout") != "result.narration_pdf_unavailable.timeout"
    # The reason sits right under the narration row, before the review row.
    reason_index = recorder.events.index(("caption", t("result.narration_pdf_unavailable.timeout")))
    review_index = recorder.events.index(("caption", t("result.review_section_title")))
    assert reason_index < review_index


def test_audiobook_without_docx_and_pdf_shows_txt_and_both_reasons(recorder):
    _render_audiobook(
        _exports(
            docx_bytes=None,
            pdf_bytes=None,
            docx_unavailable_reason="failed",
            pdf_unavailable_reason="docx_not_built",
        )
    )

    assert recorder.column_counts == [1, 2]
    assert [b["file_name"] for b in recorder.buttons[:-2]] == ["My Book.tts.txt"]
    assert t("result.narration_docx_unavailable") in recorder.captions
    assert t("result.narration_pdf_unavailable.docx_not_built") in recorder.captions
    # With the narration DOCX gone the primary button is not handed to another format.
    assert not any(b.get("type") == "primary" for b in recorder.buttons)


def test_audiobook_without_docx_keeps_pdf_and_txt(recorder):
    _render_audiobook(_exports(docx_bytes=None, docx_unavailable_reason="failed"))

    assert recorder.column_counts == [2, 2]
    assert [b["file_name"] for b in recorder.buttons[:-2]] == ["My Book.tts.pdf", "My Book.tts.txt"]
    assert t("result.narration_docx_unavailable") in recorder.captions


def test_unknown_pdf_reason_falls_back_to_a_localised_line(recorder):
    _render_audiobook(_exports(pdf_bytes=None, pdf_unavailable_reason="something_new"))

    assert t("result.narration_pdf_unavailable.failed") in recorder.captions


@pytest.mark.parametrize("empty", [b"", None])
def test_empty_bytes_are_not_a_button(recorder, empty):
    _render_audiobook(_exports(pdf_bytes=empty, pdf_unavailable_reason="empty_output"))

    assert not any(b["file_name"].endswith(".tts.pdf") for b in recorder.buttons)


# -- T-G4: old bundle (SC-007) and blocked delivery ----------------------------------------------

def test_old_bundle_without_exports_shows_txt_only(recorder):
    _render_audiobook(None)

    assert recorder.column_counts == [1, 2]
    assert recorder.captions == [t("result.narration_section_title"), t("result.review_section_title")]
    assert [b["file_name"] for b in recorder.buttons] == [
        "My Book.tts.txt",
        "My Book_edited.docx",
        "My Book_edited.md",
    ]


def test_exports_with_unexpected_shape_do_not_raise(recorder):
    _render_audiobook({})

    assert [b["file_name"] for b in recorder.buttons][0] == "My Book.tts.txt"


def test_blocked_delivery_makes_every_button_secondary(recorder, monkeypatch):
    monkeypatch.setattr(ui.st, "error", lambda *a, **k: None)

    _render_audiobook(
        _exports(),
        delivery_disposition={"status": "blocked", "explanation": "blocked", "message_key": ""},
    )

    assert len(recorder.buttons) == 5
    assert all(b["type"] == "secondary" for b in recorder.buttons)
    assert all(b["width"] == "stretch" for b in recorder.buttons)


# -- T-G5: the app passes the field; catalogs; no deprecated parameter ----------------------------

def test_completed_result_view_passes_narration_exports(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: captured.update(kwargs))
    exports = _exports()

    app._render_completed_result_view(
        {
            "docx_bytes": b"docx",
            "markdown_text": "markdown",
            "source_name": "My Book.docx",
            "narration_text": "narration",
            "processing_operation": "audiobook",
            "narration_exports": exports,
        }
    )

    assert captured["narration_exports"] is exports


def test_completed_result_view_of_an_old_bundle_passes_none(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(app, "render_markdown_preview", lambda **kwargs: None)
    monkeypatch.setattr(app, "render_result_bundle", lambda **kwargs: captured.update(kwargs))

    app._render_completed_result_view(
        {
            "docx_bytes": b"docx",
            "markdown_text": "markdown",
            "source_name": "My Book.docx",
            "narration_text": "narration",
            "processing_operation": "audiobook",
        }
    )

    assert "narration_exports" in captured
    assert captured["narration_exports"] is None


_NEW_KEYS = (
    "result.narration_section_title",
    "result.review_section_title",
    "result.narration_docx",
    "result.narration_pdf",
    "result.narration_docx_unavailable",
    "result.narration_pdf_unavailable.docx_not_built",
    "result.narration_pdf_unavailable.soffice_not_found",
    "result.narration_pdf_unavailable.timeout",
    "result.narration_pdf_unavailable.failed",
    "result.narration_pdf_unavailable.missing_output",
    "result.narration_pdf_unavailable.empty_output",
    "result.narration_pdf_unavailable.not_pdf",
    "result.audiobook_studio_limits_exceeded",
)


@pytest.mark.parametrize("catalog", ["ru.json", "en.json"])
def test_every_new_key_is_in_both_catalogs(catalog):
    data = json.loads((_UI_DIR / "locales" / catalog).read_text(encoding="utf-8"))

    missing = [key for key in _NEW_KEYS if not str(data.get(key, "")).strip()]
    assert missing == []


def test_limits_notice_interpolates_in_each_locale():
    for lang in ("ru", "en"):
        catalog = json.loads((_UI_DIR / "locales" / f"{lang}.json").read_text(encoding="utf-8"))
        text = catalog["result.audiobook_studio_limits_exceeded"]
        assert "{limits}" in text
        assert text.format(limits="x") != text


def test_ui_package_never_uses_use_container_width():
    offenders = []
    for path in sorted(_UI_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "use_container_width":
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []


def test_filename_builders_use_the_source_stem():
    assert ui._build_narration_docx_filename("path/My Book.v2.docx") == "My Book.v2.tts.docx"
    assert ui._build_narration_pdf_filename("My Book.docx") == "My Book.tts.pdf"
    assert ui._build_narration_filename("My Book.docx") == "My Book.tts.txt"
    assert re.fullmatch(r".+\.tts\.pdf", ui._build_narration_pdf_filename("a.docx"))


def test_language_switch_does_not_change_download_names(recorder, monkeypatch):
    monkeypatch.setattr(i18n, "get_ui_language", lambda: "en")

    _render_audiobook(_exports())

    assert [b["file_name"] for b in recorder.buttons[:3]] == [
        "My Book.tts.docx",
        "My Book.tts.pdf",
        "My Book.tts.txt",
    ]
