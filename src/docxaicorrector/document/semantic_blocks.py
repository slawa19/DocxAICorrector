import re

from docxaicorrector.document.structure_authority import get_effective_structural_role, phase_uses_advisory_hints
from docxaicorrector.document.relations import build_paragraph_relations, resolve_effective_relation_kinds
from docxaicorrector.core.models import DocumentBlock, ParagraphRelation, ParagraphUnit


# Spec TOC/minimal-formatting 2026-04-21: a block becomes TOC-dominant at 70%+
# TOC structural-role composition unless all paragraphs are TOC lines.
TOC_DOMINANCE_THRESHOLD = 0.7
_INTERNAL_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")
_BIBLIOGRAPHY_LEAD_PATTERN = re.compile(r"^\s*(?:\[\d+\]|\(\d+\)|\d+[.)]\s+)")
_BIBLIOGRAPHY_TOKEN_PATTERN = re.compile(r"(?:https?://|www\.|\b(?:doi|isbn|issn|arxiv)\b)", re.IGNORECASE)
_BIBLIOGRAPHY_HEADING_PATTERN = re.compile(
    r"\b(?:references|bibliography|works cited|литература|список литературы|bibliographie)\b",
    re.IGNORECASE,
)
_SEMANTIC_BLOCK_TOC_ENTRY_PATTERN = re.compile(r"^.{1,120}(?:\.{2,}|\s{2,})\s*\d+\s*$")


def build_marker_wrapped_block_text(paragraphs: list[ParagraphUnit], *, paragraph_ids: list[str] | None = None) -> str:
    parts: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        paragraph_id = paragraph_ids[index] if paragraph_ids is not None else _resolve_marker_paragraph_id(paragraph, index)
        parts.append(f"[[DOCX_PARA_{paragraph_id}]]\n{paragraph.rendered_text}")
    return "\n\n".join(parts).strip()


def build_semantic_blocks(
    paragraphs: list[ParagraphUnit],
    max_chars: int = 6000,
    *,
    relations: list[ParagraphRelation] | None = None,
    hard_boundary_paragraph_ids: set[str] | None = None,
    structure_phase: str = "post_ai_final",
) -> list[DocumentBlock]:
    if not paragraphs:
        return []

    resolved_relations = relations
    if resolved_relations is None:
        resolved_relations, _ = build_paragraph_relations(
            paragraphs,
            enabled_relation_kinds=resolve_effective_relation_kinds(),
            structure_phase=structure_phase,
        )
    resolved_hard_boundary_paragraph_ids = {
        str(paragraph_id).strip() for paragraph_id in (hard_boundary_paragraph_ids or set()) if str(paragraph_id).strip()
    }
    paragraph_units = _build_semantic_block_units(
        paragraphs,
        resolved_relations,
        hard_boundary_paragraph_ids=resolved_hard_boundary_paragraph_ids,
        structure_phase=structure_phase,
    )
    soft_limit = max(1200, min(max_chars, int(max_chars * 0.7)))
    blocks: list[DocumentBlock] = []
    current: list[ParagraphUnit] = []
    current_size = 0

    def flush_current() -> None:
        nonlocal current, current_size
        if current:
            blocks.append(DocumentBlock(paragraphs=current))
            current = []
            current_size = 0

    def append_unit(unit_paragraphs: list[ParagraphUnit]) -> None:
        nonlocal current_size
        separator_size = 2 if current else 0
        current.extend(unit_paragraphs)
        unit_text = "\n\n".join(paragraph.rendered_text for paragraph in unit_paragraphs)
        current_size += separator_size + len(unit_text)

    for unit_paragraphs in paragraph_units:
        unit_text = "\n\n".join(paragraph.rendered_text for paragraph in unit_paragraphs)
        unit_contains_atomic_block = any(paragraph.role in {"image", "table"} for paragraph in unit_paragraphs)
        unit_all_headings = all(paragraph.role == "heading" for paragraph in unit_paragraphs)
        unit_is_list = all(paragraph.role == "list" for paragraph in unit_paragraphs)
        unit_is_quote_cluster = bool(unit_paragraphs) and all(
            _is_quote_structural_role(paragraph, structure_phase=structure_phase) for paragraph in unit_paragraphs
        )
        unit_is_toc_cluster = bool(unit_paragraphs) and all(
            _is_toc_structural_role(paragraph, structure_phase=structure_phase) for paragraph in unit_paragraphs
        )
        unit_starts_at_hard_boundary = bool(unit_paragraphs) and _paragraph_boundary_key(unit_paragraphs[0]) in resolved_hard_boundary_paragraph_ids
        if not current:
            append_unit(unit_paragraphs)
            continue

        if unit_starts_at_hard_boundary:
            flush_current()
            append_unit(unit_paragraphs)
            continue

        current_contains_atomic_block = any(item.role in {"image", "table"} for item in current)
        if current_contains_atomic_block:
            flush_current()
            append_unit(unit_paragraphs)
            continue

        if unit_contains_atomic_block:
            flush_current()
            append_unit(unit_paragraphs)
            continue

        projected_size = current_size + 2 + len(unit_text)
        current_all_headings = all(item.role == "heading" for item in current)
        current_is_list = all(item.role == "list" for item in current)
        current_is_toc_cluster = bool(current) and all(
            _is_toc_structural_role(item, structure_phase=structure_phase) for item in current
        )

        if unit_is_toc_cluster and not current_is_toc_cluster:
            flush_current()
            append_unit(unit_paragraphs)
            continue

        if current_is_toc_cluster and not unit_is_toc_cluster:
            flush_current()
            append_unit(unit_paragraphs)
            continue

        if unit_all_headings:
            if current_all_headings:
                append_unit(unit_paragraphs)
                continue
            flush_current()
            append_unit(unit_paragraphs)
            continue

        if current_all_headings:
            append_unit(unit_paragraphs)
            continue

        if current[-1].role == "heading" and unit_is_quote_cluster:
            append_unit(unit_paragraphs)
            continue

        if current[-1].role == "heading" and all(paragraph.role == "caption" for paragraph in unit_paragraphs):
            append_unit(unit_paragraphs)
            continue

        if current_is_list and unit_is_list:
            if projected_size <= max_chars or current_size < soft_limit:
                append_unit(unit_paragraphs)
            else:
                flush_current()
                append_unit(unit_paragraphs)
            continue

        if current_is_list and not unit_is_list:
            if current_size >= max(600, soft_limit // 2) or len(current) > 1:
                flush_current()
                append_unit(unit_paragraphs)
                continue

        if projected_size <= max_chars and current_size < soft_limit:
            append_unit(unit_paragraphs)
            continue

        if projected_size <= max_chars and len(unit_text) <= max(500, max_chars // 4) and current_size < int(max_chars * 0.9):
            append_unit(unit_paragraphs)
            continue

        flush_current()
        append_unit(unit_paragraphs)

    flush_current()
    return _split_unsafe_front_matter_blocks(blocks, max_chars=max_chars, structure_phase=structure_phase)


def build_context_excerpt(blocks: list[DocumentBlock], block_index: int, limit_chars: int, *, reverse: bool) -> str:
    if limit_chars <= 0:
        return ""

    indexes = range(block_index - 1, -1, -1) if reverse else range(block_index + 1, len(blocks))
    collected: list[str] = []
    total_size = 0

    for index in indexes:
        block_text = blocks[index].text.strip()
        if not block_text:
            continue

        separator_size = 2 if collected else 0
        projected_size = total_size + separator_size + len(block_text)
        if projected_size <= limit_chars:
            collected.append(block_text)
            total_size = projected_size
            continue

        remaining = limit_chars - total_size - separator_size
        if remaining > 0:
            excerpt = block_text[-remaining:] if reverse else block_text[:remaining]
            if excerpt.strip():
                collected.append(excerpt.strip())
        break

    if reverse:
        collected.reverse()

    return "\n\n".join(collected).strip()


def build_editing_jobs(
    blocks: list[DocumentBlock],
    *,
    max_chars: int,
    processing_operation: str = "edit",
    structure_phase: str = "post_ai_final",
) -> list[dict[str, object]]:
    context_before_chars = max(600, min(1400, int(max_chars * 0.2)))
    context_after_chars = max(300, min(800, int(max_chars * 0.12)))
    jobs: list[dict[str, object]] = []
    fallback_paragraph_index = 0
    bibliography_tail_indexes = _resolve_bibliography_tail_indexes(blocks, structure_phase=structure_phase)
    structure_source = _semantic_block_structure_source(structure_phase)

    for index, block in enumerate(blocks):
        context_before = build_context_excerpt(blocks, index, context_before_chars, reverse=True)
        context_after = build_context_excerpt(blocks, index, context_after_chars, reverse=False)
        structural_roles = [_paragraph_structural_kind(paragraph, structure_phase=structure_phase) for paragraph in block.paragraphs]
        paragraph_count = len(block.paragraphs)
        toc_only_paragraph_count = sum(
            1 for paragraph in block.paragraphs if _is_toc_only_paragraph(paragraph, structure_phase=structure_phase)
        )
        toc_dominant = bool(paragraph_count) and (
            toc_only_paragraph_count == paragraph_count
            or (toc_only_paragraph_count / paragraph_count) >= TOC_DOMINANCE_THRESHOLD
        )
        normalized_operation = str(processing_operation or "edit").strip().lower() or "edit"
        narration_include = _resolve_narration_include(
            block,
            block_index=index,
            bibliography_tail_indexes=bibliography_tail_indexes,
            structure_phase=structure_phase,
        )
        job_kind = (
            "passthrough"
            if block.paragraphs
            and (
                all(paragraph.role == "image" for paragraph in block.paragraphs)
                or (normalized_operation == "audiobook" and not narration_include)
                or (
                    normalized_operation != "translate"
                    and all(_is_toc_only_paragraph(paragraph, structure_phase=structure_phase) for paragraph in block.paragraphs)
                )
            )
            else "llm"
        )
        paragraph_ids = [
            _resolve_marker_paragraph_id(paragraph, fallback_paragraph_index + paragraph_index)
            for paragraph_index, paragraph in enumerate(block.paragraphs)
        ]
        jobs.append(
            {
                "job_kind": job_kind,
                "target_text": block.text,
                "target_text_with_markers": build_marker_wrapped_block_text(block.paragraphs, paragraph_ids=paragraph_ids),
                "paragraph_ids": paragraph_ids,
                "structural_roles": structural_roles,
                "narration_include": narration_include,
                "toc_dominant": toc_dominant,
                "toc_paragraph_count": toc_only_paragraph_count,
                "paragraph_count": paragraph_count,
                "context_before": context_before,
                "context_after": context_after,
                "target_chars": len(block.text),
                "context_chars": len(context_before) + len(context_after),
                "structure_phase": structure_phase,
                "structure_source": structure_source,
            }
        )
        fallback_paragraph_index += len(block.paragraphs)

    return jobs


def _build_semantic_block_units(
    paragraphs: list[ParagraphUnit],
    relations: list[ParagraphRelation],
    *,
    hard_boundary_paragraph_ids: set[str] | None = None,
    structure_phase: str,
) -> list[list[ParagraphUnit]]:
    resolved_hard_boundary_paragraph_ids = hard_boundary_paragraph_ids or set()
    index_by_paragraph_id = {
        paragraph.paragraph_id: index for index, paragraph in enumerate(paragraphs) if paragraph.paragraph_id
    }
    parent = list(range(len(paragraphs)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        if _indexes_cross_hard_boundary(
            paragraphs,
            left_index,
            right_index,
            hard_boundary_paragraph_ids=resolved_hard_boundary_paragraph_ids,
        ):
            return
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    for relation in relations:
        member_indexes = [index_by_paragraph_id[paragraph_id] for paragraph_id in relation.member_paragraph_ids if paragraph_id in index_by_paragraph_id]
        if len(member_indexes) < 2:
            continue
        for member_index in member_indexes[1:]:
            union(member_indexes[0], member_index)

    for index in range(len(paragraphs) - 1):
        left = paragraphs[index]
        right = paragraphs[index + 1]
        if _is_quote_structural_role(left, structure_phase=structure_phase) and _is_quote_structural_role(right, structure_phase=structure_phase):
            union(index, index + 1)
            continue
        if _is_toc_structural_role(left, structure_phase=structure_phase) and _is_toc_structural_role(right, structure_phase=structure_phase):
            union(index, index + 1)

    grouped_indexes: dict[int, list[int]] = {}
    for index in range(len(paragraphs)):
        grouped_indexes.setdefault(find(index), []).append(index)

    clusters = sorted((sorted(indexes) for indexes in grouped_indexes.values()), key=lambda indexes: indexes[0])
    units: list[list[ParagraphUnit]] = []
    for indexes in clusters:
        if indexes != list(range(indexes[0], indexes[-1] + 1)):
            for index in indexes:
                units.append([paragraphs[index]])
            continue
        units.append([paragraphs[index] for index in indexes])
    return units


def _resolve_marker_paragraph_id(paragraph: ParagraphUnit, fallback_index: int) -> str:
    if paragraph.paragraph_id:
        return paragraph.paragraph_id
    if paragraph.source_index >= 0:
        return f"p{paragraph.source_index:04d}"
    return f"p{fallback_index:04d}"


def _paragraph_structural_kind(paragraph: ParagraphUnit, *, structure_phase: str) -> str:
    return get_effective_structural_role(paragraph, phase=structure_phase)


def _paragraph_boundary_key(paragraph: ParagraphUnit) -> str:
    if paragraph.paragraph_id:
        return str(paragraph.paragraph_id).strip()
    if paragraph.source_index >= 0:
        return f"p{paragraph.source_index:04d}"
    return ""


def _indexes_cross_hard_boundary(
    paragraphs: list[ParagraphUnit],
    left_index: int,
    right_index: int,
    *,
    hard_boundary_paragraph_ids: set[str],
) -> bool:
    if not hard_boundary_paragraph_ids:
        return False
    start_index = min(left_index, right_index) + 1
    end_index = max(left_index, right_index)
    for index in range(start_index, end_index + 1):
        if _paragraph_boundary_key(paragraphs[index]) in hard_boundary_paragraph_ids:
            return True
    return False


def _is_quote_structural_role(paragraph: ParagraphUnit, *, structure_phase: str) -> bool:
    return _paragraph_structural_kind(paragraph, structure_phase=structure_phase) in {"epigraph", "attribution", "dedication"}


def _is_toc_structural_role(paragraph: ParagraphUnit, *, structure_phase: str) -> bool:
    if _paragraph_structural_kind(paragraph, structure_phase=structure_phase) in {"toc_header", "toc_entry"}:
        return True
    return _SEMANTIC_BLOCK_TOC_ENTRY_PATTERN.match(str(getattr(paragraph, "text", "")).strip()) is not None


def _is_toc_only_paragraph(paragraph: ParagraphUnit, *, structure_phase: str = "post_ai_final") -> bool:
    embedded_kinds = _embedded_hint_boundary_kinds(paragraph)
    if embedded_kinds:
        return all(kind in {"toc_header", "toc_entry"} for kind in embedded_kinds)
    return _is_toc_structural_role(paragraph, structure_phase=structure_phase)


def _embedded_hint_boundary_kinds(paragraph: ParagraphUnit) -> tuple[str, ...]:
    hints = getattr(paragraph, "heuristic_embedded_structure_hints", None) or ()
    kinds: list[str] = []
    for hint in hints:
        structural_role = str(getattr(hint, "structural_role", "") or "").strip().lower()
        role = str(getattr(hint, "role", "") or "").strip().lower()
        if structural_role and structural_role != "body":
            kinds.append(structural_role)
            continue
        if role and role != "body":
            kinds.append(role)
            continue
        kinds.append("body")
    return tuple(kinds)


def _paragraph_has_embedded_boundary_signal(paragraph: ParagraphUnit) -> bool:
    kinds = _embedded_hint_boundary_kinds(paragraph)
    if len(kinds) < 2:
        return False
    return any(right != left for left, right in zip(kinds, kinds[1:]))


def _strip_internal_placeholders(text: str) -> str:
    return _INTERNAL_PLACEHOLDER_PATTERN.sub("", text).strip()


def _iter_block_text_lines(block: DocumentBlock) -> list[str]:
    lines: list[str] = []
    for paragraph in block.paragraphs:
        raw_text = _strip_internal_placeholders(paragraph.text)
        if not raw_text:
            continue
        lines.extend(line.strip() for line in raw_text.splitlines() if line.strip())
    return lines


def _is_bibliography_like_line(line: str) -> bool:
    normalized = line.strip()
    if not normalized:
        return False
    return bool(
        _BIBLIOGRAPHY_LEAD_PATTERN.match(normalized)
        or _BIBLIOGRAPHY_TOKEN_PATTERN.search(normalized)
        or _BIBLIOGRAPHY_HEADING_PATTERN.search(normalized)
    )


def _is_heading_like_block(block: DocumentBlock, *, structure_phase: str = "post_ai_final") -> bool:
    if not block.paragraphs:
        return False
    if all(_is_toc_structural_role(paragraph, structure_phase=structure_phase) for paragraph in block.paragraphs):
        return False
    if not any(paragraph.role == "heading" for paragraph in block.paragraphs):
        return False
    lines = _iter_block_text_lines(block)
    if not lines:
        return False
    matches = sum(1 for line in lines if _is_bibliography_like_line(line))
    return (matches / len(lines)) < TOC_DOMINANCE_THRESHOLD


def _is_bibliography_like_block(block: DocumentBlock) -> bool:
    lines = _iter_block_text_lines(block)
    if not lines:
        return False
    matches = sum(1 for line in lines if _is_bibliography_like_line(line))
    return (matches / len(lines)) >= TOC_DOMINANCE_THRESHOLD


def _is_bibliography_like_region(blocks: list[DocumentBlock]) -> bool:
    region_lines: list[str] = []
    for block in blocks:
        region_lines.extend(_iter_block_text_lines(block))
    if not region_lines:
        return False
    matches = sum(1 for line in region_lines if _is_bibliography_like_line(line))
    return (matches / len(region_lines)) >= TOC_DOMINANCE_THRESHOLD


def _semantic_block_structure_source(structure_phase: str) -> str:
    return "pre_ai_diagnostic_hint" if phase_uses_advisory_hints(structure_phase) else "post_ai_final_binding"


def _resolve_bibliography_tail_indexes(blocks: list[DocumentBlock], *, structure_phase: str = "post_ai_final") -> set[int]:
    last_narrative_heading_index = -1
    for index, block in enumerate(blocks):
        if _is_heading_like_block(block, structure_phase=structure_phase):
            last_narrative_heading_index = index
    if last_narrative_heading_index < 0 or last_narrative_heading_index >= len(blocks) - 1:
        return set()

    for start_index in range(last_narrative_heading_index + 1, len(blocks)):
        candidate_blocks = blocks[start_index:]
        if not candidate_blocks:
            continue
        if _is_bibliography_like_region(candidate_blocks):
            return set(range(start_index, len(blocks)))
    return set()


def _resolve_narration_include(
    block: DocumentBlock,
    *,
    block_index: int,
    bibliography_tail_indexes: set[int],
    structure_phase: str = "post_ai_final",
) -> bool:
    if not block.paragraphs:
        return False
    if all(_is_toc_structural_role(paragraph, structure_phase=structure_phase) for paragraph in block.paragraphs):
        return False
    if all(_paragraph_structural_kind(paragraph, structure_phase=structure_phase) == "image" for paragraph in block.paragraphs):
        return False
    if not _iter_block_text_lines(block):
        return False
    if block_index in bibliography_tail_indexes:
        return False
    return True


def _split_unsafe_front_matter_blocks(
    blocks: list[DocumentBlock],
    *,
    max_chars: int,
    structure_phase: str = "pre_ai_diagnostic",
) -> list[DocumentBlock]:
    split_blocks: list[DocumentBlock] = []
    for block in blocks:
        split_blocks.extend(_split_single_unsafe_block(block, max_chars=max_chars, structure_phase=structure_phase))
    return split_blocks


def _split_single_unsafe_block(block: DocumentBlock, *, max_chars: int, structure_phase: str = "pre_ai_diagnostic") -> list[DocumentBlock]:
    paragraphs = list(block.paragraphs)
    if len(paragraphs) < 2:
        return [block]

    boundary_indexes: set[int] = set()
    for index in range(1, len(paragraphs)):
        previous = paragraphs[index - 1]
        current = paragraphs[index]
        previous_kind = _paragraph_structural_kind(previous, structure_phase=structure_phase)
        current_kind = _paragraph_structural_kind(current, structure_phase=structure_phase)

        if _paragraph_has_embedded_boundary_signal(previous):
            boundary_indexes.add(index)
            continue

        if previous_kind in {"toc_header", "toc_entry"} and current_kind not in {"toc_header", "toc_entry"}:
            boundary_indexes.add(index)
            continue
        if previous_kind not in {"toc_header", "toc_entry"} and current_kind in {"toc_header", "toc_entry"}:
            boundary_indexes.add(index)
            continue
        if previous_kind in {"epigraph", "attribution", "dedication"} and current_kind not in {"epigraph", "attribution", "dedication"}:
            boundary_indexes.add(index)
            continue
        if current.role == "heading" and any(
            _paragraph_structural_kind(paragraph, structure_phase=structure_phase)
            in {"toc_header", "toc_entry", "epigraph", "attribution", "dedication"}
            for paragraph in paragraphs[:index]
        ):
            boundary_indexes.add(index)
            continue

    if not boundary_indexes:
        return [block]

    chunks: list[DocumentBlock] = []
    start = 0
    for boundary in sorted(boundary_indexes):
        if boundary <= start:
            continue
        chunks.append(DocumentBlock(paragraphs=paragraphs[start:boundary]))
        start = boundary
    if start < len(paragraphs):
        chunks.append(DocumentBlock(paragraphs=paragraphs[start:]))

    if len(chunks) <= 1:
        return [block]

    # Keep extremely small chunks only when they isolate a real structural boundary.
    normalized_chunks: list[DocumentBlock] = []
    for chunk in chunks:
        if not normalized_chunks:
            normalized_chunks.append(chunk)
            continue
        if len(chunk.text) < 30 and len(chunk.paragraphs) == 1 and chunk.paragraphs[0].role != "heading":
            normalized_chunks[-1] = DocumentBlock(paragraphs=[*normalized_chunks[-1].paragraphs, *chunk.paragraphs])
            continue
        normalized_chunks.append(chunk)
    return normalized_chunks
