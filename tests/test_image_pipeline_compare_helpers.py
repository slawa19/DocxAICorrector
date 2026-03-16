from models import ImageAnalysisResult, ImageAsset, ImageValidationResult, ImageVariantCandidate
from image_pipeline import ImageProcessingContext, _build_compare_variant_candidate, _prepare_compare_variants


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


def _build_context(**overrides) -> ImageProcessingContext:
    payload = {
        "config": {},
        "on_progress": lambda **kwargs: None,
        "runtime": None,
        "client": None,
        "emit_state": lambda *args, **kwargs: None,
        "emit_image_reset": lambda *args, **kwargs: None,
        "emit_finalize": lambda *args, **kwargs: None,
        "emit_activity": lambda *args, **kwargs: None,
        "emit_status": lambda *args, **kwargs: None,
        "emit_image_log": lambda *args, **kwargs: None,
        "should_stop": lambda runtime: False,
        "analyze_image_fn": lambda *args, **kwargs: _build_analysis(),
        "generate_image_candidate_fn": lambda image_bytes, analysis, **kwargs: PNG_BYTES,
        "validate_redraw_result_fn": lambda *args, **kwargs: _build_validation_result(),
        "get_client_fn": lambda: object(),
        "log_event_fn": lambda *args, **kwargs: None,
        "detect_image_mime_type_fn": lambda image_bytes: "image/png",
        "image_model_call_budget_cls": type(
            "Budget",
            (),
            {
                "__init__": lambda self, max_calls: setattr(self, "max_calls", max_calls) or setattr(self, "used_calls", 0),
                "remaining_calls": property(lambda self: max(0, self.max_calls - self.used_calls)),
                "ensure_available": lambda self, operation_name: None,
                "consume": lambda self, operation_name: setattr(self, "used_calls", self.used_calls + 1),
            },
        ),
        "image_model_call_budget_exceeded_cls": RuntimeError,
    }
    payload.update(overrides)
    return ImageProcessingContext(**payload)


def test_build_compare_variant_candidate_marks_safe_variant_without_validation():
    asset = _build_asset()
    analysis = _build_analysis()
    context = _build_context(
        analyze_image_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("analyze should not run")),
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: PNG_BYTES,
        validate_redraw_result_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("validation should not run")),
    )

    variant = _build_compare_variant_candidate(
        asset,
        analysis,
        "safe",
        context,
        client=object(),
    )

    assert variant.mode == "safe"
    assert variant.validation_status == "skipped"
    assert variant.final_variant == "safe"
    assert asset.safe_bytes == PNG_BYTES


def test_build_compare_variant_candidate_uses_processed_semantic_outcome():
    asset = _build_asset()
    asset.safe_bytes = PNG_BYTES[:-1] + b"s"
    analysis = _build_analysis()
    context = _build_context(
        config={"validation_model": "gpt-4.1"},
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
    )

    variant = _build_compare_variant_candidate(
        asset,
        analysis,
        "semantic_redraw_direct",
        context,
        client=object(),
    )

    assert variant.validation_status == "soft-pass"
    assert variant.final_decision == "accept_soft"
    assert variant.final_variant == "redrawn"


def test_prepare_compare_variants_keeps_original_as_selected_default():
    asset = _build_asset()
    analysis = _build_analysis()
    logged = []
    context = _build_context(
        config={"validation_model": "gpt-4.1"},
        analyze_image_fn=lambda *args, **kwargs: _build_analysis(),
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES + mode.encode("ascii"),
        validate_redraw_result_fn=lambda *args, **kwargs: _build_validation_result(),
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
    )

    result = _prepare_compare_variants(
        asset,
        analysis,
        context,
        client=object(),
    )

    assert result.selected_compare_variant == "original"
    assert result.final_variant == "original"
    assert set(result.comparison_variants.keys()) == {
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }


def test_prepare_compare_variants_falls_back_to_safe_when_compare_all_is_incomplete():
    asset = _build_asset()
    analysis = _build_analysis(semantic_redraw_allowed=False, render_strategy="safe_mode")
    context = _build_context(
        analyze_image_fn=lambda *args, **kwargs: analysis,
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES,
    )

    result = _prepare_compare_variants(
        asset,
        analysis,
        context,
        client=object(),
    )

    assert result.validation_status == "failed"
    assert result.final_decision == "fallback_safe"
    assert result.final_variant == "safe"
    assert result.selected_compare_variant is None
    assert result.final_reason == "compare_all_variants_incomplete:safe"


def test_image_variant_candidate_to_dict_is_json_safe_summary():
    variant = ImageVariantCandidate(
        mode="safe",
        bytes=b"payload",
        mime_type="image/png",
        validation_result=_build_validation_result(),
    )

    payload = variant.to_dict()

    assert "bytes" not in payload
    assert payload["has_bytes"] is True
    assert payload["bytes_size"] == len(b"payload")