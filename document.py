import re
import zipfile
from io import BytesIO
from pathlib import Path

import document_extraction as _document_extraction
from constants import (
    MAX_DOCX_ARCHIVE_SIZE_BYTES,
    MAX_DOCX_COMPRESSION_RATIO,
    MAX_DOCX_ENTRY_COUNT,
    MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
)
from document_boundaries import (
    summarize_boundary_normalization_metrics,
    write_paragraph_boundary_report_artifact as _write_paragraph_boundary_report_artifact_impl,
)
from document_boundary_review import (
    request_ai_review_recommendations as _request_ai_review_recommendations_impl,
    run_paragraph_boundary_ai_review as _run_paragraph_boundary_ai_review_impl,
)
from document_extraction import (
    IMAGE_PLACEHOLDER_PATTERN,
    ORDERED_LIST_FORMATS,
    _extract_run_text,
    extract_inline_images,
    extract_paragraph_units_from_docx,
    validate_docx_source_bytes,
)
from document_relations import (
    build_paragraph_relations,
    resolve_effective_relation_kinds,
    write_relation_normalization_report_artifact as _write_relation_normalization_report_artifact_impl,
)
from document_roles import (
    HEADING_STYLE_PATTERN,
    INLINE_HTML_TAG_PATTERN,
    MARKDOWN_LINK_PATTERN,
    classify_paragraph_role,
    detect_explicit_list_kind as _detect_explicit_list_kind,
    find_child_element as _find_child_element,
    get_xml_attribute as _get_xml_attribute,
    infer_heuristic_heading_level as _infer_heuristic_heading_level,
    is_image_only_text as _is_image_only_text,
    is_likely_caption_text as _is_likely_caption_text,
    paragraph_has_strong_heading_format,
    promote_short_standalone_headings as _promote_short_standalone_headings,
    resolve_effective_paragraph_font_size,
    resolve_paragraph_outline_level as _resolve_paragraph_outline_level,
    xml_local_name as _xml_local_name,
)
from document_semantic_blocks import build_editing_jobs, build_marker_wrapped_block_text, build_semantic_blocks
from models import ImageAsset, ParagraphUnit, RawBlock
from processing_runtime import read_uploaded_file_bytes, resolve_uploaded_filename
from runtime_artifact_retention import (
    PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_AGE_SECONDS,
    PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_COUNT,
    PARAGRAPH_BOUNDARY_REPORTS_MAX_AGE_SECONDS,
    PARAGRAPH_BOUNDARY_REPORTS_MAX_COUNT,
    RELATION_NORMALIZATION_REPORTS_MAX_AGE_SECONDS,
    RELATION_NORMALIZATION_REPORTS_MAX_COUNT,
)


PARAGRAPH_MARKER_PATTERN = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]")
COMPARE_ALL_VARIANT_LABELS = {
    "safe": "Вариант 1: Просто улучшить",
    "semantic_redraw_direct": "Вариант 2: Креативная AI-перерисовка",
    "semantic_redraw_structured": "Вариант 3: Структурная AI-перерисовка",
}
MANUAL_REVIEW_SAFE_LABEL = "safe"
PARAGRAPH_BOUNDARY_REPORTS_DIR = Path(".run") / "paragraph_boundary_reports"
RELATION_NORMALIZATION_REPORTS_DIR = Path(".run") / "relation_normalization_reports"
PARAGRAPH_BOUNDARY_AI_REVIEW_DIR = Path(".run") / "paragraph_boundary_ai_review"
EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE = "2026-06-30"
EXTRACTION_COMPATIBILITY_OVERRIDE_TARGETS = (
    "MAX_DOCX_ARCHIVE_SIZE_BYTES",
    "MAX_DOCX_COMPRESSION_RATIO",
    "MAX_DOCX_ENTRY_COUNT",
    "MAX_DOCX_UNCOMPRESSED_SIZE_BYTES",
    "PARAGRAPH_BOUNDARY_REPORTS_DIR",
    "RELATION_NORMALIZATION_REPORTS_DIR",
    "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR",
    "read_uploaded_file_bytes",
    "resolve_uploaded_filename",
    "_validate_docx_archive",
    "_read_uploaded_docx_bytes",
    "_write_paragraph_boundary_report_artifact",
    "_write_relation_normalization_report_artifact",
    "_request_ai_review_recommendations",
    "_run_paragraph_boundary_ai_review",
)


def _sync_extraction_compatibility_overrides() -> None:
    # Transitional compatibility seam: remove after facade-level monkeypatch targets
    # are retired from callers and tests no later than EXTRACTION_COMPATIBILITY_OVERRIDE_DEADLINE.
    override_map = _build_extraction_compatibility_overrides()
    if tuple(override_map) != EXTRACTION_COMPATIBILITY_OVERRIDE_TARGETS:
        raise RuntimeError("Extraction compatibility override inventory drifted; update the contract before changing the seam.")
    for attribute_name, value in override_map.items():
        setattr(_document_extraction, attribute_name, value)


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


def _read_uploaded_docx_bytes(uploaded_file) -> bytes:
    try:
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    except ValueError as exc:
        raise ValueError("Не удалось прочитать содержимое DOCX-файла.") from exc
    if zipfile.is_zipfile(BytesIO(source_bytes)):
        return source_bytes
    source_name = resolve_uploaded_filename(uploaded_file)
    raise ValueError(
        "Ожидался уже нормализованный DOCX-архив, но получен ненормализованный входной файл: "
        f"{source_name}"
    )


def _write_paragraph_boundary_report_artifact(*, source_name: str, source_bytes: bytes, mode: str, report) -> str | None:
    return _write_paragraph_boundary_report_artifact_impl(
        source_name=source_name,
        source_bytes=source_bytes,
        mode=mode,
        report=report,
        target_dir=PARAGRAPH_BOUNDARY_REPORTS_DIR,
        max_age_seconds=PARAGRAPH_BOUNDARY_REPORTS_MAX_AGE_SECONDS,
        max_count=PARAGRAPH_BOUNDARY_REPORTS_MAX_COUNT,
    )


def _write_relation_normalization_report_artifact(
    *,
    source_name: str,
    source_bytes: bytes,
    profile: str,
    enabled_relation_kinds: tuple[str, ...],
    report,
) -> str | None:
    return _write_relation_normalization_report_artifact_impl(
        source_name=source_name,
        source_bytes=source_bytes,
        profile=profile,
        enabled_relation_kinds=enabled_relation_kinds,
        report=report,
        target_dir=RELATION_NORMALIZATION_REPORTS_DIR,
        max_age_seconds=RELATION_NORMALIZATION_REPORTS_MAX_AGE_SECONDS,
        max_count=RELATION_NORMALIZATION_REPORTS_MAX_COUNT,
    )


def _request_ai_review_recommendations(
    *,
    model: str,
    candidates: list[dict[str, object]],
    timeout_seconds: int,
    max_tokens_per_candidate: int,
) -> dict[str, dict[str, object]]:
    return _request_ai_review_recommendations_impl(
        model=model,
        candidates=candidates,
        timeout_seconds=timeout_seconds,
        max_tokens_per_candidate=max_tokens_per_candidate,
    )


def _run_paragraph_boundary_ai_review(
    *,
    source_name: str,
    source_bytes: bytes,
    mode: str,
    model: str,
    raw_blocks: list[RawBlock],
    paragraphs: list[ParagraphUnit],
    boundary_report,
    relation_report,
    candidate_limit: int,
    timeout_seconds: int,
    max_tokens_per_candidate: int,
) -> str | None:
    return _run_paragraph_boundary_ai_review_impl(
        source_name=source_name,
        source_bytes=source_bytes,
        mode=mode,
        model=model,
        raw_blocks=raw_blocks,
        paragraphs=paragraphs,
        boundary_report=boundary_report,
        relation_report=relation_report,
        candidate_limit=candidate_limit,
        timeout_seconds=timeout_seconds,
        max_tokens_per_candidate=max_tokens_per_candidate,
        target_dir=PARAGRAPH_BOUNDARY_AI_REVIEW_DIR,
        max_age_seconds=PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_AGE_SECONDS,
        max_count=PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_COUNT,
        request_ai_review_recommendations_impl=_request_ai_review_recommendations,
    )


def _build_extraction_compatibility_overrides() -> dict[str, object]:
    return {
        "MAX_DOCX_ARCHIVE_SIZE_BYTES": MAX_DOCX_ARCHIVE_SIZE_BYTES,
        "MAX_DOCX_COMPRESSION_RATIO": MAX_DOCX_COMPRESSION_RATIO,
        "MAX_DOCX_ENTRY_COUNT": MAX_DOCX_ENTRY_COUNT,
        "MAX_DOCX_UNCOMPRESSED_SIZE_BYTES": MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
        "PARAGRAPH_BOUNDARY_REPORTS_DIR": PARAGRAPH_BOUNDARY_REPORTS_DIR,
        "RELATION_NORMALIZATION_REPORTS_DIR": RELATION_NORMALIZATION_REPORTS_DIR,
        "PARAGRAPH_BOUNDARY_AI_REVIEW_DIR": PARAGRAPH_BOUNDARY_AI_REVIEW_DIR,
        "read_uploaded_file_bytes": read_uploaded_file_bytes,
        "resolve_uploaded_filename": resolve_uploaded_filename,
        "_validate_docx_archive": _validate_docx_archive,
        "_read_uploaded_docx_bytes": _read_uploaded_docx_bytes,
        "_write_paragraph_boundary_report_artifact": _write_paragraph_boundary_report_artifact,
        "_write_relation_normalization_report_artifact": _write_relation_normalization_report_artifact,
        "_request_ai_review_recommendations": _request_ai_review_recommendations,
        "_run_paragraph_boundary_ai_review": _run_paragraph_boundary_ai_review,
    }


def extract_document_content_from_docx(uploaded_file) -> tuple[list[ParagraphUnit], list[ImageAsset]]:
    _sync_extraction_compatibility_overrides()
    return _document_extraction.extract_document_content_from_docx(uploaded_file)


def extract_document_content_with_normalization_reports(uploaded_file):
    _sync_extraction_compatibility_overrides()
    return _document_extraction.extract_document_content_with_normalization_reports(uploaded_file)


def extract_document_content_with_boundary_report(uploaded_file):
    _sync_extraction_compatibility_overrides()
    return _document_extraction.extract_document_content_with_boundary_report(uploaded_file)


def build_document_text(paragraphs: list[ParagraphUnit]) -> str:
    return "\n\n".join(paragraph.rendered_text for paragraph in paragraphs).strip()


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


xml_local_name = _xml_local_name
resolve_paragraph_outline_level = _resolve_paragraph_outline_level
infer_heuristic_heading_level = _infer_heuristic_heading_level
is_image_only_text = _is_image_only_text
is_likely_caption_text = _is_likely_caption_text
detect_explicit_list_kind = _detect_explicit_list_kind
find_child_element = _find_child_element
get_xml_attribute = _get_xml_attribute
_paragraph_has_strong_heading_format = paragraph_has_strong_heading_format
_resolve_effective_paragraph_font_size = resolve_effective_paragraph_font_size
