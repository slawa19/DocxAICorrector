import copy
import logging


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
    if any(reason in {"candidate_image_unreadable", "image_type_changed"} for reason in suspicious_reasons):
        return asset
    if any(str(reason).startswith("added_entities:") for reason in suspicious_reasons):
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
    return asset


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
            attempt_asset = copy.deepcopy(asset)
            attempt_asset.redrawn_bytes = generate_image_candidate_fn(
                attempt_asset.original_bytes,
                analysis,
                mode=image_mode,
                client=client,
                budget=call_budget,
            )
            attempt_asset.redrawn_mime_type = detect_image_mime_type_fn(attempt_asset.redrawn_bytes)
            candidate_analysis = analyze_image_fn(
                attempt_asset.redrawn_bytes,
                model=str(config.get("validation_model", "")),
                mime_type=attempt_asset.redrawn_mime_type or attempt_asset.mime_type,
            )
            attempt_asset = process_image_asset_fn(
                attempt_asset,
                image_mode=image_mode,
                config=config,
                candidate_analysis=candidate_analysis,
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
            analysis = analyze_image_fn(
                asset.original_bytes,
                model=str(config.get("validation_model", "")),
                mime_type=asset.mime_type,
            )
            asset.analysis_result = analysis
            asset.prompt_key = analysis.prompt_key
            asset.render_strategy = analysis.render_strategy

            if image_mode == "safe" or not analysis.semantic_redraw_allowed:
                asset.safe_bytes = generate_image_candidate_fn(asset.original_bytes, analysis, mode="safe", client=image_client)
                asset.validation_status = "skipped"
                asset.final_decision = "accept"
                asset.final_variant = "safe" if asset.safe_bytes else "original"
                asset.final_reason = "Изображение обработано в safe-mode."
            else:
                if image_client is None:
                    image_client = get_client_fn()
                asset.safe_bytes = generate_image_candidate_fn(asset.original_bytes, analysis, mode="safe", client=image_client)
                asset = select_best_semantic_asset(
                    asset,
                    analysis,
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
                    "validated"
                    if asset.validation_status in {"passed", "failed", "soft-pass"}
                    else asset.validation_status
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