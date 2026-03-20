import json
import time
from collections.abc import Iterable, Mapping


IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"RIFF",
)

_SUPPORTED_RESPONSE_TEXT_TYPES = {"output_text", "text"}


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
    try:
        numeric_value = float(value)
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


def _read_response_field(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _coerce_response_text_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    nested_value = _read_response_field(value, "value")
    if isinstance(nested_value, str):
        return nested_value
    return None


def _extract_text_from_content_item(content_item: object) -> tuple[str | None, bool]:
    item_type = _read_response_field(content_item, "type")
    if item_type not in _SUPPORTED_RESPONSE_TEXT_TYPES:
        return None, False
    text_value = _coerce_response_text_value(_read_response_field(content_item, "text"))
    if text_value is None:
        raise RuntimeError("Model returned unsupported response shape.")
    return text_value, True


def extract_response_text(
    response: object,
    *,
    empty_message: str,
    incomplete_message: str | None = None,
    non_completed_message: str | None = None,
    unsupported_message: str = "Model returned unsupported response shape.",
) -> str:
    response_status = _read_response_field(response, "status")
    if response_status == "incomplete":
        raise RuntimeError(incomplete_message or "Model returned incomplete response.")
    if isinstance(response_status, str) and response_status != "completed":
        raise RuntimeError(non_completed_message or f"Model returned unexpected response status: {response_status}.")

    output_text = getattr(response, "output_text", None)
    if output_text is not None:
        if not isinstance(output_text, str):
            raise RuntimeError(unsupported_message)
        if output_text.strip():
            return output_text

    output_items = _read_response_field(response, "output")
    if output_items is None:
        raise RuntimeError(empty_message)
    if isinstance(output_items, (str, bytes)) or not isinstance(output_items, Iterable):
        raise RuntimeError(unsupported_message)

    collected_texts: list[str] = []
    saw_supported_text_shape = False

    for output_item in output_items:
        direct_text, direct_supported = _extract_text_from_content_item(output_item)
        if direct_supported:
            saw_supported_text_shape = True
            if direct_text:
                collected_texts.append(direct_text)
            continue

        content_items = _read_response_field(output_item, "content")
        if content_items is None:
            continue
        if isinstance(content_items, (str, bytes)) or not isinstance(content_items, Iterable):
            raise RuntimeError(unsupported_message)

        for content_item in content_items:
            extracted_text, supported = _extract_text_from_content_item(content_item)
            if not supported:
                continue
            saw_supported_text_shape = True
            if extracted_text:
                collected_texts.append(extracted_text)

    if collected_texts:
        return "\n".join(collected_texts)
    if saw_supported_text_shape:
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
    timeout_removed = False
    for attempt in range(1, max_retries + 1):
        try:
            ensure_budget_available()
            response = client.responses.create(**current_payload)
        except TypeError as exc:
            if "timeout" in str(exc) and "timeout" in current_payload:
                current_payload.pop("timeout", None)
                timeout_removed = True
                continue
            raise
        except Exception as exc:
            should_retry = attempt < max_retries and retryable_error_predicate(exc)
            if not should_retry:
                consume_budget()
                raise
            time.sleep(min(2 ** (attempt - 1), max_backoff_seconds))
        else:
            consume_budget()
            return response
    if timeout_removed:
        ensure_budget_available()
        response = client.responses.create(**current_payload)
        consume_budget()
        return response
    raise RuntimeError("Responses retry loop exhausted unexpectedly.")