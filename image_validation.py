import logging
import base64
import re
from typing import Mapping

from image_shared import (
    call_responses_create_with_retry,
    clamp_score,
    detect_image_mime_type,
    is_retryable_error,
    is_supported_image_bytes as shared_is_supported_image_bytes,
    parse_json_object,
)
from logger import log_event
from models import ImageAnalysisResult, ImageValidationResult

DEFAULT_VALIDATION_CONFIG: dict[str, object] = {
    "min_semantic_match_score": 0.75,
    "min_text_match_score": 0.80,
    "min_structure_match_score": 0.70,
    "validator_confidence_threshold": 0.75,
    "allow_accept_with_partial_text_loss": False,
}

VISION_VALIDATION_TIMEOUT_SECONDS = 45.0
VISION_VALIDATION_MAX_RETRIES = 2
_TEXT_TOKEN_PATTERN = re.compile(r"[0-9A-Za-zА-Яа-яІіЇїЄєҐґ]+")


def validate_redraw_result(
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult | dict[str, object],
    *,
    candidate_analysis: ImageAnalysisResult | dict[str, object] | None = None,
    config: Mapping[str, object] | None = None,
    image_context: Mapping[str, object] | None = None,
    client=None,
    enable_vision_validation: bool = True,
    validation_model: str | None = None,
    budget=None,
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
            vision_assessment=_maybe_build_vision_validation_assessment(
                original_image=original_image,
                candidate_image=candidate_image,
                analysis_before=normalized_analysis,
                candidate_analysis=_coerce_analysis_result(candidate_analysis) if candidate_analysis else None,
                client=client,
                model=validation_model or str((config or {}).get("validation_model", "gpt-4.1")),
                enable_vision_validation=enable_vision_validation,
                budget=budget,
            ),
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


def _validate_redraw_result(
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult,
    *,
    candidate_analysis: ImageAnalysisResult | dict[str, object] | None,
    config: Mapping[str, object] | None,
    vision_assessment: dict[str, object] | None = None,
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
    heuristic_result = ImageValidationResult(
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
    if vision_assessment is None:
        return heuristic_result
    return _merge_with_vision_assessment(
        heuristic_result,
        analysis_before,
        normalized_candidate_analysis,
        resolved_config,
        vision_assessment,
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
        contains_text=analysis_before.contains_text,
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
    return {token for token in _TEXT_TOKEN_PATTERN.findall(summary.lower()) if len(token) > 1}


def _normalize_labels(labels: list[str]) -> set[str]:
    return {
        normalized
        for normalized in (
            " ".join(_TEXT_TOKEN_PATTERN.findall(label.lower())).strip()
            for label in labels
        )
        if normalized
    }


def _is_supported_image_bytes(image_bytes: bytes | None) -> bool:
    return shared_is_supported_image_bytes(image_bytes)


def _clamp_score(value: float) -> float:
    return clamp_score(value)


def _safe_image_type(analysis_before: ImageAnalysisResult | dict[str, object]) -> str:
    if isinstance(analysis_before, ImageAnalysisResult):
        return analysis_before.image_type
    if isinstance(analysis_before, dict):
        return str(analysis_before.get("image_type", "unknown"))
    return "unknown"


def _build_vision_validation_assessment(
    *,
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult,
    candidate_analysis: ImageAnalysisResult | None,
    client,
    model: str,
    budget=None,
) -> dict[str, object]:
    original_mime = detect_image_mime_type(original_image)
    candidate_mime = detect_image_mime_type(candidate_image)
    if original_mime is None or candidate_mime is None:
        raise RuntimeError("Vision validation requires readable image payloads.")

    response = call_responses_create_with_retry(
        client,
        {
            "model": model or "gpt-4.1",
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You compare original and candidate document images conservatively. "
                                "Return strict JSON only and prefer fallback when uncertain."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Return JSON with keys: semantic_match_score, text_match_score, structure_match_score, "
                                "validator_confidence, candidate_contains_text, missing_labels, added_entities, suspicious_reasons. "
                                f"Original image_type={analysis_before.image_type}; original_labels={analysis_before.extracted_labels}; "
                                f"candidate_labels={candidate_analysis.extracted_labels if candidate_analysis else []}."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{original_mime};base64,{base64.b64encode(original_image).decode('ascii')}",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{candidate_mime};base64,{base64.b64encode(candidate_image).decode('ascii')}",
                        },
                    ],
                },
            ],
            "timeout": VISION_VALIDATION_TIMEOUT_SECONDS,
        },
        max_retries=VISION_VALIDATION_MAX_RETRIES,
        retryable_error_predicate=is_retryable_error,
        budget=budget,
    )
    return parse_json_object(
        getattr(response, "output_text", ""),
        empty_message="Vision validation returned empty output.",
        no_json_message="Vision validation did not return JSON.",
    )


def _maybe_build_vision_validation_assessment(
    *,
    original_image: bytes,
    candidate_image: bytes,
    analysis_before: ImageAnalysisResult,
    candidate_analysis: ImageAnalysisResult | None,
    client,
    model: str,
    enable_vision_validation: bool,
    budget=None,
) -> dict[str, object] | None:
    if not enable_vision_validation or not _supports_responses_client(client):
        return None
    try:
        return _build_vision_validation_assessment(
            original_image=original_image,
            candidate_image=candidate_image,
            analysis_before=analysis_before,
            candidate_analysis=candidate_analysis,
            client=client,
            model=model,
            budget=budget,
        )
    except Exception as exc:
        log_event(
            logging.WARNING,
            "image_vision_validation_skipped_after_failure",
            "Vision validation недоступен; продолжаю heuristic-only validation.",
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            image_type=analysis_before.image_type,
            validation_model=model,
        )
        return None




def _merge_with_vision_assessment(
    heuristic_result: ImageValidationResult,
    analysis_before: ImageAnalysisResult,
    candidate_analysis: ImageAnalysisResult,
    resolved_config: Mapping[str, object],
    vision_assessment: dict[str, object],
) -> ImageValidationResult:
    type_match_score = _type_match_score(analysis_before.image_type, candidate_analysis.image_type)
    missing_labels = sorted(set(heuristic_result.missing_labels) | set(_normalize_labels_list(vision_assessment.get("missing_labels", []))))
    added_entities = _normalize_labels_list(vision_assessment.get("added_entities", []))
    suspicious_reasons = list(dict.fromkeys(
        list(heuristic_result.suspicious_reasons)
        + [str(reason).strip() for reason in vision_assessment.get("suspicious_reasons", []) if str(reason).strip()]
    ))

    semantic_match_score = _clamp_score(
        (heuristic_result.semantic_match_score + _clamp_score(vision_assessment.get("semantic_match_score", 0.0))) / 2.0
    )
    vision_text_score = _clamp_score(vision_assessment.get("text_match_score", heuristic_result.text_match_score))
    text_match_score = min(heuristic_result.text_match_score, vision_text_score) if analysis_before.contains_text else max(heuristic_result.text_match_score, vision_text_score)
    structure_match_score = _clamp_score(
        (heuristic_result.structure_match_score + _clamp_score(vision_assessment.get("structure_match_score", 0.0))) / 2.0
    )
    validator_confidence = _clamp_score(
        (heuristic_result.validator_confidence + _clamp_score(vision_assessment.get("validator_confidence", 0.0))) / 2.0
    )
    added_entities_detected = heuristic_result.added_entities_detected or bool(added_entities)
    candidate_contains_text = bool(vision_assessment.get("candidate_contains_text", candidate_analysis.contains_text))

    if analysis_before.contains_text and not candidate_contains_text and "text_missing_in_candidate" not in suspicious_reasons:
        suspicious_reasons.append("text_missing_in_candidate")
    if type_match_score < 1.0 and "image_type_changed" not in suspicious_reasons:
        suspicious_reasons.append("image_type_changed")
    if missing_labels and not any(str(reason).startswith("missing_labels:") for reason in suspicious_reasons):
        suspicious_reasons.append(f"missing_labels:{', '.join(missing_labels)}")
    if added_entities_detected and not any(str(reason).startswith("added_entities:") for reason in suspicious_reasons):
        suspicious_reasons.append(f"added_entities:{', '.join(added_entities)}")

    validation_passed = (
        semantic_match_score >= float(resolved_config["min_semantic_match_score"])
        and text_match_score >= float(resolved_config["min_text_match_score"])
        and structure_match_score >= float(resolved_config["min_structure_match_score"])
        and validator_confidence >= float(resolved_config["validator_confidence_threshold"])
        and type_match_score >= 1.0
        and not added_entities_detected
        and (not missing_labels or bool(resolved_config["allow_accept_with_partial_text_loss"]))
        and (not analysis_before.contains_text or candidate_contains_text)
    )
    return ImageValidationResult(
        validation_passed=validation_passed,
        decision="accept" if validation_passed else "fallback_safe",
        semantic_match_score=semantic_match_score,
        text_match_score=text_match_score,
        structure_match_score=structure_match_score,
        validator_confidence=validator_confidence,
        missing_labels=missing_labels,
        added_entities_detected=added_entities_detected,
        suspicious_reasons=suspicious_reasons,
    )




def _normalize_labels_list(labels: object) -> list[str]:
    if not isinstance(labels, list):
        return []
    return sorted(
        {
            " ".join(_TEXT_TOKEN_PATTERN.findall(str(item).lower())).strip()
            for item in labels
            if str(item).strip()
        }
        - {""}
    )


def _supports_responses_client(client) -> bool:
    responses = getattr(client, "responses", None)
    create = getattr(responses, "create", None)
    return callable(create)
