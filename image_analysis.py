from io import BytesIO

from PIL import Image, ImageFile, ImageFilter, ImageOps

from models import ImageAnalysisResult


ImageFile.LOAD_TRUNCATED_IMAGES = True


def analyze_image(image_bytes: bytes, *, model: str, mime_type: str | None = None) -> ImageAnalysisResult:
    del model

    detected_mime_type = mime_type or _detect_mime_type(image_bytes)
    visual_features = _extract_visual_features(image_bytes)

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
                render_strategy="semantic_redraw_direct",
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
                render_strategy="semantic_redraw_structured",
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
                render_strategy="semantic_redraw_direct",
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
                render_strategy="semantic_redraw_structured",
                structure_summary="Diagram-like image with labels and layout relationships.",
                extracted_labels=[],
            )
        return ImageAnalysisResult(
            image_type="mixed_or_ambiguous",
            image_subtype="raster_ambiguous",
            contains_text=False,
            semantic_redraw_allowed=False,
            confidence=0.58,
            structured_parse_confidence=0.16,
            prompt_key="mixed_or_ambiguous_fallback",
            render_strategy="safe_mode",
            structure_summary="Raster image without reliable diagram evidence; preserve original appearance.",
            extracted_labels=[],
            fallback_reason="raster_safe_only",
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
