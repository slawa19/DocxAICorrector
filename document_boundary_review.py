import hashlib
import json
import re
from pathlib import Path

from image_shared import (
    call_responses_create_with_retry,
    extract_model_response_error_code,
    extract_response_text,
    is_retryable_error,
    parse_json_object,
)
from models import ParagraphBoundaryNormalizationReport, ParagraphUnit, RawBlock, RawParagraph, RelationNormalizationReport
from runtime_artifact_retention import prune_artifact_dir


def resolve_paragraph_boundary_ai_review_settings(
    *,
    allowed_modes: tuple[str, ...] | list[str] | set[str],
) -> tuple[bool, str, int, int, int, str]:
    from config import get_text_model_default, load_app_config

    app_config = load_app_config()
    enabled = bool(app_config.get("paragraph_boundary_ai_review_enabled", False))
    mode = str(app_config.get("paragraph_boundary_ai_review_mode", "off") or "off")
    if mode not in allowed_modes:
        mode = "off"
    if not enabled:
        mode = "off"
    effective_enabled = enabled and mode != "off"
    model = get_text_model_default(app_config) if effective_enabled else ""
    return (
        effective_enabled,
        mode,
        coerce_int_config_value(app_config.get("paragraph_boundary_ai_review_candidate_limit"), 200),
        coerce_int_config_value(app_config.get("paragraph_boundary_ai_review_timeout_seconds"), 30),
        coerce_int_config_value(app_config.get("paragraph_boundary_ai_review_max_tokens_per_candidate"), 120),
        model,
    )


def coerce_int_config_value(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def build_ai_review_candidates(
    *,
    raw_blocks: list[RawBlock],
    paragraphs: list[ParagraphUnit],
    boundary_report: ParagraphBoundaryNormalizationReport,
    relation_report: RelationNormalizationReport,
    candidate_limit: int,
) -> list[dict[str, object]]:
    raw_paragraphs_by_index = {
        block.raw_index: block
        for block in raw_blocks
        if isinstance(block, RawParagraph)
    }
    paragraph_text_by_id = {
        paragraph.paragraph_id: paragraph.text
        for paragraph in paragraphs
        if paragraph.paragraph_id
    }

    candidates: list[dict[str, object]] = []
    for decision in boundary_report.decisions:
        if decision.confidence != "medium":
            continue
        left = raw_paragraphs_by_index.get(decision.left_raw_index)
        right = raw_paragraphs_by_index.get(decision.right_raw_index)
        candidates.append(
            {
                "candidate_kind": "boundary_medium",
                "candidate_id": f"{decision.left_raw_index}:{decision.right_raw_index}",
                "deterministic_decision": decision.decision,
                "confidence": decision.confidence,
                "left_raw_index": decision.left_raw_index,
                "right_raw_index": decision.right_raw_index,
                "left_text": None if left is None else left.text,
                "right_text": None if right is None else right.text,
                "reasons": list(decision.reasons),
            }
        )

    for decision in relation_report.decisions:
        if decision.decision == "accept":
            continue
        candidates.append(
            {
                "candidate_kind": "relation_rejected",
                "candidate_id": f"{decision.relation_kind}:{'|'.join(decision.member_paragraph_ids)}",
                "deterministic_decision": decision.decision,
                "relation_kind": decision.relation_kind,
                "member_paragraph_ids": list(decision.member_paragraph_ids),
                "member_texts": [paragraph_text_by_id.get(paragraph_id, "") for paragraph_id in decision.member_paragraph_ids],
                "anchor_asset_id": decision.anchor_asset_id,
                "reasons": list(decision.reasons),
            }
        )

    return candidates[: max(0, candidate_limit)]


def build_ai_review_request_payload(
    *,
    model: str,
    candidates: list[dict[str, object]],
    timeout_seconds: int,
    max_tokens_per_candidate: int,
) -> dict[str, object]:
    system_prompt = (
        "You review ambiguous DOCX paragraph-boundary and grouping candidates. "
        "Return only JSON with a top-level recommendations array. "
        "For boundary candidates use recommendation merge or keep. "
        "For relation candidates use recommendation accept or reject."
    )
    user_prompt = json.dumps(
        {
            "instructions": {
                "review_scope": "ambiguous normalization candidates",
                "required_output_shape": {
                    "recommendations": [
                        {
                            "candidate_id": "string",
                            "recommendation": "merge|keep|accept|reject",
                            "reasons": ["string"],
                        }
                    ]
                },
            },
            "candidates": candidates,
        },
        ensure_ascii=False,
    )
    return {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "max_output_tokens": max(256, min(len(candidates) * max_tokens_per_candidate, 8192)),
        "timeout": timeout_seconds,
    }


def request_ai_review_recommendations(
    *,
    model: str,
    candidates: list[dict[str, object]],
    timeout_seconds: int,
    max_tokens_per_candidate: int,
) -> dict[str, dict[str, object]]:
    from config import get_client

    response = call_responses_create_with_retry(
        get_client(),
        build_ai_review_request_payload(
            model=model,
            candidates=candidates,
            timeout_seconds=timeout_seconds,
            max_tokens_per_candidate=max_tokens_per_candidate,
        ),
        max_retries=2,
        retryable_error_predicate=is_retryable_error,
    )
    raw_text = extract_response_text(
        response,
        empty_message="AI review did not return text.",
        incomplete_message="AI review returned incomplete response.",
        unsupported_message="AI review returned unsupported response shape.",
    )
    payload = parse_json_object(
        raw_text,
        empty_message="AI review returned empty output.",
        no_json_message="AI review did not return JSON.",
    )
    recommendations = payload.get("recommendations", [])
    if not isinstance(recommendations, list):
        raise RuntimeError("AI review returned invalid recommendations payload.")

    result: dict[str, dict[str, object]] = {}
    for entry in recommendations:
        if not isinstance(entry, dict):
            continue
        candidate_id = entry.get("candidate_id")
        recommendation = entry.get("recommendation")
        reasons = entry.get("reasons", [])
        if not isinstance(candidate_id, str) or not candidate_id.strip():
            continue
        if not isinstance(recommendation, str) or not recommendation.strip():
            continue
        if not isinstance(reasons, list):
            reasons = []
        result[candidate_id] = {
            "recommendation": recommendation.strip().lower(),
            "reasons": [str(reason) for reason in reasons if str(reason).strip()],
        }
    return result


def build_ai_review_decision_records(
    *,
    candidates: list[dict[str, object]],
    recommendations: dict[str, dict[str, object]],
    mode: str,
    error_code: str | None,
) -> list[dict[str, object]]:
    decisions: list[dict[str, object]] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        deterministic_decision = str(candidate.get("deterministic_decision") or "keep")
        recommendation_payload = recommendations.get(candidate_id, {})
        ai_recommendation = recommendation_payload.get("recommendation")
        reasons = [f"{mode}_mode"]
        if error_code is not None:
            reasons.append(f"ai_review_unavailable:{error_code}")
        elif ai_recommendation is None:
            reasons.append("ai_review_no_recommendation")
        elif ai_recommendation != deterministic_decision:
            reasons.append("deterministic_decision_retained")
        else:
            reasons.append("ai_agreed_with_deterministic")

        decisions.append(
            {
                "candidate_kind": candidate.get("candidate_kind"),
                "candidate_id": candidate_id,
                "deterministic_decision": deterministic_decision,
                "ai_recommendation": ai_recommendation,
                "final_decision": deterministic_decision,
                "reasons": reasons,
            }
        )
    return decisions


def write_paragraph_boundary_ai_review_artifact(
    *,
    source_name: str,
    source_bytes: bytes,
    mode: str,
    decisions: list[dict[str, object]],
    target_dir: Path,
    max_age_seconds: int,
    max_count: int,
    error_code: str | None = None,
) -> str | None:
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        source_hash = hashlib.sha1(source_bytes).hexdigest()[:8]
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name or "document.docx").strip("_") or "document.docx"
        artifact_path = target_dir / f"{safe_name}_{source_hash}.json"
        payload: dict[str, object] = {
            "version": 1,
            "source_file": source_name,
            "source_hash": source_hash,
            "mode": mode,
            "reviewed_candidate_count": len(decisions),
            "accepted_candidate_count": sum(
                1 for decision in decisions if decision.get("final_decision") in {"merge", "accept", "group"}
            ),
            "decisions": decisions,
        }
        if error_code is not None:
            payload["error_code"] = error_code
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_artifact_dir(
            target_dir=target_dir,
            max_age_seconds=max_age_seconds,
            max_count=max_count,
        )
        return str(artifact_path)
    except Exception:
        return None


def run_paragraph_boundary_ai_review(
    *,
    source_name: str,
    source_bytes: bytes,
    mode: str,
    model: str,
    raw_blocks: list[RawBlock],
    paragraphs: list[ParagraphUnit],
    boundary_report: ParagraphBoundaryNormalizationReport,
    relation_report: RelationNormalizationReport,
    candidate_limit: int,
    timeout_seconds: int,
    max_tokens_per_candidate: int,
    target_dir: Path,
    max_age_seconds: int,
    max_count: int,
    request_ai_review_recommendations_impl=request_ai_review_recommendations,
) -> str | None:
    candidates = build_ai_review_candidates(
        raw_blocks=raw_blocks,
        paragraphs=paragraphs,
        boundary_report=boundary_report,
        relation_report=relation_report,
        candidate_limit=candidate_limit,
    )
    if not candidates:
        return None

    recommendations: dict[str, dict[str, object]] = {}
    error_code: str | None = None
    try:
        recommendations = request_ai_review_recommendations_impl(
            model=model,
            candidates=candidates,
            timeout_seconds=timeout_seconds,
            max_tokens_per_candidate=max_tokens_per_candidate,
        )
    except Exception as exc:
        error_code = extract_model_response_error_code(exc)
        if error_code is None and "timeout" in str(exc).lower():
            error_code = "timeout"
        if error_code is None:
            error_code = "review_failed"

    decisions = build_ai_review_decision_records(
        candidates=candidates,
        recommendations=recommendations,
        mode=mode,
        error_code=error_code,
    )
    return write_paragraph_boundary_ai_review_artifact(
        source_name=source_name,
        source_bytes=source_bytes,
        mode=mode,
        decisions=decisions,
        target_dir=target_dir,
        max_age_seconds=max_age_seconds,
        max_count=max_count,
        error_code=error_code,
    )
