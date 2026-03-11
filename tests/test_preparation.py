from io import BytesIO

from docx import Document

import preparation


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_prepare_document_for_processing_uses_cache_for_identical_inputs(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return [], []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    source_bytes = b"docx-bytes"
    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
    )

    assert calls["count"] == 1


def test_prepare_document_for_processing_returns_independent_copies():
    session_state = {"preparation_cache": {}}
    source_bytes = _build_docx_bytes(["Первый абзац.", "Второй абзац."])

    first = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:token",
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:token",
        chunk_size=6000,
        session_state=session_state,
    )

    first.paragraphs[0].text = "Изменено"
    first.jobs[0]["target_text"] = "Изменено"

    assert second.paragraphs[0].text == "Первый абзац.\n\nВторой абзац." or second.paragraphs[0].text == "Первый абзац."
    assert str(second.jobs[0]["target_text"]).strip() != "Изменено"


def test_prepare_document_for_processing_limits_session_cache_size(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", lambda uploaded_file: ([], []))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_filename="one.docx",
        source_bytes=b"one",
        uploaded_file_token="one:3:a",
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_filename="two.docx",
        source_bytes=b"two",
        uploaded_file_token="two:3:b",
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_filename="three.docx",
        source_bytes=b"three",
        uploaded_file_token="three:5:c",
        chunk_size=6000,
        session_state=session_state,
    )

    assert list(session_state["preparation_cache"].keys()) == [
        "two:3:b:6000",
        "three:5:c:6000",
    ]