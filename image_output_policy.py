from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


DEFAULT_GENERATE_CANDIDATE_SIZES = ("1536x1024", "1024x1536", "1024x1024")
DEFAULT_EDIT_CANDIDATE_SIZES = ("1536x1024", "1024x1536", "1024x1024", "512x512", "256x256")
DEFAULT_SQUARE_SIZE = "1024x1024"
DEFAULT_LANDSCAPE_SIZE = "1536x1024"
DEFAULT_PORTRAIT_SIZE = "1024x1536"
DEFAULT_ASPECT_RATIO_THRESHOLD = 1.2
DEFAULT_TRIM_TOLERANCE = 20
DEFAULT_TRIM_PADDING_RATIO = 0.02
DEFAULT_TRIM_PADDING_MIN_PX = 4
DEFAULT_TRIM_MAX_LOSS_RATIO = 0.15


@dataclass(frozen=True)
class ImageOutputPolicy:
    generate_candidate_sizes: tuple[str, ...] = DEFAULT_GENERATE_CANDIDATE_SIZES
    edit_candidate_sizes: tuple[str, ...] = DEFAULT_EDIT_CANDIDATE_SIZES
    generate_size_square: str = DEFAULT_SQUARE_SIZE
    generate_size_landscape: str = DEFAULT_LANDSCAPE_SIZE
    generate_size_portrait: str = DEFAULT_PORTRAIT_SIZE
    aspect_ratio_threshold: float = DEFAULT_ASPECT_RATIO_THRESHOLD
    trim_tolerance: int = DEFAULT_TRIM_TOLERANCE
    trim_padding_ratio: float = DEFAULT_TRIM_PADDING_RATIO
    trim_padding_min_px: int = DEFAULT_TRIM_PADDING_MIN_PX
    trim_max_loss_ratio: float = DEFAULT_TRIM_MAX_LOSS_RATIO


def resolve_image_output_policy(config: Mapping[str, object] | None = None) -> ImageOutputPolicy:
    if config is None:
        return ImageOutputPolicy()
    return ImageOutputPolicy(
        generate_candidate_sizes=_config_size_list(
            config,
            "image_output_generate_candidate_sizes",
            DEFAULT_GENERATE_CANDIDATE_SIZES,
        ),
        edit_candidate_sizes=_config_size_list(
            config,
            "image_output_edit_candidate_sizes",
            DEFAULT_EDIT_CANDIDATE_SIZES,
        ),
        generate_size_square=_config_str(config, "image_output_generate_size_square", DEFAULT_SQUARE_SIZE),
        generate_size_landscape=_config_str(config, "image_output_generate_size_landscape", DEFAULT_LANDSCAPE_SIZE),
        generate_size_portrait=_config_str(config, "image_output_generate_size_portrait", DEFAULT_PORTRAIT_SIZE),
        aspect_ratio_threshold=_config_float(
            config,
            "image_output_aspect_ratio_threshold",
            DEFAULT_ASPECT_RATIO_THRESHOLD,
        ),
        trim_tolerance=_config_int(config, "image_output_trim_tolerance", DEFAULT_TRIM_TOLERANCE),
        trim_padding_ratio=_config_float(
            config,
            "image_output_trim_padding_ratio",
            DEFAULT_TRIM_PADDING_RATIO,
        ),
        trim_padding_min_px=_config_int(
            config,
            "image_output_trim_padding_min_px",
            DEFAULT_TRIM_PADDING_MIN_PX,
        ),
        trim_max_loss_ratio=_config_float(
            config,
            "image_output_trim_max_loss_ratio",
            DEFAULT_TRIM_MAX_LOSS_RATIO,
        ),
    )


def select_nearest_size(source_size: tuple[int, int], candidate_sizes: tuple[str, ...]) -> str:
    if not candidate_sizes:
        return DEFAULT_SQUARE_SIZE
    source_width, source_height = source_size
    if source_width <= 0 or source_height <= 0:
        return candidate_sizes[-1]

    source_ratio = source_width / source_height
    ranked_sizes = sorted(
        candidate_sizes,
        key=lambda candidate: (_size_ratio_distance(source_ratio, candidate), _size_area_distance(source_size, candidate)),
    )
    return ranked_sizes[0]


def select_nearest_fallback_size(current_size: str, supported_sizes: tuple[str, ...]) -> str | None:
    if not supported_sizes:
        return None
    try:
        current_width, current_height = _parse_size(current_size)
    except ValueError:
        return supported_sizes[0]
    return select_nearest_size((current_width, current_height), supported_sizes)


def _config_str(config: Mapping[str, object], key: str, default: str) -> str:
    value = config.get(key, default)
    return value if isinstance(value, str) and value.strip() else default


def _config_size_list(config: Mapping[str, object], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = config.get(key)
    if value is None:
        return default
    if not isinstance(value, (list, tuple)):
        return default
    normalized = [item.strip().lower() for item in value if isinstance(item, str) and item.strip()]
    if not normalized:
        return default
    return tuple(normalized)


def _config_int(config: Mapping[str, object], key: str, default: int) -> int:
    value = config.get(key, default)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _config_float(config: Mapping[str, object], key: str, default: float) -> float:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def _parse_size(size: str) -> tuple[int, int]:
    width_text, separator, height_text = size.partition("x")
    if separator != "x":
        raise ValueError(size)
    width = int(width_text)
    height = int(height_text)
    if width <= 0 or height <= 0:
        raise ValueError(size)
    return width, height


def _size_ratio_distance(source_ratio: float, candidate_size: str) -> float:
    candidate_width, candidate_height = _parse_size(candidate_size)
    return abs(source_ratio - (candidate_width / candidate_height))


def _size_area_distance(source_size: tuple[int, int], candidate_size: str) -> int:
    candidate_width, candidate_height = _parse_size(candidate_size)
    return abs((source_size[0] * source_size[1]) - (candidate_width * candidate_height))