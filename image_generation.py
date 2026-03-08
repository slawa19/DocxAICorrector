import logging

from image_prompts import get_image_prompt_profile, load_image_prompt_text
from logger import log_event
from models import ImageAnalysisResult


def generate_image_candidate(
    image_bytes: bytes,
    analysis: ImageAnalysisResult,
    *,
    mode: str,
) -> bytes:
    if not _is_supported_image_bytes(image_bytes):
        raise RuntimeError("Передан неподдерживаемый image payload.")

    prompt_profile = get_image_prompt_profile(analysis.prompt_key)
    load_image_prompt_text(analysis.prompt_key)
    requested_mode = mode
    if mode not in {"safe", "semantic_redraw_direct", "semantic_redraw_structured"}:
        requested_mode = "safe"

    if requested_mode != "safe" and not analysis.semantic_redraw_allowed:
        requested_mode = "safe"

    log_event(
        logging.INFO,
        "image_candidate_generated",
        "Подготовлен candidate image для текущей стратегии",
        requested_mode=requested_mode,
        prompt_key=analysis.prompt_key,
        preferred_strategy=prompt_profile["preferred_strategy"],
        image_type=analysis.image_type,
        render_strategy=analysis.render_strategy,
    )
    return image_bytes


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
