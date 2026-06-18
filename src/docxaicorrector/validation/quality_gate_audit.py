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
        "heldout_money_sustainability_class": "b_extraction_noise_front_matter_title_split",
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
        "evidence": "source_import_bullet_glyphs_are_observability_not_hard_fail; raw_count_kept_for_review",
        "heldout_money_sustainability_class": "c_observability_source_bullets",
        "severity_model": "legacy_hygiene_review_threshold",
    },
    "list_fragment_regression": {
        "verdict": "tolerant",
        "evidence": "body_and_citation_numeric_tails_require_review_context_not_release_blocking_without_profile_threshold",
        "heldout_money_sustainability_class": "b_extraction_noise_or_citation_tail",
        "severity_model": "legacy_hygiene_review_threshold",
    },
    "mixed_script_term": {
        "verdict": "tolerant",
        "evidence": "token_level_homoglyph_detector; strict_policy_uses_manual_review_threshold",
        "severity_model": "legacy_hygiene_review_threshold",
    },
    "toc_body_concat": {
        "verdict": "tolerant",
        "evidence": "topology_projection_overrides_legacy_markdown_when_boundary_evidence_is_available",
        "heldout_money_sustainability_class": "b_extraction_noise_front_matter_toc_compaction",
        "severity_model": "structure_evidence_required_else_review",
    },
    "inline_page_furniture_leakage": {
        "verdict": "unit_aware_after_structural_label_exemption",
        "evidence": "requires_repeated_running_header_context_after_excluding_structural_numbered_labels",
        "heldout_money_sustainability_class": "a_gate_misclass_fixed",
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
    "adjacent_h1_without_body": {
        "verdict": "tolerant",
        "evidence": "front_matter_title_split_noise_is_profile_thresholded_not_intrinsic_release_failure",
        "heldout_money_sustainability_class": "b_extraction_noise_front_matter_title_split",
        "severity_model": "profile_threshold",
    },
}


def quality_gate_audit_classifications_payload() -> dict[str, dict[str, str]]:
    return {
        gate_name: dict(classification)
        for gate_name, classification in QUALITY_GATE_AUDIT_CLASSIFICATIONS.items()
    }
