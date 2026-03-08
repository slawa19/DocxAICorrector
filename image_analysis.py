from models import ImageAnalysisResult


def analyze_image(image_bytes: bytes, *, model: str, mime_type: str | None = None) -> ImageAnalysisResult:
    del model

    detected_mime_type = mime_type or _detect_mime_type(image_bytes)
    if detected_mime_type == "image/jpeg":
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
