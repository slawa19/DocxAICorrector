import re

from docxaicorrector.document.structure_authority import (
    get_effective_structural_role,
    normalize_structure_phase,
    phase_uses_advisory_hints,
)
from docxaicorrector.document.relations import build_paragraph_relations, resolve_effective_relation_kinds
from docxaicorrector.core.models import DocumentBlock, ParagraphRelation, ParagraphUnit
from docxaicorrector.validation.formatting_coverage import (
    _BACKMATTER_SECTION_TITLES,
    _normalize_structural_text,
)


# Spec TOC/minimal-formatting 2026-04-21: a block becomes TOC-dominant at 70%+
# TOC structural-role composition unless all paragraphs are TOC lines.
TOC_DOMINANCE_THRESHOLD = 0.7
_INTERNAL_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")
_SEMANTIC_BLOCK_TOC_ENTRY_PATTERN = re.compile(r"^.{1,120}(?:\.{2,}|\s{2,})\s*\d+\s*$")

# Spec 054 (2026-08-04): the audiobook narration drops the back-matter reference sections
# outright — nobody listens to a bibliography. Constitution VII names the region family in
# `validation/formatting_coverage.py` as the precedent for this kind of detection and blesses
# its structural-anchor title lexicon as an accepted, extensible residual, so that lexicon is
# REUSED here rather than restated: one list, one place, no drift.
#
# The index used to be subtracted from that lexicon, because the owner's first framing named the
# table of contents, the notes and the sources and did not name the index. **That decision was
# reversed by the owner on 2026-08-06**, once the price was measured: on Rethinking Money the index
# is 463 paragraphs / 38 470 characters of "Красота, 152, 201, 223" read aloud. The signal is also
# the sound one of the three — unlike its NOTES and BIBLIOGRAPHY, that book's index title arrives
# from import carrying a real heading role. So the whole lexicon is used, and the subtraction and
# its constant are gone rather than commented out: the next reader should see the decision, not its
# archaeology.
_NARRATION_REFERENCE_SECTION_TITLES = frozenset(_BACKMATTER_SECTION_TITLES)

# Markdown emphasis the PDF import path carries INSIDE `ParagraphUnit.text`.
_INLINE_EMPHASIS_MARKERS = ("**", "__", "*", "_")


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
    reference_region_indexes = _resolve_reference_region_indexes(blocks, structure_phase=structure_phase)
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
            reference_region_indexes=reference_region_indexes,
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
        if not _relation_supports_semantic_grouping(relation, structure_phase=structure_phase):
            continue
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


def _relation_supports_semantic_grouping(relation: ParagraphRelation, *, structure_phase: str) -> bool:
    allowed_relation_kinds = {"image_caption", "table_caption", "epigraph_attribution", "toc_region"}
    if phase_uses_advisory_hints(structure_phase):
        allowed_relation_kinds.add("toc_region_candidate")
    return str(getattr(relation, "relation_kind", "") or "").strip() in allowed_relation_kinds


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
    if not phase_uses_advisory_hints(structure_phase):
        return False
    return _SEMANTIC_BLOCK_TOC_ENTRY_PATTERN.match(str(getattr(paragraph, "text", "")).strip()) is not None


def _is_toc_only_paragraph(paragraph: ParagraphUnit, *, structure_phase: str = "post_ai_final") -> bool:
    embedded_kinds = _embedded_hint_boundary_kinds(paragraph)
    if embedded_kinds and _phase_uses_embedded_toc_only_fallback(structure_phase):
        return all(kind in {"toc_header", "toc_entry"} for kind in embedded_kinds)
    return _is_toc_structural_role(paragraph, structure_phase=structure_phase)


def _phase_uses_embedded_toc_only_fallback(structure_phase: str) -> bool:
    normalized_phase = normalize_structure_phase(structure_phase)
    return phase_uses_advisory_hints(normalized_phase) or normalized_phase == "ai_first_degraded_fallback"


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


def _semantic_block_structure_source(structure_phase: str) -> str:
    if str(structure_phase or "").strip().lower() == "ai_first_degraded_fallback":
        return "ai_first_degraded_fallback"
    return "pre_ai_diagnostic_hint" if phase_uses_advisory_hints(structure_phase) else "post_ai_final_binding"


def _block_has_heading_paragraph(block: DocumentBlock) -> bool:
    return any(paragraph.role == "heading" for paragraph in block.paragraphs)


def _paragraph_heading_level(paragraph: ParagraphUnit) -> int | None:
    """The outline depth this PARAGRAPH carries, or None when it is not a heading or its level
    is missing. None means "depth unknown", never "depth 0"."""
    if paragraph.role != "heading":
        return None
    level = getattr(paragraph, "heading_level", None)
    return int(level) if isinstance(level, int) and level > 0 else None


def _block_leading_heading_level(block: DocumentBlock) -> int | None:
    """The outline depth of the block's first heading paragraph, or None when the block has
    no heading or the heading carries no level. None means "depth unknown" and is always
    treated as a section boundary, never as "deeper"."""
    for paragraph in block.paragraphs:
        if paragraph.role != "heading":
            continue
        return _paragraph_heading_level(paragraph)
    return None


def _document_top_heading_level(blocks: list[DocumentBlock]) -> int | None:
    """The shallowest outline depth that occurs anywhere in the document, or None when no
    heading carries a level at all.

    This is the depth at which this document's own top-level sections open — read off the
    document's outline, not chosen. It is used for exactly one purpose (spec 054, 2026-08-06):
    when a back-matter section title arrives carrying NO depth of its own, the region's end
    cannot be expressed relative to the title, and the only outline fact still worth anything
    is "a top-level section starts here". Rethinking Money is the case: `**NOTES**` and
    `**BIBLIOGRAPHY**` arrive as `role=body`, while its `ACKNOWLEDGEMENTS` — the author prose
    that must survive between the bibliography and the index — arrives as a level-1 heading,
    one of that book's 23.

    It is a property of the document, not a threshold and not a per-book literal, and every way
    it can be wrong makes the region SHORTER: if import flattens the outline, the top depth is
    the only depth and the first following heading closes the region; if the top depth never
    recurs after the region, nothing closes it and the caller falls back to its conservative
    bound. Leaving reference material in is the accepted outcome; cutting prose is not.
    """
    levels = [
        level
        for block in blocks
        for paragraph in block.paragraphs
        if (level := _paragraph_heading_level(paragraph)) is not None
    ]
    return min(levels) if levels else None


def _unwrap_inline_emphasis(text: str) -> str:
    """Drop a matched inline-emphasis wrapper from the WHOLE of `text`.

    The PDF import path carries emphasis inside `ParagraphUnit.text` as markdown, so a bolded
    section title arrives as `**NOTES**` and an italic one as `*Notes*` (measured on all four
    corpus books, 2026-08-06). Those markers are markup the importer synthesised, not part of
    the title; comparing them literally would make an exact title match depend on whether the
    typesetter emphasised the word. This is normalisation of our own markup, the same job
    `_strip_internal_placeholders` does for `[[DOCX_*]]`, not a matcher on the shape of the
    text: only a pair wrapping the entire string is removed, never anything from inside it, so
    a sentence can never be turned into a title.
    """
    stripped = text.strip()
    for _ in range(3):
        for marker in _INLINE_EMPHASIS_MARKERS:
            size = len(marker)
            if len(stripped) > 2 * size and stripped.startswith(marker) and stripped.endswith(marker):
                stripped = stripped[size:-size].strip()
                break
        else:
            break
    return stripped


def _reference_section_title(paragraph: ParagraphUnit, *, structure_phase: str) -> str:
    """The bare back-matter section title this PARAGRAPH is, or "".

    Exact match after normalisation — never containment. That is what keeps a front-matter
    contents row ("Notes ......... 225", which carries its page number) and a chapter heading
    that merely mentions sources from anchoring a region, exactly as
    `_resolve_references_region_start` does in the blessed precedent. A paragraph already
    tagged with a TOC structural role can never anchor, whatever it says.

    The `heading` role is deliberately NOT required. Requiring it made the rule fire zero times
    on Rethinking Money (measured 2026-08-06), whose NOTES and BIBLIOGRAPHY arrive from import
    as `role=body` while its INDEX arrives as a heading — the same three section titles, the
    same book, two different import outcomes. Constitution VII's "no source signal, no repair"
    is not in tension with this: nothing here is reconstructed from the shape of the text. The
    signal is that a paragraph's whole text IS a blessed section title; the guards that replace
    the role requirement are structural and live in `_block_reference_title_position`.
    """
    if _is_toc_structural_role(paragraph, structure_phase=structure_phase):
        return ""
    title = _normalize_structural_text(_unwrap_inline_emphasis(_strip_internal_placeholders(paragraph.text))).lower()
    return title if title in _NARRATION_REFERENCE_SECTION_TITLES else ""


def _block_reference_title_position(block: DocumentBlock, *, structure_phase: str) -> tuple[int, str] | None:
    """`(paragraph position, title)` of the one back-matter section title this block can be
    anchored on, or None. Two structural guards stand in for the dropped `heading` role:

    * **The block must carry exactly ONE such title.** A genuine section title is followed by
      its entries, so it is alone in its block; a contents list packs several of them together.
      Both corpus books whose front matter lists "Notes / Bibliography / Acknowledgements" as
      plain paragraphs are refused here — The Value of Everything block 18 carries three and
      Money & Sustainability block 14 carries two (measured 2026-08-06). This is the guard that
      matters, because on The Value of Everything those rows are NOT tagged as TOC rows.
    * **The title must sit at an edge of its block** — first or last. A section break is a
      block boundary, so a title that really opens a section is either the paragraph that opens
      the block or the one swept onto the tail of the preceding unit. A title with paragraphs
      on BOTH sides inside a single block is a line in a list, not a section opening, and it is
      refused rather than guessed at: there is no way to start a region there that neither cuts
      the prose in front of it nor is a guess.
    """
    hits = [
        (position, title)
        for position, paragraph in enumerate(block.paragraphs)
        if (title := _reference_section_title(paragraph, structure_phase=structure_phase))
    ]
    if len(hits) != 1:
        return None
    position, title = hits[0]
    if position not in {0, len(block.paragraphs) - 1}:
        return None
    return position, title


def _block_reference_section_title(block: DocumentBlock, *, structure_phase: str) -> str:
    """The bare back-matter section title this block can be anchored on, or ""."""
    hit = _block_reference_title_position(block, structure_phase=structure_phase)
    return hit[1] if hit is not None else ""


def _block_reference_region_start(blocks: list[DocumentBlock], index: int, *, structure_phase: str) -> int | None:
    """First block index of the region the block at `index` anchors, or None.

    When the title OPENS its block, the region starts at that block. When the title is the LAST
    paragraph of its block — Rethinking Money's `**NOTES**` is paragraph 7 of 8, sitting behind
    the closing paragraphs of the final chapter — the region starts at the NEXT block, so the
    chapter text in front of the title stays in the narration. The title line itself is then
    narrated, which is a spoken word or two; cutting seven paragraphs of prose to save them is
    not a trade this rule is allowed to make.
    """
    hit = _block_reference_title_position(blocks[index], structure_phase=structure_phase)
    if hit is None:
        return None
    position, _ = hit
    start_index = index if position == 0 else index + 1
    return start_index if start_index < len(blocks) else None


def _nearest_following_heading_index(blocks: list[DocumentBlock], start_index: int) -> int:
    """The first heading-bearing block after `start_index`, or `len(blocks)`. The most timid
    bound available, used only when nothing else closes the region at all."""
    index = start_index + 1
    while index < len(blocks) and not _block_has_heading_paragraph(blocks[index]):
        index += 1
    return index


def _resolve_reference_region_outline_bound(
    blocks: list[DocumentBlock],
    start_index: int,
    *,
    title_level: int | None,
    document_top_heading_level: int | None,
) -> int | None:
    """The block where the OUTLINE says this reference section ends, or None when the outline
    says nothing usable. Two cases, because the section title's own depth is the thing PDF
    import most often fails to deliver.

    **The title carries a depth.** A section runs until the outline returns to that depth or
    shallower — that is what a heading level MEANS. A following heading with NO level also
    closes it, because unknown depth is never "deeper".

    **The title carries no depth at all.** Then the region has no depth to be measured against,
    and the pre-2026-08-06 rule's answer — stop at the nearest following heading — is wrong on
    exactly the books this rule exists for: Rethinking Money's notes section is full of headings,
    because import promoted its per-chapter labels (`Chapter 2`, `Chapter 3`) to level 3, and the
    region died three blocks in. So the bound becomes the only outline fact left that is worth
    anything: **the next block that opens a section at the document's own top depth**
    (`_document_top_heading_level`). On Rethinking Money that is `# ACKNOWLEDGEMENTS`, level 1,
    standing between the bibliography and the index — author prose, and the region stops there.
    An unlevelled heading is deliberately NOT a bound in this case: when the title had no depth
    either, a heading without one carries no information about where the section ends.

    Returning None means "the outline does not close this region", which is a finding, not a
    licence to run to the end of the document — see the caller.
    """
    if title_level is None:
        if document_top_heading_level is None:
            return None
        for index in range(start_index + 1, len(blocks)):
            level = _block_leading_heading_level(blocks[index])
            if level is not None and level <= document_top_heading_level:
                return index
        return None

    for index in range(start_index + 1, len(blocks)):
        if not _block_has_heading_paragraph(blocks[index]):
            continue
        level = _block_leading_heading_level(blocks[index])
        if level is None or level <= title_level:
            return index
    return None


def _resolve_reference_region_end(
    blocks: list[DocumentBlock],
    start_index: int,
    *,
    title_level: int | None,
    document_top_heading_level: int | None,
    next_region_start: int | None,
) -> int:
    """Exclusive end of the reference section opened at `start_index`.

    Two independent bounds are taken, and the EARLIER wins:

    * **the start of the next reference section** — the strongest signal available here and the
      one that needs no heading level at all, because it is the same blessed back-matter title
      lexicon, with the same guards, that opened this region. A bibliography ends where an index
      begins. On Rethinking Money this is what carries the notes region over the 11 blocks of
      chapter labels that import turned into level-3 headings;
    * **the outline bound** (`_resolve_reference_region_outline_bound`), which is what stops a
      region at an AUTHOR section rather than at the next reference one — Rethinking Money's
      `ACKNOWLEDGEMENTS` sits between its bibliography and its index, and only the outline sees
      it. There is no lexicon of author-section titles and Constitution VII forbids inventing
      one, so the outline is the whole of that defence.

    When NEITHER closes the region, the region is not extended to the end of the document. The
    end of the document is a legitimate bound for a last reference section, but it is not
    distinguishable here from "this book keeps its author biography and its publisher's
    advertising behind the index" — which is exactly what Rethinking Money does — so the timid
    `_nearest_following_heading_index` bound stands and the residual is accepted. Every failure
    mode of this function leaves reference material in the narration; none of them cuts prose.
    """
    bounds = [bound for bound in (next_region_start, _resolve_reference_region_outline_bound(
        blocks,
        start_index,
        title_level=title_level,
        document_top_heading_level=document_top_heading_level,
    )) if bound is not None and bound > start_index]
    if bounds:
        return min(bounds)
    return _nearest_following_heading_index(blocks, start_index)


def _resolve_reference_regions(blocks: list[DocumentBlock], *, structure_phase: str = "post_ai_final") -> list[tuple[int, int]]:
    """Every back-matter reference section of the document, as `(start, end)` half-open block
    ranges, in document order.

    Resolved in two passes on purpose: all the anchors first, then the ends. The end rule needs
    to know where the NEXT reference section starts, and a single forward pass cannot tell it
    that without re-deriving the anchor it is about to walk into.
    """
    anchors: list[tuple[int, int | None]] = []
    for index in range(len(blocks)):
        start_index = _block_reference_region_start(blocks, index, structure_phase=structure_phase)
        if start_index is None:
            continue
        hit = _block_reference_title_position(blocks[index], structure_phase=structure_phase)
        title_level = _paragraph_heading_level(blocks[index].paragraphs[hit[0]]) if hit is not None else None
        anchors.append((start_index, title_level))

    document_top_heading_level = _document_top_heading_level(blocks)
    regions: list[tuple[int, int]] = []
    for order, (start_index, title_level) in enumerate(anchors):
        next_region_start = next(
            (start for start, _ in anchors[order + 1 :] if start > start_index),
            None,
        )
        end_index = _resolve_reference_region_end(
            blocks,
            start_index,
            title_level=title_level,
            document_top_heading_level=document_top_heading_level,
            next_region_start=next_region_start,
        )
        if end_index > start_index:
            regions.append((start_index, end_index))
    return regions


def _resolve_reference_region_indexes(blocks: list[DocumentBlock], *, structure_phase: str = "post_ai_final") -> set[int]:
    """Block indexes that belong to a back-matter reference section (notes / endnotes /
    references / bibliography / sources / index), for the audiobook narration to drop.

    A region STARTS where `_block_reference_region_start` anchors it on a bare back-matter
    section title and ENDS where `_resolve_reference_region_end` puts the next section
    boundary. Nothing here reads the shape of the entries.

    This replaced a bibliography-ratio test over the document suffix, which measured 0
    excluded blocks on 4 of 4 books on 2026-08-04 for two independent reasons: its anchor
    was the LAST heading-like block, which on a real book is publisher back-matter standing
    BEHIND the bibliography; and its region test required >= 70% "bibliography-like" lines,
    while a PDF-imported entry wraps over several lines of which only one carries a year,
    publisher or URL — the genuine bibliography of *The Value of Everything* scores 9-21%.
    Neither was a threshold to tune, so both are gone (Constitution VII: region and
    structural role, not the shape of the text).
    """
    excluded: set[int] = set()
    for start_index, end_index in _resolve_reference_regions(blocks, structure_phase=structure_phase):
        excluded.update(range(start_index, end_index))
    return excluded


def _resolve_narration_include(
    block: DocumentBlock,
    *,
    block_index: int,
    reference_region_indexes: set[int],
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
    if block_index in reference_region_indexes:
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
