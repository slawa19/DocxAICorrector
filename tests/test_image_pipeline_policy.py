from models import ImageAnalysisResult, ImageAsset, ImageValidationResult
from image_pipeline import score_semantic_candidate
from image_pipeline_policy import (
    build_generation_analysis,
    is_advisory_safe_fallback,
    is_hard_validation_failure,
    resolve_validation_delivery_outcome,
    should_attempt_semantic_redraw,
)


def test_should_attempt_semantic_redraw_allows_advisory_dense_text_bypass():
    analysis = ImageAnalysisResult(
        image_type="infographic",
        image_subtype=None,
        contains_text=True,
        semantic_redraw_allowed=False,
        confidence=0.9,
        structured_parse_confidence=0.8,
        prompt_key="infographic_semantic_redraw",
        render_strategy="safe_mode",
        structure_summary="dense infographic",
        extracted_labels=["A"],
        fallback_reason="dense_text_bypass:24_nodes",
    )

    assert should_attempt_semantic_redraw(analysis, "semantic_redraw_structured") is True
    assert build_generation_analysis(analysis).semantic_redraw_allowed is True


def test_is_advisory_safe_fallback_checks_known_prefixes():
    advisory_analysis = ImageAnalysisResult(
        image_type="infographic",
        image_subtype=None,
        contains_text=True,
        semantic_redraw_allowed=False,
        confidence=0.7,
        structured_parse_confidence=0.6,
        prompt_key="infographic_semantic_redraw",
        render_strategy="safe_mode",
        structure_summary="dense infographic",
        extracted_labels=[],
        fallback_reason="dense_non_latin_text_bypass:12_nodes",
    )
    non_advisory_analysis = ImageAnalysisResult(
        image_type="photo",
        image_subtype=None,
        contains_text=False,
        semantic_redraw_allowed=False,
        confidence=0.7,
        structured_parse_confidence=0.1,
        prompt_key="photo_safe_fallback",
        render_strategy="safe_mode",
        structure_summary="photo",
        extracted_labels=[],
        fallback_reason="photo_safe_only",
    )

    assert is_advisory_safe_fallback(advisory_analysis) is True
    assert is_advisory_safe_fallback(non_advisory_analysis) is False


def test_is_hard_validation_failure_accepts_unreadable_and_validator_exception_only():
    unreadable = ImageValidationResult(
        validation_passed=False,
        decision="fallback_safe",
        semantic_match_score=0.0,
        text_match_score=0.0,
        structure_match_score=0.0,
        validator_confidence=0.0,
        missing_labels=[],
        added_entities_detected=False,
        suspicious_reasons=["candidate_image_unreadable"],
    )
    advisory_mismatch = ImageValidationResult(
        validation_passed=False,
        decision="fallback_safe",
        semantic_match_score=0.8,
        text_match_score=0.8,
        structure_match_score=0.7,
        validator_confidence=0.7,
        missing_labels=[],
        added_entities_detected=False,
        suspicious_reasons=["structure_mismatch"],
    )
    validator_exception = ImageValidationResult(
        validation_passed=False,
        decision="fallback_safe",
        semantic_match_score=0.0,
        text_match_score=0.0,
        structure_match_score=0.0,
        validator_confidence=0.0,
        missing_labels=[],
        added_entities_detected=False,
        suspicious_reasons=["validator_exception:RuntimeError"],
    )

    assert is_hard_validation_failure(unreadable) is True
    assert is_hard_validation_failure(advisory_mismatch) is False
    assert is_hard_validation_failure(validator_exception) is True


def test_should_attempt_semantic_redraw_rejects_non_semantic_modes():
    analysis = ImageAnalysisResult(
        image_type="diagram",
        image_subtype=None,
        contains_text=True,
        semantic_redraw_allowed=True,
        confidence=0.8,
        structured_parse_confidence=0.8,
        prompt_key="diagram_semantic_redraw",
        render_strategy="semantic_redraw_structured",
        structure_summary="diagram",
        extracted_labels=[],
    )

    assert should_attempt_semantic_redraw(analysis, "safe") is False


def test_resolve_validation_delivery_outcome_soft_accepts_advisory_mismatch():
    result = ImageValidationResult(
        validation_passed=False,
        decision="fallback_safe",
        semantic_match_score=0.81,
        text_match_score=0.79,
        structure_match_score=0.83,
        validator_confidence=0.8,
        missing_labels=[],
        added_entities_detected=False,
        suspicious_reasons=["structure_mismatch"],
    )

    outcome = resolve_validation_delivery_outcome(
        result,
        validation_policy="advisory",
        has_safe_fallback=True,
    )

    assert outcome["final_decision"] == "accept_soft"
    assert outcome["final_variant"] == "redrawn"
    assert outcome["soft_accepted"] is True


def test_resolve_validation_delivery_outcome_keeps_hard_failure_on_unreadable_candidate():
    result = ImageValidationResult(
        validation_passed=False,
        decision="fallback_safe",
        semantic_match_score=0.0,
        text_match_score=0.0,
        structure_match_score=0.0,
        validator_confidence=0.0,
        missing_labels=["A"],
        added_entities_detected=False,
        suspicious_reasons=["candidate_image_unreadable"],
    )

    outcome = resolve_validation_delivery_outcome(
        result,
        validation_policy="advisory",
        has_safe_fallback=True,
    )

    assert outcome["final_decision"] == "fallback_safe"
    assert outcome["soft_accepted"] is False


def test_score_semantic_candidate_penalizes_drift_and_rewards_clean_accept():
    asset = ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=0,
        redrawn_bytes=b"redrawn",
        final_variant="redrawn",
        final_decision="accept",
        validation_result=ImageValidationResult(
            validation_passed=True,
            decision="accept",
            semantic_match_score=0.9,
            text_match_score=0.8,
            structure_match_score=0.85,
            validator_confidence=0.88,
            missing_labels=[],
            added_entities_detected=False,
            suspicious_reasons=[],
        ),
    )
    drifted = ImageAsset(
        image_id="img_002",
        placeholder="[[DOCX_IMAGE_img_002]]",
        original_bytes=b"original",
        mime_type="image/png",
        position_index=1,
        redrawn_bytes=b"redrawn",
        final_variant="redrawn",
        final_decision="accept_soft",
        validation_result=ImageValidationResult(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.9,
            text_match_score=0.8,
            structure_match_score=0.85,
            validator_confidence=0.88,
            missing_labels=[],
            added_entities_detected=True,
            suspicious_reasons=["image_type_changed", "added_entities:X"],
        ),
    )

    assert score_semantic_candidate(asset) > score_semantic_candidate(drifted)