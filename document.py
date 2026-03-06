import re

from docx import Document

from models import DocumentBlock, ParagraphUnit


def classify_paragraph_role(text: str, style_name: str) -> str:
    normalized_style = style_name.strip().lower()
    stripped_text = text.lstrip()

    if normalized_style.startswith("heading") or normalized_style.startswith("заголовок"):
        return "heading"

    if "list" in normalized_style or "спис" in normalized_style:
        return "list"

    if stripped_text.startswith(("- ", "* ", "• ", "— ")):
        return "list"

    if re.match(r"^\d+[\.)]\s+", stripped_text):
        return "list"

    return "body"


def extract_paragraph_units_from_docx(uploaded_file) -> list[ParagraphUnit]:
    uploaded_file.seek(0)
    document = Document(uploaded_file)
    paragraphs: list[ParagraphUnit] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style and paragraph.style.name else ""
        paragraphs.append(ParagraphUnit(text=text, role=classify_paragraph_role(text, style_name)))

    if not paragraphs:
        raise ValueError("В документе не найден текст для обработки.")
    return paragraphs


def build_document_text(paragraphs: list[ParagraphUnit]) -> str:
    return "\n\n".join(paragraph.text for paragraph in paragraphs).strip()


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
        current_size += separator_size + len(paragraph.text)

    for paragraph in paragraphs:
        if not current:
            append_paragraph(paragraph)
            continue

        projected_size = current_size + 2 + len(paragraph.text)
        current_only_heading = len(current) == 1 and current[0].role == "heading"
        current_is_list = all(item.role == "list" for item in current)

        if paragraph.role == "heading":
            flush_current()
            append_paragraph(paragraph)
            continue

        if current_only_heading:
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

        if projected_size <= max_chars and len(paragraph.text) <= max(500, max_chars // 4) and current_size < int(max_chars * 0.9):
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


def build_editing_jobs(blocks: list[DocumentBlock], max_chars: int) -> list[dict[str, str | int]]:
    context_before_chars = max(600, min(1400, int(max_chars * 0.2)))
    context_after_chars = max(300, min(800, int(max_chars * 0.12)))
    jobs: list[dict[str, str | int]] = []

    for index, block in enumerate(blocks):
        context_before = build_context_excerpt(blocks, index, context_before_chars, reverse=True)
        context_after = build_context_excerpt(blocks, index, context_after_chars, reverse=False)
        jobs.append(
            {
                "target_text": block.text,
                "context_before": context_before,
                "context_after": context_after,
                "target_chars": len(block.text),
                "context_chars": len(context_before) + len(context_after),
            }
        )

    return jobs
