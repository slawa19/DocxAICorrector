#!/usr/bin/env python3
"""Classify formatting residuals from an existing real-document report.

This is an offline PR-I2d helper. It does not run the pipeline; it reads an
already written JSON report and classifies saved restore-diagnostic residual
samples into marker-closable, dissolved, aggregate, and uncovered buckets.
"""

from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


def _iter_restore_diagnostics(value: Any, path: str = "$") -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        residual = value.get("unmapped_source_residual_diagnostics")
        if isinstance(residual, Mapping):
            yield path, value
        for key, child in value.items():
            yield from _iter_restore_diagnostics(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _iter_restore_diagnostics(child, f"{path}[{index}]")


def _mapped_source_by_target(diagnostic: Mapping[str, Any]) -> dict[int, int]:
    mapped: dict[int, int] = {}
    source_registry = diagnostic.get("source_registry")
    if not isinstance(source_registry, list):
        return mapped
    for fallback_index, entry in enumerate(source_registry):
        if not isinstance(entry, Mapping):
            continue
        target_index = entry.get("mapped_target_index")
        source_index = entry.get("source_index", fallback_index)
        if isinstance(target_index, int) and isinstance(source_index, int):
            mapped[target_index] = source_index
    return mapped


def _target_roles_by_index(diagnostic: Mapping[str, Any]) -> dict[int, str]:
    roles: dict[int, str] = {}
    target_registry = diagnostic.get("target_registry")
    if not isinstance(target_registry, list):
        return roles
    for fallback_index, entry in enumerate(target_registry):
        if not isinstance(entry, Mapping):
            continue
        target_index = entry.get("target_index", fallback_index)
        if not isinstance(target_index, int):
            continue
        heading_level = entry.get("heading_level")
        roles[target_index] = "heading" if isinstance(heading_level, int) else "body"
    return roles


def _target_previews_by_index(diagnostic: Mapping[str, Any]) -> dict[int, str]:
    previews: dict[int, str] = {}
    target_registry = diagnostic.get("target_registry")
    if not isinstance(target_registry, list):
        return previews
    for fallback_index, entry in enumerate(target_registry):
        if not isinstance(entry, Mapping):
            continue
        target_index = entry.get("target_index", fallback_index)
        text_preview = entry.get("text_preview")
        if isinstance(target_index, int) and isinstance(text_preview, str):
            previews[target_index] = text_preview
    return previews


def _source_format_role(sample: Mapping[str, Any]) -> str:
    role = str(sample.get("role") or "").strip().lower()
    structural_role = str(sample.get("structural_role") or "").strip().lower()
    if role == "heading" or structural_role == "heading":
        return "heading"
    if role == "list" or structural_role in {"list", "list_item"}:
        return "list"
    if role == "caption" or structural_role == "caption":
        return "caption"
    if structural_role in {"toc_header", "toc_entry"}:
        return "toc"
    if structural_role in {"epigraph", "attribution", "dedication"}:
        return structural_role
    return "body"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _text_coverage_evidence(candidate_text: str, target_text: str) -> dict[str, Any] | None:
    normalized_candidate = _normalize_text(candidate_text)
    normalized_target = _normalize_text(target_text)
    if not normalized_candidate or not normalized_target:
        return None
    if normalized_candidate == normalized_target or normalized_candidate in normalized_target:
        return {"evidence_type": "exact_contains", "score": 1.0, "token_overlap_ratio": 1.0}

    candidate_tokens = set(re.findall(r"\w+", normalized_candidate, flags=re.UNICODE))
    target_tokens = set(re.findall(r"\w+", normalized_target, flags=re.UNICODE))
    if not candidate_tokens or not target_tokens:
        return None
    common_count = len(candidate_tokens & target_tokens)
    token_overlap_ratio = common_count / len(candidate_tokens)
    sequence_ratio = SequenceMatcher(None, normalized_candidate, normalized_target).ratio()
    if (
        (common_count >= 4 and token_overlap_ratio >= 0.62)
        or (common_count >= 2 and token_overlap_ratio >= 0.8)
        or (len(normalized_candidate) >= 20 and sequence_ratio >= 0.75)
    ):
        return {
            "evidence_type": "fuzzy_token_overlap",
            "score": round(max(token_overlap_ratio, sequence_ratio), 4),
            "token_overlap_ratio": round(token_overlap_ratio, 4),
            "sequence_ratio": round(sequence_ratio, 4),
            "common_token_count": common_count,
            "candidate_token_count": len(candidate_tokens),
        }
    return None


def _neighbor_evidence(
    sample: Mapping[str, Any],
    mapped_source_by_target: Mapping[int, int],
    target_previews_by_index: Mapping[int, str],
    *,
    source_window: int = 3,
) -> list[dict[str, Any]]:
    source_index = sample.get("source_index")
    candidate_text = sample.get("generated_text_preview") or sample.get("text_preview")
    if not isinstance(source_index, int) or not isinstance(candidate_text, str):
        return []
    evidence: list[dict[str, Any]] = []
    for target_index, mapped_source_index in sorted(mapped_source_by_target.items()):
        target_text = target_previews_by_index.get(target_index)
        if not target_text:
            continue
        source_distance = abs(mapped_source_index - source_index)
        if source_distance > source_window:
            continue
        text_evidence = _text_coverage_evidence(candidate_text, target_text)
        if text_evidence is None:
            continue
        evidence.append(
            {
                "target_index": target_index,
                "mapped_source_index": mapped_source_index,
                "source_distance": source_distance,
                **text_evidence,
            }
        )
    return evidence


def _free_target_candidates(sample: Mapping[str, Any], mapped_source_by_target: Mapping[int, int]) -> list[int]:
    target_candidates = sample.get("target_candidate_indexes_containing_registry_text")
    if not isinstance(target_candidates, list):
        return []
    return [
        target_index
        for target_index in target_candidates
        if isinstance(target_index, int) and target_index not in mapped_source_by_target
    ]


def _classify_sample(
    sample: Mapping[str, Any],
    mapped_source_by_target: Mapping[int, int],
    target_previews_by_index: Mapping[int, str],
) -> str:
    residual_category = str(sample.get("residual_category") or "")
    free_candidates = _free_target_candidates(sample, mapped_source_by_target)
    neighbor_evidence = _neighbor_evidence(sample, mapped_source_by_target, target_previews_by_index)

    if residual_category == "single_origin_lost_match":
        if free_candidates:
            return "target_exists_text_align_missed"
        if neighbor_evidence:
            return "target_occupied_by_mapped_neighbor"
        return "target_absent_or_unproven"
    if residual_category == "true_aggregate_unmapped":
        return "true_aggregate_relation_gap"
    if residual_category == "real_uncovered":
        return "real_uncovered"
    if residual_category == "image_or_placeholder_accounted_elsewhere":
        return "image_or_placeholder_accounted_elsewhere"
    return "unknown"


def _classify_effective_formatting_coverage(
    sample: Mapping[str, Any],
    mapped_source_by_target: Mapping[int, int],
    target_roles_by_index: Mapping[int, str],
    target_previews_by_index: Mapping[int, str],
) -> str:
    residual_category = str(sample.get("residual_category") or "")
    if residual_category == "single_origin_lost_match":
        neighbor_evidence = _neighbor_evidence(sample, mapped_source_by_target, target_previews_by_index)
        if not neighbor_evidence:
            return "unproven_or_marker_closable"
        source_format_role = _source_format_role(sample)
        if source_format_role == "body" and any(
            target_roles_by_index.get(evidence["target_index"]) == "body" for evidence in neighbor_evidence
        ):
            return "format_neutral_body_dissolved_creditable"
        return "content_survived_but_format_role_lost"
    if residual_category == "true_aggregate_unmapped":
        return "true_aggregate_relation_gap"
    if residual_category == "real_uncovered":
        return "real_uncovered"
    if residual_category == "image_or_placeholder_accounted_elsewhere":
        return "image_or_placeholder_accounted_elsewhere"
    return "unknown"


def _count_classes(
    samples: list[Mapping[str, Any]],
    mapped_source_by_target: Mapping[int, int],
    target_previews_by_index: Mapping[int, str],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        class_name = _classify_sample(sample, mapped_source_by_target, target_previews_by_index)
        counts[class_name] = counts.get(class_name, 0) + 1
    return dict(sorted(counts.items()))


def _count_effective_classes(
    samples: list[Mapping[str, Any]],
    mapped_source_by_target: Mapping[int, int],
    target_roles_by_index: Mapping[int, str],
    target_previews_by_index: Mapping[int, str],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        class_name = _classify_effective_formatting_coverage(
            sample,
            mapped_source_by_target,
            target_roles_by_index,
            target_previews_by_index,
        )
        counts[class_name] = counts.get(class_name, 0) + 1
    return dict(sorted(counts.items()))


def _summarize_diagnostic(path: str, diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    residual = diagnostic.get("unmapped_source_residual_diagnostics")
    if not isinstance(residual, Mapping):
        residual = {}
    residual_rows = residual.get("residual_rows")
    if not isinstance(residual_rows, list):
        residual_rows = []
    samples = residual.get("samples")
    if not isinstance(samples, list):
        samples = []
    row_source = residual_rows if residual_rows else samples
    row_mappings = [sample for sample in row_source if isinstance(sample, Mapping)]
    category_counts = residual.get("category_counts")
    if not isinstance(category_counts, Mapping):
        category_counts = {}
    total_residual_count = sum(value for value in category_counts.values() if isinstance(value, int))
    mapped_source_by_target = _mapped_source_by_target(diagnostic)
    target_roles_by_index = _target_roles_by_index(diagnostic)
    target_previews_by_index = _target_previews_by_index(diagnostic)
    classification_counts = _count_classes(row_mappings, mapped_source_by_target, target_previews_by_index)
    effective_counts = _count_effective_classes(
        row_mappings,
        mapped_source_by_target,
        target_roles_by_index,
        target_previews_by_index,
    )

    return {
        "path": path,
        "stage": diagnostic.get("stage"),
        "source_count": diagnostic.get("source_count"),
        "target_count": diagnostic.get("target_count"),
        "mapped_count": diagnostic.get("mapped_count"),
        "unmapped_source_count": len(diagnostic.get("unmapped_source_ids") or []),
        "unmapped_target_count": len(diagnostic.get("unmapped_target_indexes") or []),
        "residual_category_counts": dict(sorted(category_counts.items())),
        "classification_basis": "full_residual_rows" if residual_rows else "saved_residual_samples",
        "sample_based": not bool(residual_rows),
        "row_count": len(row_mappings),
        "sample_count": len(samples),
        "total_residual_count_from_category_counts": total_residual_count,
        "classification_counts": classification_counts,
        "embedded_marker_upper_bound_count": classification_counts.get("target_exists_text_align_missed", 0),
        "embedded_marker_upper_bound_class": "target_exists_text_align_missed",
        "embedded_marker_upper_bound_note": "Counts only candidates on unmapped/free target paragraphs.",
        "effective_formatting_coverage_counts": effective_counts,
        "format_neutral_creditable_count": effective_counts.get("format_neutral_body_dissolved_creditable", 0),
        "effective_formatting_coverage_note": (
            "Only body source with exact/fuzzy evidence in an already mapped neighbor body target is credited."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_json", type=Path, help="Existing real-document report JSON")
    parser.add_argument(
        "--diagnostic-index",
        type=int,
        default=-1,
        help="Which restore diagnostics block to print. Default: -1 (last/final). Use --all for every block.",
    )
    parser.add_argument("--all", action="store_true", help="Print summaries for every restore diagnostics block")
    args = parser.parse_args()

    payload = json.loads(args.report_json.read_text(encoding="utf-8"))
    summaries = [_summarize_diagnostic(path, diagnostic) for path, diagnostic in _iter_restore_diagnostics(payload)]
    if args.all:
        result: Any = summaries
    else:
        if not summaries:
            raise SystemExit(f"No restore diagnostics found in {args.report_json}")
        result = summaries[args.diagnostic_index]
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
