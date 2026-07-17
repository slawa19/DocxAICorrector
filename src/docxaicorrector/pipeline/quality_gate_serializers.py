"""Pure quality-gate sample/decision serializers.

Byte-identical satellite extraction from ``pipeline/quality_gate.py`` (mirrors the
spec 035 output_validation pattern): the stateless ``getattr``-based serializers that
flatten assembly decisions and quality samples into JSON-ready dict rows. No behaviour
change -- ``quality_gate`` re-exports every name so ``quality_gate.<name>`` /
``late_phases.<name>`` keep resolving.
"""

from collections.abc import Mapping, Sequence


def _serialize_assembly_decisions(decisions: Sequence[object], *, limit: int = 20) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for decision in decisions[:limit]:
        action = getattr(decision, "action", None)
        block_index = getattr(decision, "block_index", None)
        paragraph_ids = getattr(decision, "paragraph_ids", ())
        reason = getattr(decision, "reason", None)
        serialized.append(
            {
                "action": action,
                "block_index": block_index,
                "paragraph_ids": list(paragraph_ids) if isinstance(paragraph_ids, tuple) else list(paragraph_ids or []),
                "reason": reason,
            }
        )
    return serialized


def _serialize_quality_samples(samples: Sequence[object], *, limit: int = 8) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for sample in list(samples)[:limit]:
        line = getattr(sample, "line", None)
        text = getattr(sample, "text", None)
        reason = getattr(sample, "reason", None)
        serialized.append(
            {
                "line": line,
                "text": text,
                "reason": reason,
            }
        )
    return serialized


def _serialize_paragraph_break_samples(samples: Sequence[object], *, limit: int = 8) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for sample in list(samples)[:limit]:
        serialized.append(
            {
                "source_index": getattr(sample, "source_index", None),
                "text": getattr(sample, "text", None),
                "next_text": getattr(sample, "next_text", None),
            }
        )
    return serialized


def _serialize_recovered_heading_entries(entries: Sequence[object], *, limit: int = 12) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for entry in list(entries)[:limit]:
        serialized.append(
            {
                "paragraph_id": getattr(entry, "paragraph_id", None),
                "source_index": getattr(entry, "source_index", None),
                "role": getattr(entry, "role", None),
                "structural_role": getattr(entry, "structural_role", None),
                "generated_heading_kind": getattr(entry, "generated_heading_kind", None),
                "text": getattr(entry, "text", None),
            }
        )
    return serialized


def _serialize_untranslated_structural_sample(sample: object) -> Mapping[str, object]:
    return {
        "line": getattr(sample, "line", None),
        "text": getattr(sample, "text", None),
        "reason": getattr(sample, "reason", None),
        "role": getattr(sample, "role", None),
        "structural_role": getattr(sample, "structural_role", None),
        "paragraph_id": getattr(sample, "paragraph_id", None),
        "char_count": getattr(sample, "char_count", 0),
    }


def _serialize_role_loss_sample(sample: Mapping[str, object]) -> dict[str, object]:
    text = sample.get("text_preview") or sample.get("generated_text_preview") or ""
    return {
        "line": None,
        "text": text,
        "reason": "content_survived_but_format_role_lost",
        "role": sample.get("role"),
        "structural_role": sample.get("structural_role"),
        # None on today's residual rows; the heading role above still yields "Заголовок".
        "heading_level": sample.get("heading_level"),
    }


def _serialize_heading_demotion_sample(sample: Mapping[str, object]) -> dict[str, object]:
    """Serialize a 1‑D heading-demotion sample (mapped source-heading rendered as
    body/list) into the role_loss review-item shape, tagged with its own reason so the
    UI can distinguish the demoted-heading axis from unmapped role-loss."""
    return {
        "line": None,
        "text": sample.get("text_preview") or "",
        "target_text": sample.get("target_text_preview") or "",
        "reason": "content_survived_but_heading_demoted",
        "role": sample.get("source_role"),
        "structural_role": sample.get("source_structural_role"),
        "heading_level": sample.get("source_heading_level"),
        "source_index": sample.get("source_index"),
        "mapped_target_index": sample.get("mapped_target_index"),
    }
