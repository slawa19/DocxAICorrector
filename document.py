import re
import zipfile
from io import BytesIO

from docx import Document
from docx.shared import Emu

from models import DocumentBlock, ImageAsset, ParagraphUnit

IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_img_\d+\]\]")
MAX_DOCX_ARCHIVE_SIZE_BYTES = 25 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_SIZE_BYTES = 100 * 1024 * 1024
MAX_DOCX_ENTRY_COUNT = 2048
MAX_DOCX_COMPRESSION_RATIO = 150.0


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
    paragraphs, _ = extract_document_content_from_docx(uploaded_file)
    return paragraphs


def extract_inline_images(uploaded_file) -> list[ImageAsset]:
    _, image_assets = extract_document_content_from_docx(uploaded_file)
    return image_assets


def extract_document_content_from_docx(uploaded_file) -> tuple[list[ParagraphUnit], list[ImageAsset]]:
    source_bytes = _read_uploaded_docx_bytes(uploaded_file)
    _validate_docx_archive(source_bytes)
    document = Document(BytesIO(source_bytes))
    paragraphs: list[ParagraphUnit] = []
    image_assets: list[ImageAsset] = []

    for paragraph in document.paragraphs:
        text = _build_paragraph_text_with_placeholders(paragraph, image_assets).strip()
        if not text:
            continue

        style_name = paragraph.style.name if paragraph.style and paragraph.style.name else ""
        paragraphs.append(ParagraphUnit(text=text, role=classify_paragraph_role(text, style_name)))

    if not paragraphs:
        raise ValueError("В документе не найден текст для обработки.")
    return paragraphs, image_assets


def build_document_text(paragraphs: list[ParagraphUnit]) -> str:
    return "\n\n".join(paragraph.text for paragraph in paragraphs).strip()


def inspect_placeholder_integrity(markdown_text: str, image_assets: list[ImageAsset]) -> dict[str, str]:
    status_map: dict[str, str] = {}
    for asset in image_assets:
        occurrence_count = markdown_text.count(asset.placeholder)
        if occurrence_count == 1:
            status_map[asset.image_id] = "ok"
        elif occurrence_count == 0:
            status_map[asset.image_id] = "lost"
        else:
            status_map[asset.image_id] = "duplicated"
    return status_map


def reinsert_inline_images(docx_bytes: bytes, image_assets: list[ImageAsset]) -> bytes:
    if not image_assets:
        return docx_bytes

    source_stream = BytesIO(docx_bytes)
    document = Document(source_stream)
    asset_map = {asset.placeholder: asset for asset in image_assets}

    for paragraph in document.paragraphs:
        paragraph_text = paragraph.text
        placeholders = [token for token in IMAGE_PLACEHOLDER_PATTERN.findall(paragraph_text) if token in asset_map]
        if not placeholders:
            continue

        parts = re.split(f"({IMAGE_PLACEHOLDER_PATTERN.pattern})", paragraph_text)
        _clear_paragraph_runs(paragraph)
        for part in parts:
            if not part:
                continue
            asset = asset_map.get(part)
            if asset is None:
                paragraph.add_run(part)
                continue
            image_bytes = resolve_final_image_bytes(asset)
            if not image_bytes:
                continue
            add_picture_kwargs = _build_picture_size_kwargs(asset)
            paragraph.add_run().add_picture(BytesIO(image_bytes), **add_picture_kwargs)

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()


def resolve_final_image_bytes(asset: ImageAsset) -> bytes:
    if asset.selected_compare_variant:
        selected_variant = asset.comparison_variants.get(asset.selected_compare_variant, {})
        selected_bytes = selected_variant.get("bytes") if isinstance(selected_variant, dict) else None
        if isinstance(selected_bytes, (bytes, bytearray)) and selected_bytes:
            return bytes(selected_bytes)
    if asset.final_variant == "redrawn" and asset.redrawn_bytes:
        return asset.redrawn_bytes
    if asset.final_variant == "safe" and asset.safe_bytes:
        return asset.safe_bytes
    return asset.original_bytes


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


def _build_paragraph_text_with_placeholders(paragraph, image_assets: list[ImageAsset]) -> str:
    parts: list[str] = []
    for run in paragraph.runs:
        if run.text:
            parts.append(run.text)
        for image_blob, mime_type, width_emu, height_emu in _extract_run_images(run):
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
            parts.append(placeholder)
    return "".join(parts)


def _extract_run_images(run) -> list[tuple[bytes, str | None, int | None, int | None]]:
    images: list[tuple[bytes, str | None, int | None, int | None]] = []
    for drawing in run._element.xpath(".//w:drawing"):
        blips = drawing.xpath(".//a:blip")
        width_emu, height_emu = _resolve_drawing_extent_emu(drawing)
        for blip in blips:
            embed_id = blip.get(f"{{http://schemas.openxmlformats.org/officeDocument/2006/relationships}}embed")
            if not embed_id:
                continue
            image_part = run.part.related_parts.get(embed_id)
            if image_part is None:
                continue
            images.append((image_part.blob, getattr(image_part, "content_type", None), width_emu, height_emu))
    return images


def _clear_paragraph_runs(paragraph) -> None:
    paragraph_element = paragraph._element
    for child in list(paragraph_element):
        if _xml_local_name(child.tag) in {"r", "hyperlink"}:
            paragraph_element.remove(child)


def _build_picture_size_kwargs(asset: ImageAsset) -> dict[str, Emu]:
    size_kwargs: dict[str, Emu] = {}
    if isinstance(asset.width_emu, int) and asset.width_emu > 0:
        size_kwargs["width"] = Emu(asset.width_emu)
    if isinstance(asset.height_emu, int) and asset.height_emu > 0:
        size_kwargs["height"] = Emu(asset.height_emu)
    return size_kwargs


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
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    if hasattr(uploaded_file, "getvalue"):
        source_bytes = uploaded_file.getvalue()
    else:
        source_bytes = uploaded_file.read()
    if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        raise ValueError("Не удалось прочитать содержимое DOCX-файла.")
    return bytes(source_bytes)


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

    filenames = {entry.filename for entry in entries}
    if "[Content_Types].xml" not in filenames:
        raise RuntimeError("Передан невалидный DOCX-архив: отсутствует [Content_Types].xml.")
