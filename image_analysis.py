from io import BytesIO

from PIL import Image, ImageFile, ImageFilter, ImageOps

from models import ImageAnalysisResult


ImageFile.LOAD_TRUNCATED_IMAGES = True


def analyze_image(image_bytes: bytes, *, model: str, mime_type: str | None = None) -> ImageAnalysisResult:
    del model

    detected_mime_type = mime_type or _detect_mime_type(image_bytes)
    if detected_mime_type == "image/jpeg":
        if _looks_like_structured_diagram(image_bytes):
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


def _looks_like_structured_diagram(image_bytes: bytes) -> bool:
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            rgb_image = ImageOps.exif_transpose(source_image).convert("RGB")
    except Exception:
        return False

    if rgb_image.width < 80 or rgb_image.height < 80:
        return False

    preview = rgb_image.resize((min(256, rgb_image.width), min(256, rgb_image.height)))
    pixel_count = max(1, preview.width * preview.height)

    white_pixels = 0
    low_saturation_pixels = 0
    dark_pixels = 0
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

    if white_ratio >= 0.55 and edge_ratio >= 0.06:
        return True
    if white_ratio >= 0.45 and low_saturation_ratio >= 0.7 and edge_ratio >= 0.055 and dark_ratio >= 0.03:
        return True
    return False
