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


def resolve_structure_recovery_settings(
    *,
    config_data: dict[str, object],
    parse_optional_config_section_fn: Any,
    parse_config_bool_fn: Any,
    parse_choice_str_fn: Any,
    parse_config_int_fn: Any,
    parse_optional_config_str_fn: Any,
    parse_bool_env_fn: Any,
    parse_int_env_fn: Any,
    parse_choice_env_fn: Any,
    parse_optional_str_env_fn: Any,
    clamp_int_fn: Any,
    structure_recovery_mode_values: tuple[str, ...],
    structure_recognition_min_confidence_values: tuple[str, ...],
) -> dict[str, Any]:
    structure_recovery_config = parse_optional_config_section_fn(config_data, "structure_recovery")
    document_map_config = parse_optional_config_section_fn(
        structure_recovery_config,
        "document_map",
        parent_name="structure_recovery",
    )
    anchored_classification_config = parse_optional_config_section_fn(
        structure_recovery_config,
        "anchored_classification",
        parent_name="structure_recovery",
    )
    reconciliation_config = parse_optional_config_section_fn(
        structure_recovery_config,
        "reconciliation",
        parent_name="structure_recovery",
    )

    structure_recovery_enabled = parse_config_bool_fn(structure_recovery_config, "enabled", False)
    structure_recovery_mode = parse_choice_str_fn(
        structure_recovery_config,
        "mode",
        "ai_first",
        set(structure_recovery_mode_values),
    )

    document_map_enabled = parse_config_bool_fn(document_map_config, "enabled", False)
    raw_document_map_model = document_map_config.get("model")
    if raw_document_map_model is None:
        document_map_model = ""
    elif not isinstance(raw_document_map_model, str):
        raise RuntimeError("Некорректное поле model в structure_recovery.document_map: ожидается строка")
    else:
        document_map_model = raw_document_map_model.strip()
    document_map_timeout_seconds = parse_config_int_fn(document_map_config, "timeout_seconds", 120)
    document_map_max_input_paragraphs = parse_config_int_fn(document_map_config, "max_input_paragraphs", 6000)
    document_map_max_input_tokens = parse_config_int_fn(document_map_config, "max_input_tokens", 180000)
    document_map_preview_chars = parse_config_int_fn(document_map_config, "preview_chars", 120)
    document_map_cache_enabled = parse_config_bool_fn(document_map_config, "cache_enabled", True)
    document_map_save_debug_artifacts = parse_config_bool_fn(document_map_config, "save_debug_artifacts", True)

    anchored_max_window_paragraphs = parse_config_int_fn(
        anchored_classification_config,
        "max_window_paragraphs",
        3000,
    )
    anchored_overlap_paragraphs = parse_config_int_fn(anchored_classification_config, "overlap_paragraphs", 0)
    anchored_preview_chars = parse_config_int_fn(anchored_classification_config, "preview_chars", 1500)
    anchored_target_input_tokens = parse_config_int_fn(
        anchored_classification_config,
        "target_input_tokens",
        180000,
    )
    anchored_min_confidence = parse_choice_str_fn(
        anchored_classification_config,
        "min_confidence",
        "medium",
        set(structure_recognition_min_confidence_values),
    )

    reconciliation_targeted_enabled = parse_config_bool_fn(reconciliation_config, "targeted_enabled", False)
    reconciliation_targeted_threshold = parse_config_int_fn(reconciliation_config, "targeted_threshold", 3)
    reconciliation_targeted_max_paragraphs = parse_config_int_fn(reconciliation_config, "targeted_max_paragraphs", 60)
    reconciliation_targeted_timeout_seconds = parse_config_int_fn(
        reconciliation_config,
        "targeted_timeout_seconds",
        60,
    )

    structure_recovery_enabled = parse_bool_env_fn("DOCX_AI_STRUCTURE_RECOVERY_ENABLED", structure_recovery_enabled)
    structure_recovery_mode = parse_choice_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_MODE",
        default=structure_recovery_mode,
        allowed_values=set(structure_recovery_mode_values),
    )
    document_map_enabled = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_ENABLED",
        document_map_enabled,
    )
    document_map_model = parse_optional_str_env_fn("DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_MODEL") or document_map_model
    document_map_timeout_seconds = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_TIMEOUT_SECONDS",
        document_map_timeout_seconds,
    )
    document_map_max_input_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_MAX_INPUT_PARAGRAPHS",
        document_map_max_input_paragraphs,
    )
    document_map_max_input_tokens = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_MAX_INPUT_TOKENS",
        document_map_max_input_tokens,
    )
    document_map_preview_chars = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_PREVIEW_CHARS",
        document_map_preview_chars,
    )
    document_map_cache_enabled = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_CACHE_ENABLED",
        document_map_cache_enabled,
    )
    document_map_save_debug_artifacts = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_DOCUMENT_MAP_SAVE_DEBUG_ARTIFACTS",
        document_map_save_debug_artifacts,
    )

    anchored_max_window_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MAX_WINDOW_PARAGRAPHS",
        anchored_max_window_paragraphs,
    )
    anchored_overlap_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_OVERLAP_PARAGRAPHS",
        anchored_overlap_paragraphs,
    )
    anchored_preview_chars = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_PREVIEW_CHARS",
        anchored_preview_chars,
    )
    anchored_target_input_tokens = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_TARGET_INPUT_TOKENS",
        anchored_target_input_tokens,
    )
    anchored_min_confidence = parse_choice_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_ANCHORED_CLASSIFICATION_MIN_CONFIDENCE",
        default=anchored_min_confidence,
        allowed_values=set(structure_recognition_min_confidence_values),
    )

    reconciliation_targeted_enabled = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_RECONCILIATION_TARGETED_ENABLED",
        reconciliation_targeted_enabled,
    )
    reconciliation_targeted_threshold = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_RECONCILIATION_TARGETED_THRESHOLD",
        reconciliation_targeted_threshold,
    )
    reconciliation_targeted_max_paragraphs = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_RECONCILIATION_TARGETED_MAX_PARAGRAPHS",
        reconciliation_targeted_max_paragraphs,
    )
    reconciliation_targeted_timeout_seconds = parse_int_env_fn(
        "DOCX_AI_STRUCTURE_RECOVERY_RECONCILIATION_TARGETED_TIMEOUT_SECONDS",
        reconciliation_targeted_timeout_seconds,
    )

    return {
        "structure_recovery_enabled": structure_recovery_enabled,
        "structure_recovery_mode": structure_recovery_mode,
        "structure_recovery_coordinate_schema_version": 1,
        "structure_recovery_document_map_enabled": document_map_enabled,
        "structure_recovery_document_map_model": document_map_model,
        "structure_recovery_document_map_timeout_seconds": clamp_int_fn(document_map_timeout_seconds, minimum=1, maximum=600),
        "structure_recovery_document_map_max_input_paragraphs": clamp_int_fn(
            document_map_max_input_paragraphs,
            minimum=100,
            maximum=20000,
        ),
        "structure_recovery_document_map_max_input_tokens": clamp_int_fn(
            document_map_max_input_tokens,
            minimum=1000,
            maximum=400000,
        ),
        "structure_recovery_document_map_preview_chars": clamp_int_fn(document_map_preview_chars, minimum=40, maximum=400),
        "structure_recovery_document_map_cache_enabled": document_map_cache_enabled,
        "structure_recovery_document_map_save_debug_artifacts": document_map_save_debug_artifacts,
        "structure_recovery_anchored_classification_max_window_paragraphs": clamp_int_fn(
            anchored_max_window_paragraphs,
            minimum=100,
            maximum=6000,
        ),
        "structure_recovery_anchored_classification_overlap_paragraphs": clamp_int_fn(
            anchored_overlap_paragraphs,
            minimum=0,
            maximum=500,
        ),
        "structure_recovery_anchored_classification_preview_chars": clamp_int_fn(
            anchored_preview_chars,
            minimum=200,
            maximum=4000,
        ),
        "structure_recovery_anchored_classification_target_input_tokens": clamp_int_fn(
            anchored_target_input_tokens,
            minimum=1000,
            maximum=400000,
        ),
        "structure_recovery_anchored_classification_min_confidence": anchored_min_confidence,
        "structure_recovery_reconciliation_targeted_enabled": reconciliation_targeted_enabled,
        "structure_recovery_reconciliation_targeted_threshold": clamp_int_fn(
            reconciliation_targeted_threshold,
            minimum=1,
            maximum=20,
        ),
        "structure_recovery_reconciliation_targeted_max_paragraphs": clamp_int_fn(
            reconciliation_targeted_max_paragraphs,
            minimum=10,
            maximum=200,
        ),
        "structure_recovery_reconciliation_targeted_timeout_seconds": clamp_int_fn(
            reconciliation_targeted_timeout_seconds,
            minimum=1,
            maximum=300,
        ),
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
    structure_validation_block_on_high_risk_noop = parse_config_bool_fn(
        structure_validation_config,
        "block_on_high_risk_noop",
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
    structure_validation_block_on_high_risk_noop = parse_bool_env_fn(
        "DOCX_AI_STRUCTURE_VALIDATION_BLOCK_ON_HIGH_RISK_NOOP",
        structure_validation_block_on_high_risk_noop,
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
        "structure_validation_block_on_high_risk_noop": structure_validation_block_on_high_risk_noop,
    }
