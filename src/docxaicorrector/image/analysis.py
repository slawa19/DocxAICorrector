import base64
from dataclasses import dataclass, replace
from io import BytesIO
import logging
import unicodedata

from PIL import Image, ImageFilter, ImageOps

from docxaicorrector.image.model_capabilities import api_model_id
from docxaicorrector.image.prompts import load_image_prompt_registry
from docxaicorrector.image.shared import (
    call_responses_create_with_retry,
    clamp_score,
    detect_image_mime_type,
    extract_model_response_error_code,
    extract_response_text,
    is_retryable_error,
    parse_json_object,
)
from docxaicorrector.core.logger import log_event
from docxaicorrector.core.model_accounting import STAGE_IMAGE_ANALYSIS
from docxaicorrector.core.models import ImageAnalysisResult
from docxaicorrector.image.pipeline_policy import MODEL_SAFE_ROUTE_ADVISORY_PREFIX


VISION_ANALYSIS_TIMEOUT_SECONDS = 45.0
VISION_ANALYSIS_MAX_RETRIES = 2
# The image types and routes the analysis prompt offers the model (spec 062 FR-008).
# Downstream routing keys on these exact values (bypass set below, reconstruction on
# "table"), so the prompt names them instead of leaving the model to invent its own.
ANALYSIS_IMAGE_TYPES: tuple[str, ...] = (
    "diagram",
    "table",
    "chart",
    "infographic",
    "mindmap",
    "screenshot",
    "photo",
    "mixed_or_ambiguous",
)
# The types the prompt calls redrawable ("`semantic_redraw_allowed`: true only for
# diagram/table/chart/infographic/mindmap ..."). A model's ``safe_mode`` route on one of them
# is advisory in the semantic modes (spec 062 routing guard); on any other type it stays hard.
REDRAWABLE_IMAGE_TYPES: frozenset[str] = frozenset({"diagram", "table", "chart", "infographic", "mindmap"})
FALLBACK_IMAGE_TYPE = "mixed_or_ambiguous"
ANALYSIS_ROUTES: tuple[str, ...] = (
    "safe_mode",
    "semantic_redraw_direct",
    "semantic_redraw_structured",
    "deterministic_reconstruction",
)
_REDRAW_RENDER_STRATEGIES: frozenset[str] = frozenset(route for route in ANALYSIS_ROUTES if route != "safe_mode")
# Text-density thresholds from image-pipeline tuning. Crossing them is ADVISORY
# (spec 062 FR-011/FR-012): the analysis records it in ``fallback_reason`` and the
# semantic modes still attempt a redraw; ``render_strategy`` is never overwritten,
# so dense tables keep the deterministic-reconstruction route with real fonts.
DENSE_TEXT_BYPASS_THRESHOLD = 18
NON_LATIN_DENSE_TEXT_BYPASS_THRESHOLD = 12
HEURISTIC_WHITE_RATIO_THRESHOLD = 0.55
HEURISTIC_EDGE_RATIO_THRESHOLD = 0.06
HEURISTIC_BRIGHT_RATIO_THRESHOLD = 0.82
HEURISTIC_COLORFUL_RATIO_THRESHOLD = 0.12

# --- Decompression-bomb / pixel-budget guard (finding F8) --------------------
# The raster decode paths here and in image.generation previously called
# Image.open(...).load() with no upper bound, so an accidentally or maliciously
# huge image (a "decompression bomb") could exhaust memory before any check ran,
# and a real DecompressionBombError would be swallowed by the broad
# `except Exception`. We inspect the header (Image.open(...).size — no .load(),
# no pixel decode) and reject BEFORE decoding when the reported geometry exceeds
# a conservative budget. Constants are named so they are easy to tune.
MAX_IMAGE_DIMENSION_PX = 12000
MAX_IMAGE_MEGAPIXELS = 50.0
# Upper bound on the decoded raster; Pillow expands to at most 4 bytes/pixel
# (RGBA). 50 MP * 4 bytes ~= 200 MiB, so 256 MiB leaves conservative headroom.
MAX_DECODED_IMAGE_BYTES = 256 * 1024 * 1024

# Upper bound on a base64-encoded image payload BEFORE it is decoded (round-5
# finding 5). ``base64.b64decode`` allocates ~3/4 of the encoded length as raw
# compressed-file bytes, and that file is then handed to Pillow. A provider that
# returns a malicious/degenerate payload would otherwise force that allocation
# before any pixel-budget gate could run. 64 MiB of base64 decodes to ~48 MiB of
# compressed image bytes — far above any legitimate provider output (a few MB)
# while keeping the pre-decode allocation bounded.
MAX_ENCODED_IMAGE_BYTES = 64 * 1024 * 1024


def encoded_image_within_byte_budget(encoded_payload: str | bytes, *, stage: str) -> bool:
    """Return True when a base64 image payload is small enough to decode.

    Checked BEFORE ``base64.b64decode`` so an oversized encoded payload is
    rejected without allocating its decoded bytes. On rejection a structured
    WARNING is logged and False is returned so the caller can degrade safely
    (skip / keep the original) instead of decoding it.
    """
    encoded_length = len(encoded_payload)
    if encoded_length > MAX_ENCODED_IMAGE_BYTES:
        log_event(
            logging.WARNING,
            "image_encoded_byte_budget_exceeded",
            "Base64 image payload превышает byte budget; отклоняю без декодирования.",
            stage=stage,
            encoded_length=encoded_length,
            max_encoded_bytes=MAX_ENCODED_IMAGE_BYTES,
        )
        return False
    return True


def image_within_pixel_budget(image_bytes: bytes, *, stage: str) -> bool:
    """Return True when the image header is within the decode budget.

    Reads only the header (``Image.open(...).size`` — no ``.load()``, so no pixel
    decode) and rejects an oversized image BEFORE Pillow allocates the full
    raster. On rejection a structured WARNING is logged and False is returned so
    the caller can skip the image instead of decoding it. A real
    ``DecompressionBombError`` raised while reading the header is logged
    (surfaced), never silently swallowed. Header bytes that are simply
    corrupt/unsupported return True so the caller's own decode+except path keeps
    its prior behaviour.
    """
    try:
        with Image.open(BytesIO(image_bytes)) as header_image:
            width, height = header_image.size
    except Image.DecompressionBombError as exc:
        log_event(
            logging.WARNING,
            "image_pixel_budget_decompression_bomb",
            "Pillow пометил изображение как decompression bomb при чтении заголовка; изображение пропущено без декодирования.",
            stage=stage,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        return False
    except Exception:
        # Header unreadable for an unrelated reason (corrupt/unsupported bytes).
        # Defer to the caller's existing decode+except handling.
        return True

    megapixels = (width * height) / 1_000_000.0
    estimated_decoded_bytes = width * height * 4
    if (
        width > MAX_IMAGE_DIMENSION_PX
        or height > MAX_IMAGE_DIMENSION_PX
        or megapixels > MAX_IMAGE_MEGAPIXELS
        or estimated_decoded_bytes > MAX_DECODED_IMAGE_BYTES
    ):
        log_event(
            logging.WARNING,
            "image_pixel_budget_exceeded",
            "Изображение превышает pixel budget; пропускаю без полного декодирования.",
            stage=stage,
            width=width,
            height=height,
            megapixels=round(megapixels, 2),
            estimated_decoded_bytes=estimated_decoded_bytes,
            max_dimension_px=MAX_IMAGE_DIMENSION_PX,
            max_megapixels=MAX_IMAGE_MEGAPIXELS,
            max_decoded_bytes=MAX_DECODED_IMAGE_BYTES,
        )
        return False
    return True


def _read_image_header_geometry(image_bytes: bytes) -> tuple[int, int] | None:
    """Return ``(width, height)`` read from the header only (no ``.load()``).

    Returns None when the header cannot be read (corrupt/unsupported bytes or a
    decompression bomb); callers use this purely for aggregate accounting AFTER
    the per-image :func:`image_within_pixel_budget` gate has already run, so a
    None here simply means "do not accumulate" rather than "reject".
    """
    try:
        with Image.open(BytesIO(image_bytes)) as header_image:
            width, height = header_image.size
    except Exception:
        return None
    return width, height


# --- Per-document aggregate pixel budget (finding F8) -------------------------
# The per-image guard above bounds any SINGLE image, but a document with many
# large-but-individually-legal images could still force an unbounded total
# decode. ``ImageBudget`` is a small accumulator threaded through the
# per-document image loop that caps the TOTAL decoded pixels/bytes for one
# document. Once the running total would exceed the cap, further images are
# skipped with a WARNING (never silently dropped). Defaults are generous
# multiples of the per-image cap so normal documents are unaffected.
DEFAULT_DOCUMENT_MAX_DECODED_MEGAPIXELS = 400.0
DEFAULT_DOCUMENT_MAX_DECODED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass
class ImageBudget:
    """Aggregate decoded-pixel budget for a single document's image loop."""

    max_total_megapixels: float = DEFAULT_DOCUMENT_MAX_DECODED_MEGAPIXELS
    max_total_decoded_bytes: int = DEFAULT_DOCUMENT_MAX_DECODED_BYTES
    used_megapixels: float = 0.0
    used_decoded_bytes: int = 0
    admitted_images: int = 0
    skipped_images: int = 0

    def admit(self, image_bytes: bytes, *, stage: str) -> bool:
        """Return True if the image fits BOTH the per-image and document budgets.

        Applies the header-only per-image gate first (which also surfaces a
        decompression bomb), then charges the image's decoded footprint against
        the running document total. When either check fails the image is skipped
        (a WARNING is logged) and False is returned so the caller can fall back
        to the original raster instead of decoding/transmitting the image.
        """
        if not image_within_pixel_budget(image_bytes, stage=stage):
            self.skipped_images += 1
            return False
        return self.charge(image_bytes, stage=stage)

    def charge(self, image_bytes: bytes, *, stage: str) -> bool:
        """Charge an already per-image-gated raster against the document total.

        Unlike :meth:`admit` this does NOT re-run the per-image pixel gate — the
        caller must have applied it (or ``image_within_pixel_budget``) already.
        Used for GENERATED (provider-returned) rasters so they charge the SAME
        per-document budget as embedded images (round-5 finding 5): a single
        shared budget across embedded + generated. Returns False (and logs a
        WARNING) when adding this image would exceed the document budget, so the
        caller can degrade to the original instead of emitting the generated image.
        """
        geometry = _read_image_header_geometry(image_bytes)
        if geometry is None:
            # Header unreadable for an unrelated reason; the per-image gate has
            # already deferred to the caller's decode+except path. Do not charge
            # the aggregate for bytes we could not measure.
            return True

        width, height = geometry
        megapixels = (width * height) / 1_000_000.0
        decoded_bytes = width * height * 4
        projected_megapixels = self.used_megapixels + megapixels
        projected_bytes = self.used_decoded_bytes + decoded_bytes
        if (
            projected_megapixels > self.max_total_megapixels
            or projected_bytes > self.max_total_decoded_bytes
        ):
            self.skipped_images += 1
            log_event(
                logging.WARNING,
                "image_document_pixel_budget_exceeded",
                "Документ превысил суммарный pixel budget; дальнейшие изображения пропускаются без декодирования.",
                stage=stage,
                width=width,
                height=height,
                image_megapixels=round(megapixels, 2),
                used_megapixels=round(self.used_megapixels, 2),
                used_decoded_bytes=self.used_decoded_bytes,
                max_total_megapixels=self.max_total_megapixels,
                max_total_decoded_bytes=self.max_total_decoded_bytes,
            )
            return False

        self.used_megapixels = projected_megapixels
        self.used_decoded_bytes = projected_bytes
        self.admitted_images += 1
        return True


def _build_over_budget_analysis_result() -> ImageAnalysisResult:
    """Safe, degraded analysis for an image that exceeds the decode budget.

    Returned WITHOUT decoding or base64-encoding the image, so an oversized /
    decompression-bomb payload is never handed to the vision API. The image is
    routed to safe mode and kept as-is downstream.
    """
    return ImageAnalysisResult(
        image_type="mixed_or_ambiguous",
        image_subtype=None,
        contains_text=False,
        semantic_redraw_allowed=False,
        confidence=0.0,
        structured_parse_confidence=0.0,
        prompt_key="mixed_or_ambiguous_fallback",
        render_strategy="safe_mode",
        structure_summary="Image exceeds the decode pixel budget; kept in safe mode without decoding.",
        extracted_labels=[],
        fallback_reason="pixel_budget_exceeded",
    )


def analyze_image(
    image_bytes: bytes,
    *,
    model: str,
    mime_type: str | None = None,
    client=None,
    enable_vision: bool = True,
    dense_text_bypass_threshold: int = DENSE_TEXT_BYPASS_THRESHOLD,
    non_latin_text_bypass_threshold: int = NON_LATIN_DENSE_TEXT_BYPASS_THRESHOLD,
    budget=None,
) -> ImageAnalysisResult:
    # Mandatory pixel-budget gate BEFORE any decode / base64 / vision upload:
    # an over-budget or decompression-bomb image is skipped here so it is never
    # base64-encoded or sent to the vision API (finding F8).
    if not image_within_pixel_budget(image_bytes, stage="image_analysis"):
        log_event(
            logging.WARNING,
            "image_analysis_skipped_over_budget",
            "Изображение превышает pixel budget; анализ пропущен без декодирования и без отправки в vision API.",
            model=model,
            mime_type=mime_type,
        )
        return _build_over_budget_analysis_result()

    detected_mime_type = mime_type or detect_image_mime_type(image_bytes)
    visual_features = _extract_visual_features(image_bytes)
    heuristic_result = _build_heuristic_analysis(detected_mime_type, visual_features)

    if not enable_vision or client is None or detected_mime_type is None:
        return heuristic_result

    try:
        vision_result = _extract_vision_analysis(
            client=client,
            image_bytes=image_bytes,
            mime_type=detected_mime_type,
            model=model,
            heuristic_result=heuristic_result,
            budget=budget,
        )
    except Exception as exc:
        log_event(
            logging.WARNING,
            "image_analysis_vision_fallback_after_error",
            "Vision-анализ изображения завершился ошибкой; использую heuristic fallback.",
            model=model,
            mime_type=detected_mime_type,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            error_code=extract_model_response_error_code(exc),
            response_stage="vision_analysis",
        )
        return heuristic_result

    return _merge_analysis_results(
        heuristic_result,
        vision_result,
        dense_text_bypass_threshold=dense_text_bypass_threshold,
        non_latin_text_bypass_threshold=non_latin_text_bypass_threshold,
    )


def _build_heuristic_analysis(
    detected_mime_type: str | None,
    visual_features: dict[str, float] | None,
) -> ImageAnalysisResult:
    if detected_mime_type == "image/jpeg":
        if _looks_like_infographic(visual_features):
            return ImageAnalysisResult(
                image_type="infographic",
                image_subtype="jpeg_infographic_like",
                contains_text=True,
                semantic_redraw_allowed=True,
                confidence=0.76,
                structured_parse_confidence=0.64,
                prompt_key="infographic_semantic_redraw",
                render_strategy="deterministic_reconstruction",
                structure_summary="Editorial infographic-like image with bright background, colored accents, and dense visual layout.",
                extracted_labels=[],
            )
        if _looks_like_structured_diagram(visual_features):
            return ImageAnalysisResult(
                image_type="diagram",
                image_subtype="jpeg_diagram_like",
                contains_text=True,
                semantic_redraw_allowed=True,
                confidence=0.72,
                structured_parse_confidence=0.62,
                prompt_key="diagram_semantic_redraw",
                render_strategy="deterministic_reconstruction",
                # Structural fallback only (spec 062 FR-009, Constitution VII): the
                # heuristic knows the format and the visual class, never the content,
                # so it must not describe blocks, counts or connectors it never saw.
                structure_summary="JPEG image with diagram-like visual features; structure not analysed.",
                extracted_labels=[],
            )
        return ImageAnalysisResult(
            image_type="photo",
            image_subtype=None,
            contains_text=False,
            semantic_redraw_allowed=False,
            confidence=0.78,
            structured_parse_confidence=0.1,
            prompt_key="photo_safe_fallback",
            render_strategy="safe_mode",
            structure_summary="Photo-like image; preserve original composition.",
            extracted_labels=[],
            fallback_reason="photo_safe_only",
        )

    if detected_mime_type in {"image/png", "image/gif", "image/bmp"}:
        if _looks_like_infographic(visual_features):
            return ImageAnalysisResult(
                image_type="infographic",
                image_subtype="editorial_infographic_like",
                contains_text=True,
                semantic_redraw_allowed=True,
                confidence=0.86,
                structured_parse_confidence=0.7,
                prompt_key="infographic_semantic_redraw",
                render_strategy="deterministic_reconstruction",
                structure_summary="Infographic-like image with bright background, multiple content zones, and colored emphasis.",
                extracted_labels=[],
            )
        if _looks_like_screenshot(visual_features):
            return ImageAnalysisResult(
                image_type="screenshot",
                image_subtype="ui_screenshot_like",
                contains_text=True,
                semantic_redraw_allowed=False,
                confidence=0.79,
                structured_parse_confidence=0.18,
                prompt_key="screenshot_safe_fallback",
                render_strategy="safe_mode",
                structure_summary="Interface or screen-like raster image; preserve original layout and text safely.",
                extracted_labels=[],
                fallback_reason="screenshot_safe_only",
            )
        if _looks_like_structured_diagram(visual_features):
            return ImageAnalysisResult(
                image_type="diagram",
                image_subtype=None,
                contains_text=True,
                semantic_redraw_allowed=True,
                confidence=0.81,
                structured_parse_confidence=0.74,
                prompt_key="diagram_semantic_redraw",
                render_strategy="deterministic_reconstruction",
                structure_summary="Diagram-like image with labels and layout relationships.",
                extracted_labels=[],
            )
        return ImageAnalysisResult(
            image_type="mixed_or_ambiguous",
            image_subtype=None,
            contains_text=False,
            semantic_redraw_allowed=False,
            confidence=0.45,
            structured_parse_confidence=0.12,
            prompt_key="mixed_or_ambiguous_fallback",
            render_strategy="safe_mode",
            structure_summary="PNG/GIF/BMP image without strong diagram or screenshot signals; preserve original appearance conservatively.",
            extracted_labels=[],
            fallback_reason="ambiguous_raster_safe_only",
        )

    return ImageAnalysisResult(
        image_type="mixed_or_ambiguous",
        image_subtype=None,
        contains_text=False,
        semantic_redraw_allowed=False,
        confidence=0.4,
        structured_parse_confidence=0.0,
        prompt_key="mixed_or_ambiguous_fallback",
        render_strategy="safe_mode",
        structure_summary="Ambiguous image type; keep original appearance.",
        extracted_labels=[],
        fallback_reason="unreadable_or_unsupported_image",
    )


TEXT_COPY_RULE = (
    'Copy all text exactly in its original script and language (any language); never transliterate; '
    'write "unreadable" for illegible text.'
)


def valid_prompt_keys() -> tuple[str, ...]:
    """Prompt keys the registry defines, in registry order (spec 062 FR-008/FR-022).

    Built from ``image_prompt_registry.toml`` so the analysis prompt and the parser
    cannot drift from the profiles that actually exist.
    """
    return tuple(load_image_prompt_registry()["prompts"])


def build_vision_analysis_user_prompt() -> str:
    image_types = ",".join(f'"{image_type}"' for image_type in ANALYSIS_IMAGE_TYPES)
    routes = ",".join(f'"{route}"' for route in ANALYSIS_ROUTES)
    prompt_keys = ",".join(f'"{prompt_key}"' for prompt_key in valid_prompt_keys())
    return (
        "Return one JSON object with exactly these keys. "
        f"`image_type`: one of {image_types}. "
        "`image_subtype`: short text or null. "
        "`contains_text`: true/false. "
        "`semantic_redraw_allowed`: true only for diagram/table/chart/infographic/mindmap whose content can be redrawn "
        "without losing information. "
        "`confidence`, `structured_parse_confidence`: numbers 0..1. "
        f"`prompt_key`: one of {prompt_keys}, matching image_type (photo→photo_safe_fallback, "
        "screenshot→screenshot_safe_fallback, mixed_or_ambiguous→mixed_or_ambiguous_fallback). "
        f"`recommended_route`: one of {routes}. "
        "`structure_summary`: one sentence naming the element counts (blocks, rows×columns, series). "
        "`extracted_labels`: up to 12 clearly readable labels, verbatim. "
        "`text_node_count`: integer count of separate text blocks (labels, cells, captions, legend items). "
        "`extracted_text`: all readable text verbatim, in reading order. "
        "`fallback_reason`: null or a short reason. "
        f"{TEXT_COPY_RULE}"
        # Spec 062 FR-024 (D2): the sentence "If text is too dense for faithful redraw, set
        # recommended_route to safe_mode." is gone. The Cyrillic gate FR-005 passed for the
        # structured mode on 2026-11-07, and neither density nor script sends an image to
        # safe_mode by prose; the numeric bypass thresholds stay advisory (FR-011/FR-012).
    )


def _extract_vision_analysis(
    *,
    client,
    image_bytes: bytes,
    mime_type: str,
    model: str,
    heuristic_result: ImageAnalysisResult,
    budget=None,
) -> ImageAnalysisResult:
    response = call_responses_create_with_retry(
        client,
        {
            "model": api_model_id(model),
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                # Spec 062 FR-024 (D2): no sentence here sends dense or
                                # non-Latin images to safe_mode any more.
                                "You analyze document images conservatively for a DOCX editing pipeline. Return strict JSON only. "
                                "Screenshots and photos should usually stay in safe_mode unless the image is clearly a structured diagram or infographic."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": build_vision_analysis_user_prompt(),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}",
                        },
                    ],
                },
            ],
            "timeout": VISION_ANALYSIS_TIMEOUT_SECONDS,
        },
        max_retries=VISION_ANALYSIS_MAX_RETRIES,
        retryable_error_predicate=is_retryable_error,
        budget=budget,
        usage_stage=STAGE_IMAGE_ANALYSIS,
    )
    payload = parse_json_object(
        extract_response_text(
            response,
            empty_message="Vision analysis returned empty output.",
            incomplete_message="Vision analysis returned incomplete output.",
            non_completed_message="Vision analysis returned non-completed output.",
        ),
        empty_message="Vision analysis returned empty output.",
        no_json_message="Vision analysis did not return JSON.",
    )
    return _coerce_vision_analysis_payload(payload, heuristic_result)


def _coerce_vision_analysis_payload(
    payload: dict[str, object],
    heuristic_result: ImageAnalysisResult,
) -> ImageAnalysisResult:
    extracted_labels = _coerce_extracted_labels(payload.get("extracted_labels"))
    extracted_text = _coerce_extracted_text(payload.get("extracted_text"))
    text_node_count = _coerce_non_negative_int(payload.get("text_node_count"))
    image_type = _coerce_image_type(payload.get("image_type"), heuristic_result.image_type)
    render_strategy, force_safe_mode = _normalize_render_strategy(
        payload.get("recommended_route") or payload.get("render_strategy"),
        heuristic_result.render_strategy,
    )
    semantic_redraw_allowed = _coerce_bool(
        payload.get("semantic_redraw_allowed"),
        heuristic_result.semantic_redraw_allowed,
    )
    fallback_reason = _coerce_optional_string(payload.get("fallback_reason"), heuristic_result.fallback_reason)
    if force_safe_mode:
        semantic_redraw_allowed = False
        if image_type in REDRAWABLE_IMAGE_TYPES:
            # Spec 062 routing guard (image comparison 2026-11-07, finding 5): the model's
            # safe_mode on a redrawable type is ADVISORY, through the same path as the
            # dense_* bypasses (``pipeline_policy._ADVISORY_SAFE_FALLBACK_PREFIXES``): the
            # semantic modes restore the redraw in ``build_generation_analysis``; ``safe``
            # and ``no_change`` are untouched. Keyed on the type and the route only: terra
            # and sol sent ``semantic_redraw_allowed: false`` together with the route in all
            # four measured cases, so a guard that also required ``true`` would never fire.
            # ``render_strategy`` is the one a ``<type>_semantic_redraw`` route would give:
            # the heuristic's redraw strategy when it has one, otherwise reconstruction,
            # so a table keeps the PIL route (FR-012). Acceptance review 2026-11-07,
            # finding 2: taking the heuristic's value as is gave ``safe_mode`` whenever the
            # heuristic had typed the raster table a screenshot, photo or ambiguous image,
            # and the restored redraw then skipped reconstruction for the generative path.
            model_reason = _coerce_optional_string(payload.get("fallback_reason"), None) or "unspecified"
            fallback_reason = f"{MODEL_SAFE_ROUTE_ADVISORY_PREFIX}{model_reason}"
            render_strategy = (
                heuristic_result.render_strategy
                if heuristic_result.render_strategy in _REDRAW_RENDER_STRATEGIES
                else "deterministic_reconstruction"
            )
    contains_text = _coerce_bool(payload.get("contains_text"), heuristic_result.contains_text)
    prompt_key = _coerce_non_empty_string(payload.get("prompt_key"), heuristic_result.prompt_key)
    return ImageAnalysisResult(
        image_type=image_type,
        image_subtype=_coerce_optional_string(payload.get("image_subtype"), heuristic_result.image_subtype),
        contains_text=contains_text or bool(extracted_labels) or bool(extracted_text),
        semantic_redraw_allowed=semantic_redraw_allowed,
        confidence=_clamp_score(payload.get("confidence", heuristic_result.confidence)),
        structured_parse_confidence=_clamp_score(payload.get("structured_parse_confidence", heuristic_result.structured_parse_confidence)),
        prompt_key=prompt_key if prompt_key in valid_prompt_keys() else heuristic_result.prompt_key,
        render_strategy=render_strategy,
        structure_summary=_coerce_non_empty_string(payload.get("structure_summary"), heuristic_result.structure_summary),
        extracted_labels=extracted_labels or heuristic_result.extracted_labels,
        text_node_count=text_node_count,
        extracted_text=extracted_text,
        fallback_reason=fallback_reason,
    )


def _coerce_image_type(value: object, fallback: str) -> str:
    """The model's ``image_type`` if the prompt offers it; ``mixed_or_ambiguous`` if not.

    Spec 062 (image comparison 2026-11-07, finding 6): ``gpt-5.4-mini`` answered ``"logo"``
    for 2 of 43 book images and the value passed through unchecked, while routing keys on
    exact members of ``ANALYSIS_IMAGE_TYPES``. A missing or empty value keeps the heuristic
    type, as before.
    """

    if not isinstance(value, str) or not value.strip():
        return fallback
    normalized = value.strip().lower()
    if normalized in ANALYSIS_IMAGE_TYPES:
        return normalized
    log_event(
        logging.WARNING,
        "image_analysis_image_type_out_of_enum",
        "Vision-анализ вернул image_type вне допустимого набора; использую mixed_or_ambiguous.",
        image_type=value.strip(),
        replacement=FALLBACK_IMAGE_TYPE,
        allowed_image_types=list(ANALYSIS_IMAGE_TYPES),
    )
    return FALLBACK_IMAGE_TYPE


def _merge_analysis_results(
    heuristic_result: ImageAnalysisResult,
    vision_result: ImageAnalysisResult,
    *,
    dense_text_bypass_threshold: int = DENSE_TEXT_BYPASS_THRESHOLD,
    non_latin_text_bypass_threshold: int = NON_LATIN_DENSE_TEXT_BYPASS_THRESHOLD,
) -> ImageAnalysisResult:
    merged = ImageAnalysisResult(
        image_type=vision_result.image_type or heuristic_result.image_type,
        image_subtype=vision_result.image_subtype or heuristic_result.image_subtype,
        contains_text=heuristic_result.contains_text or vision_result.contains_text or bool(vision_result.extracted_labels),
        semantic_redraw_allowed=vision_result.semantic_redraw_allowed,
        confidence=_clamp_score((heuristic_result.confidence + vision_result.confidence) / 2.0),
        structured_parse_confidence=_clamp_score((heuristic_result.structured_parse_confidence + vision_result.structured_parse_confidence) / 2.0),
        prompt_key=vision_result.prompt_key or heuristic_result.prompt_key,
        render_strategy=vision_result.render_strategy or heuristic_result.render_strategy,
        structure_summary=vision_result.structure_summary or heuristic_result.structure_summary,
        extracted_labels=vision_result.extracted_labels or heuristic_result.extracted_labels,
        text_node_count=(
            vision_result.text_node_count
            if vision_result.text_node_count is not None
            else heuristic_result.text_node_count
        ),
        extracted_text=vision_result.extracted_text or heuristic_result.extracted_text,
        fallback_reason=vision_result.fallback_reason or heuristic_result.fallback_reason,
    )
    return _apply_routing_overrides(
        merged,
        dense_text_bypass_threshold=dense_text_bypass_threshold,
        non_latin_text_bypass_threshold=non_latin_text_bypass_threshold,
    )


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        parsed = int(value)
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value)
    elif isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
    else:
        return None
    return max(0, parsed)


def _coerce_extracted_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _coerce_extracted_labels(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = value
    else:
        return []

    extracted_labels: list[str] = []
    for item in candidates:
        normalized = str(item).strip()
        if not normalized:
            continue
        extracted_labels.append(normalized)
        if len(extracted_labels) >= 12:
            break
    return extracted_labels


def _coerce_non_empty_string(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip()
    return normalized or fallback


def _coerce_optional_string(value: object, fallback: str | None) -> str | None:
    if not isinstance(value, str):
        return fallback
    normalized = value.strip()
    return normalized or fallback


def _coerce_bool(value: object, fallback: bool) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return bool(value)


def _apply_routing_overrides(
    result: ImageAnalysisResult,
    *,
    dense_text_bypass_threshold: int,
    non_latin_text_bypass_threshold: int,
) -> ImageAnalysisResult:
    """Record an ADVISORY dense-text bypass without rerouting the image.

    Spec 062 FR-011/FR-012: the bypass is written to ``fallback_reason`` (with the
    advisory prefixes ``pipeline_policy`` recognises) and clears
    ``semantic_redraw_allowed``, which the semantic modes restore through
    ``build_generation_analysis``. ``render_strategy`` keeps the analysis value: before
    this change it was overwritten with ``safe_mode``, which silently took the densest
    tables off the deterministic-reconstruction route that renders text with real fonts.
    """
    if (
        result.text_node_count is not None
        and result.text_node_count >= dense_text_bypass_threshold
        and result.semantic_redraw_allowed
        and result.image_type in {"infographic", "mixed_or_ambiguous", "chart", "table"}
    ):
        return replace(
            result,
            semantic_redraw_allowed=False,
            fallback_reason=f"dense_text_bypass:{result.text_node_count}_nodes",
        )
    if (
        result.text_node_count is not None
        and result.text_node_count >= non_latin_text_bypass_threshold
        and result.semantic_redraw_allowed
        and result.image_type in {"infographic", "mixed_or_ambiguous", "chart", "table"}
        and _contains_non_latin_text(result.extracted_text, result.extracted_labels)
    ):
        return replace(
            result,
            semantic_redraw_allowed=False,
            fallback_reason=f"dense_non_latin_text_bypass:{result.text_node_count}_nodes",
        )
    return result


def _normalize_render_strategy(route_hint: object, fallback_strategy: str) -> tuple[str, bool]:
    route = str(route_hint).strip().lower() if route_hint is not None else ""
    if route in {"", "none"}:
        return fallback_strategy, False
    if route in {"bypass", "safe", "safe_mode"}:
        return "safe_mode", True
    if route in {"semantic_parse", "structured_parse", "scene_graph", "scene_graph_reconstruction"}:
        return "deterministic_reconstruction", False
    if route == "semantic_redraw":
        return "deterministic_reconstruction", False
    if route.endswith("_semantic_redraw"):
        if fallback_strategy == "deterministic_reconstruction":
            return "deterministic_reconstruction", False
        if fallback_strategy in {"semantic_redraw_direct", "semantic_redraw_structured"}:
            return fallback_strategy, False
        return "deterministic_reconstruction", False
    if fallback_strategy == "deterministic_reconstruction" and route in {
        "deterministic_reconstruction",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }:
        return "deterministic_reconstruction", False
    if route in ANALYSIS_ROUTES:
        return route, False
    # Spec 062 FR-008 (D8, W9): an unknown route no longer passes through raw into
    # ``render_strategy``, and the model-name branch (``gpt-…``, the archived
    # ``recommended_route: "gpt-image-1"`` contract) is gone — anything outside the
    # routes the prompt offers keeps the heuristic strategy.
    return fallback_strategy, False


def _extract_visual_features(image_bytes: bytes) -> dict[str, float] | None:
    if not image_within_pixel_budget(image_bytes, stage="image_visual_feature_extraction"):
        return None
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            rgb_image = ImageOps.exif_transpose(source_image).convert("RGB")
    except Exception:
        return None

    if rgb_image.width < 80 or rgb_image.height < 80:
        return None

    preview = rgb_image.resize((min(256, rgb_image.width), min(256, rgb_image.height)))
    pixel_count = max(1, preview.width * preview.height)
    preview_bytes = preview.tobytes()

    white_pixels = 0
    low_saturation_pixels = 0
    dark_pixels = 0
    colorful_pixels = 0
    bright_pixels = 0
    for index in range(0, len(preview_bytes), 3):
        red = preview_bytes[index]
        green = preview_bytes[index + 1]
        blue = preview_bytes[index + 2]
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        channel_delta = maximum - minimum
        if maximum >= 245 and minimum >= 235:
            white_pixels += 1
        if channel_delta <= 24:
            low_saturation_pixels += 1
        if maximum <= 72:
            dark_pixels += 1
        if maximum >= 1 and channel_delta / maximum >= 0.25:
            colorful_pixels += 1
        if maximum >= 204:
            bright_pixels += 1

    edge_map = preview.convert("L").filter(ImageFilter.FIND_EDGES)
    strong_edges = sum(pixel >= 40 for pixel in edge_map.tobytes())

    white_ratio = white_pixels / pixel_count
    low_saturation_ratio = low_saturation_pixels / pixel_count
    dark_ratio = dark_pixels / pixel_count
    edge_ratio = strong_edges / pixel_count
    colorful_ratio = colorful_pixels / pixel_count
    bright_ratio = bright_pixels / pixel_count

    return {
        "white_ratio": white_ratio,
        "low_saturation_ratio": low_saturation_ratio,
        "dark_ratio": dark_ratio,
        "edge_ratio": edge_ratio,
        "colorful_ratio": colorful_ratio,
        "bright_ratio": bright_ratio,
    }


def _looks_like_structured_diagram(visual_features: dict[str, float] | None) -> bool:
    if not visual_features:
        return False

    white_ratio = visual_features["white_ratio"]
    low_saturation_ratio = visual_features["low_saturation_ratio"]
    dark_ratio = visual_features["dark_ratio"]
    edge_ratio = visual_features["edge_ratio"]

    if white_ratio >= HEURISTIC_WHITE_RATIO_THRESHOLD and edge_ratio >= HEURISTIC_EDGE_RATIO_THRESHOLD:
        return True
    if white_ratio >= 0.45 and low_saturation_ratio >= 0.7 and edge_ratio >= 0.055 and dark_ratio >= 0.03:
        return True
    if white_ratio >= 0.32 and low_saturation_ratio >= 0.88 and edge_ratio >= 0.12 and dark_ratio >= 0.03:
        return True
    return False


def _looks_like_infographic(visual_features: dict[str, float] | None) -> bool:
    if not visual_features:
        return False

    return (
        visual_features["bright_ratio"] >= HEURISTIC_BRIGHT_RATIO_THRESHOLD
        and visual_features["colorful_ratio"] >= HEURISTIC_COLORFUL_RATIO_THRESHOLD
        and visual_features["edge_ratio"] >= 0.08
        and visual_features["dark_ratio"] <= 0.05
    )


def _looks_like_screenshot(visual_features: dict[str, float] | None) -> bool:
    if not visual_features:
        return False

    return (
        visual_features["bright_ratio"] >= 0.45
        and visual_features["white_ratio"] >= 0.18
        and visual_features["white_ratio"] <= 0.9
        and visual_features["edge_ratio"] >= 0.01
        and visual_features["edge_ratio"] <= 0.16
        and visual_features["colorful_ratio"] >= 0.01
        and visual_features["colorful_ratio"] <= 0.2
        and visual_features["dark_ratio"] <= 0.2
    )


def _clamp_score(value: object) -> float:
    return clamp_score(value)


def _contains_non_latin_text(extracted_text: str, extracted_labels: list[str]) -> bool:
    """True when the text holds a letter outside the Latin script (spec 062 FR-011, D9).

    Keyed on the Unicode character name, not on ``ord > 127``: é, ü, ß, ł, ñ are Latin
    letters of supported languages and must not trip the non-Latin bypass.
    """
    joined_text = " ".join([extracted_text, *extracted_labels])
    return any(
        character.isalpha() and not unicodedata.name(character, "").startswith("LATIN")
        for character in joined_text
    )
