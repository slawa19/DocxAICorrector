from io import BytesIO
from threading import Event, Thread

from docx import Document

from models import ImageAsset, ImageVariantCandidate
import preparation


def setup_function():
    preparation.clear_preparation_cache(clear_shared=True)


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
    progress_events = []

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
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["count"] == 1
    assert progress_events[-1]["metrics"]["cached"] is True


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


def test_prepare_document_for_processing_clones_attempt_variants_independently(monkeypatch):
    session_state = {"preparation_cache": {}}
    source_bytes = b"docx-bytes"

    asset = ImageAsset(
        image_id="img-1",
        placeholder="[[DOCX_IMAGE_img-1]]",
        original_bytes=b"orig",
        mime_type="image/png",
        position_index=0,
        attempt_variants=[
            ImageVariantCandidate(
                mode="safe",
                validation_result={"score": 0.5},
                final_reason="initial",
            )
        ],
    )

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", lambda uploaded_file: ([{"text": "p"}], [asset]))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
    )

    first.attempt_variants = []
    first.image_assets[0].attempt_variants[0].final_reason = "mutated"
    first.image_assets[0].attempt_variants[0].validation_result["score"] = 0.1

    assert len(second.image_assets[0].attempt_variants) == 1
    assert second.image_assets[0].attempt_variants[0].final_reason == "initial"
    assert second.image_assets[0].attempt_variants[0].validation_result == {"score": 0.5}


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


def test_prepare_document_for_processing_uses_shared_cache_without_session_state(monkeypatch):
    calls = {"count": 0}
    progress_events = []

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
        session_state=None,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    second = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=source_bytes,
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=None,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["count"] == 1
    assert second.cached is True
    assert progress_events[-1]["metrics"]["cached"] is True


def test_prepare_document_for_processing_uses_single_flight_for_shared_cache(monkeypatch):
    calls = {"count": 0}
    extract_started = Event()
    release_extract = Event()
    second_finished = Event()
    results = {}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        extract_started.set()
        assert release_extract.wait(timeout=5)
        return [], []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    def worker(result_key: str, finished_event: Event):
        results[result_key] = preparation.prepare_document_for_processing(
            uploaded_filename="report.docx",
            source_bytes=b"docx-bytes",
            uploaded_file_token="report.docx:10:hash",
            chunk_size=6000,
            session_state=None,
        )
        finished_event.set()

    first_finished = Event()
    first_thread = Thread(target=worker, args=("first", first_finished))
    second_thread = Thread(target=worker, args=("second", second_finished))

    first_thread.start()
    assert extract_started.wait(timeout=5)
    second_thread.start()

    assert not second_finished.wait(timeout=0.2)

    release_extract.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert calls["count"] == 1
    assert results["first"].cached is False
    assert results["second"].cached is True


def test_clear_preparation_cache_requires_explicit_shared_clear(monkeypatch):
    calls = {"count": 0}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return [], []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=b"docx-bytes",
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=None,
    )

    session_state = {"preparation_cache": {"stale": object()}}
    preparation.clear_preparation_cache(session_state=session_state)

    assert session_state["preparation_cache"] == {}

    cached_again = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=b"docx-bytes",
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=None,
    )

    preparation.clear_preparation_cache(clear_shared=True)

    uncached_after_explicit_clear = preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=b"docx-bytes",
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=None,
    )

    assert calls["count"] == 2
    assert cached_again.cached is True
    assert uncached_after_explicit_clear.cached is False


def test_prepare_document_for_processing_miss_uses_single_deepcopy_for_return(monkeypatch):
    session_state = {"preparation_cache": {}}
    deepcopy_calls = []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", lambda uploaded_file: ([{"text": "p"}], [{"image": b"x"}]))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    original_deepcopy = preparation.deepcopy

    def tracking_deepcopy(value):
        deepcopy_calls.append(type(value).__name__)
        return original_deepcopy(value)

    monkeypatch.setattr(preparation, "deepcopy", tracking_deepcopy)

    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=b"docx-bytes",
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
    )

    assert deepcopy_calls == ["list", "dict"]


def test_prepare_document_for_processing_reports_stage_metrics(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(preparation, "extract_document_content_from_docx", lambda uploaded_file: (["p1", "p2"], ["img"]))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars: ["block-a", "block-b"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}, {"target_text": "b", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_filename="report.docx",
        source_bytes=b"docx-bytes",
        uploaded_file_token="report.docx:10:hash",
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]
    assert events[1]["metrics"]["paragraph_count"] == 2
    assert events[1]["metrics"]["image_count"] == 1
    assert events[2]["metrics"]["source_chars"] == len("text-value")
    assert events[3]["metrics"]["block_count"] == 2
