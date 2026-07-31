from __future__ import annotations

from collections import Counter
from collections.abc import Iterator, Mapping, Sequence

from ._constants import _DOCX_IMAGE_PLACEHOLDER_PATTERN
from ._models import CleanupBlock, CleanupChunk, ReaderCleanupConfig
from ._utils import _coerce_int


def _build_failed_chunk_diagnostics(
    *,
    chunk: CleanupChunk,
    config: ReaderCleanupConfig,
    request_payload_char_count: int,
    raw_response: str,
    parse_error_message: str,
    retry_attempted: bool,
    retry_status: str,
    retry_error: str,
    repair_attempted: bool,
    repair_status: str,
    repair_error: str,
) -> dict[str, object]:
    stripped_response = str(raw_response or "").strip()
    return {
        "chunk_index": chunk.chunk_index,
        "primary_block_id_range": {
            "first": chunk.blocks[0].block_id if chunk.blocks else "",
            "last": chunk.blocks[-1].block_id if chunk.blocks else "",
        },
        "cleanup_model_selector": config.model,
        "request_payload_char_count": request_payload_char_count,
        "approx_prompt_input_char_count": request_payload_char_count,
        "raw_response_empty": not bool(stripped_response),
        "raw_response_char_count": len(raw_response or ""),
        "raw_response_preview": _preview_text(raw_response, limit=1000),
        "parse_error_message": parse_error_message,
        "retry_attempted": retry_attempted,
        "retry_status": retry_status,
        "retry_error": retry_error,
        "repair_attempted": repair_attempted,
        "repair_status": repair_status,
        "repair_error": repair_error,
    }


def _preview_text(value: object, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _build_anchor_repair_request_payload(
    *,
    chunk: CleanupChunk,
    anchors: Sequence[Mapping[str, str]],
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    from .service import _build_chunk_request_payload  # noqa: PLC0415  local import avoids load-time cycle
    payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
    payload.update(
        {
            "pass_name": "anchor_repair",
            "anchor_targets": [dict(anchor) for anchor in anchors],
            "anchor_window_block_ids": [block.block_id for block in chunk.blocks],
        }
    )
    return payload


def _build_cleanup_stats(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
) -> dict[str, object]:
    total_non_whitespace_chars = sum(block.non_whitespace_char_count for block in blocks)
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    proposed_cleanup_operation_count = sum(
        _coerce_int(
            entry.get("proposed_cleanup_operation_count", entry.get("proposed_delete_block_count")),
            default=0,
            minimum=0,
        )
        for entry in chunk_results
    )
    proposed_delete_block_count = sum(
        _coerce_int(entry.get("proposed_delete_block_count"), default=0, minimum=0) for entry in chunk_results
    )
    return {
        "raw_block_count": len(blocks),
        "raw_char_count": len(raw_markdown),
        "cleanup_chunk_count": len(chunk_results),
        "failed_chunk_count": failed_chunk_count,
        "proposed_cleanup_operation_count": proposed_cleanup_operation_count,
        "proposed_delete_block_count": proposed_delete_block_count,
        "accepted_cleanup_operation_count": len(accepted_cleanup_operations),
        "accepted_delete_block_count": len(accepted_delete_blocks),
        "ignored_cleanup_operation_count": len(ignored_cleanup_operations),
        "ignored_delete_block_count": len(ignored_cleanup_operations),
        "deleted_non_whitespace_char_count": deleted_char_count,
        "deleted_char_ratio": 0.0 if total_non_whitespace_chars <= 0 else round(deleted_char_count / total_non_whitespace_chars, 6),
    }


def _extract_docx_image_placeholder_ids(text: str) -> list[str]:
    ids: list[str] = []
    for match in _DOCX_IMAGE_PLACEHOLDER_PATTERN.finditer(str(text or "")):
        placeholder = match.group(0)
        image_id = placeholder[len("[[DOCX_IMAGE_") : -len("]]")]
        ids.append(image_id)
    return ids


def _docx_image_placeholder_counts(text: str) -> Counter[str]:
    return Counter(_extract_docx_image_placeholder_ids(text))


def _missing_docx_image_placeholder_ids(*, raw_markdown: str, cleaned_markdown: str) -> list[str]:
    """Image anchor ids present in the source markdown but absent from the cleaned one."""
    before_counts = _docx_image_placeholder_counts(raw_markdown)
    after_counts = _docx_image_placeholder_counts(cleaned_markdown)
    return sorted((before_counts - after_counts).elements())


def _docx_image_anchor_source_block_ids(
    *,
    raw_blocks: Sequence[CleanupBlock],
    image_ids: Sequence[str],
) -> set[str]:
    """Ids of the source blocks the given anchors came from.

    This is one half of anchor attribution: it says WHERE the lost anchor lived. The other
    half — which operation wrote over that block — is the write set
    ``_apply_cleanup_operations`` records per applied operation. An operation's declared
    ``block_id``/``next_id`` is NOT that write set: ``normalize_heading_boundary`` can
    absorb the following block or rewrite the preceding one after a join, and a join moves
    a block's characters into a slot another operation may later overwrite.
    """
    wanted = {str(image_id) for image_id in image_ids if str(image_id).strip()}
    if not wanted:
        return set()
    return {
        block.block_id
        for block in raw_blocks
        if wanted.intersection(_extract_docx_image_placeholder_ids(block.text))
    }


def _reconcile_docx_image_placeholders(
    *,
    raw_markdown: str,
    cleaned_markdown: str,
    raw_blocks: Sequence[CleanupBlock],
) -> tuple[str, dict[str, object]]:
    """Verify every image anchor survived; discard the whole cleanup if one did not.

    Spec 052 item 5. This used to re-append a lost anchor at the END of the document: the
    count reconciled, the report went green, and a chapter-3 figure landed after the
    bibliography. "Nothing was lost" was true of the id list and false of the book.

    There is no correct place to put an anchor whose position is unknown, so this refuses
    to guess. The caller has already had its chance to reject the specific operation that
    lost the anchor (``service._reject_operations_losing_docx_image_anchors``); by the
    time an anchor is still missing here, the cleanup as a whole cannot be delivered
    without relocating an image, and the fail-closed answer is to deliver the original
    markdown unchanged. A cleanup worth 12-44 operations is not worth a misplaced figure.
    """
    before_counts = _docx_image_placeholder_counts(raw_markdown)
    after_counts = _docx_image_placeholder_counts(cleaned_markdown)
    missing_ids = sorted((before_counts - after_counts).elements())
    extra_ids = sorted((after_counts - before_counts).elements())
    if not missing_ids:
        return cleaned_markdown, {
            "before_image_id_count": sum(before_counts.values()),
            "after_image_id_count": sum(after_counts.values()),
            "missing_image_ids": [],
            # Owned by the caller, not by this function: it means "still missing after the
            # anchor-repair pass ran", and only ``run_reader_cleanup`` knows whether that
            # pass ran. This function reconciles a single application step.
            "missing_after_repair": [],
            "extra_image_ids": extra_ids,
            "reinserted_image_ids": [],
            "cleanup_discarded_for_missing_image_ids": False,
            "lost_image_source_block_ids": [],
            "touched": bool(extra_ids),
        }

    restored_counts = _docx_image_placeholder_counts(raw_markdown)
    return raw_markdown, {
        "before_image_id_count": sum(before_counts.values()),
        "after_image_id_count": sum(restored_counts.values()),
        "missing_image_ids": missing_ids,
        # Nothing is missing after the discard — the delivered markdown IS the source.
        # ``run_reader_cleanup`` overwrites this if a later anchor-repair pass loses one.
        "missing_after_repair": [],
        "extra_image_ids": extra_ids,
        # Never again: an anchor is never re-inserted at a position it did not come from.
        "reinserted_image_ids": [],
        "cleanup_discarded_for_missing_image_ids": True,
        "lost_image_source_block_ids": sorted(
            _docx_image_anchor_source_block_ids(raw_blocks=raw_blocks, image_ids=missing_ids)
        ),
        "touched": True,
    }


def _image_reconciliation_warnings(image_reconciliation: Mapping[str, object]) -> list[str]:
    missing = [str(item) for item in image_reconciliation.get("missing_image_ids") or [] if str(item).strip()]
    remaining = [str(item) for item in image_reconciliation.get("missing_after_repair") or [] if str(item).strip()]
    extra = [str(item) for item in image_reconciliation.get("extra_image_ids") or [] if str(item).strip()]
    warnings: list[str] = []
    if missing:
        warnings.append(f"reader_cleanup_image_ids_lost_cleanup_discarded:{len(missing)}")
    if remaining:
        warnings.append(f"reader_cleanup_image_ids_missing_after_reconcile:{len(remaining)}")
    if extra:
        warnings.append(f"reader_cleanup_image_ids_extra_after_cleanup:{len(extra)}")
    return warnings


def _extract_http_status_code(exc: BaseException) -> int | None:
    visited: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int):
            return status_code
        response = getattr(current, "response", None)
        response_status_code = getattr(response, "status_code", None)
        if isinstance(response_status_code, int):
            return response_status_code
        current = current.__cause__ or current.__context__
    return None


def _is_auth_or_credential_error(exc: BaseException) -> bool:
    status_code = _extract_http_status_code(exc)
    if status_code in {401, 403}:
        return True
    return any(type(current).__name__ in {"AuthenticationError", "PermissionDeniedError"} for current in _iter_exception_chain(exc))


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    visited: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _failed_chunk_ratio(chunk_results: Sequence[Mapping[str, object]]) -> float:
    if not chunk_results:
        return 0.0
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    return failed_chunk_count / len(chunk_results)


def _failed_chunk_ratio_exceeds_threshold(
    *,
    chunk_results: Sequence[Mapping[str, object]],
    config: ReaderCleanupConfig,
) -> bool:
    """True when the failed-chunk share is ABOVE ``max_failed_chunk_ratio``.

    Strictly above, and both the setting's name ("max") and every message about it say so.
    The comparison used to be ``>=``, which meant a ten-chunk document losing exactly one
    chunk to a transient error hit ``0.1 >= 0.1`` and had its entire cleanup cancelled,
    while the notice told the owner the rate was "above the allowed 10.0%" — it was equal
    to it. Worse, ``max_failed_chunk_ratio = 0.0`` aborted every run, including runs with
    zero failures. The threshold is the largest failure share still tolerated.

    ``1.0`` therefore means the abort is OFF, and says so here rather than leaving it as an
    arithmetic accident (a share can never exceed 1.0). Under the old ``>=`` it meant
    "abort only when EVERY chunk failed"; that reading is gone and is not coming back as a
    ratio, because no fixed number expresses "all but not almost all" — the largest partial
    share is ``(n-1)/n``, which depends on the document. Nothing needs it: every threshold
    below 1.0 already aborts a total failure, and the one caller that sets 1.0
    (``scripts/run-reader-cleanup-structural-matrix.py``, a research sweep that deliberately
    drives models into failing chunks) wants the abort disabled, not narrowed. That sweep
    reads the failure counts back out of each cell's score instead.
    """
    if not chunk_results:
        return False
    threshold = min(1.0, max(0.0, float(config.max_failed_chunk_ratio)))
    if threshold >= 1.0:
        return False
    return _failed_chunk_ratio(chunk_results) > threshold


def _serialize_cleanup_settings(config: ReaderCleanupConfig) -> dict[str, object]:
    return {
        "model_selector": config.model,
        "chunk_size": config.chunk_size,
        "overlap_blocks_before": config.overlap_blocks_before,
        "overlap_blocks_after": config.overlap_blocks_after,
        "global_plan_enabled": config.global_plan_enabled,
        "allowed_operations": sorted(config.allowed_operations),
        "max_failed_chunk_ratio": config.max_failed_chunk_ratio,
    }


def _build_reader_cleanup_report_payload(
    *,
    raw_markdown: str,
    config: ReaderCleanupConfig,
    blocks: Sequence[CleanupBlock],
    global_plan: Mapping[str, object],
    warnings: Sequence[str],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]] = (),
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
    changed: bool,
    model_resolution: Mapping[str, object] | None = None,
    image_reconciliation: Mapping[str, object] | None = None,
    failure: Mapping[str, object] | None = None,
) -> dict[str, object]:
    stats = _build_cleanup_stats(
        raw_markdown=raw_markdown,
        blocks=blocks,
        accepted_delete_blocks=accepted_delete_blocks,
        accepted_cleanup_operations=accepted_cleanup_operations,
        ignored_cleanup_operations=ignored_cleanup_operations,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
    )
    report_payload = {
        "version": 1,
        "policy": config.policy,
        "model": config.model,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "stage_status": "failed" if failure is not None else "completed",
        "changed": changed,
        "warnings": list(warnings),
        "stats": stats,
        "global_plan": dict(global_plan),
        "model_resolution": dict(model_resolution or {}),
        "image_reconciliation": dict(image_reconciliation or {}),
        "accepted_cleanup_operations": list(accepted_cleanup_operations),
        "accepted_delete_blocks": list(accepted_delete_blocks),
        "ignored_cleanup_operations": list(ignored_cleanup_operations),
        "ignored_delete_blocks": list(ignored_cleanup_operations),
        "heading_boundary_application_diagnostics": _build_heading_boundary_application_diagnostics(
            accepted_cleanup_operations=accepted_cleanup_operations,
            ignored_cleanup_operations=ignored_cleanup_operations,
        ),
        "chunk_results": [dict(entry) for entry in chunk_results],
    }
    if failure is not None:
        report_payload["failure"] = dict(failure)
    return report_payload


def _build_heading_boundary_application_diagnostics(
    *,
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    accepted_heading_operations = [
        dict(entry) for entry in accepted_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_heading_operations = [
        dict(entry) for entry in ignored_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_reason_counts: Counter[str] = Counter(
        str(entry.get("ignored_reason") or "unknown") for entry in ignored_heading_operations
    )
    return {
        "accepted_count": len(accepted_heading_operations),
        "ignored_count": len(ignored_heading_operations),
        "ignored_reason_counts": dict(sorted(ignored_reason_counts.items())),
        "ignored_examples": [
            _build_heading_boundary_diagnostic_example(entry)
            for entry in ignored_heading_operations[:5]
        ],
    }


def _build_heading_boundary_diagnostic_example(entry: Mapping[str, object]) -> dict[str, object]:
    preview = str(entry.get("raw_text_preview") or entry.get("evidence_before") or "").replace("\n", " ").strip()
    if len(preview) > 180:
        preview = preview[:177].rstrip() + "..."
    heading = str(entry.get("heading_substring") or "").replace("\n", " ").strip()
    body = str(entry.get("body_substring") or "").replace("\n", " ").strip()
    if len(body) > 180:
        body = body[:177].rstrip() + "..."
    return {
        "chunk_index": _coerce_int(entry.get("chunk_index"), default=0, minimum=0),
        "ignored_reason": str(entry.get("ignored_reason") or "unknown"),
        "reason": str(entry.get("reason") or ""),
        "preview": preview,
        "heading_substring": heading,
        "body_substring_preview": body,
    }
