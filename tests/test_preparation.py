from io import BytesIO
from threading import Event, Thread

from docx import Document

from models import ImageAsset, ImageVariantCandidate
from models import ParagraphBoundaryNormalizationReport
from models import ParagraphClassification, ParagraphUnit, StructureMap
import preparation
from processing_runtime import FrozenUploadPayload


def setup_function():
    preparation.clear_preparation_cache(clear_shared=True)


def _build_report(*, raw=0, logical=0, merged_groups=0, merged_raw=0):
    return ParagraphBoundaryNormalizationReport(
        total_raw_paragraphs=raw,
        total_logical_paragraphs=logical,
        merged_group_count=merged_groups,
        merged_raw_paragraph_count=merged_raw,
    )
def _build_extract_result(paragraphs, image_assets, report, relations=None, relation_report=None):
    return paragraphs, image_assets, report, ([] if relations is None else relations), relation_report


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_uploaded_payload(filename: str, content_bytes: bytes, file_token: str) -> FrozenUploadPayload:
    return FrozenUploadPayload(
        filename=filename,
        content_bytes=content_bytes,
        file_size=len(content_bytes),
        content_hash="test-hash",
        file_token=file_token,
    )


def _build_paragraph(*, source_index: int, text: str, role: str = "body") -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, source_index=source_index)


def test_prepare_document_for_processing_uses_cache_for_identical_inputs(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    source_bytes = b"docx-bytes"
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: progress_events.append(payload),
    )

    assert calls["count"] == 1
    assert progress_events[-1]["metrics"]["cached"] is True


def test_build_prepared_source_key_includes_normalization_mode():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        paragraph_boundary_normalization_mode="high_only",
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region"


def test_build_prepared_source_key_adds_structure_recognition_suffix_when_enabled():
    assert preparation.build_prepared_source_key(
        "report.docx:10:hash",
        6000,
        paragraph_boundary_normalization_mode="high_only",
        structure_recognition_enabled=True,
    ) == "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region:sr=1"


def test_prepare_document_for_processing_cache_key_changes_with_ai_review_mode(monkeypatch):
    calls = {"count": 0}
    session_state = {"preparation_cache": {}}

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    config_state = {
        "paragraph_boundary_normalization_enabled": True,
        "paragraph_boundary_normalization_mode": "high_only",
        "paragraph_boundary_ai_review_enabled": False,
        "paragraph_boundary_ai_review_mode": "off",
        "relation_normalization_enabled": True,
        "relation_normalization_profile": "phase2_default",
        "relation_normalization_enabled_relation_kinds": (
            "image_caption",
            "table_caption",
            "epigraph_attribution",
            "toc_region",
        ),
    }
    monkeypatch.setattr(preparation, "load_app_config", lambda: dict(config_state))

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    config_state["paragraph_boundary_ai_review_enabled"] = True
    config_state["paragraph_boundary_ai_review_mode"] = "review_only"

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert calls["count"] == 2
    assert list(session_state["preparation_cache"].keys()) == [
        "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
        "report.docx:10:hash:6000:high_only:review_only:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
    ]


def test_prepare_document_for_processing_returns_independent_copies():
    session_state = {"preparation_cache": {}}
    source_bytes = _build_docx_bytes(["Первый абзац.", "Второй абзац."])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:token"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:token"),
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

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    first.image_assets[0].attempt_variants[0].final_reason = "mutated"
    first.image_assets[0].attempt_variants[0].validation_result["score"] = 0.1

    assert len(second.image_assets[0].attempt_variants) == 1
    assert second.image_assets[0].attempt_variants[0].final_reason == "initial"
    assert second.image_assets[0].attempt_variants[0].validation_result == {"score": 0.5}


def test_prepare_document_for_processing_clones_comparison_variants_independently(monkeypatch):
    session_state = {"preparation_cache": {}}
    source_bytes = b"docx-bytes"

    asset = ImageAsset(
        image_id="img-1",
        placeholder="[[DOCX_IMAGE_img-1]]",
        original_bytes=b"orig",
        mime_type="image/png",
        position_index=0,
        comparison_variants={
            "safe": {
                "mode": "safe",
                "validation_result": {"score": 0.7},
                "final_reason": "initial",
            }
        },
    )

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [asset], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    first.image_assets[0].comparison_variants["safe"]["final_reason"] = "mutated"
    first.image_assets[0].comparison_variants["safe"]["validation_result"]["score"] = 0.2

    assert second.image_assets[0].comparison_variants["safe"]["final_reason"] == "initial"
    assert second.image_assets[0].comparison_variants["safe"]["validation_result"] == {"score": 0.7}


def test_prepare_document_for_processing_limits_session_cache_size(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("one.docx", b"one", "one:3:a"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("two.docx", b"two", "two:3:b"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("three.docx", b"three", "three:5:c"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert list(session_state["preparation_cache"].keys()) == [
        "two:3:b:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
        "three:5:c:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region",
    ]


def test_prepare_document_for_processing_uses_shared_cache_without_session_state(monkeypatch):
    calls = {"count": 0}
    progress_events = []

    def fake_extract(uploaded_file):
        calls["count"] += 1
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    source_bytes = b"docx-bytes"
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
        progress_callback=lambda **payload: progress_events.append(payload),
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", source_bytes, "report.docx:10:hash"),
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
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    def worker(result_key: str, finished_event: Event):
        results[result_key] = preparation.prepare_document_for_processing(
            uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
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
        return _build_extract_result([], [], None)

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    session_state = {"preparation_cache": {"stale": object()}}
    preparation.clear_preparation_cache(session_state=session_state)

    assert session_state["preparation_cache"] == {}

    cached_again = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    preparation.clear_preparation_cache(clear_shared=True)

    uncached_after_explicit_clear = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=None,
    )

    assert calls["count"] == 2
    assert cached_again.cached is True
    assert uncached_after_explicit_clear.cached is False


def test_prepare_document_for_processing_miss_returns_clone_separate_from_cached_entry(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [{"image": b"x"}], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([{"text": "p"}], [{"image": b"x"}], None))
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    cached_entry = session_state["preparation_cache"]["report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region"]

    assert result is not cached_entry
    assert result.paragraphs is not cached_entry.paragraphs
    assert result.image_assets is not cached_entry.image_assets
    assert result.jobs is not cached_entry.jobs
    assert result.jobs[0] is not cached_entry.jobs[0]


def test_prepare_document_for_processing_reports_stage_metrics(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(["p1", "p2"], ["img"], _build_report(raw=3, logical=2, merged_groups=1, merged_raw=2)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a", "block-b"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}, {"target_text": "b", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
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
    assert events[1]["metrics"]["raw_paragraph_count"] == 3
    assert events[1]["metrics"]["logical_paragraph_count"] == 2
    assert events[1]["metrics"]["merged_group_count"] == 1
    assert events[1]["metrics"]["merged_raw_paragraph_count"] == 2
    assert events[2]["metrics"]["source_chars"] == len("text-value")
    assert events[3]["metrics"]["block_count"] == 2


def test_prepare_document_for_processing_runs_structure_recognition_when_enabled(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []
    paragraphs = [_build_paragraph(source_index=0, text="ГЛАВА 1"), _build_paragraph(source_index=1, text="Основной текст")]

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(paragraphs, [], _build_report(raw=2, logical=2)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="heading", heading_level=1, confidence="high")},
            model_used="gpt-4o-mini",
            total_tokens_used=12,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "# ГЛАВА 1\n\nОсновной текст")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert [event["stage"] for event in events] == [
        "Разбор DOCX",
        "Структура извлечена",
        "Распознавание структуры…",
        "Структура распознана",
        "Текст собран",
        "Смысловые блоки",
        "Задания собраны",
    ]
    assert events[3]["metrics"]["ai_classified"] == 1
    assert events[3]["metrics"]["ai_headings"] == 1
    assert events[3]["metrics"]["ai_role_changes"] == 1
    assert events[3]["metrics"]["ai_heading_promotions"] == 1
    assert events[3]["metrics"]["ai_structural_role_changes"] == 1
    assert result.ai_classified_count == 1
    assert result.ai_heading_count == 1
    assert result.ai_role_change_count == 1
    assert result.ai_heading_promotion_count == 1
    assert result.ai_heading_demotion_count == 0
    assert result.ai_structural_role_change_count == 1
    assert result.structure_map is not None


def test_prepare_document_for_processing_tracks_ai_heading_demotions_against_heuristics(monkeypatch):
    session_state = {"preparation_cache": {}}
    paragraph = _build_paragraph(source_index=0, text="Короткий заголовок", role="heading")
    paragraph.heading_source = "heuristic"
    paragraph.heading_level = 2
    paragraph.structural_role = "heading"

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([paragraph], [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: object())
    monkeypatch.setattr(
        preparation,
        "build_structure_map",
        lambda *args, **kwargs: StructureMap(
            classifications={0: ParagraphClassification(index=0, role="body", heading_level=None, confidence="high")},
            model_used="gpt-4o-mini",
            total_tokens_used=9,
            processing_time_seconds=0.1,
            window_count=1,
        ),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "Короткий заголовок")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
        },
    )

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.ai_classified_count == 1
    assert result.ai_heading_count == 0
    assert result.ai_role_change_count == 1
    assert result.ai_heading_promotion_count == 0
    assert result.ai_heading_demotion_count == 1
    assert result.ai_structural_role_change_count == 1


def test_prepare_document_for_processing_falls_back_to_heuristics_when_structure_recognition_setup_fails(monkeypatch):
    session_state = {"preparation_cache": {}}

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([_build_paragraph(source_index=0, text="text")], [], _build_report(raw=1, logical=1)),
    )
    monkeypatch.setattr(preparation, "get_client", lambda: (_ for _ in ()).throw(RuntimeError("missing api key")))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "block", "target_chars": 5, "context_chars": 0}])
    monkeypatch.setattr(
        preparation,
        "load_app_config",
        lambda: {
            "paragraph_boundary_normalization_enabled": True,
            "paragraph_boundary_normalization_mode": "high_only",
            "paragraph_boundary_ai_review_enabled": False,
            "paragraph_boundary_ai_review_mode": "off",
            "relation_normalization_enabled": True,
            "relation_normalization_profile": "phase2_default",
            "relation_normalization_enabled_relation_kinds": ("epigraph_attribution", "image_caption", "table_caption", "toc_region"),
            "structure_recognition_enabled": True,
            "structure_recognition_model": "gpt-4o-mini",
            "structure_recognition_max_window_paragraphs": 1800,
            "structure_recognition_overlap_paragraphs": 50,
            "structure_recognition_timeout_seconds": 60,
            "structure_recognition_min_confidence": "medium",
        },
    )
    logged_events = []
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.ai_classified_count == 0
    assert result.ai_heading_count == 0
    assert result.ai_role_change_count == 0
    assert result.ai_heading_promotion_count == 0
    assert result.ai_heading_demotion_count == 0
    assert result.ai_structural_role_change_count == 0
    assert result.structure_map is None
    assert logged_events[1][0] == "structure_recognition_fallback"


def test_prepare_document_for_processing_logs_cache_miss_and_hit(monkeypatch):
    session_state = {"preparation_cache": {}}
    logged_events = []

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", lambda uploaded_file: _build_extract_result([], [], None))
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: [])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [])
    monkeypatch.setattr(preparation, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert logged_events == [
        (
            "preparation_cache_miss",
            {"prepared_source_key": "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region"},
        ),
        (
            "preparation_cache_hit",
            {"prepared_source_key": "report.docx:10:hash:6000:high_only:off:phase2_default:epigraph_attribution,image_caption,table_caption,toc_region", "cache_level": "session"},
        ),
    ]


def test_prepare_document_for_processing_retains_normalization_report_on_fresh_preparation(monkeypatch):
    session_state = {"preparation_cache": {}}
    report = _build_report(raw=4, logical=3, merged_groups=1, merged_raw=2)

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result([{"text": "p"}], [], report),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    result = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert result.normalization_report == report
    assert result.normalization_report is not report


def test_prepare_document_for_processing_retains_normalization_report_across_cache_hit_clone(monkeypatch):
    session_state = {"preparation_cache": {}}
    extract_calls = {"count": 0}

    def fake_extract(uploaded_file):
        extract_calls["count"] += 1
        return _build_extract_result([{"text": "p"}], [], _build_report(raw=4, logical=3, merged_groups=1, merged_raw=2))

    monkeypatch.setattr(preparation, "extract_document_content_with_normalization_reports", fake_extract)
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "text", "target_chars": 4, "context_chars": 0}])

    first = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    second = preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )

    assert first.normalization_report is not None
    first.normalization_report.merged_group_count = 99

    assert extract_calls["count"] == 1
    assert second.cached is True
    assert second.normalization_report is not None
    assert second.normalization_report.merged_group_count == 1
    assert second.normalization_report is not first.normalization_report


def test_prepare_document_for_processing_reports_cache_hit_normalization_metrics(monkeypatch):
    session_state = {"preparation_cache": {}}
    events = []

    monkeypatch.setattr(
        preparation,
        "extract_document_content_with_normalization_reports",
        lambda uploaded_file: _build_extract_result(["p1", "p2"], ["img"], _build_report(raw=3, logical=2, merged_groups=1, merged_raw=2)),
    )
    monkeypatch.setattr(preparation, "build_document_text", lambda paragraphs: "text-value")
    monkeypatch.setattr(preparation, "build_semantic_blocks", lambda paragraphs, max_chars, relations=None: ["block-a", "block-b"])
    monkeypatch.setattr(preparation, "build_editing_jobs", lambda blocks, max_chars: [{"target_text": "a", "target_chars": 1, "context_chars": 0}, {"target_text": "b", "target_chars": 1, "context_chars": 0}])

    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
    )
    preparation.prepare_document_for_processing(
        uploaded_payload=_build_uploaded_payload("report.docx", b"docx-bytes", "report.docx:10:hash"),
        chunk_size=6000,
        session_state=session_state,
        progress_callback=lambda **payload: events.append(payload),
    )

    assert len(events) == 1
    assert events[0]["stage"] == "Подготовка документа"
    assert events[0]["metrics"]["cached"] is True
    assert events[0]["metrics"]["raw_paragraph_count"] == 3
    assert events[0]["metrics"]["logical_paragraph_count"] == 2
    assert events[0]["metrics"]["merged_group_count"] == 1
    assert events[0]["metrics"]["merged_raw_paragraph_count"] == 2
