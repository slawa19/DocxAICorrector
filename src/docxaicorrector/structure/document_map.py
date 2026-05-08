from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from math import isclose
import json
import logging
from pathlib import Path
from queue import Queue
import re
from statistics import median
from threading import Thread
import time
from typing import Any, Callable, Protocol, cast

from docxaicorrector.core.constants import PROMPTS_DIR, RUN_DIR
from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, ParagraphUnit
from docxaicorrector.core.models import DocumentMapOutlineEntry, DocumentMapReviewZone, DocumentMapTocEntry, DocumentMapTocRegion
from docxaicorrector.generation._generation import normalize_model_output
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal
from docxaicorrector.image.shared import call_responses_create_with_retry
from docxaicorrector.runtime.artifact_retention import STRUCTURE_MAPS_MAX_AGE_SECONDS, STRUCTURE_MAPS_MAX_COUNT, prune_artifact_dir


_TOC_HEADER_VALUES = {"contents", "table of contents", "содержание"}
_TOC_SUFFIX_PATTERN = re.compile(r"\.{2,}\s*\d+\s*$")
_ISOLATED_MARKER_PATTERN = re.compile(r"^(?:\s*[•●\-*]\s*|\s*\d+[\.)]\s*)$")
_SCRIPTURE_REFERENCE_PATTERN = re.compile(r"\b(?:[A-Za-zА-Яа-яЁё]+)\s+\d+:\d+(?:-\d+)?\b")
_VALID_DOCUMENT_MAP_ROLES = frozenset({"heading", "body", "caption", "epigraph", "attribution", "toc_entry", "toc_header", "dedication", "list"})
_VALID_DOCUMENT_MAP_CONFIDENCES = frozenset({"high", "medium", "low"})
_VALID_REVIEW_ZONE_SEVERITIES = frozenset({"info", "warning", "critical"})
_TIMEOUT_ERROR_NAMES = {"APITimeoutError", "TimeoutError"}
DOCUMENT_MAP_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "document_map_system.txt"
DOCUMENT_MAP_PROMPT_VERSION = 1
DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION = 1
_DOCUMENT_MAP_MALFORMED_DIR = RUN_DIR / "document_maps"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentMapParagraphDescriptor:
    logical_index: int
    text_preview: str
    text_length: int
    style_cluster_id: int | None
    is_bold: bool
    is_centered: bool
    is_all_caps: bool
    font_size_z_score: float | None
    page_number: int | None
    position_fraction: float
    vertical_gap_before_pt: float | None
    is_repeated_across_pages: bool
    is_likely_page_number: bool
    is_isolated_marker: bool
    toc_pattern_hint: bool
    scripture_reference_hint: bool
    explicit_heading_level: int | None

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "i": self.logical_index,
            "t": self.text_preview,
            "len": self.text_length,
            "sty": self.style_cluster_id,
            "b": self.is_bold,
            "ctr": self.is_centered,
            "caps": self.is_all_caps,
            "sz": self.font_size_z_score,
            "pg": self.page_number,
            "pos": self.position_fraction,
            "gap": self.vertical_gap_before_pt,
            "rep": self.is_repeated_across_pages,
            "pn": self.is_likely_page_number,
            "iso": self.is_isolated_marker,
            "toc": self.toc_pattern_hint,
            "scr": self.scripture_reference_hint,
            "hl": self.explicit_heading_level,
        }


@dataclass(frozen=True)
class DocumentMapProgress:
    event: str
    descriptor_count: int
    sampled_count: int


DocumentMapProgressCallback = Callable[[DocumentMapProgress], None]


class _ResponsesApi(Protocol):
    def create(self, *, model: str, input: list[dict[str, object]], timeout: float) -> Any:
        ...


class _ResponsesCreateClient(Protocol):
    responses: _ResponsesApi


class DocumentMapRequestTimeout(TimeoutError):
    pass


class DocumentMapSchemaError(ValueError):
    pass


def build_document_map(
    paragraphs: list[ParagraphUnit],
    *,
    client: object,
    model: str,
    timeout: float,
    max_input_paragraphs: int,
    max_input_tokens: int,
    preview_chars: int = 120,
    progress_callback: DocumentMapProgressCallback | None = None,
) -> DocumentMap:
    _ = client, timeout
    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=preview_chars)
    sampled_logical_indexes = select_document_map_logical_indexes(
        descriptors,
        max_input_paragraphs=max_input_paragraphs,
        max_input_tokens=max_input_tokens,
    )
    _emit_progress(
        progress_callback,
        DocumentMapProgress(
            event="descriptors_built",
            descriptor_count=len(descriptors),
            sampled_count=len(sampled_logical_indexes),
        ),
    )
    default_document_map = build_default_document_map(
        paragraphs,
        model_used=model,
        max_input_paragraphs=max_input_paragraphs,
        max_input_tokens=max_input_tokens,
        preview_chars=preview_chars,
    )
    sampled_descriptor_set = {int(index) for index in sampled_logical_indexes}
    sampled_descriptors = [descriptor for descriptor in descriptors if descriptor.logical_index in sampled_descriptor_set]
    started_at = time.perf_counter()
    document_map = default_document_map
    if sampled_descriptors and str(model or "").strip():
        try:
            document_map = _generate_document_map_from_ai(
                descriptors=sampled_descriptors,
                all_logical_indexes={descriptor.logical_index for descriptor in descriptors},
                sampled_logical_indexes=sampled_logical_indexes,
                client=client,
                model=model,
                timeout=timeout,
            )
        except Exception as exc:
            _LOGGER.warning("Document map AI generation fell back to deterministic map: %s", exc)
            document_map = default_document_map
    document_map.model_used = str(model or document_map.model_used or "")
    if document_map is default_document_map:
        document_map.processing_time_seconds = max(0.0, time.perf_counter() - started_at)
    _emit_progress(
        progress_callback,
        DocumentMapProgress(
            event="completed",
            descriptor_count=len(descriptors),
            sampled_count=len(sampled_logical_indexes),
        ),
    )
    return document_map


def build_document_map_paragraph_descriptors(
    paragraphs: list[ParagraphUnit],
    *,
    preview_chars: int = 120,
) -> list[DocumentMapParagraphDescriptor]:
    preview_limit = max(1, int(preview_chars or 120))
    style_cluster_ids = _build_style_cluster_ids(paragraphs)
    font_size_z_scores = _build_font_size_z_scores(paragraphs)
    last_index = max(len(paragraphs) - 1, 1)

    descriptors: list[DocumentMapParagraphDescriptor] = []
    for position, paragraph in enumerate(paragraphs):
        text = str(paragraph.text or "").strip()
        preview = text[:preview_limit].rstrip()
        alpha_chars = [char for char in preview if char.isalpha()]
        descriptors.append(
            DocumentMapParagraphDescriptor(
                logical_index=int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", position))),
                text_preview=preview,
                text_length=len(text),
                style_cluster_id=style_cluster_ids[position],
                is_bold=bool(getattr(paragraph, "is_bold", False)),
                is_centered=getattr(paragraph, "paragraph_alignment", None) == "center",
                is_all_caps=bool(alpha_chars) and preview.upper() == preview,
                font_size_z_score=font_size_z_scores[position],
                page_number=_extract_page_number_hint(text, paragraph),
                position_fraction=round(position / last_index, 3),
                vertical_gap_before_pt=None,
                is_repeated_across_pages=bool(getattr(paragraph, "is_repeated_across_pages", False)),
                is_likely_page_number=bool(getattr(paragraph, "is_likely_page_number", False)),
                is_isolated_marker=_is_isolated_marker_text(text),
                toc_pattern_hint=_is_toc_pattern_hint(text, paragraph),
                scripture_reference_hint=_is_scripture_reference_text(text),
                explicit_heading_level=(
                    getattr(paragraph, "heading_level", None)
                    if getattr(paragraph, "heading_source", None) == "explicit"
                    else None
                ),
            )
        )
    return descriptors


def select_document_map_logical_indexes(
    descriptors: list[DocumentMapParagraphDescriptor],
    *,
    max_input_paragraphs: int,
    max_input_tokens: int | None = None,
) -> tuple[int, ...]:
    limit = max(1, int(max_input_paragraphs or 0))
    all_indexes = [descriptor.logical_index for descriptor in descriptors]
    if len(all_indexes) <= limit:
        return _shrink_logical_indexes_to_token_budget(
            descriptors,
            tuple(all_indexes),
            max_input_tokens=max_input_tokens,
        )

    important_indexes = [
        descriptor.logical_index
        for descriptor in descriptors
        if _is_structurally_important_descriptor(descriptor)
    ]
    sampled = sorted(dict.fromkeys(important_indexes))
    if len(sampled) >= limit:
        return _shrink_logical_indexes_to_token_budget(
            descriptors,
            tuple(sampled[:limit]),
            max_input_tokens=max_input_tokens,
        )

    remaining_indexes = [index for index in all_indexes if index not in set(sampled)]
    slots = limit - len(sampled)
    if slots > 0 and remaining_indexes:
        sampled.extend(_select_uniform_indexes(remaining_indexes, slots))
    return _shrink_logical_indexes_to_token_budget(
        descriptors,
        tuple(sorted(dict.fromkeys(sampled))),
        max_input_tokens=max_input_tokens,
    )


def build_default_document_map(
    paragraphs: list[ParagraphUnit],
    *,
    model_used: str = "",
    max_input_paragraphs: int = 6000,
    max_input_tokens: int = 180000,
    preview_chars: int = 120,
) -> DocumentMap:
    descriptors = build_document_map_paragraph_descriptors(paragraphs, preview_chars=preview_chars)
    sampled_logical_indexes = select_document_map_logical_indexes(
        descriptors,
        max_input_paragraphs=max_input_paragraphs,
        max_input_tokens=max_input_tokens,
    )
    paragraph_anchors = {
        descriptor.logical_index: DocumentMapAnchor(role="body", heading_level=None, confidence="low")
        for descriptor in descriptors
    }
    body_start_logical_index = descriptors[0].logical_index if descriptors else 0
    return DocumentMap(
        body_start_logical_index=body_start_logical_index,
        toc_region=None,
        outline=(),
        paragraph_anchors=paragraph_anchors,
        review_zones=(),
        model_used=model_used,
        total_tokens_used=0,
        processing_time_seconds=0.0,
        sampled=len(sampled_logical_indexes) < len(descriptors),
        sampled_logical_indexes=sampled_logical_indexes,
    )


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return DOCUMENT_MAP_SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def _with_request_timeout(client: object, *, timeout: float) -> object:
    with_options = getattr(client, "with_options", None)
    if not callable(with_options):
        return client
    return with_options(timeout=timeout)


def _as_responses_create_client(client: object) -> _ResponsesCreateClient | None:
    responses = getattr(client, "responses", None)
    if responses is None or not hasattr(responses, "create"):
        return None
    return cast(_ResponsesCreateClient, client)


def _generate_document_map_from_ai(
    *,
    descriptors: list[DocumentMapParagraphDescriptor],
    all_logical_indexes: set[int],
    sampled_logical_indexes: tuple[int, ...],
    client: object,
    model: str,
    timeout: float,
) -> DocumentMap:
    timeout_scoped_client = _with_request_timeout(client, timeout=timeout)
    responses_client = _as_responses_create_client(timeout_scoped_client)
    if responses_client is None:
        raise RuntimeError("Unsupported document-map client")

    started_at = time.perf_counter()
    last_schema_error: DocumentMapSchemaError | None = None
    for attempt in range(2):
        schema_error_summary = None if attempt == 0 else str(last_schema_error or "")
        payload_text, total_tokens = _request_document_map_payload(
            client=responses_client,
            model=model,
            timeout=timeout,
            descriptors=descriptors,
            all_logical_indexes=all_logical_indexes,
            sampled_logical_indexes=sampled_logical_indexes,
            schema_error_summary=schema_error_summary,
        )
        try:
            return _parse_document_map_payload(
                payload_text,
                all_logical_indexes=all_logical_indexes,
                sampled_logical_indexes=sampled_logical_indexes,
                model_used=model,
                total_tokens_used=total_tokens,
                processing_time_seconds=max(0.0, time.perf_counter() - started_at),
            )
        except DocumentMapSchemaError as exc:
            last_schema_error = exc
            if attempt == 0:
                continue
            _write_malformed_document_map_output_artifact(
                raw_payload=payload_text,
                schema_error_summary=str(exc),
                model=model,
                sampled_logical_indexes=sampled_logical_indexes,
                descriptors=descriptors,
            )
            raise
    raise RuntimeError("Document map generation failed without a terminal result")


def _write_malformed_document_map_output_artifact(
    *,
    raw_payload: str,
    schema_error_summary: str,
    model: str,
    sampled_logical_indexes: tuple[int, ...],
    descriptors: list[DocumentMapParagraphDescriptor],
) -> str:
    _DOCUMENT_MAP_MALFORMED_DIR.mkdir(parents=True, exist_ok=True)
    artifact_key = hashlib.sha256(
        json.dumps(
            {
                "stage": "document_map_v1",
                "model": model,
                "sampled_logical_indexes": list(sampled_logical_indexes),
                "schema_error_summary": schema_error_summary,
                "raw_payload": raw_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    artifact_path = _DOCUMENT_MAP_MALFORMED_DIR / f"{artifact_key}.malformed.json"
    artifact_path.write_text(
        json.dumps(
            {
                "artifact_kind": "document_map_malformed_output",
                "stage": "document_map_v1",
                "model": model,
                "prompt_version": DOCUMENT_MAP_PROMPT_VERSION,
                "descriptor_schema_version": DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION,
                "descriptor_count": len(descriptors),
                "sampled_logical_indexes": list(sampled_logical_indexes),
                "schema_error_summary": schema_error_summary,
                "raw_payload": raw_payload,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    prune_artifact_dir(
        target_dir=_DOCUMENT_MAP_MALFORMED_DIR,
        max_age_seconds=STRUCTURE_MAPS_MAX_AGE_SECONDS,
        max_count=STRUCTURE_MAPS_MAX_COUNT,
    )
    _LOGGER.warning("Saved malformed document map output artifact: %s", artifact_path)
    return str(artifact_path)


def _request_document_map_payload(
    *,
    client: _ResponsesCreateClient,
    model: str,
    timeout: float,
    descriptors: list[DocumentMapParagraphDescriptor],
    all_logical_indexes: set[int],
    sampled_logical_indexes: tuple[int, ...],
    schema_error_summary: str | None,
) -> tuple[str, int]:
    system_prompt = _load_system_prompt()
    response = _call_document_map_responses_with_timeout(
        client=client,
        request_payload={
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": _build_document_map_user_prompt(
                                descriptors=descriptors,
                                all_logical_indexes=all_logical_indexes,
                                sampled_logical_indexes=sampled_logical_indexes,
                                schema_error_summary=schema_error_summary,
                            ),
                        }
                    ],
                },
            ],
            "timeout": timeout,
        },
        timeout=timeout,
    )
    traversal = collect_response_text_traversal(
        response,
        unsupported_message="Document map response used an unsupported text shape.",
    )
    content = normalize_model_output("\n".join(traversal.collected_texts) if traversal.collected_texts else (traversal.raw_output_text or ""))
    usage = getattr(response, "usage", None)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return content, total_tokens


def _call_document_map_responses_with_timeout(*, client: _ResponsesCreateClient, request_payload: dict[str, object], timeout: float) -> Any:
    result_queue: Queue[tuple[str, object]] = Queue(maxsize=1)

    def _run_request() -> None:
        try:
            response = call_responses_create_with_retry(
                client,
                request_payload,
                max_retries=1,
                retryable_error_predicate=lambda exc: False,
            )
        except Exception as exc:
            result_queue.put(("error", exc))
            return
        result_queue.put(("ok", response))

    worker = Thread(target=_run_request, name="document-map-request", daemon=True)
    worker.start()
    worker.join(timeout=max(0.001, timeout))
    if worker.is_alive():
        raise DocumentMapRequestTimeout(f"Document map request timed out after {timeout:.3f}s.")

    status, payload = result_queue.get_nowait()
    if status == "error":
        raise cast(Exception, payload)
    return payload


def _build_document_map_user_prompt(
    *,
    descriptors: list[DocumentMapParagraphDescriptor],
    all_logical_indexes: set[int],
    sampled_logical_indexes: tuple[int, ...],
    schema_error_summary: str | None,
) -> str:
    font_z_scores = [descriptor.font_size_z_score for descriptor in descriptors if descriptor.font_size_z_score is not None]
    style_cluster_ids = [descriptor.style_cluster_id for descriptor in descriptors if descriptor.style_cluster_id is not None]
    page_numbers = [descriptor.page_number for descriptor in descriptors if descriptor.page_number is not None]
    summary = {
        "total_paragraph_count": len(all_logical_indexes),
        "sampled": len(sampled_logical_indexes) < len(all_logical_indexes),
        "sampled_paragraph_count": len(sampled_logical_indexes),
        "sampled_logical_index_min": min(sampled_logical_indexes) if sampled_logical_indexes else None,
        "sampled_logical_index_max": max(sampled_logical_indexes) if sampled_logical_indexes else None,
        "median_font_size_z_score": None if not font_z_scores else round(float(median(font_z_scores)), 1),
        "dominant_style_cluster_id": None if not style_cluster_ids else Counter(style_cluster_ids).most_common(1)[0][0],
        "page_hint_count": len(page_numbers),
        "max_page_hint": None if not page_numbers else max(page_numbers),
    }
    retry_suffix = ""
    if schema_error_summary:
        retry_suffix = (
            "\n\nPrevious output failed schema validation. Correct the JSON strictly."
            f"\nValidation error summary: {schema_error_summary}"
        )
    return (
        "Return a single JSON object with keys `body_start_logical_index`, `toc_region`, `outline`, `paragraph_anchors`, and `review_zones`. "
        "For `paragraph_anchors`, prefer an object mapping logical indexes to `{role, heading_level, confidence}`; a list of `{i, r, l, c}` is also accepted."
        "\n\nDocument summary:\n"
        f"{json.dumps(summary, ensure_ascii=False)}"
        "\n\nSampled paragraph descriptors:\n"
        f"{json.dumps([descriptor.to_prompt_dict() for descriptor in descriptors], ensure_ascii=False)}"
        f"{retry_suffix}"
    )


def _parse_document_map_payload(
    payload: str | dict[str, object],
    *,
    all_logical_indexes: set[int],
    sampled_logical_indexes: tuple[int, ...],
    model_used: str,
    total_tokens_used: int,
    processing_time_seconds: float,
) -> DocumentMap:
    parsed = json.loads(payload) if isinstance(payload, str) else payload
    if not isinstance(parsed, dict):
        raise DocumentMapSchemaError("Document map payload must be a JSON object")

    body_start_logical_index = _coerce_known_logical_index(
        parsed.get("body_start_logical_index"),
        all_logical_indexes=all_logical_indexes,
        field_name="body_start_logical_index",
    )
    toc_region = _parse_toc_region(parsed.get("toc_region"), all_logical_indexes=all_logical_indexes)
    outline = _parse_outline_entries(parsed.get("outline"), all_logical_indexes=all_logical_indexes)
    paragraph_anchors = _parse_paragraph_anchors(parsed.get("paragraph_anchors"), all_logical_indexes=all_logical_indexes)
    review_zones = _parse_review_zones(parsed.get("review_zones"), all_logical_indexes=all_logical_indexes)

    for logical_index in all_logical_indexes:
        paragraph_anchors.setdefault(logical_index, DocumentMapAnchor(role="body", heading_level=None, confidence="low"))

    return DocumentMap(
        body_start_logical_index=body_start_logical_index,
        toc_region=toc_region,
        outline=outline,
        paragraph_anchors=paragraph_anchors,
        review_zones=review_zones,
        model_used=model_used,
        total_tokens_used=int(total_tokens_used or 0),
        processing_time_seconds=float(processing_time_seconds or 0.0),
        sampled=len(sampled_logical_indexes) < len(all_logical_indexes),
        sampled_logical_indexes=tuple(int(index) for index in sampled_logical_indexes),
    )


def _parse_toc_region(raw_value: object, *, all_logical_indexes: set[int]) -> DocumentMapTocRegion | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, dict):
        raise DocumentMapSchemaError("toc_region must be an object or null")
    start_logical_index = _coerce_known_logical_index(raw_value.get("start_logical_index"), all_logical_indexes=all_logical_indexes, field_name="toc_region.start_logical_index")
    end_logical_index = _coerce_known_logical_index(raw_value.get("end_logical_index"), all_logical_indexes=all_logical_indexes, field_name="toc_region.end_logical_index")
    if end_logical_index < start_logical_index:
        raise DocumentMapSchemaError("toc_region end_logical_index must be >= start_logical_index")
    header_logical_index = _coerce_optional_known_logical_index(raw_value.get("header_logical_index"), all_logical_indexes=all_logical_indexes, field_name="toc_region.header_logical_index")
    entries = raw_value.get("entries", ())
    if isinstance(entries, tuple):
        entries = list(entries)
    if not isinstance(entries, list):
        raise DocumentMapSchemaError("toc_region.entries must be an array")
    parsed_entries: list[DocumentMapTocEntry] = []
    for item in entries:
        if not isinstance(item, dict):
            raise DocumentMapSchemaError("toc_region entry must be an object")
        parsed_entries.append(
            DocumentMapTocEntry(
                title=str(item.get("title", "") or "").strip(),
                target_level=_coerce_heading_level(item.get("target_level"), field_name="toc_region.entries.target_level"),
                candidate_body_logical_index=_coerce_optional_known_logical_index(item.get("candidate_body_logical_index"), all_logical_indexes=all_logical_indexes, field_name="toc_region.entries.candidate_body_logical_index"),
                confidence=_coerce_confidence(item.get("confidence"), field_name="toc_region.entries.confidence"),
            )
        )
    confidence = _coerce_confidence(raw_value.get("confidence", "low"), field_name="toc_region.confidence")
    return DocumentMapTocRegion(
        start_logical_index=start_logical_index,
        end_logical_index=end_logical_index,
        header_logical_index=header_logical_index,
        entries=tuple(parsed_entries),
        confidence=confidence,
    )


def _parse_outline_entries(raw_value: object, *, all_logical_indexes: set[int]) -> tuple[DocumentMapOutlineEntry, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise DocumentMapSchemaError("outline must be an array")
    parsed_entries: list[DocumentMapOutlineEntry] = []
    for item in raw_value:
        if not isinstance(item, dict):
            raise DocumentMapSchemaError("outline entry must be an object")
        evidence = item.get("evidence", ())
        if isinstance(evidence, tuple):
            evidence = list(evidence)
        if not isinstance(evidence, list):
            raise DocumentMapSchemaError("outline evidence must be an array")
        parsed_entries.append(
            DocumentMapOutlineEntry(
                title=str(item.get("title", "") or "").strip(),
                level=_coerce_heading_level(item.get("level"), field_name="outline.level"),
                logical_index=_coerce_known_logical_index(item.get("logical_index"), all_logical_indexes=all_logical_indexes, field_name="outline.logical_index"),
                confidence=_coerce_confidence(item.get("confidence"), field_name="outline.confidence"),
                evidence=tuple(str(value or "") for value in evidence),
            )
        )
    return tuple(parsed_entries)


def _parse_paragraph_anchors(raw_value: object, *, all_logical_indexes: set[int]) -> dict[int, DocumentMapAnchor]:
    if raw_value is None:
        return {}
    parsed: dict[int, DocumentMapAnchor] = {}
    if isinstance(raw_value, dict):
        items = []
        for raw_key, raw_anchor in raw_value.items():
            if not isinstance(raw_anchor, dict):
                raise DocumentMapSchemaError("paragraph_anchors values must be objects")
            anchor_payload = dict(raw_anchor)
            anchor_payload.setdefault("i", raw_key)
            items.append(anchor_payload)
    elif isinstance(raw_value, list):
        items = raw_value
    else:
        raise DocumentMapSchemaError("paragraph_anchors must be an object or array")

    for item in items:
        if not isinstance(item, dict):
            raise DocumentMapSchemaError("paragraph anchor entry must be an object")
        logical_index = _coerce_known_logical_index(item.get("i", item.get("logical_index")), all_logical_indexes=all_logical_indexes, field_name="paragraph_anchors.index")
        role = _coerce_role(item.get("r", item.get("role")), field_name="paragraph_anchors.role")
        heading_level = _coerce_optional_heading_level(item.get("l", item.get("heading_level")), role=role, field_name="paragraph_anchors.heading_level")
        confidence = _coerce_confidence(item.get("c", item.get("confidence")), field_name="paragraph_anchors.confidence")
        parsed[logical_index] = DocumentMapAnchor(role=role, heading_level=heading_level, confidence=confidence)
    return parsed


def _parse_review_zones(raw_value: object, *, all_logical_indexes: set[int]) -> tuple[DocumentMapReviewZone, ...]:
    if raw_value is None:
        return ()
    if not isinstance(raw_value, list):
        raise DocumentMapSchemaError("review_zones must be an array")
    parsed_zones: list[DocumentMapReviewZone] = []
    for item in raw_value:
        if not isinstance(item, dict):
            raise DocumentMapSchemaError("review zone must be an object")
        start_logical_index = _coerce_known_logical_index(item.get("start_logical_index"), all_logical_indexes=all_logical_indexes, field_name="review_zones.start_logical_index")
        end_logical_index = _coerce_known_logical_index(item.get("end_logical_index"), all_logical_indexes=all_logical_indexes, field_name="review_zones.end_logical_index")
        if end_logical_index < start_logical_index:
            raise DocumentMapSchemaError("review zone end_logical_index must be >= start_logical_index")
        severity = str(item.get("severity", "") or "").strip().lower()
        if severity not in _VALID_REVIEW_ZONE_SEVERITIES:
            raise DocumentMapSchemaError(f"Unsupported review zone severity: {severity}")
        parsed_zones.append(
            DocumentMapReviewZone(
                start_logical_index=start_logical_index,
                end_logical_index=end_logical_index,
                reason=str(item.get("reason", "") or "").strip(),
                severity=severity,
            )
        )
    return tuple(parsed_zones)


def _coerce_known_logical_index(raw_value: object, *, all_logical_indexes: set[int], field_name: str) -> int:
    try:
        logical_index = int(cast(Any, raw_value))
    except Exception as exc:
        raise DocumentMapSchemaError(f"{field_name} must be an integer logical index") from exc
    if logical_index not in all_logical_indexes:
        raise DocumentMapSchemaError(f"{field_name} references unknown logical index: {logical_index}")
    return logical_index


def _coerce_optional_known_logical_index(raw_value: object, *, all_logical_indexes: set[int], field_name: str) -> int | None:
    if raw_value is None:
        return None
    return _coerce_known_logical_index(raw_value, all_logical_indexes=all_logical_indexes, field_name=field_name)


def _coerce_heading_level(raw_value: object, *, field_name: str) -> int:
    try:
        level = int(cast(Any, raw_value))
    except Exception as exc:
        raise DocumentMapSchemaError(f"{field_name} must be an integer heading level") from exc
    if level < 1 or level > 6:
        raise DocumentMapSchemaError(f"{field_name} must be in 1..6")
    return level


def _coerce_optional_heading_level(raw_value: object, *, role: str, field_name: str) -> int | None:
    if raw_value is None:
        return None
    if role != "heading":
        raise DocumentMapSchemaError(f"{field_name} must be null when role is not heading")
    return _coerce_heading_level(raw_value, field_name=field_name)


def _coerce_confidence(raw_value: object, *, field_name: str) -> str:
    confidence = str(raw_value or "").strip().lower()
    if confidence not in _VALID_DOCUMENT_MAP_CONFIDENCES:
        raise DocumentMapSchemaError(f"Unsupported confidence for {field_name}: {confidence}")
    return confidence


def _coerce_role(raw_value: object, *, field_name: str) -> str:
    role = str(raw_value or "").strip().lower()
    if role not in _VALID_DOCUMENT_MAP_ROLES:
        raise DocumentMapSchemaError(f"Unsupported role for {field_name}: {role}")
    return role


def _is_structurally_important_descriptor(descriptor: DocumentMapParagraphDescriptor) -> bool:
    return bool(
        descriptor.is_bold
        or descriptor.is_centered
        or descriptor.is_all_caps
        or descriptor.style_cluster_id is not None
        or descriptor.toc_pattern_hint
        or descriptor.is_isolated_marker
        or descriptor.scripture_reference_hint
        or descriptor.text_length < 60
        or descriptor.explicit_heading_level is not None
    )


def _shrink_logical_indexes_to_token_budget(
    descriptors: list[DocumentMapParagraphDescriptor],
    logical_indexes: tuple[int, ...],
    *,
    max_input_tokens: int | None,
) -> tuple[int, ...]:
    if max_input_tokens is None:
        return logical_indexes
    token_limit = max(1, int(max_input_tokens or 0))
    if not logical_indexes:
        return logical_indexes

    descriptors_by_index = {descriptor.logical_index: descriptor for descriptor in descriptors}
    selected = sorted(dict.fromkeys(int(index) for index in logical_indexes if int(index) in descriptors_by_index))
    if not selected:
        return ()

    def _selected_descriptors(indexes: list[int]) -> list[DocumentMapParagraphDescriptor]:
        return [descriptors_by_index[index] for index in indexes]

    while len(selected) > 1 and _estimate_document_map_descriptor_tokens(_selected_descriptors(selected)) > token_limit:
        important = [index for index in selected if _is_structurally_important_descriptor(descriptors_by_index[index])]
        optional = [index for index in selected if index not in set(important)]
        if optional:
            reduced_optional = _select_uniform_indexes(optional, max(0, len(optional) - 1))
            selected = sorted(important + reduced_optional)
            continue
        selected = sorted(_select_uniform_indexes(selected, max(1, len(selected) - 1)))

    return tuple(selected)


def _estimate_document_map_descriptor_tokens(descriptors: list[DocumentMapParagraphDescriptor]) -> int:
    if not descriptors:
        return 0
    payload = [descriptor.to_prompt_dict() for descriptor in descriptors]
    encoded = json.dumps(payload, ensure_ascii=False)
    return max(1, len(encoded) // 4 + 64)


def _build_style_cluster_ids(paragraphs: list[ParagraphUnit]) -> list[int | None]:
    normalized_styles = [str(getattr(paragraph, "style_name", "") or "").strip().lower() for paragraph in paragraphs]
    nonempty_styles = [style for style in normalized_styles if style]
    if not nonempty_styles:
        return [None for _ in paragraphs]
    default_style = Counter(nonempty_styles).most_common(1)[0][0]
    cluster_map: dict[str, int] = {}
    next_cluster_id = 1
    cluster_ids: list[int | None] = []
    for style in normalized_styles:
        if not style or style == default_style:
            cluster_ids.append(None)
            continue
        if style not in cluster_map:
            cluster_map[style] = next_cluster_id
            next_cluster_id += 1
        cluster_ids.append(cluster_map[style])
    return cluster_ids


def _build_font_size_z_scores(paragraphs: list[ParagraphUnit]) -> list[float | None]:
    sizes = [getattr(paragraph, "font_size_pt", None) for paragraph in paragraphs]
    numeric_sizes = [float(size) for size in sizes if isinstance(size, (int, float))]
    if not numeric_sizes:
        return [None for _ in paragraphs]
    mean = sum(numeric_sizes) / len(numeric_sizes)
    variance = sum((size - mean) ** 2 for size in numeric_sizes) / len(numeric_sizes)
    stddev = variance ** 0.5
    z_scores: list[float | None] = []
    for size in sizes:
        if not isinstance(size, (int, float)):
            z_scores.append(None)
            continue
        if isclose(stddev, 0.0):
            z_scores.append(0.0)
            continue
        z_scores.append(round((float(size) - mean) / stddev, 1))
    return z_scores


def _extract_page_number_hint(text: str, paragraph: ParagraphUnit) -> int | None:
    if not bool(getattr(paragraph, "is_likely_page_number", False)):
        return None
    stripped = text.strip()
    if stripped.isdigit():
        return int(stripped)
    match = re.search(r"\b(\d{1,4})\b", stripped)
    if match is None:
        return None
    return int(match.group(1))


def _is_isolated_marker_text(text: str) -> bool:
    return bool(_ISOLATED_MARKER_PATTERN.fullmatch(str(text or "").strip()))


def _is_toc_pattern_hint(text: str, paragraph: ParagraphUnit) -> bool:
    if getattr(paragraph, "heuristic_structural_role_hint", None) in {"toc_header", "toc_entry"}:
        return True
    if getattr(paragraph, "structural_role", None) in {"toc_header", "toc_entry"}:
        return True
    normalized = str(text or "").strip().casefold()
    if normalized in _TOC_HEADER_VALUES:
        return True
    return bool(_TOC_SUFFIX_PATTERN.search(str(text or "").strip()))


def _is_scripture_reference_text(text: str) -> bool:
    return bool(_SCRIPTURE_REFERENCE_PATTERN.search(str(text or "").strip()))


def _select_uniform_indexes(indexes: list[int], limit: int) -> list[int]:
    if limit <= 0 or not indexes:
        return []
    if limit >= len(indexes):
        return list(indexes)
    picks: list[int] = []
    for slot in range(limit):
        position = int(((slot + 0.5) * len(indexes)) / limit)
        position = min(max(position, 0), len(indexes) - 1)
        candidate = indexes[position]
        if candidate in picks:
            continue
        picks.append(candidate)
    return picks


def _emit_progress(callback: DocumentMapProgressCallback | None, progress: DocumentMapProgress) -> None:
    if callback is None:
        return
    callback(progress)