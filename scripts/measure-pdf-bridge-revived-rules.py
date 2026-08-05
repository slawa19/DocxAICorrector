"""Measure the three rules spec 055 calls dead, per book, before and after the bridge carries signal.

The spec's claim is that `promote_short_standalone_headings`, `normalize_front_matter_display_title`
and every branch requiring `paragraph_alignment == "center"` cannot fire on a PDF-imported book,
because the intermediate DOCX carries neither alignment nor a real font size. A count alone would not
settle whether reviving them is an improvement, so this script records WHAT each rule touched, with
the text of the paragraph and its neighbours, so a human can read the promotion and judge it.

It also dumps the final paragraph stream (text, role, heading level, alignment, font size) keyed by
text, which is what a before/after diff has to be argued on -- per source paragraph, not per counter.

Offline: `_prepare_document_for_processing` never constructs an LLM client.

Run (WSL, `.venv` has pdfminer):
    . .venv/bin/activate && export PYTHONPATH="$PWD/src:$PWD" \
        && python scripts/measure-pdf-bridge-revived-rules.py tests/sources/book/*.pdf \
            --json-out .run/brg_rules_before.json --dump-dir .run/brg_paragraphs_before
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

import docxaicorrector.document.extraction as extraction
import docxaicorrector.document.relations as relations
import docxaicorrector.document.roles as roles
import docxaicorrector.document.segments as segments
import docxaicorrector.document.structure_repair as structure_repair
import docxaicorrector.processing.processing_runtime as processing_runtime
import docxaicorrector.structure.validation as structure_validation
from docxaicorrector.core.config import load_app_config
from docxaicorrector.core.constants import DEFAULT_CHUNK_SIZE
from docxaicorrector.processing.preparation import _prepare_document_for_processing

PRODUCTION_STRUCTURE_PHASE = "pre_ai_diagnostic"

# Prose that spec 054 recovered; anti-regression item 5 requires it to stay in the stream.
_SPEC_054_PROSE_PROBES = (
    "Jungian psychologist Bernice Hill",
    "not generally known",
    "large-scale banking crises",
    "deeply ingrained ideas",
)


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


def _head(value: object, limit: int = 160) -> str:
    return str(value or "").replace("\n", " ⏎ ")[:limit]


class _RuleProbe:
    """Wraps the rules and the center-alignment predicates and records every firing."""

    def __init__(self) -> None:
        self.promotions: list[dict[str, Any]] = []
        self.front_matter: list[dict[str, Any]] = []
        self.center_hits: Counter[str] = Counter()
        self.center_samples: dict[str, list[str]] = {}
        self._originals: list[tuple[Any, str, Any]] = []

    def _record_center(self, site: str, text: str) -> None:
        self.center_hits[site] += 1
        samples = self.center_samples.setdefault(site, [])
        if len(samples) < 10:
            samples.append(_head(text, 120))

    def _patch(self, module: Any, name: str, replacement: Any) -> None:
        self._originals.append((module, name, getattr(module, name)))
        setattr(module, name, replacement)

    def install(self) -> None:
        original_promote = roles.promote_short_standalone_headings
        original_front_matter = roles.normalize_front_matter_display_title
        original_strong = roles._paragraph_unit_has_strong_heading_format
        original_docx_strong = roles.paragraph_has_strong_heading_format
        original_probable = roles.is_probable_heading
        original_epigraph = roles._is_short_centered_epigraph_attribution_candidate
        original_boundary = structure_repair._is_body_boundary_candidate
        original_typography = segments._has_typography_heading_signal
        original_centered_body = structure_validation._is_centered_body
        original_attribution = relations._is_epigraph_relation_candidate

        def promote(paragraphs, **kwargs):
            before = [(p.role, p.heading_level, p.heuristic_role_hint) for p in paragraphs]
            original_promote(paragraphs, **kwargs)
            for index, (previous, paragraph) in enumerate(zip(before, paragraphs, strict=False)):
                after = (paragraph.role, paragraph.heading_level, paragraph.heuristic_role_hint)
                if after == previous:
                    continue
                self.promotions.append(
                    {
                        "index": index,
                        "text": _head(paragraph.text),
                        "font_size_pt": paragraph.font_size_pt,
                        "alignment": paragraph.paragraph_alignment,
                        "is_bold": paragraph.is_bold,
                        "before": {"role": previous[0], "heading_level": previous[1], "hint": previous[2]},
                        "after": {"role": after[0], "heading_level": after[1], "hint": after[2]},
                        "prev_text": _head(paragraphs[index - 1].text, 110) if index else "",
                        "prev_font_size_pt": paragraphs[index - 1].font_size_pt if index else None,
                        "next_text": _head(paragraphs[index + 1].text, 110) if index + 1 < len(paragraphs) else "",
                        "next_font_size_pt": paragraphs[index + 1].font_size_pt if index + 1 < len(paragraphs) else None,
                    }
                )

        def front_matter(paragraphs, **kwargs):
            before = [(p.role, p.heading_level, p.heuristic_role_hint) for p in paragraphs]
            original_front_matter(paragraphs, **kwargs)
            for index, (previous, paragraph) in enumerate(zip(before, paragraphs, strict=False)):
                after = (paragraph.role, paragraph.heading_level, paragraph.heuristic_role_hint)
                if after == previous:
                    continue
                self.front_matter.append(
                    {
                        "index": index,
                        "text": _head(paragraph.text),
                        "font_size_pt": paragraph.font_size_pt,
                        "alignment": paragraph.paragraph_alignment,
                        "before": {"role": previous[0], "heading_level": previous[1], "hint": previous[2]},
                        "after": {"role": after[0], "heading_level": after[1], "hint": after[2]},
                    }
                )

        def strong_heading_format(paragraph):
            result = original_strong(paragraph)
            if result and paragraph.paragraph_alignment == "center" and not paragraph.is_bold:
                self._record_center("roles._paragraph_unit_has_strong_heading_format", paragraph.text)
            return result

        def docx_strong_heading_format(paragraph):
            # The raw-DOCX twin of the predicate above, and the one that actually decides a
            # role: `extraction._build_raw_paragraph` reaches `is_probable_heading` through it.
            result = original_docx_strong(paragraph)
            if result and roles.resolve_paragraph_alignment(paragraph) == "center":
                self._record_center("roles.paragraph_has_strong_heading_format", paragraph.text)
            return result

        def probable_heading(paragraph, text, normalized_style):
            result = original_probable(paragraph, text, normalized_style)
            if result and roles.resolve_paragraph_alignment(paragraph) == "center":
                self._record_center("roles.is_probable_heading", text)
            return result

        def epigraph_attribution(paragraph, **kwargs):
            result = original_epigraph(paragraph, **kwargs)
            if result:
                self._record_center("roles._is_short_centered_epigraph_attribution_candidate", paragraph.text)
            return result

        def body_boundary(paragraph):
            result = original_boundary(paragraph)
            if (
                result
                and paragraph.role != "heading"
                and paragraph.paragraph_alignment == "center"
                and not structure_repair._is_toc_candidate_text(str(paragraph.text or "").strip())
            ):
                self._record_center("structure_repair._is_body_boundary_candidate", paragraph.text)
            return result

        def typography_heading_signal(paragraph, text):
            result = original_typography(paragraph, text)
            if result and str(getattr(paragraph, "paragraph_alignment", "") or "").lower() == "center":
                self._record_center("segments._has_typography_heading_signal", text)
            return result

        def centered_body(paragraph, *, phase):
            result = original_centered_body(paragraph, phase=phase)
            if result:
                self._record_center("structure.validation._is_centered_body", getattr(paragraph, "text", ""))
            return result

        def attribution_pair(left, right, *, structure_phase):
            result = original_attribution(left, right, structure_phase=structure_phase)
            if result and getattr(left, "paragraph_alignment", None) == "center":
                self._record_center("relations._is_epigraph_relation_candidate", getattr(right, "text", ""))
            return result

        self._patch(roles, "promote_short_standalone_headings", promote)
        self._patch(extraction, "promote_short_standalone_headings", promote)
        self._patch(roles, "normalize_front_matter_display_title", front_matter)
        self._patch(extraction, "normalize_front_matter_display_title", front_matter)
        self._patch(roles, "_paragraph_unit_has_strong_heading_format", strong_heading_format)
        self._patch(roles, "paragraph_has_strong_heading_format", docx_strong_heading_format)
        self._patch(roles, "is_probable_heading", probable_heading)
        self._patch(extraction, "is_probable_heading", probable_heading)
        self._patch(roles, "_is_short_centered_epigraph_attribution_candidate", epigraph_attribution)
        self._patch(structure_repair, "_is_body_boundary_candidate", body_boundary)
        self._patch(segments, "_has_typography_heading_signal", typography_heading_signal)
        self._patch(structure_validation, "_is_centered_body", centered_body)
        self._patch(relations, "_is_epigraph_relation_candidate", attribution_pair)

    def uninstall(self) -> None:
        for module, name, original in reversed(self._originals):
            setattr(module, name, original)
        self._originals.clear()


def measure(source_path: Path, *, chunk_size: int, dump_dir: Path | None) -> dict[str, Any]:
    probe = _RuleProbe()
    probe.install()
    try:
        source_bytes = source_path.read_bytes()
        normalized = processing_runtime.normalize_uploaded_document(
            filename=source_path.name, source_bytes=source_bytes
        )
        prepared = _prepare_document_for_processing(
            normalized.filename,
            normalized.content_bytes,
            chunk_size,
            source_format=normalized.source_format,
            conversion_backend=normalized.conversion_backend,
            app_config=_app_config_mapping(),
            processing_operation="translate",
            get_client_fn=_no_llm_client,
            client_factory=None,
        )
    finally:
        probe.uninstall()

    paragraphs = list(prepared.paragraphs)
    roles_counter = Counter(str(p.role or "") for p in paragraphs)
    structural_counter = Counter(str(p.structural_role or "") for p in paragraphs)
    heading_levels = Counter(p.heading_level for p in paragraphs if p.role == "heading")
    alignment_counter = Counter(str(p.paragraph_alignment or "") for p in paragraphs)

    if dump_dir is not None:
        dump_dir.mkdir(parents=True, exist_ok=True)
        dump = [
            {
                "i": index,
                "role": p.role,
                "structural_role": p.structural_role,
                "heading_level": p.heading_level,
                "alignment": p.paragraph_alignment,
                "font_size_pt": p.font_size_pt,
                "gap_before_pt": p.vertical_gap_before_pt,
                "text": str(p.text or ""),
            }
            for index, p in enumerate(paragraphs)
        ]
        (dump_dir / f"{source_path.stem}.json").write_text(
            json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    prose_probe = {}
    for needle in _SPEC_054_PROSE_PROBES:
        matches = [index for index, p in enumerate(paragraphs) if needle in str(p.text or "")]
        prose_probe[needle] = {
            "count": len(matches),
            "indexes": matches[:4],
            "roles": [paragraphs[index].role for index in matches[:4]],
        }

    return {
        "source": source_path.name,
        "source_format": normalized.source_format,
        "paragraph_count": len(paragraphs),
        "block_count": len(prepared.jobs),
        "role_counts": dict(roles_counter.most_common()),
        "structural_role_counts": dict(structural_counter.most_common()),
        "heading_level_counts": {str(k): v for k, v in sorted(heading_levels.items(), key=lambda i: (i[0] is None, i[0]))},
        "alignment_counts": dict(alignment_counter.most_common()),
        "promote_short_standalone_headings": {
            "fire_count": len(probe.promotions),
            "firings": probe.promotions,
        },
        "normalize_front_matter_display_title": {
            "fire_count": len(probe.front_matter),
            "firings": probe.front_matter,
        },
        "center_alignment_branches": {
            "hits": dict(probe.center_hits.most_common()),
            "samples": probe.center_samples,
        },
        "spec_054_prose_probe": prose_probe,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--dump-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    results: list[dict[str, Any]] = []
    for source_path in args.sources:
        if not source_path.exists():
            print(f"!! missing: {source_path}", flush=True)
            continue
        print(f"== {source_path.name}", flush=True)
        try:
            result = measure(source_path, chunk_size=args.chunk_size, dump_dir=args.dump_dir)
        except Exception as exc:
            print(f"   FAILED: {type(exc).__name__}: {exc}", flush=True)
            results.append({"source": source_path.name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        results.append(result)
        print(
            f"   paragraphs={result['paragraph_count']} roles={result['role_counts']}",
            flush=True,
        )
        print(
            f"   promote={result['promote_short_standalone_headings']['fire_count']}"
            f" front_matter={result['normalize_front_matter_display_title']['fire_count']}"
            f" center_branches={result['center_alignment_branches']['hits']}",
            flush=True,
        )

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
