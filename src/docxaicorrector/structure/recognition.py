from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from collections.abc import Iterable, Sequence
import logging
import json
from pathlib import Path
import re
import time
from typing import Any, Callable, Protocol, cast

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.generation._generation import normalize_model_output
from docxaicorrector.core.models import DocumentMap, ParagraphClassification, ParagraphDescriptor, ParagraphUnit, StructureMap
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal
from docxaicorrector.structure._responses_timeout import call_responses_with_hard_timeout


SYSTEM_PROMPT_PATH = PROMPTS_DIR / "structure_recognition_system.txt"
_LOGGER = logging.getLogger(__name__)
_PIPELINE_BODY_STRUCTURAL_ROLES = {"epigraph", "attribution", "toc_entry", "toc_header", "dedication"}
_VALID_AI_ROLES = {"heading", "body", "caption", "epigraph", "attribution", "toc_entry", "toc_header", "dedication", "list"}
_VALID_AI_CONFIDENCES = {"high", "medium", "low"}
_LOCKED_ROLE_CONFIDENCES = {"explicit", "adjacent"}
_NON_OVERRIDEABLE_LOCKED_ROLES = {"image", "table", "caption"}
_DESCRIPTOR_PREVIEW_CHARS = 600
_MIN_TOKEN_BUDGET_PREVIEW_CHARS = 120
STRUCTURE_RECOGNITION_PROMPT_VERSION = 2
STRUCTURE_RECOGNITION_DESCRIPTOR_SCHEMA_VERSION = 2
_TIMEOUT_ERROR_NAMES = {"APITimeoutError", "TimeoutError"}
_SCRIPTURE_REFERENCE_PATTERN = re.compile(
    r"\b(?:[1-3]\s*)?(?:Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|"
    r"1\s*Samuel|2\s*Samuel|1\s*Kings|2\s*Kings|1\s*Chronicles|2\s*Chronicles|Ezra|"
    r"Nehemiah|Esther|Job|Psalms?|Proverbs|Ecclesiastes|Song of Solomon|Isaiah|Jeremiah|"
    r"Lamentations|Ezekiel|Daniel|Hosea|Joel|Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|"
    r"Zephaniah|Haggai|Zechariah|Malachi|Matthew|Mark|Luke|John|Acts|Romans|"
    r"1\s*Corinthians|2\s*Corinthians|Galatians|Ephesians|Philippians|Colossians|"
    r"1\s*Thessalonians|2\s*Thessalonians|1\s*Timothy|2\s*Timothy|Titus|Philemon|Hebrews|"
    r"James|1\s*Peter|2\s*Peter|1\s*John|2\s*John|3\s*John|Jude|Revelation|"
    r"Бытие|Исход|Левит|Числа|Второзаконие|Иисус[а]? Навин|Судей|Руфь|"
    r"1\s*Царств|2\s*Царств|3\s*Царств|4\s*Царств|1\s*Паралипоменон|2\s*Паралипоменон|Ездра|"
    r"Неемия|Есфирь|Иов|Пс(?:алом|алмы)?|Притч(?:и)?|Екклесиаст|Песнь Песней|Исаия|Иеремия|"
    r"Плач Иеремии|Иезекииль|Даниил|Осия|Иоиль|Амос|Авдий|Иона|Михей|Наум|Аввакум|"
    r"Софония|Аггей|Захария|Малахия|Матфея|Марка|Луки|Иоанна|Деяния|Римлянам|"
    r"1\s*Коринфянам|2\s*Коринфянам|Галатам|Ефесянам|Филиппийцам|Колоссянам|"
    r"1\s*Фессалоникийцам|2\s*Фессалоникийцам|1\s*Тимофею|2\s*Тимофею|Титу|Филимону|Евреям|"
    r"Иакова|1\s*Петра|2\s*Петра|1\s*Иоанна|2\s*Иоанна|3\s*Иоанна|Иуды|Откровение)\s+\d{1,3}[:.]\d{1,3}\b",
    re.IGNORECASE,
)


def _descriptor_preview_text(text: str, *, preview_chars: int = _DESCRIPTOR_PREVIEW_CHARS) -> str:
    stripped = text.strip()
    preview_limit = max(1, int(preview_chars or _DESCRIPTOR_PREVIEW_CHARS))
    if len(stripped) <= preview_limit:
        return stripped
    return stripped[:preview_limit].rstrip()


def _is_isolated_marker_text(text: str) -> bool:
    return bool(text in {"●", "•", "-", "*"} or re.match(r"^\d+[\.)]$", text))


def _is_toc_candidate_text(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    if re.search(r"\.{2,}\s*\d+\s*$", normalized):
        return True
    return len(normalized.split()) <= 12 and normalized.lower() in {"contents", "table of contents", "содержание"}


def _is_scripture_reference_text(text: str) -> bool:
    return bool(_SCRIPTURE_REFERENCE_PATTERN.search(text.strip()))


class _ResponsesApi(Protocol):
    def create(self, *, model: str, input: list[dict[str, object]], timeout: float) -> Any:
        ...


class _StructureRecognitionClient(Protocol):
    responses: _ResponsesApi


class _ResponsesCreateClient(Protocol):
    responses: _ResponsesApi


class StructureRecognitionRequestTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class StructureRecognitionProgress:
    event: str
    processed_windows: int
    total_windows: int
    current_window: int | None = None
    descriptor_count: int | None = None
    fallback_depth: int = 0


StructureProgressCallback = Callable[[StructureRecognitionProgress], None]


def _emit_structure_progress(
    callback: StructureProgressCallback | None,
    event: StructureRecognitionProgress,
) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:
        _LOGGER.debug(
            "Structure progress callback failed for event=%s current_window=%s processed=%s total=%s",
            event.event,
            event.current_window,
            event.processed_windows,
            event.total_windows,
            exc_info=True,
        )
        return


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


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_paragraph_descriptors(
    paragraphs: list[ParagraphUnit],
    *,
    document_map: DocumentMap | None = None,
    preview_chars: int = _DESCRIPTOR_PREVIEW_CHARS,
) -> list[ParagraphDescriptor]:
    descriptors: list[ParagraphDescriptor] = []
    nonempty_paragraphs = [paragraph for paragraph in paragraphs if str(paragraph.text or "").strip()]
    for index, paragraph in enumerate(nonempty_paragraphs):
        text = str(paragraph.text or "").strip()
        if not text:
            continue
        logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
        anchor = document_map.get_anchor(logical_index) if document_map is not None else None
        preview = _descriptor_preview_text(text, preview_chars=preview_chars)
        alpha_chars = [char for char in preview if char.isalpha()]
        embedded_hint_payload = _build_embedded_structure_hint_payload(paragraph, preview_chars=preview_chars)
        context_before = ""
        context_after = ""
        if index > 0:
            context_before = _descriptor_preview_text(str(nonempty_paragraphs[index - 1].text or ""), preview_chars=preview_chars)
        if index + 1 < len(nonempty_paragraphs):
            context_after = _descriptor_preview_text(str(nonempty_paragraphs[index + 1].text or ""), preview_chars=preview_chars)
        descriptors.append(
            ParagraphDescriptor(
                index=logical_index,
                text_preview=preview,
                text_length=len(text),
                style_name=paragraph.style_name,
                is_bold=paragraph.is_bold,
                is_centered=paragraph.paragraph_alignment == "center",
                is_all_caps=bool(alpha_chars) and preview.upper() == preview,
                font_size_pt=paragraph.font_size_pt,
                has_numbering=paragraph.list_kind is not None or any(hint.get("lk") is not None for hint in embedded_hint_payload),
                explicit_heading_level=(paragraph.heading_level if paragraph.heading_source == "explicit" else None),
                context_before_preview=context_before,
                context_after_preview=context_after,
                isolated_marker=bool(getattr(paragraph, "is_isolated_marker", False)) or any(
                    hint.get("iso", False) for hint in embedded_hint_payload
                ) or _is_isolated_marker_text(text),
                toc_candidate=bool(getattr(paragraph, "toc_pattern_hint", False)) or any(
                    hint.get("sr") in {"toc_header", "toc_entry"} for hint in embedded_hint_payload
                ) or _is_toc_candidate_text(text),
                scripture_reference_candidate=bool(getattr(paragraph, "scripture_reference_hint", False)) or any(
                    hint.get("scr", False) for hint in embedded_hint_payload
                ) or _is_scripture_reference_text(text),
                embedded_structure_hints=embedded_hint_payload,
                anchor_role=None if anchor is None else anchor.role,
                anchor_heading_level=None if anchor is None else anchor.heading_level,
                anchor_confidence=None if anchor is None else anchor.confidence,
            )
        )
    return descriptors


def _build_embedded_structure_hint_payload(
    paragraph: ParagraphUnit,
    *,
    preview_chars: int,
) -> tuple[dict[str, object], ...]:
    hints = getattr(paragraph, "heuristic_embedded_structure_hints", None) or ()
    preview_limit = max(1, int(preview_chars or _DESCRIPTOR_PREVIEW_CHARS))
    payload: list[dict[str, object]] = []
    for hint in hints:
        text = str(getattr(hint, "text", "") or "").strip()
        payload.append(
            {
                "t": _descriptor_preview_text(text, preview_chars=preview_limit),
                "r": str(getattr(hint, "role", "body") or "body"),
                "sr": str(getattr(hint, "structural_role", "body") or "body"),
                "hl": getattr(hint, "heading_level", None),
                "lk": getattr(hint, "list_kind", None),
                "iso": _is_isolated_marker_text(text),
                "scr": _is_scripture_reference_text(text),
            }
        )
    return tuple(payload)


def _is_anchor_consistent(
    classification: ParagraphClassification,
    *,
    anchor_role: str,
    anchor_heading_level: int | None,
) -> bool:
    if classification.role != anchor_role:
        return False
    if anchor_role != "heading":
        return True
    return classification.heading_level == anchor_heading_level


def _looks_clearly_prose_like(paragraph: ParagraphUnit) -> bool:
    text = str(getattr(paragraph, "text", "") or "").strip()
    if not text:
        return False
    words = [part for part in text.split() if part]
    if len(words) >= 12:
        return True
    return len(text) >= 80 or text.endswith((".", "!", "?", "…"))


def _looks_clearly_heading_like(paragraph: ParagraphUnit) -> bool:
    text = str(getattr(paragraph, "text", "") or "").strip()
    if not text:
        return False
    words = [part for part in text.split() if part]
    alpha_chars = [char for char in text if char.isalpha()]
    is_all_caps = bool(alpha_chars) and "".join(alpha_chars).upper() == "".join(alpha_chars)
    return bool(
        len(words) <= 10
        and len(text) <= 80
        and (
            bool(getattr(paragraph, "is_bold", False))
            or getattr(paragraph, "paragraph_alignment", None) == "center"
            or is_all_caps
            or getattr(paragraph, "heading_source", None) == "explicit"
            or getattr(paragraph, "heading_level", None) is not None
        )
    )


def _is_clearly_inconsistent_with_high_confidence_anchor(
    paragraph: ParagraphUnit,
    classification: ParagraphClassification,
    *,
    anchor_role: str,
) -> bool:
    if classification.role == anchor_role:
        return False
    if classification.confidence == "high":
        return False
    if anchor_role == "heading" and classification.role == "body":
        return _looks_clearly_prose_like(paragraph)
    if anchor_role == "body" and classification.role == "heading":
        return _looks_clearly_heading_like(paragraph) and classification.heading_level is not None
    return False


def _is_allowed_by_document_map_anchor(
    paragraph: ParagraphUnit,
    classification: ParagraphClassification,
    *,
    document_map: DocumentMap | None,
) -> bool:
    if document_map is None:
        return True

    logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
    anchor = document_map.get_anchor(logical_index)
    if anchor is None:
        return True

    if _is_anchor_consistent(
        classification,
        anchor_role=anchor.role,
        anchor_heading_level=anchor.heading_level,
    ):
        return True

    if anchor.confidence == "high":
        return False

    if anchor.confidence != "medium":
        return True

    # Medium anchors stay advisory-only: they constrain weak local drift inside
    # Stage 2 but do not become deterministic Stage 3 patch sources on their own.
    if classification.confidence != "high":
        return False

    if anchor.role == "body" and classification.role == "heading":
        return False

    return True


def apply_structure_map(
    paragraphs: list[ParagraphUnit],
    structure_map: StructureMap,
    *,
    min_confidence: str = "medium",
    document_map: DocumentMap | None = None,
) -> dict[str, int]:
    allowed_confidences = {"high"} if min_confidence == "high" else {"high", "medium"}
    applied_heading_count = 0
    applied_classified_count = 0
    reconciliation_patches_applied = 0
    reconciliation_locked_overrides_applied = 0
    reconciliation_locked_overrides_skipped = 0
    for paragraph in paragraphs:
        logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
        classification = structure_map.get(logical_index)
        if classification is None or classification.confidence not in allowed_confidences:
            continue
        is_locked = paragraph.role_confidence in _LOCKED_ROLE_CONFIDENCES
        if is_locked:
            if not _can_apply_locked_reconciliation_override(
                paragraph,
                classification,
                document_map=document_map,
            ):
                if classification.rationale == "document_map_reconciliation":
                    reconciliation_locked_overrides_skipped += 1
                continue
            reconciliation_locked_overrides_applied += 1
        elif not _is_allowed_by_document_map_anchor(
            paragraph,
            classification,
            document_map=document_map,
        ):
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
        if classification.rationale == "document_map_reconciliation":
            reconciliation_patches_applied += 1
        if mapped_role == "heading":
            applied_heading_count += 1
    return {
        "ai_classified": applied_classified_count,
        "ai_headings": applied_heading_count,
        "reconciliation_patches_applied": reconciliation_patches_applied,
        "reconciliation_locked_overrides_applied": reconciliation_locked_overrides_applied,
        "reconciliation_locked_overrides_skipped": reconciliation_locked_overrides_skipped,
    }


def _can_apply_locked_reconciliation_override(
    paragraph: ParagraphUnit,
    classification: ParagraphClassification,
    *,
    document_map: DocumentMap | None,
) -> bool:
    if document_map is None:
        return False
    if classification.rationale != "document_map_reconciliation" or classification.confidence != "high":
        return False

    current_role = str(paragraph.role or "").strip().lower()
    current_structural_role = str(paragraph.structural_role or "").strip().lower()
    if current_role in _NON_OVERRIDEABLE_LOCKED_ROLES or current_structural_role in _NON_OVERRIDEABLE_LOCKED_ROLES:
        return False
    if getattr(paragraph, "attached_to_asset_id", None) is not None:
        return False

    logical_index = int(getattr(paragraph, "logical_index", paragraph.source_index))
    anchor = document_map.get_anchor(logical_index)
    if anchor is None or str(anchor.confidence or "").strip().lower() != "high":
        return False

    desired_role = _map_ai_role_to_pipeline_role(classification.role)
    desired_heading_level = classification.heading_level if desired_role == "heading" else None
    anchor_heading_level = anchor.heading_level if anchor.role == "heading" else None
    if anchor.role != classification.role or anchor_heading_level != desired_heading_level:
        return False

    if current_role == "heading" and paragraph.heading_source == "explicit" and desired_role != "heading":
        return False
    if current_role == "heading" and paragraph.heading_source == "explicit" and desired_role == "heading" and desired_heading_level is None:
        return False
    return True


def build_structure_map(
    paragraphs: list[ParagraphUnit],
    *,
    client: object,
    model: str,
    max_window_paragraphs: int = 1800,
    overlap_paragraphs: int = 50,
    timeout: float = 60.0,
    document_map: DocumentMap | None = None,
    preview_chars: int = _DESCRIPTOR_PREVIEW_CHARS,
    target_input_tokens: int | None = None,
    progress_callback: StructureProgressCallback | None = None,
) -> StructureMap:
    started_at = time.perf_counter()
    descriptors = build_paragraph_descriptors(paragraphs, document_map=document_map, preview_chars=preview_chars)
    if not descriptors:
        return StructureMap({}, model, 0, 0.0, 0)

    windows = list(
        _iter_descriptor_windows(
            descriptors,
            max_window_paragraphs=max_window_paragraphs,
            overlap_paragraphs=overlap_paragraphs,
            target_input_tokens=target_input_tokens,
        )
    )
    total_windows = len(windows)
    processed_windows = 0

    _emit_structure_progress(
        progress_callback,
        StructureRecognitionProgress(
            event="prepared",
            processed_windows=0,
            total_windows=total_windows,
            descriptor_count=len(descriptors),
        ),
    )

    merged_classifications: dict[int, ParagraphClassification] = {}
    window_count = 0
    total_tokens_used = 0
    for window_index, window in enumerate(windows, start=1):
        _emit_structure_progress(
            progress_callback,
            StructureRecognitionProgress(
                event="window_started",
                processed_windows=processed_windows,
                total_windows=total_windows,
                current_window=window_index,
                descriptor_count=len(window),
            ),
        )
        try:
            resolved_windows, resolved_tokens = _classify_descriptor_window_with_fallback(
                client=cast(_StructureRecognitionClient, client),
                model=model,
                descriptors=window,
                timeout=timeout,
                progress_callback=progress_callback,
                processed_windows=processed_windows,
                total_windows=total_windows,
                current_window=window_index,
            )
        except Exception:
            window_count += 1
            processed_windows += 1
            _emit_structure_progress(
                progress_callback,
                StructureRecognitionProgress(
                    event="window_failed",
                    processed_windows=processed_windows,
                    total_windows=total_windows,
                    current_window=window_index,
                    descriptor_count=len(window),
                ),
            )
            continue
        window_count += len(resolved_windows)
        total_tokens_used += resolved_tokens
        for resolved_window, window_classifications in resolved_windows:
            _merge_window_classifications(merged_classifications, window_classifications, window=resolved_window)
        processed_windows += 1
        _emit_structure_progress(
            progress_callback,
            StructureRecognitionProgress(
                event="window_completed",
                processed_windows=processed_windows,
                total_windows=total_windows,
                current_window=window_index,
                descriptor_count=len(window),
            ),
        )
    _emit_structure_progress(
        progress_callback,
        StructureRecognitionProgress(
            event="completed",
            processed_windows=processed_windows,
            total_windows=total_windows,
        ),
    )
    return StructureMap(
        classifications=merged_classifications,
        model_used=model,
        total_tokens_used=total_tokens_used,
        processing_time_seconds=max(0.0, time.perf_counter() - started_at),
        window_count=window_count,
    )


def _classify_descriptor_window_with_fallback(
    *,
    client: _StructureRecognitionClient,
    model: str,
    descriptors: Sequence[ParagraphDescriptor],
    timeout: float,
    progress_callback: StructureProgressCallback | None = None,
    processed_windows: int = 0,
    total_windows: int = 0,
    current_window: int | None = None,
    fallback_depth: int = 0,
) -> tuple[list[tuple[list[ParagraphDescriptor], list[ParagraphClassification]]], int]:
    descriptor_list = list(descriptors)
    try:
        classifications, total_tokens = _classify_descriptor_window(
            client=client,
            model=model,
            descriptors=descriptor_list,
            timeout=timeout,
        )
        return [(descriptor_list, classifications)], total_tokens
    except Exception as exc:
        if not _should_split_descriptor_window(exc=exc, descriptor_count=len(descriptor_list)):
            raise

    _emit_structure_progress(
        progress_callback,
        StructureRecognitionProgress(
            event="window_split",
            processed_windows=processed_windows,
            total_windows=total_windows,
            current_window=current_window,
            descriptor_count=len(descriptor_list),
            fallback_depth=fallback_depth + 1,
        ),
    )

    midpoint = max(1, len(descriptor_list) // 2)
    left_windows, left_tokens = _classify_descriptor_window_with_fallback(
        client=client,
        model=model,
        descriptors=descriptor_list[:midpoint],
        timeout=timeout,
        progress_callback=progress_callback,
        processed_windows=processed_windows,
        total_windows=total_windows,
        current_window=current_window,
        fallback_depth=fallback_depth + 1,
    )
    right_windows, right_tokens = _classify_descriptor_window_with_fallback(
        client=client,
        model=model,
        descriptors=descriptor_list[midpoint:],
        timeout=timeout,
        progress_callback=progress_callback,
        processed_windows=processed_windows,
        total_windows=total_windows,
        current_window=current_window,
        fallback_depth=fallback_depth + 1,
    )
    return left_windows + right_windows, left_tokens + right_tokens


def _should_split_descriptor_window(*, exc: Exception, descriptor_count: int) -> bool:
    if descriptor_count <= 1:
        return False
    error_name = type(exc).__name__
    if error_name in _TIMEOUT_ERROR_NAMES:
        return True
    error_text = str(exc).strip().casefold()
    return "timed out" in error_text or "timeout" in error_text


def _classify_descriptor_window(
    *,
    client: _StructureRecognitionClient,
    model: str,
    descriptors: Sequence[ParagraphDescriptor],
    timeout: float,
) -> tuple[list[ParagraphClassification], int]:
    system_prompt = _load_system_prompt()
    descriptor_payload = [descriptor.to_prompt_dict() for descriptor in descriptors]
    timeout_scoped_client = _with_request_timeout(client, timeout=timeout)
    responses_client = _as_responses_create_client(timeout_scoped_client)
    if responses_client is None:
        raise RuntimeError("Unsupported structure recognition client")

    response = _call_structure_responses_with_timeout(
        client=responses_client,
        request_payload={
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
        timeout=timeout,
    )
    traversal = collect_response_text_traversal(
        response,
        unsupported_message="Structure recognition response used an unsupported text shape.",
    )
    content = normalize_model_output("\n".join(traversal.collected_texts) if traversal.collected_texts else (traversal.raw_output_text or ""))
    usage = getattr(response, "usage", None)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return _parse_classification_payload(content), total_tokens


def _call_structure_responses_with_timeout(
    *, client: _ResponsesCreateClient, request_payload: dict[str, object], timeout: float
) -> Any:
    return call_responses_with_hard_timeout(
        client=client,
        request_payload=request_payload,
        timeout=timeout,
        thread_name="structure-recognition-request",
        logger=_LOGGER,
        request_kind="structure_recognition_request",
        timeout_error_factory=lambda seconds: StructureRecognitionRequestTimeout(
            f"Structure recognition request timed out after {seconds:.3f}s."
        ),
    )


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
        '{"i": index, "t": "text preview", "len": full_length, '
        '"s": "DOCX style", "b": bold, "ctr": centered, "caps": all_caps, '
        '"pt": font_size, "num": has_numbering, "hl": explicit_heading_level_or_null, '
        '"prev": "previous paragraph preview", "next": "next paragraph preview", '
        '"iso": isolated_marker, "toc": toc_candidate, "scr": scripture_reference_candidate, '
        '"anchor_r": optional_document_map_role, "anchor_l": optional_document_map_heading_level, '
        '"anchor_c": optional_document_map_confidence}\n\n'
        "Paragraphs:\n"
        f"{json.dumps(list(descriptor_payload), ensure_ascii=False)}"
    )


def _iter_descriptor_windows(
    descriptors: Sequence[ParagraphDescriptor],
    *,
    max_window_paragraphs: int,
    overlap_paragraphs: int,
    target_input_tokens: int | None = None,
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
    budget_limit = None if target_input_tokens is None else max(1, int(target_input_tokens or 0))
    while start < len(descriptor_list):
        end = min(len(descriptor_list), start + max_window_paragraphs)
        window = descriptor_list[start:end]
        if budget_limit is not None:
            window = _shrink_window_to_token_budget(
                descriptor_list,
                start=start,
                end=end,
                budget_limit=budget_limit,
            )
        yield window
        end = start + len(window)
        if end >= len(descriptor_list):
            break
        next_start = end - overlap_paragraphs
        start = next_start if next_start > start else start + 1


def _shrink_window_to_token_budget(
    descriptors: Sequence[ParagraphDescriptor],
    *,
    start: int,
    end: int,
    budget_limit: int,
) -> list[ParagraphDescriptor]:
    candidate_window = list(descriptors[start : max(start + 1, end)])
    preview_fitted = _shrink_preview_to_token_budget(candidate_window, budget_limit=budget_limit)
    if preview_fitted is not None:
        return preview_fitted

    minimized_window = [
        _truncate_descriptor_previews(descriptor, preview_chars=_MIN_TOKEN_BUDGET_PREVIEW_CHARS)
        for descriptor in candidate_window
    ]
    low = 1
    high = len(minimized_window)
    best_fit: list[ParagraphDescriptor] | None = None
    while low <= high:
        mid = (low + high) // 2
        candidate_prefix = minimized_window[:mid]
        if _estimate_descriptor_window_tokens(candidate_prefix) <= budget_limit:
            best_fit = candidate_prefix
            low = mid + 1
        else:
            high = mid - 1

    if best_fit is not None:
        return best_fit
    return minimized_window[:1] or list(descriptors[start : min(start + 1, len(descriptors))])


def _shrink_preview_to_token_budget(
    descriptors: list[ParagraphDescriptor],
    *,
    budget_limit: int,
) -> list[ParagraphDescriptor] | None:
    if _estimate_descriptor_window_tokens(descriptors) <= budget_limit:
        return descriptors

    max_preview_chars = max(
        max(len(descriptor.text_preview), len(descriptor.context_before_preview), len(descriptor.context_after_preview))
        for descriptor in descriptors
    )
    if max_preview_chars <= _MIN_TOKEN_BUDGET_PREVIEW_CHARS:
        return None

    preview_chars = max_preview_chars
    while preview_chars > _MIN_TOKEN_BUDGET_PREVIEW_CHARS:
        preview_chars = max(_MIN_TOKEN_BUDGET_PREVIEW_CHARS, preview_chars // 2)
        shrunk = [_truncate_descriptor_previews(descriptor, preview_chars=preview_chars) for descriptor in descriptors]
        if _estimate_descriptor_window_tokens(shrunk) <= budget_limit:
            return shrunk
    return None


def _truncate_descriptor_previews(descriptor: ParagraphDescriptor, *, preview_chars: int) -> ParagraphDescriptor:
    return replace(
        descriptor,
        text_preview=_descriptor_preview_text(descriptor.text_preview, preview_chars=preview_chars),
        context_before_preview=_descriptor_preview_text(descriptor.context_before_preview, preview_chars=preview_chars),
        context_after_preview=_descriptor_preview_text(descriptor.context_after_preview, preview_chars=preview_chars),
    )


def _estimate_descriptor_window_tokens(descriptors: Sequence[ParagraphDescriptor]) -> int:
    if not descriptors:
        return 0
    prompt_payload = [descriptor.to_prompt_dict() for descriptor in descriptors]
    encoded = json.dumps(prompt_payload, ensure_ascii=False)
    return max(1, len(encoded) // 4 + 64)


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
