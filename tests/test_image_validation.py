import image_validation
from image_pipeline import _apply_validation_result_to_asset
from image_pipeline_policy import resolve_validation_delivery_outcome
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


def _apply_validation_for_asset(
    asset: ImageAsset,
    *,
    image_mode: str,
    config: dict[str, object],
    candidate_analysis: ImageAnalysisResult,
):
    validation_result = image_validation.validate_redraw_result(
        asset.original_bytes,
        asset.redrawn_bytes or b"",
        asset.analysis_result,
        candidate_analysis=candidate_analysis,
        config=config,
    )
    return _apply_validation_result_to_asset(
        asset,
        validation_result,
        image_mode=image_mode,
        config=config,
        log_event_fn=lambda *args, **kwargs: None,
    )


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


def test_apply_validation_result_keeps_redrawn_variant_under_advisory_policy_when_safe_variant_absent():
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

    processed_asset = _apply_validation_for_asset(
        asset,
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True},
        candidate_analysis=candidate_analysis,
    )

    assert processed_asset.validation_status == "soft-pass"
    assert processed_asset.final_decision == "accept_soft"
    assert processed_asset.final_variant == "redrawn"
    assert processed_asset.final_reason


def test_apply_validation_result_accepts_redrawn_variant_when_validation_passes():
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

    processed_asset = _apply_validation_for_asset(
        asset,
        image_mode="semantic_redraw_structured",
        config={"keep_all_image_variants": True},
        candidate_analysis=build_analysis_result(),
    )

    assert processed_asset.validation_status == "passed"
    assert processed_asset.final_decision == "accept"
    assert processed_asset.final_variant == "redrawn"


def test_apply_validation_result_keeps_redrawn_variant_under_advisory_policy():
    analysis_before = build_analysis_result()
    asset = ImageAsset(
        image_id="img-4",
        placeholder="[[image-4]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=3,
        analysis_result=analysis_before,
        safe_bytes=PNG_BYTES,
        redrawn_bytes=PNG_BYTES,
    )
    candidate_analysis = build_analysis_result(
        confidence=0.2,
        structure_summary="boxes with visual restyling",
        extracted_labels=["Start", "Review", "Finish"],
    )

    processed_asset = _apply_validation_for_asset(
        asset,
        image_mode="semantic_redraw_structured",
        config={"keep_all_image_variants": True, "semantic_validation_policy": "advisory"},
        candidate_analysis=candidate_analysis,
    )

    assert processed_asset.validation_status == "soft-pass"
    assert processed_asset.final_decision == "accept_soft"
    assert processed_asset.final_variant == "redrawn"
    assert processed_asset.metadata.soft_accepted is True


def test_apply_validation_result_keeps_hard_validation_failures_blocking_under_advisory_policy():
    analysis_before = build_analysis_result()
    asset = ImageAsset(
        image_id="img-5",
        placeholder="[[image-5]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=4,
        analysis_result=analysis_before,
        safe_bytes=PNG_BYTES,
        redrawn_bytes=b"not-an-image",
    )

    processed_asset = _apply_validation_for_asset(
        asset,
        image_mode="semantic_redraw_direct",
        config={"keep_all_image_variants": True, "semantic_validation_policy": "advisory"},
        candidate_analysis=build_analysis_result(),
    )

    assert processed_asset.validation_status == "failed"
    assert processed_asset.final_decision == "fallback_original"
    assert processed_asset.final_variant == "original"


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


def test_validate_redraw_result_keeps_type_change_as_hard_reject_after_vision_merge():
    analysis_before = build_analysis_result()
    candidate_analysis = build_analysis_result(
        image_type="photo",
        contains_text=True,
        extracted_labels=["Start", "Review", "Finish"],
        structure_summary="three boxes connected by arrows",
    )
    client = _FakeResponsesClient(
        '{"semantic_match_score":0.98,"text_match_score":0.98,"structure_match_score":0.98,'
        '"validator_confidence":0.98,"candidate_contains_text":true,"missing_labels":[],'
        '"added_entities":[],"suspicious_reasons":[]}'
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
    assert "image_type_changed" in result.suspicious_reasons


def test_maybe_build_vision_validation_assessment_logs_failures(monkeypatch):
    logged_events = []

    monkeypatch.setattr(
        image_validation,
        "_build_vision_validation_assessment",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("vision failed")),
    )
    monkeypatch.setattr(image_validation, "log_event", lambda *args, **kwargs: logged_events.append((args, kwargs)))

    result = image_validation._maybe_build_vision_validation_assessment(
        original_image=PNG_BYTES,
        candidate_image=PNG_BYTES,
        analysis_before=build_analysis_result(),
        candidate_analysis=build_analysis_result(),
        client=_FakeResponsesClient("{}"),
        model="gpt-4.1",
        enable_vision_validation=True,
    )

    assert result is None
    assert logged_events
    assert logged_events[0][0][1] == "image_vision_validation_skipped_after_failure"


def test_resolve_validation_delivery_outcome_promotes_missing_safe_fallback_to_original():
    outcome = resolve_validation_delivery_outcome(
        ImageValidationResult(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.1,
            text_match_score=0.0,
            structure_match_score=0.2,
            validator_confidence=0.9,
            missing_labels=["review"],
            added_entities_detected=False,
            suspicious_reasons=["text_missing_in_candidate"],
        ),
        validation_policy="strict",
        has_safe_fallback=False,
    )

    assert outcome["validation_status"] == "failed"
    assert outcome["final_decision"] == "fallback_original"
    assert outcome["final_variant"] == "original"
    assert outcome["soft_accepted"] is False


def test_resolve_validation_delivery_outcome_keeps_type_drift_advisory_soft_accept():
    outcome = resolve_validation_delivery_outcome(
        ImageValidationResult(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.62,
            text_match_score=0.84,
            structure_match_score=0.70,
            validator_confidence=0.81,
            missing_labels=[],
            added_entities_detected=False,
            suspicious_reasons=["image_type_changed"],
        ),
        validation_policy="advisory",
        has_safe_fallback=True,
    )

    assert outcome["validation_status"] == "soft-pass"
    assert outcome["final_decision"] == "accept_soft"
    assert outcome["final_variant"] == "redrawn"
    assert outcome["soft_accepted"] is True
