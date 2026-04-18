import image_pipeline
from typing import cast
from models import ImageAnalysisResult, ImageAsset, ImageDeliveryPayload, ImageValidationResult, ImageVariantCandidate
from image_pipeline import (
    ImageProcessingPlan,
    ImageProcessingContext,
    _build_compare_variant_candidate,
    _build_image_processing_plan,
    _build_passthrough_image_processing_plan,
    _emit_asset_image_log,
    _execute_image_processing_plan,
    _execute_plan_delivery_strategy,
    _execute_plan_selection_strategy,
    _prepare_compare_variants,
)


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


def _build_context(resolved_test_model_registry, **overrides) -> ImageProcessingContext:
    payload = {
        "config": {"models": resolved_test_model_registry},
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


def test_build_compare_variant_candidate_marks_safe_variant_without_validation(resolved_test_model_registry):
    asset = _build_asset()
    analysis = _build_analysis()
    context = _build_context(
        resolved_test_model_registry,
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


def test_build_compare_variant_candidate_executes_shared_child_plan(monkeypatch, resolved_test_model_registry):
    captured = []

    def fake_execute(asset, source_analysis, generation_analysis, plan, **kwargs):
        captured.append(
            {
                "requested_mode": plan.requested_mode,
                "effective_mode": plan.effective_mode,
                "generation_strategy": plan.generation_strategy,
                "delivery_mode": plan.delivery_mode,
                "source_prompt_key": source_analysis.prompt_key,
                "generation_prompt_key": generation_analysis.prompt_key,
            }
        )
        asset.safe_bytes = PNG_BYTES
        asset.apply_final_selection_outcome(
            validation_status="skipped",
            final_decision="accept",
            final_variant="safe",
            final_reason="shared_plan_result",
        )
        return asset

    monkeypatch.setattr(image_pipeline, "_execute_image_processing_plan", fake_execute)
    asset = _build_asset()
    analysis = _build_analysis(prompt_key="compare-plan")

    variant = _build_compare_variant_candidate(
        asset,
        analysis,
        "safe",
        _build_context(resolved_test_model_registry),
        client=object(),
    )

    assert captured == [
        {
            "requested_mode": "safe",
            "effective_mode": "safe",
            "generation_strategy": "safe_only",
            "delivery_mode": "raster_with_geometry",
            "source_prompt_key": "compare-plan",
            "generation_prompt_key": "compare-plan",
        }
    ]
    assert variant.final_reason == "compare_all_safe_variant_ready"


def test_build_passthrough_image_processing_plan_marks_no_change_as_original_drawing():
    plan = _build_passthrough_image_processing_plan("no_change")

    assert plan.requested_mode == "no_change"
    assert plan.generation_strategy == "none"
    assert plan.delivery_mode == "original_drawing"
    assert plan.validation_strategy == "skip"


def test_build_image_processing_plan_for_compare_all_reduces_modes_when_semantic_is_disabled():
    analysis = _build_analysis(semantic_redraw_allowed=False, render_strategy="safe_mode")

    plan = _build_image_processing_plan(analysis, "compare_all")

    assert plan.generation_strategy == "compare_all"
    assert plan.compare_modes == ("safe",)
    assert plan.needs_client is False


def test_build_image_processing_plan_for_semantic_mode_falls_back_to_safe_strategy_when_redraw_disabled():
    analysis = _build_analysis(semantic_redraw_allowed=False, render_strategy="safe_mode")

    plan = _build_image_processing_plan(analysis, "semantic_redraw_direct")

    assert plan.requested_mode == "semantic_redraw_direct"
    assert plan.effective_mode == "safe"
    assert plan.generation_strategy == "safe_only"
    assert plan.needs_client is False


def test_build_image_processing_plan_for_structured_semantic_uses_semantic_strategy():
    analysis = _build_analysis()

    plan = _build_image_processing_plan(analysis, "semantic_redraw_structured")

    assert plan.effective_mode == "semantic_redraw_structured"
    assert plan.generation_strategy == "semantic_with_safe_fallback"
    assert plan.needs_client is True
    assert plan.needs_safe_candidate is True


def test_execute_image_processing_plan_dispatches_via_strategy_registry(monkeypatch, resolved_test_model_registry):
    calls = []

    def fake_executor(asset, source_analysis, generation_analysis, plan, **kwargs):
        calls.append(
            {
                "asset": asset.image_id,
                "requested_mode": plan.requested_mode,
                "source_prompt_key": source_analysis.prompt_key,
                "generation_prompt_key": generation_analysis.prompt_key,
            }
        )
        return asset

    monkeypatch.setitem(image_pipeline._IMAGE_PROCESSING_STRATEGY_EXECUTORS, "test_strategy", fake_executor)
    asset = _build_asset()
    source_analysis = _build_analysis(prompt_key="source")
    generation_analysis = _build_analysis(prompt_key="generation")
    plan = ImageProcessingPlan(
        requested_mode="semantic_redraw_direct",
        effective_mode="semantic_redraw_direct",
        generation_strategy="test_strategy",
        delivery_mode="raster_with_geometry",
        validation_strategy="strict_or_advisory",
    )

    result = _execute_image_processing_plan(
        asset,
        source_analysis,
        generation_analysis,
        plan,
        pipeline_context=_build_context(resolved_test_model_registry),
        client=object(),
    )

    assert result is asset
    assert calls == [
        {
            "asset": "img_001",
            "requested_mode": "semantic_redraw_direct",
            "source_prompt_key": "source",
            "generation_prompt_key": "generation",
        }
    ]


def test_execute_plan_selection_strategy_dispatches_via_selection_registry(monkeypatch, resolved_test_model_registry):
    calls = []

    def fake_selection_executor(asset, source_analysis, generation_analysis, plan, **kwargs):
        calls.append(
            {
                "asset": asset.image_id,
                "validation_strategy": plan.validation_strategy,
                "source_prompt_key": source_analysis.prompt_key,
                "generation_prompt_key": generation_analysis.prompt_key,
            }
        )
        return asset

    monkeypatch.setitem(image_pipeline._IMAGE_SELECTION_STRATEGY_EXECUTORS, "test_selection", fake_selection_executor)
    asset = _build_asset()
    source_analysis = _build_analysis(prompt_key="source-selection")
    generation_analysis = _build_analysis(prompt_key="generation-selection")
    plan = ImageProcessingPlan(
        requested_mode="safe",
        effective_mode="safe",
        generation_strategy="safe_only",
        delivery_mode="raster_with_geometry",
        validation_strategy="test_selection",
    )

    result = _execute_plan_selection_strategy(
        asset,
        source_analysis,
        generation_analysis,
        plan,
        pipeline_context=_build_context(resolved_test_model_registry),
        client=object(),
    )

    assert result is asset
    assert calls == [
        {
            "asset": "img_001",
            "validation_strategy": "test_selection",
            "source_prompt_key": "source-selection",
            "generation_prompt_key": "generation-selection",
        }
    ]


def test_execute_plan_delivery_strategy_dispatches_via_delivery_registry(monkeypatch, resolved_test_model_registry):
    calls = []

    def fake_delivery_executor(asset, source_analysis, generation_analysis, plan, **kwargs):
        calls.append(
            {
                "asset": asset.image_id,
                "delivery_mode": plan.delivery_mode,
                "source_prompt_key": source_analysis.prompt_key,
                "generation_prompt_key": generation_analysis.prompt_key,
            }
        )
        return asset

    monkeypatch.setitem(image_pipeline._IMAGE_DELIVERY_STRATEGY_EXECUTORS, "test_delivery", fake_delivery_executor)
    asset = _build_asset()
    source_analysis = _build_analysis(prompt_key="source-delivery")
    generation_analysis = _build_analysis(prompt_key="generation-delivery")
    plan = ImageProcessingPlan(
        requested_mode="safe",
        effective_mode="safe",
        generation_strategy="safe_only",
        delivery_mode="test_delivery",
        validation_strategy="skip",
    )

    result = _execute_plan_delivery_strategy(
        asset,
        source_analysis,
        generation_analysis,
        plan,
        pipeline_context=_build_context(resolved_test_model_registry),
        client=object(),
    )

    assert result is asset
    assert calls == [
        {
            "asset": "img_001",
            "delivery_mode": "test_delivery",
            "source_prompt_key": "source-delivery",
            "generation_prompt_key": "generation-delivery",
        }
    ]


def test_execute_image_processing_plan_runs_delivery_stage_after_generation(monkeypatch, resolved_test_model_registry):
    call_order = []

    def fake_executor(asset, source_analysis, generation_analysis, plan, **kwargs):
        call_order.append(("generation", plan.generation_strategy))
        return asset

    def fake_delivery_executor(asset, source_analysis, generation_analysis, plan, **kwargs):
        call_order.append(("delivery", plan.delivery_mode))
        return asset

    monkeypatch.setitem(image_pipeline._IMAGE_PROCESSING_STRATEGY_EXECUTORS, "test_strategy", fake_executor)
    monkeypatch.setitem(image_pipeline._IMAGE_DELIVERY_STRATEGY_EXECUTORS, "test_delivery", fake_delivery_executor)
    asset = _build_asset()
    source_analysis = _build_analysis(prompt_key="source")
    generation_analysis = _build_analysis(prompt_key="generation")
    plan = ImageProcessingPlan(
        requested_mode="semantic_redraw_direct",
        effective_mode="semantic_redraw_direct",
        generation_strategy="test_strategy",
        delivery_mode="test_delivery",
        validation_strategy="strict_or_advisory",
    )

    result = _execute_image_processing_plan(
        asset,
        source_analysis,
        generation_analysis,
        plan,
        pipeline_context=_build_context(resolved_test_model_registry),
        client=object(),
    )

    assert result is asset
    assert call_order == [
        ("generation", "test_strategy"),
        ("delivery", "test_delivery"),
    ]


def test_emit_asset_image_log_uses_resolved_delivery_payload_variant(resolved_test_model_registry):
    captured = []
    asset = _build_asset()
    asset.apply_final_selection_outcome(
        validation_status="passed",
        final_decision="accept",
        final_variant="original",
        final_reason="stale_final_variant",
    )
    asset.delivery_payload = ImageDeliveryPayload(
        delivery_kind="final_selection",
        final_bytes=asset.original_bytes,
        final_variant="safe",
        final_decision="accept",
        final_reason="delivery_payload_authority",
    )
    context = _build_context(resolved_test_model_registry, emit_image_log=lambda runtime, **payload: captured.append(payload))

    _emit_asset_image_log(context, asset, analysis=_build_analysis(confidence=0.42))

    assert captured == [
        {
            "image_id": "img_001",
            "status": "validated",
            "decision": "accept",
            "confidence": 0.42,
            "suspicious_reasons": [],
            "final_variant": "safe",
            "final_reason": "delivery_payload_authority",
        }
    ]


def test_build_compare_variant_candidate_uses_processed_semantic_outcome(resolved_test_model_registry):
    asset = _build_asset()
    asset.safe_bytes = PNG_BYTES[:-1] + b"s"
    analysis = _build_analysis()
    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry},
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


def test_prepare_compare_variants_keeps_original_as_selected_default(resolved_test_model_registry):
    asset = _build_asset()
    analysis = _build_analysis()
    logged = []
    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry},
        analyze_image_fn=lambda *args, **kwargs: _build_analysis(),
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES + mode.encode("ascii"),
        validate_redraw_result_fn=lambda *args, **kwargs: _build_validation_result(),
        log_event_fn=lambda *args, **kwargs: logged.append((args, kwargs)),
    )

    result = cast(ImageAsset, _prepare_compare_variants(
        asset,
        analysis,
        context,
        client=object(),
    ))

    assert result.selected_compare_variant == "original"
    assert result.final_variant == "original"
    assert set(result.comparison_variants.keys()) == {
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }


def test_prepare_compare_variants_falls_back_to_safe_when_compare_all_is_incomplete(resolved_test_model_registry):
    asset = _build_asset()
    analysis = _build_analysis(semantic_redraw_allowed=False, render_strategy="safe_mode")
    context = _build_context(
        resolved_test_model_registry,
        analyze_image_fn=lambda *args, **kwargs: analysis,
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES,
    )

    result = cast(ImageAsset, _prepare_compare_variants(
        asset,
        analysis,
        context,
        client=object(),
    ))

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
