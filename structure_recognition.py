from __future__ import annotations

from functools import lru_cache
from collections.abc import Iterable, Sequence
import json
from pathlib import Path
import time
from typing import Any, Protocol, cast

from generation import normalize_model_output
from image_shared import call_responses_create_with_retry
from models import ParagraphClassification, ParagraphDescriptor, ParagraphUnit, StructureMap
from openai_response_utils import collect_response_text_traversal


SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "structure_recognition_system.txt"
_PIPELINE_BODY_STRUCTURAL_ROLES = {"epigraph", "attribution", "toc_entry", "toc_header", "dedication"}
_VALID_AI_ROLES = {"heading", "body", "caption", "epigraph", "attribution", "toc_entry", "toc_header", "dedication", "list"}
_VALID_AI_CONFIDENCES = {"high", "medium", "low"}


class _ResponsesApi(Protocol):
    def create(self, *, model: str, input: list[dict[str, object]], timeout: float) -> Any:
        ...


class _StructureRecognitionClient(Protocol):
    responses: _ResponsesApi


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_paragraph_descriptors(paragraphs: list[ParagraphUnit]) -> list[ParagraphDescriptor]:
    descriptors: list[ParagraphDescriptor] = []
    for paragraph in paragraphs:
        text = str(paragraph.text or "").strip()
        if not text:
            continue
        preview = text[:60]
        alpha_chars = [char for char in preview if char.isalpha()]
        descriptors.append(
            ParagraphDescriptor(
                index=paragraph.source_index,
                text_preview=preview,
                text_length=len(text),
                style_name=paragraph.style_name,
                is_bold=paragraph.is_bold,
                is_centered=paragraph.paragraph_alignment == "center",
                is_all_caps=bool(alpha_chars) and preview.upper() == preview,
                font_size_pt=paragraph.font_size_pt,
                has_numbering=paragraph.list_kind is not None,
                explicit_heading_level=(paragraph.heading_level if paragraph.heading_source == "explicit" else None),
            )
        )
    return descriptors


def apply_structure_map(paragraphs: list[ParagraphUnit], structure_map: StructureMap, *, min_confidence: str = "medium") -> dict[str, int]:
    allowed_confidences = {"high"} if min_confidence == "high" else {"high", "medium"}
    applied_heading_count = 0
    applied_classified_count = 0
    for paragraph in paragraphs:
        if paragraph.role_confidence in {"explicit", "adjacent"}:
            continue

        classification = structure_map.get(paragraph.source_index)
        if classification is None or classification.confidence not in allowed_confidences:
            continue

        mapped_role = _map_ai_role_to_pipeline_role(classification.role)
        paragraph.role = mapped_role
        paragraph.role_confidence = "ai"
        paragraph.heading_source = "ai" if mapped_role == "heading" else None
        paragraph.structural_role = classification.role if classification.role in _PIPELINE_BODY_STRUCTURAL_ROLES else mapped_role
        if classification.heading_level is not None:
            paragraph.heading_level = classification.heading_level
        elif mapped_role != "heading":
            paragraph.heading_level = None
        applied_classified_count += 1
        if mapped_role == "heading":
            applied_heading_count += 1
    return {
        "ai_classified": applied_classified_count,
        "ai_headings": applied_heading_count,
    }


def build_structure_map(
    paragraphs: list[ParagraphUnit],
    *,
    client: object,
    model: str,
    max_window_paragraphs: int = 1800,
    overlap_paragraphs: int = 50,
    timeout: float = 60.0,
) -> StructureMap:
    started_at = time.perf_counter()
    descriptors = build_paragraph_descriptors(paragraphs)
    if not descriptors:
        return StructureMap({}, model, 0, 0.0, 0)

    merged_classifications: dict[int, ParagraphClassification] = {}
    window_count = 0
    total_tokens_used = 0
    for window in _iter_descriptor_windows(descriptors, max_window_paragraphs=max_window_paragraphs, overlap_paragraphs=overlap_paragraphs):
        window_count += 1
        try:
            window_classifications, window_tokens = _classify_descriptor_window(
                client=cast(_StructureRecognitionClient, client),
                model=model,
                descriptors=window,
                timeout=timeout,
            )
        except Exception:
            continue
        total_tokens_used += window_tokens
        _merge_window_classifications(merged_classifications, window_classifications, window=window)
    return StructureMap(
        classifications=merged_classifications,
        model_used=model,
        total_tokens_used=total_tokens_used,
        processing_time_seconds=max(0.0, time.perf_counter() - started_at),
        window_count=window_count,
    )


def _classify_descriptor_window(
    *,
    client: _StructureRecognitionClient,
    model: str,
    descriptors: Sequence[ParagraphDescriptor],
    timeout: float,
) -> tuple[list[ParagraphClassification], int]:
    system_prompt = _load_system_prompt()
    descriptor_payload = [descriptor.to_prompt_dict() for descriptor in descriptors]
    if not hasattr(client, "responses") or not hasattr(client.responses, "create"):
        raise RuntimeError("Unsupported structure recognition client")

    response = call_responses_create_with_retry(
        client,
        {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": _build_user_prompt(descriptor_payload)}],
                },
            ],
            "timeout": timeout,
        },
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
    )
    traversal = collect_response_text_traversal(
        response,
        unsupported_message="Structure recognition response used an unsupported text shape.",
    )
    content = normalize_model_output("\n".join(traversal.collected_texts) if traversal.collected_texts else (traversal.raw_output_text or ""))
    usage = getattr(response, "usage", None)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return _parse_classification_payload(content), total_tokens


def _parse_classification_payload(payload: str | Sequence[object]) -> list[ParagraphClassification]:
    parsed = json.loads(payload) if isinstance(payload, str) else list(payload)
    if not isinstance(parsed, list):
        raise ValueError("Structure recognition payload must be a JSON array")
    classifications: list[ParagraphClassification] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Structure recognition item must be an object")
        role = str(item["r"]).strip().lower()
        if role not in _VALID_AI_ROLES:
            raise ValueError(f"Unsupported structure recognition role: {role}")
        confidence = str(item["c"]).strip().lower()
        if confidence not in _VALID_AI_CONFIDENCES:
            raise ValueError(f"Unsupported structure recognition confidence: {confidence}")
        heading_level = _normalize_heading_level(item.get("l"), role=role)
        classifications.append(
            ParagraphClassification(
                index=int(item["i"]),
                role=role,
                heading_level=heading_level,
                confidence=confidence,
                rationale=None if item.get("reason") is None else str(item.get("reason")),
            )
        )
    return classifications


def _normalize_heading_level(raw_level: object, *, role: str) -> int | None:
    if role != "heading" or raw_level is None:
        return None
    return min(max(int(cast(Any, raw_level)), 1), 6)


def _build_user_prompt(descriptor_payload: Sequence[dict[str, object]]) -> str:
    return (
        "Classify each paragraph. Metadata format:\n"
        '{"i": index, "t": "text preview (first 60 chars)", "len": full_length, '
        '"s": "DOCX style", "b": bold, "ctr": centered, "caps": all_caps, '
        '"pt": font_size, "num": has_numbering, "hl": explicit_heading_level_or_null}\n\n'
        "Paragraphs:\n"
        f"{json.dumps(list(descriptor_payload), ensure_ascii=False)}"
    )


def _iter_descriptor_windows(
    descriptors: Sequence[ParagraphDescriptor],
    *,
    max_window_paragraphs: int,
    overlap_paragraphs: int,
) -> Iterable[list[ParagraphDescriptor]]:
    if max_window_paragraphs <= 0:
        raise ValueError("max_window_paragraphs must be positive")
    if overlap_paragraphs < 0:
        raise ValueError("overlap_paragraphs must be non-negative")
    if overlap_paragraphs >= max_window_paragraphs:
        raise ValueError("overlap_paragraphs must be smaller than max_window_paragraphs")

    start = 0
    step = max_window_paragraphs - overlap_paragraphs
    descriptor_list = list(descriptors)
    while start < len(descriptor_list):
        end = min(len(descriptor_list), start + max_window_paragraphs)
        yield descriptor_list[start:end]
        if end >= len(descriptor_list):
            break
        start += step


def _merge_window_classifications(
    merged: dict[int, ParagraphClassification],
    window_classifications: Sequence[ParagraphClassification],
    *,
    window: Sequence[ParagraphDescriptor],
) -> None:
    if not window:
        return
    window_indexes = [descriptor.index for descriptor in window]
    left_edge = min(window_indexes)
    right_edge = max(window_indexes)
    for classification in window_classifications:
        existing = merged.get(classification.index)
        if existing is None:
            merged[classification.index] = classification
            continue
        existing_distance = min(abs(existing.index - left_edge), abs(right_edge - existing.index))
        candidate_distance = min(abs(classification.index - left_edge), abs(right_edge - classification.index))
        if candidate_distance > existing_distance:
            merged[classification.index] = classification


def _map_ai_role_to_pipeline_role(ai_role: str) -> str:
    if ai_role in {"heading", "body", "caption", "list", "image", "table"}:
        return ai_role
    if ai_role in _PIPELINE_BODY_STRUCTURAL_ROLES:
        return "body"
    return "body"


__all__ = [
    "build_paragraph_descriptors",
    "apply_structure_map",
    "build_structure_map",
]
