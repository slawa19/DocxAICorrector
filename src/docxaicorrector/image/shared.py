import json
import logging
import time

from docxaicorrector.core.logger import log_event
from docxaicorrector.core.model_accounting import (
    STAGE_IMAGE_ANALYSIS,
    STAGE_IMAGE_GENERATION,
    STAGE_IMAGE_RECONSTRUCTION,
    STAGE_IMAGE_VALIDATION,
    STAGE_UNATTRIBUTED,
    record_model_call_usage,
)

# Spec 062: the image role a ``responses.create`` call serves, by its accounting stage.
# On this path ``image_generation`` is always the vision brief that precedes a drawing
# call; the drawing calls themselves are recorded in image/generation.py.
_IMAGE_ROLE_BY_RESPONSES_STAGE = {
    STAGE_IMAGE_ANALYSIS: "image_analysis",
    STAGE_IMAGE_VALIDATION: "image_validation",
    STAGE_IMAGE_RECONSTRUCTION: "image_reconstruction",
    STAGE_IMAGE_GENERATION: "image_generation_vision",
}
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal, read_response_field


IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"RIFF",
)

def detect_image_mime_type(image_bytes: bytes | None) -> str | None:
    if not isinstance(image_bytes, (bytes, bytearray)):
        return None
    payload = bytes(image_bytes)
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if payload.startswith(b"BM"):
        return "image/bmp"
    return None


def is_supported_image_bytes(image_bytes: bytes | None) -> bool:
    if not isinstance(image_bytes, (bytes, bytearray)) or len(image_bytes) < 8:
        return False
    payload = bytes(image_bytes)
    return any(payload.startswith(signature) for signature in IMAGE_SIGNATURES)


def clamp_score(value: object) -> float:
    if isinstance(value, (int, float, str)):
        numeric_input: int | float | str = value
    else:
        return 0.0
    try:
        numeric_value = float(numeric_input)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(numeric_value, 1.0))


def is_retryable_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in {408, 409, 429}:
        return True
    if isinstance(status_code, int) and status_code >= 500:
        return True
    return exc.__class__.__name__ in {"APIConnectionError", "APITimeoutError", "RateLimitError", "InternalServerError"}


def extract_unsupported_parameter_name(error_message: str) -> str | None:
    markers = (
        "Unsupported parameter: '",
        "Unknown parameter: '",
        "unexpected keyword argument '",
        # Spec 062 FR-006, measured 2026-11-07: the 2.5 image models answer
        # "The model 'gpt-image-2.5-flare' does not support the 'input_fidelity' parameter."
        # The capability table keeps such a parameter out of the request; this marker only
        # lets the last-resort retry recognise the wording if a new model surprises it.
        "does not support the '",
    )
    for marker in markers:
        if marker not in error_message:
            continue
        tail = error_message.split(marker, 1)[1]
        return tail.split("'", 1)[0]
    return None


def provider_error_code(exc: BaseException) -> str:
    """The provider's own error code when the SDK carries one, else the exception class name.

    Same rule as ``pipeline/glossary_phase.py::_error_code``: a typed code when there is
    one, the class name otherwise. OpenAI-compatible SDK errors expose ``code`` (for a
    rejected parameter, ``"unsupported_parameter"``); a ``TypeError`` from an SDK that does
    not know the keyword has none.
    """

    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return type(exc).__name__


def drop_rejected_optional_param(
    exc: BaseException,
    payload: dict[str, object],
    removable_params: set[str],
    *,
    stage: str,
) -> bool:
    """Remove the optional parameter the provider rejected and say so; ``False`` if none.

    Spec 066 FR-007: the drop used to be silent, so the absence of a log line proved nothing
    about whether the current model rejects ``temperature``. The drop stays per call: the
    next call sends the parameter again (no memory between calls until a run shows the
    rejection is real).
    """

    param = extract_unsupported_parameter_name(str(exc))
    if param is None or param not in removable_params or param not in payload:
        return False
    payload.pop(param, None)
    log_event(
        logging.WARNING,
        "model_call_param_dropped",
        "Провайдер отклонил необязательный параметр запроса; вызов повторяется без него.",
        param=param,
        model=str(payload.get("model") or ""),
        stage=stage,
        error_code=provider_error_code(exc),
    )
    return True


def parse_json_object(raw_text: str, *, empty_message: str, no_json_message: str) -> dict[str, object]:
    text = raw_text.strip()
    if not text:
        raise RuntimeError(empty_message)
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
            last_fence = text.rfind("```")
            if last_fence != -1:
                text = text[:last_fence]
            text = text.strip()
        else:
            text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(no_json_message)
    return json.loads(text[start : end + 1])


def extract_response_text(
    response: object,
    *,
    empty_message: str,
    incomplete_message: str | None = None,
    non_completed_message: str | None = None,
    unsupported_message: str = "Model returned unsupported response shape.",
) -> str:
    response_status = read_response_field(response, "status")
    if response_status == "incomplete":
        raise RuntimeError(incomplete_message or "Model returned incomplete response.")
    if isinstance(response_status, str) and response_status != "completed":
        raise RuntimeError(non_completed_message or f"Model returned unexpected response status: {response_status}.")

    traversal = collect_response_text_traversal(response, unsupported_message=unsupported_message)
    if traversal.collected_texts:
        return "\n".join(traversal.collected_texts)
    if (
        traversal.raw_output_text is not None
        or not traversal.saw_output_items
        or traversal.saw_supported_text_shape
        or traversal.saw_empty_content_container
    ):
        raise RuntimeError(empty_message)
    raise RuntimeError(unsupported_message)


def extract_model_response_error_code(exc: Exception | str) -> str | None:
    message = str(exc).strip().lower()
    if not message:
        return None
    if "incomplete" in message:
        return "incomplete_response"
    if "non-completed" in message or "unexpected response status" in message:
        return "non_completed_response"
    if "unsupported response shape" in message:
        return "unsupported_response_shape"
    if "did not return json" in message:
        return "no_json_object"
    if "invalid json" in message or "невалидный json" in message:
        return "invalid_json_object"
    if "empty output" in message or "did not return text" in message:
        return "empty_response"
    return None


def call_responses_create_with_retry(
    client,
    request_payload: dict[str, object],
    *,
    max_retries: int,
    retryable_error_predicate,
    max_backoff_seconds: float = 4.0,
    budget=None,
    retryable_optional_params: set[str] | None = None,
    usage_stage: str = STAGE_UNATTRIBUTED,
):
    """Single choke point for every ``responses.create`` the product makes.

    Text generation, paragraph-boundary review, image analysis/validation/reconstruction
    and the vision leg of image generation all land here, which is why token/cost
    accounting is recorded here rather than in each caller: one recording point covers
    every operation (translate, literary edit, proofreading, images) at once.
    """

    def ensure_budget_available() -> None:
        if budget is None:
            return
        ensure_available = getattr(budget, "ensure_available", None)
        if callable(ensure_available):
            ensure_available("responses.create")

    def consume_budget() -> None:
        if budget is None:
            return
        budget.consume("responses.create")

    current_payload = dict(request_payload)
    removable_optional_params = set(retryable_optional_params or {"timeout", "temperature"})
    for attempt in range(1, max_retries + 1):
        while True:
            try:
                ensure_budget_available()
                response = client.responses.create(**current_payload)
            except TypeError as exc:
                if drop_rejected_optional_param(exc, current_payload, removable_optional_params, stage=usage_stage):
                    continue
                raise
            except Exception as exc:
                if drop_rejected_optional_param(exc, current_payload, removable_optional_params, stage=usage_stage):
                    continue
                should_retry = attempt < max_retries and retryable_error_predicate(exc)
                if not should_retry:
                    consume_budget()
                    raise
                time.sleep(min(2 ** (attempt - 1), max_backoff_seconds))
                break
            else:
                consume_budget()
                record_model_call_usage(
                    stage=usage_stage,
                    response=response,
                    model=str(current_payload.get("model") or ""),
                    image_role=_IMAGE_ROLE_BY_RESPONSES_STAGE.get(usage_stage, ""),
                )
                return response
    raise RuntimeError("Responses retry loop exhausted unexpectedly.")
