from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from docxaicorrector.core.config import get_client_for_model_selector, load_app_config, resolve_model_selector
from docxaicorrector.generation._generation import generate_markdown_block
from docxaicorrector.reader_cleanup_mvp import (
    ReaderCleanupConfig,
    build_cleanup_blocks,
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
MODELS = {
    "haiku-4.5": "openrouter:anthropic/claude-haiku-4.5",
    "sonnet-4-6": "openrouter:anthropic/claude-sonnet-4-6",
    "opus": "openrouter:anthropic/claude-opus-4.1",
}
GROUND_TRUTH_TARGETS = {
    "fused_heading_wealth_concentration": "Экономические последствия концентрации богатства",
    "fused_heading_sustainability": "Последствия для устойчивости",
    "broken_five_processes_list": "пять пагубных процессов",
    "footnote_marker_25": "25",
    "footnote_marker_43": "43",
    "footnote_marker_44": "44",
}


@dataclass(frozen=True)
class MatrixConfig:
    mode: str
    model_label: str
    model_selector: str
    layout_signals: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted reader-cleanup structural replay matrix.")
    parser.add_argument("--input-markdown", default=str(DEFAULT_INPUT_MARKDOWN))
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--modes", nargs="+", default=["edit_ops", "reannotation"])
    parser.add_argument("--layout", nargs="+", default=["without", "with"], choices=["without", "with"])
    parser.add_argument("--max-configs", type=int, default=0)
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args()


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "run"


def _extract_window_markdown(markdown: str) -> tuple[str, dict[int, dict[str, object]]]:
    blocks = build_cleanup_blocks(markdown)
    selected_indexes: set[int] = set()
    for index, block in enumerate(blocks):
        text = block.normalized_text
        if any(target in text for target in GROUND_TRUTH_TARGETS.values()) or "[[DOCX_IMAGE_" in text:
            selected_indexes.update(range(max(0, index - 2), min(len(blocks), index + 3)))
    selected = [blocks[index] for index in sorted(selected_indexes)]
    metadata: dict[int, dict[str, object]] = {}
    for new_index, block in enumerate(selected):
        metadata[new_index] = {
            "paragraph_id": f"replay_b{block.index:06d}",
            "layout_signals": {
                "source_block_index": block.index,
                "standalone_short_line": "\n" not in block.normalized_text and len(block.normalized_text) <= 90,
                "looks_like_superscript_marker": bool(re.fullmatch(r"\[?\d{1,3}\]?|\(\d{1,3}\)", block.normalized_text)),
                "is_docx_image_anchor": "[[DOCX_IMAGE_" in block.normalized_text,
            },
        }
    return "\n\n".join(block.text for block in selected), metadata


def _without_layout(metadata: Mapping[int, Mapping[str, object]]) -> dict[int, dict[str, object]]:
    stripped: dict[int, dict[str, object]] = {}
    for index, entry in metadata.items():
        paragraph_id = entry.get("paragraph_id")
        if isinstance(paragraph_id, str) and paragraph_id.strip():
            stripped[int(index)] = {"paragraph_id": paragraph_id}
    return stripped


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


def _reannotation_system_prompt() -> str:
    return (
        "You re-annotate translated book Markdown structure. Return JSON only with annotations and warnings.\n"
        "Do not translate, rewrite, summarize, delete, or reorder visible content.\n"
        "Allowed roles: heading, body, list_item, caption, footnote.\n"
        "If one block starts with a real heading followed by body prose, return heading_text and body_text as exact substrings.\n"
        "If a standalone short digit is an inline footnote marker glued to prose nearby, mark it footnote only when layout/context supports it.\n"
        "Preserve [[DOCX_IMAGE_*]] anchors. If uncertain, return no annotation and a warning.\n"
        'Example: {"annotations":[{"id":"b_000001","text_hash":"abc","role":"heading","confidence":"high","reason":"heading_body_boundary","heading_text":"Title","body_text":"Body text"}],"warnings":[]}'
    )


def _score(raw_markdown: str, cleaned_markdown: str, report: Mapping[str, object], elapsed_seconds: float) -> dict[str, object]:
    accepted = [dict(entry) for entry in cast(Sequence[Mapping[str, object]], report.get("accepted_cleanup_operations") or [])]
    ignored = [dict(entry) for entry in cast(Sequence[Mapping[str, object]], report.get("ignored_cleanup_operations") or [])]
    caught: dict[str, bool] = {}
    for defect_id, target in GROUND_TRUTH_TARGETS.items():
        if defect_id.startswith("fused_heading"):
            caught[defect_id] = f"## {target}" in cleaned_markdown or any(target in str(op.get("expected_after_preview") or "") for op in accepted)
        elif defect_id == "broken_five_processes_list":
            caught[defect_id] = len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+", cleaned_markdown)) >= 5 and target in cleaned_markdown
        else:
            marker = defect_id.rsplit("_", 1)[-1]
            caught[defect_id] = any(
                marker in str(op.get("noise_substring") or op.get("expected_after_preview") or "")
                for op in accepted
            )
    image_reconciliation = cast(Mapping[str, object], report.get("image_reconciliation") or {})
    false_positive_count = sum(
        1
        for op in accepted
        if not any(str(target) in str(op.get("raw_text_preview") or "") or str(target) in str(op.get("expected_after_preview") or "") for target in GROUND_TRUTH_TARGETS.values())
        and "[[DOCX_IMAGE_" not in str(op.get("raw_text_preview") or "")
    )
    return {
        "caught": caught,
        "caught_count": sum(1 for value in caught.values() if value),
        "false_positive_count": false_positive_count,
        "accepted_operation_count": len(accepted),
        "ignored_operation_count": len(ignored),
        "images_touched": bool(image_reconciliation.get("touched")),
        "image_before_count": image_reconciliation.get("before_image_id_count"),
        "image_after_count": image_reconciliation.get("after_image_id_count"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "reported_cost": cast(Mapping[str, object], report.get("model_resolution") or {}).get("cost"),
    }


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
    effective_metadata = metadata if config.layout_signals else _without_layout(metadata)
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
                system_prompt=_reannotation_system_prompt(),
                max_retries=max_retries,
            ),
            block_metadata_by_index=effective_metadata,
            model_resolution={"requested_selector": config.model_selector, "model_id": selector.model_id},
        )
    elapsed = time.perf_counter() - started
    base = f"{config.mode}_{config.model_label}_{'layout' if config.layout_signals else 'nolayout'}"
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
            "layout_signals": config.layout_signals,
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
    raw_window, metadata = _extract_window_markdown(raw_full)
    output_dir = Path(args.output_root) / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "input.window.md").write_text(raw_window, encoding="utf-8")
    configs = [
        MatrixConfig(mode=mode, model_label=model_label, model_selector=MODELS[model_label], layout_signals=layout == "with")
        for mode in args.modes
        for model_label in args.models
        for layout in args.layout
    ]
    if args.max_configs > 0:
        configs = configs[: args.max_configs]
    results = []
    for config in configs:
        print(f"[matrix] {config.mode} {config.model_label} layout={config.layout_signals}", flush=True)
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
        "results": results,
    }
    summary_path = output_dir / "matrix_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[matrix] summary={summary_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
