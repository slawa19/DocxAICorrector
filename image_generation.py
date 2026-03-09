import base64
import logging
import time
from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageEnhance, ImageOps
from PIL import ImageChops

from config import get_client
from image_prompts import get_image_prompt_profile, load_image_prompt_text
from image_reconstruction import reconstruct_image
from logger import log_event
from models import ImageAnalysisResult

IMAGE_EDIT_MODEL = "gpt-image-1"
IMAGE_GENERATE_MODEL = "gpt-image-1"
IMAGE_STRUCTURE_VISION_MODEL = "gpt-4.1"
IMAGE_API_TIMEOUT_SECONDS = 90.0
IMAGE_API_MAX_RETRIES = 3
IMAGE_API_MAX_BACKOFF_SECONDS = 8.0
SEMANTIC_MODES = {"semantic_redraw_direct", "semantic_redraw_structured"}
RECONSTRUCTION_STRATEGY = "deterministic_reconstruction"


class ImageModelCallBudgetExceeded(RuntimeError):
    pass


class ImageModelCallBudget:
    def __init__(self, max_calls: int):
        self.max_calls = max(1, int(max_calls))
        self.used_calls = 0

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.used_calls)

    def ensure_available(self, operation_name: str) -> None:
        if self.remaining_calls <= 0:
            raise ImageModelCallBudgetExceeded(
                f"Image model call budget exhausted before {operation_name}: {self.used_calls}/{self.max_calls} calls used."
            )

    def consume(self, operation_name: str) -> None:
        self.ensure_available(operation_name)
        self.used_calls += 1


def generate_image_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    mode: str,
    prefer_deterministic_reconstruction: bool = True,
    reconstruction_model: str | None = None,
    reconstruction_render_config: dict[str, object] | None = None,
    client=None,
    budget: ImageModelCallBudget | None = None,
) -> bytes:
    if not _is_supported_image_bytes(image_bytes):
        raise RuntimeError("Передан неподдерживаемый image payload.")

    prompt_profile = get_image_prompt_profile(analysis.prompt_key)
    prompt_text = load_image_prompt_text(analysis.prompt_key)
    requested_mode = _resolve_requested_mode(mode, analysis)

    if requested_mode == "safe":
        candidate_bytes = _generate_safe_candidate(image_bytes)
    elif _should_use_reconstruction(
        analysis,
        requested_mode=requested_mode,
        prefer_deterministic_reconstruction=prefer_deterministic_reconstruction,
    ):
        candidate_bytes = _generate_reconstructed_candidate(
            image_bytes,
            analysis,
            client=client,
            budget=budget,
            reconstruction_model=reconstruction_model,
            reconstruction_render_config=reconstruction_render_config,
        )
    else:
        candidate_bytes = _generate_semantic_candidate(
            image_bytes,
            analysis,
            requested_mode=requested_mode,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
            client=client,
            budget=budget,
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


def _should_use_reconstruction(
    analysis: ImageAnalysisResult,
    *,
    requested_mode: str,
    prefer_deterministic_reconstruction: bool,
) -> bool:
    return (
        prefer_deterministic_reconstruction
        and analysis.render_strategy == RECONSTRUCTION_STRATEGY
        and requested_mode in SEMANTIC_MODES
    )


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
    client=None,
    budget: ImageModelCallBudget | None = None,
    reconstruction_model: str | None = None,
    reconstruction_render_config: dict[str, object] | None = None,
) -> bytes:
    """Deterministic reconstruction via VLM scene-graph extraction + PIL rendering.

    Falls back to safe candidate if reconstruction fails.
    """
    model = reconstruction_model or "gpt-4.1"
    try:
        _consume_budget(budget, "deterministic_reconstruction.responses.create")
        candidate_bytes, scene_graph = reconstruct_image(
            image_bytes,
            model=model,
            mime_type=None,
            client=client,
            render_config=reconstruction_render_config,
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
    client=None,
    budget: ImageModelCallBudget | None = None,
) -> bytes:
    resolved_client = client or get_client()
    prompt = _build_image_edit_prompt(
        analysis,
        requested_mode=requested_mode,
        prompt_text=prompt_text,
        prompt_profile=prompt_profile,
        source_size=_read_image_size(image_bytes),
    )

    if requested_mode == "semantic_redraw_structured":
        return _generate_structured_candidate(
            resolved_client,
            image_bytes,
            analysis,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
            prompt=prompt,
            budget=budget,
        )

    try:
        return _generate_direct_semantic_candidate(
            resolved_client,
            image_bytes,
            analysis,
            prompt=prompt,
            budget=budget,
        )
    except Exception as exc:
        log_event(
            logging.WARNING,
            "semantic_image_edit_fallback_to_structured_generate",
            "Прямой semantic edit не удался, перехожу на structured Vision + Generate pipeline.",
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            image_type=analysis.image_type,
            prompt_key=analysis.prompt_key,
        )
        return _generate_structured_candidate(
            resolved_client,
            image_bytes,
            analysis,
            prompt_text=prompt_text,
            prompt_profile=prompt_profile,
            prompt=prompt,
            budget=budget,
        )


def _generate_direct_semantic_candidate(
    client,
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    prompt: str,
    budget: ImageModelCallBudget | None = None,
) -> bytes:
    use_high_fidelity = _uses_high_fidelity_semantic_edit(analysis, "semantic_redraw_direct")
    semantic_upload, restore_context = _prepare_semantic_edit_image(image_bytes)
    request_payload = {
        "model": IMAGE_EDIT_MODEL,
        "image": [_build_edit_file_like(semantic_upload)],
        "prompt": prompt,
        "quality": "high" if use_high_fidelity else "medium",
        "size": _select_generate_size(restore_context["original_size"]),
        "response_format": "b64_json",
    }
    response = _call_images_edit(client, request_payload, budget=budget)
    candidate_bytes, revised_prompt = _extract_image_bytes(response)
    candidate_bytes = _restore_semantic_output(candidate_bytes, restore_context)
    log_event(
        logging.INFO,
        "semantic_image_edit_completed",
        "Direct semantic redraw завершен через OpenAI Images API.",
        requested_mode="semantic_redraw_direct",
        prompt_key=analysis.prompt_key,
        image_type=analysis.image_type,
        revised_prompt=revised_prompt,
    )
    return candidate_bytes


def _generate_structured_candidate(
    client,
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    prompt_text: str,
    prompt_profile: dict[str, str],
    prompt: str,
    budget: ImageModelCallBudget | None = None,
) -> bytes:
    original_size = _read_image_size(image_bytes)
    layout_description = _extract_structured_layout_description(client, image_bytes, analysis, budget=budget)
    generate_prompt = _build_structured_generate_prompt(
        analysis,
        prompt_text=prompt_text,
        prompt_profile=prompt_profile,
        base_prompt=prompt,
        layout_description=layout_description,
        source_size=original_size,
    )
    request_payload = {
        "model": IMAGE_GENERATE_MODEL,
        "prompt": generate_prompt,
        "size": _select_generate_size(original_size),
        "quality": "high",
        "response_format": "b64_json",
    }
    response = _call_images_generate(client, request_payload, budget=budget)
    candidate_bytes, revised_prompt = _extract_image_bytes(response)
    candidate_bytes = _restore_generated_output(candidate_bytes, original_size)
    log_event(
        logging.INFO,
        "structured_image_generate_completed",
        "Structured semantic redraw завершен через Vision + Images.generate.",
        requested_mode="semantic_redraw_structured",
        prompt_key=analysis.prompt_key,
        image_type=analysis.image_type,
        revised_prompt=revised_prompt,
    )
    return candidate_bytes


def _call_images_edit(client, request_payload: dict[str, object], *, budget: ImageModelCallBudget | None = None):
    retryable_optional_params = {
        "moderation",
        "input_fidelity",
        "quality",
        "output_format",
        "response_format",
        "size",
        "timeout",
    }
    current_payload = dict(request_payload)
    attempt = 1
    while True:
        try:
            _consume_budget(budget, "images.edit")
            return client.images.edit(**_with_timeout(current_payload))
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
            continue
        except Exception as exc:
            prompt_limit = _extract_prompt_limit(str(exc))
            if prompt_limit is not None and isinstance(current_payload.get("prompt"), str):
                current_payload["prompt"] = _shorten_prompt_for_limit(str(current_payload["prompt"]), prompt_limit)
                log_event(
                    logging.INFO,
                    "semantic_image_edit_retry_with_shorter_prompt",
                    "Images API отклонил слишком длинный prompt, повторяю запрос с сокращенным prompt.",
                    prompt_limit=prompt_limit,
                )
                continue
            fallback_size = _extract_supported_size_fallback(str(exc), str(current_payload.get("size", "")))
            if fallback_size is not None:
                current_payload["size"] = fallback_size
                log_event(
                    logging.INFO,
                    "semantic_image_edit_retry_with_fallback_size",
                    "Images API отклонил auto-size, повторяю запрос с совместимым фиксированным размером.",
                    fallback_size=fallback_size,
                )
                continue
            unsupported_param = _extract_unsupported_parameter_name(str(exc))
            if unsupported_param in retryable_optional_params and unsupported_param in current_payload:
                current_payload.pop(unsupported_param, None)
                log_event(
                    logging.INFO,
                    "semantic_image_edit_retry_without_optional_param",
                    "Images API отклонил optional param, повторяю запрос без него.",
                    removed_param=unsupported_param,
                )
                continue
            if attempt < IMAGE_API_MAX_RETRIES and _is_retryable_api_error(exc):
                _ensure_budget_available(budget, "images.edit")
                retry_delay = _compute_retry_delay(attempt)
                log_event(
                    logging.WARNING,
                    "semantic_image_edit_retry_after_transient_error",
                    "Transient ошибка Images.edit, повторяю запрос с backoff.",
                    attempt=attempt,
                    retry_delay_seconds=retry_delay,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
                time.sleep(retry_delay)
                attempt += 1
                continue
            raise


def _call_images_generate(client, request_payload: dict[str, object], *, budget: ImageModelCallBudget | None = None):
    retryable_optional_params = {"quality", "response_format", "size", "timeout"}
    current_payload = dict(request_payload)
    attempt = 1
    while True:
        try:
            _consume_budget(budget, "images.generate")
            return client.images.generate(**_with_timeout(current_payload))
        except TypeError as exc:
            unsupported_param = _extract_unsupported_parameter_name(str(exc))
            if unsupported_param not in retryable_optional_params or unsupported_param not in current_payload:
                raise
            current_payload.pop(unsupported_param, None)
            log_event(
                logging.INFO,
                "structured_image_generate_retry_without_optional_param",
                "OpenAI SDK не поддерживает optional param для Images.generate, повторяю запрос без него.",
                removed_param=unsupported_param,
            )
            continue
        except Exception as exc:
            prompt_limit = _extract_prompt_limit(str(exc))
            if prompt_limit is not None and isinstance(current_payload.get("prompt"), str):
                current_payload["prompt"] = _shorten_prompt_for_limit(str(current_payload["prompt"]), prompt_limit)
                log_event(
                    logging.INFO,
                    "structured_image_generate_retry_with_shorter_prompt",
                    "Images.generate отклонил слишком длинный prompt, повторяю запрос с сокращенным prompt.",
                    prompt_limit=prompt_limit,
                )
                continue
            fallback_size = _extract_supported_generate_size_fallback(str(exc), str(current_payload.get("size", "")))
            if fallback_size is not None:
                current_payload["size"] = fallback_size
                log_event(
                    logging.INFO,
                    "structured_image_generate_retry_with_fallback_size",
                    "Images.generate отклонил размер, повторяю запрос с совместимым размером.",
                    fallback_size=fallback_size,
                )
                continue
            unsupported_param = _extract_unsupported_parameter_name(str(exc))
            if unsupported_param in retryable_optional_params and unsupported_param in current_payload:
                current_payload.pop(unsupported_param, None)
                log_event(
                    logging.INFO,
                    "structured_image_generate_retry_without_optional_param",
                    "Images.generate отклонил optional param, повторяю запрос без него.",
                    removed_param=unsupported_param,
                )
                continue
            if attempt < IMAGE_API_MAX_RETRIES and _is_retryable_api_error(exc):
                _ensure_budget_available(budget, "images.generate")
                retry_delay = _compute_retry_delay(attempt)
                log_event(
                    logging.WARNING,
                    "structured_image_generate_retry_after_transient_error",
                    "Transient ошибка Images.generate, повторяю запрос с backoff.",
                    attempt=attempt,
                    retry_delay_seconds=retry_delay,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
                time.sleep(retry_delay)
                attempt += 1
                continue
            raise


def _call_responses_create(client, request_payload: dict[str, object], *, budget: ImageModelCallBudget | None = None):
    retryable_optional_params = {"timeout"}
    current_payload = dict(request_payload)
    attempt = 1
    while True:
        try:
            _consume_budget(budget, "responses.create")
            return client.responses.create(**_with_timeout(current_payload))
        except TypeError as exc:
            unsupported_param = _extract_unsupported_parameter_name(str(exc))
            if unsupported_param not in retryable_optional_params or unsupported_param not in current_payload:
                raise
            current_payload.pop(unsupported_param, None)
            log_event(
                logging.INFO,
                "structured_layout_retry_without_optional_param",
                "OpenAI SDK не поддерживает optional param для Responses API, повторяю запрос без него.",
                removed_param=unsupported_param,
            )
            continue
        except Exception as exc:
            unsupported_param = _extract_unsupported_parameter_name(str(exc))
            if unsupported_param in retryable_optional_params and unsupported_param in current_payload:
                current_payload.pop(unsupported_param, None)
                log_event(
                    logging.INFO,
                    "structured_layout_retry_without_optional_param",
                    "Responses API отклонил optional param, повторяю запрос без него.",
                    removed_param=unsupported_param,
                )
                continue
            if attempt < IMAGE_API_MAX_RETRIES and _is_retryable_api_error(exc):
                _ensure_budget_available(budget, "responses.create")
                retry_delay = _compute_retry_delay(attempt)
                log_event(
                    logging.WARNING,
                    "structured_layout_retry_after_transient_error",
                    "Transient ошибка Responses API, повторяю Vision-запрос с backoff.",
                    attempt=attempt,
                    retry_delay_seconds=retry_delay,
                    error_type=exc.__class__.__name__,
                    error_message=str(exc),
                )
                time.sleep(retry_delay)
                attempt += 1
                continue
            raise


def _with_timeout(request_payload: dict[str, object]) -> dict[str, object]:
    payload_with_timeout = dict(request_payload)
    payload_with_timeout.setdefault("timeout", IMAGE_API_TIMEOUT_SECONDS)
    return payload_with_timeout


def _is_retryable_api_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429}:
        return True
    if isinstance(status_code, int) and status_code >= 500:
        return True
    return exc.__class__.__name__ in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}


def _compute_retry_delay(attempt: int) -> float:
    return min(2 ** (attempt - 1), IMAGE_API_MAX_BACKOFF_SECONDS)


def _ensure_budget_available(budget: ImageModelCallBudget | None, operation_name: str) -> None:
    if budget is None:
        return
    budget.ensure_available(operation_name)


def _consume_budget(budget: ImageModelCallBudget | None, operation_name: str) -> None:
    if budget is None:
        return
    budget.consume(operation_name)


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
    for candidate in ("1536x1024", "1024x1536", "1024x1024", "512x512", "256x256"):
        if candidate in error_message:
            supported_sizes.append(candidate)
    for candidate in supported_sizes:
        if candidate != current_size:
            return candidate
    return None


def _extract_supported_generate_size_fallback(error_message: str, current_size: str) -> str | None:
    if "Supported values are:" not in error_message or "size" not in error_message:
        return None
    supported_sizes = []
    for candidate in ("1536x1024", "1024x1536", "1024x1024", "1792x1024", "1024x1792"):
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


def _build_edit_file_like(image_upload: tuple[str, bytes, str]):
    filename, image_bytes, _mime_type = image_upload
    file_like = BytesIO(image_bytes)
    file_like.name = filename
    return file_like


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
        f"Original content aspect ratio: {source_size[0]}:{source_size[1]}. Fill the entire generated canvas completely from edge to edge — no empty outer margins, padding, or borders around the artwork.",
        f"Structure summary: {analysis.structure_summary}",
    ]
    if labels:
        prompt_parts.append(f"Preserve these labels exactly when readable: {labels}")
        prompt_parts.append("Do not remove, translate, paraphrase, or invent labels. Preserve visible text verbatim.")
    if analysis.extracted_text.strip():
        prompt_parts.append("Preserve this extracted source text verbatim when it is readable:")
        prompt_parts.append(analysis.extracted_text.strip())
    if analysis.fallback_reason:
        prompt_parts.append(f"Avoid the failure mode noted during analysis: {analysis.fallback_reason}.")
    if analysis.contains_text:
        prompt_parts.append("Prioritize legible text and preserve the same count of labeled elements and connectors.")
    prompt_parts.append("Do not merely upscale, sharpen, or restyle the existing pixels. Rebuild the visual from scratch while keeping the same meaning and layout.")
    prompt_parts.append("Return a single edited image, not a textual explanation.")
    return "\n\n".join(part for part in prompt_parts if part)


def _build_structured_generate_prompt(
    analysis: ImageAnalysisResult,
    *,
    prompt_text: str,
    prompt_profile: dict[str, str],
    base_prompt: str,
    layout_description: str,
    source_size: tuple[int, int],
) -> str:
    prompt_parts = [
        prompt_text,
        f"Profile: {prompt_profile['description']}",
        f"Detected image type: {analysis.image_type}.",
        f"Original content aspect ratio: {source_size[0]}:{source_size[1]}. Fill the entire generated canvas completely from edge to edge — no empty outer margins, padding, or borders.",
        "Generate a brand-new clean vector-style diagram from scratch. Do not mimic scan artifacts, JPEG noise, blur, shadows, or the original raster texture.",
        "Preserve every readable label, connector, block, lane, table cell, legend item, and hierarchy level from the source structure.",
        base_prompt,
        "Structured layout description for exact redraw:",
        layout_description,
    ]
    if analysis.extracted_text.strip():
        prompt_parts.append("Verbatim text that should appear in the generated image when readable:")
        prompt_parts.append(analysis.extracted_text.strip())
    prompt_parts.append("Return a single generated image, not a textual explanation.")
    return "\n\n".join(prompt_parts)


def _extract_structured_layout_description(
    client,
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    budget: ImageModelCallBudget | None = None,
) -> str:
    mime_type = _detect_mime_type(image_bytes)
    if mime_type is None:
        raise RuntimeError("Не удалось определить MIME-тип изображения для structured redraw.")

    image_data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    response = _call_responses_create(
        client,
        {
            "model": IMAGE_STRUCTURE_VISION_MODEL,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "You convert diagrams, tables, and infographics into exact redraw specifications for image generation. "
                                "List every readable label verbatim, preserve structure conservatively, and never invent missing content."
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
                                "Describe this image as a production-ready redraw specification. Include layout, reading order, block geometry, arrows, "
                                "table structure, colors, and all readable text verbatim. If text is unreadable, say unreadable instead of guessing. "
                                f"Detected image type: {analysis.image_type}. Structure summary: {analysis.structure_summary}."
                            ),
                        },
                        {"type": "input_image", "image_url": image_data_url},
                    ],
                },
            ],
        },
        budget=budget,
    )
    layout_description = getattr(response, "output_text", "").strip()
    if not layout_description:
        raise RuntimeError("Vision-модель не вернула описание структуры для structured redraw.")
    return layout_description


def _read_image_size(image_bytes: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            return ImageOps.exif_transpose(image).size
    except Exception as exc:
        raise RuntimeError("Не удалось определить размеры исходного изображения.") from exc


def _select_generate_size(_source_size: tuple[int, int]) -> str:
    """Request auto-sizing so gpt-image-1 picks the aspect ratio closest to the source."""
    return "auto"


def _restore_generated_output(image_bytes: bytes, original_size: tuple[int, int]) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as generated_image:
            generated_image.load()
            normalized_image = ImageOps.exif_transpose(generated_image)
            trimmed_image = _trim_generated_outer_padding(normalized_image)
            fitted = ImageOps.contain(trimmed_image, original_size, Image.Resampling.LANCZOS)
            if fitted.size != original_size:
                background_color = _pick_generated_background_color(fitted)
                canvas_mode = "RGBA" if fitted.mode in {"RGBA", "LA"} else "RGB"
                canvas = Image.new(canvas_mode, original_size, background_color)
                offset_x = (original_size[0] - fitted.width) // 2
                offset_y = (original_size[1] - fitted.height) // 2
                if canvas_mode == "RGBA":
                    canvas.alpha_composite(fitted.convert("RGBA"), (offset_x, offset_y))
                else:
                    canvas.paste(fitted, (offset_x, offset_y))
                restored_image = canvas
            else:
                restored_image = fitted

            output = BytesIO()
            output_format = _select_pillow_output_format(generated_image.format)
            save_kwargs = {"format": output_format}
            if output_format == "PNG":
                save_kwargs["optimize"] = True
            elif output_format == "JPEG":
                save_kwargs["quality"] = 92
                save_kwargs["optimize"] = True
                if restored_image.mode not in {"RGB", "L"}:
                    restored_image = restored_image.convert("RGB")
            restored_image.save(output, **save_kwargs)
            restored_bytes = output.getvalue()
            return restored_bytes or image_bytes
    except Exception:
        return image_bytes


def _trim_generated_outer_padding(image: Image.Image) -> Image.Image:
    rgb_image = image.convert("RGB")
    background_rgb = _pick_generated_background_color(rgb_image)
    background = Image.new("RGB", rgb_image.size, background_rgb)
    difference = ImageChops.difference(rgb_image, background)
    mask = difference.convert("L").point(lambda value: 255 if value > 12 else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return image

    left, top, right, bottom = bbox
    if left == 0 and top == 0 and right == image.width and bottom == image.height:
        return image

    pad_x = max(2, int(round(image.width * 0.01)))
    pad_y = max(2, int(round(image.height * 0.01)))
    expanded_bbox = (
        max(0, left - pad_x),
        max(0, top - pad_y),
        min(image.width, right + pad_x),
        min(image.height, bottom + pad_y),
    )
    cropped = image.crop(expanded_bbox)
    if cropped.width <= 0 or cropped.height <= 0:
        return image
    return cropped


def _pick_generated_background_color(image: Image.Image) -> tuple[int, ...]:
    """Sample 4x4 corner patches and return the median RGB, robust against noisy corner pixels."""
    rgb_image = image.convert("RGB")
    w, h = rgb_image.size
    patch = max(4, min(w, h) // 16)
    corner_regions = [
        (0, 0, patch, patch),
        (max(0, w - patch), 0, w, patch),
        (0, max(0, h - patch), patch, h),
        (max(0, w - patch), max(0, h - patch), w, h),
    ]
    samples: list[tuple[int, int, int]] = []
    for box in corner_regions:
        region = rgb_image.crop(box)
        for y_coord in range(region.height):
            for x_coord in range(region.width):
                pixel = region.getpixel((x_coord, y_coord))
                if isinstance(pixel, int):
                    samples.append((pixel, pixel, pixel))
                else:
                    samples.append((int(pixel[0]), int(pixel[1]), int(pixel[2])))

    if not samples:
        return (255, 255, 255, 255) if image.mode in {"RGBA", "LA"} else (255, 255, 255)

    rgb_result = tuple(
        sorted(s[c] for s in samples)[len(samples) // 2]
        for c in range(3)
    )
    return rgb_result + (255,) if image.mode in {"RGBA", "LA"} else rgb_result


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


def detect_image_mime_type(image_bytes: bytes) -> str | None:
    return _detect_mime_type(image_bytes)


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
