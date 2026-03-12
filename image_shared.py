import json
import time


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
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise RuntimeError(no_json_message)
    return json.loads(text[start : end + 1])


def call_responses_create_with_retry(
    client,
    request_payload: dict[str, object],
    *,
    max_retries: int,
    retryable_error_predicate,
    max_backoff_seconds: float = 4.0,
    budget=None,
):
    current_payload = dict(request_payload)
    timeout_removed = False
    for attempt in range(1, max_retries + 1):
        try:
            if budget is not None:
                budget.consume("responses.create")
            return client.responses.create(**current_payload)
        except TypeError as exc:
            if "timeout" in str(exc) and "timeout" in current_payload:
                current_payload.pop("timeout", None)
                timeout_removed = True
                continue
            raise
        except Exception as exc:
            if attempt >= max_retries or not retryable_error_predicate(exc):
                raise
            time.sleep(min(2 ** (attempt - 1), max_backoff_seconds))
    if timeout_removed:
        if budget is not None:
            budget.consume("responses.create")
        return client.responses.create(**current_payload)
    raise RuntimeError("Responses retry loop exhausted unexpectedly.")