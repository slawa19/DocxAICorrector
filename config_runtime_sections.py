import os
from collections.abc import Mapping
from typing import Any


def resolve_semantic_validation_and_runtime_settings(
    *,
    config_data: dict[str, object],
    parse_image_mode_fn: Any,
    parse_config_str_fn: Any,
    parse_choice_str_fn: Any,
    parse_config_bool_fn: Any,
    parse_config_score_fn: Any,
    parse_config_int_fn: Any,
    parse_config_float_fn: Any,
    parse_bool_env_fn: Any,
    parse_float_env_fn: Any,
    parse_int_env_fn: Any,
    clamp_score_fn: Any,
    clamp_int_fn: Any,
    clamp_float_fn: Any,
    config_path: Any,
    image_mode_default_value: str,
) -> dict[str, Any]:
    image_mode_default = parse_image_mode_fn(
        parse_config_str_fn(config_data, "image_mode_default", image_mode_default_value),
        source_name=str(config_path),
    )
    semantic_validation_policy = parse_choice_str_fn(
        config_data,
        "semantic_validation_policy",
        "advisory",
        {"advisory", "strict"},
    )
    keep_all_image_variants = parse_config_bool_fn(config_data, "keep_all_image_variants", False)
    min_semantic_match_score = parse_config_score_fn(config_data, "min_semantic_match_score", 0.75)
    min_text_match_score = parse_config_score_fn(config_data, "min_text_match_score", 0.80)
    min_structure_match_score = parse_config_score_fn(config_data, "min_structure_match_score", 0.70)
    validator_confidence_threshold = parse_config_score_fn(config_data, "validator_confidence_threshold", 0.75)
    allow_accept_with_partial_text_loss = parse_config_bool_fn(
        config_data,
        "allow_accept_with_partial_text_loss",
        False,
    )
    prefer_deterministic_reconstruction = parse_config_bool_fn(
        config_data,
        "prefer_deterministic_reconstruction",
        True,
    )
    enable_vision_image_analysis = parse_config_bool_fn(config_data, "enable_vision_image_analysis", True)
    enable_vision_image_validation = parse_config_bool_fn(config_data, "enable_vision_image_validation", True)
    semantic_redraw_max_attempts = parse_config_int_fn(config_data, "semantic_redraw_max_attempts", 2)
    semantic_redraw_max_model_calls_per_image = parse_config_int_fn(
        config_data,
        "semantic_redraw_max_model_calls_per_image",
        semantic_redraw_max_attempts * 3,
    )
    dense_text_bypass_threshold = parse_config_int_fn(config_data, "dense_text_bypass_threshold", 18)
    non_latin_text_bypass_threshold = parse_config_int_fn(config_data, "non_latin_text_bypass_threshold", 12)
    reconstruction_min_canvas_short_side_px = parse_config_int_fn(
        config_data,
        "reconstruction_min_canvas_short_side_px",
        900,
    )
    reconstruction_target_min_font_px = parse_config_int_fn(config_data, "reconstruction_target_min_font_px", 18)
    reconstruction_max_upscale_factor = parse_config_float_fn(config_data, "reconstruction_max_upscale_factor", 3.0)
    reconstruction_background_sample_ratio = parse_config_float_fn(
        config_data,
        "reconstruction_background_sample_ratio",
        0.04,
    )
    reconstruction_background_color_distance_threshold = parse_config_float_fn(
        config_data,
        "reconstruction_background_color_distance_threshold",
        48.0,
    )
    reconstruction_background_uniformity_threshold = parse_config_float_fn(
        config_data,
        "reconstruction_background_uniformity_threshold",
        10.0,
    )

    image_mode_default = parse_image_mode_fn(
        os.getenv("DOCX_AI_IMAGE_MODE_DEFAULT", image_mode_default).strip() or image_mode_default,
        source_name="DOCX_AI_IMAGE_MODE_DEFAULT",
    )
    keep_all_image_variants = parse_bool_env_fn(
        "DOCX_AI_KEEP_ALL_IMAGE_VARIANTS",
        keep_all_image_variants,
    )
    semantic_validation_policy = os.getenv(
        "DOCX_AI_SEMANTIC_VALIDATION_POLICY",
        semantic_validation_policy,
    ).strip().lower() or semantic_validation_policy
    if semantic_validation_policy not in {"advisory", "strict"}:
        raise RuntimeError(
            f"Некорректное значение в DOCX_AI_SEMANTIC_VALIDATION_POLICY: {semantic_validation_policy}"
        )
    min_semantic_match_score = clamp_score_fn(
        parse_float_env_fn("DOCX_AI_MIN_SEMANTIC_MATCH_SCORE", min_semantic_match_score)
    )
    min_text_match_score = clamp_score_fn(parse_float_env_fn("DOCX_AI_MIN_TEXT_MATCH_SCORE", min_text_match_score))
    min_structure_match_score = clamp_score_fn(
        parse_float_env_fn("DOCX_AI_MIN_STRUCTURE_MATCH_SCORE", min_structure_match_score)
    )
    validator_confidence_threshold = clamp_score_fn(
        parse_float_env_fn("DOCX_AI_VALIDATOR_CONFIDENCE_THRESHOLD", validator_confidence_threshold)
    )
    allow_accept_with_partial_text_loss = parse_bool_env_fn(
        "DOCX_AI_ALLOW_ACCEPT_WITH_PARTIAL_TEXT_LOSS",
        allow_accept_with_partial_text_loss,
    )
    prefer_deterministic_reconstruction = parse_bool_env_fn(
        "DOCX_AI_PREFER_DETERMINISTIC_RECONSTRUCTION",
        prefer_deterministic_reconstruction,
    )
    enable_vision_image_analysis = parse_bool_env_fn(
        "DOCX_AI_ENABLE_VISION_IMAGE_ANALYSIS",
        enable_vision_image_analysis,
    )
    enable_vision_image_validation = parse_bool_env_fn(
        "DOCX_AI_ENABLE_VISION_IMAGE_VALIDATION",
        enable_vision_image_validation,
    )
    semantic_redraw_max_attempts = parse_int_env_fn(
        "DOCX_AI_SEMANTIC_REDRAW_MAX_ATTEMPTS",
        semantic_redraw_max_attempts,
    )
    semantic_redraw_max_model_calls_per_image = parse_int_env_fn(
        "DOCX_AI_SEMANTIC_REDRAW_MAX_MODEL_CALLS_PER_IMAGE",
        semantic_redraw_max_model_calls_per_image,
    )
    dense_text_bypass_threshold = parse_int_env_fn(
        "DOCX_AI_DENSE_TEXT_BYPASS_THRESHOLD",
        dense_text_bypass_threshold,
    )
    non_latin_text_bypass_threshold = parse_int_env_fn(
        "DOCX_AI_NON_LATIN_TEXT_BYPASS_THRESHOLD",
        non_latin_text_bypass_threshold,
    )
    reconstruction_min_canvas_short_side_px = parse_int_env_fn(
        "DOCX_AI_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX",
        reconstruction_min_canvas_short_side_px,
    )
    reconstruction_target_min_font_px = parse_int_env_fn(
        "DOCX_AI_RECONSTRUCTION_TARGET_MIN_FONT_PX",
        reconstruction_target_min_font_px,
    )
    reconstruction_max_upscale_factor = parse_float_env_fn(
        "DOCX_AI_RECONSTRUCTION_MAX_UPSCALE_FACTOR",
        reconstruction_max_upscale_factor,
    )
    reconstruction_background_sample_ratio = parse_float_env_fn(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_SAMPLE_RATIO",
        reconstruction_background_sample_ratio,
    )
    reconstruction_background_color_distance_threshold = parse_float_env_fn(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_COLOR_DISTANCE_THRESHOLD",
        reconstruction_background_color_distance_threshold,
    )
    reconstruction_background_uniformity_threshold = parse_float_env_fn(
        "DOCX_AI_RECONSTRUCTION_BACKGROUND_UNIFORMITY_THRESHOLD",
        reconstruction_background_uniformity_threshold,
    )

    return {
        "image_mode_default": image_mode_default,
        "semantic_validation_policy": semantic_validation_policy,
        "keep_all_image_variants": keep_all_image_variants,
        "min_semantic_match_score": min_semantic_match_score,
        "min_text_match_score": min_text_match_score,
        "min_structure_match_score": min_structure_match_score,
        "validator_confidence_threshold": validator_confidence_threshold,
        "allow_accept_with_partial_text_loss": allow_accept_with_partial_text_loss,
        "prefer_deterministic_reconstruction": prefer_deterministic_reconstruction,
        "enable_vision_image_analysis": enable_vision_image_analysis,
        "enable_vision_image_validation": enable_vision_image_validation,
        "semantic_redraw_max_attempts": clamp_int_fn(semantic_redraw_max_attempts, minimum=1, maximum=2),
        "semantic_redraw_max_model_calls_per_image": clamp_int_fn(
            semantic_redraw_max_model_calls_per_image,
            minimum=1,
            maximum=20,
        ),
        "dense_text_bypass_threshold": clamp_int_fn(dense_text_bypass_threshold, minimum=1, maximum=80),
        "non_latin_text_bypass_threshold": clamp_int_fn(non_latin_text_bypass_threshold, minimum=1, maximum=80),
        "reconstruction_min_canvas_short_side_px": clamp_int_fn(
            reconstruction_min_canvas_short_side_px,
            minimum=256,
            maximum=4096,
        ),
        "reconstruction_target_min_font_px": clamp_int_fn(
            reconstruction_target_min_font_px,
            minimum=10,
            maximum=48,
        ),
        "reconstruction_max_upscale_factor": clamp_float_fn(
            reconstruction_max_upscale_factor,
            minimum=1.0,
            maximum=6.0,
        ),
        "reconstruction_background_sample_ratio": clamp_float_fn(
            reconstruction_background_sample_ratio,
            minimum=0.01,
            maximum=0.2,
        ),
        "reconstruction_background_color_distance_threshold": clamp_float_fn(
            reconstruction_background_color_distance_threshold,
            minimum=5.0,
            maximum=255.0,
        ),
        "reconstruction_background_uniformity_threshold": clamp_float_fn(
            reconstruction_background_uniformity_threshold,
            minimum=1.0,
            maximum=64.0,
        ),
    }


def resolve_image_output_settings(
    *,
    image_output_config: dict[str, object],
    parse_image_output_size_fn: Any,
    parse_config_str_fn: Any,
    parse_config_float_fn: Any,
    parse_image_output_size_list_fn: Any,
    parse_config_int_fn: Any,
    parse_image_output_size_csv_env_fn: Any,
    parse_float_env_fn: Any,
    parse_int_env_fn: Any,
    clamp_int_fn: Any,
    clamp_float_fn: Any,
    config_path: Any,
) -> dict[str, Any]:
    image_output_generate_size_square = parse_image_output_size_fn(
        parse_config_str_fn(image_output_config, "generate_size_square", "1024x1024"),
        source_name=f"{config_path}: image_output.generate_size_square",
    )
    image_output_generate_size_landscape = parse_image_output_size_fn(
        parse_config_str_fn(image_output_config, "generate_size_landscape", "1536x1024"),
        source_name=f"{config_path}: image_output.generate_size_landscape",
    )
    image_output_generate_size_portrait = parse_image_output_size_fn(
        parse_config_str_fn(image_output_config, "generate_size_portrait", "1024x1536"),
        source_name=f"{config_path}: image_output.generate_size_portrait",
    )
    image_output_aspect_ratio_threshold = parse_config_float_fn(
        image_output_config,
        "aspect_ratio_threshold",
        1.2,
    )
    image_output_generate_candidate_sizes = parse_image_output_size_list_fn(
        image_output_config.get("generate_candidate_sizes"),
        source_name=f"{config_path}: image_output.generate_candidate_sizes",
        default=("1536x1024", "1024x1536", "1024x1024"),
    )
    image_output_edit_candidate_sizes = parse_image_output_size_list_fn(
        image_output_config.get("edit_candidate_sizes"),
        source_name=f"{config_path}: image_output.edit_candidate_sizes",
        default=("1536x1024", "1024x1536", "1024x1024", "512x512", "256x256"),
    )
    image_output_trim_tolerance = parse_config_int_fn(image_output_config, "trim_tolerance", 20)
    image_output_trim_padding_ratio = parse_config_float_fn(image_output_config, "trim_padding_ratio", 0.02)
    image_output_trim_padding_min_px = parse_config_int_fn(image_output_config, "trim_padding_min_px", 4)
    image_output_trim_max_loss_ratio = parse_config_float_fn(image_output_config, "trim_max_loss_ratio", 0.15)

    image_output_generate_size_square = parse_image_output_size_fn(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE", image_output_generate_size_square).strip()
        or image_output_generate_size_square,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_SQUARE",
    )
    image_output_generate_size_landscape = parse_image_output_size_fn(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_LANDSCAPE", image_output_generate_size_landscape).strip()
        or image_output_generate_size_landscape,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_LANDSCAPE",
    )
    image_output_generate_size_portrait = parse_image_output_size_fn(
        os.getenv("DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_PORTRAIT", image_output_generate_size_portrait).strip()
        or image_output_generate_size_portrait,
        source_name="DOCX_AI_IMAGE_OUTPUT_GENERATE_SIZE_PORTRAIT",
    )
    image_output_generate_candidate_sizes = parse_image_output_size_csv_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_GENERATE_CANDIDATE_SIZES",
        image_output_generate_candidate_sizes,
    )
    image_output_edit_candidate_sizes = parse_image_output_size_csv_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_EDIT_CANDIDATE_SIZES",
        image_output_edit_candidate_sizes,
    )
    image_output_aspect_ratio_threshold = parse_float_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_ASPECT_RATIO_THRESHOLD",
        image_output_aspect_ratio_threshold,
    )
    image_output_trim_tolerance = parse_int_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_TOLERANCE",
        image_output_trim_tolerance,
    )
    image_output_trim_padding_ratio = parse_float_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_RATIO",
        image_output_trim_padding_ratio,
    )
    image_output_trim_padding_min_px = parse_int_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_PADDING_MIN_PX",
        image_output_trim_padding_min_px,
    )
    image_output_trim_max_loss_ratio = parse_float_env_fn(
        "DOCX_AI_IMAGE_OUTPUT_TRIM_MAX_LOSS_RATIO",
        image_output_trim_max_loss_ratio,
    )

    return {
        "image_output_generate_size_square": image_output_generate_size_square,
        "image_output_generate_size_landscape": image_output_generate_size_landscape,
        "image_output_generate_size_portrait": image_output_generate_size_portrait,
        "image_output_generate_candidate_sizes": image_output_generate_candidate_sizes,
        "image_output_edit_candidate_sizes": image_output_edit_candidate_sizes,
        "image_output_aspect_ratio_threshold": clamp_float_fn(
            image_output_aspect_ratio_threshold,
            minimum=1.01,
            maximum=3.0,
        ),
        "image_output_trim_tolerance": clamp_int_fn(image_output_trim_tolerance, minimum=0, maximum=64),
        "image_output_trim_padding_ratio": clamp_float_fn(
            image_output_trim_padding_ratio,
            minimum=0.0,
            maximum=0.25,
        ),
        "image_output_trim_padding_min_px": clamp_int_fn(
            image_output_trim_padding_min_px,
            minimum=0,
            maximum=128,
        ),
        "image_output_trim_max_loss_ratio": clamp_float_fn(
            image_output_trim_max_loss_ratio,
            minimum=0.0,
            maximum=0.49,
        ),
    }


def _resolve_audiobook_model_default(
    *,
    config_data: dict[str, object],
    model_registry_settings: Mapping[str, Any],
    config_path: Any,
) -> str:
    models_value = config_data.get("models")
    if models_value is None:
        models_config: dict[str, object] = {}
    elif isinstance(models_value, dict):
        models_config = models_value
    else:
        raise RuntimeError(f"Некорректное поле models в {config_path}: ожидается таблица")

    audiobook_value = models_config.get("audiobook")
    if audiobook_value is None:
        audiobook_config: dict[str, object] = {}
    elif isinstance(audiobook_value, dict):
        audiobook_config = audiobook_value
    else:
        raise RuntimeError(f"Некорректное поле models.audiobook в {config_path}: ожидается таблица")

    raw_audiobook_model = audiobook_config.get("default")
    if raw_audiobook_model is not None:
        if not isinstance(raw_audiobook_model, str) or not raw_audiobook_model.strip():
            raise RuntimeError(f"Некорректное поле models.audiobook.default в {config_path}: ожидается непустая строка")
        return raw_audiobook_model.strip()

    models = model_registry_settings.get("models")
    text_model = getattr(models, "text", None)
    text_default_model = str(getattr(text_model, "default", "")).strip()
    if not text_default_model:
        raise RuntimeError("Text default model is not resolved for audiobook fallback.")
    return text_default_model


def resolve_text_runtime_defaults(
    *,
    config_data: dict[str, object],
    model_registry_settings: Mapping[str, Any],
    default_chunk_size: int,
    default_max_retries: int,
    config_path: Any,
    parse_supported_languages_fn: Any,
    parse_choice_str_fn: Any,
    parse_config_str_fn: Any,
    parse_optional_config_str_fn: Any,
    validate_text_transform_context_fn: Any,
    parse_config_bool_fn: Any,
    parse_int_env_fn: Any,
    parse_choice_env_fn: Any,
    parse_bool_env_fn: Any,
    parse_optional_str_env_fn: Any,
    clamp_int_fn: Any,
    processing_operation_values: tuple[str, ...],
) -> dict[str, Any]:
    chunk_size = config_data.get("chunk_size", default_chunk_size)
    if not isinstance(chunk_size, int):
        raise RuntimeError(f"Некорректное поле chunk_size в {config_path}")

    max_retries = config_data.get("max_retries", default_max_retries)
    if not isinstance(max_retries, int):
        raise RuntimeError(f"Некорректное поле max_retries в {config_path}")

    supported_languages = parse_supported_languages_fn(
        config_data.get("supported_languages"),
        source_name=f"{config_path}: supported_languages",
    )
    supported_language_codes = {language.code for language in supported_languages}
    processing_operation_default = parse_choice_str_fn(
        config_data,
        "processing_operation_default",
        "edit",
        set(processing_operation_values),
    )
    source_language_default = parse_config_str_fn(config_data, "source_language_default", "en").strip().lower()
    target_language_default = parse_config_str_fn(config_data, "target_language_default", "ru").strip().lower()
    editorial_intensity_default = parse_config_str_fn(config_data, "editorial_intensity_default", "literary").strip().lower()
    translation_second_pass_default = parse_config_bool_fn(config_data, "translation_second_pass_default", False)
    audiobook_postprocess_default = parse_config_bool_fn(config_data, "audiobook_postprocess_default", False)
    raw_translation_second_pass_model = config_data.get("translation_second_pass_model")
    if raw_translation_second_pass_model is None:
        translation_second_pass_model = ""
    elif not isinstance(raw_translation_second_pass_model, str):
        raise RuntimeError(f"Некорректное поле translation_second_pass_model в {config_path}: ожидается строка")
    else:
        translation_second_pass_model = raw_translation_second_pass_model.strip()
    audiobook_model = _resolve_audiobook_model_default(
        config_data=config_data,
        model_registry_settings=model_registry_settings,
        config_path=config_path,
    )
    validate_text_transform_context_fn(
        operation=processing_operation_default,
        source_language=source_language_default,
        target_language=target_language_default,
        supported_language_codes=supported_language_codes,
    )
    enable_paragraph_markers = parse_config_bool_fn(config_data, "enable_paragraph_markers", False)

    chunk_size = parse_int_env_fn("DOCX_AI_CHUNK_SIZE", chunk_size)
    max_retries = parse_int_env_fn("DOCX_AI_MAX_RETRIES", max_retries)
    processing_operation_default = parse_choice_env_fn(
        "DOCX_AI_PROCESSING_OPERATION_DEFAULT",
        default=processing_operation_default,
        allowed_values=set(processing_operation_values),
    )
    source_language_default = (
        os.getenv("DOCX_AI_SOURCE_LANGUAGE_DEFAULT", source_language_default).strip().lower()
        or source_language_default
    )
    target_language_default = (
        os.getenv("DOCX_AI_TARGET_LANGUAGE_DEFAULT", target_language_default).strip().lower()
        or target_language_default
    )
    editorial_intensity_default = (
        os.getenv("DOCX_AI_EDITORIAL_INTENSITY_DEFAULT", editorial_intensity_default).strip().lower()
        or editorial_intensity_default
    )
    translation_second_pass_default = parse_bool_env_fn(
        "DOCX_AI_TRANSLATION_SECOND_PASS_DEFAULT",
        translation_second_pass_default,
    )
    audiobook_postprocess_default = parse_bool_env_fn(
        "DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT",
        audiobook_postprocess_default,
    )
    translation_second_pass_model = parse_optional_str_env_fn("DOCX_AI_TRANSLATION_SECOND_PASS_MODEL") or translation_second_pass_model
    validate_text_transform_context_fn(
        operation=processing_operation_default,
        source_language=source_language_default,
        target_language=target_language_default,
        supported_language_codes=supported_language_codes,
    )
    enable_paragraph_markers = parse_bool_env_fn(
        "DOCX_AI_ENABLE_PARAGRAPH_MARKERS",
        enable_paragraph_markers,
    )

    return {
        "chunk_size": clamp_int_fn(chunk_size, minimum=3000, maximum=12000),
        "max_retries": clamp_int_fn(max_retries, minimum=1, maximum=5),
        "supported_languages": supported_languages,
        "processing_operation_default": processing_operation_default,
        "source_language_default": source_language_default,
        "target_language_default": target_language_default,
        "editorial_intensity_default": editorial_intensity_default,
        "translation_second_pass_default": translation_second_pass_default,
        "translation_second_pass_model": translation_second_pass_model,
        "audiobook_postprocess_default": audiobook_postprocess_default,
        "audiobook_model": audiobook_model,
        "enable_paragraph_markers": enable_paragraph_markers,
    }


def resolve_output_font_settings(
    *,
    config_data: dict[str, object],
    parse_optional_config_section_fn: Any,
    parse_optional_config_str_fn: Any,
    parse_optional_str_env_fn: Any,
) -> dict[str, Any]:
    output_config = parse_optional_config_section_fn(config_data, "output")
    output_fonts_config = parse_optional_config_section_fn(output_config, "fonts", parent_name="output")
    output_body_font = parse_optional_config_str_fn(output_fonts_config, "body")
    output_heading_font = parse_optional_config_str_fn(output_fonts_config, "heading")

    output_body_font = parse_optional_str_env_fn("DOCX_AI_OUTPUT_BODY_FONT") or output_body_font
    output_heading_font = parse_optional_str_env_fn("DOCX_AI_OUTPUT_HEADING_FONT") or output_heading_font

    return {
        "output_body_font": output_body_font,
        "output_heading_font": output_heading_font,
    }
