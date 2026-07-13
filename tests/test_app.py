import pytest
from types import SimpleNamespace

import docxaicorrector.runtime.state as state
import docxaicorrector.ui._app as app
import docxaicorrector.ui._ui as ui
from conftest import SessionState as SessionState
from docxaicorrector.document.segments import DocumentContextProfile, GlossaryTerm, SegmentOutlineEntry


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


def test_resolve_sidebar_settings_accepts_new_text_transform_tuple():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de", False))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de", False)


@pytest.mark.compat_legacy
def test_resolve_sidebar_settings_keeps_eight_tuple_compatible():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de"))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "translate", "auto", "de", False)


@pytest.mark.compat_legacy
def test_resolve_sidebar_settings_keeps_legacy_tuple_compatible():
    result = app._resolve_sidebar_settings(("gpt-5.4", 6000, 3, "safe", True))

    assert result == ("gpt-5.4", 6000, 3, "safe", True, "edit", "en", "ru", False)


def test_assess_text_transform_stores_assessment_in_session_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(state.st, "session_state", session_state)

    assessment = app._assess_text_transform(
        source_text="Привет, это уже русский текст.",
        target_language="ru",
    )

    assert assessment == session_state.text_transform_assessment
    assert assessment["dominant_language"] == "ru"
    assert assessment["dominant_script"] == "cyrillic"
    assert assessment["target_language_script_match"] is True


def test_resolve_result_bundle_passes_mode_flags_for_completed_view(monkeypatch):
    captured = {}
    session_state = SessionState(
        latest_processing_operation="translate",
        latest_audiobook_postprocess_enabled=True,
    )
    monkeypatch.setattr(app.st, "session_state", session_state)
    monkeypatch.setattr(state.st, "session_state", session_state)

    monkeypatch.setattr(ui, "render_result_bundle", lambda **kwargs: captured.update(kwargs))

    app.render_result(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        narration_text="[thoughtful] narration",
        processing_operation="translate",
        audiobook_postprocess_enabled=True,
    )

    assert captured["docx_bytes"] == b"docx"
    assert captured["markdown_text"] == "markdown"
    assert captured["original_filename"] == "report.docx"
    assert captured["narration_text"] == "[thoughtful] narration"
    assert captured["processing_operation"] == "translate"
    assert captured["audiobook_postprocess_enabled"] is True


def test_build_document_context_prompt_includes_outline_and_glossary_terms():
    prompt = app._build_document_context_prompt(
        prepared_run_context=SimpleNamespace(
            document_context_profile=DocumentContextProfile(
                outline_entries=(SegmentOutlineEntry(segment_id="seg_0001", title="Chapter 1", level=1),),
                glossary_terms=(GlossaryTerm(source_term="Great Tribulation", target_term="die grosse Trubsal"),),
            ),
            segments=[
                SimpleNamespace(segment_id="seg_0001", ordinal=1, level=1, structural_role="chapter", title="Chapter 1"),
                SimpleNamespace(segment_id="seg_0002", ordinal=2, level=1, structural_role="chapter", title="Chapter 2"),
                SimpleNamespace(segment_id="seg_0003", ordinal=3, level=1, structural_role="chapter", title="Chapter 3"),
            ],
        ),
    )

    assert "Chapter 1" in prompt
    assert "Great Tribulation" in prompt


def test_start_background_processing_forwards_explicit_output_mode(monkeypatch):
    captured = {}

    class FakeService:
        def run_processing_worker(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(app, "start_background_processing", lambda **kwargs: kwargs["worker_target"](
        runtime=object(),
        uploaded_filename=kwargs["uploaded_filename"],
        prepared_source_key=kwargs["prepared_source_key"],
        structure_fingerprint=kwargs["structure_fingerprint"],
        jobs=kwargs["jobs"],
        selected_segment_ids=kwargs["selected_segment_ids"],
        output_mode=kwargs["output_mode"],
        include_front_matter=kwargs["include_front_matter"],
        include_toc=kwargs["include_toc"],
        source_paragraphs=kwargs["source_paragraphs"],
        image_assets=kwargs["image_assets"],
        image_mode=kwargs["image_mode"],
        app_config=kwargs["app_config"],
        model=kwargs["model"],
        max_retries=kwargs["max_retries"],
        processing_operation=kwargs["processing_operation"],
        source_language=kwargs["source_language"],
        target_language=kwargs["target_language"],
    ))
    monkeypatch.setitem(__import__("sys").modules, "docxaicorrector.processing.processing_service", SimpleNamespace(get_processing_service=lambda: FakeService()))

    app._start_background_processing(
        uploaded_filename="report.docx",
        uploaded_token="token",
        source_bytes=b"source",
        prepared_source_key="prep:report:1234",
        structure_fingerprint="struct-abc",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        output_mode="legacy_full_document",
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        document_context_prompt="CTX",
        model="gpt-5.4",
        max_retries=1,
    )

    assert captured["output_mode"] == "legacy_full_document"
    assert captured["prepared_source_key"] == "prep:report:1234"
    assert captured["structure_fingerprint"] == "struct-abc"
    assert captured["document_context_prompt"] == "CTX"
