"""Spec 072 WP-F: the narration-exports state key, the result bundle and the shared soffice search.

Contract: ``specs/072-narration-docx-pdf/contracts/state-bundle.md`` sections 1-2 (FR-008, FR-005,
SC-007). The worker -> UI allowlist carries ``latest_narration_exports``; the bundle carries
``narration_exports`` only while ``latest_narration_text`` is set; a new run never shows the
previous run's files.
"""

import logging
from pathlib import Path

import pytest

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.processing.processing_runtime import _filter_allowed_set_state_values
from docxaicorrector.runtime import external_process, state
from docxaicorrector.runtime.events import SetStateEvent

from conftest import SessionState as SessionState  # noqa: F811
from test_processing_service import _build_service


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


_FULL_EXPORTS = {
    "docx_bytes": b"docx",
    "pdf_bytes": b"%PDF",
    "docx_unavailable_reason": None,
    "pdf_unavailable_reason": None,
}


def _patch_bundle_session(monkeypatch, session_state):
    monkeypatch.setattr(processing_runtime.st, "session_state", session_state)
    monkeypatch.setattr(processing_runtime, "get_latest_source_name", lambda: "report.docx")
    monkeypatch.setattr(processing_runtime, "get_latest_source_token", lambda: "report.docx:3:abc")


# --- T-F2: the allowlist ---------------------------------------------------------------


def test_allowlist_passes_narration_exports_without_warning(monkeypatch):
    records: list[tuple] = []
    monkeypatch.setattr(processing_runtime, "log_event", lambda *args, **kwargs: records.append((args, kwargs)))

    result = _filter_allowed_set_state_values({"latest_narration_exports": dict(_FULL_EXPORTS)})

    assert result == {"latest_narration_exports": _FULL_EXPORTS}
    assert not [r for r in records if "state_event_unknown_keys" in r[0]]


# --- T-F3: bundle normalisation and the pairing rule ------------------------------------


def test_build_result_bundle_normalises_narration_exports():
    bundle = processing_runtime.build_result_bundle(
        source_name="r.docx",
        source_token="t",
        docx_bytes=None,
        markdown_text="md",
        narration_text="text",
        narration_exports={
            "docx_bytes": b"docx",
            "pdf_bytes": "not-bytes",
            "docx_unavailable_reason": None,
            "pdf_unavailable_reason": "timeout",
            "extra": b"drop me",
        },
    )

    assert bundle["narration_exports"] == {
        "docx_bytes": b"docx",
        "pdf_bytes": None,
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": "timeout",
        "book_json": None,
    }


def test_build_result_bundle_empty_bytes_and_bad_reasons_become_none():
    bundle = processing_runtime.build_result_bundle(
        source_name="r.docx",
        source_token="t",
        docx_bytes=None,
        markdown_text="md",
        narration_text="text",
        narration_exports={"docx_bytes": b"", "pdf_bytes": bytearray(b"x"), "docx_unavailable_reason": 5},
    )

    assert bundle["narration_exports"] == {
        "docx_bytes": None,
        "pdf_bytes": None,
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": None,
        "book_json": None,
    }


def test_build_result_bundle_without_exports_carries_none():
    bundle = processing_runtime.build_result_bundle(
        source_name="r.docx", source_token="t", docx_bytes=b"d", markdown_text="md"
    )

    assert bundle["narration_exports"] is None


def test_get_current_result_bundle_carries_exports_with_narration_text(monkeypatch):
    session_state = SessionState(
        latest_docx_bytes=None,
        latest_markdown="md",
        latest_narration_text="text",
        latest_narration_exports=dict(_FULL_EXPORTS),
    )
    _patch_bundle_session(monkeypatch, session_state)

    bundle = processing_runtime.get_current_result_bundle()

    assert bundle is not None
    assert bundle["narration_exports"] == {**_FULL_EXPORTS, "book_json": None}


def test_get_current_result_bundle_drops_exports_when_narration_text_is_gone(monkeypatch):
    """Pairing rule (R10): a stale exports key next to a nulled text must not reach the screen."""
    session_state = SessionState(
        latest_docx_bytes=b"final-docx",
        latest_markdown="md",
        latest_narration_text=None,
        latest_narration_exports=dict(_FULL_EXPORTS),
    )
    _patch_bundle_session(monkeypatch, session_state)

    bundle = processing_runtime.get_current_result_bundle()

    assert bundle is not None
    assert bundle["narration_exports"] is None


def test_get_current_result_bundle_without_the_key_is_none(monkeypatch):
    session_state = SessionState(latest_docx_bytes=None, latest_markdown="md", latest_narration_text="text")
    _patch_bundle_session(monkeypatch, session_state)

    bundle = processing_runtime.get_current_result_bundle()

    assert bundle is not None
    assert bundle["narration_exports"] is None


# --- T-F4: init, reset, crash handler --------------------------------------------------


def test_init_session_state_sets_exports_to_none(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)

    state.init_session_state()

    assert "latest_narration_exports" in session_state
    assert session_state.latest_narration_exports is None


@pytest.mark.parametrize("keep_restart_source", [True, False])
def test_reset_run_state_clears_exports(monkeypatch, keep_restart_source):
    session_state = SessionState(latest_narration_exports=dict(_FULL_EXPORTS), latest_narration_text="text")
    monkeypatch.setattr(state.st, "session_state", session_state)
    monkeypatch.setattr(state, "clear_restart_source", lambda restart_source: None)

    state.init_session_state()
    state.reset_run_state(keep_restart_source=keep_restart_source)

    assert session_state.latest_narration_exports is None
    assert session_state.latest_narration_text is None


class _CrashSessionStub(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _CrashRuntimeStub:
    def __init__(self, session_state):
        self._session_state = session_state

    def emit(self, event):
        if isinstance(event, SetStateEvent):
            self._session_state.update(event.values)

    def should_stop(self):
        return False


def _run_crashing_worker(*, session_state, emit_before_crash):
    runtime = _CrashRuntimeStub(session_state)

    def _crash(**kwargs):
        emit_before_crash(kwargs["runtime"])
        raise RuntimeError("late phase exploded")

    service = _build_service(run_document_processing_impl_fn=_crash)
    service.run_processing_worker(
        runtime=runtime,
        uploaded_filename="report.docx",
        jobs=[{"target_text": "x", "context_before": "", "context_after": "", "target_chars": 1, "context_chars": 0}],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
    )


def test_crash_before_delivery_clears_exports_with_narration_text():
    session_state = _CrashSessionStub(latest_processing_operation="audiobook")

    def _emit(runtime):
        runtime.emit(
            SetStateEvent(values={"latest_narration_text": "text", "latest_narration_exports": dict(_FULL_EXPORTS)})
        )

    _run_crashing_worker(session_state=session_state, emit_before_crash=_emit)

    assert session_state["latest_narration_text"] is None
    assert session_state["latest_narration_exports"] is None


def test_crash_after_delivery_keeps_exports_like_the_text():
    session_state = _CrashSessionStub(latest_processing_operation="audiobook")

    def _emit(runtime):
        runtime.emit(
            SetStateEvent(
                values={
                    "latest_narration_text": "text",
                    "latest_narration_exports": dict(_FULL_EXPORTS),
                    "latest_delivery_disposition": {"status": "accepted"},
                }
            )
        )

    _run_crashing_worker(session_state=session_state, emit_before_crash=_emit)

    assert session_state["latest_narration_text"] == "text"
    assert session_state["latest_narration_exports"] == _FULL_EXPORTS


# --- T-F5: one soffice search, one process runner --------------------------------------


def test_processing_runtime_has_no_private_soffice_search():
    source = Path(processing_runtime.__file__).read_text(encoding="utf-8")

    assert 'shutil.which("soffice")' not in source
    assert 'shutil.which("libreoffice")' not in source


def test_process_helpers_are_the_shared_ones():
    assert processing_runtime._run_completed_process is external_process.run_completed_process
    assert processing_runtime._terminate_process_tree is external_process.terminate_process_tree


def test_legacy_doc_conversion_available_uses_find_soffice_binary(monkeypatch):
    monkeypatch.setattr(processing_runtime, "find_soffice_binary", lambda: "/opt/lo/soffice")

    assert processing_runtime.legacy_doc_conversion_available() is True


def test_legacy_doc_conversion_available_false_without_soffice_and_antiword(monkeypatch):
    monkeypatch.setattr(processing_runtime, "find_soffice_binary", lambda: None)
    monkeypatch.setattr(processing_runtime.shutil, "which", lambda name: None)

    assert processing_runtime.legacy_doc_conversion_available() is False


def test_convert_legacy_doc_to_docx_uses_find_soffice_binary(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(processing_runtime, "find_soffice_binary", lambda: "/opt/lo/soffice")

    def fake_convert(*, soffice_path, filename, source_bytes):
        seen.append(soffice_path)
        return b"docx"

    monkeypatch.setattr(processing_runtime, "_convert_legacy_doc_with_soffice", fake_convert)

    result = processing_runtime._convert_legacy_doc_to_docx(filename="a.doc", source_bytes=b"doc")

    assert result == (b"docx", "libreoffice")
    assert seen == ["/opt/lo/soffice"]


def test_convert_pdf_to_docx_uses_find_soffice_binary(monkeypatch):
    monkeypatch.setattr(processing_runtime, "find_soffice_binary", lambda: None)

    with pytest.raises(RuntimeError, match="LibreOffice"):
        processing_runtime._convert_pdf_to_docx(filename="a.pdf", source_bytes=b"%PDF")
