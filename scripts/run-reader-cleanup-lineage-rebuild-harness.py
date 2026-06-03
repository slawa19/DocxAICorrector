#!/usr/bin/env python3
"""Short PR-I1b lineage/rebuild harness for captured reader-cleanup artifacts.

This is intentionally not a full real-document validation run and does not call
any model. It reconstructs the generated paragraph registry from the captured
raw cleanup Markdown plus formatting diagnostics, then exercises the same
cleanup lineage and rebuild-only image placeholder stitches used by runtime.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence, cast


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

from docxaicorrector.pipeline import late_phases  # noqa: E402
from docxaicorrector.reader_cleanup_mvp import build_cleanup_blocks  # noqa: E402


DEFAULT_RUN_ID = "20260602T_pr_i1_formatting_lineage_sparse_alignment_proof_v4"
DEFAULT_RUN_DIR = PROJECT_ROOT / "tests/artifacts/real_document_pipeline/runs" / DEFAULT_RUN_ID
DEFAULT_VALIDATION_REPORT = DEFAULT_RUN_DIR / "lietaer_pdf_chapter_region_report.json"
DEFAULT_UI_STEM = PROJECT_ROOT / ".run/ui_results/20260602_162746_Rethinking-money-chapter-region-pages-10-11-and-156-217"
DEFAULT_RAW_MARKDOWN = DEFAULT_UI_STEM.with_suffix(".raw.result.md")
DEFAULT_CLEANED_MARKDOWN = DEFAULT_UI_STEM.with_suffix(".result.md")
DEFAULT_CLEANUP_REPORT = DEFAULT_UI_STEM.with_suffix(".reader_cleanup_report.json")
DEFAULT_OUTPUT = PROJECT_ROOT / ".run/diagnostics/pr_i1b_lineage_rebuild_harness.json"

_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"^\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]$")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _resolve_artifact_path(value: object, *, project_root: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.startswith("/mnt/") and len(text) > 7 and text[6] == "/":
        drive = text[5].upper()
        converted = Path(f"{drive}:/") / text[7:]
        if converted.exists():
            return converted
    path = Path(text)
    if path.is_absolute():
        return path
    return project_root / path


def _docx_image_placeholder_count(markdown_text: str) -> int:
    return sum(
        1
        for block in build_cleanup_blocks(markdown_text)
        if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(block.normalized_text)
    )


def _accepted_delete_block_ids(cleanup_report: Mapping[str, object]) -> list[str]:
    accepted_ids: list[str] = []
    accepted_delete_blocks = cleanup_report.get("accepted_delete_blocks") or []
    if isinstance(accepted_delete_blocks, Sequence) and not isinstance(
        accepted_delete_blocks, (str, bytes, bytearray)
    ):
        for raw_item in accepted_delete_blocks:
            if isinstance(raw_item, Mapping):
                block_id = str(raw_item.get("id") or "").strip()
                if block_id:
                    accepted_ids.append(block_id)
    accepted_cleanup_operations = cleanup_report.get("accepted_cleanup_operations") or []
    if isinstance(accepted_cleanup_operations, Sequence) and not isinstance(
        accepted_cleanup_operations, (str, bytes, bytearray)
    ):
        for raw_item in accepted_cleanup_operations:
            if not isinstance(raw_item, Mapping):
                continue
            if str(raw_item.get("operation") or "").strip() != "delete_block":
                continue
            block_id = str(raw_item.get("id") or "").strip()
            if block_id:
                accepted_ids.append(block_id)
    return sorted(set(accepted_ids))


def _formatting_paths_from_report(report: Mapping[str, object]) -> list[Path]:
    paths: list[Path] = []
    raw_paths = report.get("formatting_diagnostics_paths") or []
    if isinstance(raw_paths, Sequence) and not isinstance(raw_paths, (str, bytes, bytearray)):
        for raw_path in raw_paths:
            path = _resolve_artifact_path(raw_path, project_root=PROJECT_ROOT)
            if path is not None and path.exists():
                paths.append(path)
    return paths


def _select_formatting_diagnostics(
    *,
    paths: Sequence[Path],
    raw_non_image_block_count: int,
) -> tuple[Path | None, dict[str, Any] | None]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        try:
            loaded.append((path, _read_json(path)))
        except Exception:
            continue
    for path, payload in loaded:
        if int(payload.get("target_count") or 0) == raw_non_image_block_count:
            return path, payload
    return loaded[0] if loaded else (None, None)


def _paragraph_ids_by_target_index(formatting_payload: Mapping[str, object]) -> dict[int, list[str]]:
    result: dict[int, list[str]] = {}
    source_registry = formatting_payload.get("source_registry") or []
    if not isinstance(source_registry, Sequence) or isinstance(source_registry, (str, bytes, bytearray)):
        return result
    for entry in source_registry:
        if not isinstance(entry, Mapping):
            continue
        raw_target_index = entry.get("mapped_target_index")
        if not isinstance(raw_target_index, int):
            continue
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        if not paragraph_id:
            continue
        result.setdefault(raw_target_index, [])
        if paragraph_id not in result[raw_target_index]:
            result[raw_target_index].append(paragraph_id)
    return result


def _build_registry_from_raw_blocks_and_formatting(
    *,
    raw_markdown: str,
    formatting_payload: Mapping[str, object],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    paragraph_ids_by_target_index = _paragraph_ids_by_target_index(formatting_payload)
    registry: list[dict[str, object]] = []
    target_index = 0
    missing_target_id_count = 0
    for block in build_cleanup_blocks(raw_markdown):
        if _DOCX_IMAGE_PLACEHOLDER_PATTERN.fullmatch(block.normalized_text):
            continue
        paragraph_ids = paragraph_ids_by_target_index.get(target_index) or []
        if not paragraph_ids:
            missing_target_id_count += 1
            target_index += 1
            continue
        entry: dict[str, object] = {
            "paragraph_id": paragraph_ids[0],
            "text": block.text,
            "target_index": target_index,
            "block_index": block.index,
        }
        if len(paragraph_ids) > 1:
            entry["merged_paragraph_ids"] = paragraph_ids
        registry.append(entry)
        target_index += 1
    diagnostics = {
        "source": "raw_cleanup_blocks_plus_formatting_diagnostics",
        "formatting_target_count": int(formatting_payload.get("target_count") or 0),
        "mapped_target_index_count": len(paragraph_ids_by_target_index),
        "generated_registry_count": len(registry),
        "missing_target_id_count": missing_target_id_count,
    }
    return registry, diagnostics


def _evaluate_registry_candidate(
    *,
    name: str,
    generated_registry: Sequence[Mapping[str, object]],
    registry_diagnostics: Mapping[str, object],
    raw_markdown: str,
    cleaned_markdown: str,
    cleanup_report: Mapping[str, object],
) -> dict[str, object]:
    identity_metadata, identity_diagnostics = late_phases._build_reader_cleanup_block_identity_metadata(
        raw_markdown=raw_markdown,
        generated_paragraph_registry=generated_registry,
    )
    derived_registry, lineage_diagnostics = late_phases._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=generated_registry,
        cleanup_report=cleanup_report,
        raw_markdown=raw_markdown,
        cleanup_block_metadata_by_index=identity_metadata,
    )
    rebuilt_markdown = late_phases._build_docx_rebuild_markdown_after_reader_cleanup(
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        accepted_delete_block_ids=_accepted_delete_block_ids(cleanup_report),
        cleanup_block_metadata_by_index=identity_metadata,
        generated_paragraph_registry=derived_registry,
    )
    raw_image_placeholder_count = _docx_image_placeholder_count(raw_markdown)
    cleaned_image_placeholder_count = _docx_image_placeholder_count(cleaned_markdown)
    rebuilt_image_placeholder_count = _docx_image_placeholder_count(rebuilt_markdown)
    pass_checks = {
        "identity_available": identity_diagnostics.get("status") == "available",
        "identity_text_gap_zero": identity_diagnostics.get("text_gap_count") == 0,
        "lineage_derived": lineage_diagnostics.get("status") == "derived",
        "lineage_identity_mode": str(lineage_diagnostics.get("alignment_mode") or "").startswith("identity_"),
        "rebuild_restores_all_raw_placeholders": rebuilt_image_placeholder_count == raw_image_placeholder_count,
        "reader_display_has_no_placeholders": cleaned_image_placeholder_count == 0,
    }
    return {
        "name": name,
        "status": "passed" if all(pass_checks.values()) else "blocked",
        "registry_diagnostics": dict(registry_diagnostics),
        "identity_diagnostics": identity_diagnostics,
        "lineage_diagnostics": lineage_diagnostics,
        "artifact_shape": {
            "raw_image_placeholder_count": raw_image_placeholder_count,
            "cleaned_image_placeholder_count": cleaned_image_placeholder_count,
            "rebuilt_image_placeholder_count": rebuilt_image_placeholder_count,
        },
        "pass_checks": pass_checks,
    }


def run_harness(args: argparse.Namespace) -> dict[str, object]:
    if args.lineage_artifact:
        return run_lineage_artifact_harness(Path(args.lineage_artifact))

    validation_report_path = Path(args.validation_report)
    raw_markdown_path = Path(args.raw_markdown)
    cleaned_markdown_path = Path(args.cleaned_markdown)
    cleanup_report_path = Path(args.cleanup_report)

    raw_markdown = raw_markdown_path.read_text(encoding="utf-8")
    cleaned_markdown = cleaned_markdown_path.read_text(encoding="utf-8")
    cleanup_report = _read_json(cleanup_report_path)
    validation_report = _read_json(validation_report_path) if validation_report_path.exists() else {}

    raw_blocks = build_cleanup_blocks(raw_markdown)
    raw_image_placeholder_count = _docx_image_placeholder_count(raw_markdown)
    raw_non_image_block_count = len(raw_blocks) - raw_image_placeholder_count
    formatting_paths = [Path(value) for value in args.formatting_diagnostics]
    if not formatting_paths:
        formatting_paths = _formatting_paths_from_report(validation_report)
    formatting_path, formatting_payload = _select_formatting_diagnostics(
        paths=formatting_paths,
        raw_non_image_block_count=raw_non_image_block_count,
    )
    if formatting_payload is None:
        return {
            "status": "blocked",
            "reason": "missing_formatting_diagnostics",
            "raw_block_count": len(raw_blocks),
            "raw_image_placeholder_count": raw_image_placeholder_count,
            "raw_non_image_block_count": raw_non_image_block_count,
        }

    candidate_attempts: list[dict[str, object]] = []
    processed_registry = (
        cast(Mapping[str, object], cast(Mapping[str, object], validation_report.get("runtime") or {}).get("state") or {})
        .get("processed_paragraph_registry")
    )
    if isinstance(processed_registry, Sequence) and not isinstance(processed_registry, (str, bytes, bytearray)):
        processed_entries = [dict(entry) for entry in processed_registry if isinstance(entry, Mapping)]
        candidate_attempts.append(
            _evaluate_registry_candidate(
                name="runtime_state_processed_paragraph_registry",
                generated_registry=processed_entries,
                registry_diagnostics={
                    "source": "validation_report.runtime.state.processed_paragraph_registry",
                    "generated_registry_count": len(processed_entries),
                },
                raw_markdown=raw_markdown,
                cleaned_markdown=cleaned_markdown,
                cleanup_report=cleanup_report,
            )
        )

    reconstructed_registry, registry_diagnostics = _build_registry_from_raw_blocks_and_formatting(
        raw_markdown=raw_markdown,
        formatting_payload=formatting_payload,
    )
    candidate_attempts.append(
        _evaluate_registry_candidate(
            name="raw_cleanup_blocks_plus_formatting_diagnostics",
            generated_registry=reconstructed_registry,
            registry_diagnostics=registry_diagnostics,
            raw_markdown=raw_markdown,
            cleaned_markdown=cleaned_markdown,
            cleanup_report=cleanup_report,
        )
    )

    reader_cleanup_event_context = {}
    for event in validation_report.get("event_log") or []:
        if isinstance(event, Mapping) and event.get("event_id") == "reader_cleanup_applied":
            context = event.get("context")
            if isinstance(context, Mapping):
                reader_cleanup_event_context = dict(context)
            break

    cleaned_image_placeholder_count = _docx_image_placeholder_count(cleaned_markdown)
    passing_attempt = next((attempt for attempt in candidate_attempts if attempt.get("status") == "passed"), None)
    status = "passed" if passing_attempt is not None else "blocked"
    return {
        "status": status,
        "reason": None if passing_attempt is not None else "captured_artifacts_do_not_preserve_cleanup_generated_registry",
        "run_id": DEFAULT_RUN_ID,
        "artifact_inputs": {
            "validation_report": str(validation_report_path),
            "raw_markdown": str(raw_markdown_path),
            "cleaned_markdown": str(cleaned_markdown_path),
            "cleanup_report": str(cleanup_report_path),
            "formatting_diagnostics": str(formatting_path) if formatting_path is not None else None,
        },
        "artifact_shape": {
            "raw_block_count": len(raw_blocks),
            "raw_image_placeholder_count": raw_image_placeholder_count,
            "raw_non_image_block_count": raw_non_image_block_count,
            "cleaned_image_placeholder_count": cleaned_image_placeholder_count,
        },
        "selected_attempt": passing_attempt.get("name") if passing_attempt is not None else None,
        "candidate_attempts": candidate_attempts,
        "previous_reader_cleanup_event": {
            key: reader_cleanup_event_context.get(key)
            for key in (
                "formatting_lineage_status",
                "formatting_lineage_alignment_mode",
                "formatting_lineage_alignment_gap_count",
                "formatting_lineage_raw_cleanup_block_count",
                "formatting_lineage_generated_registry_count",
                "formatting_lineage_derived_registry_count",
                "formatting_lineage_applied_operation_count",
            )
        },
        "evidence_caveat": (
            "This is a short PR-I1b stitch harness, not a full validation run. If status is blocked, "
            "the old proof artifacts can invoke the helpers but do not preserve the cleanup-time "
            "generated registry required for meaningful real-artifact id-first lineage proof."
        ),
    }


def run_lineage_artifact_harness(lineage_artifact_path: Path) -> dict[str, object]:
    payload = _read_json(lineage_artifact_path)
    raw_markdown = str(payload.get("raw_markdown") or "")
    cleaned_markdown = str(payload.get("cleaned_markdown") or "")
    cleanup_report = cast(Mapping[str, object], payload.get("cleanup_report") or {})
    active_formatting_registry = [
        dict(entry)
        for entry in cast(Sequence[object], payload.get("active_formatting_registry") or [])
        if isinstance(entry, Mapping)
    ]
    attempt = _evaluate_registry_candidate(
        name="reader_cleanup_lineage_artifact_active_formatting_registry",
        generated_registry=active_formatting_registry,
        registry_diagnostics={
            "source": "reader_cleanup_lineage_artifact.active_formatting_registry",
            "generated_registry_count": len(active_formatting_registry),
            "artifact_path": str(lineage_artifact_path),
        },
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        cleanup_report=cleanup_report,
    )
    return {
        "status": "passed" if attempt.get("status") == "passed" else "blocked",
        "reason": None if attempt.get("status") == "passed" else "lineage_artifact_registry_did_not_align",
        "artifact_inputs": {"lineage_artifact": str(lineage_artifact_path)},
        "candidate_attempts": [attempt],
        "persisted_cleanup_identity_diagnostics": payload.get("cleanup_identity_diagnostics"),
        "persisted_cleanup_formatting_lineage": payload.get("cleanup_formatting_lineage"),
        "evidence_caveat": "Harness used the cleanup-time lineage artifact written by runtime, without LLM/full validation.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-artifact", default="")
    parser.add_argument("--validation-report", default=str(DEFAULT_VALIDATION_REPORT))
    parser.add_argument("--raw-markdown", default=str(DEFAULT_RAW_MARKDOWN))
    parser.add_argument("--cleaned-markdown", default=str(DEFAULT_CLEANED_MARKDOWN))
    parser.add_argument("--cleanup-report", default=str(DEFAULT_CLEANUP_REPORT))
    parser.add_argument("--formatting-diagnostics", action="append", default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    payload = run_harness(args)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
