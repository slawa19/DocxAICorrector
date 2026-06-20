from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from docxaicorrector.core.config import get_client_for_model_selector, load_app_config, resolve_model_selector
from docxaicorrector.generation._generation import generate_markdown_block
from docxaicorrector.pdf_import.logical_import import build_paragraph_units_from_text_spans
from docxaicorrector.pdf_import.text_layer_quality import extract_pdf_text_spans_with_pdfminer
from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupConfig,
    build_cleanup_blocks,
    build_reader_cleanup_reannotation_system_prompt,
    build_reader_cleanup_schema_repair_system_prompt,
    build_reader_cleanup_system_prompt,
    resolve_reader_cleanup_config,
    run_reader_cleanup,
    run_reader_cleanup_reannotation,
)

DEFAULT_INPUT_MARKDOWN = (
    PROJECT_ROOT
    / "tests/artifacts/real_document_pipeline/runs/20260618T195903Z_6156_bernardlietaer-moneyandsustainabilitypdffromepub-160516072426/Money_Sustainability_pdf_full_heldout.md"
)
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / ".run" / "reader_cleanup_structural_matrix"
DEFAULT_VALIDATION_REPORT = (
    PROJECT_ROOT
    / "tests/artifacts/real_document_pipeline/runs/20260618T195903Z_6156_bernardlietaer-moneyandsustainabilitypdffromepub-160516072426/money_sustainability_pdf_full_heldout_report.json"
)
DEFAULT_SOURCE_PDF = PROJECT_ROOT / "tests/sources/book/bernardlietaer-moneyandsustainabilitypdffromepub-160516072426.pdf"
MODELS = {
    "haiku-4.5": "openrouter:anthropic/claude-haiku-4.5",
    "sonnet-4-6": "openrouter:anthropic/claude-sonnet-4-6",
    "opus": "openrouter:anthropic/claude-opus-4.1",
}
GROUND_TRUTH_TARGETS = {
    "fused_heading_wealth_concentration": "Экономические последствия концентрации богатства",
    "fused_heading_sustainability": "Последствия для устойчивости",
    "broken_five_processes_list": "пять пагубных процессов",
}
GROUND_TRUTH_FOOTNOTE_MARKERS = ("25", "43", "44")


@dataclass(frozen=True)
class MatrixConfig:
    mode: str
    model_label: str
    model_selector: str
    layout_mode: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted reader-cleanup structural replay matrix.")
    parser.add_argument("--input-markdown", default=str(DEFAULT_INPUT_MARKDOWN))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--modes", nargs="+", default=["edit_ops", "reannotation"])
    parser.add_argument(
        "--layout",
        nargs="+",
        default=["none", "pseudo"],
        choices=["without", "with", "none", "pseudo", "real", "both"],
        help="'without' aliases 'none'; 'with' aliases legacy pseudo markdown-derived signals.",
    )
    parser.add_argument("--validation-report", default=str(DEFAULT_VALIDATION_REPORT))
    parser.add_argument("--source-pdf", default=str(DEFAULT_SOURCE_PDF))
    parser.add_argument("--max-configs", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "run"


def _extract_window_markdown(
    markdown: str,
    *,
    target_index_metadata: Mapping[int, Mapping[str, object]] | None = None,
) -> tuple[str, dict[int, dict[str, object]], dict[str, object]]:
    blocks = build_cleanup_blocks(markdown)
    selected_indexes: set[int] = set()
    for index, block in enumerate(blocks):
        text = block.normalized_text
        if (
            any(target in text for target in GROUND_TRUTH_TARGETS.values())
            or any(marker in text for marker in GROUND_TRUTH_FOOTNOTE_MARKERS)
            or "[[DOCX_IMAGE_" in text
        ):
            selected_indexes.update(range(max(0, index - 2), min(len(blocks), index + 3)))
    selected = [blocks[index] for index in sorted(selected_indexes)]
    metadata: dict[int, dict[str, object]] = {}
    real_signal_count = 0
    pseudo_signal_count = 0
    for new_index, block in enumerate(selected):
        source_index = block.index
        real_entry = dict(target_index_metadata.get(source_index) or {}) if target_index_metadata is not None else {}
        real_signals = dict(cast(Mapping[str, object], real_entry.get("layout_signals") or {}))
        if real_signals:
            real_signal_count += 1
        pseudo_signals = _pseudo_layout_signals_for_block(block=block)
        if pseudo_signals:
            pseudo_signal_count += 1
        layout_signals = {
            "source_block_index": source_index,
            **real_signals,
            "pseudo": pseudo_signals,
        }
        metadata[new_index] = {
            "paragraph_id": str(real_entry.get("paragraph_id") or f"replay_b{source_index:06d}"),
            "layout_signals": layout_signals,
        }
    return "\n\n".join(block.text for block in selected), metadata, {
        "window_block_count": len(selected),
        "window_blocks_with_real_layout_signal_count": real_signal_count,
        "window_blocks_with_pseudo_layout_signal_count": pseudo_signal_count,
    }


def _pseudo_layout_signals_for_block(*, block: object) -> dict[str, object]:
    text = str(getattr(block, "normalized_text", "") or "")
    return {
        "standalone_short_line": "\n" not in text and len(text) <= 90,
        "looks_like_superscript_marker": bool(re.fullmatch(r"\[?\d{1,3}\]?|\(\d{1,3}\)", text)),
        "is_docx_image_anchor": "[[DOCX_IMAGE_" in text,
    }


def _without_layout(metadata: Mapping[int, Mapping[str, object]]) -> dict[int, dict[str, object]]:
    stripped: dict[int, dict[str, object]] = {}
    for index, entry in metadata.items():
        paragraph_id = entry.get("paragraph_id")
        if isinstance(paragraph_id, str) and paragraph_id.strip():
            stripped[int(index)] = {"paragraph_id": paragraph_id}
    return stripped


def _metadata_for_layout_mode(metadata: Mapping[int, Mapping[str, object]], *, layout_mode: str) -> dict[int, dict[str, object]]:
    normalized_mode = _normalize_layout_mode(layout_mode)
    if normalized_mode == "none":
        return _without_layout(metadata)
    effective: dict[int, dict[str, object]] = {}
    for index, entry in metadata.items():
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        raw_signals = dict(cast(Mapping[str, object], entry.get("layout_signals") or {}))
        pseudo = dict(cast(Mapping[str, object], raw_signals.pop("pseudo", {}) or {}))
        source_block_index = raw_signals.get("source_block_index")
        if normalized_mode == "pseudo":
            layout_signals = {"source_block_index": source_block_index, **pseudo}
        elif normalized_mode == "real":
            layout_signals = {key: value for key, value in raw_signals.items() if key != "source_block_index"}
            if source_block_index is not None:
                layout_signals["source_block_index"] = source_block_index
        elif normalized_mode == "both":
            layout_signals = {**raw_signals, **{f"pseudo_{key}": value for key, value in pseudo.items()}}
            if source_block_index is not None:
                layout_signals["source_block_index"] = source_block_index
        else:
            layout_signals = {}
        effective[int(index)] = {"paragraph_id": paragraph_id or f"replay_b{index:06d}"}
        if layout_signals:
            effective[int(index)]["layout_signals"] = layout_signals
    return effective


def _normalize_layout_mode(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "without":
        return "none"
    if normalized == "with":
        return "pseudo"
    if normalized in {"none", "pseudo", "real", "both"}:
        return normalized
    raise ValueError(f"unsupported layout mode: {value}")


def _make_provider(*, client: object, model_id: str, system_prompt: str, max_retries: int):
    def provider(request_payload: Mapping[str, object], chunk_index: int, chunk_count: int) -> str:
        target_text = json.dumps(request_payload, ensure_ascii=False, indent=2)
        return generate_markdown_block(
            client=cast(Any, client),
            model=model_id,
            system_prompt=system_prompt,
            target_text=target_text,
            context_before=str(request_payload.get("context_before_preview") or ""),
            context_after=str(request_payload.get("context_after_preview") or ""),
            max_retries=max(1, max_retries),
            expected_paragraph_ids=None,
            marker_mode=False,
        )

    return provider


def _build_real_layout_metadata_by_target_index(
    *,
    validation_report_path: Path,
    source_pdf_path: Path,
) -> tuple[dict[int, dict[str, object]], dict[str, object]]:
    if not validation_report_path.exists():
        return {}, {"status": "blocked", "reason": "validation_report_missing", "path": str(validation_report_path)}
    if not source_pdf_path.exists():
        return {}, {"status": "blocked", "reason": "source_pdf_missing", "path": str(source_pdf_path)}
    validation_report = json.loads(validation_report_path.read_text(encoding="utf-8"))
    source_registry = _load_source_registry(validation_report)
    if not source_registry:
        return {}, {"status": "blocked", "reason": "source_registry_missing", "path": str(validation_report_path)}

    spans = extract_pdf_text_spans_with_pdfminer(source_pdf_path)
    import_result = build_paragraph_units_from_text_spans(spans)
    pdf_paragraphs = import_result.paragraphs
    spans_by_origin = {_pdf_span_origin_index(span): span for span in spans}
    body_font_size = _body_font_size_for_pdf_paragraphs(pdf_paragraphs)
    body_left_x0 = _body_left_x0_for_pdf_paragraphs(pdf_paragraphs, spans_by_origin=spans_by_origin)
    pdf_matches, match_stats = _match_source_registry_to_pdf_paragraphs(
        source_registry=source_registry,
        pdf_paragraphs=pdf_paragraphs,
    )

    metadata_by_target_index: dict[int, dict[str, object]] = {}
    for entry in source_registry:
        target_index = entry.get("mapped_target_index")
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        if not isinstance(target_index, int) or target_index < 0 or not paragraph_id:
            continue
        pdf_paragraph = pdf_matches.get(paragraph_id)
        if pdf_paragraph is None:
            metadata_by_target_index[target_index] = {"paragraph_id": paragraph_id}
            continue
        layout_signals = _real_layout_signals_for_pdf_paragraph(
            pdf_paragraph,
            spans_by_origin=spans_by_origin,
            body_font_size=body_font_size,
            body_left_x0=body_left_x0,
        )
        metadata_by_target_index[target_index] = {
            "paragraph_id": paragraph_id,
            "layout_signals": layout_signals,
        }
    return metadata_by_target_index, {
        "status": "ok",
        "source": "pdf_text_layer_import_plus_formatting_source_registry_text_containment",
        "source_pdf_path": str(source_pdf_path),
        "validation_report_path": str(validation_report_path),
        "source_registry_count": len(source_registry),
        "pdf_import_paragraph_count": len(pdf_paragraphs),
        "pdf_span_count": len(spans),
        "body_font_size_pt": body_font_size,
        "body_left_x0": body_left_x0,
        "target_metadata_count": len(metadata_by_target_index),
        **match_stats,
    }


def _load_source_registry(validation_report: Mapping[str, object]) -> list[Mapping[str, object]]:
    diagnostics = validation_report.get("formatting_diagnostics")
    if not isinstance(diagnostics, list) or not diagnostics:
        return []
    first = diagnostics[0]
    if not isinstance(first, Mapping):
        return []
    source_registry = first.get("source_registry")
    if not isinstance(source_registry, list):
        return []
    return [entry for entry in source_registry if isinstance(entry, Mapping)]


def _match_source_registry_to_pdf_paragraphs(
    *,
    source_registry: Sequence[Mapping[str, object]],
    pdf_paragraphs: Sequence[object],
) -> tuple[dict[str, object], dict[str, object]]:
    matches: dict[str, object] = {}
    ambiguous_count = 0
    unmatched_count = 0
    short_skipped_count = 0
    image_skipped_count = 0
    examples: list[dict[str, object]] = []
    pdf_fingerprints = [(_registry_text_fingerprint(getattr(paragraph, "text", "")), paragraph) for paragraph in pdf_paragraphs]
    for entry in source_registry:
        paragraph_id = str(entry.get("paragraph_id") or "").strip()
        if not paragraph_id:
            continue
        if str(entry.get("role") or "").strip().lower() == "image":
            image_skipped_count += 1
            continue
        source_fp = _registry_text_fingerprint(entry.get("text_preview"))
        if len(source_fp) < 24:
            short_skipped_count += 1
            continue
        candidates = [
            paragraph
            for pdf_fp, paragraph in pdf_fingerprints
            if len(pdf_fp) >= 24 and (pdf_fp.startswith(source_fp[:120]) or source_fp[:120] in pdf_fp or pdf_fp[:120] in source_fp)
        ]
        if len(candidates) == 1:
            matches[paragraph_id] = candidates[0]
            continue
        if candidates:
            ambiguous_count += 1
            if len(examples) < 5:
                examples.append(
                    {
                        "kind": "ambiguous",
                        "paragraph_id": paragraph_id,
                        "text_preview": str(entry.get("text_preview") or "")[:120],
                        "candidate_count": len(candidates),
                    }
                )
            continue
        unmatched_count += 1
        if len(examples) < 5:
            examples.append(
                {
                    "kind": "unmatched",
                    "paragraph_id": paragraph_id,
                    "text_preview": str(entry.get("text_preview") or "")[:120],
                }
            )
    non_image_count = sum(1 for entry in source_registry if str(entry.get("role") or "").strip().lower() != "image")
    return matches, {
        "source_non_image_count": non_image_count,
        "real_layout_matched_source_count": len(matches),
        "real_layout_ambiguous_source_count": ambiguous_count,
        "real_layout_short_skipped_source_count": short_skipped_count,
        "real_layout_unmatched_source_count": unmatched_count,
        "real_layout_image_skipped_source_count": image_skipped_count,
        "real_layout_match_examples": examples,
    }


def _registry_text_fingerprint(value: object) -> str:
    return re.sub(r"[^0-9a-zа-яё]+", "", str(value or "").casefold())


def _body_font_size_for_pdf_paragraphs(paragraphs: Sequence[object]) -> float | None:
    rounded_sizes = [
        round(float(size), 1)
        for paragraph in paragraphs
        for size in [getattr(paragraph, "font_size_pt", None)]
        if isinstance(size, (int, float)) and size > 0 and str(getattr(paragraph, "role", "body")) == "body"
    ]
    if not rounded_sizes:
        return None
    return float(Counter(rounded_sizes).most_common(1)[0][0])


def _body_left_x0_for_pdf_paragraphs(
    paragraphs: Sequence[object],
    *,
    spans_by_origin: Mapping[int, object],
) -> float | None:
    values: list[float] = []
    for paragraph in paragraphs:
        if str(getattr(paragraph, "role", "body")) != "body":
            continue
        origin_indexes = list(getattr(paragraph, "origin_raw_indexes", []) or [])
        if not origin_indexes:
            continue
        span = spans_by_origin.get(int(origin_indexes[0]))
        x0 = getattr(span, "x0", None)
        if isinstance(x0, (int, float)):
            values.append(float(x0))
    return float(median(values)) if values else None


def _real_layout_signals_for_pdf_paragraph(
    paragraph: object,
    *,
    spans_by_origin: Mapping[int, object],
    body_font_size: float | None,
    body_left_x0: float | None,
) -> dict[str, object]:
    origin_indexes = [int(value) for value in (getattr(paragraph, "origin_raw_indexes", []) or [])]
    spans = [spans_by_origin[index] for index in origin_indexes if index in spans_by_origin]
    font_size = getattr(paragraph, "font_size_pt", None)
    first_span = spans[0] if spans else None
    x0 = getattr(first_span, "x0", None)
    top = getattr(first_span, "top", None)
    bottom = getattr(first_span, "bottom", None)
    font_ratio = None
    font_delta = None
    if isinstance(font_size, (int, float)) and isinstance(body_font_size, (int, float)) and body_font_size > 0:
        font_ratio = float(font_size) / float(body_font_size)
        font_delta = float(font_size) - float(body_font_size)
    left_delta = None
    if isinstance(x0, (int, float)) and isinstance(body_left_x0, (int, float)):
        left_delta = float(x0) - float(body_left_x0)
    span_tops = [float(getattr(span, "top")) for span in spans if isinstance(getattr(span, "top", None), (int, float))]
    span_bottoms = [float(getattr(span, "bottom")) for span in spans if isinstance(getattr(span, "bottom", None), (int, float))]
    return {
        "real_layout_source": "pdf_text_layer",
        "pdf_role": str(getattr(paragraph, "role", "") or ""),
        "pdf_structural_role": str(getattr(paragraph, "structural_role", "") or ""),
        "pdf_heading_level": getattr(paragraph, "heading_level", None),
        "font_size_pt": float(font_size) if isinstance(font_size, (int, float)) else None,
        "body_font_size_pt": body_font_size,
        "font_size_ratio_to_body": round(font_ratio, 4) if isinstance(font_ratio, float) else None,
        "font_size_delta_from_body": round(font_delta, 4) if isinstance(font_delta, float) else None,
        "is_bold": bool(getattr(paragraph, "is_bold", False)),
        "is_italic": bool(getattr(paragraph, "is_italic", False)),
        "left_x0": float(x0) if isinstance(x0, (int, float)) else None,
        "body_left_x0": body_left_x0,
        "left_indent_delta": round(left_delta, 3) if isinstance(left_delta, float) else None,
        "top": float(top) if isinstance(top, (int, float)) else None,
        "bottom": float(bottom) if isinstance(bottom, (int, float)) else None,
        "span_count": len(spans),
        "line_top_min": min(span_tops) if span_tops else None,
        "line_bottom_max": max(span_bottoms) if span_bottoms else None,
        "origin_raw_indexes": origin_indexes[:12],
    }


def _pdf_span_origin_index(span: object) -> int:
    return max(0, (int(getattr(span, "page_number", 1)) - 1) * 10000 + int(round(float(getattr(span, "top", 0.0)))))


def _score(raw_markdown: str, cleaned_markdown: str, report: Mapping[str, object], elapsed_seconds: float) -> dict[str, object]:
    accepted = [dict(entry) for entry in cast(Sequence[Mapping[str, object]], report.get("accepted_cleanup_operations") or [])]
    ignored = [dict(entry) for entry in cast(Sequence[Mapping[str, object]], report.get("ignored_cleanup_operations") or [])]
    caught: dict[str, bool] = {}
    for defect_id, target in GROUND_TRUTH_TARGETS.items():
        if defect_id.startswith("fused_heading"):
            caught[defect_id] = _heading_target_is_own_heading_line(cleaned_markdown=cleaned_markdown, target=target)
        elif defect_id == "broken_five_processes_list":
            caught[defect_id] = _broken_list_is_reassembled_locally(cleaned_markdown=cleaned_markdown, target=target)
    caught["footnote_markers_detached"] = _footnote_markers_are_detached(cleaned_markdown=cleaned_markdown)
    image_reconciliation = cast(Mapping[str, object], report.get("image_reconciliation") or {})
    containment_violation_count = _containment_violation_count(raw_markdown=raw_markdown, cleaned_markdown=cleaned_markdown, ignored=ignored)
    return {
        "caught": caught,
        "caught_count": sum(1 for value in caught.values() if value),
        "false_positive_count": containment_violation_count,
        "containment_violation_count": containment_violation_count,
        "accepted_operation_count": len(accepted),
        "ignored_operation_count": len(ignored),
        "images_touched": bool(image_reconciliation.get("touched")),
        "image_before_count": image_reconciliation.get("before_image_id_count"),
        "image_after_count": image_reconciliation.get("after_image_id_count"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "reported_cost": cast(Mapping[str, object], report.get("model_resolution") or {}).get("cost"),
    }


def _heading_target_is_own_heading_line(*, cleaned_markdown: str, target: str) -> bool:
    pattern = re.compile(rf"(?m)^\s*#{{1,6}}\s+{re.escape(target)}\s*$")
    return pattern.search(cleaned_markdown) is not None


def _broken_list_is_reassembled_locally(*, cleaned_markdown: str, target: str) -> bool:
    target_index = cleaned_markdown.find(target)
    if target_index < 0:
        return False
    window = cleaned_markdown[max(0, target_index - 1200) : target_index + 2200]
    list_lines = re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+\S", window)
    if len(list_lines) < 5:
        return False
    marker_positions = [match.start() for match in re.finditer(r"(?m)^\s*(?:[-*]|\d+\.)\s+\S", window)]
    return bool(marker_positions and max(marker_positions[:5]) - min(marker_positions[:5]) <= 1800)


def _footnote_markers_are_detached(*, cleaned_markdown: str) -> bool:
    return all(_footnote_marker_is_detached(cleaned_markdown=cleaned_markdown, marker=marker) for marker in GROUND_TRUTH_FOOTNOTE_MARKERS)


def _footnote_marker_is_detached(*, cleaned_markdown: str, marker: str) -> bool:
    own_line = re.compile(rf"(?m)^\s*(?:\[\^?{re.escape(marker)}\]|\({re.escape(marker)}\)|{re.escape(marker)})\s*$")
    if own_line.search(cleaned_markdown):
        return True
    attached_tail = re.compile(rf"[\wА-Яа-яЁё][\.\?!»”’'\)]?\s*{re.escape(marker)}(?=\s|$)")
    return attached_tail.search(cleaned_markdown) is None


def _containment_violation_count(*, raw_markdown: str, cleaned_markdown: str, ignored: Sequence[Mapping[str, object]]) -> int:
    _ = raw_markdown, cleaned_markdown
    return sum(1 for entry in ignored if entry.get("ignored_reason") == "visible_content_containment_failed")


def _visible_content_fingerprint(text: str) -> str:
    lines: list[str] = []
    for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = line.strip()
        stripped = re.sub(r"^#{1,6}\s+", "", stripped)
        stripped = re.sub(r"^(?:[-*]|\d+\.)\s+", "", stripped)
        if stripped:
            lines.append(stripped)
    return re.sub(r"\s+", "", " ".join(lines)).casefold()


def _run_config(
    *,
    config: MatrixConfig,
    raw_markdown: str,
    metadata: Mapping[int, Mapping[str, object]],
    output_dir: Path,
    max_retries: int,
) -> dict[str, object]:
    app_config = dict(cast(Mapping[str, object], load_app_config()))
    app_config.update(
        {
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "reader_cleanup_model": config.model_selector,
            "reader_cleanup_chunk_size": 50000,
            "reader_cleanup_overlap_blocks_before": 2,
            "reader_cleanup_overlap_blocks_after": 2,
            "reader_cleanup_global_plan_enabled": False,
            "reader_cleanup_keep_toc": False,
        }
    )
    cleanup_config = resolve_reader_cleanup_config(app_config=app_config, fallback_model=config.model_selector)
    selector = resolve_model_selector(config.model_selector, "responses_text", config_like=app_config, source_name="reader-cleanup structural matrix")
    client = get_client_for_model_selector(config.model_selector, "responses_text", config_like=app_config)
    effective_metadata = _metadata_for_layout_mode(metadata, layout_mode=config.layout_mode)
    started = time.perf_counter()
    if config.mode == "edit_ops":
        result = run_reader_cleanup(
            markdown_text=raw_markdown,
            config=cleanup_config,
            operation_provider=_make_provider(
                client=client,
                model_id=selector.model_id,
                system_prompt=build_reader_cleanup_system_prompt(),
                max_retries=max_retries,
            ),
            repair_provider=_make_provider(
                client=client,
                model_id=selector.model_id,
                system_prompt=build_reader_cleanup_schema_repair_system_prompt(),
                max_retries=max_retries,
            ),
            block_metadata_by_index=effective_metadata,
            model_resolution={"requested_selector": config.model_selector, "model_id": selector.model_id},
        )
    else:
        result = run_reader_cleanup_reannotation(
            markdown_text=raw_markdown,
            config=cleanup_config,
            annotation_provider=_make_provider(
                client=client,
                model_id=selector.model_id,
                system_prompt=build_reader_cleanup_reannotation_system_prompt(),
                max_retries=max_retries,
            ),
            block_metadata_by_index=effective_metadata,
            model_resolution={"requested_selector": config.model_selector, "model_id": selector.model_id},
        )
    elapsed = time.perf_counter() - started
    base = f"{config.mode}_{config.model_label}_{_slug(_normalize_layout_mode(config.layout_mode))}"
    cleaned_path = output_dir / f"{base}.cleaned.md"
    report_path = output_dir / f"{base}.report.json"
    cleaned_path.write_text(result.cleaned_markdown, encoding="utf-8")
    report_path.write_text(json.dumps(result.report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    score = _score(raw_markdown, result.cleaned_markdown, result.report_payload, elapsed)
    return {
        "config": {
            "mode": config.mode,
            "model": config.model_label,
            "model_selector": config.model_selector,
            "layout_mode": _normalize_layout_mode(config.layout_mode),
            "layout_signals": _normalize_layout_mode(config.layout_mode) != "none",
        },
        "score": score,
        "artifact_paths": {"cleaned_markdown": str(cleaned_path), "report": str(report_path)},
    }


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input_markdown)
    if not input_path.exists():
        raise SystemExit(f"Input markdown not found: {input_path}")
    raw_full = input_path.read_text(encoding="utf-8")
    real_metadata_by_target_index, layout_signal_report = _build_real_layout_metadata_by_target_index(
        validation_report_path=Path(args.validation_report),
        source_pdf_path=Path(args.source_pdf),
    )
    raw_window, metadata, window_metadata_report = _extract_window_markdown(
        raw_full,
        target_index_metadata=real_metadata_by_target_index,
    )
    output_dir = Path(args.output_root) / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input.window.md").write_text(raw_window, encoding="utf-8")
    configs = [
        MatrixConfig(
            mode=mode,
            model_label=model_label,
            model_selector=MODELS[model_label],
            layout_mode=_normalize_layout_mode(layout),
        )
        for mode in args.modes
        for model_label in args.models
        for layout in args.layout
    ]
    if args.max_configs > 0:
        configs = configs[: args.max_configs]
    results = []
    for config in configs:
        print(f"[matrix] {config.mode} {config.model_label} layout={config.layout_mode}", flush=True)
        results.append(
            _run_config(
                config=config,
                raw_markdown=raw_window,
                metadata=metadata,
                output_dir=output_dir,
                max_retries=args.max_retries,
            )
        )
    summary = {
        "input_markdown": str(input_path),
        "input_window_path": str(output_dir / "input.window.md"),
        "window_block_count": len(build_cleanup_blocks(raw_window)),
        "layout_signal_report": {
            **layout_signal_report,
            **window_metadata_report,
        },
        "results": results,
    }
    summary_path = output_dir / "matrix_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[matrix] summary={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
