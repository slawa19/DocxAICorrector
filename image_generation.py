import base64
import logging
from io import BytesIO

from PIL import Image, ImageEnhance, ImageOps

from config import get_client
from image_prompts import get_image_prompt_profile, load_image_prompt_text
from image_reconstruction import reconstruct_image
from logger import log_event
from models import ImageAnalysisResult

IMAGE_EDIT_MODEL = "gpt-image-1"
SEMANTIC_MODES = {"semantic_redraw_direct", "semantic_redraw_structured"}
RECONSTRUCTION_STRATEGY = "deterministic_reconstruction"


def generate_image_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    mode: str,
    reconstruction_model: str | None = None,
) -> bytes:
    if not _is_supported_image_bytes(image_bytes):
        raise RuntimeError("Передан неподдерживаемый image payload.")

    prompt_profile = get_image_prompt_profile(analysis.prompt_key)
    prompt_text = load_image_prompt_text(analysis.prompt_key)
    requested_mode = _resolve_requested_mode(mode, analysis)

    if requested_mode == "safe":
        candidate_bytes = _generate_safe_candidate(image_bytes)
    elif analysis.render_strategy == RECONSTRUCTION_STRATEGY and requested_mode in SEMANTIC_MODES:
        candidate_bytes = _generate_reconstructed_candidate(
            image_bytes,
            analysis,
            reconstruction_model=reconstruction_model,
        )
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


def _generate_reconstructed_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    reconstruction_model: str | None = None,
) -> bytes:
    """Deterministic reconstruction via VLM scene-graph extraction + PIL rendering.

    Falls back to safe candidate if reconstruction fails.
    """
    from image_reconstruction import reconstruct_image as _reconstruct

    model = reconstruction_model or "gpt-4.1"
    try:
        candidate_bytes, scene_graph = _reconstruct(
            image_bytes,
            model=model,
            mime_type=None,
        )
        log_event(
            logging.INFO,
            "deterministic_reconstruction_succeeded",
            "Детерминированная реконструкция через scene graph завершена успешно.",
            image_type=analysis.image_type,
            element_count=len(scene_graph.get("elements", [])),
        )
        return candidate_bytes
    except Exception as exc:
        log_event(
            logging.WARNING,
            "deterministic_reconstruction_failed",
            "Детерминированная реконструкция не удалась, применяется safe fallback.",
            image_type=analysis.image_type,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        return _generate_safe_candidate(image_bytes)


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
    use_high_fidelity = _uses_high_fidelity_semantic_edit(analysis, requested_mode)
    semantic_upload, restore_context = _prepare_semantic_edit_image(image_bytes)
    request_payload = {
        "model": IMAGE_EDIT_MODEL,
        "image": semantic_upload,
        "prompt": _build_image_edit_prompt(
            analysis,
            requested_mode=requested_mode,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
            source_size=restore_context["original_size"],
        ),
        "input_fidelity": "high" if use_high_fidelity else "low",
        "quality": "high" if use_high_fidelity else "medium",
        "size": "auto",
        "output_format": _select_semantic_api_output_format(image_bytes, analysis),
        "response_format": "b64_json",
        "moderation": "auto",
    }
    response = _call_images_edit(client, request_payload)
    candidate_bytes, revised_prompt = _extract_image_bytes(response)
    candidate_bytes = _restore_semantic_output(candidate_bytes, restore_context)
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


def _call_images_edit(client, request_payload: dict[str, object]):
    retryable_optional_params = {
        "moderation",
        "input_fidelity",
        "quality",
        "output_format",
        "response_format",
        "size",
    }
    current_payload = dict(request_payload)
    try:
        return client.images.edit(**current_payload)
    except TypeError as exc:
        unsupported_param = _extract_unsupported_parameter_name(str(exc))
        if unsupported_param not in retryable_optional_params or unsupported_param not in current_payload:
            raise
        current_payload.pop(unsupported_param, None)
        log_event(
            logging.INFO,
            "semantic_image_edit_retry_without_optional_param",
            "OpenAI SDK не поддерживает один из optional params для Images.edit, повторяю запрос без него.",
            removed_param=unsupported_param,
        )
        return _call_images_edit(client, current_payload)
    except Exception as exc:
        fallback_model = _extract_supported_model_fallback(str(exc), str(current_payload.get("model", "")))
        if fallback_model is not None:
            current_payload["model"] = fallback_model
            log_event(
                logging.INFO,
                "semantic_image_edit_retry_with_fallback_model",
                "Images API отклонил model, повторяю запрос с совместимой моделью.",
                fallback_model=fallback_model,
            )
            return _call_images_edit(client, current_payload)
        prompt_limit = _extract_prompt_limit(str(exc))
        if prompt_limit is not None and isinstance(current_payload.get("prompt"), str):
            current_payload["prompt"] = _shorten_prompt_for_limit(str(current_payload["prompt"]), prompt_limit)
            log_event(
                logging.INFO,
                "semantic_image_edit_retry_with_shorter_prompt",
                "Images API отклонил слишком длинный prompt, повторяю запрос с сокращенным prompt.",
                prompt_limit=prompt_limit,
            )
            return _call_images_edit(client, current_payload)
        fallback_size = _extract_supported_size_fallback(str(exc), str(current_payload.get("size", "")))
        if fallback_size is not None:
            current_payload["size"] = fallback_size
            log_event(
                logging.INFO,
                "semantic_image_edit_retry_with_fallback_size",
                "Images API отклонил auto-size, повторяю запрос с совместимым фиксированным размером.",
                fallback_size=fallback_size,
            )
            return _call_images_edit(client, current_payload)
        unsupported_param = _extract_unsupported_parameter_name(str(exc))
        if unsupported_param not in retryable_optional_params or unsupported_param not in current_payload:
            raise
        current_payload.pop(unsupported_param, None)
        log_event(
            logging.INFO,
            "semantic_image_edit_retry_without_optional_param",
            "Images API отклонил optional param, повторяю запрос без него.",
            removed_param=unsupported_param,
        )
        return _call_images_edit(client, current_payload)


def _extract_unsupported_parameter_name(error_message: str) -> str | None:
    marker = "Unknown parameter: '"
    if marker in error_message:
        tail = error_message.split(marker, 1)[1]
        return tail.split("'", 1)[0]
    marker = "unexpected keyword argument '"
    if marker in error_message:
        tail = error_message.split(marker, 1)[1]
        return tail.split("'", 1)[0]
    return None


def _extract_supported_model_fallback(error_message: str, current_model: str) -> str | None:
    marker = "Value must be '"
    if marker not in error_message:
        return None
    tail = error_message.split(marker, 1)[1]
    fallback_model = tail.split("'", 1)[0]
    if not fallback_model or fallback_model == current_model:
        return None
    return fallback_model


def _extract_prompt_limit(error_message: str) -> int | None:
    marker = "maximum length "
    if marker not in error_message:
        return None
    tail = error_message.split(marker, 1)[1]
    digits: list[str] = []
    for character in tail:
        if character.isdigit():
            digits.append(character)
            continue
        if digits:
            break
    if not digits:
        return None
    return int("".join(digits))


def _shorten_prompt_for_limit(prompt_text: str, limit: int) -> str:
    if len(prompt_text) <= limit:
        return prompt_text
    suffix = "\n\nReturn a single edited image."
    allowed_body_length = max(0, limit - len(suffix))
    shortened_body = prompt_text[:allowed_body_length].rstrip()
    return f"{shortened_body}{suffix}"[:limit]


def _extract_supported_size_fallback(error_message: str, current_size: str) -> str | None:
    if "Supported values are:" not in error_message or "size" not in error_message:
        return None
    supported_sizes = []
    for candidate in ("1024x1024", "512x512", "256x256"):
        if candidate in error_message:
            supported_sizes.append(candidate)
    for candidate in supported_sizes:
        if candidate != current_size:
            return candidate
    return None


def _build_image_upload(image_bytes: bytes, prefer_png: bool = False) -> tuple[str, bytes, str]:
    if prefer_png:
        png_bytes = _convert_image_bytes_to_png(image_bytes)
        return ("source.png", png_bytes, "image/png")

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


def _convert_image_bytes_to_png(image_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            normalized_image = ImageOps.exif_transpose(source_image)
            output_image = normalized_image.convert("RGBA")
            output = BytesIO()
            output_image.save(output, format="PNG", optimize=True)
            png_bytes = output.getvalue()
            if not png_bytes:
                raise RuntimeError("PNG conversion produced empty payload.")
            return png_bytes
    except Exception as exc:
        raise RuntimeError("Не удалось подготовить PNG payload для OpenAI Images API.") from exc


def _prepare_semantic_edit_image(
    image_bytes: bytes,
) -> tuple[tuple[str, bytes, str], dict[str, int | tuple[int, int] | tuple[int, int, int, int]]]:
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            normalized_image = ImageOps.exif_transpose(source_image).convert("RGBA")
            original_size = normalized_image.size
            canvas_size = max(original_size)
            offset_x = (canvas_size - original_size[0]) // 2
            offset_y = (canvas_size - original_size[1]) // 2
            square_canvas = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 255))
            square_canvas.alpha_composite(normalized_image, (offset_x, offset_y))

            output = BytesIO()
            square_canvas.save(output, format="PNG", optimize=True)
            png_bytes = output.getvalue()
            if not png_bytes:
                raise RuntimeError("Semantic edit preparation produced empty payload.")

            return (
                ("source.png", png_bytes, "image/png"),
                {
                    "original_size": original_size,
                    "canvas_size": canvas_size,
                    "crop_box": (offset_x, offset_y, offset_x + original_size[0], offset_y + original_size[1]),
                },
            )
    except Exception as exc:
        raise RuntimeError("Не удалось подготовить image payload для semantic redraw без искажения пропорций.") from exc


def _restore_semantic_output(
    image_bytes: bytes,
    restore_context: dict[str, int | tuple[int, int] | tuple[int, int, int, int]],
) -> bytes:
    original_size = restore_context.get("original_size")
    crop_box = restore_context.get("crop_box")
    canvas_size = restore_context.get("canvas_size")
    if not isinstance(original_size, tuple) or not isinstance(crop_box, tuple) or not isinstance(canvas_size, int) or canvas_size <= 0:
        return image_bytes

    try:
        with Image.open(BytesIO(image_bytes)) as semantic_image:
            semantic_image.load()
            normalized_image = ImageOps.exif_transpose(semantic_image)
            if normalized_image.width <= 0 or normalized_image.height <= 0:
                return image_bytes

            left, top, right, bottom = crop_box
            scale_x = normalized_image.width / canvas_size
            scale_y = normalized_image.height / canvas_size
            scaled_crop_box = (
                max(0, int(round(left * scale_x))),
                max(0, int(round(top * scale_y))),
                min(normalized_image.width, int(round(right * scale_x))),
                min(normalized_image.height, int(round(bottom * scale_y))),
            )
            cropped = normalized_image.crop(scaled_crop_box)
            if cropped.size != original_size:
                cropped = cropped.resize(original_size, Image.Resampling.LANCZOS)

            output = BytesIO()
            output_format = _select_pillow_output_format(semantic_image.format)
            save_kwargs = {"format": output_format}
            if output_format == "PNG":
                save_kwargs["optimize"] = True
            elif output_format == "JPEG":
                save_kwargs["quality"] = 92
                save_kwargs["optimize"] = True
                if cropped.mode not in {"RGB", "L"}:
                    cropped = cropped.convert("RGB")
            cropped.save(output, **save_kwargs)
            restored_bytes = output.getvalue()
            return restored_bytes or image_bytes
    except Exception:
        return image_bytes


def _build_image_edit_prompt(
    analysis: ImageAnalysisResult,
    *,
    requested_mode: str,
    prompt_text: str,
    prompt_profile: dict[str, str],
    source_size: tuple[int, int],
) -> str:
    mode_guidance = {
        "semantic_redraw_direct": (
            "Use the original image strictly as a semantic reference and fully re-render it from scratch as a clean publication-ready graphic, "
            "while preserving meaning, key labels, and the overall information hierarchy."
        ),
        "semantic_redraw_structured": (
            "Use the original image strictly as a structural reference and fully reconstruct the diagram from scratch with clean vector-like shapes and typeset text. "
            "Preserve layout, block count, connectors, arrows, table structure, and readable labels as strictly as possible."
        ),
    }[requested_mode]
    labels = ", ".join(label for label in analysis.extracted_labels[:20] if label.strip())
    prompt_parts = [
        prompt_text,
        mode_guidance,
        f"Profile: {prompt_profile['description']}",
        f"Detected image type: {analysis.image_type}.",
        f"Original aspect ratio: {source_size[0]}:{source_size[1]}. Keep the same aspect ratio and composition. Do not stretch content to fill a square canvas.",
        f"Structure summary: {analysis.structure_summary}",
    ]
    if labels:
        prompt_parts.append(f"Preserve these labels exactly when readable: {labels}")
        prompt_parts.append("Do not remove, translate, paraphrase, or invent labels. Preserve visible text verbatim.")
    if analysis.fallback_reason:
        prompt_parts.append(f"Avoid the failure mode noted during analysis: {analysis.fallback_reason}.")
    if analysis.contains_text:
        prompt_parts.append("Prioritize legible text and preserve the same count of labeled elements and connectors.")
    prompt_parts.append("Do not merely upscale, sharpen, or restyle the existing pixels. Rebuild the visual from scratch while keeping the same meaning and layout.")
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


def _select_semantic_api_output_format(image_bytes: bytes, analysis: ImageAnalysisResult) -> str:
    if analysis.contains_text or analysis.image_type != "photo":
        return "png"
    return _select_api_output_format(image_bytes)


def _uses_high_fidelity_semantic_edit(analysis: ImageAnalysisResult, requested_mode: str) -> bool:
    if requested_mode == "semantic_redraw_structured":
        return True
    if analysis.contains_text:
        return True
    if analysis.render_strategy == "semantic_redraw_structured":
        return True
    return analysis.image_type in {"diagram", "chart", "table", "infographic", "mindmap"}


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
