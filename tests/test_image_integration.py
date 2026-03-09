import app
from models import ImageAnalysisResult, ImageAsset


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image-payload"
REDRAWN_BYTES = PNG_BYTES + b"-edited"


def build_analysis_result(**overrides):
    payload = {
        "image_type": "diagram",
        "image_subtype": None,
        "contains_text": True,
        "semantic_redraw_allowed": True,
        "confidence": 0.95,
        "structured_parse_confidence": 0.9,
        "prompt_key": "diagram_semantic_redraw",
        "render_strategy": "semantic_redraw_structured",
        "structure_summary": "three boxes connected by arrows",
        "extracted_labels": ["Start", "Review", "Finish"],
        "fallback_reason": None,
    }
    payload.update(overrides)
    return ImageAnalysisResult(**payload)


def build_asset() -> ImageAsset:
    return ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
    )


def _prepare_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(app.st, "session_state", session_state)
    app.init_session_state()
    monkeypatch.setattr(app, "set_processing_status", lambda **kwargs: None)
    monkeypatch.setattr(app, "push_activity", lambda message: None)
    monkeypatch.setattr(app, "append_image_log", lambda **kwargs: None)
    monkeypatch.setattr(app, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        app,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, prefer_deterministic_reconstruction=True, reconstruction_model=None: (
            PNG_BYTES if mode == "safe" else REDRAWN_BYTES
        ),
    )
    return session_state


def test_process_document_images_accepts_semantic_redraw(monkeypatch):
    _prepare_state(monkeypatch)

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert len(result) == 1
    assert result[0].final_decision == "accept"
    assert result[0].final_variant == "redrawn"
    assert result[0].validation_status == "passed"


def test_process_document_images_applies_fallback_safe(monkeypatch):
    _prepare_state(monkeypatch)
    analyses = iter(
        [
            build_analysis_result(),
            build_analysis_result(image_type="photo", structure_summary="photo", extracted_labels=["Start"]),
        ]
    )
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: next(analyses))

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].validation_status == "failed"


def test_process_document_images_applies_fallback_original_for_unreadable_candidate(monkeypatch):
    _prepare_state(monkeypatch)

    def generate_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
    ):
        if mode == "safe":
            return b""
        return b"not-an-image"

    monkeypatch.setattr(app, "generate_image_candidate", generate_candidate)

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "fallback_original"
    assert result[0].final_variant == "original"
    assert result[0].validation_status == "failed"


def test_process_document_images_keeps_document_flow_when_validator_raises(monkeypatch):
    _prepare_state(monkeypatch)
    monkeypatch.setattr(app, "process_image_asset", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert len(result) == 1
    assert result[0].final_decision == "fallback_original"
    assert result[0].final_variant == "original"
    assert result[0].validation_status == "error"


def test_process_document_images_soft_accepts_best_semantic_candidate(monkeypatch):
    _prepare_state(monkeypatch)
    analyses = iter(
        [
            build_analysis_result(),
            build_analysis_result(
                image_type="diagram",
                contains_text=True,
                extracted_labels=["Start", "Review", "Finish"],
                structure_summary="three boxes connected by arrows and slightly shifted spacing",
                confidence=0.74,
            ),
            build_analysis_result(
                image_type="diagram",
                contains_text=True,
                extracted_labels=["Start", "Review", "Finish"],
                structure_summary="three boxes connected by arrows and slightly shifted spacing",
                confidence=0.74,
            ),
        ]
    )
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: next(analyses))

    class ValidationResultStub:
        validation_passed = False
        decision = "fallback_safe"
        semantic_match_score = 0.72
        text_match_score = 0.90
        structure_match_score = 0.70
        validator_confidence = 0.69
        missing_labels = []
        added_entities_detected = False
        suspicious_reasons = ["structure_mismatch"]

    def fake_process_image_asset(asset, **kwargs):
        asset.validation_result = ValidationResultStub()
        asset.validation_status = "failed"
        asset.final_decision = "fallback_safe"
        asset.final_variant = "safe"
        asset.final_reason = "structure_mismatch"
        return asset

    monkeypatch.setattr(app, "process_image_asset", fake_process_image_asset)

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 2},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "accept_soft"
    assert result[0].final_variant == "redrawn"
    assert result[0].validation_status == "soft-pass"
