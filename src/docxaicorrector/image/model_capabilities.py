"""What each OpenAI image model accepts, so a request is built right the first time.

Spec 062 FR-004. Before this table every Images API payload carried the same optional
parameters for every model (``response_format``, ``input_fidelity``, ``quality``,
``background``) and a parameter the model refused was removed only when the provider's
ERROR TEXT happened to name it (``image/shared.py::extract_unsupported_parameter_name``).
A model that refused with any other wording sent the whole image down the safe-fallback
chain. Now the payload is built from a POSITIVE statement of what the model accepts; the
error-text adaptation in ``image/generation.py`` stays only as a logged last resort.

The table is keyed by model id (product configuration, Constitution VII), never by
anything in a document. A dated snapshot (``gpt-image-2.5-flare-2026-09-08``) resolves to
its family. An id outside the table gets the minimal request — ``model``, ``prompt``,
``size``, ``quality``, ``output_format`` (plus ``image`` for edits) — and one WARNING per
id per process.

Where each row comes from, read 2026-11-07:

* installed SDK ``openai`` 3.16.2, ``types/image_generate_params.py`` /
  ``types/image_edit_params.py``: ``response_format`` "isn't supported for the GPT image
  models, which always return base64-encoded images"; 2.5 sunburst/flare "also support
  ``xhigh`` and ``max``" and "support ``opaque`` and ``transparent`` backgrounds"; for
  ``gpt-image-2`` transparent is "in preview"; ``gpt-image-2`` and 2.5 accept arbitrary
  ``WxH``, "divisible by 16", aspect "between 1:3 and 3:1", maximum ``3840x2160``;
* developers.openai.com/api/reference/resources/images/methods/edit: ``input_fidelity``
  "Supports ``high`` and ``low`` on ``gpt-image-1.5``", "For ``gpt-image-2``, omit this
  parameter"; nothing stated for 2.5 or 2.6;
* developers.openai.com/api/docs/guides/image-generation: total pixels "between 655,360
  and 8,294,400";
* developers.openai.com/api/docs/models/gpt-image-2.6-{flare,sunburst}: no quality,
  background or size rules stated — the 2.6 rows are therefore the conservative ones
  (standard sizes, low/medium/high, no background, no input_fidelity) until a live call
  says otherwise.

Measured by the spec 062 FR-006 live probe on 2026-11-07 (``specs/062-image-models-refresh/
spec.md`` Changelog): both 2.5 models accept ``images.generate`` with ``size=1024x640`` (the
655 360-pixel minimum), ``quality=low``, ``background=transparent``, ``output_format=png`` and
no ``response_format``, and ``images.edit`` without ``input_fidelity``. With it they answer
400 ``invalid_input_fidelity_model``: "The model 'gpt-image-2.5-flare' does not support the
'input_fidelity' parameter." That wording carries none of the markers
``extract_unsupported_parameter_name`` looks for, so before this table every structured and
direct edit on 2.5 would have failed outright instead of being retried without the parameter.
The responses carry ``usage`` (input/output image and text tokens) but no model id.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from docxaicorrector.core.logger import log_event
from docxaicorrector.image.output_policy import select_nearest_fallback_size

STANDARD_GPT_IMAGE_SIZES = ("1024x1024", "1536x1024", "1024x1536")
_SNAPSHOT_SUFFIX_PATTERN = re.compile(r"^(?P<family>.+?)-\d{4}-\d{2}-\d{2}$")
_SIZE_PATTERN = re.compile(r"^(?P<width>\d+)x(?P<height>\d+)$")


@dataclass(frozen=True)
class ImageModelCapabilities:
    family: str
    quality_values: frozenset[str]
    background_values: frozenset[str]
    accepts_input_fidelity: bool
    accepts_response_format: bool
    standard_sizes: tuple[str, ...]
    arbitrary_sizes: bool
    size_multiple: int
    min_pixels: int
    max_pixels: int
    max_edge: int
    max_aspect_ratio: float
    max_input_images: int


def _gpt_image_2x(
    family: str,
    *,
    quality_values: tuple[str, ...],
    background_values: tuple[str, ...],
    accepts_input_fidelity: bool,
    arbitrary_sizes: bool,
) -> ImageModelCapabilities:
    return ImageModelCapabilities(
        family=family,
        quality_values=frozenset(quality_values),
        background_values=frozenset(background_values),
        accepts_input_fidelity=accepts_input_fidelity,
        accepts_response_format=False,
        standard_sizes=STANDARD_GPT_IMAGE_SIZES,
        arbitrary_sizes=arbitrary_sizes,
        size_multiple=16,
        min_pixels=655_360,
        max_pixels=8_294_400,
        max_edge=3840,
        max_aspect_ratio=3.0,
        max_input_images=16,
    )


IMAGE_MODEL_CAPABILITIES: dict[str, ImageModelCapabilities] = {
    # Retires 2026-12-01 (OpenAI deprecations page); kept so an explicit pin still builds a
    # correct request until then.
    "gpt-image-1.5": ImageModelCapabilities(
        family="gpt-image-1.5",
        quality_values=frozenset({"low", "medium", "high", "auto"}),
        background_values=frozenset({"transparent", "opaque", "auto"}),
        accepts_input_fidelity=True,
        accepts_response_format=False,
        standard_sizes=STANDARD_GPT_IMAGE_SIZES,
        arbitrary_sizes=False,
        size_multiple=1,
        min_pixels=1024 * 1024,
        max_pixels=1536 * 1024,
        max_edge=1536,
        max_aspect_ratio=1.5,
        max_input_images=16,
    ),
    "gpt-image-2": _gpt_image_2x(
        "gpt-image-2",
        quality_values=("low", "medium", "high", "auto"),
        background_values=("opaque", "auto"),
        accepts_input_fidelity=False,
        arbitrary_sizes=True,
    ),
    "gpt-image-2.5-flare": _gpt_image_2x(
        "gpt-image-2.5-flare",
        quality_values=("low", "medium", "high", "xhigh", "max", "auto"),
        background_values=("opaque", "transparent"),
        accepts_input_fidelity=False,
        arbitrary_sizes=True,
    ),
    "gpt-image-2.5-sunburst": _gpt_image_2x(
        "gpt-image-2.5-sunburst",
        quality_values=("low", "medium", "high", "xhigh", "max", "auto"),
        background_values=("opaque", "transparent"),
        accepts_input_fidelity=False,
        arbitrary_sizes=True,
    ),
    "gpt-image-2.6-flare": _gpt_image_2x(
        "gpt-image-2.6-flare",
        quality_values=("low", "medium", "high", "auto"),
        background_values=(),
        accepts_input_fidelity=False,
        arbitrary_sizes=False,
    ),
    "gpt-image-2.6-sunburst": _gpt_image_2x(
        "gpt-image-2.6-sunburst",
        quality_values=("low", "medium", "high", "auto"),
        background_values=(),
        accepts_input_fidelity=False,
        arbitrary_sizes=False,
    ),
}

_WARNED_UNKNOWN_IMAGE_MODELS: set[str] = set()


def api_model_id(model: str) -> str:
    """The id an OpenAI request carries: the selector without its ``openai:`` provider prefix.

    Spec 062 acceptance review 2026-11-07, finding 3: ``openai:gpt-image-2.5-flare`` is a valid
    selector (``core.config._validate_image_model_selection``), but the prefix was stripped
    only to look up this table, and the request went out with ``model="openai:…"``. Every
    image-pipeline request (Images API and the vision Responses calls) passes its model
    through here; the configuration keeps the selector as written.
    """

    normalized = str(model or "").strip()
    if normalized.lower().startswith("openai:"):
        normalized = normalized.split(":", 1)[1].strip()
    return normalized


def resolve_image_model_capabilities(model: str) -> ImageModelCapabilities | None:
    """The table row for ``model`` or its dated snapshot; None when the id is unknown."""

    model_id = api_model_id(model)
    if model_id in IMAGE_MODEL_CAPABILITIES:
        return IMAGE_MODEL_CAPABILITIES[model_id]
    snapshot_match = _SNAPSHOT_SUFFIX_PATTERN.match(model_id)
    if snapshot_match is not None:
        return IMAGE_MODEL_CAPABILITIES.get(snapshot_match.group("family"))
    return None


def _parse_size(size: str) -> tuple[int, int] | None:
    match = _SIZE_PATTERN.match(str(size or "").strip().lower())
    if match is None:
        return None
    return int(match.group("width")), int(match.group("height"))


def accepts_size(capabilities: ImageModelCapabilities, size: str) -> bool:
    normalized_size = str(size or "").strip().lower()
    if normalized_size in capabilities.standard_sizes:
        return True
    if not capabilities.arbitrary_sizes:
        return False
    parsed = _parse_size(normalized_size)
    if parsed is None:
        return False
    width, height = parsed
    if width <= 0 or height <= 0:
        return False
    if width % capabilities.size_multiple or height % capabilities.size_multiple:
        return False
    if max(width, height) > capabilities.max_edge:
        return False
    if not capabilities.min_pixels <= width * height <= capabilities.max_pixels:
        return False
    return max(width, height) / min(width, height) <= capabilities.max_aspect_ratio


def filter_sizes_for_model(model: str, sizes: tuple[str, ...]) -> tuple[str, ...]:
    """The subset of ``sizes`` the model accepts; its standard sizes when none survive.

    An unknown model keeps only the three standard sizes every GPT image model accepts.
    """

    capabilities = resolve_image_model_capabilities(model)
    standard_sizes = capabilities.standard_sizes if capabilities is not None else STANDARD_GPT_IMAGE_SIZES
    if capabilities is None:
        accepted = tuple(size for size in sizes if size.strip().lower() in standard_sizes)
    else:
        accepted = tuple(size for size in sizes if accepts_size(capabilities, size))
    return accepted or standard_sizes


def _coerce_size(capabilities: ImageModelCapabilities | None, size: str) -> str:
    standard_sizes = capabilities.standard_sizes if capabilities is not None else STANDARD_GPT_IMAGE_SIZES
    if capabilities is not None and accepts_size(capabilities, size):
        return size
    if capabilities is None and str(size).strip().lower() in standard_sizes:
        return size
    return select_nearest_fallback_size(str(size), standard_sizes) or standard_sizes[0]


def _warn_unknown_image_model(model: str, operation: str) -> None:
    if model in _WARNED_UNKNOWN_IMAGE_MODELS:
        return
    _WARNED_UNKNOWN_IMAGE_MODELS.add(model)
    log_event(
        logging.WARNING,
        "image_model_capabilities_unknown",
        "Image-модель вне таблицы возможностей: запрос отправляется с минимальным набором параметров.",
        model=model,
        operation=operation,
        known_families=sorted(IMAGE_MODEL_CAPABILITIES),
    )


def build_images_request(
    *,
    operation: str,
    model: str,
    prompt: str,
    size: str,
    quality: str,
    output_format: str = "png",
    background: str | None = None,
    input_fidelity: str | None = None,
    image: Any = None,
) -> dict[str, Any]:
    """One ``images.generate`` / ``images.edit`` payload, holding only what ``model`` accepts.

    ``operation`` is ``"generate"`` or ``"edit"``. A requested value the model does not
    accept is left out rather than sent and stripped later by error text; the size is moved
    to the nearest size the model accepts.
    """

    if operation not in {"generate", "edit"}:
        raise ValueError(f"Unknown Images API operation: {operation}")
    capabilities = resolve_image_model_capabilities(model)
    payload: dict[str, Any] = {"model": api_model_id(model)}
    if operation == "edit":
        payload["image"] = image
    payload["prompt"] = prompt
    payload["size"] = _coerce_size(capabilities, size)
    payload["output_format"] = output_format
    if capabilities is None:
        _warn_unknown_image_model(api_model_id(model), operation)
        payload["quality"] = quality
        return payload
    if quality in capabilities.quality_values:
        payload["quality"] = quality
    if background is not None and background in capabilities.background_values:
        payload["background"] = background
    if operation == "edit" and input_fidelity is not None and capabilities.accepts_input_fidelity:
        payload["input_fidelity"] = input_fidelity
    if capabilities.accepts_response_format:
        payload["response_format"] = "b64_json"
    return payload
