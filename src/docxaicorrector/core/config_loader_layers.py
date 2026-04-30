import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OptionalSectionConfigs:
    image_output_config: dict[str, object]
    paragraph_boundary_normalization_config: dict[str, object]
    layout_artifact_cleanup_config: dict[str, object]
    relation_normalization_config: dict[str, object]
    paragraph_boundary_ai_review_config: dict[str, object]
    structure_validation_config: dict[str, object]


@dataclass(frozen=True)
class ResolvedAppConfigSections:
    model_registry_settings: Mapping[str, Any]
    text_runtime_defaults: Mapping[str, Any]
    output_font_settings: Mapping[str, Any]
    paragraph_boundary_settings: Mapping[str, Any]
    layout_artifact_cleanup_settings: Mapping[str, Any]
    relation_normalization_settings: Mapping[str, Any]
    structure_recognition_settings: Mapping[str, Any]
    structure_validation_settings: Mapping[str, Any]
    semantic_validation_runtime_settings: Mapping[str, Any]
    image_output_settings: Mapping[str, Any]


def build_app_config_payload(
    *,
    model_registry_settings: Mapping[str, Any],
    text_runtime_defaults: Mapping[str, Any],
    paragraph_boundary_settings: Mapping[str, Any],
    layout_artifact_cleanup_settings: Mapping[str, Any],
    relation_normalization_settings: Mapping[str, Any],
    structure_recognition_settings: Mapping[str, Any],
    structure_validation_settings: Mapping[str, Any],
    output_font_settings: Mapping[str, Any],
    semantic_validation_runtime_settings: Mapping[str, Any],
    image_output_settings: Mapping[str, Any],
) -> dict[str, Any]:
    models = model_registry_settings["models"]
    paragraph_boundary_ai_review_mode = paragraph_boundary_settings["paragraph_boundary_ai_review_mode"]
    if not paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"]:
        paragraph_boundary_ai_review_mode = "off"

    return {
        "models": models,
        "default_model": model_registry_settings["default_model"],
        "model_options": list(models.text.options),
        "chunk_size": text_runtime_defaults["chunk_size"],
        "max_retries": text_runtime_defaults["max_retries"],
        "processing_operation_default": text_runtime_defaults["processing_operation_default"],
        "source_language_default": text_runtime_defaults["source_language_default"],
        "target_language_default": text_runtime_defaults["target_language_default"],
        "editorial_intensity_default": text_runtime_defaults["editorial_intensity_default"],
        "translation_domain_default": text_runtime_defaults["translation_domain_default"],
        "translation_second_pass_default": text_runtime_defaults["translation_second_pass_default"],
        "translation_second_pass_model": text_runtime_defaults["translation_second_pass_model"],
        "audiobook_postprocess_default": text_runtime_defaults["audiobook_postprocess_default"],
        "audiobook_model": text_runtime_defaults["audiobook_model"],
        "supported_languages": text_runtime_defaults["supported_languages"],
        "enable_paragraph_markers": text_runtime_defaults["enable_paragraph_markers"],
        "paragraph_boundary_normalization_enabled": paragraph_boundary_settings["paragraph_boundary_normalization_enabled"],
        "paragraph_boundary_normalization_mode": paragraph_boundary_settings["paragraph_boundary_normalization_mode"],
        "paragraph_boundary_normalization_save_debug_artifacts": paragraph_boundary_settings[
            "paragraph_boundary_normalization_save_debug_artifacts"
        ],
        "paragraph_boundary_ai_review_enabled": paragraph_boundary_settings["paragraph_boundary_ai_review_enabled"],
        "paragraph_boundary_ai_review_mode": paragraph_boundary_ai_review_mode,
        "paragraph_boundary_ai_review_candidate_limit": paragraph_boundary_settings[
            "paragraph_boundary_ai_review_candidate_limit"
        ],
        "paragraph_boundary_ai_review_timeout_seconds": paragraph_boundary_settings[
            "paragraph_boundary_ai_review_timeout_seconds"
        ],
        "paragraph_boundary_ai_review_max_tokens_per_candidate": paragraph_boundary_settings[
            "paragraph_boundary_ai_review_max_tokens_per_candidate"
        ],
        "layout_artifact_cleanup_enabled": layout_artifact_cleanup_settings["layout_artifact_cleanup_enabled"],
        "layout_artifact_cleanup_min_repeat_count": layout_artifact_cleanup_settings[
            "layout_artifact_cleanup_min_repeat_count"
        ],
        "layout_artifact_cleanup_max_repeated_text_chars": layout_artifact_cleanup_settings[
            "layout_artifact_cleanup_max_repeated_text_chars"
        ],
        "layout_artifact_cleanup_save_debug_artifacts": layout_artifact_cleanup_settings[
            "layout_artifact_cleanup_save_debug_artifacts"
        ],
        "relation_normalization_enabled": relation_normalization_settings["relation_normalization_enabled"],
        "relation_normalization_profile": relation_normalization_settings["relation_normalization_profile"],
        "relation_normalization_enabled_relation_kinds": relation_normalization_settings[
            "relation_normalization_enabled_relation_kinds"
        ],
        "relation_normalization_save_debug_artifacts": relation_normalization_settings[
            "relation_normalization_save_debug_artifacts"
        ],
        "structure_recognition_mode": structure_recognition_settings["structure_recognition_mode"],
        "structure_recognition_enabled": structure_recognition_settings["structure_recognition_enabled"],
        "structure_recognition_model": models.structure_recognition,
        "structure_recognition_max_window_paragraphs": structure_recognition_settings[
            "structure_recognition_max_window_paragraphs"
        ],
        "structure_recognition_overlap_paragraphs": structure_recognition_settings[
            "structure_recognition_overlap_paragraphs"
        ],
        "structure_recognition_timeout_seconds": structure_recognition_settings[
            "structure_recognition_timeout_seconds"
        ],
        "structure_recognition_min_confidence": structure_recognition_settings["structure_recognition_min_confidence"],
        "structure_recognition_cache_enabled": structure_recognition_settings["structure_recognition_cache_enabled"],
        "structure_recognition_save_debug_artifacts": structure_recognition_settings[
            "structure_recognition_save_debug_artifacts"
        ],
        "structure_validation_enabled": structure_validation_settings["structure_validation_enabled"],
        "structure_validation_min_paragraphs_for_auto_gate": structure_validation_settings[
            "structure_validation_min_paragraphs_for_auto_gate"
        ],
        "structure_validation_min_explicit_heading_density": structure_validation_settings[
            "structure_validation_min_explicit_heading_density"
        ],
        "structure_validation_max_suspicious_short_body_ratio_without_escalation": structure_validation_settings[
            "structure_validation_max_suspicious_short_body_ratio_without_escalation"
        ],
        "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation": structure_validation_settings[
            "structure_validation_max_all_caps_or_centered_body_ratio_without_escalation"
        ],
        "structure_validation_toc_like_sequence_min_length": structure_validation_settings[
            "structure_validation_toc_like_sequence_min_length"
        ],
        "structure_validation_forbid_heading_only_collapse": structure_validation_settings[
            "structure_validation_forbid_heading_only_collapse"
        ],
        "structure_validation_save_debug_artifacts": structure_validation_settings[
            "structure_validation_save_debug_artifacts"
        ],
        "structure_validation_block_on_high_risk_noop": structure_validation_settings[
            "structure_validation_block_on_high_risk_noop"
        ],
        "output_body_font": output_font_settings["output_body_font"],
        "output_heading_font": output_font_settings["output_heading_font"],
        "image_mode_default": semantic_validation_runtime_settings["image_mode_default"],
        "semantic_validation_policy": semantic_validation_runtime_settings["semantic_validation_policy"],
        "keep_all_image_variants": semantic_validation_runtime_settings["keep_all_image_variants"],
        "validation_model": models.image_validation,
        "min_semantic_match_score": semantic_validation_runtime_settings["min_semantic_match_score"],
        "min_text_match_score": semantic_validation_runtime_settings["min_text_match_score"],
        "min_structure_match_score": semantic_validation_runtime_settings["min_structure_match_score"],
        "validator_confidence_threshold": semantic_validation_runtime_settings["validator_confidence_threshold"],
        "allow_accept_with_partial_text_loss": semantic_validation_runtime_settings[
            "allow_accept_with_partial_text_loss"
        ],
        "prefer_deterministic_reconstruction": semantic_validation_runtime_settings[
            "prefer_deterministic_reconstruction"
        ],
        "reconstruction_model": models.image_reconstruction,
        "enable_vision_image_analysis": semantic_validation_runtime_settings["enable_vision_image_analysis"],
        "enable_vision_image_validation": semantic_validation_runtime_settings["enable_vision_image_validation"],
        "semantic_redraw_max_attempts": semantic_validation_runtime_settings["semantic_redraw_max_attempts"],
        "semantic_redraw_max_model_calls_per_image": semantic_validation_runtime_settings[
            "semantic_redraw_max_model_calls_per_image"
        ],
        "dense_text_bypass_threshold": semantic_validation_runtime_settings["dense_text_bypass_threshold"],
        "non_latin_text_bypass_threshold": semantic_validation_runtime_settings["non_latin_text_bypass_threshold"],
        "reconstruction_min_canvas_short_side_px": semantic_validation_runtime_settings[
            "reconstruction_min_canvas_short_side_px"
        ],
        "reconstruction_target_min_font_px": semantic_validation_runtime_settings[
            "reconstruction_target_min_font_px"
        ],
        "reconstruction_max_upscale_factor": semantic_validation_runtime_settings[
            "reconstruction_max_upscale_factor"
        ],
        "reconstruction_background_sample_ratio": semantic_validation_runtime_settings[
            "reconstruction_background_sample_ratio"
        ],
        "reconstruction_background_color_distance_threshold": semantic_validation_runtime_settings[
            "reconstruction_background_color_distance_threshold"
        ],
        "reconstruction_background_uniformity_threshold": semantic_validation_runtime_settings[
            "reconstruction_background_uniformity_threshold"
        ],
        "image_output_generate_size_square": image_output_settings["image_output_generate_size_square"],
        "image_output_generate_size_landscape": image_output_settings["image_output_generate_size_landscape"],
        "image_output_generate_size_portrait": image_output_settings["image_output_generate_size_portrait"],
        "image_output_generate_candidate_sizes": image_output_settings["image_output_generate_candidate_sizes"],
        "image_output_edit_candidate_sizes": image_output_settings["image_output_edit_candidate_sizes"],
        "image_output_aspect_ratio_threshold": image_output_settings["image_output_aspect_ratio_threshold"],
        "image_output_trim_tolerance": image_output_settings["image_output_trim_tolerance"],
        "image_output_trim_padding_ratio": image_output_settings["image_output_trim_padding_ratio"],
        "image_output_trim_padding_min_px": image_output_settings["image_output_trim_padding_min_px"],
        "image_output_trim_max_loss_ratio": image_output_settings["image_output_trim_max_loss_ratio"],
    }


def load_config_data(
    *,
    config_path: Path,
    load_project_dotenv_fn: Callable[[], None],
    reject_legacy_manual_review_aliases_fn: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    load_project_dotenv_fn()
    config_data: dict[str, object] = {}
    if config_path.exists():
        with config_path.open("rb") as file_handle:
            config_data = tomllib.load(file_handle)
    reject_legacy_manual_review_aliases_fn(config_data)
    return config_data


def resolve_optional_section_configs(
    config_data: dict[str, object],
    *,
    parse_optional_config_section_fn: Callable[..., dict[str, object]],
) -> OptionalSectionConfigs:
    return OptionalSectionConfigs(
        image_output_config=parse_optional_config_section_fn(config_data, "image_output"),
        paragraph_boundary_normalization_config=parse_optional_config_section_fn(
            config_data,
            "paragraph_boundary_normalization",
        ),
        layout_artifact_cleanup_config=parse_optional_config_section_fn(
            config_data,
            "layout_artifact_cleanup",
        ),
        relation_normalization_config=parse_optional_config_section_fn(
            config_data,
            "relation_normalization",
        ),
        paragraph_boundary_ai_review_config=parse_optional_config_section_fn(
            config_data,
            "paragraph_boundary_ai_review",
        ),
        structure_validation_config=parse_optional_config_section_fn(
            config_data,
            "structure_validation",
        ),
    )


def resolve_app_config_sections(
    *,
    config_data: dict[str, object],
    optional_sections: OptionalSectionConfigs,
    resolve_model_registry_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_text_runtime_defaults_fn: Callable[..., Mapping[str, Any]],
    resolve_output_font_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_paragraph_boundary_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_layout_artifact_cleanup_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_relation_normalization_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_structure_recognition_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_structure_validation_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_semantic_validation_and_runtime_settings_fn: Callable[..., Mapping[str, Any]],
    resolve_image_output_settings_fn: Callable[..., Mapping[str, Any]],
) -> ResolvedAppConfigSections:
    model_registry_settings = resolve_model_registry_settings_fn(
        config_data=config_data,
    )
    return ResolvedAppConfigSections(
        model_registry_settings=model_registry_settings,
        text_runtime_defaults=resolve_text_runtime_defaults_fn(
            config_data=config_data,
            model_registry_settings=model_registry_settings,
        ),
        output_font_settings=resolve_output_font_settings_fn(
            config_data=config_data,
        ),
        paragraph_boundary_settings=resolve_paragraph_boundary_settings_fn(
            paragraph_boundary_normalization_config=optional_sections.paragraph_boundary_normalization_config,
            paragraph_boundary_ai_review_config=optional_sections.paragraph_boundary_ai_review_config,
        ),
        layout_artifact_cleanup_settings=resolve_layout_artifact_cleanup_settings_fn(
            layout_artifact_cleanup_config=optional_sections.layout_artifact_cleanup_config,
        ),
        relation_normalization_settings=resolve_relation_normalization_settings_fn(
            relation_normalization_config=optional_sections.relation_normalization_config,
        ),
        structure_recognition_settings=resolve_structure_recognition_settings_fn(
            structure_recognition_config=model_registry_settings["structure_recognition_config"],
        ),
        structure_validation_settings=resolve_structure_validation_settings_fn(
            structure_validation_config=optional_sections.structure_validation_config,
        ),
        semantic_validation_runtime_settings=resolve_semantic_validation_and_runtime_settings_fn(
            config_data=config_data,
        ),
        image_output_settings=resolve_image_output_settings_fn(
            image_output_config=optional_sections.image_output_config,
        ),
    )
