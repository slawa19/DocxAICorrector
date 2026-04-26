import os
from typing import Any


def resolve_paragraph_boundary_settings(
    *,
    paragraph_boundary_normalization_config: dict[str, object],
    paragraph_boundary_ai_review_config: dict[str, object],
    parse_config_bool_fn: Any,
    parse_choice_str_fn: Any,
    parse_choice_env_fn: Any,
    parse_config_int_fn: Any,
    parse_bool_env_fn: Any,
    parse_int_env_fn: Any,
    clamp_int_fn: Any,
    paragraph_boundary_normalization_mode_values: tuple[str, ...],
    paragraph_boundary_ai_review_mode_values: tuple[str, ...],
) -> dict[str, Any]:
    paragraph_boundary_normalization_enabled = parse_config_bool_fn(
        paragraph_boundary_normalization_config,
        "enabled",
        True,
    )
    paragraph_boundary_normalization_mode = parse_choice_str_fn(
        paragraph_boundary_normalization_config,
        "mode",
        "high_only",
        set(paragraph_boundary_normalization_mode_values),
    )
    paragraph_boundary_normalization_mode = parse_choice_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_NORMALIZATION_MODE",
        default=paragraph_boundary_normalization_mode,
        allowed_values=set(paragraph_boundary_normalization_mode_values),
    )
    paragraph_boundary_normalization_save_debug_artifacts = parse_config_bool_fn(
        paragraph_boundary_normalization_config,
        "save_debug_artifacts",
        True,
    )
    paragraph_boundary_ai_review_enabled = parse_config_bool_fn(
        paragraph_boundary_ai_review_config,
        "enabled",
        False,
    )
    paragraph_boundary_ai_review_mode = parse_choice_str_fn(
        paragraph_boundary_ai_review_config,
        "mode",
        "off",
        set(paragraph_boundary_ai_review_mode_values),
    )
    paragraph_boundary_ai_review_candidate_limit = parse_config_int_fn(
        paragraph_boundary_ai_review_config,
        "candidate_limit",
        200,
    )
    paragraph_boundary_ai_review_timeout_seconds = parse_config_int_fn(
        paragraph_boundary_ai_review_config,
        "timeout_seconds",
        30,
    )
    paragraph_boundary_ai_review_max_tokens_per_candidate = parse_config_int_fn(
        paragraph_boundary_ai_review_config,
        "max_tokens_per_candidate",
        120,
    )

    paragraph_boundary_ai_review_enabled = parse_bool_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_ENABLED",
        paragraph_boundary_ai_review_enabled,
    )
    paragraph_boundary_ai_review_mode = parse_choice_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MODE",
        default=paragraph_boundary_ai_review_mode,
        allowed_values=set(paragraph_boundary_ai_review_mode_values),
    )
    paragraph_boundary_ai_review_candidate_limit = parse_int_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_CANDIDATE_LIMIT",
        paragraph_boundary_ai_review_candidate_limit,
    )
    paragraph_boundary_ai_review_timeout_seconds = parse_int_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_TIMEOUT_SECONDS",
        paragraph_boundary_ai_review_timeout_seconds,
    )
    paragraph_boundary_ai_review_max_tokens_per_candidate = parse_int_env_fn(
        "DOCX_AI_PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_TOKENS_PER_CANDIDATE",
        paragraph_boundary_ai_review_max_tokens_per_candidate,
    )

    return {
        "paragraph_boundary_normalization_enabled": paragraph_boundary_normalization_enabled,
        "paragraph_boundary_normalization_mode": paragraph_boundary_normalization_mode,
        "paragraph_boundary_normalization_save_debug_artifacts": paragraph_boundary_normalization_save_debug_artifacts,
        "paragraph_boundary_ai_review_enabled": paragraph_boundary_ai_review_enabled,
        "paragraph_boundary_ai_review_mode": paragraph_boundary_ai_review_mode,
        "paragraph_boundary_ai_review_candidate_limit": clamp_int_fn(
            paragraph_boundary_ai_review_candidate_limit,
            minimum=1,
            maximum=500,
        ),
        "paragraph_boundary_ai_review_timeout_seconds": clamp_int_fn(
            paragraph_boundary_ai_review_timeout_seconds,
            minimum=1,
            maximum=120,
        ),
        "paragraph_boundary_ai_review_max_tokens_per_candidate": clamp_int_fn(
            paragraph_boundary_ai_review_max_tokens_per_candidate,
            minimum=32,
            maximum=512,
        ),
    }


def resolve_relation_normalization_settings(
    *,
    relation_normalization_config: dict[str, object],
    parse_config_bool_fn: Any,
    parse_choice_str_fn: Any,
    parse_string_list_fn: Any,
    config_path: Any,
    relation_normalization_profile_values: tuple[str, ...],
    relation_normalization_kind_values: tuple[str, ...],
) -> dict[str, Any]:
    relation_normalization_enabled = parse_config_bool_fn(
        relation_normalization_config,
        "enabled",
        True,
    )
    relation_normalization_profile = parse_choice_str_fn(
        relation_normalization_config,
        "profile",
        "phase2_default",
        set(relation_normalization_profile_values),
    )
    relation_normalization_enabled_relation_kinds = parse_string_list_fn(
        relation_normalization_config.get("enabled_relation_kinds"),
        source_name=f"{config_path}: relation_normalization.enabled_relation_kinds",
        default=tuple(relation_normalization_kind_values),
    )
    invalid_relation_kinds = sorted(
        set(relation_normalization_enabled_relation_kinds) - set(relation_normalization_kind_values)
    )
    if invalid_relation_kinds:
        raise RuntimeError(
            "Некорректные relation normalization kinds в "
            f"{config_path}: {', '.join(invalid_relation_kinds)}"
        )
    relation_normalization_save_debug_artifacts = parse_config_bool_fn(
        relation_normalization_config,
        "save_debug_artifacts",
        True,
    )
    return {
        "relation_normalization_enabled": relation_normalization_enabled,
        "relation_normalization_profile": relation_normalization_profile,
        "relation_normalization_enabled_relation_kinds": relation_normalization_enabled_relation_kinds,
        "relation_normalization_save_debug_artifacts": relation_normalization_save_debug_artifacts,
    }


def resolve_layout_artifact_cleanup_settings(
    *,
    layout_artifact_cleanup_config: dict[str, object],
    parse_config_bool_fn: Any,
    parse_config_int_fn: Any,
    parse_bool_env_fn: Any,
    parse_int_env_fn: Any,
    clamp_int_fn: Any,
) -> dict[str, Any]:
    enabled = parse_config_bool_fn(layout_artifact_cleanup_config, "enabled", True)
    min_repeat_count = parse_config_int_fn(layout_artifact_cleanup_config, "min_repeat_count", 3)
    max_repeated_text_chars = parse_config_int_fn(layout_artifact_cleanup_config, "max_repeated_text_chars", 80)
    save_debug_artifacts = parse_config_bool_fn(layout_artifact_cleanup_config, "save_debug_artifacts", True)

    enabled = parse_bool_env_fn("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_ENABLED", enabled)
    min_repeat_count = parse_int_env_fn("DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_MIN_REPEAT_COUNT", min_repeat_count)
    max_repeated_text_chars = parse_int_env_fn(
        "DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_MAX_REPEATED_TEXT_CHARS",
        max_repeated_text_chars,
    )
    save_debug_artifacts = parse_bool_env_fn(
        "DOCX_AI_LAYOUT_ARTIFACT_CLEANUP_SAVE_DEBUG_ARTIFACTS",
        save_debug_artifacts,
    )

    return {
        "layout_artifact_cleanup_enabled": enabled,
        "layout_artifact_cleanup_min_repeat_count": clamp_int_fn(min_repeat_count, minimum=2, maximum=100),
        "layout_artifact_cleanup_max_repeated_text_chars": clamp_int_fn(max_repeated_text_chars, minimum=1, maximum=500),
        "layout_artifact_cleanup_save_debug_artifacts": save_debug_artifacts,
    }


def resolve_structure_recognition_settings(
    *,
    structure_recognition_config: dict[str, object],
    parse_config_bool_fn: Any,
    parse_choice_str_fn: Any,
    parse_config_int_fn: Any,
    parse_int_env_fn: Any,
    parse_bool_env_fn: Any,
    parse_choice_env_fn: Any,
    clamp_int_fn: Any,
    structure_recognition_mode_values: tuple[str, ...],
    structure_recognition_min_confidence_values: tuple[str, ...],
) -> dict[str, Any]:
    structure_recognition_has_mode = "mode" in structure_recognition_config
    legacy_structure_recognition_enabled = parse_config_bool_fn(
        structure_recognition_config,
        "enabled",
        False,
    )
    if structure_recognition_has_mode:
        structure_recognition_mode = parse_choice_str_fn(
            structure_recognition_config,
            "mode",
            "off",
            set(structure_recognition_mode_values),
        )
    else:
        structure_recognition_mode = "always" if legacy_structure_recognition_enabled else "off"
    structure_recognition_max_window_paragraphs = parse_config_int_fn(
        structure_recognition_config,
        "max_window_paragraphs",
        1800,
    )
    structure_recognition_overlap_paragraphs = parse_config_int_fn(
        structure_recognition_config,
        "overlap_paragraphs",
        50,
    )
    structure_recognition_timeout_seconds = parse_config_int_fn(
        structure_recognition_config,
        "timeout_seconds",
        60,
    )
    structure_recognition_min_confidence = parse_choice_str_fn(
        structure_recognition_config,
        "min_confidence",
        "medium",
        set(structure_recognition_min_confidence_values),
    )
    structure_recognition_cache_enabled = parse_config_bool_fn(
        structure_recognition_config,
        "cache_enabled",
        True,
    )
    structure_recognition_save_debug_artifacts = parse_config_bool_fn(
        structure_recognition_config,
        "save_debug_artifacts",
        True,
    )

    raw_structure_recognition_mode_env = os.getenv("DOCX_AI_STRUCTURE_RECOGNITION_MODE", "").strip().lower()
    if raw_structure_recognition_mode_env:
        if raw_structure_recognition_mode_env not in set(structure_recognition_mode_values):
            raise RuntimeError(
                f"Некорректное значение в DOCX_AI_STRUCTURE_RECOGNITION_MODE: {raw_structure_recognition_mode_env}"
            )
        structure_recognition_mode = raw_structure_recognition_mode_env
    elif not structure_recognition_has_mode:
        legacy_structure_recognition_enabled = parse_bool_env_fn(
            "DOCX_AI_STRUCTURE_RECOGNITION_ENABLED",
            legacy_structure_recognition_enabled,
        )
        structure_recognition_mode = "always" if legacy_structure_recognition_enabled else "off"

    structure_recognition_max_window_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_MAX_WINDOW_PARAGRAPHS",
        structure_recognition_max_window_paragraphs,
    )
    structure_recognition_overlap_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_OVERLAP_PARAGRAPHS",
        structure_recognition_overlap_paragraphs,
    )
    structure_recognition_timeout_seconds = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_TIMEOUT_SECONDS",
        structure_recognition_timeout_seconds,
    )
    structure_recognition_min_confidence = parse_choice_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_MIN_CONFIDENCE",
        default=structure_recognition_min_confidence,
        allowed_values=set(structure_recognition_min_confidence_values),
    )
    structure_recognition_cache_enabled = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_CACHE_ENABLED",
        structure_recognition_cache_enabled,
    )
    structure_recognition_save_debug_artifacts = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOGNITION_SAVE_DEBUG_ARTIFACTS",
        structure_recognition_save_debug_artifacts,
    )

    return {
        "structure_recognition_mode": structure_recognition_mode,
        "structure_recognition_enabled": structure_recognition_mode == "always",
        "structure_recognition_max_window_paragraphs": clamp_int_fn(
            structure_recognition_max_window_paragraphs,
            minimum=100,
            maximum=4000,
        ),
        "structure_recognition_overlap_paragraphs": clamp_int_fn(
            structure_recognition_overlap_paragraphs,
            minimum=0,
            maximum=200,
        ),
        "structure_recognition_timeout_seconds": clamp_int_fn(
            structure_recognition_timeout_seconds,
            minimum=1,
            maximum=300,
        ),
        "structure_recognition_min_confidence": structure_recognition_min_confidence,
        "structure_recognition_cache_enabled": structure_recognition_cache_enabled,
        "structure_recognition_save_debug_artifacts": structure_recognition_save_debug_artifacts,
    }


def resolve_structure_validation_settings(
    *,
    structure_validation_config: dict[str, object],
    parse_config_bool_fn: Any,
    parse_config_int_fn: Any,
    parse_config_float_fn: Any,
    parse_bool_env_fn: Any,
    parse_int_env_fn: Any,
    parse_float_env_fn: Any,
    clamp_int_fn: Any,
    clamp_float_fn: Any,
) -> dict[str, Any]:
    structure_validation_enabled = parse_config_bool_fn(
        structure_validation_config,
        "enabled",
        True,
    )
    structure_validation_min_paragraphs_for_auto_gate = parse_config_int_fn(
        structure_validation_config,
        "min_paragraphs_for_auto_gate",
        40,
    )
    structure_validation_min_explicit_heading_density = parse_config_float_fn(
        structure_validation_config,
        "min_explicit_heading_density",
        0.003,
    )
    structure_validation_max_suspicious_short_body_ratio_without_escalation = parse_config_float_fn(
        structure_validation_config,
        "max_suspicious_short_body_ratio_without_escalation",
        0.05,
    )
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation = parse_config_float_fn(
        structure_validation_config,
        "max_all_caps_or_centered_body_ratio_without_escalation",
        0.03,
    )
    structure_validation_toc_like_sequence_min_length = parse_config_int_fn(
        structure_validation_config,
        "toc_like_sequence_min_length",
        4,
    )
    structure_validation_forbid_heading_only_collapse = parse_config_bool_fn(
        structure_validation_config,
        "forbid_heading_only_collapse",
        True,
    )
    structure_validation_save_debug_artifacts = parse_config_bool_fn(
        structure_validation_config,
        "save_debug_artifacts",
        True,
    )

    structure_validation_enabled = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_ENABLED",
        structure_validation_enabled,
    )
    structure_validation_min_paragraphs_for_auto_gate = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_MIN_PARAGRAPHS_FOR_AUTO_GATE",
        structure_validation_min_paragraphs_for_auto_gate,
    )
    structure_validation_min_explicit_heading_density = parse_float_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_MIN_EXPLICIT_HEADING_DENSITY",
        structure_validation_min_explicit_heading_density,
    )
    structure_validation_max_suspicious_short_body_ratio_without_escalation = parse_float_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_MAX_SUSPICIOUS_SHORT_BODY_RATIO_WITHOUT_ESCALATION",
        structure_validation_max_suspicious_short_body_ratio_without_escalation,
    )
    structure_validation_max_all_caps_or_centered_body_ratio_without_escalation = parse_float_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_MAX_ALL_CAPS_OR_CENTERED_BODY_RATIO_WITHOUT_ESCALATION",
        structure_validation_max_all_caps_or_centered_body_ratio_without_escalation,
    )
    structure_validation_toc_like_sequence_min_length = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_TOC_LIKE_SEQUENCE_MIN_LENGTH",
        structure_validation_toc_like_sequence_min_length,
    )
    structure_validation_forbid_heading_only_collapse = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_FORBID_HEADING_ONLY_COLLAPSE",
        structure_validation_forbid_heading_only_collapse,
    )
    structure_validation_save_debug_artifacts = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_SAVE_DEBUG_ARTIFACTS",
        structure_validation_save_debug_artifacts,
    )

    return {
        "structure_validation_enabled": structure_validation_enabled,
        "structure_validation_min_paragraphs_for_auto_gate": clamp_int_fn(
            structure_validation_min_paragraphs_for_auto_gate,
            minimum=1,
            maximum=10000,
        ),
        "structure_validation_min_explicit_heading_density": clamp_float_fn(
            structure_validation_min_explicit_heading_density,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_max_suspicious_short_body_ratio_without_escalation": clamp_float_fn(
            structure_validation_max_suspicious_short_body_ratio_without_escalation,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": clamp_float_fn(
            structure_validation_max_all_caps_or_centered_body_ratio_without_escalation,
            minimum=0.0,
            maximum=1.0,
        ),
        "structure_validation_toc_like_sequence_min_length": clamp_int_fn(
            structure_validation_toc_like_sequence_min_length,
            minimum=1,
            maximum=100,
        ),
        "structure_validation_forbid_heading_only_collapse": structure_validation_forbid_heading_only_collapse,
        "structure_validation_save_debug_artifacts": structure_validation_save_debug_artifacts,
    }
