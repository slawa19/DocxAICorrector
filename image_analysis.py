import base64
import json
import time
from dataclasses import replace
from io import BytesIO

from PIL import Image, ImageFile, ImageFilter, ImageOps

from generation import is_retryable_error
from models import ImageAnalysisResult


ImageFile.LOAD_TRUNCATED_IMAGES = True
VISION_ANALYSIS_TIMEOUT_SECONDS = 45.0
VISION_ANALYSIS_MAX_RETRIES = 2
DENSE_TEXT_BYPASS_THRESHOLD = 18  # text nodes at which image regeneration loses too much fidelity
NON_LATIN_DENSE_TEXT_BYPASS_THRESHOLD = 12


def analyze_image(
    image_bytes: bytes,
    *,
    model: str,
    mime_type: str | None = None,
    client=None,
    enable_vision: bool = True,
    dense_text_bypass_threshold: int = DENSE_TEXT_BYPASS_THRESHOLD,
    non_latin_text_bypass_threshold: int = NON_LATIN_DENSE_TEXT_BYPASS_THRESHOLD,
) -> ImageAnalysisResult:
    detected_mime_type = mime_type or _detect_mime_type(image_bytes)
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
        )
    except Exception:
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
                structure_summary="JPEG image with strong diagram-like layout, edges, and light background.",
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


def _extract_vision_analysis(
    *,
    client,
    image_bytes: bytes,
    mime_type: str,
    model: str,
    heuristic_result: ImageAnalysisResult,
) -> ImageAnalysisResult:
    response = _call_responses_create_with_retry(
        client,
        {
            "model": model or "gpt-4.1",
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You analyze document images conservatively for a DOCX editing pipeline. Return strict JSON only. "
                                    "Screenshots and photos should usually stay in safe_mode unless the image is clearly a structured diagram or infographic. "
                                    "Dense infographics, posters, and comparison charts with many text blocks, especially in Cyrillic or mixed non-Latin text, should prefer safe_mode."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Return JSON with keys: image_type, image_subtype, contains_text, semantic_redraw_allowed, confidence, "
                                "structured_parse_confidence, prompt_key, render_strategy, recommended_route, structure_summary, extracted_labels, "
                                "text_node_count, extracted_text, fallback_reason. "
                                "Populate extracted_labels only with clearly readable labels, max 12 items. Heuristic baseline: "
                                f"image_type={heuristic_result.image_type}, prompt_key={heuristic_result.prompt_key}, render_strategy={heuristic_result.render_strategy}. "
                                "Copy Cyrillic, Ukrainian, and Russian text exactly in Unicode. If text is too dense for faithful redraw, set recommended_route to safe_mode."
                            ),
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
    )
    payload = _parse_json_object(getattr(response, "output_text", ""))
    return _coerce_vision_analysis_payload(payload, heuristic_result)


def _call_responses_create_with_retry(client, request_payload: dict[str, object]):
    current_payload = dict(request_payload)
    for attempt in range(1, VISION_ANALYSIS_MAX_RETRIES + 1):
        try:
            return client.responses.create(**current_payload)
        except TypeError as exc:
            if "timeout" in str(exc) and "timeout" in current_payload:
                current_payload.pop("timeout", None)
                continue
            raise
        except Exception as exc:
            if attempt >= VISION_ANALYSIS_MAX_RETRIES or not is_retryable_error(exc):
                raise
            time.sleep(min(2 ** (attempt - 1), 4))
    raise RuntimeError("Vision analysis retry loop exhausted unexpectedly.")


def _parse_json_object(raw_text: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise RuntimeError("Vision analysis returned empty output.")
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError("Vision analysis did not return JSON.")
    return json.loads(text[start : end + 1])


def _coerce_vision_analysis_payload(
    payload: dict[str, object],
    heuristic_result: ImageAnalysisResult,
) -> ImageAnalysisResult:
    extracted_labels = [str(item).strip() for item in payload.get("extracted_labels", []) if str(item).strip()][:12]
    extracted_text = _coerce_extracted_text(payload.get("extracted_text"))
    text_node_count = _coerce_non_negative_int(payload.get("text_node_count"))
    render_strategy, force_safe_mode = _normalize_render_strategy(
        payload.get("recommended_route") or payload.get("render_strategy"),
        heuristic_result.render_strategy,
    )
    semantic_redraw_allowed = bool(payload.get("semantic_redraw_allowed", heuristic_result.semantic_redraw_allowed))
    if force_safe_mode:
        semantic_redraw_allowed = False
    return ImageAnalysisResult(
        image_type=str(payload.get("image_type", heuristic_result.image_type)).strip() or heuristic_result.image_type,
        image_subtype=(
            str(payload.get("image_subtype")).strip()
            if isinstance(payload.get("image_subtype"), str) and str(payload.get("image_subtype")).strip()
            else heuristic_result.image_subtype
        ),
        contains_text=bool(payload.get("contains_text", heuristic_result.contains_text)) or bool(extracted_labels) or bool(extracted_text),
        semantic_redraw_allowed=semantic_redraw_allowed,
        confidence=_clamp_score(payload.get("confidence", heuristic_result.confidence)),
        structured_parse_confidence=_clamp_score(payload.get("structured_parse_confidence", heuristic_result.structured_parse_confidence)),
        prompt_key=str(payload.get("prompt_key", heuristic_result.prompt_key)).strip() or heuristic_result.prompt_key,
        render_strategy=render_strategy,
        structure_summary=str(payload.get("structure_summary", heuristic_result.structure_summary)).strip() or heuristic_result.structure_summary,
        extracted_labels=extracted_labels or heuristic_result.extracted_labels,
        text_node_count=text_node_count,
        extracted_text=extracted_text,
        fallback_reason=(
            str(payload.get("fallback_reason")).strip()
            if isinstance(payload.get("fallback_reason"), str) and str(payload.get("fallback_reason")).strip()
            else heuristic_result.fallback_reason
        ),
    )


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
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, parsed)


def _coerce_extracted_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _apply_routing_overrides(
    result: ImageAnalysisResult,
    *,
    dense_text_bypass_threshold: int,
    non_latin_text_bypass_threshold: int,
) -> ImageAnalysisResult:
    """Override to safe_mode when Vision detects text density too high for reliable regeneration."""
    if (
        result.text_node_count is not None
        and result.text_node_count >= dense_text_bypass_threshold
        and result.semantic_redraw_allowed
        and result.image_type in {"infographic", "mixed_or_ambiguous", "chart", "table"}
    ):
        return replace(
            result,
            render_strategy="safe_mode",
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
            render_strategy="safe_mode",
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
        "gpt-image-1",
        "semantic_redraw_direct",
        "semantic_redraw_structured",
    }:
        return "deterministic_reconstruction", False
    if route == "gpt-image-1":
        if fallback_strategy in {"semantic_redraw_direct", "semantic_redraw_structured"}:
            return fallback_strategy, False
        return "semantic_redraw_structured", False
    return str(route_hint).strip() or fallback_strategy, False


def _detect_mime_type(image_bytes: bytes) -> str | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    return None


def _extract_visual_features(image_bytes: bytes) -> dict[str, float] | None:
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

    white_pixels = 0
    low_saturation_pixels = 0
    dark_pixels = 0
    colorful_pixels = 0
    bright_pixels = 0
    for y_coord in range(preview.height):
        for x_coord in range(preview.width):
            red, green, blue = preview.getpixel((x_coord, y_coord))
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            if maximum >= 245 and minimum >= 235:
                white_pixels += 1
            if maximum - minimum <= 24:
                low_saturation_pixels += 1
            if maximum <= 72:
                dark_pixels += 1
            if maximum >= 1 and (maximum - minimum) / maximum >= 0.25:
                colorful_pixels += 1
            if maximum >= 204:
                bright_pixels += 1

    edge_map = preview.convert("L").filter(ImageFilter.FIND_EDGES)
    strong_edges = sum(
        1
        for y_coord in range(edge_map.height)
        for x_coord in range(edge_map.width)
        if edge_map.getpixel((x_coord, y_coord)) >= 40
    )

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

    if white_ratio >= 0.55 and edge_ratio >= 0.06:
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
        visual_features["bright_ratio"] >= 0.82
        and visual_features["colorful_ratio"] >= 0.12
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
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _contains_non_latin_text(extracted_text: str, extracted_labels: list[str]) -> bool:
    joined_text = " ".join([extracted_text, *extracted_labels])
    return any(ord(character) > 127 and character.isalpha() for character in joined_text)
