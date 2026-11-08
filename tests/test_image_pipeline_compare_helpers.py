import docxaicorrector.image.pipeline as image_pipeline
from typing import cast
from docxaicorrector.core.models import ImageAnalysisResult, ImageAsset, ImageDeliveryPayload, ImageValidationResult, ImageVariantCandidate
from docxaicorrector.image.pipeline import (
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
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: PNG_BYTES + b"redrawn",  # spec 062 FR-017: a candidate equal to the source is now rejected
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


# --- spec 062 P1: candidate selection (FR-016, FR-017) -------------------------------


def _run_semantic_selection(resolved_test_model_registry, *, candidates, validations):
    """Drive ``select_best_semantic_asset`` with scripted candidates and verdicts."""
    candidate_iter = iter(candidates)
    validation_iter = iter(validations)
    validator_calls = []
    logged = []

    def _validate(*args, **kwargs):
        validator_calls.append(args)
        return next(validation_iter)

    asset = _build_asset()
    asset.safe_bytes = PNG_BYTES + b"safe"
    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry, "semantic_redraw_max_attempts": 2},
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: next(candidate_iter),
        validate_redraw_result_fn=_validate,
        log_event_fn=lambda *args, **kwargs: logged.append(args[1]),
    )
    result = image_pipeline.select_best_semantic_asset(
        asset,
        _build_analysis(),
        "semantic_redraw_direct",
        pipeline_context=context,
        client=object(),
    )
    return result, validator_calls, logged


_STRUCTURE_ONLY_MISS = dict(
    validation_passed=False,
    decision="fallback_safe",
    structure_match_score=0.4,
    suspicious_reasons=["structure_mismatch", "validator_confidence_too_low"],
)


def test_structure_mismatch_alone_no_longer_requests_a_challenger(resolved_test_model_registry):
    """FR-016 (D7): a low structure Jaccard is data, not a reason for a second paid candidate."""
    result, validator_calls, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"candidate1", PNG_BYTES + b"candidate2"],
        validations=[_build_validation_result(**_STRUCTURE_ONLY_MISS)],
    )

    assert len(validator_calls) == 1
    assert result.final_decision == "accept_soft"
    assert [variant.mode for variant in result.attempt_variants] == ["candidate1"]


def test_concrete_validation_failures_still_request_a_challenger(resolved_test_model_registry):
    """FR-016 anti-vacuum: missing labels, added entities and a type change still do."""
    concrete_failures = [
        dict(missing_labels=["review"], suspicious_reasons=["missing_labels:review"]),
        dict(added_entities_detected=True, suspicious_reasons=["added_entities:extra"]),
        dict(suspicious_reasons=["image_type_changed"]),
        dict(suspicious_reasons=["text_missing_in_candidate"]),
        dict(suspicious_reasons=["entities_added"]),
    ]
    for failure in concrete_failures:
        result, validator_calls, _ = _run_semantic_selection(
            resolved_test_model_registry,
            candidates=[PNG_BYTES + b"candidate1", PNG_BYTES + b"candidate2"],
            validations=[
                _build_validation_result(validation_passed=False, decision="fallback_safe", **failure),
                _build_validation_result(),
            ],
        )

        assert len(validator_calls) == 2, failure
        assert result.final_decision == "accept", failure
        assert [variant.mode for variant in result.attempt_variants] == ["candidate1", "candidate2"], failure


def test_candidate_equal_to_source_is_rejected_without_validation(resolved_test_model_registry):
    """FR-017 (D6): generation returned the source bytes (refused provider raster); the
    validator must not compare the original with itself."""
    result, validator_calls, logged = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES],
        validations=[],
    )

    assert validator_calls == []
    assert result.final_decision == "fallback_original"
    assert result.final_variant == "original"
    assert result.final_reason == "semantic_redraw_returned_source"
    assert "semantic_candidate_returned_source" in logged


def test_candidate_different_from_source_still_passes_validation(resolved_test_model_registry):
    """FR-017 counter-proof: a genuinely different candidate is validated and accepted."""
    result, validator_calls, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"redrawn"],
        validations=[_build_validation_result()],
    )

    assert len(validator_calls) == 1
    assert result.final_decision == "accept"
    assert result.final_variant == "redrawn"


def test_candidate_equal_to_safe_still_goes_to_safe_first(resolved_test_model_registry):
    """Anti-regression: the existing safe-equality check keeps precedence over FR-017."""
    result, validator_calls, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"safe"],
        validations=[],
    )

    assert validator_calls == []
    assert result.final_decision == "fallback_safe"
    assert result.final_reason == "semantic_redraw_fell_back_to_safe_candidate"


# --- spec 062 P3/P1: compare_all delivery and document budget (FR-032, FR-022) -------


def test_compare_all_does_not_deliver_a_semantic_variant_that_is_the_safe_picture(resolved_test_model_registry):
    """FR-032 (M2): when both semantic variants fall back to the safe picture, the DOCX
    gets one picture, not the same picture three times under three captions."""
    safe_like = PNG_BYTES + b"safe"
    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry},
        generate_image_candidate_fn=lambda image_bytes, analysis, **kwargs: safe_like,
    )

    asset = _build_asset()
    result = cast(ImageAsset, _prepare_compare_variants(asset, _build_analysis(), context, client=object()))

    assert result is asset
    assert result.validation_status == "compared"
    assert set(result.comparison_variants) == {"safe", "semantic_redraw_direct", "semantic_redraw_structured"}
    for mode in ("semantic_redraw_direct", "semantic_redraw_structured"):
        variant = cast(ImageVariantCandidate, result.comparison_variants[mode])
        assert variant.bytes is None
        assert str(variant.final_reason).startswith("compare_all_semantic_variant_equals_safe:")
    insertions = result.resolved_delivery_payload().insertions
    assert [insertion.variant_key for insertion in insertions] == ["safe"]


def test_compare_all_still_delivers_semantic_variants_that_differ(resolved_test_model_registry):
    """FR-032 counter-proof: genuinely different semantic variants are all delivered."""
    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry},
        generate_image_candidate_fn=lambda image_bytes, analysis, *, mode, **kwargs: PNG_BYTES + mode.encode("ascii"),
    )

    result = cast(ImageAsset, _prepare_compare_variants(_build_asset(), _build_analysis(), context, client=object()))

    insertions = result.resolved_delivery_payload().insertions
    assert [insertion.variant_key for insertion in insertions] == [
        "safe",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    ]


def test_compare_all_document_budget_covers_two_semantic_variants():
    """FR-022 (M7): each semantic variant has its own per-image budget, so compare_all
    needs 2 × per_image + 1 calls per image; the old flat 7 was below one variant's 9."""
    config = {"semantic_redraw_max_model_calls_per_image": 9}

    assert image_pipeline._resolve_document_model_call_budget(config, total_images=3, image_mode="compare_all") == 3 * 19
    # Counter-proof: the single-mode estimate is unchanged.
    assert (
        image_pipeline._resolve_document_model_call_budget(config, total_images=3, image_mode="semantic_redraw_direct")
        == 3 * 10
    )
    # Without the per-image key the budget follows `semantic_redraw_max_attempts` (the key
    # `resources/config.toml` ships): 2 attempts × 3 calls = 6 per variant. Spec 066 C-12
    # removed the per-document override, which no config layer produced.
    assert (
        image_pipeline._resolve_document_model_call_budget(
            {"semantic_redraw_max_attempts": 2}, total_images=3, image_mode="compare_all"
        )
        == 3 * 13
    )


# --- spec 062 acceptance review 2026-11-07 (Codex): selection and compare_all delivery ---


_LABELS_MISSING_SOFT = dict(
    validation_passed=False,
    decision="fallback_safe",
    missing_labels=["review"],
    suspicious_reasons=["missing_labels:review"],
)


def test_second_candidate_scoring_lower_does_not_replace_the_first(resolved_test_model_registry):
    """Finding 1: on the last attempt the challenger check is necessarily False and the code
    returned the second candidate, discarding a better first one (7 of 22 two-attempt cells
    of the 2026-11-07 comparison). The review's input: both ``accept_soft``, the second with
    a lower score."""
    first = _build_validation_result(
        semantic_match_score=0.9, text_match_score=0.9, structure_match_score=0.9, validator_confidence=0.9,
        **_LABELS_MISSING_SOFT,
    )
    second = _build_validation_result(
        semantic_match_score=0.5, text_match_score=0.5, structure_match_score=0.5, validator_confidence=0.5,
        **_LABELS_MISSING_SOFT,
    )

    result, validator_calls, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"candidate1", PNG_BYTES + b"candidate2"],
        validations=[first, second],
    )

    assert len(validator_calls) == 2
    assert result.final_decision == "accept_soft"
    assert result.final_variant == "redrawn"
    assert result.redrawn_bytes == PNG_BYTES + b"candidate1"
    assert image_pipeline.score_semantic_candidate(result) > 0.9
    # Both attempts stay recorded on the delivered asset.
    assert [variant.mode for variant in result.attempt_variants] == ["candidate1", "candidate2"]


def test_second_candidate_scoring_higher_still_wins(resolved_test_model_registry):
    """Counter-proof: a challenger that scores higher is delivered."""
    first = _build_validation_result(
        semantic_match_score=0.5, text_match_score=0.5, structure_match_score=0.5, validator_confidence=0.5,
        **_LABELS_MISSING_SOFT,
    )
    second = _build_validation_result(
        semantic_match_score=0.9, text_match_score=0.9, structure_match_score=0.9, validator_confidence=0.9,
        **_LABELS_MISSING_SOFT,
    )

    result, _, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"candidate1", PNG_BYTES + b"candidate2"],
        validations=[first, second],
    )

    assert result.redrawn_bytes == PNG_BYTES + b"candidate2"
    assert [variant.mode for variant in result.attempt_variants] == ["candidate1", "candidate2"]


def test_unreadable_second_candidate_does_not_replace_the_first(resolved_test_model_registry):
    first = _build_validation_result(**_LABELS_MISSING_SOFT)
    unreadable = _build_validation_result(
        validation_passed=False,
        decision="fallback_safe",
        suspicious_reasons=["candidate_image_unreadable"],
    )

    result, _, _ = _run_semantic_selection(
        resolved_test_model_registry,
        candidates=[PNG_BYTES + b"candidate1", PNG_BYTES + b"candidate2"],
        validations=[first, unreadable],
    )

    assert result.final_variant == "redrawn"
    assert result.redrawn_bytes == PNG_BYTES + b"candidate1"


def test_second_candidate_equal_to_original_or_safe_keeps_the_first(resolved_test_model_registry):
    """Finding 1, second half: the early returns for a candidate equal to the source
    (FR-017) or to the safe picture dropped the first, scored candidate."""
    for second_bytes, name in ((PNG_BYTES, "original"), (PNG_BYTES + b"safe", "safe")):
        result, validator_calls, _ = _run_semantic_selection(
            resolved_test_model_registry,
            candidates=[PNG_BYTES + b"candidate1", second_bytes],
            validations=[_build_validation_result(**_LABELS_MISSING_SOFT)],
        )

        assert len(validator_calls) == 1, name
        assert result.final_variant == "redrawn", name
        assert result.final_decision == "accept_soft", name
        assert result.redrawn_bytes == PNG_BYTES + b"candidate1", name
        assert [variant.mode for variant in result.attempt_variants] == ["candidate1"], name


def test_compare_all_never_captions_the_original_as_a_redraw(resolved_test_model_registry):
    """Finding 5: generation handed the source back (FR-017, pixel-budget refusal on the
    output) while the safe picture differs from it. The semantic variants became
    ``fallback_original`` and the comparison builder read ``final_bytes`` — the original —
    and put it into the DOCX under the creative and structural captions. Only equality with
    the safe picture was suppressed."""

    def _generate(image_bytes, analysis, *, mode, **kwargs):
        return PNG_BYTES + b"safe" if mode == "safe" else image_bytes

    context = _build_context(
        resolved_test_model_registry,
        config={"models": resolved_test_model_registry},
        generate_image_candidate_fn=_generate,
    )

    result = cast(ImageAsset, _prepare_compare_variants(_build_asset(), _build_analysis(), context, client=object()))

    assert result.validation_status == "compared"
    for mode in ("semantic_redraw_direct", "semantic_redraw_structured"):
        variant = cast(ImageVariantCandidate, result.comparison_variants[mode])
        assert variant.final_variant == "original", mode
        assert variant.bytes is None, mode
        assert str(variant.final_reason).startswith("compare_all_semantic_variant_not_redrawn:original:"), mode
    insertions = result.resolved_delivery_payload().insertions
    assert [insertion.variant_key for insertion in insertions] == ["safe"]
    assert all(insertion.bytes != PNG_BYTES for insertion in insertions)
