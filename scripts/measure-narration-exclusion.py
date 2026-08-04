"""Measure what `_resolve_narration_include` actually excludes, before writing any rule.

Spec 054 asks the first question of the audiobook run: how many blocks does the existing
narration-exclusion decision really drop, and for which reason. Twice in 2026-08-02..03 this
project found a rule that existed and never fired, so the count comes before the code.

The whole chain used here is LLM-free: `_prepare_document_for_processing` never touches
`get_client_fn`, and structure recognition was removed from preparation. So this reproduces the
production decision exactly (same structure phase, same segmentation, same block indexes) without
spending a token.

Run (WSL, .venv has pdfminer):
    . .venv/bin/activate && export PYTHONPATH="$PWD/src:$PWD" \
        && python scripts/measure-narration-exclusion.py tests/sources/book/*.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import docxaicorrector.processing.processing_runtime as processing_runtime
from docxaicorrector.core.config import load_app_config
from docxaicorrector.core.constants import DEFAULT_CHUNK_SIZE
from docxaicorrector.processing.preparation import _prepare_document_for_processing

# Production preparation passes this phase, not the `post_ai_final` default of the callee.
PRODUCTION_STRUCTURE_PHASE = "pre_ai_diagnostic"


def _no_llm_client(*args: object, **kwargs: object) -> object:
    raise AssertionError("preparation must not need an LLM client — measurement is offline by contract")


def _app_config_mapping() -> dict[str, Any]:
    app_config = load_app_config()
    if isinstance(app_config, dict):
        return dict(app_config)
    to_dict = getattr(app_config, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return {}


def _classify_exclusion_reason(job: dict[str, Any]) -> str:
    """Attribute an excluded block to the branch of `_resolve_narration_include` that dropped it.

    Mirrors the function's own order of checks; `structural_roles` and the block text are the two
    signals the job carries, which is enough to separate the four existing branches.
    """
    roles = [str(role or "").strip().lower() for role in (job.get("structural_roles") or [])]
    text = str(job.get("target_text") or "")
    if not roles:
        return "empty_block"
    if all(role in {"toc_header", "toc_entry"} for role in roles):
        return "toc_structural_role"
    if all(role == "image" for role in roles):
        return "image_only"
    if not text.strip():
        return "no_text_lines"
    # Spec 054: the region branch was renamed `bibliography_tail` -> `reference_region` on
    # 2026-08-04 when it stopped being a bibliography-ratio test over the document suffix and
    # became a back-matter section region (notes / references / bibliography / sources).
    return "reference_region"


def measure(source_path: Path, *, chunk_size: int) -> dict[str, Any]:
    source_bytes = source_path.read_bytes()
    normalized = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
    prepared = _prepare_document_for_processing(
        normalized.filename,
        normalized.content_bytes,
        chunk_size,
        source_format=normalized.source_format,
        conversion_backend=normalized.conversion_backend,
        app_config=_app_config_mapping(),
        processing_operation="audiobook",
        get_client_fn=_no_llm_client,
        client_factory=None,
    )

    jobs = list(prepared.jobs)
    excluded = [job for job in jobs if not bool(job.get("narration_include", True))]
    reasons = Counter(_classify_exclusion_reason(job) for job in excluded)

    total_chars = sum(len(str(job.get("target_text") or "")) for job in jobs)
    excluded_chars = sum(len(str(job.get("target_text") or "")) for job in excluded)

    return {
        "source": source_path.name,
        "source_format": normalized.source_format,
        "structure_phase": PRODUCTION_STRUCTURE_PHASE,
        "paragraph_count": len(prepared.paragraphs),
        "block_count": len(jobs),
        "excluded_narration_block_count": len(excluded),
        "excluded_block_share": round(len(excluded) / len(jobs), 4) if jobs else 0.0,
        "excluded_char_share": round(excluded_chars / total_chars, 4) if total_chars else 0.0,
        "excluded_by_reason": dict(sorted(reasons.items())),
        # Samples per reason, not per position: the region branch fires at the end of the
        # document and would otherwise never appear behind the image/TOC blocks.
        "excluded_samples": _samples_by_reason(jobs, excluded),
    }


def _samples_by_reason(jobs: list[dict[str, Any]], excluded: list[dict[str, Any]], *, per_reason: int = 8) -> list[dict[str, Any]]:
    seen: Counter[str] = Counter()
    samples: list[dict[str, Any]] = []
    for job in excluded:
        reason = _classify_exclusion_reason(job)
        seen[reason] += 1
        if seen[reason] > per_reason:
            continue
        samples.append(
            {
                "block_index": jobs.index(job),
                "reason": reason,
                "roles": list(job.get("structural_roles") or [])[:6],
                "chars": len(str(job.get("target_text") or "")),
                "text_head": str(job.get("target_text") or "")[:300].replace("\n", " ⏎ "),
            }
        )
    return samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path, help="book files (.pdf/.docx) to measure")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    results: list[dict[str, Any]] = []
    for source_path in args.sources:
        if not source_path.exists():
            print(f"!! missing: {source_path}", flush=True)
            continue
        print(f"== {source_path.name}", flush=True)
        try:
            result = measure(source_path, chunk_size=args.chunk_size)
        except Exception as exc:  # a failed book must not hide the others
            print(f"   FAILED: {type(exc).__name__}: {exc}", flush=True)
            results.append({"source": source_path.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        results.append(result)
        print(
            f"   blocks={result['block_count']} excluded={result['excluded_narration_block_count']}"
            f" ({result['excluded_block_share']:.1%} of blocks, {result['excluded_char_share']:.1%} of chars)"
            f" by_reason={result['excluded_by_reason']}",
            flush=True,
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
