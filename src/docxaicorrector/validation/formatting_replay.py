from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any, cast

from docx import Document

from docxaicorrector.core.models import ParagraphUnit
from docxaicorrector.document._document import extract_document_content_from_docx
from docxaicorrector.generation.formatting_transfer import (
    _build_output_formatting_diagnostics,
    _collect_target_paragraphs,
)
from docxaicorrector.validation.formatting_coverage import (
    resolve_role_aware_formatting_unmapped_source_summary,
)


_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s*(?P<marker>#{1,6})\s+(?P<text>\S.*)$")
_MARKDOWN_BULLET_PATTERN = re.compile(r"^\s*(?:[-*+]|\u2022)\s+(?P<text>\S.*)$")
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\s*\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]\s*$")


def _iter_report_search_roots(report_path: Path, report_payload: Mapping[str, object]) -> list[Path]:
    roots: list[Path] = [report_path.parent.resolve()]
    for parent in report_path.parents[1:5]:
        roots.append(parent.resolve())

    run_payload = report_payload.get("run")
    if isinstance(run_payload, Mapping):
        artifact_root = resolve_report_artifact_path(
            report_path=report_path,
            candidate_path=cast(str | None, run_payload.get("artifact_root")),
        )
        if artifact_root is not None:
            roots.append(artifact_root.resolve())

    artifact_dir = resolve_report_artifact_path(
        report_path=report_path,
        candidate_path=cast(str | None, report_payload.get("artifact_dir")),
    )
    if artifact_dir is not None:
        roots.append(artifact_dir.resolve())

    unique_roots: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        if root in seen or not root.exists():
            continue
        seen.add(root)
        unique_roots.append(root)
    return unique_roots


def resolve_report_artifact_path(*, report_path: Path, candidate_path: str | None) -> Path | None:
    if not candidate_path:
        return None
    candidate = Path(candidate_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    report_relative = (report_path.parent / candidate).resolve()
    if report_relative.exists():
        return report_relative
    cwd_relative = (Path.cwd() / candidate).resolve()
    if cwd_relative.exists():
        return cwd_relative
    return None


def load_report_payload(report_path: Path) -> dict[str, object]:
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Report payload is not a JSON object: {report_path}")
    return payload


def resolve_source_docx_from_report(
    *,
    report_path: Path,
    report_payload: Mapping[str, object],
    target_docx_path: Path | None,
) -> Path | None:
    candidate_names: list[str] = []

    preparation = report_payload.get("preparation")
    if isinstance(preparation, Mapping):
        uploaded_filename = str(preparation.get("uploaded_filename") or "").strip()
        if uploaded_filename.lower().endswith(".docx"):
            candidate_names.append(Path(uploaded_filename).name)

    if target_docx_path is not None:
        candidate_names.append(target_docx_path.name)

    seen_names: set[str] = set()
    normalized_names = [name for name in candidate_names if not (name in seen_names or seen_names.add(name))]
    if not normalized_names:
        return None

    target_resolved = target_docx_path.resolve() if target_docx_path is not None and target_docx_path.exists() else None
    for root in _iter_report_search_roots(report_path, report_payload):
        for candidate_name in normalized_names:
            direct_candidate = (root / candidate_name).resolve()
            if direct_candidate.exists() and direct_candidate.is_file():
                if target_resolved is None or direct_candidate != target_resolved:
                    return direct_candidate
    return None


def _coerce_mapping_sequence(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def build_source_paragraphs_from_saved_registry(
    source_registry: Sequence[Mapping[str, object]],
) -> list[ParagraphUnit]:
    paragraphs: list[ParagraphUnit] = []
    for fallback_index, entry in enumerate(source_registry):
        text = str(entry.get("text_preview") or "").strip()
        paragraphs.append(
            ParagraphUnit(
                text=text,
                role=str(entry.get("role") or "body"),
                structural_role=str(entry.get("structural_role") or entry.get("role") or "body"),
                role_confidence=str(entry.get("role_confidence") or "heuristic"),
                paragraph_id=str(entry.get("paragraph_id") or ""),
                source_index=int(entry.get("source_index", fallback_index) or fallback_index),
                heading_level=cast(int | None, entry.get("heading_level")),
                list_kind=cast(str | None, entry.get("list_kind")),
                list_level=int(entry.get("list_level", 0) or 0),
                list_numbering_format=cast(str | None, entry.get("list_numbering_format")),
                list_num_id=cast(str | None, entry.get("list_num_id")),
                list_abstract_num_id=cast(str | None, entry.get("list_abstract_num_id")),
                asset_id=cast(str | None, entry.get("asset_id")),
                attached_to_asset_id=cast(str | None, entry.get("attached_to_asset_id")),
                origin_raw_indexes=[int(value) for value in cast(Sequence[object], entry.get("origin_raw_indexes") or []) if isinstance(value, int)],
                boundary_source=str(entry.get("boundary_source") or "raw"),
                boundary_confidence=str(entry.get("boundary_confidence") or "heuristic"),
                boundary_rationale=cast(str | None, entry.get("boundary_rationale")),
            )
        )
    return paragraphs


def _coerce_target_paragraph_indexes(value: object) -> list[int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [int(item) for item in value if isinstance(item, int)]


def _build_source_paragraph_from_final_registry_entry(
    entry: Mapping[str, object],
    *,
    fallback_index: int,
) -> ParagraphUnit:
    raw_text = str(entry.get("text") or entry.get("generated_text") or entry.get("text_preview") or "").strip()
    text = raw_text
    role = "body"
    structural_role = "body"
    heading_level: int | None = None
    list_kind: str | None = None

    heading_match = _MARKDOWN_HEADING_PATTERN.match(raw_text)
    if heading_match is not None:
        heading_level = len(str(heading_match.group("marker") or "#"))
        text = str(heading_match.group("text") or "").strip()
        role = "heading"
        structural_role = "heading"
    elif _DOCX_IMAGE_PLACEHOLDER_PATTERN.match(raw_text) is not None:
        role = "image"
        structural_role = "image"
    else:
        bullet_match = _MARKDOWN_BULLET_PATTERN.match(raw_text)
        if bullet_match is not None:
            text = str(bullet_match.group("text") or "").strip()
            role = "list"
            structural_role = "list_item"
            list_kind = "bullet"

    return ParagraphUnit(
        text=text,
        role=role,
        structural_role=structural_role,
        role_confidence="final_registry_replay",
        paragraph_id=str(entry.get("paragraph_id") or f"p{fallback_index:04d}"),
        source_index=fallback_index,
        heading_level=heading_level,
        list_kind=list_kind,
    )


def build_source_paragraphs_from_final_generated_registry(
    generated_paragraph_registry: Sequence[Mapping[str, object]],
) -> list[ParagraphUnit]:
    paragraphs: list[ParagraphUnit] = []
    for fallback_index, entry in enumerate(generated_paragraph_registry):
        if not str(entry.get("paragraph_id") or "").strip() and not str(entry.get("text") or "").strip():
            continue
        paragraphs.append(_build_source_paragraph_from_final_registry_entry(entry, fallback_index=fallback_index))
    return paragraphs


def _select_final_generated_paragraph_registry(
    report_payload: Mapping[str, object],
) -> list[Mapping[str, object]]:
    runtime = report_payload.get("runtime")
    if not isinstance(runtime, Mapping):
        return []
    state = runtime.get("state")
    if not isinstance(state, Mapping):
        return []
    return _coerce_mapping_sequence(state.get("final_generated_paragraph_registry"))


def _saved_registry_preview_looks_source_language(
    source_registry: Sequence[Mapping[str, object]],
    target_registry: Sequence[Mapping[str, object]],
) -> bool:
    source_previews = [
        str(entry.get("text_preview") or "").strip().casefold()
        for entry in source_registry[:8]
        if str(entry.get("text_preview") or "").strip()
    ]
    target_previews = [
        str(entry.get("text_preview") or "").strip().casefold()
        for entry in target_registry[:8]
        if str(entry.get("text_preview") or "").strip()
    ]
    if not source_previews or not target_previews:
        return False
    if any(preview.startswith("contents") or preview.startswith("foreword") or preview.startswith("introduction") for preview in source_previews):
        if any("содержание" in preview or "предислов" in preview or "введение" in preview for preview in target_previews):
            return True
    return False


def _select_formatting_payload(
    report_payload: Mapping[str, object],
    diagnostic_index: int = -1,
) -> Mapping[str, object] | None:
    formatting_diagnostics = _coerce_mapping_sequence(report_payload.get("formatting_diagnostics"))
    if not formatting_diagnostics:
        return None
    return formatting_diagnostics[diagnostic_index]


def replay_formatting_diagnostics_from_report(
    *,
    report_path: Path,
    diagnostic_index: int = -1,
    source_docx_path: Path | None = None,
    target_docx_path: Path | None = None,
) -> dict[str, object]:
    report_payload = load_report_payload(report_path)
    saved_payload = _select_formatting_payload(report_payload, diagnostic_index=diagnostic_index)
    final_generated_registry = _select_final_generated_paragraph_registry(report_payload)
    if saved_payload is None and not final_generated_registry:
        raise ValueError(f"No formatting_diagnostics or final_generated_paragraph_registry found in {report_path}")

    output_artifacts = cast(Mapping[str, object], report_payload.get("output_artifacts") or {})
    resolved_target_docx_path = target_docx_path or resolve_report_artifact_path(
        report_path=report_path,
        candidate_path=cast(str | None, output_artifacts.get("docx_path")),
    )
    if resolved_target_docx_path is None or not resolved_target_docx_path.exists():
        raise FileNotFoundError("Target DOCX path for replay is missing.")

    source_registry = _coerce_mapping_sequence(saved_payload.get("source_registry")) if saved_payload is not None else []
    saved_target_registry = _coerce_mapping_sequence(saved_payload.get("target_registry")) if saved_payload is not None else []
    resolved_source_docx_path = source_docx_path
    if resolved_source_docx_path is not None:
        if not resolved_source_docx_path.exists():
            raise FileNotFoundError(f"Explicit source_docx_path does not exist: {resolved_source_docx_path}")
        source_paragraphs, _ = extract_document_content_from_docx(BytesIO(resolved_source_docx_path.read_bytes()))
        source_reconstruction_basis = "source_docx_override"
    elif (
        source_registry
        and final_generated_registry
        and _saved_registry_preview_looks_source_language(source_registry, saved_target_registry)
    ):
        source_paragraphs = build_source_paragraphs_from_final_generated_registry(final_generated_registry)
        source_reconstruction_basis = "final_generated_paragraph_registry"
    elif source_registry:
        source_paragraphs = build_source_paragraphs_from_saved_registry(source_registry)
        source_reconstruction_basis = "saved_source_registry_preview"
    elif final_generated_registry:
        source_paragraphs = build_source_paragraphs_from_final_generated_registry(final_generated_registry)
        source_reconstruction_basis = "final_generated_paragraph_registry"
    else:
        resolved_source_docx_path = resolve_source_docx_from_report(
            report_path=report_path,
            report_payload=report_payload,
            target_docx_path=resolved_target_docx_path,
        )
        if resolved_source_docx_path is None or not resolved_source_docx_path.exists():
            raise FileNotFoundError("Replay requires saved source_registry or explicit/derived source_docx_path.")
        source_paragraphs, _ = extract_document_content_from_docx(BytesIO(resolved_source_docx_path.read_bytes()))
        source_reconstruction_basis = "source_docx_fallback"

    target_document = Document(str(resolved_target_docx_path))
    target_paragraphs = _collect_target_paragraphs(target_document)
    saved_source_registry = _coerce_mapping_sequence(saved_payload.get("source_registry")) if saved_payload is not None else []
    saved_source_count = len(saved_source_registry) or len(final_generated_registry)
    replayed_diagnostics = _build_output_formatting_diagnostics(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=final_generated_registry or None,
    )
    role_aware_summary = resolve_role_aware_formatting_unmapped_source_summary([replayed_diagnostics])
    replay_fidelity = "matched_saved_source_count"
    replay_fidelity_note = "Replayed source paragraph count matches the saved report source_registry count."
    if source_reconstruction_basis == "final_generated_paragraph_registry":
        replay_fidelity = "current_output_registry_replay"
        if saved_payload is None:
            replay_fidelity_note = (
                "Report did not include formatting_diagnostics; replay reconstructed current-code diagnostics "
                "from runtime.state.final_generated_paragraph_registry and the saved final DOCX."
            )
        else:
            replay_fidelity_note = (
                "Saved source_registry preview appears to remain in the source language; replay reconstructed "
                "current-code diagnostics from runtime.state.final_generated_paragraph_registry and the saved final DOCX."
            )
    elif saved_source_count and len(source_paragraphs) != saved_source_count:
        replay_fidelity = "source_count_mismatch_vs_saved_report"
        replay_fidelity_note = (
            "Current replay source paragraphs do not match the saved report source_registry count; "
            "treat replay output as current-code diagnostic evidence, not exact historical parity."
        )
    elif (
        source_reconstruction_basis == "saved_source_registry_preview"
        and _saved_registry_preview_looks_source_language(saved_source_registry, saved_target_registry)
    ):
        replay_fidelity = "count_parity_only_source_language_preview"
        replay_fidelity_note = (
            "Saved source_registry restores paragraph count/order, but its text preview appears to remain in the source language. "
            "This is enough for count parity, not for exact historical rebuild-key parity against translated output."
        )
    return {
        "report_path": str(report_path),
        "target_docx_path": str(resolved_target_docx_path),
        "source_docx_path": str(resolved_source_docx_path) if resolved_source_docx_path is not None else None,
        "source_reconstruction_basis": source_reconstruction_basis,
        "replay_scope": "restore_diagnostics_from_saved_final_docx",
        "replay_mode": "no_llm_current_mapping_code",
        "replay_fidelity": replay_fidelity,
        "replay_fidelity_note": replay_fidelity_note,
        "saved_source_count": saved_source_count,
        "replayed_source_count": len(source_paragraphs),
        "saved_diagnostic_stage": saved_payload.get("stage") if saved_payload is not None else None,
        "saved_mapped_count": saved_payload.get("mapped_count") if saved_payload is not None else None,
        "saved_unmapped_source_count": len(cast(Sequence[object], saved_payload.get("unmapped_source_ids") or [])) if saved_payload is not None else None,
        "saved_unmapped_target_count": len(cast(Sequence[object], saved_payload.get("unmapped_target_indexes") or [])) if saved_payload is not None else None,
        "replayed_diagnostics": replayed_diagnostics,
        "replayed_summary": {
            "mapped_count": replayed_diagnostics.get("mapped_count"),
            "unmapped_source_count": len(cast(Sequence[object], replayed_diagnostics.get("unmapped_source_ids") or [])),
            "unmapped_target_count": len(cast(Sequence[object], replayed_diagnostics.get("unmapped_target_indexes") or [])),
            "role_aware_summary": role_aware_summary,
        },
    }
