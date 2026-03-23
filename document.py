import html
import re
import zipfile
from io import BytesIO
from typing import cast

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
import lxml.etree as etree

from constants import (
    MAX_DOCX_ARCHIVE_SIZE_BYTES,
    MAX_DOCX_COMPRESSION_RATIO,
    MAX_DOCX_ENTRY_COUNT,
    MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
)
from models import DocumentBlock, ImageAsset, ParagraphUnit
from processing_runtime import normalize_uploaded_document, read_uploaded_file_bytes, resolve_uploaded_filename

IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_img_\d+\]\]")
PARAGRAPH_MARKER_PATTERN = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]")
IMAGE_ONLY_PATTERN = re.compile(r"^(?:\s*\[\[DOCX_IMAGE_img_\d+\]\]\s*)+$")
CAPTION_PREFIX_PATTERN = re.compile(r"^(?:рис\.?|рисунок|figure|fig\.?|табл\.?|таблица|table)\b", re.IGNORECASE)
HEADING_STYLE_PATTERN = re.compile(r"^(?:heading|заголовок)\s*(\d+)?$", re.IGNORECASE)
COMPARE_ALL_VARIANT_LABELS = {
    "safe": "Вариант 1: Просто улучшить",
    "semantic_redraw_direct": "Вариант 2: Креативная AI-перерисовка",
    "semantic_redraw_structured": "Вариант 3: Структурная AI-перерисовка",
}
MANUAL_REVIEW_SAFE_LABEL = "safe"
PRESERVED_PARAGRAPH_PROPERTY_NAMES = {
    "adjustRightInd",
    "bidi",
    "contextualSpacing",
    "ind",
    "jc",
    "keepLines",
    "keepNext",
    "mirrorIndents",
    "numPr",
    "outlineLvl",
    "pStyle",
    "pageBreakBefore",
    "rPr",
    "spacing",
    "suppressAutoHyphens",
    "tabs",
    "textAlignment",
    "textDirection",
    "widowControl",
}
RELATIONSHIP_NAMESPACE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ORDERED_LIST_FORMATS = {
    "aiueo",
    "cardinalText",
    "chicago",
    "decimal",
    "decimalEnclosedCircle",
    "decimalEnclosedFullstop",
    "decimalEnclosedParen",
    "decimalFullWidth",
    "decimalFullWidth2",
    "decimalHalfWidth",
    "ganada",
    "hebrew1",
    "hebrew2",
    "hindiConsonants",
    "hindiCounting",
    "hindiNumbers",
    "hindiVowels",
    "ideographDigital",
    "ideographEnclosedCircle",
    "ideographLegalTraditional",
    "ideographTraditional",
    "iroha",
    "japaneseCounting",
    "japaneseDigitalTenThousand",
    "japaneseLegal",
    "koreanCounting",
    "koreanDigital",
    "koreanDigital2",
    "koreanLegal",
    "lowerLetter",
    "lowerRoman",
    "numberInDash",
    "ordinal",
    "ordinalText",
    "russianLower",
    "russianUpper",
    "taiwaneseCounting",
    "taiwaneseCountingThousand",
    "taiwaneseDigital",
    "thaiCounting",
    "thaiLetters",
    "thaiNumbers",
    "upperLetter",
    "upperRoman",
    "vietnameseCounting",
}
UNORDERED_LIST_FORMATS = {"bullet", "none"}
INLINE_HTML_TAG_PATTERN = re.compile(r"</?(?:u|sup|sub)>", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")


def classify_paragraph_role(text: str, style_name: str, *, heading_level: int | None = None) -> str:
    normalized_style = style_name.strip().lower()
    stripped_text = text.lstrip()

    if _is_image_only_text(text):
        return "image"

    if heading_level is not None:
        return "heading"

    if _is_caption_style(normalized_style):
        return "caption"

    if "list" in normalized_style or "спис" in normalized_style:
        return "list"

    if stripped_text.startswith(("- ", "* ", "• ", "— ")):
        return "list"

    if re.match(r"^\d+[\.)]\s+", stripped_text):
        return "list"

    return "body"


def _infer_role_confidence(
    *,
    role: str,
    text: str,
    normalized_style: str,
    explicit_heading_level: int | None,
    heading_source: str | None,
) -> str:
    if role in {"image", "table"}:
        return "explicit"
    if role == "heading":
        return "explicit" if explicit_heading_level is not None or heading_source == "explicit" else "heuristic"
    if role == "caption":
        return "explicit" if _is_caption_style(normalized_style) else "heuristic"
    if role == "list":
        if "list" in normalized_style or "спис" in normalized_style or _detect_explicit_list_kind(text) is not None:
            return "explicit"
    return "heuristic"


def _assign_paragraph_identity(paragraph: ParagraphUnit, source_index: int) -> None:
    paragraph.source_index = source_index
    paragraph.paragraph_id = f"p{source_index:04d}"
    if not paragraph.structural_role or paragraph.structural_role == "body":
        paragraph.structural_role = paragraph.role


def extract_paragraph_units_from_docx(uploaded_file) -> list[ParagraphUnit]:
    paragraphs, _ = extract_document_content_from_docx(uploaded_file)
    return paragraphs


def extract_inline_images(uploaded_file) -> list[ImageAsset]:
    _, image_assets = extract_document_content_from_docx(uploaded_file)
    return image_assets


def extract_document_content_from_docx(uploaded_file) -> tuple[list[ParagraphUnit], list[ImageAsset]]:
    source_bytes = _read_uploaded_docx_bytes(uploaded_file)
    validate_docx_source_bytes(source_bytes)
    document = Document(BytesIO(source_bytes))
    paragraphs: list[ParagraphUnit] = []
    source_paragraphs: list[Paragraph | None] = []
    image_assets: list[ImageAsset] = []
    table_count = 0

    for block_kind, block in _iter_document_block_items(document):
        if block_kind == "paragraph":
            source_paragraph = cast(Paragraph, block)
            paragraph_unit = _build_paragraph_unit(source_paragraph, image_assets)
        else:
            source_paragraph = None
            table_count += 1
            paragraph_unit = _build_table_unit(cast(Table, block), image_assets, asset_id=f"table_{table_count:03d}")
        if paragraph_unit is not None:
            _assign_paragraph_identity(paragraph_unit, len(paragraphs))
            paragraphs.append(paragraph_unit)
            source_paragraphs.append(source_paragraph)

    _reclassify_adjacent_captions(paragraphs)
    _promote_short_standalone_headings(paragraphs, source_paragraphs)

    if not paragraphs:
        raise ValueError("В документе не найден текст для обработки.")
    return paragraphs, image_assets


def build_document_text(paragraphs: list[ParagraphUnit]) -> str:
    return "\n\n".join(paragraph.rendered_text for paragraph in paragraphs).strip()


def _resolve_marker_paragraph_id(paragraph: ParagraphUnit, fallback_index: int) -> str:
    if paragraph.paragraph_id:
        return paragraph.paragraph_id
    if paragraph.source_index >= 0:
        return f"p{paragraph.source_index:04d}"
    return f"p{fallback_index:04d}"


def build_marker_wrapped_block_text(paragraphs: list[ParagraphUnit], *, paragraph_ids: list[str] | None = None) -> str:
    parts: list[str] = []
    for index, paragraph in enumerate(paragraphs):
        paragraph_id = paragraph_ids[index] if paragraph_ids is not None else _resolve_marker_paragraph_id(paragraph, index)
        parts.append(f"[[DOCX_PARA_{paragraph_id}]]\n{paragraph.rendered_text}")
    return "\n\n".join(parts).strip()


def inspect_placeholder_integrity(markdown_text: str, image_assets: list[ImageAsset]) -> dict[str, str]:
    status_map: dict[str, str] = {}
    expected_placeholders = {asset.placeholder for asset in image_assets}
    for asset in image_assets:
        occurrence_count = markdown_text.count(asset.placeholder)
        if occurrence_count == 1:
            status_map[asset.image_id] = "ok"
        elif occurrence_count == 0:
            status_map[asset.image_id] = "lost"
        else:
            status_map[asset.image_id] = "duplicated"
    for unexpected_placeholder in sorted(set(IMAGE_PLACEHOLDER_PATTERN.findall(markdown_text)) - expected_placeholders):
        status_map[f"unexpected:{unexpected_placeholder}"] = "unexpected"
    return status_map


def build_semantic_blocks(paragraphs: list[ParagraphUnit], max_chars: int = 6000) -> list[DocumentBlock]:
    if not paragraphs:
        return []

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

    def append_paragraph(paragraph: ParagraphUnit) -> None:
        nonlocal current_size
        separator_size = 2 if current else 0
        current.append(paragraph)
        current_size += separator_size + len(paragraph.rendered_text)

    for paragraph in paragraphs:
        if not current:
            append_paragraph(paragraph)
            continue

        current_contains_atomic_block = any(item.role in {"image", "table"} for item in current)
        if current_contains_atomic_block:
            if current[-1].role in {"image", "table"} and paragraph.role == "caption":
                append_paragraph(paragraph)
                continue
            flush_current()
            append_paragraph(paragraph)
            continue

        if paragraph.role in {"image", "table"}:
            flush_current()
            append_paragraph(paragraph)
            continue

        projected_size = current_size + 2 + len(paragraph.rendered_text)
        current_all_headings = all(item.role == "heading" for item in current)
        current_is_list = all(item.role == "list" for item in current)

        if paragraph.role == "heading":
            if current_all_headings:
                append_paragraph(paragraph)
                continue
            flush_current()
            append_paragraph(paragraph)
            continue

        if current_all_headings:
            append_paragraph(paragraph)
            continue

        if current[-1].role == "heading" and paragraph.role == "caption":
            append_paragraph(paragraph)
            continue

        if current_is_list and paragraph.role == "list":
            if projected_size <= max_chars or current_size < soft_limit:
                append_paragraph(paragraph)
            else:
                flush_current()
                append_paragraph(paragraph)
            continue

        if current_is_list and paragraph.role != "list":
            if current_size >= max(600, soft_limit // 2) or len(current) > 1:
                flush_current()
                append_paragraph(paragraph)
                continue

        if projected_size <= max_chars and current_size < soft_limit:
            append_paragraph(paragraph)
            continue

        if projected_size <= max_chars and len(paragraph.rendered_text) <= max(500, max_chars // 4) and current_size < int(max_chars * 0.9):
            append_paragraph(paragraph)
            continue

        flush_current()
        append_paragraph(paragraph)

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


def build_editing_jobs(blocks: list[DocumentBlock], max_chars: int) -> list[dict[str, object]]:
    context_before_chars = max(600, min(1400, int(max_chars * 0.2)))
    context_after_chars = max(300, min(800, int(max_chars * 0.12)))
    jobs: list[dict[str, object]] = []
    fallback_paragraph_index = 0

    for index, block in enumerate(blocks):
        context_before = build_context_excerpt(blocks, index, context_before_chars, reverse=True)
        context_after = build_context_excerpt(blocks, index, context_after_chars, reverse=False)
        job_kind = "passthrough" if block.paragraphs and all(paragraph.role == "image" for paragraph in block.paragraphs) else "llm"
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
                "context_before": context_before,
                "context_after": context_after,
                "target_chars": len(block.text),
                "context_chars": len(context_before) + len(context_after),
            }
        )
        fallback_paragraph_index += len(block.paragraphs)

    return jobs


def _build_paragraph_text_with_placeholders(paragraph, image_assets: list[ImageAsset]) -> str:
    parts: list[str] = []
    for child in paragraph._element:
        local_name = _xml_local_name(child.tag)
        if local_name == "r":
            parts.append(_render_run_element(child, paragraph.part, image_assets))
            continue
        if local_name == "hyperlink":
            parts.append(_render_hyperlink_element(child, paragraph, image_assets))
    return "".join(parts)


def _build_paragraph_unit(paragraph, image_assets: list[ImageAsset]) -> ParagraphUnit | None:
    text = _build_paragraph_text_with_placeholders(paragraph, image_assets).strip()
    if not text:
        return None

    style_name = paragraph.style.name if paragraph.style and paragraph.style.name else ""
    normalized_style = style_name.strip().lower()
    explicit_heading_level = _extract_explicit_heading_level(paragraph, style_name)
    heading_level = explicit_heading_level
    heading_source = "explicit" if explicit_heading_level is not None else None
    if heading_level is None and not _is_caption_style(normalized_style):
        if _is_probable_heading(paragraph, text, normalized_style):
            heading_level = _infer_heuristic_heading_level(text)
            heading_source = "heuristic"
    role = classify_paragraph_role(text, style_name, heading_level=heading_level)
    list_metadata = _extract_paragraph_list_metadata(paragraph, text, style_name, role)
    if role != "list" and list_metadata["list_kind"] is not None:
        role = "list"
    asset_id = _extract_paragraph_asset_id(text, role=role)
    role_confidence = _infer_role_confidence(
        role=role,
        text=text,
        normalized_style=normalized_style,
        explicit_heading_level=explicit_heading_level,
        heading_source=heading_source,
    )
    return ParagraphUnit(
        text=text,
        role=role,
        asset_id=asset_id,
        heading_level=heading_level,
        heading_source=heading_source,
        list_kind=cast(str | None, list_metadata["list_kind"]),
        list_level=cast(int, list_metadata["list_level"]),
        list_numbering_format=cast(str | None, list_metadata["list_numbering_format"]),
        list_num_id=cast(str | None, list_metadata["list_num_id"]),
        list_abstract_num_id=cast(str | None, list_metadata["list_abstract_num_id"]),
        list_num_xml=cast(str | None, list_metadata["list_num_xml"]),
        list_abstract_num_xml=cast(str | None, list_metadata["list_abstract_num_xml"]),
        preserved_ppr_xml=_capture_preserved_paragraph_properties(paragraph),
        structural_role=role,
        role_confidence=role_confidence,
    )


def _build_table_unit(table: Table, image_assets: list[ImageAsset], *, asset_id: str) -> ParagraphUnit | None:
    html_table = _render_table_html(table, image_assets)
    if not html_table.strip():
        return None
    return ParagraphUnit(
        text=html_table,
        role="table",
        asset_id=asset_id,
        structural_role="table",
        role_confidence="explicit",
    )


def _iter_document_block_items(document):
    for child in document.element.body.iterchildren():
        local_name = _xml_local_name(child.tag)
        if local_name == "p":
            yield "paragraph", Paragraph(child, document)
        elif local_name == "tbl":
            yield "table", Table(child, document)


def _render_table_html(table: Table, image_assets: list[ImageAsset]) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        rendered_row = [_render_table_cell(cell, image_assets) for cell in row.cells]
        rows.append(rendered_row)

    if not any(any(cell.strip() for cell in row) for row in rows):
        return ""

    has_header = len(rows) > 1 and all(cell.strip() for cell in rows[0])
    lines = ["<table>"]
    if has_header:
        lines.append("<thead>")
        lines.append(_render_table_html_row(rows[0], cell_tag="th"))
        lines.append("</thead>")
        body_rows = rows[1:]
    else:
        body_rows = rows

    lines.append("<tbody>")
    for row in body_rows:
        lines.append(_render_table_html_row(row, cell_tag="td"))
    lines.append("</tbody>")
    lines.append("</table>")
    return "\n".join(lines)


def _render_table_cell(cell, image_assets: list[ImageAsset]) -> str:
    cell_parts: list[str] = []
    for paragraph in cell.paragraphs:
        text = _build_paragraph_text_with_placeholders(paragraph, image_assets).strip()
        if text:
            cell_parts.append(_escape_html_preserving_breaks(text))
    return "<br/>".join(cell_parts)


def _render_table_html_row(cells: list[str], *, cell_tag: str) -> str:
    rendered_cells = "".join(f"<{cell_tag}>{cell or '&nbsp;'}</{cell_tag}>" for cell in cells)
    return f"<tr>{rendered_cells}</tr>"


def _escape_html_preserving_breaks(text: str) -> str:
    return "<br/>".join(html.escape(part, quote=False) for part in text.split("<br/>"))


def _extract_run_images(run) -> list[tuple[bytes, str | None, int | None, int | None]]:
    return _extract_run_element_images(run._element, run.part)


def _extract_run_element_images(run_element, part) -> list[tuple[bytes, str | None, int | None, int | None]]:
    images: list[tuple[bytes, str | None, int | None, int | None]] = []
    for drawing in run_element.xpath(".//w:drawing"):
        blips = drawing.xpath(".//a:blip")
        width_emu, height_emu = _resolve_drawing_extent_emu(drawing)
        for blip in blips:
            embed_id = blip.get(f"{{{RELATIONSHIP_NAMESPACE}}}embed")
            if not embed_id:
                continue
            image_part = part.related_parts.get(embed_id)
            if image_part is None:
                continue
            images.append((image_part.blob, getattr(image_part, "content_type", None), width_emu, height_emu))
    return images


def _resolve_drawing_extent_emu(drawing) -> tuple[int | None, int | None]:
    extents = drawing.xpath(".//wp:extent")
    if not extents:
        return None, None

    extent = extents[0]
    try:
        width_emu = int(extent.get("cx"))
        height_emu = int(extent.get("cy"))
    except (TypeError, ValueError):
        return None, None

    if width_emu <= 0 or height_emu <= 0:
        return None, None
    return width_emu, height_emu


def _xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_uploaded_docx_bytes(uploaded_file) -> bytes:
    try:
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    except ValueError as exc:
        raise ValueError("Не удалось прочитать содержимое DOCX-файла.") from exc
    normalized_document = normalize_uploaded_document(
        filename=resolve_uploaded_filename(uploaded_file),
        source_bytes=source_bytes,
    )
    return normalized_document.content_bytes


def _capture_preserved_paragraph_properties(paragraph) -> tuple[str, ...]:
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    if paragraph_properties is None:
        return ()

    preserved_children: list[str] = []
    for child in paragraph_properties:
        if _xml_local_name(child.tag) not in PRESERVED_PARAGRAPH_PROPERTY_NAMES:
            continue
        preserved_children.append(etree.tostring(child, encoding="unicode"))
    return tuple(preserved_children)


def _extract_explicit_heading_level(paragraph, style_name: str) -> int | None:
    normalized_style = style_name.strip().lower()
    if normalized_style == "title":
        return 1
    if normalized_style == "subtitle":
        return 2

    style_match = HEADING_STYLE_PATTERN.match(normalized_style)
    if style_match is not None:
        level_text = style_match.group(1)
        if level_text:
            try:
                return max(1, min(int(level_text), 6))
            except ValueError:
                return 1
        return 1

    outline_level = _resolve_paragraph_outline_level(paragraph)
    if outline_level is not None:
        return outline_level
    return None


def _resolve_paragraph_outline_level(paragraph) -> int | None:
    outline_element = _find_paragraph_property_element(paragraph, "outlineLvl")
    outline_value = _get_xml_attribute(outline_element, "val") if outline_element is not None else None
    try:
        if outline_value is None:
            return None
        return max(1, min(int(outline_value) + 1, 6))
    except (TypeError, ValueError):
        return None


def _find_paragraph_property_element(paragraph, local_name: str):
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    element = _find_child_element(paragraph_properties, local_name)
    if element is not None:
        return element

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = _find_child_element(getattr(style, "_element", None), "pPr")
        element = _find_child_element(style_properties, local_name)
        if element is not None:
            return element
        style = getattr(style, "base_style", None)
    return None


def _resolve_paragraph_alignment(paragraph) -> str | None:
    alignment = _find_paragraph_property_element(paragraph, "jc")
    return _get_xml_attribute(alignment, "val") if alignment is not None else None


def _normalize_text_for_heading_heuristics(text: str) -> str:
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", text)
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("**", "").replace("*", "")
    return normalized.strip()


def _infer_heuristic_heading_level(text: str) -> int:
    normalized_text = _normalize_text_for_heading_heuristics(text)
    lower_text = normalized_text.lower()

    if re.match(r"^(?:глава|часть|chapter|part|appendix|приложение)\b", lower_text):
        return 1
    if re.match(r"^(?:раздел|section)\b", lower_text):
        return 2

    numeric_match = re.match(r"^(\d+(?:\.\d+){0,4})(?:[\):]|\s)", normalized_text)
    if numeric_match is not None:
        return min(numeric_match.group(1).count(".") + 2, 6)

    return 2


def _is_probable_heading(paragraph, text: str, normalized_style: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    if not stripped_text or len(stripped_text) > 140:
        return False
    word_count = len(stripped_text.split())
    if word_count > 18:
        return False
    if stripped_text.endswith(".") and word_count > 4:
        return False
    if stripped_text.count(".") > 1:
        return False
    has_strong_format = _paragraph_has_strong_heading_format(paragraph)
    if normalized_style in {"body text", "normal"} and not has_strong_format:
        return False
    if not has_strong_format:
        return False
    if _is_caption_style(normalized_style):
        return False
    resolved_alignment = _resolve_paragraph_alignment(paragraph)
    if word_count <= 8 and len(stripped_text) <= 100:
        if resolved_alignment == "center" and word_count > 2 and not _has_heading_text_signal(stripped_text):
            return False
        return _has_heading_text_signal(stripped_text) or resolved_alignment == "center"
    return _has_heading_text_signal(stripped_text)


def _has_heading_text_signal(text: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    word_count = len(stripped_text.split())
    lower_text = stripped_text.lower()

    if re.match(r"^(?:глава|раздел|часть|приложение|chapter|section|appendix)\b", lower_text):
        return True
    if re.match(r"^\d+(?:\.\d+){0,4}(?:[\):]|\s)", stripped_text):
        return True
    if ":" in stripped_text and word_count <= 12 and not stripped_text.endswith("."):
        return True
    return False


def _paragraph_has_strong_heading_format(paragraph) -> bool:
    alignment_value = _resolve_paragraph_alignment(paragraph)
    if alignment_value == "center":
        return True

    visible_runs = [run for run in paragraph.runs if run.text and run.text.strip()]
    if not visible_runs:
        return False

    bold_runs = [run for run in visible_runs if bool(run.bold)]
    if len(bold_runs) == len(visible_runs):
        return True

    visible_chars = sum(len(run.text.strip()) for run in visible_runs)
    bold_chars = sum(len(run.text.strip()) for run in bold_runs)
    return bool(bold_runs) and visible_chars > 0 and (bold_chars / visible_chars) >= 0.5


def _is_image_only_text(text: str) -> bool:
    return IMAGE_ONLY_PATTERN.fullmatch(text.strip()) is not None


def _extract_paragraph_asset_id(text: str, *, role: str) -> str | None:
    if role != "image":
        return None
    placeholders = IMAGE_PLACEHOLDER_PATTERN.findall(text)
    if len(placeholders) != 1:
        return None
    placeholder = placeholders[0]
    match = re.match(r"\[\[DOCX_IMAGE_(img_\d+)\]\]", placeholder)
    if match is None:
        return None
    return match.group(1)


def _is_caption_style(normalized_style: str) -> bool:
    return normalized_style in {"caption", "подпись"} or "caption" in normalized_style or "подпись" in normalized_style


def _is_likely_caption_text(text: str) -> bool:
    stripped_text = text.strip()
    if not stripped_text or len(stripped_text) > 140:
        return False
    return CAPTION_PREFIX_PATTERN.match(stripped_text) is not None


def _is_short_standalone_heading_text(text: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    if not stripped_text or len(stripped_text) > 80:
        return False
    if _is_likely_caption_text(stripped_text):
        return False
    word_count = len(stripped_text.split())
    if word_count == 0 or word_count > 6:
        return False
    if stripped_text.endswith((".", "?", "!", ";")):
        return False
    if stripped_text.count(".") > 0:
        return False
    return True


def _is_very_short_standalone_heading_text(text: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    if not _is_short_standalone_heading_text(stripped_text):
        return False
    word_count = len(stripped_text.split())
    return word_count <= 4 and len(stripped_text) <= 48


def _has_body_context_signal(text: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    word_count = len(stripped_text.split())
    if word_count >= 8:
        return True
    if len(stripped_text) >= 60:
        return True
    return any(marker in stripped_text for marker in (",", ":")) and word_count >= 5


def _length_to_points(length) -> float | None:
    if length is None:
        return None
    points = getattr(length, "pt", None)
    if points is None:
        return None
    try:
        return float(points)
    except (TypeError, ValueError):
        return None


def _resolve_style_font_size(style) -> float | None:
    while style is not None:
        font = getattr(style, "font", None)
        points = _length_to_points(getattr(font, "size", None))
        if points is not None:
            return points
        style = getattr(style, "base_style", None)
    return None


def _resolve_effective_paragraph_font_size(paragraph) -> float | None:
    weighted_sizes: dict[float, int] = {}
    for run in paragraph.runs:
        text = run.text.strip()
        if not text:
            continue
        points = _length_to_points(getattr(getattr(run, "font", None), "size", None))
        if points is None:
            points = _resolve_style_font_size(getattr(run, "style", None))
        if points is None:
            continue
        normalized_points = round(points, 2)
        weighted_sizes[normalized_points] = weighted_sizes.get(normalized_points, 0) + len(text)

    if weighted_sizes:
        return max(weighted_sizes.items(), key=lambda item: (item[1], item[0]))[0]
    return _resolve_style_font_size(getattr(paragraph, "style", None))


def _infer_contextual_heading_level(paragraphs: list[ParagraphUnit], index: int) -> int:
    for previous_index in range(index - 1, -1, -1):
        previous_paragraph = paragraphs[previous_index]
        if previous_paragraph.role != "heading" or previous_paragraph.heading_level is None:
            continue
        if previous_paragraph.heading_level <= 1:
            return 2
        return previous_paragraph.heading_level
    return 2


def _promote_short_standalone_headings(
    paragraphs: list[ParagraphUnit],
    source_paragraphs: list[Paragraph | None],
) -> None:
    if len(paragraphs) < 3:
        return

    for index in range(1, len(paragraphs) - 1):
        paragraph = paragraphs[index]
        source_paragraph = source_paragraphs[index]
        if paragraph.role != "body" or source_paragraph is None:
            continue
        if not _is_short_standalone_heading_text(paragraph.text):
            continue

        previous_paragraph = paragraphs[index - 1]
        next_paragraph = paragraphs[index + 1]
        if previous_paragraph.role != "body" or next_paragraph.role != "body":
            continue
        if not _has_body_context_signal(previous_paragraph.text) or not _has_body_context_signal(next_paragraph.text):
            continue

        if _is_very_short_standalone_heading_text(paragraph.text):
            paragraph.role = "heading"
            paragraph.structural_role = "heading"
            paragraph.role_confidence = "heuristic"
            paragraph.heading_source = "heuristic"
            paragraph.heading_level = _infer_contextual_heading_level(paragraphs, index)
            continue

        candidate_font_size = _resolve_effective_paragraph_font_size(source_paragraph)
        if candidate_font_size is None:
            continue

        context_font_sizes: list[float] = []
        previous_source = source_paragraphs[index - 1]
        if previous_source is not None:
            previous_font_size = _resolve_effective_paragraph_font_size(previous_source)
            if previous_font_size is not None:
                context_font_sizes.append(previous_font_size)
        next_source = source_paragraphs[index + 1]
        if next_source is not None:
            next_font_size = _resolve_effective_paragraph_font_size(next_source)
            if next_font_size is not None:
                context_font_sizes.append(next_font_size)
        if not context_font_sizes:
            continue

        required_delta = 1.0 if _paragraph_has_strong_heading_format(source_paragraph) else 1.5
        if candidate_font_size < max(context_font_sizes) + required_delta:
            continue

        paragraph.role = "heading"
        paragraph.structural_role = "heading"
        paragraph.role_confidence = "heuristic"
        paragraph.heading_source = "heuristic"
        paragraph.heading_level = _infer_contextual_heading_level(paragraphs, index)


def _reclassify_adjacent_captions(paragraphs: list[ParagraphUnit]) -> None:
    for index, paragraph in enumerate(paragraphs):
        if index == 0:
            continue
        previous_paragraph = paragraphs[index - 1]
        if previous_paragraph.role not in {"image", "table"}:
            continue
        if paragraph.role == "caption":
            paragraph.attached_to_asset_id = previous_paragraph.asset_id
            continue
        if _is_likely_caption_text(paragraph.text):
            if paragraph.role == "heading" and paragraph.heading_source != "heuristic":
                continue
            paragraph.role = "caption"
            paragraph.structural_role = "caption"
            paragraph.role_confidence = "adjacent"
            paragraph.attached_to_asset_id = previous_paragraph.asset_id
            paragraph.heading_level = None
            paragraph.heading_source = None


def _render_hyperlink_element(hyperlink_element, paragraph, image_assets: list[ImageAsset]) -> str:
    text_parts: list[str] = []
    for child in hyperlink_element:
        if _xml_local_name(child.tag) != "r":
            continue
        text_parts.append(_render_run_element(child, paragraph.part, image_assets, allow_hyperlink_markdown=False))

    text = "".join(text_parts)
    if not text.strip():
        return text

    relationship_id = hyperlink_element.get(f"{{{RELATIONSHIP_NAMESPACE}}}id")
    if not relationship_id:
        return text

    relationship = paragraph.part.rels.get(relationship_id)
    url = getattr(relationship, "target_ref", None)
    if not url:
        return text
    return f"[{text}]({url})"


def _render_run_element(run_element, part, image_assets: list[ImageAsset], *, allow_hyperlink_markdown: bool = True) -> str:
    text = _extract_run_text(run_element)
    formatted_text = _apply_run_markdown(text, run_element) if allow_hyperlink_markdown else text
    image_placeholders = _extract_run_image_placeholders(run_element, part, image_assets)
    return formatted_text + "".join(image_placeholders)


def _extract_run_text(run_element) -> str:
    text_parts: list[str] = []
    for child in run_element:
        local_name = _xml_local_name(child.tag)
        if local_name in {"t", "delText", "instrText"}:
            text_parts.append(child.text or "")
            continue
        if local_name == "tab":
            text_parts.append("\t")
            continue
        if local_name in {"br", "cr"}:
            text_parts.append("<br/>")
    return "".join(text_parts)


def _apply_run_markdown(text: str, run_element) -> str:
    if not text:
        return text

    run_properties = _find_child_element(run_element, "rPr")
    if run_properties is None:
        return text

    is_bold = _find_child_element(run_properties, "b") is not None
    is_italic = _find_child_element(run_properties, "i") is not None
    is_underline = _find_child_element(run_properties, "u") is not None
    vertical_align = _extract_vertical_align(run_properties)

    formatted = text
    if is_bold and is_italic:
        formatted = f"***{formatted}***"
    elif is_bold:
        formatted = f"**{formatted}**"
    elif is_italic:
        formatted = f"*{formatted}*"

    if is_underline:
        formatted = f"<u>{formatted}</u>"
    if vertical_align == "superscript":
        formatted = f"<sup>{formatted}</sup>"
    elif vertical_align == "subscript":
        formatted = f"<sub>{formatted}</sub>"
    return formatted


def _extract_vertical_align(run_properties) -> str | None:
    vertical_align = _find_child_element(run_properties, "vertAlign")
    return _get_xml_attribute(vertical_align, "val") if vertical_align is not None else None


def _extract_run_image_placeholders(run_element, part, image_assets: list[ImageAsset]) -> list[str]:
    placeholders: list[str] = []
    for image_blob, mime_type, width_emu, height_emu in _extract_run_element_images(run_element, part):
        image_index = len(image_assets) + 1
        placeholder = f"[[DOCX_IMAGE_img_{image_index:03d}]]"
        image_assets.append(
            ImageAsset(
                image_id=f"img_{image_index:03d}",
                placeholder=placeholder,
                original_bytes=image_blob,
                mime_type=mime_type,
                position_index=image_index - 1,
                width_emu=width_emu,
                height_emu=height_emu,
            )
        )
        placeholders.append(placeholder)
    return placeholders


def _extract_paragraph_list_metadata(paragraph, text: str, style_name: str, role: str) -> dict[str, object]:
    metadata: dict[str, object] = {
        "list_kind": None,
        "list_level": 0,
        "list_numbering_format": None,
        "list_num_id": None,
        "list_abstract_num_id": None,
        "list_num_xml": None,
        "list_abstract_num_xml": None,
    }

    explicit_kind = _detect_explicit_list_kind(text)
    style_level = _extract_style_list_level(style_name)
    num_pr = _resolve_paragraph_num_pr(paragraph)

    if role != "list" and explicit_kind is None and num_pr is None:
        return metadata

    if explicit_kind is not None:
        metadata["list_kind"] = explicit_kind
        # Still try to capture Word numbering XML so DOCX list restoration works
        # even when the source paragraph already has visible text markers in its text.
        # Per spec: numbered lists must be restored as real Word lists even if visible
        # markdown markers are present.
        if num_pr is not None:
            numbering_details = _resolve_num_pr_details(paragraph, num_pr)
            numbering_format = numbering_details["num_format"]
            metadata["list_level"] = _extract_num_pr_level(num_pr)
            metadata["list_numbering_format"] = numbering_format
            metadata["list_num_id"] = numbering_details["num_id"]
            metadata["list_abstract_num_id"] = numbering_details["abstract_num_id"]
            metadata["list_num_xml"] = numbering_details["num_xml"]
            metadata["list_abstract_num_xml"] = numbering_details["abstract_num_xml"]
            if numbering_format in ORDERED_LIST_FORMATS:
                metadata["list_kind"] = "ordered"
            elif numbering_format in UNORDERED_LIST_FORMATS:
                metadata["list_kind"] = "unordered"
        return metadata

    if num_pr is not None:
        list_level = max(_extract_num_pr_level(num_pr), style_level)
        numbering_details = _resolve_num_pr_details(paragraph, num_pr)
        numbering_format = numbering_details["num_format"]
        metadata["list_level"] = list_level
        metadata["list_numbering_format"] = numbering_format
        metadata["list_num_id"] = numbering_details["num_id"]
        metadata["list_abstract_num_id"] = numbering_details["abstract_num_id"]
        metadata["list_num_xml"] = numbering_details["num_xml"]
        metadata["list_abstract_num_xml"] = numbering_details["abstract_num_xml"]
        if numbering_format in ORDERED_LIST_FORMATS:
            metadata["list_kind"] = "ordered"
            return metadata
        if numbering_format in UNORDERED_LIST_FORMATS:
            metadata["list_kind"] = "unordered"
            return metadata
        if role != "list":
            return metadata

    if role != "list":
        return metadata

    normalized_style = style_name.strip().lower()
    if any(token in normalized_style for token in ("number", "num", "нумер", "числ")):
        metadata["list_kind"] = "ordered"
        metadata["list_level"] = style_level
        return metadata
    if any(token in normalized_style for token in ("bullet", "bulleted", "маркир", "маркер")):
        metadata["list_kind"] = "unordered"
        metadata["list_level"] = style_level
        return metadata
    metadata["list_kind"] = "unordered"
    metadata["list_level"] = style_level
    return metadata


def _detect_explicit_list_kind(text: str) -> str | None:
    stripped_text = text.lstrip()
    if stripped_text.startswith(("- ", "* ", "• ", "— ")):
        return "unordered"
    if re.match(r"^\d+[\.)]\s+", stripped_text):
        return "ordered"
    return None


def _extract_style_list_level(style_name: str) -> int:
    match = re.search(r"(\d+)\s*$", style_name.strip())
    if match is None:
        return 0
    try:
        return max(0, int(match.group(1)) - 1)
    except ValueError:
        return 0


def _resolve_paragraph_num_pr(paragraph):
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    num_pr = _find_child_element(paragraph_properties, "numPr")
    if num_pr is not None:
        return num_pr

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = _find_child_element(getattr(style, "_element", None), "pPr")
        num_pr = _find_child_element(style_properties, "numPr")
        if num_pr is not None:
            return num_pr
        style = getattr(style, "base_style", None)
    return None


def _extract_num_pr_level(num_pr) -> int:
    ilvl = _find_child_element(num_pr, "ilvl")
    level_value = _get_xml_attribute(ilvl, "val") if ilvl is not None else None
    if level_value is None:
        return 0
    try:
        return max(0, int(level_value))
    except (TypeError, ValueError):
        return 0


def _resolve_num_pr_details(paragraph, num_pr) -> dict[str, str | None]:
    num_id_element = _find_child_element(num_pr, "numId")
    ilvl_element = _find_child_element(num_pr, "ilvl")
    num_id = _get_xml_attribute(num_id_element, "val") if num_id_element is not None else None
    ilvl = _get_xml_attribute(ilvl_element, "val") if ilvl_element is not None else "0"
    if num_id is None:
        return {
            "num_id": None,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": None,
            "abstract_num_xml": None,
        }

    numbering_part = getattr(paragraph.part, "numbering_part", None)
    numbering_root = getattr(numbering_part, "element", None)
    if numbering_root is None:
        return {
            "num_id": num_id,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": None,
            "abstract_num_xml": None,
        }

    abstract_num_id = None
    num_xml = None
    for child in numbering_root:
        if _xml_local_name(child.tag) != "num":
            continue
        if _get_xml_attribute(child, "numId") != num_id:
            continue
        abstract_num = _find_child_element(child, "abstractNumId")
        abstract_num_id = _get_xml_attribute(abstract_num, "val") if abstract_num is not None else None
        num_xml = etree.tostring(child, encoding="unicode")
        break

    if abstract_num_id is None:
        return {
            "num_id": num_id,
            "abstract_num_id": None,
            "num_format": None,
            "num_xml": num_xml,
            "abstract_num_xml": None,
        }

    for child in numbering_root:
        if _xml_local_name(child.tag) != "abstractNum":
            continue
        if _get_xml_attribute(child, "abstractNumId") != abstract_num_id:
            continue
        abstract_num_xml = etree.tostring(child, encoding="unicode")
        for level in child:
            if _xml_local_name(level.tag) != "lvl":
                continue
            if _get_xml_attribute(level, "ilvl") != ilvl:
                continue
            num_format = _find_child_element(level, "numFmt")
            return {
                "num_id": num_id,
                "abstract_num_id": abstract_num_id,
                "num_format": _get_xml_attribute(num_format, "val") if num_format is not None else None,
                "num_xml": num_xml,
                "abstract_num_xml": abstract_num_xml,
            }
        return {
            "num_id": num_id,
            "abstract_num_id": abstract_num_id,
            "num_format": None,
            "num_xml": num_xml,
            "abstract_num_xml": abstract_num_xml,
        }
    return {
        "num_id": num_id,
        "abstract_num_id": abstract_num_id,
        "num_format": None,
        "num_xml": num_xml,
        "abstract_num_xml": None,
    }


def _find_child_element(parent, local_name: str):
    if parent is None:
        return None
    for child in parent:
        if _xml_local_name(child.tag) == local_name:
            return child
    return None


def _get_xml_attribute(element, attribute_name: str) -> str | None:
    if element is None:
        return None
    for key, value in element.attrib.items():
        if _xml_local_name(key) == attribute_name:
            return value
    return None


def _validate_docx_archive(source_bytes: bytes) -> None:
    if len(source_bytes) > MAX_DOCX_ARCHIVE_SIZE_BYTES:
        raise RuntimeError("DOCX-файл превышает допустимый размер архива.")

    try:
        with zipfile.ZipFile(BytesIO(source_bytes)) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise RuntimeError("Передан поврежденный или неподдерживаемый DOCX-архив.") from exc

    if not entries:
        raise RuntimeError("Передан пустой DOCX-архив.")
    if len(entries) > MAX_DOCX_ENTRY_COUNT:
        raise RuntimeError("DOCX-архив содержит слишком много файлов и отклонен из соображений безопасности.")

    total_uncompressed_size = sum(max(0, entry.file_size) for entry in entries)
    total_compressed_size = sum(max(0, entry.compress_size) for entry in entries)
    if total_uncompressed_size > MAX_DOCX_UNCOMPRESSED_SIZE_BYTES:
        raise RuntimeError("DOCX-архив слишком велик после распаковки и отклонен из соображений безопасности.")
    if total_compressed_size > 0 and (total_uncompressed_size / total_compressed_size) > MAX_DOCX_COMPRESSION_RATIO:
        raise RuntimeError("DOCX-архив имеет подозрительно высокий коэффициент сжатия и отклонен из соображений безопасности.")

    for entry in entries:
        entry_name = entry.filename
        parts = entry_name.replace("\\", "/").split("/")
        if any(part == ".." for part in parts):
            raise RuntimeError("DOCX-архив содержит подозрительные пути и отклонён из соображений безопасности.")
        if entry_name.startswith("/"):
            raise RuntimeError("DOCX-архив содержит абсолютные пути и отклонён из соображений безопасности.")

    filenames = {entry.filename for entry in entries}
    if "[Content_Types].xml" not in filenames:
        raise RuntimeError("Передан невалидный DOCX-архив: отсутствует [Content_Types].xml.")


def validate_docx_source_bytes(source_bytes: bytes) -> None:
    _validate_docx_archive(source_bytes)
