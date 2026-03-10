from models import ImageAnalysisResult, ImageAsset, ImageValidationResult
from image_pipeline import _build_compare_variant_candidate, _prepare_compare_variants


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"compare-helpers-payload"


def _build_asset() -> ImageAsset:
    return ImageAsset(
        image_id="img_001",
        placeholder="[[DOCX_IMAGE_img_001]]",
        original_bytes=PNG_BYTES,
        mime_type="image/png",
        position_index=0,
    )


def _build_analysis(**overrides) -> ImageAnalysisResult:
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


def _build_validation_result(**overrides) -> ImageValidationResult:
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


def test_build_compare_variant_candidate_marks_safe_variant_without_validation():
    asset = _build_asset()
    analysis = _build_analysis()

    variant = _build_compare_variant_candidate(
        asset,
        analysis,
        "safe",
        {},
        client=object(),
        analyze_image_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analyze should not run")),
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: PNG_BYTES,
        validate_redraw_result_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("validation should not run")),
        detect_image_mime_type_fn=lambda image_bytes: "image/png",
        log_event_fn=lambda *args, **kwargs: None,
    )

    assert variant.mode == "safe"
    assert variant.validation_status == "skipped"
    assert variant.final_variant == "safe"
    assert asset.safe_bytes == PNG_BYTES


def test_build_compare_variant_candidate_uses_processed_semantic_outcome():
    asset = _build_asset()
    asset.safe_bytes = PNG_BYTES[:-1] + b"s"
    analysis = _build_analysis()

    variant = _build_compare_variant_candidate(
        asset,
        analysis,
        "semantic_redraw_direct",
        {"validation_model": "gpt-4.1"},
        client=object(),
        analyze_image_fn=lambda *args, **kwargs: _build_analysis(),
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: PNG_BYTES,
        validate_redraw_result_fn=lambda *args, **kwargs: _build_validation_result(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.8,
            text_match_score=0.8,
            structure_match_score=0.8,
            validator_confidence=0.8,
            suspicious_reasons=["structure_mismatch"],
        ),
        detect_image_mime_type_fn=lambda image_bytes: "image/png",
        log_event_fn=lambda *args, **kwargs: None,
    )

    assert variant.validation_status == "soft-pass"
    assert variant.final_decision == "accept_soft"
    assert variant.final_variant == "redrawn"


def test_prepare_compare_variants_keeps_original_as_selected_default():
    asset = _build_asset()
    analysis = _build_analysis()
    logged = []

    result = _prepare_compare_variants(
        asset,
        analysis,
        {"validation_model": "gpt-4.1"},
        client=object(),
        analyze_image_fn=lambda *args, **kwargs: _build_analysis(),
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES + mode.encode("ascii"),
        validate_redraw_result_fn=lambda *args, **kwargs: _build_validation_result(),
        detect_image_mime_type_fn=lambda image_bytes: "image/png",
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
    )

    assert result.selected_compare_variant == "original"
    assert result.final_variant == "original"
    assert set(result.comparison_variants.keys()) == {
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }