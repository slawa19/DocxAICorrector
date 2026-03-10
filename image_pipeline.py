import inspect
import logging
from dataclasses import replace

from image_pipeline_policy import build_generation_analysis, should_attempt_semantic_redraw
from models import ImageVariantCandidate


def _mark_asset_as_unsupported_source(asset, *, detected_mime_type, log_event_fn):
    source_mime_type = detected_mime_type or asset.mime_type or "unknown"
    asset.validation_status = "skipped"
    asset.final_decision = "fallback_original"
    asset.final_variant = "original"
    asset.final_reason = f"unsupported_source_image_format:{source_mime_type}"
    log_event_fn(
        logging.WARNING,
        "image_processing_skipped_unsupported_source",
        "Исходное изображение имеет неподдерживаемый формат; оставляю оригинал без AI-обработки.",
        source_mime_type=asset.mime_type,
        detected_source_mime_type=detected_mime_type,
        **asset.to_log_context(),
    )
    return asset


def score_semantic_candidate(asset) -> float:
    validation_result = getattr(asset, "validation_result", None)
    if validation_result is None:
        return -1.0

    score = float(getattr(validation_result, "validator_confidence", 0.0))
    score += 0.20 * float(getattr(validation_result, "semantic_match_score", 0.0))
    score += 0.20 * float(getattr(validation_result, "text_match_score", 0.0))
    score += 0.20 * float(getattr(validation_result, "structure_match_score", 0.0))

    suspicious_reasons = list(getattr(validation_result, "suspicious_reasons", []))
    if any(reason == "candidate_image_unreadable" for reason in suspicious_reasons):
        return -1.0
    if any(reason == "image_type_changed" for reason in suspicious_reasons):
        score -= 0.35
    if any(str(reason).startswith("added_entities:") for reason in suspicious_reasons):
        score -= 0.30

    if getattr(asset, "final_variant", None) == "redrawn" and getattr(asset, "final_decision", None) == "accept":
        score += 1.0
    return score


def try_soft_accept_semantic_candidate(asset, analysis, image_mode: str, config: dict[str, object], *, log_event_fn):
    validation_result = getattr(asset, "validation_result", None)
    if validation_result is None or not getattr(asset, "redrawn_bytes", None):
        return asset

    suspicious_reasons = list(getattr(validation_result, "suspicious_reasons", []))
    if any(reason == "candidate_image_unreadable" for reason in suspicious_reasons):
        return asset

    min_confidence = float(
        config.get(
            "semantic_soft_accept_confidence",
            0.64 if image_mode == "semantic_redraw_structured" or analysis.contains_text else 0.58,
        )
    )
    min_semantic = float(config.get("semantic_soft_accept_semantic_match", 0.58))
    min_text = float(config.get("semantic_soft_accept_text_match", 0.72 if analysis.contains_text else 0.0))
    min_structure = float(
        config.get(
            "semantic_soft_accept_structure_match",
            0.64 if analysis.render_strategy == "semantic_redraw_structured" else 0.48,
        )
    )

    if (
        float(getattr(validation_result, "validator_confidence", 0.0)) < min_confidence
        or float(getattr(validation_result, "semantic_match_score", 0.0)) < min_semantic
        or float(getattr(validation_result, "text_match_score", 0.0)) < min_text
        or float(getattr(validation_result, "structure_match_score", 0.0)) < min_structure
    ):
        return asset

    asset.validation_status = "soft-pass"
    asset.final_decision = "accept_soft"
    asset.final_variant = "redrawn"
    asset.final_reason = (
        "Выбран лучший semantic redraw после нескольких попыток; "
        f"validator отметил умеренные расхождения: {'; '.join(suspicious_reasons) or 'нет'}"
    )
    log_event_fn(
        logging.INFO,
        "image_soft_accept_applied",
        "Применен мягкий accept для лучшего semantic redraw candidate.",
        **asset.to_log_context(),
    )
    asset.update_pipeline_metadata(soft_accepted=True)
    return asset


def _build_compare_variant_candidate(
    asset,
    analysis,
    candidate_mode: str,
    config: dict[str, object],
    *,
    client,
    analyze_image_fn,
    generate_image_candidate_fn,
    process_image_asset_fn,
    detect_image_mime_type_fn,
):
    candidate_bytes = _call_with_supported_kwargs(
        generate_image_candidate_fn,
        asset.original_bytes,
        analysis,
        mode=candidate_mode,
        prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
        reconstruction_model=str(config.get("reconstruction_model", "")) or None,
        reconstruction_render_config=_build_reconstruction_render_config(config),
        client=client,
    )
    candidate_mime_type = detect_image_mime_type_fn(candidate_bytes)
    variant = ImageVariantCandidate(
        mode=candidate_mode,
        bytes=candidate_bytes,
        mime_type=candidate_mime_type,
    )

    if candidate_mode == "safe":
        variant.validation_status = "skipped"
        variant.final_decision = "accept"
        variant.final_variant = "safe"
        variant.final_reason = "compare_all_safe_variant_prepared"
        asset.safe_bytes = candidate_bytes
        return variant

    if asset.safe_bytes and candidate_bytes == asset.safe_bytes:
        variant.validation_status = "skipped"
        variant.final_decision = "fallback_safe"
        variant.final_variant = "safe"
        variant.final_reason = "semantic_redraw_fell_back_to_safe_candidate"
        return variant

    attempt_asset = _clone_image_asset_for_attempt(asset)
    attempt_asset.safe_bytes = asset.safe_bytes
    attempt_asset.redrawn_bytes = candidate_bytes
    attempt_asset.redrawn_mime_type = candidate_mime_type
    attempt_asset.update_pipeline_metadata(rendered_mime_type=candidate_mime_type)
    candidate_analysis = _call_with_supported_kwargs(
        analyze_image_fn,
        candidate_bytes,
        model=str(config.get("validation_model", "")),
        mime_type=candidate_mime_type or attempt_asset.mime_type,
        client=client,
        enable_vision=bool(config.get("enable_vision_image_analysis", True)),
        dense_text_bypass_threshold=int(config.get("dense_text_bypass_threshold", 18)),
        non_latin_text_bypass_threshold=int(config.get("non_latin_text_bypass_threshold", 12)),
    )
    attempt_asset = _call_with_supported_kwargs(
        process_image_asset_fn,
        attempt_asset,
        image_mode=candidate_mode,
        config=config,
        candidate_analysis=candidate_analysis,
        client=client,
        enable_vision_validation=bool(config.get("enable_vision_image_validation", True)),
    )
    variant.validation_result = attempt_asset.validation_result
    variant.validation_status = attempt_asset.validation_status
    variant.final_decision = attempt_asset.final_decision
    variant.final_variant = attempt_asset.final_variant
    variant.final_reason = attempt_asset.final_reason
    return variant


def select_best_semantic_asset(
    asset,
    analysis,
    image_mode: str,
    config: dict[str, object],
    *,
    client,
    analyze_image_fn,
    generate_image_candidate_fn,
    process_image_asset_fn,
    log_event_fn,
    detect_image_mime_type_fn,
    image_model_call_budget_cls,
    image_model_call_budget_exceeded_cls,
):
    attempt_count = max(1, int(config.get("semantic_redraw_max_attempts", 3)))
    max_model_calls = max(1, int(config.get("semantic_redraw_max_model_calls_per_image", attempt_count * 3)))
    call_budget = image_model_call_budget_cls(max_model_calls)
    best_asset = None
    best_score = -1.0
    budget_exhausted = False

    for attempt_index in range(1, attempt_count + 1):
        try:
            attempt_asset = _clone_image_asset_for_attempt(asset)
            attempt_asset.redrawn_bytes = _call_with_supported_kwargs(
                generate_image_candidate_fn,
                attempt_asset.original_bytes,
                analysis,
                mode=image_mode,
                prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
                reconstruction_model=str(config.get("reconstruction_model", "")) or None,
                reconstruction_render_config=_build_reconstruction_render_config(config),
                client=client,
                budget=call_budget,
            )
            if attempt_asset.safe_bytes and attempt_asset.redrawn_bytes == attempt_asset.safe_bytes:
                attempt_asset.validation_status = "skipped"
                attempt_asset.final_decision = "fallback_safe"
                attempt_asset.final_variant = "safe"
                attempt_asset.final_reason = "semantic_redraw_fell_back_to_safe_candidate"
                log_event_fn(
                    logging.WARNING,
                    "semantic_candidate_resolved_to_safe_fallback",
                    "Semantic redraw candidate совпал с safe candidate; применяю safe fallback без post-check.",
                    attempt_index=attempt_index,
                    **attempt_asset.to_log_context(),
                )
                return attempt_asset
            attempt_asset.redrawn_mime_type = detect_image_mime_type_fn(attempt_asset.redrawn_bytes)
            attempt_asset.update_pipeline_metadata(rendered_mime_type=attempt_asset.redrawn_mime_type)
            candidate_analysis = _call_with_supported_kwargs(
                analyze_image_fn,
                attempt_asset.redrawn_bytes,
                model=str(config.get("validation_model", "")),
                mime_type=attempt_asset.redrawn_mime_type or attempt_asset.mime_type,
                client=client,
                enable_vision=bool(config.get("enable_vision_image_analysis", True)),
                dense_text_bypass_threshold=int(config.get("dense_text_bypass_threshold", 18)),
                non_latin_text_bypass_threshold=int(config.get("non_latin_text_bypass_threshold", 12)),
            )
            attempt_asset = _call_with_supported_kwargs(
                process_image_asset_fn,
                attempt_asset,
                image_mode=image_mode,
                config=config,
                candidate_analysis=candidate_analysis,
                client=client,
                enable_vision_validation=bool(config.get("enable_vision_image_validation", True)),
            )
        except image_model_call_budget_exceeded_cls as exc:
            budget_exhausted = True
            log_event_fn(
                logging.WARNING,
                "semantic_candidate_budget_exhausted",
                "Достигнут budget внешних model calls для semantic redraw; дальнейшие попытки остановлены.",
                attempt_index=attempt_index,
                max_model_calls=call_budget.max_calls,
                used_model_calls=call_budget.used_calls,
                error_message=str(exc),
                **asset.to_log_context(),
            )
            break
        except Exception as exc:
            log_event_fn(
                logging.WARNING,
                "semantic_candidate_attempt_failed",
                "Не удалось оценить semantic redraw candidate, пробую следующую попытку.",
                attempt_index=attempt_index,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                **asset.to_log_context(),
            )
            continue

        score = score_semantic_candidate(attempt_asset)
        log_event_fn(
            logging.INFO,
            "semantic_candidate_evaluated",
            "Оценен semantic redraw candidate.",
            attempt_index=attempt_index,
            candidate_score=round(score, 4),
            **attempt_asset.to_log_context(),
        )
        if best_asset is None or score > best_score:
            best_asset = attempt_asset
            best_score = score
        if attempt_asset.final_variant == "redrawn" and attempt_asset.final_decision == "accept":
            return attempt_asset

    if best_asset is None:
        asset.validation_status = "failed" if budget_exhausted else "error"
        asset.final_decision = "fallback_original"
        asset.final_variant = "original"
        asset.final_reason = (
            "semantic_model_call_budget_exhausted" if budget_exhausted else "semantic_candidate_attempts_exhausted"
        )
        return asset
    return try_soft_accept_semantic_candidate(asset=best_asset, analysis=analysis, image_mode=image_mode, config=config, log_event_fn=log_event_fn)


def process_document_images(
    *,
    image_assets,
    image_mode: str,
    config: dict[str, object],
    on_progress,
    runtime,
    client,
    emit_state,
    emit_image_reset,
    emit_finalize,
    emit_activity,
    emit_status,
    emit_image_log,
    should_stop,
    analyze_image_fn,
    generate_image_candidate_fn,
    process_image_asset_fn,
    get_client_fn,
    log_event_fn,
    detect_image_mime_type_fn,
    image_model_call_budget_cls,
    image_model_call_budget_exceeded_cls,
):
    if not image_assets:
        emit_state(runtime, image_assets=[])
        return []

    processed_assets = []
    image_client = client
    emit_image_reset(runtime)
    total_images = len(image_assets)
    for index, asset in enumerate(image_assets, start=1):
        if should_stop(runtime):
            emit_finalize(
                runtime,
                "Остановлено пользователем",
                "Обработка изображений остановлена пользователем.",
                (index - 1) / max(total_images, 1),
            )
            emit_activity(runtime, "Обработка изображений остановлена пользователем.")
            return processed_assets

        emit_status(
            runtime,
            stage="Обработка изображений",
            detail=f"Обрабатываю изображение {index} из {total_images}.",
            current_block=index,
            block_count=total_images,
            progress=index / max(total_images, 1),
            is_running=True,
        )
        emit_activity(runtime, f"Начата обработка изображения {index} из {total_images}.")
        on_progress(preview_title="Текущий Markdown")
        analysis = None
        try:
            detected_source_mime_type = detect_image_mime_type_fn(asset.original_bytes)
            if detected_source_mime_type is None:
                asset = _mark_asset_as_unsupported_source(
                    asset,
                    detected_mime_type=detected_source_mime_type,
                    log_event_fn=log_event_fn,
                )
                emit_image_log(
                    runtime,
                    image_id=asset.image_id,
                    status="skipped",
                    decision=asset.final_decision,
                    confidence=0.0,
                    suspicious_reasons=[asset.final_reason],
                )
                processed_assets.append(asset)
                emit_activity(
                    runtime,
                    f"Изображение {asset.image_id}: {asset.final_variant or 'original'} | {asset.final_decision or 'accept'}.",
                )
                emit_state(runtime, image_assets=processed_assets)
                continue

            analysis = _call_with_supported_kwargs(
                analyze_image_fn,
                asset.original_bytes,
                model=str(config.get("validation_model", "")),
                mime_type=asset.mime_type,
                client=image_client,
                enable_vision=bool(config.get("enable_vision_image_analysis", True)),
                dense_text_bypass_threshold=int(config.get("dense_text_bypass_threshold", 18)),
                non_latin_text_bypass_threshold=int(config.get("non_latin_text_bypass_threshold", 12)),
            )
            asset.analysis_result = analysis
            asset.prompt_key = analysis.prompt_key
            asset.render_strategy = analysis.render_strategy
            generation_analysis = build_generation_analysis(analysis)
            semantic_attempt_allowed = should_attempt_semantic_redraw(analysis, image_mode)

            if image_mode == "safe":
                asset.safe_bytes = _call_with_supported_kwargs(
                    generate_image_candidate_fn,
                    asset.original_bytes,
                    analysis,
                    mode="safe",
                    prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
                    reconstruction_render_config=_build_reconstruction_render_config(config),
                    client=image_client,
                )
                asset.validation_status = "skipped"
                asset.final_decision = "accept"
                asset.final_variant = "safe" if asset.safe_bytes else "original"
                asset.final_reason = "Изображение обработано в safe-mode."
            elif image_mode == "compare_all":
                if image_client is None:
                    image_client = get_client_fn()
                asset = _prepare_compare_variants(
                    asset,
                    generation_analysis,
                    config,
                    client=image_client,
                    analyze_image_fn=analyze_image_fn,
                    generate_image_candidate_fn=generate_image_candidate_fn,
                    process_image_asset_fn=process_image_asset_fn,
                    detect_image_mime_type_fn=detect_image_mime_type_fn,
                    log_event_fn=log_event_fn,
                )
            elif not semantic_attempt_allowed:
                asset.safe_bytes = _call_with_supported_kwargs(
                    generate_image_candidate_fn,
                    asset.original_bytes,
                    analysis,
                    mode="safe",
                    prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
                    reconstruction_render_config=_build_reconstruction_render_config(config),
                    client=image_client,
                )
                asset.validation_status = "skipped"
                asset.final_decision = "accept"
                asset.final_variant = "safe" if asset.safe_bytes else "original"
                asset.final_reason = "Semantic redraw отключен для этого изображения, применен safe-mode."
            else:
                if image_client is None:
                    image_client = get_client_fn()
                asset.safe_bytes = _call_with_supported_kwargs(
                    generate_image_candidate_fn,
                    asset.original_bytes,
                    analysis,
                    mode="safe",
                    prefer_deterministic_reconstruction=bool(config.get("prefer_deterministic_reconstruction", True)),
                    reconstruction_render_config=_build_reconstruction_render_config(config),
                    client=image_client,
                )
                asset = select_best_semantic_asset(
                    asset,
                    generation_analysis,
                    image_mode,
                    config,
                    client=image_client,
                    analyze_image_fn=analyze_image_fn,
                    generate_image_candidate_fn=generate_image_candidate_fn,
                    process_image_asset_fn=process_image_asset_fn,
                    log_event_fn=log_event_fn,
                    detect_image_mime_type_fn=detect_image_mime_type_fn,
                    image_model_call_budget_cls=image_model_call_budget_cls,
                    image_model_call_budget_exceeded_cls=image_model_call_budget_exceeded_cls,
                )

            validation_result = asset.validation_result if hasattr(asset, "validation_result") else None
            confidence = (
                float(getattr(validation_result, "validator_confidence", 0.0))
                if validation_result is not None
                else float(getattr(analysis, "confidence", 0.0))
            )
            emit_image_log(
                runtime,
                image_id=asset.image_id,
                status=(
                    "compared"
                    if asset.validation_status == "compared"
                    else (
                    "validated"
                    if asset.validation_status in {"passed", "failed", "soft-pass"}
                    else asset.validation_status
                    )
                ),
                decision=asset.final_decision or "accept",
                confidence=confidence,
                missing_labels=(
                    list(getattr(validation_result, "missing_labels", [])) if validation_result is not None else []
                ),
                suspicious_reasons=(
                    list(getattr(validation_result, "suspicious_reasons", [])) if validation_result is not None else []
                ),
            )
            processed_assets.append(asset)
            emit_activity(
                runtime,
                f"Изображение {asset.image_id}: {asset.final_variant or 'original'} | {asset.final_decision or 'accept'}.",
            )
        except Exception as exc:
            asset.validation_status = "error"
            asset.final_decision = "fallback_original"
            asset.final_variant = "original"
            asset.final_reason = f"image_processing_exception:{exc.__class__.__name__}"
            emit_image_log(
                runtime,
                image_id=asset.image_id,
                status="error",
                decision=asset.final_decision,
                confidence=float(getattr(analysis, "confidence", 0.0)) if analysis is not None else 0.0,
                suspicious_reasons=[asset.final_reason],
            )
            log_event_fn(
                logging.ERROR,
                "image_processing_failed",
                "Обработка изображения завершилась ошибкой, применен fallback на оригинал.",
                **asset.to_log_context(),
            )
            processed_assets.append(asset)

        emit_state(runtime, image_assets=processed_assets)
    return processed_assets


def _call_with_supported_kwargs(callable_obj, *args, **kwargs):
    signature = inspect.signature(callable_obj)
    supported_kwargs = {name: value for name, value in kwargs.items() if name in signature.parameters}
    return callable_obj(*args, **supported_kwargs)


def _clone_image_asset_for_attempt(asset):
    cloned_asset = replace(
        asset,
        validation_result=None,
        validation_status="pending",
        final_decision=None,
        final_variant=None,
        final_reason=None,
        redrawn_bytes=None,
        reconstruction_scene_graph=None,
        redrawn_mime_type=None,
        metadata=replace(asset.metadata),
    )
    cloned_asset.update_pipeline_metadata(
        rendered_mime_type=None,
        strict_validation_decision=None,
        strict_validation_passed=None,
        soft_accepted=False,
    )
    return cloned_asset


def _prepare_compare_variants(
    asset,
    analysis,
    config: dict[str, object],
    *,
    client,
    analyze_image_fn,
    generate_image_candidate_fn,
    process_image_asset_fn,
    detect_image_mime_type_fn,
    log_event_fn,
):
    variant_map: dict[str, ImageVariantCandidate] = {}
    candidate_modes = ["safe"]
    if should_attempt_semantic_redraw(analysis, "compare_all"):
        candidate_modes.extend(["semantic_redraw_direct", "semantic_redraw_structured"])

    for candidate_mode in candidate_modes:
        try:
            variant = _build_compare_variant_candidate(
                asset,
                analysis,
                candidate_mode,
                config,
                client=client,
                analyze_image_fn=analyze_image_fn,
                generate_image_candidate_fn=generate_image_candidate_fn,
                process_image_asset_fn=process_image_asset_fn,
                detect_image_mime_type_fn=detect_image_mime_type_fn,
            )
        except Exception as exc:
            log_event_fn(
                logging.WARNING,
                "image_compare_variant_failed",
                "Не удалось подготовить один из compare-all вариантов изображения.",
                image_id=asset.image_id,
                candidate_mode=candidate_mode,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            continue

        variant_map[candidate_mode] = variant

    asset.comparison_variants = variant_map
    asset.selected_compare_variant = "original"
    asset.validation_status = "compared"
    asset.final_decision = "compared"
    asset.final_variant = "original"
    prepared_modes = [mode for mode in ["safe", "semantic_redraw_direct", "semantic_redraw_structured"] if mode in variant_map]
    asset.final_reason = f"Подготовлены compare-all варианты: {', '.join(prepared_modes)}."
    return asset


def _build_reconstruction_render_config(config: dict[str, object]) -> dict[str, object]:
    return {
        "min_canvas_short_side_px": int(config.get("reconstruction_min_canvas_short_side_px", 900)),
        "target_min_font_px": int(config.get("reconstruction_target_min_font_px", 18)),
        "max_upscale_factor": float(config.get("reconstruction_max_upscale_factor", 3.0)),
        "background_sample_ratio": float(config.get("reconstruction_background_sample_ratio", 0.04)),
        "background_color_distance_threshold": float(
            config.get("reconstruction_background_color_distance_threshold", 48.0)
        ),
        "background_uniformity_threshold": float(
            config.get("reconstruction_background_uniformity_threshold", 10.0)
        ),
    }
