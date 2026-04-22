from typing import Any


def coerce_required_text_field(job: Any, field_name: str, *, allow_blank: bool = True) -> str:
    value = job[field_name]
    if value is None:
        raise ValueError(f"{field_name} is None")
    text = str(value)
    if not allow_blank and not text.strip():
        raise ValueError(f"{field_name} is empty")
    return text


def coerce_optional_string_list(job: Any, field_name: str) -> list[str] | None:
    value = job.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise TypeError(f"{field_name} must be a non-empty string list")
    return list(value)


def coerce_optional_bool(job: Any, field_name: str) -> bool | None:
    value = job.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise TypeError(f"{field_name} must be a boolean")


def coerce_optional_text_field(job: Any, field_name: str) -> str | None:
    value = job.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def coerce_required_int_field(job: Any, field_name: str) -> int:
    value = job[field_name]
    if value is None:
        raise ValueError(f"{field_name} is None")
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"{field_name} must be an integer or numeric string")


def coerce_job_kind(job: Any) -> str:
    value = job.get("job_kind", "llm")
    if not isinstance(value, str):
        raise TypeError("job_kind must be a string")
    normalized = value.strip() or "llm"
    if normalized not in {"llm", "passthrough"}:
        raise ValueError(f"Unsupported job_kind: {normalized}")
    return normalized


def parse_processing_job(*, job: Any, payload_factory: Any) -> Any:
    job_kind = coerce_job_kind(job)
    target_chars = coerce_required_int_field(job, "target_chars")
    context_chars = coerce_required_int_field(job, "context_chars")
    target_text = coerce_required_text_field(job, "target_text", allow_blank=False)
    target_text_with_markers = coerce_optional_text_field(job, "target_text_with_markers") or target_text
    paragraph_ids = coerce_optional_string_list(job, "paragraph_ids")
    structural_roles = coerce_optional_string_list(job, "structural_roles")
    context_before = coerce_required_text_field(job, "context_before")
    context_after = coerce_required_text_field(job, "context_after")
    toc_dominant = coerce_optional_bool(job, "toc_dominant")
    toc_paragraph_count = int(job.get("toc_paragraph_count", 0) or 0)
    paragraph_count = int(job.get("paragraph_count", 0) or 0)
    return payload_factory(
        job_kind=job_kind,
        target_chars=target_chars,
        context_chars=context_chars,
        target_text=target_text,
        target_text_with_markers=target_text_with_markers,
        paragraph_ids=paragraph_ids,
        context_before=context_before,
        context_after=context_after,
        structural_roles=structural_roles,
        toc_dominant=bool(toc_dominant),
        toc_paragraph_count=toc_paragraph_count,
        paragraph_count=paragraph_count,
    )


def is_marker_mode_enabled(context: Any, payload: Any) -> bool:
    return bool(context.app_config.get("enable_paragraph_markers", False)) and bool(payload.paragraph_ids)