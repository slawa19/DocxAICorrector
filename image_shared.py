import json
import time

from openai_response_utils import collect_response_text_traversal, read_response_field


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
    )
    for marker in markers:
        if marker not in error_message:
            continue
        tail = error_message.split(marker, 1)[1]
        return tail.split("'", 1)[0]
    return None


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
):
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
                unsupported_param = extract_unsupported_parameter_name(str(exc))
                if unsupported_param in removable_optional_params and unsupported_param in current_payload:
                    current_payload.pop(unsupported_param, None)
                    continue
                raise
            except Exception as exc:
                unsupported_param = extract_unsupported_parameter_name(str(exc))
                if unsupported_param in removable_optional_params and unsupported_param in current_payload:
                    current_payload.pop(unsupported_param, None)
                    continue
                should_retry = attempt < max_retries and retryable_error_predicate(exc)
                if not should_retry:
                    consume_budget()
                    raise
                time.sleep(min(2 ** (attempt - 1), max_backoff_seconds))
                break
            else:
                consume_budget()
                return response
    raise RuntimeError("Responses retry loop exhausted unexpectedly.")
