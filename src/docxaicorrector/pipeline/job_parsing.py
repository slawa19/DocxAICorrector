from typing import Any

from docxaicorrector.core.models import BACK_MATTER_SECTION_VALUES, PARAGRAPH_REGION_VALUES


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


def coerce_paragraph_regions(job: Any) -> list[str] | None:
    """Spec 059 A-II: the per-paragraph region list, validated against a CLOSED vocabulary.

    An unknown name raises rather than being folded into either answer. A region the pipeline
    does not define carries no meaning, and silently reading it as prose (or as apparatus)
    would let the vocabulary drift on one side of the contract while the other side kept
    deciding on it — which is the exact failure the shared constants in ``core.models`` exist
    to prevent.
    """
    regions = coerce_optional_string_list(job, "paragraph_regions")
    if regions is None:
        return None
    unknown = sorted({region for region in regions if region not in PARAGRAPH_REGION_VALUES})
    if unknown:
        raise ValueError(f"paragraph_regions carries unknown region names: {unknown}")
    return regions


def coerce_back_matter_section(job: Any) -> str | None:
    """Spec 063 FR-011: which back-matter section the block belongs to, from a CLOSED
    vocabulary, for the same reason ``coerce_paragraph_regions`` closes its own: a policy
    that keeps text in the source language must never be keyed on a name nobody defined."""
    value = coerce_optional_text_field(job, "back_matter_section")
    if value is None:
        return None
    if value not in BACK_MATTER_SECTION_VALUES:
        raise ValueError(f"back_matter_section carries an unknown section name: {value!r}")
    return value


def coerce_paragraph_id_subset(job: Any, field_name: str, *, paragraph_ids: list[str] | None) -> list[str] | None:
    """A per-paragraph mark carried as ids (spec 067 FR-001): every id must name a paragraph of
    THIS block. An id the block does not have would mark nothing on one side of the contract
    while the other side counted it, so it raises rather than being dropped."""
    values = coerce_optional_string_list(job, field_name)
    if values is None:
        return None
    unknown = sorted(set(values) - set(paragraph_ids or ()))
    if unknown:
        raise ValueError(f"{field_name} names paragraphs outside the block: {unknown}")
    return values


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


def _require_parallel_to_paragraph_ids(
    paragraph_ids: list[str] | None,
    *,
    structural_roles: list[str] | None,
    paragraph_regions: list[str] | None,
) -> None:
    """Spec 059 A-II: "parallel to ``paragraph_ids``" is a CONTRACT, so it is checked.

    A short list is the quiet failure, not a loud one: ``["back_matter"]`` against two
    paragraphs — the second of them prose — reads to
    ``block_execution.payload_contains_prose`` as "this block is all apparatus", and the
    block ships its own source text without a word. The shipped producer keeps the lists in
    step; nothing until now REQUIRED it, and a contract that depends on one producer's good
    behaviour is not a contract.

    Only checked when both lists are present. Absence is a different statement — "this
    caller resolved nothing" — and it is answered elsewhere, conservatively.
    """
    if paragraph_ids is None:
        return
    expected = len(paragraph_ids)
    for field_name, values in (
        ("structural_roles", structural_roles),
        ("paragraph_regions", paragraph_regions),
    ):
        if values is not None and len(values) != expected:
            raise ValueError(
                f"{field_name} must be parallel to paragraph_ids: "
                f"{len(values)} entries against {expected} paragraphs"
            )


def parse_processing_job(*, job: Any, payload_factory: Any) -> Any:
    job_kind = coerce_job_kind(job)
    target_chars = coerce_required_int_field(job, "target_chars")
    context_chars = coerce_required_int_field(job, "context_chars")
    target_text = coerce_required_text_field(job, "target_text", allow_blank=False)
    target_text_with_markers = coerce_optional_text_field(job, "target_text_with_markers") or target_text
    paragraph_ids = coerce_optional_string_list(job, "paragraph_ids")
    structural_roles = coerce_optional_string_list(job, "structural_roles")
    paragraph_regions = coerce_paragraph_regions(job)
    back_matter_section = coerce_back_matter_section(job)
    notes_in_body_paragraph_ids = coerce_paragraph_id_subset(
        job, "notes_in_body_paragraph_ids", paragraph_ids=paragraph_ids
    )
    _require_parallel_to_paragraph_ids(
        paragraph_ids,
        structural_roles=structural_roles,
        paragraph_regions=paragraph_regions,
    )
    context_before = coerce_required_text_field(job, "context_before")
    context_after = coerce_required_text_field(job, "context_after")
    narration_include = coerce_optional_bool(job, "narration_include")
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
        paragraph_regions=paragraph_regions,
        back_matter_section=back_matter_section,
        notes_in_body_paragraph_ids=notes_in_body_paragraph_ids,
        narration_include=True if narration_include is None else narration_include,
        toc_dominant=bool(toc_dominant),
        toc_paragraph_count=toc_paragraph_count,
        paragraph_count=paragraph_count,
    )


def is_marker_mode_enabled(context: Any, payload: Any) -> bool:
    return bool(context.app_config.get("enable_paragraph_markers", False)) and bool(payload.paragraph_ids)
