from io import BytesIO

import pytest
from PIL import Image, ImageDraw
from models import ImageAnalysisResult, ImageAsset, ImageValidationResult
import processing_service
import state


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


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


def build_validation_result(**overrides) -> ImageValidationResult:
    payload = {
        "validation_passed": True,
        "decision": "accept",
        "semantic_match_score": 0.95,
        "text_match_score": 0.95,
        "structure_match_score": 0.95,
        "validator_confidence": 0.95,
        "missing_labels": [],
        "added_entities_detected": False,
        "suspicious_reasons": [],
    }
    payload.update(overrides)
    return ImageValidationResult(**payload)


def _prepare_state(monkeypatch):
    session_state = SessionState()
    monkeypatch.setattr(state.st, "session_state", session_state)
    state.init_session_state()
    monkeypatch.setattr(processing_service, "emit_status_impl", lambda runtime, **kwargs: None)
    monkeypatch.setattr(processing_service, "emit_activity_impl", lambda runtime, message: None)
    monkeypatch.setattr(processing_service, "emit_image_log_impl", lambda runtime, **kwargs: None)
    monkeypatch.setattr(processing_service, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: build_analysis_result())
    monkeypatch.setattr(processing_service, "get_client", lambda: object())
    monkeypatch.setattr(
        processing_service,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, prefer_deterministic_reconstruction=True, reconstruction_model=None, reconstruction_render_config=None, client=None, budget=None: (
            PNG_BYTES if mode == "safe" else REDRAWN_BYTES
        ),
    )
    return session_state, processing_service.build_processing_service()


def test_process_document_images_accepts_semantic_redraw(monkeypatch):
    _, service = _prepare_state(monkeypatch)

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert len(result) == 1
    assert result[0].final_decision == "accept"
    assert result[0].final_variant == "redrawn"
    assert result[0].validation_status == "passed"


def test_process_document_images_no_change_skips_all_image_processing(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    analyze_calls = []
    generate_calls = []

    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: analyze_calls.append((args, kwargs)))
    monkeypatch.setattr(
        processing_service,
        "generate_image_candidate",
        lambda *args, **kwargs: generate_calls.append((args, kwargs)),
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="no_change",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert len(result) == 1
    assert result[0].mode_requested == "no_change"
    assert result[0].final_decision == "accept"
    assert result[0].final_variant == "original"
    assert result[0].validation_status == "skipped"
    assert analyze_calls == []
    assert generate_calls == []


def test_process_document_images_soft_accepts_advisory_type_drift(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    analyses = iter(
        [
            build_analysis_result(),
            build_analysis_result(image_type="photo", structure_summary="photo", extracted_labels=["Start"]),
        ]
    )
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: next(analyses))
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "accept_soft"
    assert result[0].final_variant == "redrawn"
    assert result[0].validation_status == "soft-pass"


def test_process_document_images_applies_fallback_original_for_unreadable_candidate(monkeypatch):
    _, service = _prepare_state(monkeypatch)

    def generate_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        if mode == "safe":
            return b""
        return b"not-an-image"

    monkeypatch.setattr(processing_service, "generate_image_candidate", generate_candidate)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "fallback_original"
    assert result[0].final_variant == "original"
    assert result[0].validation_status == "failed"


def test_process_document_images_keeps_document_flow_when_validator_raises(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    monkeypatch.setattr(processing_service, "validate_redraw_result", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert len(result) == 1
    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].validation_status == "error"


def test_process_document_images_uses_single_policy_soft_accept_path(monkeypatch):
    _, service = _prepare_state(monkeypatch)
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
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: next(analyses))

    monkeypatch.setattr(
        processing_service,
        "validate_redraw_result",
        lambda *args, **kwargs: build_validation_result(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.72,
            text_match_score=0.90,
            structure_match_score=0.70,
            validator_confidence=0.69,
            suspicious_reasons=["structure_mismatch"],
        ),
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 2},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "accept_soft"
    assert result[0].final_variant == "redrawn"
    assert result[0].validation_status == "soft-pass"


def test_process_document_images_reuses_single_client_for_image_attempts(monkeypatch):
    _, service = _prepare_state(monkeypatch)
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

    def fake_generate_image_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        generation_clients.append(client)
        return PNG_BYTES if mode == "safe" else REDRAWN_BYTES

    def fake_validate_redraw_result(*args, **kwargs):
        if not hasattr(fake_validate_redraw_result, "calls"):
            fake_validate_redraw_result.calls = 0
        fake_validate_redraw_result.calls += 1
        if fake_validate_redraw_result.calls == 1:
            return build_validation_result(
                validation_passed=False,
                decision="fallback_safe",
                suspicious_reasons=["structure_mismatch"],
            )
        return build_validation_result()

    monkeypatch.setattr(processing_service, "get_client", get_client_once)
    monkeypatch.setattr(processing_service, "generate_image_candidate", fake_generate_image_candidate)
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: next(analyses))
    monkeypatch.setattr(processing_service, "validate_redraw_result", fake_validate_redraw_result)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 2},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "accept"
    assert len(client_calls) == 1
    assert generation_clients == [client_calls[0], client_calls[0], client_calls[0]]
    assert [variant.mode for variant in result[0].attempt_variants] == ["candidate1", "candidate2"]


def test_process_document_images_marks_assets_for_manual_review_output(monkeypatch):
    _, service = _prepare_state(monkeypatch)

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 1},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].metadata.preserve_all_variants_in_docx is True
    assert [variant.mode for variant in result[0].attempt_variants] == ["candidate1"]


def test_process_document_images_uses_detected_redraw_mime_type_for_candidate_analysis(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    mime_types = []
    analyses = iter([build_analysis_result(), build_analysis_result()])

    asset = build_asset()
    asset.mime_type = "image/jpeg"

    def capture_analyze_image(
        image_bytes,
        *,
        model,
        mime_type,
        client=None,
        enable_vision=True,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
        budget=None,
    ):
        mime_types.append(mime_type)
        return next(analyses)

    monkeypatch.setattr(processing_service, "analyze_image", capture_analyze_image)
    monkeypatch.setattr(
        processing_service,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, prefer_deterministic_reconstruction=True, reconstruction_model=None, reconstruction_render_config=None, client=None, budget=None: PNG_BYTES if mode == "safe" else REDRAWN_BYTES,
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[asset],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 1},
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "accept"
    assert mime_types == ["image/png", "image/png"]
    assert result[0].mime_type == "image/png"
    assert result[0].metadata.source_mime_type == "image/png"


def test_process_document_images_compare_all_prepares_three_variants(monkeypatch):
    _, service = _prepare_state(monkeypatch)

    generated_modes = []

    def fake_generate_image_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        generated_modes.append(mode)
        return {
            "safe": PNG_BYTES,
            "semantic_redraw_direct": REDRAWN_BYTES,
            "semantic_redraw_structured": REDRAWN_BYTES[::-1],
        }[mode]

    monkeypatch.setattr(processing_service, "generate_image_candidate", fake_generate_image_candidate)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="compare_all",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert generated_modes == ["safe", "semantic_redraw_direct", "semantic_redraw_structured"]
    assert result[0].validation_status == "compared"
    assert result[0].final_variant == "original"
    assert result[0].selected_compare_variant == "original"
    assert set(result[0].comparison_variants.keys()) == {
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }
    assert result[0].comparison_variants["safe"].final_variant == "safe"
    assert result[0].comparison_variants["semantic_redraw_direct"].validation_status in {"passed", "failed", "soft-pass"}


def test_process_document_images_attempts_semantic_mode_for_advisory_dense_text_bypass(monkeypatch):
    _, service = _prepare_state(monkeypatch)

    advisory_analysis = build_analysis_result(
        semantic_redraw_allowed=False,
        render_strategy="safe_mode",
        fallback_reason="dense_text_bypass:22_nodes",
        text_node_count=22,
        image_type="infographic",
    )
    generated_modes = []

    def fake_generate_image_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        generated_modes.append((mode, analysis.semantic_redraw_allowed))
        return PNG_BYTES if mode == "safe" else REDRAWN_BYTES

    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: advisory_analysis)
    monkeypatch.setattr(processing_service, "generate_image_candidate", fake_generate_image_candidate)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert generated_modes == [("safe", False), ("semantic_redraw_direct", True)]
    assert result[0].final_variant == "redrawn"


def test_process_document_images_falls_back_when_model_call_budget_is_exhausted(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: build_analysis_result())
    monkeypatch.setattr(
        processing_service,
        "generate_image_candidate",
        lambda image_bytes, analysis, *, mode, prefer_deterministic_reconstruction=True, reconstruction_model=None, reconstruction_render_config=None, client=None, budget=None: (_ for _ in ()).throw(
            processing_service.ImageModelCallBudgetExceeded("budget exhausted")
        )
        if mode != "safe"
        else PNG_BYTES,
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={
            "keep_all_image_variants": True,
            "validation_model": "gpt-4.1",
            "semantic_redraw_max_attempts": 2,
            "semantic_redraw_max_model_calls_per_image": 1,
        },
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].validation_status == "failed"
    assert result[0].final_reason == "semantic_model_call_budget_exhausted"


def test_process_document_images_compare_all_falls_back_when_variants_are_incomplete(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    generated_modes = []

    def fake_generate_image_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        generated_modes.append(mode)
        if mode == "safe":
            return PNG_BYTES
        raise processing_service.ImageModelCallBudgetExceeded("budget exhausted")

    monkeypatch.setattr(processing_service, "generate_image_candidate", fake_generate_image_candidate)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="compare_all",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert generated_modes == ["safe", "semantic_redraw_direct", "semantic_redraw_structured"]
    assert result[0].validation_status == "failed"
    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].selected_compare_variant is None
    assert result[0].final_reason == "compare_all_variants_incomplete:safe"


def test_process_document_images_uses_safe_variant_when_semantic_candidate_collapses_to_safe(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: build_analysis_result(render_strategy="deterministic_reconstruction"))

    def generate_candidate(image_bytes, analysis, *, mode, client=None, budget=None, **kwargs):
        return PNG_BYTES

    monkeypatch.setattr(processing_service, "generate_image_candidate", generate_candidate)
    monkeypatch.setattr(
        processing_service,
        "validate_redraw_result",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("post-check should not run for safe fallback")),
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_structured",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 1},
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert result[0].final_decision == "fallback_safe"
    assert result[0].final_variant == "safe"
    assert result[0].final_reason == "semantic_redraw_fell_back_to_safe_candidate"


def test_process_document_images_stops_future_images_when_document_budget_is_exhausted(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    budgeted_analyses = []

    def budgeted_analyze_image(
        image_bytes,
        *,
        model,
        mime_type=None,
        client=None,
        enable_vision=True,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
        budget=None,
    ):
        if budget is not None:
            budget.consume("test.analyze")
            if hasattr(budget, "used_calls"):
                budgeted_analyses.append(budget.used_calls)
        return build_analysis_result()

    def budgeted_generate_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        if budget is not None and mode != "safe":
            budget.consume("test.generate")
        return PNG_BYTES if mode == "safe" else REDRAWN_BYTES

    def budgeted_validate_redraw_result(
        original_image,
        candidate_image,
        analysis_before,
        *,
        candidate_analysis=None,
        config=None,
        image_context=None,
        client=None,
        enable_vision_validation=True,
        validation_model=None,
        budget=None,
    ):
        if budget is not None:
            budget.consume("test.validate")
        return build_validation_result()

    monkeypatch.setattr(processing_service, "analyze_image", budgeted_analyze_image)
    monkeypatch.setattr(processing_service, "generate_image_candidate", budgeted_generate_candidate)
    monkeypatch.setattr(processing_service, "validate_redraw_result", budgeted_validate_redraw_result)
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset(), build_asset()],
        image_mode="semantic_redraw_direct",
        config={
            "keep_all_image_variants": True,
            "validation_model": "gpt-4.1",
            "semantic_redraw_max_attempts": 1,
            "image_model_call_budget_per_document": 4,
        },
        on_progress=lambda **kwargs: None,
        client=object(),
    )

    assert len(result) == 2
    assert result[0].final_decision == "accept"
    assert result[1].final_decision == "fallback_original"
    assert result[1].final_reason == "document_model_call_budget_exhausted"
    assert budgeted_analyses == [1]


def test_process_document_images_skips_unsupported_source_image_without_validation_error(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    image_logs = []

    asset = build_asset()
    asset.original_bytes = b"\x01\x02not-a-supported-raster"
    asset.mime_type = "image/x-emf"

    monkeypatch.setattr(processing_service, "emit_image_log_impl", lambda runtime, **kwargs: image_logs.append(kwargs))
    monkeypatch.setattr(
        processing_service,
        "analyze_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analyze_image should not run")),
    )
    monkeypatch.setattr(
        processing_service,
        "generate_image_candidate",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("generate_image_candidate should not run")),
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[asset],
        image_mode="compare_all",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1"},
        on_progress=lambda **kwargs: None,
    )

    assert result[0].final_decision == "fallback_original"
    assert result[0].final_variant == "original"
    assert result[0].validation_status == "skipped"
    assert result[0].final_reason == "unsupported_source_image_format:image/x-emf"
    assert image_logs == [
        {
            "image_id": "img_001",
            "status": "skipped",
            "decision": "fallback_original",
            "confidence": 0.0,
            "suspicious_reasons": ["unsupported_source_image_format:image/x-emf"],
        }
    ]


def test_process_document_images_does_not_request_candidate2_after_hard_validation_failure(monkeypatch):
    _, service = _prepare_state(monkeypatch)
    analyses = iter([build_analysis_result(), build_analysis_result()])
    generated_modes = []

    def fake_generate_image_candidate(
        image_bytes,
        analysis,
        *,
        mode,
        prefer_deterministic_reconstruction=True,
        reconstruction_model=None,
        reconstruction_render_config=None,
        client=None,
        budget=None,
    ):
        generated_modes.append(mode)
        return PNG_BYTES if mode == "safe" else REDRAWN_BYTES

    monkeypatch.setattr(processing_service, "analyze_image", lambda *args, **kwargs: next(analyses))
    monkeypatch.setattr(processing_service, "generate_image_candidate", fake_generate_image_candidate)
    monkeypatch.setattr(
        processing_service,
        "validate_redraw_result",
        lambda *args, **kwargs: build_validation_result(
            validation_passed=False,
            decision="fallback_safe",
            suspicious_reasons=["candidate_image_unreadable"],
        ),
    )
    service = processing_service.build_processing_service()

    result = service.process_document_images(
        image_assets=[build_asset()],
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "validation_model": "gpt-4.1", "semantic_redraw_max_attempts": 2},
        on_progress=lambda **kwargs: None,
    )

    assert generated_modes == ["safe", "semantic_redraw_direct"]
    assert [variant.mode for variant in result[0].attempt_variants] == ["candidate1"]
