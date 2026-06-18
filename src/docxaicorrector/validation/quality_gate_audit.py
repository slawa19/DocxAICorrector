from __future__ import annotations

from collections.abc import Mapping


QUALITY_GATE_AUDIT_CLASSIFICATIONS: Mapping[str, Mapping[str, str]] = {
    "bullet_heading": {
        "verdict": "unit_aware",
        "evidence": "markdown_heading_contains_only_list_marker",
        "severity_model": "legacy_hygiene_fix_review_threshold",
    },
    "false_fragment_heading": {
        "verdict": "unit_aware",
        "evidence": "entry_assembly_when_available_else_markdown_continuation_context",
        "severity_model": "legacy_hygiene_fix_review_threshold",
    },
    "scripture_reference_heading": {
        "verdict": "tolerant",
        "evidence": "source_backed_entry_headings_are_exempt; markdown_only_hits_require_manual_review_not_hard_fail_within_threshold",
        "severity_model": "legacy_hygiene_fix_review_threshold",
    },
    "suspicious_heading_repetition": {
        "verdict": "tolerant",
        "evidence": "repetition_requires_adjacent_heading_without_intervening_body",
        "severity_model": "legacy_hygiene_fix_review_threshold",
    },
    "residual_bullet_glyph": {
        "verdict": "tolerant",
        "evidence": "display_hygiene_normalization_applies_before_gate; raw_legacy_count_kept_for_observability",
        "severity_model": "legacy_hygiene_review_threshold",
    },
    "mixed_script_term": {
        "verdict": "tolerant",
        "evidence": "token_level_homoglyph_detector; strict_policy_uses_manual_review_threshold",
        "severity_model": "legacy_hygiene_review_threshold",
    },
    "toc_body_concat": {
        "verdict": "unit_aware",
        "evidence": "topology_projection_overrides_legacy_markdown_when_boundary_evidence_is_available",
        "severity_model": "structure_evidence_required_else_review",
    },
    "inline_page_furniture_leakage": {
        "verdict": "unit_aware",
        "evidence": "requires repeated_running_header_context_or_exact_page_furniture_detector",
        "severity_model": "profile_threshold",
    },
    "pdf_blank_page_marker_leakage": {
        "verdict": "unit_aware",
        "evidence": "standalone_page_furniture_detector_excluding_headings_blockquotes_and_code",
        "severity_model": "profile_threshold",
    },
    "heading_body_concat_detected": {
        "verdict": "tolerant",
        "evidence": "long_heading_heuristic_exempts accepted_title_shapes_and_is_profile_thresholded",
        "severity_model": "profile_threshold",
    },
}


def quality_gate_audit_classifications_payload() -> dict[str, dict[str, str]]:
    return {
        gate_name: dict(classification)
        for gate_name, classification in QUALITY_GATE_AUDIT_CLASSIFICATIONS.items()
    }
