"""Runtime-display Markdown normalization + registry-heading restore (spec 031 Cluster A).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the markdown
normalizers that produce the quality-gate text, the display-hygiene reporting text, and
the delivered runtime-display Markdown, plus the generated-paragraph-registry heading
restore helpers that stitch source-declared heading lines back onto DOCX image
placeholders. ``late_phases`` re-exports every name here so ``late_phases.<name>`` keeps
resolving for the test namespace and the still-in-``late_phases`` callers. No module-level
mutable state; nothing here is monkeypatched.
"""

import re
from collections.abc import Collection, Mapping, Sequence

from docxaicorrector.pipeline.output_validation import (
    normalize_false_fragment_headings_markdown,
    normalize_heading_match_text,
    normalize_list_fragment_regressions_markdown,
    normalize_mixed_script_markdown,
    normalize_page_placeholder_heading_concats_markdown,
    normalize_residual_bullet_glyphs_markdown,
)


_BULLET_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^\s{0,3}#{1,6}\s*[\u2022\u25cf\u25e6\u2023*\-]\s*$")
_DOCX_IMAGE_HEADING_CONCAT_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?P<placeholder>\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\])\s+(?P<text>\S.*)$"
)
_MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^\s*(?P<marker>#{1,6})\s+(?P<text>\S.*)$")
# User-facing review anchors must never carry internal paragraph/image ids. Covers both
# placeholder families (reuses the shapes at _DOCX_IMAGE_PLACEHOLDER_PATTERN and
# generation/document PARAGRAPH_MARKER_PATTERN); a bare literal "[[" is deliberately NOT
# matched so real code samples survive (FR-004 anti-regression).
_DOCX_INTERNAL_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_(?:PARA|IMAGE)_[A-Za-z0-9_]+\]\]")
# A leading markdown heading marker ("### ") is display noise, not locatable text; strip it
# only when it is a genuine heading marker (followed by whitespace or end-of-string), so an
# inline "#hashtag" is left intact.
_REVIEW_ANCHOR_HEADING_MARKER_PATTERN = re.compile(r"^#{1,6}(?=\s|$)\s*")


def _normalize_final_markdown_for_quality_gate(text: str) -> str:
    normalized = text
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _normalize_final_markdown_for_display_hygiene_reporting(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _apply_runtime_display_structure_compatibility_cleanup(
    text: str,
    protected_heading_texts: Collection[str] | None = None,
) -> str:
    # This output IS the delivered DOCX (rebuilt from runtime_display_markdown below);
    # it is not display-only. The protected set keeps source-declared headings intact.
    normalized = normalize_false_fragment_headings_markdown(text, protected_heading_texts=protected_heading_texts)
    return normalize_list_fragment_regressions_markdown(normalized, protected_heading_texts=protected_heading_texts)


def _apply_runtime_display_hygiene_cleanup(text: str) -> str:
    normalized = normalize_page_placeholder_heading_concats_markdown(text)
    normalized = normalize_residual_bullet_glyphs_markdown(normalized)
    return normalize_mixed_script_markdown(normalized)


def _normalize_final_markdown_for_runtime_display(
    text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> str:
    protected_heading_texts = _registry_protected_heading_texts(generated_paragraph_registry)
    normalized = _apply_runtime_display_structure_compatibility_cleanup(text, protected_heading_texts)
    normalized = _apply_runtime_display_hygiene_cleanup(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if "\n" not in normalized and "\n\n" in text:
        return text
    return normalized


def _normalize_heading_match_text(text: str) -> str:
    # Single source of truth lives in output_validation so the protected-heading
    # set and the false-fragment cleanup normalize identically.
    return normalize_heading_match_text(text)


def _registry_heading_markdown_lines(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> list[tuple[str, str]]:
    heading_lines: list[tuple[str, str]] = []
    for entry in generated_paragraph_registry or []:
        text = str(entry.get("text") or entry.get("generated_text") or "").strip()
        match = _MARKDOWN_HEADING_LINE_PATTERN.match(text)
        if match is None:
            continue
        heading_text = str(match.group("text") or "").strip()
        normalized_heading = _normalize_heading_match_text(heading_text)
        if not normalized_heading:
            continue
        heading_lines.append((normalized_heading, f"{match.group('marker')} {heading_text}"))
    return heading_lines


def _registry_protected_heading_texts(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> set[str]:
    # Source-declared heading lines whose role must survive into the delivered DOCX.
    return {normalized for normalized, _ in _registry_heading_markdown_lines(generated_paragraph_registry)}


def _restore_image_heading_lines_from_registry(
    markdown_text: str,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> str:
    heading_lines = _registry_heading_markdown_lines(generated_paragraph_registry)
    if not heading_lines:
        return markdown_text

    restored_lines: list[str] = []
    changed = False
    for raw_line in markdown_text.splitlines():
        match = _DOCX_IMAGE_HEADING_CONCAT_PATTERN.match(raw_line.rstrip())
        if match is None:
            restored_lines.append(raw_line.rstrip())
            continue

        concat_text = str(match.group("text") or "")
        normalized_concat = _normalize_heading_match_text(concat_text)
        matched_headings: list[str] = []
        for normalized_heading, heading_markdown in heading_lines:
            if normalized_heading in normalized_concat and heading_markdown not in matched_headings:
                matched_headings.append(heading_markdown)
        if not matched_headings:
            restored_lines.append(raw_line.rstrip())
            continue

        restored_lines.append(f"{match.group('indent')}{match.group('placeholder')}")
        restored_lines.append("")
        restored_lines.extend(f"{match.group('indent')}{heading}" for heading in matched_headings)
        changed = True

    if not changed:
        return markdown_text
    return re.sub(r"\n{3,}", "\n\n", "\n".join(restored_lines)).strip()


def _resolve_runtime_display_markdown(*, docx_phase: Mapping[str, object], fallback_markdown: str) -> str:
    runtime_display_markdown = docx_phase.get("runtime_display_markdown")
    if isinstance(runtime_display_markdown, str) and runtime_display_markdown:
        return runtime_display_markdown

    return _normalize_final_markdown_for_runtime_display(fallback_markdown)
