from dataclasses import replace

from models import ImageAnalysisResult, ImageMode, ImageValidationResult, SEMANTIC_IMAGE_MODE_VALUES


_ADVISORY_SAFE_FALLBACK_PREFIXES = (
    "dense_text_bypass:",
    "dense_non_latin_text_bypass:",
)

_HARD_VALIDATION_REASONS = {
    "candidate_image_unreadable",
    "original_image_unreadable",
}


def should_attempt_semantic_redraw(analysis: ImageAnalysisResult, image_mode: str) -> bool:
    if image_mode not in {*SEMANTIC_IMAGE_MODE_VALUES, ImageMode.COMPARE_ALL.value}:
        return False
    if analysis.semantic_redraw_allowed:
        return True
    return is_advisory_safe_fallback(analysis)


def build_generation_analysis(analysis: ImageAnalysisResult) -> ImageAnalysisResult:
    if analysis.semantic_redraw_allowed or not is_advisory_safe_fallback(analysis):
        return analysis
    return replace(analysis, semantic_redraw_allowed=True)


def is_advisory_safe_fallback(analysis: ImageAnalysisResult) -> bool:
    fallback_reason = str(analysis.fallback_reason or "")
    return any(fallback_reason.startswith(prefix) for prefix in _ADVISORY_SAFE_FALLBACK_PREFIXES)


def is_hard_validation_failure(validation_result: ImageValidationResult) -> bool:
    suspicious_reasons = list(validation_result.suspicious_reasons)
    return any(
        reason in _HARD_VALIDATION_REASONS
        or str(reason).startswith("validator_exception:")
        for reason in suspicious_reasons
    )


def should_deliver_redrawn_candidate(validation_result: ImageValidationResult, validation_policy: str) -> bool:
    return validation_policy == "advisory" and not is_hard_validation_failure(validation_result)


def resolve_validation_delivery_outcome(
    validation_result: ImageValidationResult,
    *,
    validation_policy: str,
    has_safe_fallback: bool,
) -> dict[str, object]:
    if validation_result.decision == "accept":
        return {
            "validation_status": "passed",
            "final_decision": "accept",
            "final_variant": "redrawn",
            "final_reason": "Validator подтвердил semantic redraw.",
            "soft_accepted": False,
        }

    if should_deliver_redrawn_candidate(validation_result, validation_policy):
        return {
            "validation_status": "soft-pass",
            "final_decision": "accept_soft",
            "final_variant": "redrawn",
            "final_reason": (
                "Semantic redraw доставлен по advisory-policy; validator отметил расхождения: "
                f"{'; '.join(validation_result.suspicious_reasons) or 'нет'}"
            ),
            "soft_accepted": True,
        }

    fallback_reason = "; ".join(validation_result.suspicious_reasons)
    if validation_result.decision == "fallback_safe" and has_safe_fallback:
        return {
            "validation_status": "failed",
            "final_decision": "fallback_safe",
            "final_variant": "safe",
            "final_reason": fallback_reason or "Validator запросил safe fallback.",
            "soft_accepted": False,
        }

    return {
        "validation_status": "failed",
        "final_decision": "fallback_original",
        "final_variant": "original",
        "final_reason": fallback_reason or "Validator запросил fallback на оригинал.",
        "soft_accepted": False,
    }