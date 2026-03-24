import logging
import traceback
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol, TypeAlias, cast

from image_pipeline_policy import build_generation_analysis, is_hard_validation_failure, resolve_validation_delivery_outcome, should_attempt_semantic_redraw
from models import ImageAnalysisResult, ImageMode, ImageValidationResult, ImageVariantCandidate


class _ImageModelCallBudgetLike(Protocol):
    def ensure_available(self, operation_name: str) -> None:
        ...

    def consume(self, operation_name: str) -> None:
        ...


_Callback: TypeAlias = Callable[..., object]
_BudgetFactory: TypeAlias = Callable[[int], _ImageModelCallBudgetLike]
_BudgetExceededClass: TypeAlias = type[Exception]
_AnalyzeImageFn: TypeAlias = Callable[..., ImageAnalysisResult]
_GenerateImageCandidateFn: TypeAlias = Callable[..., bytes]
_ValidateRedrawResultFn: TypeAlias = Callable[..., ImageValidationResult]


@dataclass(frozen=True)
class _CompositeImageModelCallBudget:
    budgets: tuple[_ImageModelCallBudgetLike, ...]

    def ensure_available(self, operation_name: str) -> None:
        for budget in self.budgets:
            budget.ensure_available(operation_name)

    def consume(self, operation_name: str) -> None:
        self.ensure_available(operation_name)
        for budget in self.budgets:
            budget.consume(operation_name)


@dataclass
class ImageProcessingContext:
    config: Mapping[str, object]
    on_progress: _Callback
    runtime: object | None
    client: object | None
    emit_state: _Callback
    emit_image_reset: _Callback
    emit_finalize: _Callback
    emit_activity: _Callback
    emit_status: _Callback
    emit_image_log: _Callback
    should_stop: Callable[[object | None], bool]
    analyze_image_fn: _AnalyzeImageFn
    generate_image_candidate_fn: _GenerateImageCandidateFn
    validate_redraw_result_fn: _ValidateRedrawResultFn
    get_client_fn: Callable[[], object]
    log_event_fn: _Callback
    detect_image_mime_type_fn: Callable[[bytes], str | None]
    image_model_call_budget_cls: _BudgetFactory
    image_model_call_budget_exceeded_cls: _BudgetExceededClass
    document_call_budget: _ImageModelCallBudgetLike | None = None

    def ensure_client(self) -> object:
        if self.client is None:
            self.client = self.get_client_fn()
        return self.client

    def analyze_image(
        self,
        image_bytes: bytes,
        *,
        mime_type: str | None,
        client=None,
        budget: _ImageModelCallBudgetLike | None = None,
    ) -> ImageAnalysisResult:
        return self.analyze_image_fn(
            image_bytes,
            model=_config_str(self.config, "validation_model", ""),
            mime_type=mime_type,
            client=client,
            enable_vision=_config_bool(self.config, "enable_vision_image_analysis", True),
            dense_text_bypass_threshold=_config_int(self.config, "dense_text_bypass_threshold", 18),
            non_latin_text_bypass_threshold=_config_int(self.config, "non_latin_text_bypass_threshold", 12),
            budget=budget,
        )

    def generate_candidate(
        self,
        image_bytes: bytes,
        analysis: ImageAnalysisResult,
        *,
        mode: str,
        client=None,
        budget: _ImageModelCallBudgetLike | None = None,
    ) -> bytes:
        return self.generate_image_candidate_fn(
            image_bytes,
            analysis,
            mode=mode,
            prefer_deterministic_reconstruction=_config_bool(self.config, "prefer_deterministic_reconstruction", True),
            reconstruction_model=_config_optional_str(self.config.get("reconstruction_model")),
            reconstruction_render_config=_build_reconstruction_render_config(self.config),
            client=client,
            budget=budget,
        )

    def validate_redraw_result(
        self,
        original_image: bytes,
        candidate_image: bytes,
        analysis_before: ImageAnalysisResult,
        *,
        candidate_analysis: ImageAnalysisResult,
        image_context: Mapping[str, object],
        client=None,
        budget: _ImageModelCallBudgetLike | None = None,
    ) -> ImageValidationResult:
        return self.validate_redraw_result_fn(
            original_image,
            candidate_image,
            analysis_before,
            candidate_analysis=candidate_analysis,
            config=self.config,
            image_context=image_context,
            client=client,
            enable_vision_validation=_config_bool(self.config, "enable_vision_image_validation", True),
            validation_model=_config_str(self.config, "validation_model", "gpt-4.1"),
            budget=budget,
        )

    def build_document_call_budget(self, *, total_images: int, image_mode: str) -> _ImageModelCallBudgetLike:
        if self.document_call_budget is None:
            self.document_call_budget = self.image_model_call_budget_cls(
                _resolve_document_model_call_budget(self.config, total_images=total_images, image_mode=image_mode)
            )
        return self.document_call_budget

    def compose_budget(self, *budgets: _ImageModelCallBudgetLike | None) -> _ImageModelCallBudgetLike | None:
        active_budgets = tuple(budget for budget in budgets if budget is not None)
        if not active_budgets:
            return None
        if len(active_budgets) == 1:
            return active_budgets[0]
        return _CompositeImageModelCallBudget(active_budgets)


def _mark_asset_as_unsupported_source(asset, *, detected_mime_type, log_event_fn):
    source_mime_type = detected_mime_type or asset.mime_type or "unknown"
    asset.apply_final_selection_outcome(
        validation_status="skipped",
        final_decision="fallback_original",
        final_variant="original",
        final_reason=f"unsupported_source_image_format:{source_mime_type}",
    )
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


def _apply_validation_result_to_asset(asset, validation_result, *, image_mode: str, config: dict[str, object], log_event_fn):
    validation_policy = str(config.get("semantic_validation_policy", "advisory")).strip().lower() or "advisory"
    context = {
        "image_id": asset.image_id,
        "placeholder": asset.placeholder,
        "image_mode": image_mode,
        "semantic_validation_policy": validation_policy,
    }

    asset.mode_requested = image_mode
    asset.update_runtime_attempt_state(validation_result=validation_result)
    asset.apply_final_selection_outcome(
        validation_status="passed" if validation_result.validation_passed else "failed",
        strict_validation_decision=validation_result.decision,
        strict_validation_passed=validation_result.validation_passed,
    )

    outcome = resolve_validation_delivery_outcome(
        validation_result,
        validation_policy=validation_policy,
        has_safe_fallback=bool(asset.safe_bytes),
    )
    asset.apply_final_selection_outcome(
        validation_status=str(outcome["validation_status"]),
        final_decision=str(outcome["final_decision"]),
        final_variant=str(outcome["final_variant"]),
        final_reason=str(outcome["final_reason"]),
        soft_accepted=bool(outcome["soft_accepted"]),
    )

    if asset.final_decision == "accept_soft":
        log_event_fn(
            logging.INFO,
            "image_validation_advisory_accept",
            "Validator вернул fallback, но semantic redraw сохранен по advisory-policy.",
            validator_decision=validation_result.decision,
            suspicious_reasons=validation_result.suspicious_reasons,
            **context,
        )
    elif asset.final_decision not in {"accept", "accept_soft"}:
        log_event_fn(
            logging.WARNING,
            "image_fallback_applied",
            "Применен fallback по результату post-check",
            final_decision=asset.final_decision,
            final_variant=asset.final_variant,
            final_reason=asset.final_reason,
            **context,
        )

    return asset


def _validate_semantic_attempt(
    attempt_asset,
    *,
    image_mode: str,
    pipeline_context: ImageProcessingContext,
    candidate_analysis,
    client,
    budget=None,
):
    validation_result = pipeline_context.validate_redraw_result(
        attempt_asset.original_bytes,
        attempt_asset.redrawn_bytes,
        attempt_asset.analysis_result,
        candidate_analysis=candidate_analysis,
        image_context={
            "image_id": attempt_asset.image_id,
            "placeholder": attempt_asset.placeholder,
            "image_mode": image_mode,
        },
        client=client,
        budget=budget,
    )
    return _apply_validation_result_to_asset(
        attempt_asset,
        validation_result,
        image_mode=image_mode,
        config=dict(pipeline_context.config),
        log_event_fn=pipeline_context.log_event_fn,
    )


def _build_attempt_variant(attempt_asset, *, attempt_index: int) -> ImageVariantCandidate:
    return ImageVariantCandidate(
        mode=f"candidate{attempt_index}",
        bytes=attempt_asset.redrawn_bytes,
        mime_type=attempt_asset.redrawn_mime_type,
        validation_result=attempt_asset.validation_result,
        validation_status=attempt_asset.validation_status,
        final_decision=attempt_asset.final_decision,
        final_variant=attempt_asset.final_variant,
        final_reason=attempt_asset.final_reason,
    )


def _should_request_challenger_candidate(attempt_asset, *, attempt_index: int, attempt_count: int) -> bool:
    if attempt_index >= attempt_count:
        return False
    if getattr(attempt_asset, "final_variant", None) != "redrawn":
        return False

    validation_result = getattr(attempt_asset, "validation_result", None)
    if validation_result is None:
        return False
    if is_hard_validation_failure(validation_result):
        return False
    if getattr(attempt_asset, "final_decision", None) == "accept_soft":
        return True
    return getattr(attempt_asset, "validation_status", None) == "failed"


def _build_compare_variant_candidate(
    asset,
    analysis,
    candidate_mode: str,
    pipeline_context: ImageProcessingContext,
    *,
    client,
    budget=None,
):
    candidate_bytes = pipeline_context.generate_candidate(
        asset.original_bytes,
        analysis,
        mode=candidate_mode,
        client=client,
        budget=budget,
    )
    candidate_mime_type = pipeline_context.detect_image_mime_type_fn(candidate_bytes)
    variant = ImageVariantCandidate(
        mode=candidate_mode,
        bytes=candidate_bytes,
        mime_type=candidate_mime_type,
    )

    if candidate_mode == ImageMode.SAFE.value:
        variant.validation_status = "skipped"
        variant.final_decision = "accept"
        variant.final_variant = ImageMode.SAFE.value
        variant.final_reason = "compare_all_safe_variant_ready"
        asset.safe_bytes = candidate_bytes
        return variant

    if asset.safe_bytes and candidate_bytes == asset.safe_bytes:
        variant.validation_status = "skipped"
        variant.final_decision = "fallback_safe"
        variant.final_variant = ImageMode.SAFE.value
        variant.final_reason = "semantic_redraw_fell_back_to_safe_candidate"
        return variant

    attempt_asset = _clone_image_asset_for_attempt(asset)
    attempt_asset.safe_bytes = asset.safe_bytes
    attempt_asset.update_runtime_attempt_state(
        redrawn_bytes=candidate_bytes,
        redrawn_mime_type=candidate_mime_type,
    )
    attempt_asset.update_pipeline_metadata(rendered_mime_type=candidate_mime_type)
    candidate_analysis = pipeline_context.analyze_image(
        candidate_bytes,
        mime_type=candidate_mime_type or attempt_asset.mime_type,
        client=client,
        budget=budget,
    )
    attempt_asset = _validate_semantic_attempt(
        attempt_asset,
        image_mode=candidate_mode,
        pipeline_context=pipeline_context,
        candidate_analysis=candidate_analysis,
        client=client,
        budget=budget,
    )
    variant.validation_result = attempt_asset.validation_result
    variant.validation_status = attempt_asset.validation_status
    variant.final_decision = attempt_asset.final_decision
    variant.final_variant = attempt_asset.final_variant
    variant.final_reason = attempt_asset.final_reason
    return variant


def _apply_compare_all_incomplete_fallback(asset, *, prepared_modes: list[str]) -> object:
    asset.apply_final_selection_outcome(
        validation_status="failed",
        final_decision="fallback_safe" if asset.safe_bytes else "fallback_original",
        final_variant=ImageMode.SAFE.value if asset.safe_bytes else "original",
        final_reason=f"compare_all_variants_incomplete:{', '.join(prepared_modes) or 'none'}",
        clear_selected_compare_variant=True,
    )
    return asset


def _apply_safe_fallback_outcome(asset, *, reason: str, validation_status: str = "skipped"):
    asset.apply_final_selection_outcome(
        validation_status=validation_status,
        final_decision="fallback_safe",
        final_variant=ImageMode.SAFE.value,
        final_reason=reason,
    )
    return asset


def _apply_original_fallback_outcome(asset, *, reason: str, validation_status: str):
    asset.apply_final_selection_outcome(
        validation_status=validation_status,
        final_decision="fallback_original",
        final_variant="original",
        final_reason=reason,
    )
    return asset


def select_best_semantic_asset(
    asset,
    analysis,
    image_mode: str,
    *,
    pipeline_context: ImageProcessingContext,
    client,
):
    # Keep semantic redraw bounded and explainable: at most two generated
    # candidates are evaluated, and each successful candidate is preserved on the
    # asset so manual-review DOCX output can show why the final verdict won.
    attempt_count = max(1, min(_config_int(pipeline_context.config, "semantic_redraw_max_attempts", 2), 2))
    max_model_calls = max(
        1,
        _config_int(pipeline_context.config, "semantic_redraw_max_model_calls_per_image", attempt_count * 3),
    )
    image_call_budget = pipeline_context.image_model_call_budget_cls(max_model_calls)
    operation_budget = pipeline_context.compose_budget(image_call_budget, pipeline_context.document_call_budget)
    best_asset = None
    best_score = -1.0
    budget_exhausted = False
    budget_exhausted_reason = "semantic_model_call_budget_exhausted"
    attempt_variants: list[ImageVariantCandidate] = []

    for attempt_index in range(1, attempt_count + 1):
        try:
            attempt_asset = _clone_image_asset_for_attempt(asset)
            candidate_bytes = pipeline_context.generate_candidate(
                attempt_asset.original_bytes,
                analysis,
                mode=image_mode,
                client=client,
                budget=operation_budget,
            )
            attempt_asset.update_runtime_attempt_state(redrawn_bytes=candidate_bytes)
            if attempt_asset.safe_bytes and attempt_asset.redrawn_bytes == attempt_asset.safe_bytes:
                _apply_safe_fallback_outcome(
                    attempt_asset,
                    reason="semantic_redraw_fell_back_to_safe_candidate",
                    validation_status="skipped",
                )
                pipeline_context.log_event_fn(
                    logging.WARNING,
                    "semantic_candidate_resolved_to_safe_fallback",
                    "Semantic redraw candidate совпал с safe candidate; применяю safe fallback без post-check.",
                    attempt_index=attempt_index,
                    **attempt_asset.to_log_context(),
                )
                attempt_asset.update_runtime_attempt_state(attempt_variants=list(attempt_variants))
                return attempt_asset
            attempt_asset.update_runtime_attempt_state(
                redrawn_mime_type=pipeline_context.detect_image_mime_type_fn(attempt_asset.redrawn_bytes)
            )
            attempt_asset.update_pipeline_metadata(rendered_mime_type=attempt_asset.redrawn_mime_type)
            candidate_analysis = pipeline_context.analyze_image(
                attempt_asset.redrawn_bytes,
                mime_type=attempt_asset.redrawn_mime_type or attempt_asset.mime_type,
                client=client,
                budget=operation_budget,
            )
            attempt_asset = _validate_semantic_attempt(
                attempt_asset,
                image_mode=image_mode,
                pipeline_context=pipeline_context,
                candidate_analysis=candidate_analysis,
                client=client,
                budget=operation_budget,
            )
        except pipeline_context.image_model_call_budget_exceeded_cls as exc:
            budget_exhausted = True
            budget_exhausted_reason = _resolve_budget_exhausted_reason(
                document_call_budget=pipeline_context.document_call_budget,
                image_call_budget=image_call_budget,
            )
            pipeline_context.log_event_fn(
                logging.WARNING,
                "semantic_candidate_budget_exhausted",
                "Достигнут budget внешних model calls для semantic redraw; дальнейшие попытки остановлены.",
                attempt_index=attempt_index,
                max_model_calls=getattr(image_call_budget, "max_calls", None),
                used_model_calls=getattr(image_call_budget, "used_calls", None),
                document_max_model_calls=getattr(pipeline_context.document_call_budget, "max_calls", None),
                document_used_model_calls=getattr(pipeline_context.document_call_budget, "used_calls", None),
                exhausted_reason=budget_exhausted_reason,
                error_message=str(exc),
                **asset.to_log_context(),
            )
            break
        except Exception as exc:
            pipeline_context.log_event_fn(
                logging.WARNING,
                "semantic_candidate_attempt_failed",
                "Не удалось оценить semantic redraw candidate, пробую следующую попытку.",
                attempt_index=attempt_index,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                **asset.to_log_context(),
            )
            continue

        attempt_variants.append(_build_attempt_variant(attempt_asset, attempt_index=attempt_index))
        attempt_asset.update_runtime_attempt_state(attempt_variants=list(attempt_variants))

        score = score_semantic_candidate(attempt_asset)
        pipeline_context.log_event_fn(
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
        if not _should_request_challenger_candidate(
            attempt_asset,
            attempt_index=attempt_index,
            attempt_count=attempt_count,
        ):
            return attempt_asset

    if best_asset is None:
        asset.update_runtime_attempt_state(attempt_variants=list(attempt_variants))
        if asset.safe_bytes:
            _apply_safe_fallback_outcome(
                asset,
                reason=budget_exhausted_reason if budget_exhausted else "semantic_candidate_attempts_exhausted",
                validation_status="failed" if budget_exhausted else "error",
            )
        else:
            _apply_original_fallback_outcome(
                asset,
                reason=budget_exhausted_reason if budget_exhausted else "semantic_candidate_attempts_exhausted",
                validation_status="failed" if budget_exhausted else "error",
            )
        return asset
    best_asset.update_runtime_attempt_state(attempt_variants=list(attempt_variants))
    return best_asset


def process_document_images(
    *,
    image_assets,
    image_mode: str,
    context: ImageProcessingContext,
):
    if not image_assets:
        context.emit_state(context.runtime, image_assets=[])
        return []

    if image_mode == ImageMode.NO_CHANGE.value:
        context.emit_image_reset(context.runtime)
        for asset in image_assets:
            asset.mode_requested = image_mode
            asset.apply_final_selection_outcome(
                validation_status="skipped",
                final_decision="accept",
                final_variant="original",
                final_reason="no_change_mode",
            )
            context.emit_image_log(
                context.runtime,
                image_id=asset.image_id,
                status="skipped",
                decision="accept",
                confidence=0.0,
                final_variant="original",
                final_reason="no_change_mode",
            )
        context.emit_state(context.runtime, image_assets=image_assets)
        return list(image_assets)

    processed_assets = []
    image_client = context.client
    document_call_budget = context.build_document_call_budget(total_images=len(image_assets), image_mode=image_mode)
    document_budget_exhausted = False
    context.emit_image_reset(context.runtime)
    total_images = len(image_assets)
    for index, asset in enumerate(image_assets, start=1):
        asset = cast(Any, asset)
        asset.update_pipeline_metadata(
            preserve_all_variants_in_docx=_should_preserve_all_variants_in_docx(context.config),
        )
        if context.should_stop(context.runtime):
            context.emit_finalize(
                context.runtime,
                "Остановлено пользователем",
                "Обработка изображений остановлена пользователем.",
                (index - 1) / max(total_images, 1),
                "stopped",
            )
            context.emit_activity(context.runtime, "Обработка изображений остановлена пользователем.")
            return processed_assets

        if document_budget_exhausted:
            _apply_original_fallback_outcome(
                asset,
                reason="document_model_call_budget_exhausted",
                validation_status="failed",
            )
            context.emit_image_log(
                context.runtime,
                image_id=asset.image_id,
                status="failed",
                decision=asset.final_decision,
                confidence=0.0,
                suspicious_reasons=[asset.final_reason],
                final_variant=asset.final_variant,
                final_reason=asset.final_reason,
            )
            processed_assets.append(asset)
            context.emit_state(context.runtime, image_assets=processed_assets)
            continue

        context.emit_status(
            context.runtime,
            stage="Обработка изображений",
            detail=f"Обрабатываю изображение {index} из {total_images}.",
            current_block=index,
            block_count=total_images,
            progress=index / max(total_images, 1),
            is_running=True,
        )
        context.emit_activity(context.runtime, f"Начата обработка изображения {index} из {total_images}.")
        context.on_progress(preview_title="Текущий Markdown")
        analysis = None
        try:
            detected_source_mime_type = context.detect_image_mime_type_fn(asset.original_bytes)
            if detected_source_mime_type is None:
                asset = _mark_asset_as_unsupported_source(
                    asset,
                    detected_mime_type=detected_source_mime_type,
                    log_event_fn=context.log_event_fn,
                )
                asset = cast(Any, asset)
                context.emit_image_log(
                    context.runtime,
                    image_id=asset.image_id,
                    status="skipped",
                    decision=asset.final_decision,
                    confidence=0.0,
                    suspicious_reasons=[asset.final_reason],
                    final_variant=asset.final_variant,
                    final_reason=asset.final_reason,
                )
                processed_assets.append(asset)
                context.emit_state(context.runtime, image_assets=processed_assets)
                continue

            asset.mime_type = detected_source_mime_type
            asset.update_pipeline_metadata(source_mime_type=detected_source_mime_type)
            analysis = context.analyze_image(
                asset.original_bytes,
                mime_type=detected_source_mime_type,
                client=image_client,
                budget=document_call_budget,
            )
            asset.analysis_result = analysis
            asset.prompt_key = analysis.prompt_key
            asset.render_strategy = analysis.render_strategy
            generation_analysis = build_generation_analysis(analysis)
            semantic_attempt_allowed = should_attempt_semantic_redraw(analysis, image_mode)

            if image_mode == ImageMode.SAFE.value:
                asset.safe_bytes = context.generate_candidate(
                    asset.original_bytes,
                    analysis,
                    mode=ImageMode.SAFE.value,
                    client=image_client,
                    budget=document_call_budget,
                )
                asset.apply_final_selection_outcome(
                    validation_status="skipped",
                    final_decision="accept",
                    final_variant=ImageMode.SAFE.value if asset.safe_bytes else "original",
                    final_reason="Изображение обработано в safe-mode.",
                )
            elif image_mode == ImageMode.COMPARE_ALL.value:
                if image_client is None:
                    image_client = context.ensure_client()
                asset = _prepare_compare_variants(
                    asset,
                    generation_analysis,
                    pipeline_context=context,
                    client=image_client,
                    budget=document_call_budget,
                )
                asset = cast(Any, asset)
            elif not semantic_attempt_allowed:
                asset.safe_bytes = context.generate_candidate(
                    asset.original_bytes,
                    analysis,
                    mode=ImageMode.SAFE.value,
                    client=image_client,
                    budget=document_call_budget,
                )
                asset.apply_final_selection_outcome(
                    validation_status="skipped",
                    final_decision="accept",
                    final_variant=ImageMode.SAFE.value if asset.safe_bytes else "original",
                    final_reason="Semantic redraw отключен для этого изображения, применен safe-mode.",
                )
            else:
                if image_client is None:
                    image_client = context.ensure_client()
                asset.safe_bytes = context.generate_candidate(
                    asset.original_bytes,
                    analysis,
                    mode=ImageMode.SAFE.value,
                    client=image_client,
                    budget=document_call_budget,
                )
                asset = select_best_semantic_asset(
                    asset,
                    generation_analysis,
                    image_mode,
                    pipeline_context=context,
                    client=image_client,
                )
                asset = cast(Any, asset)

            asset = cast(Any, asset)
            validation_result = asset.validation_result
            confidence = (
                float(getattr(validation_result, "validator_confidence", 0.0))
                if validation_result is not None
                else float(getattr(analysis, "confidence", 0.0))
            )
            context.emit_image_log(
                context.runtime,
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
                final_variant=asset.final_variant,
                final_reason=asset.final_reason,
            )
            processed_assets.append(asset)
        except context.image_model_call_budget_exceeded_cls as exc:
            asset = cast(Any, asset)
            document_budget_exhausted = _is_budget_exhausted(document_call_budget)
            _apply_original_fallback_outcome(
                asset,
                reason=(
                    "document_model_call_budget_exhausted" if document_budget_exhausted else "image_model_call_budget_exhausted"
                ),
                validation_status="failed",
            )
            context.emit_image_log(
                context.runtime,
                image_id=asset.image_id,
                status="failed",
                decision=asset.final_decision,
                confidence=float(getattr(analysis, "confidence", 0.0)) if analysis is not None else 0.0,
                suspicious_reasons=[asset.final_reason],
                final_variant=asset.final_variant,
                final_reason=asset.final_reason,
            )
            context.log_event_fn(
                logging.WARNING,
                "image_processing_budget_exhausted",
                "Обработка изображения остановлена из-за исчерпания model call budget.",
                exhausted_reason=asset.final_reason,
                document_max_model_calls=getattr(document_call_budget, "max_calls", None),
                document_used_model_calls=getattr(document_call_budget, "used_calls", None),
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                **asset.to_log_context(),
            )
            processed_assets.append(asset)
        except Exception as exc:
            asset = cast(Any, asset)
            _apply_original_fallback_outcome(
                asset,
                reason=f"image_processing_exception:{exc.__class__.__name__}",
                validation_status="error",
            )
            context.emit_image_log(
                context.runtime,
                image_id=asset.image_id,
                status="error",
                decision=asset.final_decision,
                confidence=float(getattr(analysis, "confidence", 0.0)) if analysis is not None else 0.0,
                suspicious_reasons=[asset.final_reason],
                final_variant=asset.final_variant,
                final_reason=asset.final_reason,
            )
            context.log_event_fn(
                logging.ERROR,
                "image_processing_failed",
                "Обработка изображения завершилась ошибкой, применен fallback на оригинал.",
                error_traceback=traceback.format_exc(),
                **asset.to_log_context(),
            )
            processed_assets.append(asset)

        context.emit_state(context.runtime, image_assets=processed_assets)
    return processed_assets


def _clone_image_asset_for_attempt(asset):
    cloned_asset = replace(
        asset,
        metadata=replace(asset.metadata),
        runtime_attempt_state=replace(asset.runtime_attempt_state),
    )
    cloned_asset.reset_runtime_attempt_state()
    cloned_asset.apply_final_selection_outcome(
        final_decision=None,
        final_variant=None,
        final_reason=None,
    )
    return cloned_asset


def _prepare_compare_variants(
    asset,
    analysis,
    pipeline_context: ImageProcessingContext,
    *,
    client,
    budget=None,
):
    variant_map: dict[str, ImageVariantCandidate] = {}
    candidate_modes = [
        ImageMode.SAFE.value,
        ImageMode.SEMANTIC_REDRAW_DIRECT.value,
        ImageMode.SEMANTIC_REDRAW_STRUCTURED.value,
    ]
    semantic_redraw_enabled = should_attempt_semantic_redraw(analysis, ImageMode.COMPARE_ALL.value)
    expected_modes = list(candidate_modes)

    for candidate_mode in candidate_modes:
        if candidate_mode != ImageMode.SAFE.value and not semantic_redraw_enabled:
            continue
        try:
            variant = _build_compare_variant_candidate(
                asset,
                analysis,
                candidate_mode,
                pipeline_context,
                client=client,
                budget=budget,
            )
        except Exception as exc:
            pipeline_context.log_event_fn(
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

    asset.update_runtime_attempt_state(comparison_variants=variant_map)
    prepared_modes = [mode for mode in candidate_modes if mode in variant_map]
    if len(prepared_modes) != len(expected_modes):
        return _apply_compare_all_incomplete_fallback(asset, prepared_modes=prepared_modes)

    asset.apply_final_selection_outcome(
        validation_status="compared",
        final_decision="compared",
        final_variant="original",
        final_reason=f"compare_all_variants_ready:{', '.join(prepared_modes)}",
        selected_compare_variant="original",
    )
    return asset


def _resolve_document_model_call_budget(
    config: Mapping[str, object],
    *,
    total_images: int,
    image_mode: str,
) -> int:
    explicit_limit = _coerce_positive_int(
        config.get("image_model_call_budget_per_document", config.get("semantic_redraw_max_model_calls_per_document"))
    )
    if explicit_limit is not None:
        return explicit_limit

    per_image_attempt_budget = max(
        1,
        _config_int(
            config,
            "semantic_redraw_max_model_calls_per_image",
            max(1, min(_config_int(config, "semantic_redraw_max_attempts", 2), 2)) * 3,
        ),
    )
    estimated_calls_per_image = 7 if image_mode == ImageMode.COMPARE_ALL.value else per_image_attempt_budget + 1
    return max(estimated_calls_per_image, max(1, total_images) * estimated_calls_per_image)


def _resolve_budget_exhausted_reason(*, document_call_budget, image_call_budget) -> str:
    if _is_budget_exhausted(document_call_budget):
        return "document_model_call_budget_exhausted"
    if image_call_budget is not None:
        return "semantic_model_call_budget_exhausted"
    return "image_model_call_budget_exhausted"


def _is_budget_exhausted(budget) -> bool:
    if budget is None:
        return False
    remaining_calls = getattr(budget, "remaining_calls", None)
    if isinstance(remaining_calls, int):
        return remaining_calls <= 0
    max_calls = getattr(budget, "max_calls", None)
    used_calls = getattr(budget, "used_calls", None)
    return isinstance(max_calls, int) and isinstance(used_calls, int) and used_calls >= max_calls


def _coerce_positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        parsed_value = int(value)
    elif isinstance(value, int):
        parsed_value = value
    elif isinstance(value, float):
        parsed_value = int(value)
    elif isinstance(value, str):
        try:
            parsed_value = int(value.strip())
        except ValueError:
            return None
    else:
        return None
    return parsed_value if parsed_value > 0 else None


def _config_int(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _config_float(config: Mapping[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _config_bool(config: Mapping[str, object], key: str, default: bool) -> bool:
    value = config.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized_value = value.strip().lower()
        if normalized_value in {"1", "true", "yes", "on"}:
            return True
        if normalized_value in {"0", "false", "no", "off"}:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _config_str(config: Mapping[str, object], key: str, default: str) -> str:
    return _coerce_str(config.get(key), default)


def _should_preserve_all_variants_in_docx(config: Mapping[str, object]) -> bool:
    return _config_bool(config, "keep_all_image_variants", False)


def _coerce_str(value: object, default: str = "") -> str:
    if value is None:
        return default
    normalized_value = str(value).strip()
    return normalized_value or default


def _config_optional_str(value: object) -> str | None:
    if value is None:
        return None
    normalized_value = str(value).strip()
    if not normalized_value or normalized_value.lower() in {"none", "null"}:
        return None
    return normalized_value


def _build_reconstruction_render_config(config: Mapping[str, object]) -> dict[str, object]:
    return {
        "min_canvas_short_side_px": _config_int(config, "reconstruction_min_canvas_short_side_px", 900),
        "target_min_font_px": _config_int(config, "reconstruction_target_min_font_px", 18),
        "max_upscale_factor": _config_float(config, "reconstruction_max_upscale_factor", 3.0),
        "background_sample_ratio": _config_float(config, "reconstruction_background_sample_ratio", 0.04),
        "background_color_distance_threshold": _config_float(
            config,
            "reconstruction_background_color_distance_threshold",
            48.0,
        ),
        "background_uniformity_threshold": _config_float(
            config,
            "reconstruction_background_uniformity_threshold",
            10.0,
        ),
    }
