import logging
import re
from typing import Mapping

from logger import log_event
from models import ImageAnalysisResult, ImageAsset, ImageValidationResult

DEFAULT_VALIDATION_CONFIG: dict[str, object] = {
    "min_semantic_match_score": 0.75,
    "min_text_match_score": 0.80,
    "min_structure_match_score": 0.70,
    "validator_confidence_threshold": 0.75,
    "allow_accept_with_partial_text_loss": False,
}

_IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"RIFF",
)


def validate_redraw_result(
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult | dict[str, object],
    *,
    candidate_analysis: ImageAnalysisResult | dict[str, object] | None = None,
    config: Mapping[str, object] | None = None,
    image_context: Mapping[str, object] | None = None,
) -> ImageValidationResult:
    normalized_context = dict(image_context or {})
    try:
        normalized_analysis = _coerce_analysis_result(analysis_before)
        log_event(
            logging.INFO,
            "image_validation_started",
            "Запущен Level 1 post-check для изображения",
            image_type=normalized_analysis.image_type,
            render_strategy=normalized_analysis.render_strategy,
            **normalized_context,
        )
        result = _validate_redraw_result(
            original_image,
            candidate_image,
            normalized_analysis,
            candidate_analysis=candidate_analysis,
            config=config,
        )
    except Exception as exc:
        log_event(
            logging.ERROR,
            "image_validation_failed",
            "Validator завершился с ошибкой и применил консервативный fallback",
            image_type=_safe_image_type(analysis_before),
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            **normalized_context,
        )
        missing_labels = []
        if isinstance(analysis_before, ImageAnalysisResult):
            missing_labels = list(analysis_before.extracted_labels)
        elif isinstance(analysis_before, dict):
            missing_labels = [
                str(item).strip() for item in analysis_before.get("extracted_labels", []) if str(item).strip()
            ]
        return ImageValidationResult(
            validation_passed=False,
            decision="fallback_safe",
            semantic_match_score=0.0,
            text_match_score=0.0,
            structure_match_score=0.0,
            validator_confidence=0.0,
            missing_labels=missing_labels,
            added_entities_detected=False,
            suspicious_reasons=[f"validator_exception:{exc.__class__.__name__}"],
        )

    log_event(
        logging.INFO,
        "image_validation_completed",
        "Level 1 post-check завершен",
        image_type=normalized_analysis.image_type,
        validation_passed=result.validation_passed,
        decision=result.decision,
        semantic_match_score=result.semantic_match_score,
        text_match_score=result.text_match_score,
        structure_match_score=result.structure_match_score,
        validator_confidence=result.validator_confidence,
        suspicious_reasons=result.suspicious_reasons,
        **normalized_context,
    )
    return result


def process_image_asset(
    asset: ImageAsset,
    *,
    image_mode: str,
    config: Mapping[str, object],
    candidate_analysis: ImageAnalysisResult | dict[str, object] | None = None,
) -> ImageAsset:
    asset.mode_requested = image_mode
    context = {
        "image_id": asset.image_id,
        "placeholder": asset.placeholder,
        "image_mode": image_mode,
    }

    if image_mode not in {"semantic_redraw_direct", "semantic_redraw_structured"}:
        asset.validation_status = "skipped"
        asset.final_decision = "accept"
        asset.final_variant = "safe" if asset.safe_bytes else "original"
        asset.final_reason = "Пост-проверка пропущена для не-semantic режима."
        return asset

    if not asset.redrawn_bytes:
        asset.validation_status = "failed"
        asset.final_decision = "fallback_safe" if asset.safe_bytes else "fallback_original"
        asset.final_variant = "safe" if asset.safe_bytes else "original"
        asset.final_reason = "Не получен candidate image для post-check."
        log_event(
            logging.WARNING,
            "image_fallback_applied",
            "Пост-проверка не выполнена: отсутствует candidate image",
            final_decision=asset.final_decision,
            final_variant=asset.final_variant,
            **context,
        )
        return asset

    analysis_before = _coerce_analysis_result(asset.analysis_result)
    asset.prompt_key = asset.prompt_key or analysis_before.prompt_key
    asset.render_strategy = asset.render_strategy or analysis_before.render_strategy

    if not bool(config.get("enable_post_redraw_validation", True)):
        asset.validation_status = "skipped"
        asset.final_decision = "accept"
        asset.final_variant = "redrawn"
        asset.final_reason = "Пост-проверка отключена конфигурацией."
        return asset

    result = validate_redraw_result(
        asset.original_bytes,
        asset.redrawn_bytes,
        analysis_before,
        candidate_analysis=candidate_analysis,
        config=config,
        image_context=context,
    )
    asset.validation_result = result
    asset.validation_status = "passed" if result.validation_passed else "failed"

    if result.decision == "accept":
        asset.final_decision = "accept"
        asset.final_variant = "redrawn"
        asset.final_reason = "Validator подтвердил semantic redraw."
        return asset

    asset.final_decision = result.decision
    if result.decision == "fallback_safe" and asset.safe_bytes:
        asset.final_variant = "safe"
        asset.final_reason = "; ".join(result.suspicious_reasons) or "Validator запросил safe fallback."
    else:
        asset.final_decision = "fallback_original"
        asset.final_variant = "original"
        asset.final_reason = "; ".join(result.suspicious_reasons) or "Validator запросил fallback на оригинал."

    log_event(
        logging.WARNING,
        "image_fallback_applied",
        "Применен fallback по результату post-check",
        final_decision=asset.final_decision,
        final_variant=asset.final_variant,
        final_reason=asset.final_reason,
        **context,
    )
    return asset


def _validate_redraw_result(
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult,
    *,
    candidate_analysis: ImageAnalysisResult | dict[str, object] | None,
    config: Mapping[str, object] | None,
) -> ImageValidationResult:
    resolved_config = {**DEFAULT_VALIDATION_CONFIG, **dict(config or {})}

    if not _is_supported_image_bytes(original_image):
        return ImageValidationResult(
            validation_passed=False,
            decision="fallback_original",
            semantic_match_score=0.0,
            text_match_score=0.0,
            structure_match_score=0.0,
            validator_confidence=0.0,
            missing_labels=list(analysis_before.extracted_labels),
            added_entities_detected=False,
            suspicious_reasons=["original_image_unreadable"],
        )

    if not _is_supported_image_bytes(candidate_image):
        return ImageValidationResult(
            validation_passed=False,
            decision="fallback_original",
            semantic_match_score=0.0,
            text_match_score=0.0,
            structure_match_score=0.0,
            validator_confidence=0.0,
            missing_labels=list(analysis_before.extracted_labels),
            added_entities_detected=False,
            suspicious_reasons=["candidate_image_unreadable"],
        )

    normalized_candidate_analysis = _coerce_analysis_result(
        candidate_analysis or _build_conservative_candidate_analysis(analysis_before)
    )
    original_labels = _normalize_labels(analysis_before.extracted_labels)
    candidate_labels = _normalize_labels(normalized_candidate_analysis.extracted_labels)
    missing_labels = sorted(original_labels - candidate_labels)
    added_entities = sorted(candidate_labels - original_labels)

    type_match_score = _type_match_score(analysis_before.image_type, normalized_candidate_analysis.image_type)
    structure_match_score = _structure_match_score(
        analysis_before.structure_summary,
        normalized_candidate_analysis.structure_summary,
    )
    text_match_score = _text_match_score(
        analysis_before=analysis_before,
        candidate_analysis=normalized_candidate_analysis,
        missing_labels=missing_labels,
        allow_partial_text_loss=bool(resolved_config["allow_accept_with_partial_text_loss"]),
    )
    added_entities_detected = bool(added_entities)
    semantic_match_score = _clamp_score(
        (type_match_score + structure_match_score + (0.0 if added_entities_detected else 1.0)) / 3.0
    )

    validator_confidence = _clamp_score(
        (
            semantic_match_score
            + text_match_score
            + structure_match_score
            + _clamp_score(normalized_candidate_analysis.confidence)
        )
        / 4.0
    )

    suspicious_reasons: list[str] = []
    if type_match_score < 1.0:
        suspicious_reasons.append("image_type_changed")
    if analysis_before.contains_text and not normalized_candidate_analysis.contains_text:
        suspicious_reasons.append("text_missing_in_candidate")
    if missing_labels:
        suspicious_reasons.append(f"missing_labels:{', '.join(missing_labels)}")
    if added_entities_detected:
        suspicious_reasons.append(f"added_entities:{', '.join(added_entities)}")
    if structure_match_score < float(resolved_config["min_structure_match_score"]):
        suspicious_reasons.append("structure_mismatch")
    if validator_confidence < float(resolved_config["validator_confidence_threshold"]):
        suspicious_reasons.append("validator_confidence_too_low")

    validation_passed = (
        semantic_match_score >= float(resolved_config["min_semantic_match_score"])
        and text_match_score >= float(resolved_config["min_text_match_score"])
        and structure_match_score >= float(resolved_config["min_structure_match_score"])
        and validator_confidence >= float(resolved_config["validator_confidence_threshold"])
        and type_match_score >= 1.0
        and not added_entities_detected
        and (
            not missing_labels
            or bool(resolved_config["allow_accept_with_partial_text_loss"])
        )
        and (not analysis_before.contains_text or normalized_candidate_analysis.contains_text)
    )

    decision = "accept" if validation_passed else "fallback_safe"
    return ImageValidationResult(
        validation_passed=validation_passed,
        decision=decision,
        semantic_match_score=semantic_match_score,
        text_match_score=text_match_score,
        structure_match_score=structure_match_score,
        validator_confidence=validator_confidence,
        missing_labels=missing_labels,
        added_entities_detected=added_entities_detected,
        suspicious_reasons=suspicious_reasons,
    )


def _coerce_analysis_result(value: ImageAnalysisResult | dict[str, object] | None) -> ImageAnalysisResult:
    if isinstance(value, ImageAnalysisResult):
        return value
    if isinstance(value, dict):
        return ImageAnalysisResult(
            image_type=str(value.get("image_type", "unknown")),
            image_subtype=value.get("image_subtype") if isinstance(value.get("image_subtype"), str) else None,
            contains_text=bool(value.get("contains_text", False)),
            semantic_redraw_allowed=bool(value.get("semantic_redraw_allowed", False)),
            confidence=_clamp_score(float(value.get("confidence", 0.0))),
            structured_parse_confidence=_clamp_score(float(value.get("structured_parse_confidence", 0.0))),
            prompt_key=str(value.get("prompt_key", "")),
            render_strategy=str(value.get("render_strategy", "")),
            structure_summary=str(value.get("structure_summary", "")),
            extracted_labels=[str(item).strip() for item in value.get("extracted_labels", []) if str(item).strip()],
            fallback_reason=(str(value["fallback_reason"]) if value.get("fallback_reason") is not None else None),
        )
    raise RuntimeError("Не передан корректный ImageAnalysisResult для image post-check.")


def _build_conservative_candidate_analysis(analysis_before: ImageAnalysisResult) -> ImageAnalysisResult:
    return ImageAnalysisResult(
        image_type=analysis_before.image_type,
        image_subtype=analysis_before.image_subtype,
        contains_text=False if analysis_before.contains_text else analysis_before.contains_text,
        semantic_redraw_allowed=analysis_before.semantic_redraw_allowed,
        confidence=0.35,
        structured_parse_confidence=0.35,
        prompt_key=analysis_before.prompt_key,
        render_strategy=analysis_before.render_strategy,
        structure_summary="",
        extracted_labels=[],
        fallback_reason="candidate_analysis_missing",
    )


def _text_match_score(
    *,
    analysis_before: ImageAnalysisResult,
    candidate_analysis: ImageAnalysisResult,
    missing_labels: list[str],
    allow_partial_text_loss: bool,
) -> float:
    if not analysis_before.contains_text:
        return 1.0
    if not candidate_analysis.contains_text:
        return 0.0

    original_labels = _normalize_labels(analysis_before.extracted_labels)
    if not original_labels:
        return 1.0

    preserved_fraction = (len(original_labels) - len(missing_labels)) / len(original_labels)
    if allow_partial_text_loss:
        return _clamp_score(preserved_fraction)
    return 1.0 if not missing_labels else _clamp_score(preserved_fraction * 0.6)


def _type_match_score(original_type: str, candidate_type: str) -> float:
    normalized_original = original_type.strip().lower()
    normalized_candidate = candidate_type.strip().lower()
    if normalized_original == normalized_candidate:
        return 1.0
    if "unknown" in {normalized_original, normalized_candidate}:
        return 0.5
    return 0.0


def _structure_match_score(original_summary: str, candidate_summary: str) -> float:
    original_tokens = _summary_tokens(original_summary)
    candidate_tokens = _summary_tokens(candidate_summary)
    if not original_tokens and not candidate_tokens:
        return 1.0
    if not original_tokens or not candidate_tokens:
        return 0.0
    overlap = len(original_tokens & candidate_tokens) / len(original_tokens | candidate_tokens)
    return _clamp_score(overlap)


def _summary_tokens(summary: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Zа-яА-Я0-9]+", summary.lower()) if len(token) > 1}


def _normalize_labels(labels: list[str]) -> set[str]:
    return {
        normalized
        for normalized in (
            " ".join(re.findall(r"[a-zA-Zа-яА-Я0-9]+", label.lower())).strip()
            for label in labels
        )
        if normalized
    }


def _is_supported_image_bytes(image_bytes: bytes | None) -> bool:
    if not isinstance(image_bytes, bytes) or len(image_bytes) < 8:
        return False
    return any(image_bytes.startswith(signature) for signature in _IMAGE_SIGNATURES)


def _clamp_score(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _safe_image_type(analysis_before: ImageAnalysisResult | dict[str, object]) -> str:
    if isinstance(analysis_before, ImageAnalysisResult):
        return analysis_before.image_type
    if isinstance(analysis_before, dict):
        return str(analysis_before.get("image_type", "unknown"))
    return "unknown"
