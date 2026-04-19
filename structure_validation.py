from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from models import ParagraphUnit
from runtime_artifact_retention import (
    STRUCTURE_VALIDATION_MAX_AGE_SECONDS,
    STRUCTURE_VALIDATION_MAX_COUNT,
    prune_artifact_dir,
)


_STRUCTURE_VALIDATION_DEBUG_DIR = Path(__file__).resolve().parent / ".run" / "structure_validation"
_BODY_STRUCTURAL_ROLES = {"body", ""}
ParagraphLike = ParagraphUnit | Mapping[str, object]


@dataclass(frozen=True)
class StructureValidationReport:
    paragraph_count: int
    nonempty_paragraph_count: int
    explicit_heading_count: int
    heuristic_heading_count: int
    suspicious_short_body_count: int
    all_caps_body_count: int
    centered_body_count: int
    toc_like_sequence_count: int
    ambiguous_paragraph_count: int
    explicit_heading_density: float
    suspicious_short_body_ratio: float
    all_caps_or_centered_body_ratio: float
    escalation_recommended: bool
    escalation_reasons: tuple[str, ...] = ()


def _paragraph_value(paragraph: ParagraphLike, key: str, default: object = None) -> object:
    if isinstance(paragraph, Mapping):
        return paragraph.get(key, default)
    return getattr(paragraph, key, default)


def _paragraph_index(paragraph: ParagraphLike) -> int:
    value = _paragraph_value(paragraph, "source_index", -1)
    return value if isinstance(value, int) else -1


def _normalized_text(paragraph: ParagraphLike) -> str:
    return str(_paragraph_value(paragraph, "text", "") or "").strip()


def _word_count(text: str) -> int:
    return len([part for part in text.split() if part])


def _is_explicit_heading(paragraph: ParagraphLike) -> bool:
    return _paragraph_value(paragraph, "role") == "heading" and _paragraph_value(paragraph, "heading_source") == "explicit"


def _is_heuristic_heading(paragraph: ParagraphLike) -> bool:
    return _paragraph_value(paragraph, "role") == "heading" and _paragraph_value(paragraph, "heading_source") != "explicit"


def _is_body_like(paragraph: ParagraphLike) -> bool:
    return _paragraph_value(paragraph, "role") == "body" and str(_paragraph_value(paragraph, "structural_role", "body") or "body") in _BODY_STRUCTURAL_ROLES


def _is_suspicious_short_body(paragraph: ParagraphLike) -> bool:
    if not _is_body_like(paragraph):
        return False
    if _paragraph_value(paragraph, "list_kind") is not None or _paragraph_value(paragraph, "attached_to_asset_id") is not None:
        return False
    text = _normalized_text(paragraph)
    if not text:
        return False
    words = _word_count(text)
    if words < 1 or words > 8:
        return False
    return True


def _is_all_caps_body(paragraph: ParagraphLike) -> bool:
    if not _is_body_like(paragraph):
        return False
    text = _normalized_text(paragraph)
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 3:
        return False
    return "".join(letters).upper() == "".join(letters)


def _is_centered_body(paragraph: ParagraphLike) -> bool:
    return _is_body_like(paragraph) and _paragraph_value(paragraph, "paragraph_alignment") == "center"


def _is_toc_candidate(paragraph: ParagraphLike) -> bool:
    text = _normalized_text(paragraph)
    if not text:
        return False
    if _paragraph_value(paragraph, "role") == "heading":
        return False
    if str(_paragraph_value(paragraph, "structural_role", "body") or "body") in {"toc_entry", "toc_header"}:
        return False
    if _paragraph_value(paragraph, "list_kind") is not None or _paragraph_value(paragraph, "attached_to_asset_id") is not None:
        return False
    return _word_count(text) <= 12


def _count_toc_like_sequences(paragraphs: Sequence[ParagraphLike], *, min_length: int, ambiguous_indexes: set[int]) -> int:
    run_length = 0
    run_indexes: list[int] = []
    sequence_count = 0
    for paragraph in paragraphs:
        if _is_toc_candidate(paragraph):
            run_length += 1
            run_indexes.append(_paragraph_index(paragraph))
            continue
        if run_length >= min_length:
            sequence_count += 1
            ambiguous_indexes.update(run_indexes)
        run_length = 0
        run_indexes = []
    if run_length >= min_length:
        sequence_count += 1
        ambiguous_indexes.update(run_indexes)
    return sequence_count


def _max_body_run_length(paragraphs: Sequence[ParagraphLike]) -> int:
    current = 0
    maximum = 0
    for paragraph in paragraphs:
        text = _normalized_text(paragraph)
        if text and _paragraph_value(paragraph, "role") != "heading" and str(_paragraph_value(paragraph, "structural_role", "body") or "body") in _BODY_STRUCTURAL_ROLES:
            current += 1
            maximum = max(maximum, current)
            continue
        current = 0
    return maximum


def validate_structure_quality(
    *,
    paragraphs: Sequence[ParagraphLike],
    app_config: Mapping[str, Any],
) -> StructureValidationReport:
    paragraph_count = len(paragraphs)
    nonempty_paragraphs = [paragraph for paragraph in paragraphs if _normalized_text(paragraph)]
    nonempty_paragraph_count = len(nonempty_paragraphs)
    explicit_heading_count = sum(1 for paragraph in nonempty_paragraphs if _is_explicit_heading(paragraph))
    heuristic_heading_count = sum(1 for paragraph in nonempty_paragraphs if _is_heuristic_heading(paragraph))

    ambiguous_indexes: set[int] = set()
    suspicious_short_body_count = 0
    all_caps_body_count = 0
    centered_body_count = 0

    for paragraph in nonempty_paragraphs:
        if _is_suspicious_short_body(paragraph):
            suspicious_short_body_count += 1
            ambiguous_indexes.add(_paragraph_index(paragraph))
        if _is_all_caps_body(paragraph):
            all_caps_body_count += 1
            ambiguous_indexes.add(_paragraph_index(paragraph))
        if _is_centered_body(paragraph):
            centered_body_count += 1
            ambiguous_indexes.add(_paragraph_index(paragraph))

    toc_like_sequence_count = _count_toc_like_sequences(
        paragraphs,
        min_length=int(app_config.get("structure_validation_toc_like_sequence_min_length", 4) or 4),
        ambiguous_indexes=ambiguous_indexes,
    )
    all_caps_or_centered_count = len(
        {
            _paragraph_index(paragraph)
            for paragraph in nonempty_paragraphs
            if _is_all_caps_body(paragraph) or _is_centered_body(paragraph)
        }
    )
    divisor = nonempty_paragraph_count or 1
    explicit_heading_density = explicit_heading_count / divisor
    suspicious_short_body_ratio = suspicious_short_body_count / divisor
    all_caps_or_centered_body_ratio = all_caps_or_centered_count / divisor

    escalation_reasons: list[str] = []
    min_paragraphs_for_auto_gate = int(app_config.get("structure_validation_min_paragraphs_for_auto_gate", 40) or 40)
    min_explicit_heading_density = float(app_config.get("structure_validation_min_explicit_heading_density", 0.003) or 0.003)
    max_suspicious_short_body_ratio = float(
        app_config.get("structure_validation_max_suspicious_short_body_ratio_without_escalation", 0.05) or 0.05
    )
    max_all_caps_or_centered_body_ratio = float(
        app_config.get("structure_validation_max_all_caps_or_centered_body_ratio_without_escalation", 0.03) or 0.03
    )
    if nonempty_paragraph_count >= min_paragraphs_for_auto_gate and explicit_heading_density < min_explicit_heading_density:
        escalation_reasons.append("low_explicit_heading_density")
    if suspicious_short_body_ratio > max_suspicious_short_body_ratio:
        escalation_reasons.append("high_suspicious_short_body_ratio")
    if all_caps_or_centered_body_ratio > max_all_caps_or_centered_body_ratio:
        escalation_reasons.append("high_all_caps_or_centered_body_ratio")
    if toc_like_sequence_count > 0:
        escalation_reasons.append("toc_like_sequence_detected")
    if bool(app_config.get("structure_validation_forbid_heading_only_collapse", True)):
        if _max_body_run_length(paragraphs) >= 120 and explicit_heading_count < 3:
            escalation_reasons.append("heading_only_collapse_risk")

    return StructureValidationReport(
        paragraph_count=paragraph_count,
        nonempty_paragraph_count=nonempty_paragraph_count,
        explicit_heading_count=explicit_heading_count,
        heuristic_heading_count=heuristic_heading_count,
        suspicious_short_body_count=suspicious_short_body_count,
        all_caps_body_count=all_caps_body_count,
        centered_body_count=centered_body_count,
        toc_like_sequence_count=toc_like_sequence_count,
        ambiguous_paragraph_count=len(ambiguous_indexes),
        explicit_heading_density=explicit_heading_density,
        suspicious_short_body_ratio=suspicious_short_body_ratio,
        all_caps_or_centered_body_ratio=all_caps_or_centered_body_ratio,
        escalation_recommended=bool(escalation_reasons),
        escalation_reasons=tuple(escalation_reasons),
    )


def write_structure_validation_debug_artifact(
    *,
    report: StructureValidationReport,
    app_config: Mapping[str, Any],
) -> str:
    _STRUCTURE_VALIDATION_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    artifact_path = _STRUCTURE_VALIDATION_DEBUG_DIR / f"gate_report_{timestamp}.json"
    payload = {
        "mode": str(app_config.get("structure_recognition_mode", "off")),
        "model": str(app_config.get("structure_recognition_model", "")),
        **asdict(report),
        "escalation_reasons": list(report.escalation_reasons),
    }
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_artifact_dir(
        target_dir=_STRUCTURE_VALIDATION_DEBUG_DIR,
        max_age_seconds=STRUCTURE_VALIDATION_MAX_AGE_SECONDS,
        max_count=STRUCTURE_VALIDATION_MAX_COUNT,
    )
    return str(artifact_path)