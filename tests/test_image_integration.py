from io import BytesIO

import app
from PIL import Image, ImageDraw
from models import ImageAnalysisResult, ImageAsset


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _make_diagram_like_png() -> bytes:
    image = Image.new("RGB", (320, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 28, 130, 78), outline="black", width=3)
    draw.rectangle((190, 28, 296, 78), outline="black", width=3)
    draw.rectangle((106, 146, 214, 196), outline="black", width=3)
    draw.line((130, 53, 190, 53), fill="black", width=3)
    draw.line((243, 78, 170, 146), fill="black", width=3)
    draw.line((77, 78, 150, 146), fill="black", width=3)
    draw.rectangle((44, 46, 110, 56), fill="black")
    draw.rectangle((210, 46, 276, 56), fill="black")
    draw.rectangle((126, 164, 194, 174), fill="black")
    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


PNG_BYTES = _make_diagram_like_png()


def _make_redrawn_like_png() -> bytes:
    image = Image.open(BytesIO(PNG_BYTES)).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rectangle((118, 14, 202, 34), fill="#E8EEF8", outline="#4A6288", width=2)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


REDRAWN_BYTES = _make_redrawn_like_png()


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
        "text_node_count": 3,
        "extracted_text": "Start -> Review -> Finish",
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
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: build_analysis_result())
    monkeypatch.setattr(app, "get_client", lambda: object())
    monkeypatch.setattr(
        app,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, prefer_deterministic_reconstruction=True, reconstruction_model=None, client=None, budget=None: (
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
        client=None,
        budget=None,
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


def test_process_document_images_reuses_single_client_for_image_attempts(monkeypatch):
    _prepare_state(monkeypatch)
    client_calls = []
    generation_clients = []
    analyses = iter(
        [
            build_analysis_result(),
            build_analysis_result(),
            build_analysis_result(),
        ]
    )

    def get_client_once():
        client = object()
        client_calls.append(client)
        return client

    def fake_generate_image_candidate(image_bytes, analysis, *, mode, client=None, budget=None):
        generation_clients.append(client)
        return PNG_BYTES if mode == "safe" else REDRAWN_BYTES

    def fake_process_image_asset(asset, **kwargs):
        if not hasattr(fake_process_image_asset, "calls"):
            fake_process_image_asset.calls = 0
        fake_process_image_asset.calls += 1
        if fake_process_image_asset.calls == 1:
            asset.validation_status = "failed"
            asset.final_decision = "fallback_safe"
            asset.final_variant = "safe"
        else:
            asset.validation_status = "passed"
            asset.final_decision = "accept"
            asset.final_variant = "redrawn"
        return asset

    monkeypatch.setattr(app, "get_client", get_client_once)
    monkeypatch.setattr(app, "generate_image_candidate", fake_generate_image_candidate)
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: next(analyses))
    monkeypatch.setattr(app, "process_image_asset", fake_process_image_asset)

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 2},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "accept"
    assert len(client_calls) == 1
    assert generation_clients == [client_calls[0], client_calls[0], client_calls[0]]


def test_process_document_images_uses_detected_redraw_mime_type_for_candidate_analysis(monkeypatch):
    _prepare_state(monkeypatch)
    mime_types = []
    analyses = iter([build_analysis_result(), build_analysis_result()])

    asset = build_asset()
    asset.mime_type = "image/jpeg"

    def capture_analyze_image(image_bytes, *, model, mime_type):
        mime_types.append(mime_type)
        return next(analyses)

    monkeypatch.setattr(app, "analyze_image", capture_analyze_image)
    monkeypatch.setattr(app, "generate_image_candidate", lambda image_bytes, analysis, *, mode, client=None, budget=None: PNG_BYTES if mode == "safe" else REDRAWN_BYTES)

    result = app.process_document_images(
        image_assets=[asset],
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 1},
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "accept"
    assert mime_types == ["image/jpeg", "image/png"]


def test_process_document_images_falls_back_when_model_call_budget_is_exhausted(monkeypatch):
    _prepare_state(monkeypatch)
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: build_analysis_result())
    monkeypatch.setattr(
        app,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, client=None, budget=None: (_ for _ in ()).throw(
            app.ImageModelCallBudgetExceeded("budget exhausted")
        )
        if mode != "safe"
        else PNG_BYTES,
    )

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={
            "enable_post_redraw_validation": True,
            "validation_model": "gpt-4.1",
            "semantic_redraw_max_attempts": 2,
            "semantic_redraw_max_model_calls_per_image": 1,
        },
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "fallback_original"
    assert result[0].validation_status == "failed"
    assert result[0].final_reason == "semantic_model_call_budget_exhausted"


def test_process_document_images_uses_safe_variant_when_semantic_candidate_collapses_to_safe(monkeypatch):
    _prepare_state(monkeypatch)
    monkeypatch.setattr(app, "analyze_image", lambda *args, **kwargs: build_analysis_result(render_strategy="deterministic_reconstruction"))

    def generate_candidate(image_bytes, analysis, *, mode, client=None, budget=None, **kwargs):
        return PNG_BYTES

    monkeypatch.setattr(app, "generate_image_candidate", generate_candidate)
    monkeypatch.setattr(
        app,
        "process_image_asset",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("post-check should not run for safe fallback")),
    )

    result = app.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"enable_post_redraw_validation": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 1},
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].final_reason == "semantic_redraw_fell_back_to_safe_candidate"
