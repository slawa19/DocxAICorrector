import re
from dataclasses import replace

from docxaicorrector.document.structure_authority import (
    get_effective_structural_role,
    normalize_structure_phase,
    phase_uses_advisory_hints,
)
from docxaicorrector.document.narration_exclusion import (
    ends_as_a_sentence,
    follows_a_sentence_end,
    quotation_and_signature,
    resolve_narration_exclusion_reason,
)
from docxaicorrector.document.relations import build_paragraph_relations, resolve_effective_relation_kinds
from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_INDEX,
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    PARAGRAPH_REGION_BACK_MATTER,
    PARAGRAPH_REGION_FRONT_MATTER,
    PARAGRAPH_REGION_PROSE,
    PARAGRAPH_REGION_TOC,
    DocumentBlock,
    ParagraphRelation,
    ParagraphUnit,
)
from docxaicorrector.pipeline.output_validation import (
    has_hard_reference_mark,
    is_notes_run_paragraph,
    note_number_spans,
    notes_run_parts,
    notes_run_piece_reads_as_reference,
)
from docxaicorrector.text.narration_cleanup import unwrap_markdown_links
from docxaicorrector.text.narration_residue import shorten_addresses_to_domain
from docxaicorrector.validation.formatting_coverage import (
    _BACKMATTER_SECTION_TITLES,
    _normalize_structural_text,
    _resolve_source_front_matter_boundary,
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

# Spec 063 FR-011 (owner decision D1): what each title of that SAME lexicon opens -- notes, a
# reference list, or an index. A partition of the blessed anchor lexicon, not a second word
# list: no title is added here, and the check below fails at import if the two ever stop
# covering each other, so a title added to the lexicon must be given a kind in the same
# change. Constitution VII's acknowledged language-coverage residual is the lexicon's, not
# this table's. Named residual (2026-11-07): an ANNOTATED reading list under "further
# reading" or "sources" carries commentary inside its entries; it is a reference list by
# its title, so its entries are kept in the source language with their annotations. None of
# the four corpus books has one -- their reference lists are all titled "Bibliography".
_BACK_MATTER_SECTION_KIND_BY_TITLE: dict[str, str] = {
    "notes": BACK_MATTER_SECTION_NOTES,
    "endnotes": BACK_MATTER_SECTION_NOTES,
    "footnotes": BACK_MATTER_SECTION_NOTES,
    "примечания": BACK_MATTER_SECTION_NOTES,
    "сноски": BACK_MATTER_SECTION_NOTES,
    "references": BACK_MATTER_SECTION_REFERENCES,
    "bibliography": BACK_MATTER_SECTION_REFERENCES,
    "sources": BACK_MATTER_SECTION_REFERENCES,
    "works cited": BACK_MATTER_SECTION_REFERENCES,
    "further reading": BACK_MATTER_SECTION_REFERENCES,
    "библиография": BACK_MATTER_SECTION_REFERENCES,
    "источники": BACK_MATTER_SECTION_REFERENCES,
    "литература": BACK_MATTER_SECTION_REFERENCES,
    "список литературы": BACK_MATTER_SECTION_REFERENCES,
    "index": BACK_MATTER_SECTION_INDEX,
    "указатель": BACK_MATTER_SECTION_INDEX,
    "именной указатель": BACK_MATTER_SECTION_INDEX,
    "предметный указатель": BACK_MATTER_SECTION_INDEX,
}
if frozenset(_BACK_MATTER_SECTION_KIND_BY_TITLE) != _NARRATION_REFERENCE_SECTION_TITLES:
    raise RuntimeError(
        "back-matter section partition is out of step with the anchor lexicon: "
        f"{sorted(frozenset(_BACK_MATTER_SECTION_KIND_BY_TITLE) ^ _NARRATION_REFERENCE_SECTION_TITLES)}"
    )

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
    # Spec 063 FR-011: which back-matter section each block of that region belongs to. The
    # same anchors, so the two can never disagree about WHICH blocks are back matter.
    back_matter_sections = _resolve_back_matter_sections(blocks, structure_phase=structure_phase)
    # Spec 059 A-II: resolved once for the whole document, because the front-matter boundary
    # is a property of the document and not of any one block.
    paragraph_regions_by_block = _resolve_paragraph_regions(
        blocks,
        reference_region_indexes=reference_region_indexes,
        structure_phase=structure_phase,
    )
    # Spec 067 FR-001: notes runs the import left in the prose region, by document POSITION
    # (the same position space as the regions above).
    flat_paragraphs = [paragraph for block in blocks for paragraph in block.paragraphs]
    flat_regions = [region for block_regions in paragraph_regions_by_block for region in block_regions]
    notes_in_body_positions = _resolve_notes_in_body_positions(
        flat_paragraphs, flat_regions, structure_phase=structure_phase
    )
    # Spec 067 FR-004: short headings of the prose region that are NAMES by the document's own
    # case count, same position space.
    name_heading_positions = _resolve_name_heading_positions(
        flat_paragraphs, flat_regions, structure_phase=structure_phase
    )
    structure_source = _semantic_block_structure_source(structure_phase)
    normalized_operation = str(processing_operation or "edit").strip().lower() or "edit"
    # Spec 070 FR-003: the audiobook decides PER PARAGRAPH what is not narrated. Resolved for the
    # whole document before any job is built, because the neighbours' decisions shape the
    # context of every block (fix-1, Codex acceptance finding 6): a paragraph that is never sent
    # to the model as a target must not reach it through ``context_before``/``context_after``
    # either. ``None`` for translate and edit -- their jobs stay byte-identical (SC-004).
    narration_reasons_by_block: list[list[str | None]] | None = None
    context_blocks = blocks
    if normalized_operation == "audiobook":
        # The narration reads the same regions, back-matter sections and notes-in-body positions
        # as the job fields every operation carries (spec 071: one detector, no second pass).
        # Spec 077: minus a chapter's opening the mark reads as a one-entry notes run (an epigraph
        # with its signature, then prose). For the narration only -- the spec 067 mark itself
        # (``notes_in_body_paragraph_ids``) is not narrowed.
        narration_notes_positions = notes_in_body_positions - _resolve_epigraph_led_note_positions(
            flat_paragraphs, notes_in_body_positions
        )
        narration_reasons_by_block = []
        position = 0
        for index, block in enumerate(blocks):
            narration_reasons_by_block.append(
                [
                    resolve_narration_exclusion_reason(
                        structural_role=_paragraph_structural_kind(paragraph, structure_phase=structure_phase),
                        paragraph_role=paragraph.role,
                        region=paragraph_regions_by_block[index][paragraph_index],
                        back_matter_section=back_matter_sections.get(index),
                        in_notes_in_body=position + paragraph_index in narration_notes_positions,
                        text=_strip_internal_placeholders(paragraph.text),
                    )
                    for paragraph_index, paragraph in enumerate(block.paragraphs)
                ]
            )
            position += len(block.paragraphs)
        # Spec 074 FR-405: the reasons above are decided on the ORIGINAL text; from here on every narrated
        # paragraph carries its links as their labels and its web addresses shortened to the domain, so the
        # request, the context, the coverage and residue source and the reading glossary all read one and the
        # same shortened source.
        source_blocks = [
            DocumentBlock(
                paragraphs=[
                    _with_addresses_shortened(paragraph) if reason is None else paragraph
                    for paragraph, reason in zip(block.paragraphs, block_reasons)
                ]
            )
            for block, block_reasons in zip(blocks, narration_reasons_by_block)
        ]
        context_blocks = [
            DocumentBlock(
                paragraphs=[
                    paragraph for paragraph, reason in zip(block.paragraphs, block_reasons) if reason is None
                ]
            )
            for block, block_reasons in zip(source_blocks, narration_reasons_by_block)
        ]
    else:
        source_blocks = blocks

    for index, block in enumerate(blocks):
        source_block = source_blocks[index]
        context_before = build_context_excerpt(context_blocks, index, context_before_chars, reverse=True)
        context_after = build_context_excerpt(context_blocks, index, context_after_chars, reverse=False)
        structural_roles = [_paragraph_structural_kind(paragraph, structure_phase=structure_phase) for paragraph in block.paragraphs]
        paragraph_count = len(block.paragraphs)
        toc_only_paragraph_count = sum(
            1 for paragraph in block.paragraphs if _is_toc_only_paragraph(paragraph, structure_phase=structure_phase)
        )
        toc_dominant = bool(paragraph_count) and (
            toc_only_paragraph_count == paragraph_count
            or (toc_only_paragraph_count / paragraph_count) >= TOC_DOMINANCE_THRESHOLD
        )
        narration_exclusion_reasons: list[str | None] | None = None
        if narration_reasons_by_block is not None:
            # Spec 070 FR-003: the audiobook decides PER PARAGRAPH, so the block is narrated when
            # at least one of its paragraphs is. Only the audiobook carries the field: the jobs
            # of translate and edit stay byte-identical (SC-004).
            narration_exclusion_reasons = narration_reasons_by_block[index]
            narration_include = any(reason is None for reason in narration_exclusion_reasons)
        else:
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
        job: dict[str, object] = {
            "job_kind": job_kind,
            "target_text": source_block.text,
            "target_text_with_markers": build_marker_wrapped_block_text(source_block.paragraphs, paragraph_ids=paragraph_ids),
            "paragraph_ids": paragraph_ids,
            "structural_roles": structural_roles,
            # Spec 059 A-II: parallel to ``paragraph_ids``, one label per paragraph.
            "paragraph_regions": paragraph_regions_by_block[index],
            # Spec 063 FR-011: ``None`` outside the back-matter region.
            "back_matter_section": back_matter_sections.get(index),
            # Spec 067 FR-001: the paragraphs of this block that are a run of notes left
            # in the body -- a per-PARAGRAPH apparatus mark; the region stays ``prose``.
            "notes_in_body_paragraph_ids": [
                paragraph_id
                for paragraph_index, paragraph_id in enumerate(paragraph_ids)
                if fallback_paragraph_index + paragraph_index in notes_in_body_positions
            ],
            # Spec 067 FR-004: the heading paragraphs of this block that are a bare name.
            "name_heading_paragraph_ids": [
                paragraph_id
                for paragraph_index, paragraph_id in enumerate(paragraph_ids)
                if fallback_paragraph_index + paragraph_index in name_heading_positions
            ],
            "narration_include": narration_include,
            "toc_dominant": toc_dominant,
            "toc_paragraph_count": toc_only_paragraph_count,
            "paragraph_count": paragraph_count,
            "context_before": context_before,
            "context_after": context_after,
            "target_chars": len(source_block.text),
            "context_chars": len(context_before) + len(context_after),
            "structure_phase": structure_phase,
            "structure_source": structure_source,
        }
        if narration_exclusion_reasons is not None:
            # Spec 070 FR-003: parallel to ``paragraph_ids``, one reason (or ``None``) per paragraph.
            job["narration_exclusion_reasons"] = narration_exclusion_reasons
        jobs.append(job)
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


def _with_addresses_shortened(paragraph: ParagraphUnit) -> ParagraphUnit:
    """Spec 074 FR-405: a copy of a narrated paragraph whose web addresses are shortened to the domain (the same
    object when there is nothing to shorten). A Markdown link ``[label](target)`` of the importer becomes its
    label first -- the narration reads the visible text, never the target (Codex acceptance review 2026-11-11,
    finding 1) -- and an address inside the label is then shortened as any other. The copy lives only inside
    ``build_editing_jobs``: the jobs carry its text, never the unit."""

    shortened = shorten_addresses_to_domain(unwrap_markdown_links(paragraph.text))
    if shortened == paragraph.text:
        return paragraph
    return replace(paragraph, text=shortened, pdf_emphasis_runs=[])


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
    return phase_uses_advisory_hints(normalized_phase)


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


def _resolve_reference_sections(
    blocks: list[DocumentBlock],
    *,
    structure_phase: str = "post_ai_final",
) -> list[tuple[int, int, str]]:
    """Every back-matter reference section of the document, as `(start, end, title)` with a
    half-open block range, in document order. `title` is the normalised anchor title that
    opened the section -- the one fact spec 063 FR-011 needs to tell notes from a reference
    list from an index, and it is the anchor itself, not a reading of the entries.

    This is the ONE back-matter detector of the document layer: the paragraph regions, the
    back-matter section kinds, the notes-in-body positions and the narration exclusions of
    every operation (translate, edit, audiobook) are all derived from it (spec 071), so the
    operations can never disagree about which blocks are back matter.

    Resolved in two passes on purpose: all the anchors first, then the ends. The end rule needs
    to know where the NEXT reference section starts, and a single forward pass cannot tell it
    that without re-deriving the anchor it is about to walk into.

    A title WITHOUT a heading level that closes its block (`_block_reference_region_start`, the
    tail case) is believed to be a section opening only when the paragraph in front of it ends
    a sentence (`narration_exclusion.ends_as_a_sentence`) -- the closing paragraph of the last
    chapter, which is what the tail case was built for. When the paragraph in front of it is an
    unfinished line -- a heading, another row -- the title is one more row of a list of section
    names: an untagged table of contents (spec 070 fix-1, Codex acceptance finding 1; moved here
    from the audiobook's own second pass by spec 071). Measured on the translated full Money:
    the last row of such a list, `**Библиография**` (role body, no level) behind `Приложения`
    and three more rows, opened a region the top-depth bound ran over 18 blocks of forewords, a
    preface and an executive summary. On translate that prose would have been treated as a
    reference list (spec 063 D1 keeps it in the source language), on the audiobook it was
    excluded from the narration. Measured 2026-11-10 on every source of the corpus registry
    (spec 071): the guard changes nothing else. Refusing an anchor leaves material out of the
    back matter -- translated and narrated -- the direction every rule of this family fails
    towards.
    """
    anchors: list[tuple[int, int | None, str]] = []
    for index in range(len(blocks)):
        start_index = _block_reference_region_start(blocks, index, structure_phase=structure_phase)
        if start_index is None:
            continue
        hit = _block_reference_title_position(blocks[index], structure_phase=structure_phase)
        title_level = _paragraph_heading_level(blocks[index].paragraphs[hit[0]]) if hit is not None else None
        if (
            hit is not None
            and title_level is None
            and hit[0] > 0
            and not ends_as_a_sentence(_strip_internal_placeholders(blocks[index].paragraphs[hit[0] - 1].text))
        ):
            continue
        anchors.append((start_index, title_level, hit[1] if hit is not None else ""))

    document_top_heading_level = _document_top_heading_level(blocks)
    sections: list[tuple[int, int, str]] = []
    for order, (start_index, title_level, title) in enumerate(anchors):
        next_region_start = next(
            (start for start, _, _ in anchors[order + 1 :] if start > start_index),
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
            sections.append((start_index, end_index, title))
    return sections


def _resolve_reference_regions(blocks: list[DocumentBlock], *, structure_phase: str = "post_ai_final") -> list[tuple[int, int]]:
    """Every back-matter reference section of the document, as `(start, end)` half-open block
    ranges, in document order. See `_resolve_reference_sections`."""
    return [
        (start_index, end_index)
        for start_index, end_index, _ in _resolve_reference_sections(blocks, structure_phase=structure_phase)
    ]


def _resolve_back_matter_sections(
    blocks: list[DocumentBlock], *, structure_phase: str = "post_ai_final"
) -> dict[int, str]:
    """Spec 063 FR-011: block index -> which back-matter SECTION it belongs to (notes, a
    reference list, an index), for every block of the back-matter region.

    The kind is the anchor title's, through `_BACK_MATTER_SECTION_KIND_BY_TITLE`. Sections never
    overlap -- each ends no later than the next one starts -- so a block has at most one kind.
    A block outside the region has none, and a region opened by a title the partition does not
    know (impossible while the import-time check below holds) gets none either: no kind means
    no policy, which is the direction that cannot keep prose in the source language.
    """
    kinds: dict[int, str] = {}
    for start_index, end_index, title in _resolve_reference_sections(blocks, structure_phase=structure_phase):
        kind = _BACK_MATTER_SECTION_KIND_BY_TITLE.get(title)
        if kind is None:
            continue
        for block_index in range(start_index, end_index):
            kinds[block_index] = kind
    return kinds


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


def _resolve_paragraph_regions(
    blocks: list[DocumentBlock],
    *,
    reference_region_indexes: set[int],
    structure_phase: str = "post_ai_final",
) -> list[list[str]]:
    """Spec 059 A-II: one REGION label per paragraph, in document order, grouped by block.

    The regions existed already; what did not exist was a way for the BLOCK EXECUTION stage
    to read them per paragraph. Back matter was known only as a set of BLOCK indexes (for the
    narration to drop), and the front-matter / TOC boundaries were resolved only downstream in
    ``validation/formatting_coverage.py``, over the source registry, AFTER generation. On a
    mixed "apparatus + prose" block there was therefore nothing to tell the two apart at the
    moment a rejected block is either substituted or failed.

    Nothing here is new detection. The back-matter region is the same
    ``_resolve_reference_region_indexes`` the audiobook narration uses; the TOC is the
    paragraph's own structural role; the front-matter boundary is
    ``_resolve_source_front_matter_boundary``, reused rather than restated -- this module
    already imports that family, and Constitution VII names it as the precedent for
    region-based detection.

    Two deliberate choices:

    * the registry is indexed by POSITION in this block list, not by ``ParagraphUnit
      .source_index``. The boundary is only ever compared against the same positions, and
      ``source_index`` is ``-1`` for paragraphs that never came from an extracted document.
    * TOC wins over front matter where both apply. A table of contents sits inside the front
      matter, so either label would be "apparatus"; the more specific one is more useful to
      the reader of a run report.

    ``_resolve_bounded_toc_region`` is NOT reused: it needs a preparation diagnostic snapshot
    that does not exist at this stage, and the paragraph's own ``toc_header``/``toc_entry``
    structural role is a stronger signal than a region bound anyway.
    """
    registry = [
        {
            "source_index": position,
            "role": paragraph.role,
            "structural_role": paragraph.structural_role,
            "text_preview": paragraph.text,
        }
        for position, paragraph in enumerate(
            paragraph for block in blocks for paragraph in block.paragraphs
        )
    ]
    # ``None`` from the resolver means "this document does not open with front matter", and
    # the conservative reading of that is that nothing is front matter -- an unresolved
    # boundary must not quietly demote the opening of a book to apparatus.
    front_matter_boundary = _resolve_source_front_matter_boundary(registry, None)

    regions: list[list[str]] = []
    position = 0
    for block_index, block in enumerate(blocks):
        block_regions: list[str] = []
        for paragraph in block.paragraphs:
            if block_index in reference_region_indexes:
                region = PARAGRAPH_REGION_BACK_MATTER
            elif _is_toc_structural_role(paragraph, structure_phase=structure_phase):
                region = PARAGRAPH_REGION_TOC
            elif front_matter_boundary is not None and position < front_matter_boundary:
                region = PARAGRAPH_REGION_FRONT_MATTER
            else:
                region = PARAGRAPH_REGION_PROSE
            block_regions.append(region)
            position += 1
        regions.append(block_regions)
    return regions


# Spec 067 FR-001: the structural roles a notes-run paragraph arrives with from import. On the
# four corpus books every one of them is ``body`` or ``list`` (Money 61 + 1); a heading, a
# caption, an image or a TOC line is never a run of notes, whatever its text looks like.
_NOTES_IN_BODY_STRUCTURAL_ROLES = frozenset({"body", "list"})


def _toc_bracketed_positions(paragraphs: list[ParagraphUnit], *, structure_phase: str) -> frozenset[int]:
    """Positions of a stretch the role detector left untyped INSIDE a table of contents.

    A stretch of consecutive paragraphs without a TOC role, holding no heading, with a TOC
    paragraph (``toc_header``/``toc_entry``) immediately before AND immediately after it, is
    part of that table of contents: a contents list is contiguous, and what interrupts it
    without a heading of its own is a stretch of its lines the detector did not type. Read off
    the ROLES around the stretch, never off its text (Constitution VII). Measured: Rethinking
    Money ``p0045``-``p0050`` (a contents line holding two entries, then single entries --
    number, title, page number; spec 067 I-3), between ``p0044`` (``toc_entry``) and
    ``p0051`` (``toc_header``) -- the only such stretch on the four books.
    """
    toc_flags = [_is_toc_structural_role(paragraph, structure_phase=structure_phase) for paragraph in paragraphs]
    bracketed: set[int] = set()
    position = 0
    while position < len(paragraphs):
        if toc_flags[position]:
            position += 1
            continue
        end = position
        while end < len(paragraphs) and not toc_flags[end]:
            end += 1
        stretch = range(position, end)
        if (
            position > 0
            and end < len(paragraphs)
            and not any(
                _paragraph_structural_kind(paragraphs[member], structure_phase=structure_phase) == "heading"
                or str(paragraphs[member].role or "").strip().casefold() == "heading"
                for member in stretch
            )
        ):
            bracketed.update(stretch)
        position = end
    return frozenset(bracketed)


def _resolve_notes_in_body_positions(
    paragraphs: list[ParagraphUnit],
    regions: list[str],
    *,
    structure_phase: str = "post_ai_final",
) -> frozenset[int]:
    """Spec 067 FR-001: which paragraphs of the PROSE region are a run of notes by their form.

    Three conditions, all of them read off the document, none off a word list:

    * the paragraph lies in the prose region -- the back-matter region already carries the
      apparatus policy, and front matter and the TOC are not body;
    * its structural role is an entry role (``_NOTES_IN_BODY_STRUCTURAL_ROLES``) and it does not
      sit inside a table of contents the role detector left untyped
      (``_toc_bracketed_positions``);
    * its text is a notes run by form (``output_validation.is_notes_run_paragraph``).

    The answer marks the PARAGRAPH, not the book's regions: relabelling these paragraphs
    ``back_matter`` would also move them out of the narration, the glossary's source units and
    the formatting-coverage regions, none of which spec 067 asks for. The apparatus consumers
    read the mark (``block_execution.notes_in_body_paragraph_indexes``).
    """
    if len(regions) != len(paragraphs):
        return frozenset()
    bracketed = _toc_bracketed_positions(paragraphs, structure_phase=structure_phase)
    return frozenset(
        position
        for position, paragraph in enumerate(paragraphs)
        if regions[position] == PARAGRAPH_REGION_PROSE
        and position not in bracketed
        and _paragraph_structural_kind(paragraph, structure_phase=structure_phase) in _NOTES_IN_BODY_STRUCTURAL_ROLES
        and is_notes_run_paragraph(paragraph.text)
    )


def _resolve_epigraph_led_note_positions(
    paragraphs: list[ParagraphUnit],
    notes_in_body_positions: frozenset[int],
) -> frozenset[int]:
    """Spec 077: paragraphs the spec 067 mark calls a notes run that are a chapter's OPENING -- an
    epigraph with its attribution, a stray note number, then the author's prose. NARRATION ONLY:
    the mark itself (``notes_in_body_paragraph_ids``) and what translate and edit read stay as they
    were; the audiobook narrates these paragraphs.

    A marked paragraph is returned when ALL hold, read off the form (Constitution VII):

    * its notes run has exactly ONE numbered entry (``output_validation.notes_run_parts``), and
      that entry holds no further ENTRY OPENER -- a note number by the 067 form standing right
      after a sentence end (``output_validation.note_number_spans``,
      ``narration_exclusion.follows_a_sentence_end``). A chain counts consecutive numbers only, so
      the entries of a run numbered 1, 3, 5, ... all hide inside a "chain of one" (Codex
      acceptance review of spec 077, round 2, finding 3: 100 notes, 17 108 characters, narrated);
    * that entry does NOT read as a reference by the spec 067 per-piece form
      (``notes_run_piece_reads_as_reference``) -- it is prose;
    * its lead is a quotation with a signature (``narration_exclusion.quotation_and_signature``:
      a sentence, a dash between spaces, a signature with a letter);
    * the signature carries no hard reference mark (``output_validation.has_hard_reference_mark``:
      no year in brackets, no locator, no address) -- an attribution names a person, a
      bibliographic lead names a work and where to find it.
    """
    exempt: set[int] = set()
    for position in sorted(notes_in_body_positions):
        if position >= len(paragraphs):
            continue
        parts = notes_run_parts(_strip_internal_placeholders(paragraphs[position].text))
        if parts is None:
            continue
        lead, entries = parts
        if len(entries) != 1:
            continue
        entry = entries[0]
        if any(follows_a_sentence_end(entry, start) for _, start in note_number_spans(entry)):
            continue
        if notes_run_piece_reads_as_reference(entry):
            continue
        split = quotation_and_signature(lead)
        if split is None or has_hard_reference_mark(split[1]):
            continue
        exempt.add(position)
    return frozenset(exempt)


# Spec 067 FR-004 (A-4): a heading that is a bare NAME (a publisher's name) is right when
# the model returns it unchanged, and until now the pair rule called that untranslated prose and
# failed the book's acceptance (Creating Wealth, fourth run, block 434). The form, read off the
# heading and the document, never off a word list (Constitution VII):
#
# * SHAPE: 1-6 words with a letter, at least one of two letters or more; no sentence punctuation
#   anywhere (``. ! ? ;`` and the ellipsis) and no trailing ``:`` or ``,``; every word starts
#   with an uppercase letter, except a connector of at most three lowercase letters that is not
#   the first word ("Port of Kelbrook");
# * NAME, by the document's own count, two halves:
#   - at least one capitalised word of two letters or more, not written all in capitals, never
#     occurs LOWERCASE in the document's body (the prose region's body and list paragraphs) --
#     the case test ``text.glossary_pass`` applies to ``capitalised_form``, at its strict end.
#     An all-capitals word is not evidence either way: a roman numeral ("Chapter II") and an
#     acronym never occur lowercase in any book;
#   - the heading's whole phrase occurs, with the same capitals, in the MIDDLE of a sentence of
#     a non-heading paragraph ("The staff at Harbourline Press have been ...") -- the author
#     writes it as a name in running text.
#   "Introduction", "Chapter Five", "Benefits of the Fenwick System" fail one half or the other.
#
# Measured on the fourth run (2026-11-08), prose-region headings of the four books: the first
# half alone admits 8 / 6 / 12 / 39 headings (Money / VoE / RM / CW) -- ordinary titles with one
# name in them; with the second half, 1 / 0 / 1 / 5, every one a name (a person, a pair of
# authors, a local currency, a publisher), no chapter title.
_NAME_HEADING_MAX_WORDS = 6
_NAME_HEADING_CONNECTOR_MAX_LETTERS = 3
_NAME_HEADING_SENTENCE_PUNCTUATION = re.compile(r"[.!?;…]")
_NAME_HEADING_MARKUP = re.compile(r"^\s*#{1,6}\s+|[*_`]+")
_WORD_PATTERN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
_NAME_HEADING_BODY_ROLES = frozenset({"body", "list"})
_SENTENCE_BOUNDARY_CHARACTERS = ".!?:;"


def _plain_text(text: str) -> str:
    return " ".join(_NAME_HEADING_MARKUP.sub("", str(text or "")).split())


def _lowercase_body_words(
    paragraphs: list[ParagraphUnit], regions: list[str], *, structure_phase: str
) -> frozenset[str]:
    """Every word the document's body writes with a lowercase first letter, as written."""
    words: set[str] = set()
    for position, paragraph in enumerate(paragraphs):
        if regions[position] != PARAGRAPH_REGION_PROSE:
            continue
        if _paragraph_structural_kind(paragraph, structure_phase=structure_phase) not in _NAME_HEADING_BODY_ROLES:
            continue
        words.update(word for word in _WORD_PATTERN.findall(str(paragraph.text or "")) if word[0].islower())
    return frozenset(words)


def name_heading_words(text: str) -> tuple[str, ...] | None:
    """The words of a heading of the name SHAPE that can carry the name signal -- capitalised,
    two letters or more, not all in capitals -- or ``None`` when the heading has another shape or
    no such word (see the note above). The NAME halves need the document; the caller applies them.
    """
    cleaned = _plain_text(text)
    if not cleaned or _NAME_HEADING_SENTENCE_PUNCTUATION.search(cleaned) or cleaned[-1] in ":,":
        return None
    tokens = [token for token in cleaned.split() if any(char.isalpha() for char in token)]
    if not 1 <= len(tokens) <= _NAME_HEADING_MAX_WORDS:
        return None
    candidates: list[str] = []
    for order, token in enumerate(tokens):
        letters = "".join(char for char in token if char.isalpha())
        if letters[0].isupper():
            candidates.extend(
                word
                for word in _WORD_PATTERN.findall(token)
                if len(word) >= 2 and word[0].isupper() and not word.isupper()
            )
            continue
        if order > 0 and len(letters) <= _NAME_HEADING_CONNECTOR_MAX_LETTERS and letters.islower():
            continue
        return None
    return tuple(candidates) if candidates else None


def _phrase_occurs_mid_sentence(phrase: str, texts: list[str]) -> bool:
    """Does ``phrase`` occur, same capitals, after a word of the same sentence in one of ``texts``?

    As a WHOLE phrase: no letter or digit touches it on either side. A substring is not an
    occurrence -- "Trade" inside "TradeLink" is a different word (Codex acceptance review
    2026-11-08, P0). The lowercase half (``_lowercase_body_words``) is already whole-word: it
    compares tokens of ``_WORD_PATTERN``, never substrings.
    """
    pattern = re.compile(rf"(?<![^\W_]){re.escape(phrase)}(?![^\W_])")
    for text in texts:
        for match in pattern.finditer(text):
            before = text[: match.start()].rstrip()
            if any(char.isalpha() for char in before) and before[-1] not in _SENTENCE_BOUNDARY_CHARACTERS:
                return True
    return False


def _resolve_name_heading_positions(
    paragraphs: list[ParagraphUnit],
    regions: list[str],
    *,
    structure_phase: str = "post_ai_final",
) -> frozenset[int]:
    """Spec 067 FR-004: which HEADING paragraphs of the prose region are a bare name.

    Role and form, both: the paragraph's structural role is ``heading``, it lies in the prose
    region (front matter, the TOC and the back matter are not prose and are never announced as
    untranslated prose), its text has the name shape (``name_heading_words``), at least one of
    its name-signal words never occurs lowercase in the document's body, and the whole heading
    occurs mid-sentence in a non-heading paragraph (see the note above).
    """
    if len(regions) != len(paragraphs):
        return frozenset()
    lowercase_words: frozenset[str] | None = None
    running_texts: list[str] | None = None
    positions: set[int] = set()
    for position, paragraph in enumerate(paragraphs):
        if regions[position] != PARAGRAPH_REGION_PROSE:
            continue
        if _paragraph_structural_kind(paragraph, structure_phase=structure_phase) != "heading":
            continue
        words = name_heading_words(paragraph.text)
        if words is None:
            continue
        if lowercase_words is None or running_texts is None:
            lowercase_words = _lowercase_body_words(paragraphs, regions, structure_phase=structure_phase)
            running_texts = [
                _plain_text(other.text)
                for other in paragraphs
                if _paragraph_structural_kind(other, structure_phase=structure_phase) != "heading"
                and str(other.role or "").strip().casefold() != "heading"
            ]
        if not any(word.lower() not in lowercase_words for word in words):
            continue
        if _phrase_occurs_mid_sentence(_plain_text(paragraph.text), running_texts):
            positions.add(position)
    return frozenset(positions)


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
