from document_relations import build_paragraph_relations, resolve_effective_relation_kinds
from models import DocumentBlock, ParagraphRelation, ParagraphUnit


# Spec TOC/minimal-formatting 2026-04-21: a block becomes TOC-dominant at 70%+
# TOC structural-role composition unless all paragraphs are TOC lines.
TOC_DOMINANCE_THRESHOLD = 0.7


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
) -> list[DocumentBlock]:
    if not paragraphs:
        return []

    resolved_relations = relations
    if resolved_relations is None:
        resolved_relations, _ = build_paragraph_relations(
            paragraphs,
            enabled_relation_kinds=resolve_effective_relation_kinds(),
        )
    paragraph_units = _build_semantic_block_units(paragraphs, resolved_relations)
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
        unit_is_quote_cluster = bool(unit_paragraphs) and all(_is_quote_structural_role(paragraph) for paragraph in unit_paragraphs)
        unit_is_toc_cluster = bool(unit_paragraphs) and all(_is_toc_structural_role(paragraph) for paragraph in unit_paragraphs)
        if not current:
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
        current_is_toc_cluster = bool(current) and all(_is_toc_structural_role(item) for item in current)

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
    return blocks


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


def build_editing_jobs(blocks: list[DocumentBlock], max_chars: int, processing_operation: str = "edit") -> list[dict[str, object]]:
    context_before_chars = max(600, min(1400, int(max_chars * 0.2)))
    context_after_chars = max(300, min(800, int(max_chars * 0.12)))
    jobs: list[dict[str, object]] = []
    fallback_paragraph_index = 0

    for index, block in enumerate(blocks):
        context_before = build_context_excerpt(blocks, index, context_before_chars, reverse=True)
        context_after = build_context_excerpt(blocks, index, context_after_chars, reverse=False)
        structural_roles = [_paragraph_structural_kind(paragraph) for paragraph in block.paragraphs]
        paragraph_count = len(block.paragraphs)
        toc_paragraph_count = sum(1 for role in structural_roles if role in {"toc_header", "toc_entry"})
        toc_dominant = bool(paragraph_count) and (
            toc_paragraph_count == paragraph_count
            or (toc_paragraph_count / paragraph_count) >= TOC_DOMINANCE_THRESHOLD
        )
        normalized_operation = str(processing_operation or "edit").strip().lower() or "edit"
        job_kind = (
            "passthrough"
            if block.paragraphs
            and (
                all(paragraph.role == "image" for paragraph in block.paragraphs)
                or (normalized_operation != "translate" and all(_is_toc_structural_role(paragraph) for paragraph in block.paragraphs))
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
                "toc_dominant": toc_dominant,
                "toc_paragraph_count": toc_paragraph_count,
                "paragraph_count": paragraph_count,
                "context_before": context_before,
                "context_after": context_after,
                "target_chars": len(block.text),
                "context_chars": len(context_before) + len(context_after),
            }
        )
        fallback_paragraph_index += len(block.paragraphs)

    return jobs


def _build_semantic_block_units(
    paragraphs: list[ParagraphUnit],
    relations: list[ParagraphRelation],
) -> list[list[ParagraphUnit]]:
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
        if _is_quote_structural_role(left) and _is_quote_structural_role(right):
            union(index, index + 1)
            continue
        if _is_toc_structural_role(left) and _is_toc_structural_role(right):
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


def _paragraph_structural_kind(paragraph: ParagraphUnit) -> str:
    return str(paragraph.structural_role or paragraph.role or "").strip().lower()


def _is_quote_structural_role(paragraph: ParagraphUnit) -> bool:
    return _paragraph_structural_kind(paragraph) in {"epigraph", "attribution", "dedication"}


def _is_toc_structural_role(paragraph: ParagraphUnit) -> bool:
    return _paragraph_structural_kind(paragraph) in {"toc_header", "toc_entry"}
