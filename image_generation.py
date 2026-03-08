import base64
import logging
from io import BytesIO

from PIL import Image, ImageEnhance, ImageOps

from config import get_client
from image_prompts import get_image_prompt_profile, load_image_prompt_text
from logger import log_event
from models import ImageAnalysisResult

IMAGE_EDIT_MODEL = "gpt-image-1"
SEMANTIC_MODES = {"semantic_redraw_direct", "semantic_redraw_structured"}


def generate_image_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    mode: str,
) -> bytes:
    if not _is_supported_image_bytes(image_bytes):
        raise RuntimeError("Передан неподдерживаемый image payload.")

    prompt_profile = get_image_prompt_profile(analysis.prompt_key)
    prompt_text = load_image_prompt_text(analysis.prompt_key)
    requested_mode = _resolve_requested_mode(mode, analysis)

    if requested_mode == "safe":
        candidate_bytes = _generate_safe_candidate(image_bytes)
    else:
        candidate_bytes = _generate_semantic_candidate(
            image_bytes,
            analysis,
            requested_mode=requested_mode,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
        )

    log_event(
        logging.INFO,
        "image_candidate_generated",
        "Подготовлен candidate image для текущей стратегии",
        requested_mode=requested_mode,
        prompt_key=analysis.prompt_key,
        preferred_strategy=prompt_profile["preferred_strategy"],
        image_type=analysis.image_type,
        render_strategy=analysis.render_strategy,
        bytes_changed=candidate_bytes != image_bytes,
    )
    return candidate_bytes


def _resolve_requested_mode(mode: str, analysis: ImageAnalysisResult) -> str:
    requested_mode = mode if mode in {"safe", *SEMANTIC_MODES} else "safe"
    if requested_mode in SEMANTIC_MODES and not analysis.semantic_redraw_allowed:
        return "safe"
    return requested_mode


def _generate_safe_candidate(image_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            enhanced_image = _enhance_image_conservatively(source_image)
            output = BytesIO()
            output_format = _select_pillow_output_format(source_image.format)
            save_kwargs = {"format": output_format}
            if output_format == "PNG":
                save_kwargs["optimize"] = True
            elif output_format == "JPEG":
                save_kwargs["quality"] = 92
                save_kwargs["optimize"] = True
            enhanced_image.save(output, **save_kwargs)
            candidate_bytes = output.getvalue()
            return candidate_bytes or image_bytes
    except Exception as exc:
        log_event(
            logging.WARNING,
            "safe_image_enhancement_skipped",
            "Safe enhancement завершился с ошибкой, используется оригинал.",
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        return image_bytes


def _enhance_image_conservatively(source_image: Image.Image) -> Image.Image:
    normalized_image = ImageOps.exif_transpose(source_image)
    if normalized_image.mode in {"RGBA", "LA"}:
        rgba_image = normalized_image.convert("RGBA")
        alpha_channel = rgba_image.getchannel("A")
        rgb_image = rgba_image.convert("RGB")
        enhanced_rgb = _enhance_rgb_image(rgb_image)
        restored = enhanced_rgb.convert("RGBA")
        restored.putalpha(alpha_channel)
        return restored
    if normalized_image.mode == "P":
        return _enhance_rgb_image(normalized_image.convert("RGB"))
    if normalized_image.mode == "L":
        grayscale = ImageOps.autocontrast(normalized_image, cutoff=1)
        return ImageEnhance.Sharpness(grayscale).enhance(1.05)
    return _enhance_rgb_image(normalized_image.convert("RGB"))


def _enhance_rgb_image(image: Image.Image) -> Image.Image:
    enhanced = ImageOps.autocontrast(image, cutoff=1)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.04)
    enhanced = ImageEnhance.Color(enhanced).enhance(1.02)
    return ImageEnhance.Sharpness(enhanced).enhance(1.08)


def _generate_semantic_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    requested_mode: str,
    prompt_text: str,
    prompt_profile: dict[str, str],
) -> bytes:
    client = get_client()
    response = client.images.edit(
        model=IMAGE_EDIT_MODEL,
        image=_build_image_upload(image_bytes),
        prompt=_build_image_edit_prompt(
            analysis,
            requested_mode=requested_mode,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
        ),
        input_fidelity="high" if requested_mode == "semantic_redraw_structured" else "low",
        quality="high" if requested_mode == "semantic_redraw_structured" else "medium",
        size="auto",
        output_format=_select_api_output_format(image_bytes),
        response_format="b64_json",
        moderation="auto",
    )
    candidate_bytes, revised_prompt = _extract_image_bytes(response)
    log_event(
        logging.INFO,
        "semantic_image_edit_completed",
        "Semantic redraw завершен через OpenAI Images API.",
        requested_mode=requested_mode,
        prompt_key=analysis.prompt_key,
        image_type=analysis.image_type,
        revised_prompt=revised_prompt,
    )
    return candidate_bytes


def _build_image_upload(image_bytes: bytes) -> tuple[str, bytes, str]:
    mime_type = _detect_mime_type(image_bytes)
    if mime_type is None:
        raise RuntimeError("Не удалось определить MIME-тип изображения для OpenAI Images API.")
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/bmp": "bmp",
    }.get(mime_type, "png")
    return (f"source.{extension}", image_bytes, mime_type)


def _build_image_edit_prompt(
    analysis: ImageAnalysisResult,
    *,
    requested_mode: str,
    prompt_text: str,
    prompt_profile: dict[str, str],
) -> str:
    mode_guidance = {
        "semantic_redraw_direct": (
            "Use the original image as the reference and redraw it more cleanly, "
            "while preserving meaning, key labels, and the overall information hierarchy."
        ),
        "semantic_redraw_structured": (
            "Use the original image as the reference and preserve layout, block count, connectors, "
            "arrows, table structure, and readable labels as strictly as possible."
        ),
    }[requested_mode]
    labels = ", ".join(label for label in analysis.extracted_labels[:20] if label.strip())
    prompt_parts = [
        prompt_text,
        mode_guidance,
        f"Profile: {prompt_profile['description']}",
        f"Detected image type: {analysis.image_type}.",
        f"Structure summary: {analysis.structure_summary}",
    ]
    if labels:
        prompt_parts.append(f"Preserve these labels exactly when readable: {labels}")
    if analysis.fallback_reason:
        prompt_parts.append(f"Avoid the failure mode noted during analysis: {analysis.fallback_reason}.")
    prompt_parts.append("Return a single edited image, not a textual explanation.")
    return "\n\n".join(part for part in prompt_parts if part)


def _extract_image_bytes(response) -> tuple[bytes, str | None]:
    data = getattr(response, "data", None)
    if not data:
        raise RuntimeError("OpenAI Images API вернул пустой результат редактирования.")
    image_item = data[0]
    image_base64 = getattr(image_item, "b64_json", None)
    if not image_base64:
        raise RuntimeError("OpenAI Images API не вернул image payload.")
    try:
        return base64.b64decode(image_base64), getattr(image_item, "revised_prompt", None)
    except Exception as exc:
        raise RuntimeError("Не удалось декодировать изображение из OpenAI Images API.") from exc


def _select_pillow_output_format(source_format: str | None) -> str:
    normalized_format = (source_format or "").upper()
    if normalized_format in {"PNG", "JPEG", "JPG", "BMP"}:
        return "JPEG" if normalized_format in {"JPEG", "JPG"} else normalized_format
    return "PNG"


def _select_api_output_format(image_bytes: bytes) -> str:
    detected_mime_type = _detect_mime_type(image_bytes)
    if detected_mime_type == "image/jpeg":
        return "jpeg"
    return "png"


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


def _is_supported_image_bytes(image_bytes: bytes) -> bool:
    return image_bytes.startswith(
        (
            b"\x89PNG\r\n\x1a\n",
            b"\xff\xd8\xff",
            b"GIF87a",
            b"GIF89a",
            b"BM",
        )
    )
