from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import hashlib
from math import isclose
import json
import logging
from pathlib import Path
import re
from statistics import median, quantiles
import time
from typing import Any, Callable, Protocol, Sequence, cast

from docxaicorrector.core.constants import PROMPTS_DIR, RUN_DIR
from docxaicorrector.core.models import DocumentMap, DocumentMapAnchor, DocumentMapSplitHint, ParagraphUnit
from docxaicorrector.core.models import DocumentMapOutlineEntry, DocumentMapReviewZone, DocumentMapTocEntry, DocumentMapTocRegion
from docxaicorrector.core.models import normalize_heuristic_list_kind_hint, normalize_heuristic_role_hint, normalize_heuristic_structural_role_hint
from docxaicorrector.generation._generation import normalize_model_output
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal
from docxaicorrector.runtime.artifact_retention import STRUCTURE_MAPS_MAX_AGE_SECONDS, STRUCTURE_MAPS_MAX_COUNT, prune_artifact_dir
from docxaicorrector.structure._responses_timeout import call_responses_with_hard_timeout


_TOC_HEADER_VALUES = {"contents", "table of contents", "содержание"}
_TOC_SUFFIX_PATTERN = re.compile(r"\.{2,}\s*\d+\s*$")
_ISOLATED_MARKER_PATTERN = re.compile(r"^(?:\s*[•●\-*]\s*|\s*\d+[\.)]\s*)$")
_SCRIPTURE_REFERENCE_PATTERN = re.compile(r"\b(?:[A-Za-zА-Яа-яЁё]+)\s+\d+:\d+(?:-\d+)?\b")
_SPACING_BEFORE_PATTERN = re.compile(r"<(?:\w+:)?spacing\b[^>]*\b(?:\w+:)?before=\"(?P<before>\d+)\"")
_SPACING_BEFORE_AUTOSPACING_PATTERN = re.compile(
    r"<(?:\w+:)?spacing\b[^>]*\b(?:\w+:)?beforeAutospacing=\"(?P<flag>[^\"]+)\""
)
_VALID_DOCUMENT_MAP_ROLES = frozenset({"heading", "body", "caption", "epigraph", "attribution", "toc_entry", "toc_header", "dedication", "list"})
_VALID_DOCUMENT_MAP_CONFIDENCES = frozenset({"high", "medium", "low"})
_VALID_REVIEW_ZONE_SEVERITIES = frozenset({"info", "warning", "critical"})
_TIMEOUT_ERROR_NAMES = {"APITimeoutError", "TimeoutError"}
DOCUMENT_MAP_SYSTEM_PROMPT_PATH = PROMPTS_DIR / "document_map_system.txt"
DOCUMENT_MAP_PROMPT_VERSION = 7
DOCUMENT_MAP_DESCRIPTOR_SCHEMA_VERSION = 2
DOCUMENT_MAP_POSTPROCESS_VERSION = 6
DOCUMENT_MAP_SPLIT_HINT_SCHEMA_VERSION = 1
DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION = 1
_DOCUMENT_MAP_MALFORMED_DIR = RUN_DIR / "document_maps"
_LOGGER = logging.getLogger(__name__)
_REVIEW_ZONE_SEVERITY_SYNONYMS = {
    "minor": "info",
    "low": "info",
    "medium": "warning",
    "high": "critical",
}
_VALID_DOCUMENT_MAP_SPLIT_KINDS = frozenset({"page_artifact_heading", "compound_toc_entries"})


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
    embedded_structure_hints: tuple[dict[str, object], ...] = ()

    def to_prompt_dict(self) -> dict[str, object]:
        payload = {
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
        if self.embedded_structure_hints:
            payload["emb"] = [dict(hint) for hint in self.embedded_structure_hints]
        return payload


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
            _LOGGER.warning("Document map AI generation failed: %s", exc)
            raise
    document_map = _postprocess_document_map(document_map, paragraphs=paragraphs)
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
        embedded_hint_payload = _build_embedded_structure_hint_payload(paragraph, preview_chars=preview_limit)
        persisted_style_cluster_id = cast(int | None, getattr(paragraph, "style_cluster_id", None))
        persisted_font_size_z_score = cast(float | None, getattr(paragraph, "font_size_z_score", None))
        persisted_page_number = cast(int | None, getattr(paragraph, "page_number", None))
        persisted_position_fraction = cast(float | None, getattr(paragraph, "position_fraction", None))
        descriptors.append(
            DocumentMapParagraphDescriptor(
                logical_index=int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", position))),
                text_preview=preview,
                text_length=len(text),
                style_cluster_id=style_cluster_ids[position] if persisted_style_cluster_id is None else persisted_style_cluster_id,
                is_bold=bool(getattr(paragraph, "is_bold", False)),
                is_centered=getattr(paragraph, "paragraph_alignment", None) == "center",
                is_all_caps=bool(alpha_chars) and preview.upper() == preview,
                font_size_z_score=font_size_z_scores[position] if persisted_font_size_z_score is None else persisted_font_size_z_score,
                page_number=_extract_page_number_hint(text, paragraph) if persisted_page_number is None else persisted_page_number,
                position_fraction=round(position / last_index, 3) if persisted_position_fraction is None else persisted_position_fraction,
                vertical_gap_before_pt=_extract_vertical_gap_before_pt(paragraph),
                is_repeated_across_pages=bool(getattr(paragraph, "is_repeated_across_pages", False)),
                is_likely_page_number=bool(getattr(paragraph, "is_likely_page_number", False)),
                is_isolated_marker=bool(getattr(paragraph, "is_isolated_marker", False)) or any(
                    hint.get("iso", False) for hint in embedded_hint_payload
                ) or _is_isolated_marker_text(text),
                toc_pattern_hint=bool(getattr(paragraph, "toc_pattern_hint", False)) or any(
                    hint.get("sr") in {"toc_header", "toc_entry"} for hint in embedded_hint_payload
                ) or _is_toc_pattern_hint(text, paragraph),
                scripture_reference_hint=bool(getattr(paragraph, "scripture_reference_hint", False)) or any(
                    hint.get("scr", False) for hint in embedded_hint_payload
                ) or _is_scripture_reference_text(text),
                explicit_heading_level=(
                    getattr(paragraph, "heading_level", None)
                    if getattr(paragraph, "heading_source", None) == "explicit"
                    else None
                ),
                embedded_structure_hints=embedded_hint_payload,
            )
        )
    return descriptors


def _build_embedded_structure_hint_payload(
    paragraph: ParagraphUnit,
    *,
    preview_chars: int,
) -> tuple[dict[str, object], ...]:
    hints = getattr(paragraph, "heuristic_embedded_structure_hints", None) or ()
    preview_limit = max(1, int(preview_chars or 120))
    payload: list[dict[str, object]] = []
    for hint in hints:
        text = str(getattr(hint, "text", "") or "").strip()
        raw_role = getattr(hint, "role", None)
        raw_structural_role = getattr(hint, "structural_role", None)
        raw_list_kind = getattr(hint, "list_kind", None)
        normalized_role = normalize_heuristic_role_hint(raw_role) or "body"
        normalized_structural_role = normalize_heuristic_structural_role_hint(raw_structural_role) or "body"
        normalized_list_kind = normalize_heuristic_list_kind_hint(raw_list_kind)
        if raw_role and normalized_role == "body" and str(raw_role or "").strip().lower() != "body":
            _LOGGER.warning("Ignoring invalid embedded structure role hint: %s", raw_role)
        if raw_structural_role and normalized_structural_role == "body" and str(raw_structural_role or "").strip().lower() != "body":
            _LOGGER.warning("Ignoring invalid embedded structural role hint: %s", raw_structural_role)
        if raw_list_kind and normalized_list_kind is None:
            _LOGGER.warning("Ignoring invalid embedded list kind hint: %s", raw_list_kind)
        payload.append(
            {
                "t": text[:preview_limit].rstrip(),
                "r": normalized_role,
                "sr": normalized_structural_role,
                "hl": getattr(hint, "heading_level", None),
                "lk": normalized_list_kind,
                "iso": _is_isolated_marker_text(text),
                "scr": _is_scripture_reference_text(text),
            }
        )
    return tuple(payload)


def select_document_map_logical_indexes(
    descriptors: list[DocumentMapParagraphDescriptor],
    *,
    max_input_paragraphs: int,
    max_input_tokens: int | None = None,
) -> tuple[int, ...]:
    limit = max(1, int(max_input_paragraphs or 0))
    all_indexes = [descriptor.logical_index for descriptor in descriptors]
    vertical_gap_priority_threshold = _resolve_vertical_gap_priority_threshold(descriptors)
    if len(all_indexes) <= limit:
        return _shrink_logical_indexes_to_token_budget(
            descriptors,
            tuple(all_indexes),
            max_input_tokens=max_input_tokens,
        )

    important_indexes = [
        descriptor.logical_index
        for descriptor in descriptors
        if _is_structurally_important_descriptor(
            descriptor,
            vertical_gap_priority_threshold=vertical_gap_priority_threshold,
        )
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
                "outline_membership_schema_version": DOCUMENT_MAP_OUTLINE_MEMBERSHIP_SCHEMA_VERSION,
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
    request_model = model.split(":", 1)[1] if ":" in model else model
    response = _call_document_map_responses_with_timeout(
        client=client,
        request_payload={
            "model": request_model,
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
    return call_responses_with_hard_timeout(
        client=client,
        request_payload=request_payload,
        timeout=timeout,
        thread_name="document-map-request",
        logger=_LOGGER,
        request_kind="document_map_request",
        timeout_error_factory=lambda seconds: DocumentMapRequestTimeout(
            f"Document map request timed out after {seconds:.3f}s."
        ),
    )


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
        "Return a single JSON object with keys `body_start_logical_index`, `toc_region`, `outline`, `paragraph_anchors`, `review_zones`, and optional `split_hints`. "
        "For `paragraph_anchors`, use an object mapping logical indexes to `{role, heading_level, confidence}`. "
        "For `outline`, use array items `{title, level, logical_index, confidence, evidence, member_logical_indexes}` where `member_logical_indexes` is optional, must stay within the shown logical indexes, and must include `logical_index` when present. "
        "When a body heading spans multiple adjacent paragraphs, preserve the full canonical title in `title` and include the full physical membership in `member_logical_indexes` when global evidence supports it. "
        "Do not shorten a composite body heading to the shorter TOC form when body and TOC evidence together support a longer canonical title. "
        "For `split_hints`, use an array of `{logical_index, split_kind, expected_parts, authority, confidence, evidence}` and return an empty array when there is no explicit split intent."
        " If `toc_region` is present, anchor the TOC header as `toc_header` and TOC entry paragraphs as `toc_entry` instead of generic body anchors whenever that interpretation is globally coherent."
        " If one physical TOC paragraph clearly contains multiple ordered TOC entries, keep one bounded `toc_region`, emit each TOC entry separately in `toc_region.entries`, and add a `compound_toc_entries` split hint for that owning logical index only when the parts are globally supported by the bounded TOC region and body outline/body heading candidates."
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
    split_hints = _parse_split_hints(parsed.get("split_hints"), all_logical_indexes=all_logical_indexes)

    for logical_index in all_logical_indexes:
        paragraph_anchors.setdefault(logical_index, DocumentMapAnchor(role="body", heading_level=None, confidence="low"))

    outline = _sanitize_outline_entries(outline, toc_region=toc_region)

    return DocumentMap(
        body_start_logical_index=body_start_logical_index,
        toc_region=toc_region,
        outline=outline,
        paragraph_anchors=paragraph_anchors,
        review_zones=review_zones,
        split_hints=split_hints,
        model_used=model_used,
        total_tokens_used=int(total_tokens_used or 0),
        processing_time_seconds=float(processing_time_seconds or 0.0),
        sampled=len(sampled_logical_indexes) < len(all_logical_indexes),
        sampled_logical_indexes=tuple(int(index) for index in sampled_logical_indexes),
    )


def _postprocess_document_map(document_map: DocumentMap, *, paragraphs: Sequence[ParagraphUnit]) -> DocumentMap:
    logical_to_paragraph = {
        int(getattr(paragraph, "logical_index", getattr(paragraph, "source_index", 0))): paragraph
        for paragraph in paragraphs
    }
    paragraph_anchors = _recover_toc_region_anchors(
        document_map.toc_region,
        paragraph_anchors=document_map.paragraph_anchors,
        logical_to_paragraph=logical_to_paragraph,
    )
    toc_region = _recover_toc_region_entries(
        document_map.toc_region,
        logical_to_paragraph=logical_to_paragraph,
        paragraph_anchors=paragraph_anchors,
        body_start_logical_index=int(document_map.body_start_logical_index or 0),
    )
    toc_region = _enrich_toc_titles_from_authoritative_outline_membership(
        toc_region,
        outline=document_map.outline,
    )
    outline = _recover_outline_entries(
        document_map.outline,
        toc_region=toc_region,
        logical_to_paragraph=logical_to_paragraph,
        paragraph_anchors=paragraph_anchors,
    )
    toc_region, outline = _recover_missing_chapter_sequence_entries(
        toc_region=toc_region,
        outline=outline,
        logical_to_paragraph=logical_to_paragraph,
        paragraph_anchors=paragraph_anchors,
        body_start_logical_index=int(document_map.body_start_logical_index or 0),
    )
    outline = _enrich_outline_titles_from_authoritative_membership(
        outline,
        logical_to_paragraph=logical_to_paragraph,
        toc_region=toc_region,
    )
    toc_region = _enrich_toc_titles_from_authoritative_outline_membership(
        toc_region,
        outline=outline,
    )
    toc_region, paragraph_anchors, split_hints = _recover_compound_toc_stage1_authority(
        toc_region=toc_region,
        outline=outline,
        paragraph_anchors=paragraph_anchors,
        split_hints=document_map.split_hints,
        logical_to_paragraph=logical_to_paragraph,
        body_start_logical_index=int(document_map.body_start_logical_index or 0),
    )
    if (
        toc_region == document_map.toc_region
        and outline == document_map.outline
        and paragraph_anchors == document_map.paragraph_anchors
        and split_hints == document_map.split_hints
    ):
        return document_map
    return DocumentMap(
        body_start_logical_index=document_map.body_start_logical_index,
        toc_region=toc_region,
        outline=outline,
        paragraph_anchors=paragraph_anchors,
        review_zones=document_map.review_zones,
        split_hints=split_hints,
        model_used=document_map.model_used,
        total_tokens_used=document_map.total_tokens_used,
        processing_time_seconds=document_map.processing_time_seconds,
        sampled=document_map.sampled,
        sampled_logical_indexes=document_map.sampled_logical_indexes,
    )


def _recover_toc_region_anchors(
    toc_region: DocumentMapTocRegion | None,
    *,
    paragraph_anchors: dict[int, DocumentMapAnchor],
    logical_to_paragraph: dict[int, ParagraphUnit],
) -> dict[int, DocumentMapAnchor]:
    if toc_region is None:
        return paragraph_anchors

    recovered_anchors = dict(paragraph_anchors)
    recovered = False
    toc_confidence = "high" if str(toc_region.confidence or "").strip().lower() == "high" else "medium"
    header_logical_index = toc_region.header_logical_index
    if header_logical_index is not None:
        current_anchor = recovered_anchors.get(int(header_logical_index))
        if current_anchor is None or (current_anchor.role == "body" and str(current_anchor.confidence or "").strip().lower() == "low"):
            recovered_anchors[int(header_logical_index)] = DocumentMapAnchor(
                role="toc_header",
                heading_level=None,
                confidence=toc_confidence,
            )
            recovered = True

    for logical_index in range(int(toc_region.start_logical_index), int(toc_region.end_logical_index) + 1):
        if logical_index == header_logical_index:
            continue
        paragraph = logical_to_paragraph.get(logical_index)
        if paragraph is None:
            continue
        current_anchor = recovered_anchors.get(logical_index)
        if current_anchor is not None and current_anchor.role != "body":
            continue
        if current_anchor is not None and str(current_anchor.confidence or "").strip().lower() not in {"low", ""}:
            continue
        title = _extract_toc_entry_title(str(getattr(paragraph, "text", "") or ""))
        if not title:
            continue
        recovered_anchors[logical_index] = DocumentMapAnchor(role="toc_entry", heading_level=None, confidence=toc_confidence)
        recovered = True

    return recovered_anchors if recovered else paragraph_anchors


def _recover_toc_region_entries(
    toc_region: DocumentMapTocRegion | None,
    *,
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
    body_start_logical_index: int,
) -> DocumentMapTocRegion | None:
    if toc_region is None:
        return toc_region
    entries_by_candidate_index = {
        int(entry.candidate_body_logical_index): entry
        for entry in toc_region.entries
        if entry.candidate_body_logical_index is not None
    }
    title_counts = Counter(
        _normalize_document_map_title(entry.title)
        for entry in toc_region.entries
        if str(entry.title or "").strip()
    )
    recovered_entries = list(toc_region.entries)
    recovered = False

    for position, entry in enumerate(tuple(recovered_entries)):
        candidate_index = entry.candidate_body_logical_index
        if candidate_index is None:
            continue
        paragraph = logical_to_paragraph.get(int(candidate_index))
        if paragraph is None:
            continue
        candidate_title = _paragraph_title_candidate(paragraph)
        normalized_candidate_title = _normalize_document_map_title(candidate_title)
        current_title = _normalize_document_map_title(entry.title)
        if not normalized_candidate_title:
            continue
        if normalized_candidate_title == current_title:
            continue
        if normalized_candidate_title in title_counts and title_counts[normalized_candidate_title] > 0:
            continue
        if current_title:
            title_counts[current_title] = max(0, title_counts[current_title] - 1)
        recovered_entries[position] = DocumentMapTocEntry(
            title=candidate_title,
            target_level=int(entry.target_level),
            candidate_body_logical_index=int(candidate_index),
            confidence="medium",
        )
        title_counts[normalized_candidate_title] += 1
        recovered = True

    existing_titles = {
        _normalize_document_map_title(entry.title)
        for entry in recovered_entries
        if str(entry.title or "").strip()
    }
    for logical_index in range(int(toc_region.start_logical_index), int(toc_region.end_logical_index) + 1):
        if logical_index == toc_region.header_logical_index:
            continue
        paragraph = logical_to_paragraph.get(logical_index)
        if paragraph is None:
            continue
        toc_title = _extract_toc_entry_title(str(getattr(paragraph, "text", "") or ""))
        normalized_toc_title = _normalize_document_map_title(toc_title)
        if not normalized_toc_title or normalized_toc_title in existing_titles:
            continue
        candidate_body_logical_index = _find_body_heading_logical_index(
            normalized_toc_title,
            logical_to_paragraph=logical_to_paragraph,
            paragraph_anchors=paragraph_anchors,
            body_start_logical_index=body_start_logical_index,
            toc_region=toc_region,
        )
        if candidate_body_logical_index is None or candidate_body_logical_index in entries_by_candidate_index:
            continue
        anchor = paragraph_anchors.get(candidate_body_logical_index)
        recovered_entries.append(
            DocumentMapTocEntry(
                title=toc_title,
                target_level=max(1, int(getattr(anchor, "heading_level", None) or 1)),
                candidate_body_logical_index=int(candidate_body_logical_index),
                confidence="medium",
            )
        )
        entries_by_candidate_index[int(candidate_body_logical_index)] = recovered_entries[-1]
        existing_titles.add(normalized_toc_title)
        recovered = True
    if not recovered:
        return toc_region
    return DocumentMapTocRegion(
        start_logical_index=toc_region.start_logical_index,
        end_logical_index=toc_region.end_logical_index,
        header_logical_index=toc_region.header_logical_index,
        entries=tuple(recovered_entries),
        confidence=toc_region.confidence,
    )


def _recover_compound_toc_stage1_authority(
    *,
    toc_region: DocumentMapTocRegion | None,
    outline: tuple[DocumentMapOutlineEntry, ...],
    paragraph_anchors: dict[int, DocumentMapAnchor],
    split_hints: tuple[DocumentMapSplitHint, ...],
    logical_to_paragraph: dict[int, ParagraphUnit],
    body_start_logical_index: int,
) -> tuple[DocumentMapTocRegion | None, dict[int, DocumentMapAnchor], tuple[DocumentMapSplitHint, ...]]:
    if toc_region is None or str(toc_region.confidence or "").strip().lower() != "high":
        return toc_region, paragraph_anchors, split_hints

    toc_start = int(toc_region.start_logical_index)
    toc_end = int(toc_region.end_logical_index)
    outline_candidates = tuple(
        entry
        for entry in sorted(outline, key=lambda item: int(item.logical_index))
        if str(entry.confidence or "").strip().lower() == "high"
        and int(entry.logical_index) >= int(body_start_logical_index)
        and not (toc_start <= int(entry.logical_index) <= toc_end)
    )
    if len(outline_candidates) < 2:
        return toc_region, paragraph_anchors, split_hints

    recovered_entries = list(toc_region.entries)
    recovered_anchors = dict(paragraph_anchors)
    recovered_split_hints = list(split_hints)
    existing_candidate_indexes = {
        int(entry.candidate_body_logical_index)
        for entry in recovered_entries
        if entry.candidate_body_logical_index is not None
    }
    existing_hint_indexes = {
        int(hint.logical_index)
        for hint in recovered_split_hints
        if str(hint.split_kind or "").strip().lower() == "compound_toc_entries"
    }
    recovered = False

    for logical_index in range(toc_start, toc_end + 1):
        if logical_index == toc_region.header_logical_index:
            continue
        paragraph = logical_to_paragraph.get(logical_index)
        if paragraph is None:
            continue
        matched_entries = _match_outline_entries_in_toc_paragraph(
            str(getattr(paragraph, "text", "") or ""),
            outline_candidates=outline_candidates,
        )
        if len(matched_entries) < 2:
            continue

        for outline_entry in matched_entries:
            candidate_logical_index = int(outline_entry.logical_index)
            if candidate_logical_index in existing_candidate_indexes:
                continue
            recovered_entries.append(
                DocumentMapTocEntry(
                    title=outline_entry.title,
                    target_level=int(outline_entry.level),
                    candidate_body_logical_index=candidate_logical_index,
                    confidence="high",
                )
            )
            existing_candidate_indexes.add(candidate_logical_index)
            recovered = True

        current_anchor = recovered_anchors.get(logical_index)
        if current_anchor is None or (
            current_anchor.role == "body" and str(current_anchor.confidence or "").strip().lower() in {"low", "medium", ""}
        ):
            recovered_anchors[logical_index] = DocumentMapAnchor(role="toc_entry", heading_level=None, confidence="high")
            recovered = True

        if logical_index not in existing_hint_indexes:
            recovered_split_hints.append(
                DocumentMapSplitHint(
                    logical_index=logical_index,
                    split_kind="compound_toc_entries",
                    expected_parts=tuple(entry.title for entry in matched_entries),
                    authority="document_map_toc",
                    confidence="high",
                    evidence=("bounded_toc_region", "one_to_one_toc_entry_match", "toc_entry"),
                )
            )
            existing_hint_indexes.add(logical_index)
            recovered = True

    if not recovered:
        return toc_region, paragraph_anchors, split_hints

    return (
        DocumentMapTocRegion(
            start_logical_index=toc_region.start_logical_index,
            end_logical_index=toc_region.end_logical_index,
            header_logical_index=toc_region.header_logical_index,
            entries=tuple(sorted(recovered_entries, key=lambda entry: int(entry.candidate_body_logical_index or -1))),
            confidence=toc_region.confidence,
        ),
        recovered_anchors,
        tuple(recovered_split_hints),
    )


def _recover_outline_entries(
    outline: tuple[DocumentMapOutlineEntry, ...],
    *,
    toc_region: DocumentMapTocRegion | None,
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
) -> tuple[DocumentMapOutlineEntry, ...]:
    if toc_region is None or not toc_region.entries:
        return outline
    recovered_outline = list(outline)
    occupied_indexes = {int(entry.logical_index) for entry in outline}
    existing_titles = {_normalize_document_map_title(entry.title) for entry in outline if entry.title.strip()}
    recovered = False
    for toc_entry in toc_region.entries:
        candidate_index = toc_entry.candidate_body_logical_index
        if candidate_index is None or int(candidate_index) in occupied_indexes:
            continue
        paragraph = logical_to_paragraph.get(int(candidate_index))
        if paragraph is None:
            continue
        anchor = paragraph_anchors.get(int(candidate_index))
        if anchor is not None and anchor.role != "heading":
            continue
        candidate_title = _paragraph_title_candidate(paragraph)
        normalized_candidate_title = _normalize_document_map_title(candidate_title)
        if not normalized_candidate_title or normalized_candidate_title in existing_titles:
            continue
        recovered_outline.append(
            DocumentMapOutlineEntry(
                title=candidate_title,
                level=int(toc_entry.target_level),
                logical_index=int(candidate_index),
                confidence="medium",
                evidence=("toc_candidate_body_recovery",),
            )
        )
        occupied_indexes.add(int(candidate_index))
        existing_titles.add(normalized_candidate_title)
        recovered = True
    if not recovered:
        return outline
    return tuple(sorted(recovered_outline, key=lambda entry: int(entry.logical_index)))


def _enrich_outline_titles_from_authoritative_membership(
    outline: tuple[DocumentMapOutlineEntry, ...],
    *,
    logical_to_paragraph: dict[int, ParagraphUnit],
    toc_region: DocumentMapTocRegion | None,
) -> tuple[DocumentMapOutlineEntry, ...]:
    recovered_outline: list[DocumentMapOutlineEntry] = []
    recovered = False
    for entry in outline:
        authoritative_title = _resolve_authoritative_outline_title_from_membership(
            entry,
            logical_to_paragraph=logical_to_paragraph,
            toc_region=toc_region,
        )
        if not authoritative_title or authoritative_title == str(entry.title or "").strip():
            recovered_outline.append(entry)
            continue
        recovered_outline.append(
            DocumentMapOutlineEntry(
                title=authoritative_title,
                level=int(entry.level),
                logical_index=int(entry.logical_index),
                confidence=str(entry.confidence or "").strip(),
                evidence=tuple(entry.evidence),
                member_logical_indexes=tuple(int(index) for index in entry.member_logical_indexes),
            )
        )
        recovered = True
    if not recovered:
        return outline
    return tuple(recovered_outline)


def _enrich_toc_titles_from_authoritative_outline_membership(
    toc_region: DocumentMapTocRegion | None,
    *,
    outline: tuple[DocumentMapOutlineEntry, ...],
) -> DocumentMapTocRegion | None:
    if toc_region is None or not toc_region.entries:
        return toc_region
    authoritative_titles_by_candidate_index = {
        int(entry.logical_index): str(entry.title or "").strip()
        for entry in outline
        if str(entry.title or "").strip()
    }
    recovered_entries: list[DocumentMapTocEntry] = []
    recovered = False
    for entry in toc_region.entries:
        candidate_index = entry.candidate_body_logical_index
        authoritative_title = None if candidate_index is None else authoritative_titles_by_candidate_index.get(int(candidate_index))
        if not authoritative_title or authoritative_title == str(entry.title or "").strip():
            recovered_entries.append(entry)
            continue
        if not _document_map_titles_compatible(authoritative_title, entry.title):
            recovered_entries.append(entry)
            continue
        recovered_entries.append(
            DocumentMapTocEntry(
                title=authoritative_title,
                target_level=int(entry.target_level),
                candidate_body_logical_index=None if candidate_index is None else int(candidate_index),
                confidence=str(entry.confidence or "").strip(),
            )
        )
        recovered = True
    if not recovered:
        return toc_region
    return DocumentMapTocRegion(
        start_logical_index=toc_region.start_logical_index,
        end_logical_index=toc_region.end_logical_index,
        header_logical_index=toc_region.header_logical_index,
        entries=tuple(recovered_entries),
        confidence=toc_region.confidence,
    )


def _resolve_authoritative_outline_title_from_membership(
    entry: DocumentMapOutlineEntry,
    *,
    logical_to_paragraph: dict[int, ParagraphUnit],
    toc_region: DocumentMapTocRegion | None,
) -> str:
    member_logical_indexes = tuple(int(index) for index in entry.member_logical_indexes)
    if len(member_logical_indexes) <= 1:
        return str(entry.title or "").strip()
    paragraph_texts: list[str] = []
    for logical_index in member_logical_indexes:
        paragraph = logical_to_paragraph.get(int(logical_index))
        if paragraph is None:
            return str(entry.title or "").strip()
        text = str(getattr(paragraph, "text", "") or "").strip()
        if not text:
            return str(entry.title or "").strip()
        paragraph_texts.append(text)
    cluster_title = re.sub(r"\s+", " ", " ".join(paragraph_texts)).strip()
    if not cluster_title:
        return str(entry.title or "").strip()
    current_title = str(entry.title or "").strip()
    if not current_title:
        return cluster_title
    if _normalize_document_map_title(cluster_title) == _normalize_document_map_title(current_title):
        return cluster_title
    if _document_map_titles_compatible(cluster_title, current_title):
        return cluster_title
    if toc_region is not None:
        for toc_entry in toc_region.entries:
            if int(toc_entry.candidate_body_logical_index or -1) != int(entry.logical_index):
                continue
            toc_title = str(toc_entry.title or "").strip()
            if toc_title and _document_map_titles_compatible(cluster_title, toc_title):
                return cluster_title
    return current_title


def _document_map_titles_compatible(left: str, right: str) -> bool:
    left_tokens = _normalize_toc_matching_text(left)
    right_tokens = _normalize_toc_matching_text(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens in right_tokens or right_tokens in left_tokens


def _recover_missing_chapter_sequence_entries(
    *,
    toc_region: DocumentMapTocRegion | None,
    outline: tuple[DocumentMapOutlineEntry, ...],
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
    body_start_logical_index: int,
) -> tuple[DocumentMapTocRegion | None, tuple[DocumentMapOutlineEntry, ...]]:
    if toc_region is None or not outline:
        return toc_region, outline

    recovered_toc_entries = list(toc_region.entries)
    recovered_outline = list(outline)
    occupied_indexes = {int(entry.logical_index) for entry in outline}
    occupied_toc_indexes = {
        int(entry.candidate_body_logical_index)
        for entry in toc_region.entries
        if entry.candidate_body_logical_index is not None
    }
    recovered = False

    ordered_chapter_entries = sorted(
        (
            (chapter_number, int(entry.logical_index), int(entry.level))
            for entry in outline
            if (chapter_number := _extract_chapter_sequence_number(entry.title)) is not None
        ),
        key=lambda item: item[1],
    )
    for (left_number, left_index, left_level), (right_number, right_index, _right_level) in zip(
        ordered_chapter_entries,
        ordered_chapter_entries[1:],
    ):
        if right_number <= left_number + 1:
            continue
        missing_numbers = range(left_number + 1, right_number)
        for missing_number in missing_numbers:
            missing_index = _find_chapter_heading_between(
                missing_number,
                start_index=left_index,
                end_index=right_index,
                logical_to_paragraph=logical_to_paragraph,
                paragraph_anchors=paragraph_anchors,
                body_start_logical_index=body_start_logical_index,
                toc_region=toc_region,
            )
            if missing_index is None or missing_index in occupied_indexes:
                continue

            title = _paragraph_title_candidate(logical_to_paragraph[missing_index])
            recovered_outline.append(
                DocumentMapOutlineEntry(
                    title=title,
                    level=left_level,
                    logical_index=missing_index,
                    confidence="medium",
                    evidence=("chapter_sequence_recovery",),
                )
            )
            occupied_indexes.add(missing_index)

            toc_title = _find_nearby_chapter_subtitle(
                chapter_index=missing_index,
                next_chapter_index=right_index,
                logical_to_paragraph=logical_to_paragraph,
                paragraph_anchors=paragraph_anchors,
            ) or title
            if missing_index not in occupied_toc_indexes:
                recovered_toc_entries.append(
                    DocumentMapTocEntry(
                        title=toc_title,
                        target_level=left_level,
                        candidate_body_logical_index=missing_index,
                        confidence="medium",
                    )
                )
                occupied_toc_indexes.add(missing_index)
            recovered = True

    if not recovered:
        return toc_region, outline
    return (
        DocumentMapTocRegion(
            start_logical_index=toc_region.start_logical_index,
            end_logical_index=toc_region.end_logical_index,
            header_logical_index=toc_region.header_logical_index,
            entries=tuple(sorted(recovered_toc_entries, key=lambda entry: int(entry.candidate_body_logical_index or -1))),
            confidence=toc_region.confidence,
        ),
        tuple(sorted(recovered_outline, key=lambda entry: int(entry.logical_index))),
    )


def _find_chapter_heading_between(
    chapter_number: int,
    *,
    start_index: int,
    end_index: int,
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
    body_start_logical_index: int,
    toc_region: DocumentMapTocRegion,
) -> int | None:
    toc_start = int(toc_region.start_logical_index)
    toc_end = int(toc_region.end_logical_index)
    for logical_index in sorted(logical_to_paragraph):
        if logical_index <= start_index or logical_index >= end_index or logical_index < body_start_logical_index:
            continue
        if toc_start <= logical_index <= toc_end:
            continue
        paragraph = logical_to_paragraph[logical_index]
        if _extract_chapter_sequence_number(_paragraph_title_candidate(paragraph)) != chapter_number:
            continue
        anchor = paragraph_anchors.get(logical_index)
        if anchor is not None and anchor.role == "heading":
            return logical_index
        if str(getattr(paragraph, "role", "") or "").strip().lower() == "heading":
            return logical_index
        return logical_index
    return None


def _find_nearby_chapter_subtitle(
    *,
    chapter_index: int,
    next_chapter_index: int,
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
) -> str:
    for logical_index in sorted(logical_to_paragraph):
        if logical_index <= chapter_index or logical_index >= next_chapter_index or logical_index - chapter_index > 3:
            continue
        paragraph = logical_to_paragraph[logical_index]
        anchor = paragraph_anchors.get(logical_index)
        if anchor is not None and anchor.role != "heading":
            continue
        role = str(getattr(paragraph, "role", "") or "").strip().lower()
        if anchor is None and role != "heading" and not _looks_like_chapter_subtitle(_paragraph_title_candidate(paragraph)):
            continue
        title = _paragraph_title_candidate(paragraph)
        if title and _extract_chapter_sequence_number(title) is None:
            return title
    return ""


def _extract_chapter_sequence_number(text: str) -> int | None:
    match = re.match(r"^\s*(?:chapter|глава)\s+([a-zа-яё0-9ivxlcdm\-]+)\b", str(text or ""), flags=re.IGNORECASE)
    if match is None:
        return None
    token = match.group(1).casefold().strip(".:-")
    return _chapter_number_token_to_int(token)


def _looks_like_chapter_subtitle(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "").strip())
    if not normalized or normalized.casefold().startswith("this page intentionally left blank"):
        return False
    if normalized.endswith(('.', '!', '?')):
        return False
    if len(normalized.split()) > 12:
        return False
    return any(char.isalpha() for char in normalized)


def _chapter_number_token_to_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
        "twenty": 20,
    }
    if token in words:
        return words[token]
    return _roman_to_int(token)


def _roman_to_int(token: str) -> int | None:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    if not token or any(char not in values for char in token):
        return None
    total = 0
    previous = 0
    for char in reversed(token):
        value = values[char]
        if value < previous:
            total -= value
        else:
            total += value
            previous = value
    return total if total > 0 else None


def _paragraph_title_candidate(paragraph: ParagraphUnit) -> str:
    return str(getattr(paragraph, "text", "") or "").strip()


def _extract_toc_entry_title(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"\.{2,}\s*\d+\s*$", "", normalized)
    normalized = re.sub(r"\s+\d{1,4}\s*$", "", normalized)
    normalized = re.sub(r"^\s*\d+[\.)-]?\s+", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_toc_matching_text(text: str) -> str:
    normalized = _normalize_document_map_title(text)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _match_outline_entries_in_toc_paragraph(
    text: str,
    *,
    outline_candidates: tuple[DocumentMapOutlineEntry, ...],
) -> tuple[DocumentMapOutlineEntry, ...]:
    normalized_paragraph = _normalize_toc_matching_text(text)
    if not normalized_paragraph:
        return ()

    cursor = 0
    matched_entries: list[DocumentMapOutlineEntry] = []
    for entry in outline_candidates:
        normalized_title = _normalize_toc_matching_text(entry.title)
        if not normalized_title:
            continue
        position = normalized_paragraph.find(normalized_title, cursor)
        if position < 0:
            continue
        matched_entries.append(entry)
        cursor = position + len(normalized_title)
    return tuple(matched_entries) if len(matched_entries) >= 2 else ()


def _normalize_document_map_title(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    normalized = re.sub(r"\.{2,}\s*\d+\s*$", "", normalized)
    normalized = re.sub(r"\s+\d{1,4}\s*$", "", normalized)
    normalized = re.sub(r"^\s*\d+[\.)-]?\s+", "", normalized)
    normalized = re.sub(r"^\s*(?:chapter|глава)\s+[a-zа-яё0-9ivxlcdm\-]+\s*[:.\-]*\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.casefold()


def _find_body_heading_logical_index(
    normalized_title: str,
    *,
    logical_to_paragraph: dict[int, ParagraphUnit],
    paragraph_anchors: dict[int, DocumentMapAnchor],
    body_start_logical_index: int,
    toc_region: DocumentMapTocRegion,
) -> int | None:
    candidates: list[tuple[int, int]] = []
    toc_start = int(toc_region.start_logical_index)
    toc_end = int(toc_region.end_logical_index)
    for logical_index, paragraph in logical_to_paragraph.items():
        if logical_index < body_start_logical_index or toc_start <= logical_index <= toc_end:
            continue
        paragraph_title = _normalize_document_map_title(_paragraph_title_candidate(paragraph))
        if paragraph_title != normalized_title:
            continue
        anchor = paragraph_anchors.get(logical_index)
        score = 0
        if anchor is not None and anchor.role == "heading":
            score += 2
        if str(getattr(paragraph, "role", "") or "").strip().lower() == "heading":
            score += 1
        candidates.append((score, int(logical_index)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _sanitize_outline_entries(
    outline: tuple[DocumentMapOutlineEntry, ...],
    *,
    toc_region: DocumentMapTocRegion | None,
) -> tuple[DocumentMapOutlineEntry, ...]:
    if toc_region is None:
        return outline
    toc_start = int(toc_region.start_logical_index)
    toc_end = int(toc_region.end_logical_index)
    return tuple(entry for entry in outline if not (toc_start <= int(entry.logical_index) <= toc_end))


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
        if any(not isinstance(value, str) for value in evidence):
            raise DocumentMapSchemaError("outline evidence items must be strings")
        logical_index = _coerce_known_logical_index(item.get("logical_index"), all_logical_indexes=all_logical_indexes, field_name="outline.logical_index")
        member_logical_indexes = _parse_outline_member_logical_indexes(
            item.get("member_logical_indexes"),
            all_logical_indexes=all_logical_indexes,
            anchor_logical_index=logical_index,
        )
        parsed_entries.append(
            DocumentMapOutlineEntry(
                title=str(item.get("title", "") or "").strip(),
                level=_coerce_heading_level(item.get("level"), field_name="outline.level"),
                logical_index=logical_index,
                confidence=_coerce_confidence(item.get("confidence"), field_name="outline.confidence"),
                evidence=tuple(cast(str, value) for value in evidence),
                member_logical_indexes=member_logical_indexes,
            )
        )
    return tuple(parsed_entries)


def _parse_outline_member_logical_indexes(
    raw_value: object,
    *,
    all_logical_indexes: set[int],
    anchor_logical_index: int,
) -> tuple[int, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, tuple):
        raw_value = list(raw_value)
    if not isinstance(raw_value, list):
        raise DocumentMapSchemaError("outline.member_logical_indexes must be an array")
    if not raw_value:
        return ()
    parsed_indexes = [
        _coerce_known_logical_index(value, all_logical_indexes=all_logical_indexes, field_name="outline.member_logical_indexes")
        for value in raw_value
    ]
    if len(set(parsed_indexes)) != len(parsed_indexes):
        raise DocumentMapSchemaError("outline.member_logical_indexes must not contain duplicates")
    if parsed_indexes != sorted(parsed_indexes):
        raise DocumentMapSchemaError("outline.member_logical_indexes must be sorted ascending")
    if int(anchor_logical_index) not in parsed_indexes:
        raise DocumentMapSchemaError("outline.member_logical_indexes must include outline.logical_index")
    for left_index, right_index in zip(parsed_indexes, parsed_indexes[1:], strict=False):
        if int(right_index) != int(left_index) + 1:
            raise DocumentMapSchemaError("outline.member_logical_indexes must be contiguous")
    return tuple(int(index) for index in parsed_indexes)


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
        severity = _coerce_review_zone_severity(item.get("severity"))
        parsed_zones.append(
            DocumentMapReviewZone(
                start_logical_index=start_logical_index,
                end_logical_index=end_logical_index,
                reason=str(item.get("reason", "") or "").strip(),
                severity=severity,
            )
        )
    return tuple(parsed_zones)


def _parse_split_hints(raw_value: object, *, all_logical_indexes: set[int]) -> tuple[DocumentMapSplitHint, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, tuple):
        raw_value = list(raw_value)
    if not isinstance(raw_value, list):
        raise DocumentMapSchemaError("split_hints must be an array")

    parsed_hints: list[DocumentMapSplitHint] = []
    for item in raw_value:
        if not isinstance(item, dict):
            raise DocumentMapSchemaError("split hint must be an object")
        expected_parts = item.get("expected_parts", ())
        if isinstance(expected_parts, str):
            expected_parts = [expected_parts]
        if isinstance(expected_parts, tuple):
            expected_parts = list(expected_parts)
        if not isinstance(expected_parts, list):
            raise DocumentMapSchemaError("split_hints.expected_parts must be an array")
        if any(not isinstance(value, str) for value in expected_parts):
            raise DocumentMapSchemaError("split_hints.expected_parts items must be strings")
        evidence = item.get("evidence", ())
        if isinstance(evidence, tuple):
            evidence = list(evidence)
        if not isinstance(evidence, list):
            raise DocumentMapSchemaError("split_hints.evidence must be an array")
        if any(not isinstance(value, str) for value in evidence):
            raise DocumentMapSchemaError("split_hints.evidence items must be strings")
        parsed_hints.append(
            DocumentMapSplitHint(
                logical_index=_coerce_known_logical_index(
                    item.get("logical_index"),
                    all_logical_indexes=all_logical_indexes,
                    field_name="split_hints.logical_index",
                ),
                split_kind=_coerce_split_kind(item.get("split_kind"), field_name="split_hints.split_kind"),
                expected_parts=tuple(str(value).strip() for value in expected_parts if str(value).strip()),
                authority=_coerce_nonempty_string(item.get("authority"), field_name="split_hints.authority"),
                confidence=_coerce_confidence(item.get("confidence"), field_name="split_hints.confidence"),
                evidence=tuple(str(value).strip() for value in evidence if str(value).strip()),
            )
        )
    return tuple(parsed_hints)


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
        _LOGGER.warning("Dropping document-map heading_level for non-heading role: role=%s heading_level=%s", role, raw_value)
        return None
    return _coerce_heading_level(raw_value, field_name=field_name)


def _coerce_review_zone_severity(raw_value: object) -> str:
    severity = str(raw_value or "").strip().lower()
    normalized = _REVIEW_ZONE_SEVERITY_SYNONYMS.get(severity, severity)
    if normalized != severity:
        _LOGGER.warning("Normalizing document-map review zone severity: %s -> %s", severity, normalized)
    if normalized not in _VALID_REVIEW_ZONE_SEVERITIES:
        raise DocumentMapSchemaError(f"Unsupported review zone severity: {severity}")
    return normalized


def _coerce_confidence(raw_value: object, *, field_name: str) -> str:
    confidence = str(raw_value or "").strip().lower()
    if confidence not in _VALID_DOCUMENT_MAP_CONFIDENCES:
        raise DocumentMapSchemaError(f"Unsupported confidence for {field_name}: {confidence}")
    return confidence


def _coerce_split_kind(raw_value: object, *, field_name: str) -> str:
    split_kind = str(raw_value or "").strip().lower()
    if split_kind not in _VALID_DOCUMENT_MAP_SPLIT_KINDS:
        raise DocumentMapSchemaError(f"Unsupported split kind for {field_name}: {split_kind}")
    return split_kind


def _coerce_nonempty_string(raw_value: object, *, field_name: str) -> str:
    value = str(raw_value or "").strip()
    if not value:
        raise DocumentMapSchemaError(f"{field_name} must be a non-empty string")
    return value


def _coerce_role(raw_value: object, *, field_name: str) -> str:
    role = str(raw_value or "").strip().lower()
    if role not in _VALID_DOCUMENT_MAP_ROLES:
        raise DocumentMapSchemaError(f"Unsupported role for {field_name}: {role}")
    return role


def _is_structurally_important_descriptor(
    descriptor: DocumentMapParagraphDescriptor,
    *,
    vertical_gap_priority_threshold: float | None = None,
) -> bool:
    return bool(
        descriptor.is_bold
        or descriptor.is_centered
        or descriptor.is_all_caps
        or descriptor.style_cluster_id is not None
        or (
            descriptor.vertical_gap_before_pt is not None
            and vertical_gap_priority_threshold is not None
            and descriptor.vertical_gap_before_pt >= vertical_gap_priority_threshold
        )
        or descriptor.toc_pattern_hint
        or descriptor.is_isolated_marker
        or descriptor.scripture_reference_hint
        or bool(descriptor.embedded_structure_hints)
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
    vertical_gap_priority_threshold = _resolve_vertical_gap_priority_threshold(descriptors)

    def _selected_descriptors(indexes: list[int]) -> list[DocumentMapParagraphDescriptor]:
        return [descriptors_by_index[index] for index in indexes]

    while len(selected) > 1 and _estimate_document_map_descriptor_tokens(_selected_descriptors(selected)) > token_limit:
        important = [
            index
            for index in selected
            if _is_structurally_important_descriptor(
                descriptors_by_index[index],
                vertical_gap_priority_threshold=vertical_gap_priority_threshold,
            )
        ]
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


def _extract_vertical_gap_before_pt(paragraph: ParagraphUnit) -> float | None:
    direct_value = getattr(paragraph, "vertical_gap_before_pt", None)
    if isinstance(direct_value, int | float):
        return _round_vertical_gap_before_pt(float(direct_value))

    paragraph_properties_xml = str(getattr(paragraph, "paragraph_properties_xml", "") or "").strip()
    if not paragraph_properties_xml:
        return None
    autospacing_match = _SPACING_BEFORE_AUTOSPACING_PATTERN.search(paragraph_properties_xml)
    if autospacing_match and str(autospacing_match.group("flag") or "").strip().lower() in {"1", "true", "on"}:
        return None
    spacing_match = _SPACING_BEFORE_PATTERN.search(paragraph_properties_xml)
    if spacing_match is None:
        return None
    try:
        before_twips = int(spacing_match.group("before"))
    except (TypeError, ValueError):
        return None
    return _round_vertical_gap_before_pt(before_twips / 20.0)


def _round_vertical_gap_before_pt(value: float) -> float:
    return round(value * 2.0) / 2.0


def _resolve_vertical_gap_priority_threshold(descriptors: list[DocumentMapParagraphDescriptor]) -> float | None:
    nonzero_gaps = sorted(
        descriptor.vertical_gap_before_pt
        for descriptor in descriptors
        if descriptor.vertical_gap_before_pt is not None and descriptor.vertical_gap_before_pt > 0
    )
    if not nonzero_gaps:
        return None
    if len(nonzero_gaps) == 1:
        return nonzero_gaps[0]
    return float(quantiles(nonzero_gaps, n=10, method="inclusive")[8])


def _build_style_cluster_ids(paragraphs: list[ParagraphUnit]) -> list[int | None]:
    persisted = [getattr(paragraph, "style_cluster_id", None) for paragraph in paragraphs]
    if any(value is not None for value in persisted):
        return [cast(int | None, value) for value in persisted]
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
    persisted = [getattr(paragraph, "font_size_z_score", None) for paragraph in paragraphs]
    if any(value is not None for value in persisted):
        return [cast(float | None, value) for value in persisted]
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
    direct_value = getattr(paragraph, "page_number", None)
    if isinstance(direct_value, int):
        return direct_value
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
    if normalize_heuristic_structural_role_hint(getattr(paragraph, "heuristic_structural_role_hint", None)) in {"toc_header", "toc_entry"}:
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
