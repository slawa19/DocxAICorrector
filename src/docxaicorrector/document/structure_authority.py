from __future__ import annotations

from collections.abc import Mapping

from docxaicorrector.core.models import normalize_heuristic_role_hint, normalize_heuristic_structural_role_hint


ParagraphLike = object | Mapping[str, object]
_PRE_AI_DIAGNOSTIC_PHASES = {"pre_ai", "pre_ai_diagnostic", "diagnostic"}


def _paragraph_value(paragraph: ParagraphLike, key: str, default: object = None) -> object:
    if isinstance(paragraph, Mapping):
        return paragraph.get(key, default)
    return getattr(paragraph, key, default)


def normalize_structure_phase(phase: object, *, default: str = "post_ai_final") -> str:
    normalized = str(phase or "").strip().lower()
    return normalized or default


def phase_uses_advisory_hints(phase: object) -> bool:
    return normalize_structure_phase(phase) in _PRE_AI_DIAGNOSTIC_PHASES


def get_advisory_structural_role_hint(paragraph: ParagraphLike) -> str:
    return normalize_heuristic_structural_role_hint(_paragraph_value(paragraph, "heuristic_structural_role_hint", "")) or ""


def get_binding_structural_role(paragraph: ParagraphLike) -> str:
    structural_role = str(_paragraph_value(paragraph, "structural_role", "") or "").strip().lower()
    if structural_role:
        return structural_role
    role = str(_paragraph_value(paragraph, "role", "") or "").strip().lower()
    return role or "body"


def get_effective_structural_role(paragraph: ParagraphLike, *, phase: object = "post_ai_final") -> str:
    if phase_uses_advisory_hints(phase):
        hint = get_advisory_structural_role_hint(paragraph)
        if hint:
            return hint
    return get_binding_structural_role(paragraph)


def has_heading_signal(paragraph: ParagraphLike, *, phase: object = "post_ai_final") -> bool:
    role = str(_paragraph_value(paragraph, "role", "") or "").strip().lower()
    if role == "heading" and _paragraph_value(paragraph, "heading_source") is not None:
        return True
    if phase_uses_advisory_hints(phase):
        return normalize_heuristic_role_hint(_paragraph_value(paragraph, "heuristic_role_hint")) == "heading"
    return False


__all__ = [
    "get_advisory_structural_role_hint",
    "get_binding_structural_role",
    "get_effective_structural_role",
    "has_heading_signal",
    "normalize_structure_phase",
    "phase_uses_advisory_hints",
]