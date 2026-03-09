import image_validation
from models import ImageAnalysisResult, ImageAsset, ImageValidationResult


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"test-image-payload"


class _FakeResponsesClient:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.responses = self

    def create(self, **kwargs):
        class _Response:
            def __init__(self, output_text: str):
                self.output_text = output_text

        return _Response(self.output_text)


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


def test_image_validation_result_and_asset_log_context_are_serializable():
    result = ImageValidationResult(
        validation_passed=True,
        decision="accept",
        semantic_match_score=0.9,
        text_match_score=0.95,
        structure_match_score=0.88,
        validator_confidence=0.92,
        missing_labels=[],
        added_entities_detected=False,
        suspicious_reasons=[],
    )
    asset = ImageAsset(
        image_id="img-1",
        placeholder="[[image-1]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
        analysis_result=build_analysis_result(),
        validation_result=result,
        final_decision="accept",
        final_variant="redrawn",
    )

    context = asset.to_log_context()

    assert context["image_id"] == "img-1"
    assert "original_bytes" not in context
    assert context["analysis_result"]["image_type"] == "diagram"
    assert context["validation_result"]["decision"] == "accept"


def test_validate_redraw_result_accepts_matching_candidate_analysis():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result()

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
    )

    assert result.validation_passed is True
    assert result.decision == "accept"
    assert result.missing_labels == []
    assert result.added_entities_detected is False
    assert result.validator_confidence >= 0.75


def test_validate_redraw_result_detects_text_loss():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result(
        contains_text=False,
        extracted_labels=[],
        confidence=0.95,
        structure_summary="three boxes connected by arrows",
    )

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert "text_missing_in_candidate" in result.suspicious_reasons
    assert result.text_match_score == 0.0


def test_build_conservative_candidate_analysis_preserves_contains_text_flag():
    analysis_before = build_analysis_result(contains_text=True)

    candidate_analysis = image_validation._build_conservative_candidate_analysis(analysis_before)

    assert candidate_analysis.contains_text is True
    assert candidate_analysis.fallback_reason == "candidate_analysis_missing"


def test_validate_redraw_result_detects_image_type_change():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result(
        image_type="photo",
        contains_text=True,
        extracted_labels=["Start", "Review", "Finish"],
        structure_summary="photographic scene",
    )

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert "image_type_changed" in result.suspicious_reasons
    assert result.semantic_match_score < 0.75


def test_validate_redraw_result_detects_added_entities():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result(
        extracted_labels=["Start", "Review", "Finish", "Escalation"],
        structure_summary="three boxes connected by arrows and escalation branch",
    )

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert result.added_entities_detected is True
    assert any(reason.startswith("added_entities:") for reason in result.suspicious_reasons)


def test_validate_redraw_result_falls_back_on_low_validator_confidence():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result(
        confidence=0.2,
        structure_summary="boxes",
        extracted_labels=["Start", "Review", "Finish"],
    )

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert "validator_confidence_too_low" in result.suspicious_reasons


def test_validate_redraw_result_handles_internal_exception_conservatively(monkeypatch):
    analysis_before = build_analysis_result()
    monkeypatch.setattr(image_validation, "_coerce_analysis_result", lambda value: (_ for _ in ()).throw(ValueError("boom")))

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert result.suspicious_reasons == ["validator_exception:ValueError"]


def test_process_image_asset_promotes_fallback_original_when_safe_variant_absent():
    analysis_before = build_analysis_result()
    asset = ImageAsset(
        image_id="img-2",
        placeholder="[[image-2]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=1,
        analysis_result=analysis_before,
        redrawn_bytes=PNG_BYTES,
    )
    candidate_analysis = build_analysis_result(
        contains_text=False,
        extracted_labels=[],
        structure_summary="three boxes connected by arrows",
    )

    processed_asset = image_validation.process_image_asset(
        asset,
        image_mode="semantic_redraw_direct",
        config={"enable_post_redraw_validation": True},
        candidate_analysis=candidate_analysis,
    )

    assert processed_asset.validation_status == "failed"
    assert processed_asset.final_decision == "fallback_original"
    assert processed_asset.final_variant == "original"
    assert processed_asset.final_reason


def test_process_image_asset_accepts_redrawn_variant_when_validation_passes():
    analysis_before = build_analysis_result()
    asset = ImageAsset(
        image_id="img-3",
        placeholder="[[image-3]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=2,
        analysis_result=analysis_before,
        safe_bytes=PNG_BYTES,
        redrawn_bytes=PNG_BYTES,
    )

    processed_asset = image_validation.process_image_asset(
        asset,
        image_mode="semantic_redraw_structured",
        config={"enable_post_redraw_validation": True},
        candidate_analysis=build_analysis_result(),
    )

    assert processed_asset.validation_status == "passed"
    assert processed_asset.final_decision == "accept"
    assert processed_asset.final_variant == "redrawn"


def test_validate_redraw_result_uses_vision_assessment_conservatively():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result()
    client = _FakeResponsesClient(
        '{"semantic_match_score":0.92,"text_match_score":0.4,"structure_match_score":0.9,'
        '"validator_confidence":0.86,"candidate_contains_text":false,"missing_labels":["Review"],'
        '"added_entities":[],"suspicious_reasons":["vision_text_loss_detected"]}'
    )

    result = image_validation.validate_redraw_result(
        PNG_BYTES,
        PNG_BYTES,
        analysis_before,
        candidate_analysis=candidate_analysis,
        client=client,
        enable_vision_validation=True,
        validation_model="gpt-4.1",
    )

    assert result.validation_passed is False
    assert result.decision == "fallback_safe"
    assert "text_missing_in_candidate" in result.suspicious_reasons
    assert "vision_text_loss_detected" in result.suspicious_reasons
    assert result.missing_labels == ["review"]
