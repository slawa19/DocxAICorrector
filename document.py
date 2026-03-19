from copy import deepcopy
from difflib import SequenceMatcher
import html
import json
import re
from pathlib import Path
import time
import zipfile
from io import BytesIO
from typing import Mapping, Sequence, cast

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Emu
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
import lxml.etree as etree

from constants import (
    MAX_DOCX_ARCHIVE_SIZE_BYTES,
    MAX_DOCX_COMPRESSION_RATIO,
    MAX_DOCX_ENTRY_COUNT,
    MAX_DOCX_UNCOMPRESSED_SIZE_BYTES,
)
from logger import log_event
from models import DocumentBlock, ImageAsset, ParagraphUnit, get_image_variant_bytes
from processing_runtime import read_uploaded_file_bytes
import logging

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
FORMATTING_DIAGNOSTICS_DIR = Path(".run") / "formatting_diagnostics"
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


def _paragraph_preview(text: str, *, limit: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _normalize_text_for_mapping(text: str) -> str:
    normalized = text.strip()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("***", "").replace("**", "").replace("*", "")
    normalized = normalized.replace("<br/>", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip().lower()


def _collect_target_paragraphs(document) -> list[Paragraph]:
    return [
        paragraph
        for paragraph in document.paragraphs
        if paragraph.text.strip() or IMAGE_PLACEHOLDER_PATTERN.search(paragraph.text)
    ]


def _build_source_registry_entry(
    paragraph: ParagraphUnit,
    fallback_index: int,
    *,
    mapped_target_index: int | None,
    strategy: str | None,
) -> dict[str, object]:
    source_index = paragraph.source_index if paragraph.source_index >= 0 else fallback_index
    return {
        "paragraph_id": paragraph.paragraph_id or f"p{source_index:04d}",
        "source_index": source_index,
        "role": paragraph.role,
        "structural_role": paragraph.structural_role,
        "role_confidence": paragraph.role_confidence,
        "asset_id": paragraph.asset_id,
        "attached_to_asset_id": paragraph.attached_to_asset_id,
        "heading_level": paragraph.heading_level,
        "list_kind": paragraph.list_kind,
        "list_level": paragraph.list_level,
        "list_numbering_format": paragraph.list_numbering_format,
        "list_num_id": paragraph.list_num_id,
        "list_abstract_num_id": paragraph.list_abstract_num_id,
        "mapped_target_index": mapped_target_index,
        "mapping_strategy": strategy,
        "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
    }


def _build_target_registry_entry(paragraph, target_index: int, *, mapped: bool) -> dict[str, object]:
    style = getattr(paragraph, "style", None)
    style_name = getattr(style, "name", None)
    return {
        "target_index": target_index,
        "mapped": mapped,
        "style_name": style_name,
        "heading_level": _extract_target_heading_level(paragraph),
        "text_preview": _paragraph_preview(_normalize_text_for_mapping(paragraph.text) or paragraph.text),
    }


def _extract_target_heading_level(paragraph) -> int | None:
    style = getattr(paragraph, "style", None)
    style_name = getattr(style, "name", "") or ""
    normalized_style = style_name.strip().lower()
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


def _build_caption_heading_conflicts(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    mapped_target_by_source: Mapping[int, int],
    strategy_by_source: Mapping[int, str],
) -> list[dict[str, object]]:
    conflicts: list[dict[str, object]] = []
    for source_index, target_index in sorted(mapped_target_by_source.items()):
        source_paragraph = source_paragraphs[source_index]
        if source_paragraph.role != "caption":
            continue

        target_paragraph = target_paragraphs[target_index]
        target_heading_level = _extract_target_heading_level(target_paragraph)
        if target_heading_level is None:
            continue

        conflicts.append(
            {
                "paragraph_id": source_paragraph.paragraph_id or f"p{source_index:04d}",
                "source_index": source_paragraph.source_index if source_paragraph.source_index >= 0 else source_index,
                "mapped_target_index": target_index,
                "mapping_strategy": strategy_by_source.get(source_index),
                "source_role": source_paragraph.role,
                "source_role_confidence": source_paragraph.role_confidence,
                "attached_to_asset_id": source_paragraph.attached_to_asset_id,
                "target_style_name": getattr(getattr(target_paragraph, "style", None), "name", None),
                "target_heading_level": target_heading_level,
                "source_text_preview": _paragraph_preview(source_paragraph.text),
                "target_text_preview": _paragraph_preview(target_paragraph.text),
            }
        )
    return conflicts


def _mapping_similarity_score(source_paragraph: ParagraphUnit, target_text: str) -> float:
    source_text = _normalize_text_for_mapping(source_paragraph.text)
    normalized_target = _normalize_text_for_mapping(target_text)
    if not source_text or not normalized_target:
        return 0.0

    score = SequenceMatcher(None, source_text, normalized_target).ratio()
    if source_paragraph.role == "caption" and _is_likely_caption_text(target_text):
        score += 0.08
    if source_paragraph.role == "list":
        target_list_kind = _detect_explicit_list_kind(target_text)
        if target_list_kind is not None and target_list_kind == source_paragraph.list_kind:
            score += 0.05
    if source_paragraph.role == "heading" and len(target_text.split()) <= 18:
        score += 0.03
    return min(score, 1.0)


def _register_mapping(
    source_index: int,
    target_index: int,
    strategy: str,
    *,
    mapped_target_by_source: dict[int, int],
    strategy_by_source: dict[int, str],
    available_target_indexes: set[int],
) -> None:
    mapped_target_by_source[source_index] = target_index
    strategy_by_source[source_index] = strategy
    available_target_indexes.discard(target_index)


def _build_generated_registry_by_paragraph_id(
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None,
) -> dict[str, str]:
    registry_by_id: dict[str, str] = {}
    if not generated_paragraph_registry:
        return registry_by_id

    for entry in generated_paragraph_registry:
        paragraph_id = entry.get("paragraph_id")
        text = entry.get("text")
        if isinstance(paragraph_id, str) and paragraph_id and isinstance(text, str) and text.strip():
            registry_by_id[paragraph_id] = text
    return registry_by_id


def _map_source_target_paragraphs(
    source_paragraphs: list[ParagraphUnit],
    target_paragraphs: list[Paragraph],
    *,
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
):
    mapped_target_by_source: dict[int, int] = {}
    strategy_by_source: dict[int, str] = {}
    generated_registry_by_id = _build_generated_registry_by_paragraph_id(generated_paragraph_registry)

    if len(source_paragraphs) == len(target_paragraphs):
        for source_index in range(len(source_paragraphs)):
            mapped_target_by_source[source_index] = source_index
            strategy_by_source[source_index] = "positional"
    else:
        available_target_indexes = set(range(len(target_paragraphs)))
        target_indexes_by_exact_text: dict[str, list[int]] = {}
        target_indexes_by_normalized_text: dict[str, list[int]] = {}

        for target_index, target_paragraph in enumerate(target_paragraphs):
            exact_text = target_paragraph.text.strip()
            target_indexes_by_exact_text.setdefault(exact_text, []).append(target_index)
            normalized_text = _normalize_text_for_mapping(target_paragraph.text)
            if normalized_text:
                target_indexes_by_normalized_text.setdefault(normalized_text, []).append(target_index)

        for source_index, source_paragraph in enumerate(source_paragraphs):
            paragraph_id = source_paragraph.paragraph_id
            if not paragraph_id or source_index in mapped_target_by_source:
                continue
            generated_text = generated_registry_by_id.get(paragraph_id)
            if not generated_text:
                continue
            normalized_generated_text = _normalize_text_for_mapping(generated_text)
            if not normalized_generated_text:
                continue
            candidates = [
                target_index
                for target_index in target_indexes_by_normalized_text.get(normalized_generated_text, [])
                if target_index in available_target_indexes
            ]
            if len(candidates) == 1:
                _register_mapping(
                    source_index,
                    candidates[0],
                    "paragraph_id_registry",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )

        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_target_by_source or source_paragraph.role != "image":
                continue
            candidates = [
                target_index
                for target_index in target_indexes_by_exact_text.get(source_paragraph.text.strip(), [])
                if target_index in available_target_indexes
            ]
            if len(candidates) == 1:
                _register_mapping(
                    source_index,
                    candidates[0],
                    "image_anchor",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )

        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index == 0 or source_index in mapped_target_by_source or source_paragraph.role != "caption":
                continue
            previous_paragraph = source_paragraphs[source_index - 1]
            previous_target_index = mapped_target_by_source.get(source_index - 1)
            if previous_paragraph.role not in {"image", "table"} or previous_target_index is None:
                continue
            candidate_index = previous_target_index + 1
            if candidate_index not in available_target_indexes or candidate_index >= len(target_paragraphs):
                continue
            candidate_text = target_paragraphs[candidate_index].text.strip()
            if candidate_text and (
                _is_likely_caption_text(candidate_text)
                or _normalize_text_for_mapping(source_paragraph.text) == _normalize_text_for_mapping(candidate_text)
            ):
                _register_mapping(
                    source_index,
                    candidate_index,
                    "adjacent_caption",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )

        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_target_by_source:
                continue
            normalized_text = _normalize_text_for_mapping(source_paragraph.text)
            if not normalized_text:
                continue
            candidates = [
                target_index
                for target_index in target_indexes_by_normalized_text.get(normalized_text, [])
                if target_index in available_target_indexes
            ]
            if len(candidates) == 1:
                _register_mapping(
                    source_index,
                    candidates[0],
                    "exact_text",
                    mapped_target_by_source=mapped_target_by_source,
                    strategy_by_source=strategy_by_source,
                    available_target_indexes=available_target_indexes,
                )

        for source_index, source_paragraph in enumerate(source_paragraphs):
            if source_index in mapped_target_by_source or source_paragraph.role == "image":
                continue

            scored_candidates: list[tuple[float, int]] = []
            for target_index in sorted(available_target_indexes):
                score = _mapping_similarity_score(source_paragraph, target_paragraphs[target_index].text)
                if score >= 0.9:
                    scored_candidates.append((score, target_index))

            if not scored_candidates:
                continue

            scored_candidates.sort(reverse=True)
            best_score, best_target_index = scored_candidates[0]
            next_best_score = scored_candidates[1][0] if len(scored_candidates) > 1 else 0.0
            if best_score - next_best_score < 0.05:
                continue

            _register_mapping(
                source_index,
                best_target_index,
                "similarity",
                mapped_target_by_source=mapped_target_by_source,
                strategy_by_source=strategy_by_source,
                available_target_indexes=available_target_indexes,
            )

    mapping_pairs = [
        (source_paragraphs[source_index], target_paragraphs[target_index])
        for source_index, target_index in sorted(mapped_target_by_source.items())
    ]

    diagnostics = {
        "source_count": len(source_paragraphs),
        "target_count": len(target_paragraphs),
        "mapped_count": len(mapping_pairs),
        "unmapped_source_ids": [
            source_paragraphs[source_index].paragraph_id or f"p{source_index:04d}"
            for source_index in range(len(source_paragraphs))
            if source_index not in mapped_target_by_source
        ],
        "unmapped_target_indexes": [
            target_index
            for target_index in range(len(target_paragraphs))
            if target_index not in mapped_target_by_source.values()
        ],
        "source_registry": [
            _build_source_registry_entry(
                paragraph,
                index,
                mapped_target_index=mapped_target_by_source.get(index),
                strategy=strategy_by_source.get(index),
            )
            for index, paragraph in enumerate(source_paragraphs)
        ],
        "target_registry": [
            _build_target_registry_entry(
                paragraph,
                index,
                mapped=index in mapped_target_by_source.values(),
            )
            for index, paragraph in enumerate(target_paragraphs)
        ],
        "caption_heading_conflicts": _build_caption_heading_conflicts(
            source_paragraphs,
            target_paragraphs,
            mapped_target_by_source,
            strategy_by_source,
        ),
        "list_restoration_decisions": [],
    }
    return mapping_pairs, diagnostics


def _write_formatting_diagnostics_artifact(stage: str, diagnostics: dict[str, object]) -> str | None:
    try:
        FORMATTING_DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path = FORMATTING_DIAGNOSTICS_DIR / f"{stage}_{int(time.time() * 1000)}.json"
        payload = {
            "stage": stage,
            "generated_at_epoch_ms": int(time.time() * 1000),
            **diagnostics,
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(artifact_path)
    except Exception:
        return None


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
    image_assets: list[ImageAsset] = []
    table_count = 0

    for block_kind, block in _iter_document_block_items(document):
        if block_kind == "paragraph":
            paragraph_unit = _build_paragraph_unit(cast(Paragraph, block), image_assets)
        else:
            table_count += 1
            paragraph_unit = _build_table_unit(cast(Table, block), image_assets, asset_id=f"table_{table_count:03d}")
        if paragraph_unit is not None:
            _assign_paragraph_identity(paragraph_unit, len(paragraphs))
            paragraphs.append(paragraph_unit)

    _reclassify_adjacent_captions(paragraphs)

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


def preserve_source_paragraph_properties(
    docx_bytes: bytes,
    paragraphs: list[ParagraphUnit],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    if not docx_bytes or not paragraphs:
        return docx_bytes

    source_paragraphs = [paragraph for paragraph in paragraphs if paragraph.role != "table"]
    if not any(paragraph.preserved_ppr_xml for paragraph in source_paragraphs):
        return docx_bytes

    document = Document(BytesIO(docx_bytes))
    target_paragraphs = _collect_target_paragraphs(document)
    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    if len(source_paragraphs) != len(target_paragraphs) or diagnostics["mapped_count"] != len(source_paragraphs):
        artifact_path = _write_formatting_diagnostics_artifact("preserve", diagnostics)
        log_event(
            logging.WARNING,
            "paragraph_count_mismatch_preserve",
            "Число source/target абзацев не совпадает при переносе свойств форматирования; применяю только консервативно сопоставленные абзацы.",
            source_count=len(source_paragraphs),
            target_count=len(target_paragraphs),
            mapped_count=diagnostics["mapped_count"],
            unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
            unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
            artifact_path=artifact_path,
        )

    if not mapping_pairs:
        return docx_bytes

    for source_paragraph, target_paragraph in mapping_pairs:
        _apply_preserved_paragraph_properties(target_paragraph, source_paragraph.preserved_ppr_xml)

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()


def normalize_semantic_output_docx(
    docx_bytes: bytes,
    paragraphs: list[ParagraphUnit],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    if not docx_bytes or not paragraphs:
        return docx_bytes

    source_paragraphs = [paragraph for paragraph in paragraphs if paragraph.role != "table"]
    document = Document(BytesIO(docx_bytes))
    target_paragraphs = _collect_target_paragraphs(document)
    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=generated_paragraph_registry,
    )

    mismatch_detected = (
        len(source_paragraphs) != len(target_paragraphs)
        or diagnostics["mapped_count"] != len(source_paragraphs)
    )

    if not mapping_pairs:
        if mismatch_detected:
            artifact_path = _write_formatting_diagnostics_artifact("normalize", diagnostics)
            log_event(
                logging.WARNING,
                "paragraph_count_mismatch_normalize",
                "Число source/target абзацев не совпадает при semantic-normalization; нормализую только консервативно сопоставленные абзацы.",
                source_count=len(source_paragraphs),
                target_count=len(target_paragraphs),
                mapped_count=diagnostics["mapped_count"],
                unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
                unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
                artifact_path=artifact_path,
            )
        return docx_bytes

    for source_paragraph, target_paragraph in mapping_pairs:
        _normalize_output_paragraph(document, target_paragraph, source_paragraph)

    diagnostics["list_restoration_decisions"] = _restore_list_numbering_for_mapped_paragraphs(document, mapping_pairs)

    if mismatch_detected:
        artifact_path = _write_formatting_diagnostics_artifact("normalize", diagnostics)
        log_event(
            logging.WARNING,
            "paragraph_count_mismatch_normalize",
            "Число source/target абзацев не совпадает при semantic-normalization; нормализую только консервативно сопоставленные абзацы.",
            source_count=len(source_paragraphs),
            target_count=len(target_paragraphs),
            mapped_count=diagnostics["mapped_count"],
            unmapped_source_count=len(diagnostics["unmapped_source_ids"]),
            unmapped_target_count=len(diagnostics["unmapped_target_indexes"]),
            artifact_path=artifact_path,
        )

    if _style_exists(document, "Table Grid"):
        for table in document.tables:
            table.style = "Table Grid"

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()


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


def reinsert_inline_images(docx_bytes: bytes, image_assets: list[ImageAsset]) -> bytes:
    if not docx_bytes or not image_assets:
        return docx_bytes

    source_stream = BytesIO(docx_bytes)
    document = Document(source_stream)
    asset_map = {asset.placeholder: asset for asset in image_assets}

    for paragraph in _iter_reinsertion_paragraphs(document):
        paragraph_text = paragraph.text
        placeholders = _find_known_placeholders(paragraph_text, asset_map)
        if not placeholders:
            continue

        if _replace_multi_variant_placeholders_with_tables(paragraph, asset_map):
            continue

        if _replace_run_level_placeholders(paragraph, placeholders, asset_map):
            continue

        if _replace_multi_run_placeholders(paragraph, asset_map):
            continue

        _replace_paragraph_placeholders_fallback(paragraph, paragraph_text, asset_map)

    output_stream = BytesIO()
    document.save(output_stream)
    return output_stream.getvalue()



def _iter_reinsertion_paragraphs(document):
    visited_paragraph_elements: set[object] = set()

    yield from _iter_container_paragraphs(
        document,
        _visited_cell_elements=set(),
        _visited_paragraph_elements=visited_paragraph_elements,
    )

    for story_container in _iter_section_story_containers(document):
        yield from _iter_container_paragraphs(
            story_container,
            _visited_cell_elements=set(),
            _visited_paragraph_elements=visited_paragraph_elements,
        )


def _iter_section_story_containers(document):
    for section in document.sections:
        for attribute_name in (
            "header",
            "first_page_header",
            "even_page_header",
            "footer",
            "first_page_footer",
            "even_page_footer",
        ):
            story_container = getattr(section, attribute_name, None)
            if story_container is None:
                continue
            yield story_container


def _iter_container_paragraphs(
    container,
    *,
    _visited_cell_elements: set[object] | None = None,
    _visited_paragraph_elements: set[object] | None = None,
):
    if _visited_cell_elements is None:
        _visited_cell_elements = set()
    if _visited_paragraph_elements is None:
        _visited_paragraph_elements = set()

    for paragraph in getattr(container, "paragraphs", []):
        paragraph_element = paragraph._element
        if paragraph_element not in _visited_paragraph_elements:
            _visited_paragraph_elements.add(paragraph_element)
            yield paragraph

        yield from _iter_textbox_paragraphs(paragraph, _visited_paragraph_elements)

    for table in getattr(container, "tables", []):
        for row in table.rows:
            for cell in row.cells:
                cell_element = cell._tc
                if cell_element in _visited_cell_elements:
                    continue
                _visited_cell_elements.add(cell_element)
                yield from _iter_container_paragraphs(
                    cell,
                    _visited_cell_elements=_visited_cell_elements,
                    _visited_paragraph_elements=_visited_paragraph_elements,
                )


def _iter_textbox_paragraphs(paragraph, visited_paragraph_elements: set[object]):
    for textbox_paragraph_element in paragraph._element.xpath(".//w:txbxContent//w:p"):
        if textbox_paragraph_element in visited_paragraph_elements:
            continue

        visited_paragraph_elements.add(textbox_paragraph_element)
        yield Paragraph(textbox_paragraph_element, paragraph._parent)


def _find_known_placeholders(text: str, asset_map: dict[str, ImageAsset]) -> list[str]:
    return [token for token in IMAGE_PLACEHOLDER_PATTERN.findall(text) if token in asset_map]


def _replace_run_level_placeholders(paragraph, placeholders: list[str], asset_map: dict[str, ImageAsset]) -> bool:
    runs = list(paragraph.runs)
    run_placeholders: list[str] = []
    for run in runs:
        run_placeholders.extend(_find_known_placeholders(run.text, asset_map))

    if len(run_placeholders) != len(placeholders):
        return False

    for run in runs:
        run_text = run.text
        run_tokens = _find_known_placeholders(run_text, asset_map)
        if not run_tokens:
            continue

        replacement_elements = _build_run_replacement_elements(paragraph, run._element, run_text, asset_map)
        _replace_xml_element_with_sequence(run._element, replacement_elements)
    return True


def _replace_multi_run_placeholders(paragraph, asset_map: dict[str, ImageAsset]) -> bool:
    paragraph_children = [child for child in list(paragraph._element) if _xml_local_name(child.tag) in {"r", "hyperlink"}]
    if not paragraph_children or any(_xml_local_name(child.tag) == "hyperlink" for child in paragraph_children):
        return False

    runs = list(paragraph.runs)
    if not runs:
        return False

    run_texts = [run.text for run in runs]
    full_text = "".join(run_texts)
    placeholder_matches = [
        match
        for match in IMAGE_PLACEHOLDER_PATTERN.finditer(full_text)
        if match.group(0) in asset_map
    ]
    if not placeholder_matches:
        return False

    replacement_elements = []
    run_ranges: list[tuple[Run, int, int]] = []
    cursor = 0
    for run, run_text in zip(runs, run_texts):
        next_cursor = cursor + len(run_text)
        run_ranges.append((run, cursor, next_cursor))
        cursor = next_cursor

    match_index = 0
    current_match = placeholder_matches[match_index] if placeholder_matches else None

    for run, run_start, run_end in run_ranges:
        position = run_start
        while position < run_end:
            while current_match is not None and current_match.end() <= position:
                match_index += 1
                current_match = placeholder_matches[match_index] if match_index < len(placeholder_matches) else None

            if current_match is not None and position >= current_match.start() and position < current_match.end():
                if position == current_match.start():
                    placeholder_text = current_match.group(0)
                    replacement_elements.extend(
                        _build_insertion_run_elements(
                            paragraph,
                            run._element,
                            asset_map[placeholder_text],
                            placeholder_text=placeholder_text,
                        )
                    )
                position = min(run_end, current_match.end())
                continue

            segment_end = run_end
            if current_match is not None and position < current_match.start():
                segment_end = min(segment_end, current_match.start())

            if segment_end > position:
                replacement_elements.append(
                    _build_text_run_element(paragraph, run._element, full_text[position:segment_end])
                )
            position = segment_end

    if not replacement_elements:
        return False

    _clear_paragraph_runs(paragraph)
    for element in replacement_elements:
        paragraph._element.append(element)
    return True


def _replace_paragraph_placeholders_fallback(paragraph, paragraph_text: str, asset_map: dict[str, ImageAsset]) -> None:
    parts = re.split(f"({IMAGE_PLACEHOLDER_PATTERN.pattern})", paragraph_text)
    _clear_paragraph_runs(paragraph)
    for part in parts:
        if not part:
            continue
        asset = asset_map.get(part)
        if asset is None:
            paragraph.add_run(part)
            continue
        _append_image_insertions_to_paragraph(paragraph, asset, placeholder_text=part)


def _build_run_replacement_elements(paragraph, template_run_element, run_text: str, asset_map: dict[str, ImageAsset]):
    replacement_elements = []
    parts = re.split(f"({IMAGE_PLACEHOLDER_PATTERN.pattern})", run_text)
    for part in parts:
        if not part:
            continue
        asset = asset_map.get(part)
        if asset is None:
            replacement_elements.append(_build_text_run_element(paragraph, template_run_element, part))
            continue
        replacement_elements.extend(
            _build_insertion_run_elements(paragraph, template_run_element, asset, placeholder_text=part)
        )
    return replacement_elements


def _append_image_insertions_to_paragraph(paragraph, asset: ImageAsset, *, placeholder_text: str) -> None:
    insertions = resolve_image_insertions(asset)
    if not insertions:
        paragraph.add_run(placeholder_text)
        return

    if len(insertions) > 1:
        paragraph.add_run(placeholder_text)
        return

    add_picture_kwargs = _build_picture_size_kwargs(asset)
    run = paragraph.add_run()
    run.add_picture(BytesIO(insertions[0][1]), **add_picture_kwargs)
    if insertions[0][0]:
        _set_picture_description(run._element, insertions[0][0])


def _build_insertion_run_elements(paragraph, template_run_element, asset: ImageAsset, *, placeholder_text: str):
    insertions = resolve_image_insertions(asset)
    if not insertions:
        return [_build_text_run_element(paragraph, template_run_element, placeholder_text)]

    if len(insertions) > 1:
        return [_build_text_run_element(paragraph, template_run_element, placeholder_text)]

    add_picture_kwargs = _build_picture_size_kwargs(asset)
    return [
        _build_picture_run_element(
            paragraph,
            template_run_element,
            insertions[0][1],
            add_picture_kwargs,
            description=insertions[0][0],
        )
    ]


def _build_text_run_element(paragraph, template_run_element, text: str):
    run_element = OxmlElement("w:r")
    _copy_run_properties(template_run_element, run_element)
    Run(run_element, paragraph).text = text.replace("<br/>", "\n")
    return run_element


def _build_picture_run_element(
    paragraph,
    template_run_element,
    image_bytes: bytes,
    add_picture_kwargs: dict[str, Emu],
    *,
    description: str | None = None,
):
    run_element = OxmlElement("w:r")
    _copy_run_properties(template_run_element, run_element)
    Run(run_element, paragraph).add_picture(BytesIO(image_bytes), **add_picture_kwargs)
    if description:
        _set_picture_description(run_element, description)
    return run_element


def _copy_run_properties(template_run_element, target_run_element) -> None:
    run_properties = _find_child_element(template_run_element, "rPr")
    if run_properties is not None:
        target_run_element.append(deepcopy(run_properties))


def _replace_xml_element_with_sequence(element, replacements) -> None:
    if not replacements:
        return
    parent = element.getparent()
    if parent is None:
        return

    anchor = element
    for replacement in replacements:
        anchor.addnext(replacement)
        anchor = replacement
    parent.remove(element)


def _replace_multi_variant_placeholders_with_tables(paragraph, asset_map: dict[str, ImageAsset]) -> bool:
    paragraph_children = [child for child in list(paragraph._element) if _xml_local_name(child.tag) in {"r", "hyperlink"}]
    if not paragraph_children:
        return False

    child_texts = [_extract_paragraph_child_text(child) for child in paragraph_children]
    full_text = "".join(child_texts)
    placeholder_matches = [
        match
        for match in IMAGE_PLACEHOLDER_PATTERN.finditer(full_text)
        if match.group(0) in asset_map
    ]
    if not placeholder_matches:
        return False

    if not any(len(resolve_image_insertions(asset_map[match.group(0)])) > 1 for match in placeholder_matches):
        return False

    fragments: list[etree._Element | tuple[str, ImageAsset]] = []
    child_ranges: list[tuple[etree._Element, str, int, int]] = []
    cursor = 0
    for child, child_text in zip(paragraph_children, child_texts):
        next_cursor = cursor + len(child_text)
        child_ranges.append((child, child_text, cursor, next_cursor))
        cursor = next_cursor

    match_index = 0
    current_match = placeholder_matches[match_index]

    for child, child_text, child_start, child_end in child_ranges:
        position = child_start
        while position < child_end:
            while current_match is not None and current_match.end() <= position:
                match_index += 1
                current_match = placeholder_matches[match_index] if match_index < len(placeholder_matches) else None

            if current_match is not None and position >= current_match.start() and position < current_match.end():
                if position == current_match.start():
                    placeholder_text = current_match.group(0)
                    asset = asset_map[placeholder_text]
                    insertions = resolve_image_insertions(asset)
                    if len(insertions) > 1:
                        fragments.append(("table", asset))
                    elif _xml_local_name(child.tag) == "r":
                        fragments.extend(
                            _build_insertion_run_elements(
                                paragraph,
                                child,
                                asset,
                                placeholder_text=placeholder_text,
                            )
                        )
                position = min(child_end, current_match.end())
                continue

            segment_end = child_end
            if current_match is not None and position < current_match.start():
                segment_end = min(segment_end, current_match.start())

            if segment_end > position:
                if _xml_local_name(child.tag) == "hyperlink":
                    if position != child_start or segment_end != child_end:
                        return False
                    fragments.append(deepcopy(child))
                else:
                    fragments.append(_build_text_run_element(paragraph, child, full_text[position:segment_end]))
            position = segment_end

    replacement_blocks = _build_replacement_blocks_from_fragments(paragraph, fragments)
    if not replacement_blocks:
        return False

    anchor = cast(etree._Element, paragraph._element)
    for block in replacement_blocks:
        anchor.addnext(block)
        anchor = block
    paragraph._element.getparent().remove(paragraph._element)
    return True


def _build_replacement_blocks_from_fragments(
    paragraph,
    fragments: list[etree._Element | tuple[str, ImageAsset]],
) -> list[etree._Element]:
    replacement_blocks: list[etree._Element] = []
    current_paragraph = None

    def flush_current_paragraph() -> None:
        nonlocal current_paragraph
        if current_paragraph is not None and _paragraph_element_has_content(current_paragraph):
            replacement_blocks.append(current_paragraph)
        current_paragraph = None

    for fragment in fragments:
        if isinstance(fragment, tuple) and len(fragment) == 2 and fragment[0] == "table":
            flush_current_paragraph()
            table_element = _build_variant_table_element(paragraph, fragment[1])
            if table_element is not None:
                replacement_blocks.append(table_element)
            continue

        if current_paragraph is None:
            current_paragraph = _clone_paragraph_element(paragraph)
        current_paragraph.append(fragment)

    flush_current_paragraph()
    return replacement_blocks


def _clone_paragraph_element(paragraph):
    paragraph_element = OxmlElement("w:p")
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    if paragraph_properties is not None:
        paragraph_element.append(deepcopy(paragraph_properties))
    return paragraph_element


def _paragraph_element_has_content(paragraph_element) -> bool:
    return any(_xml_local_name(child.tag) != "pPr" for child in paragraph_element)


def _extract_paragraph_child_text(child) -> str:
    if _xml_local_name(child.tag) == "hyperlink":
        return "".join(_extract_run_text(run_element) for run_element in child.xpath("./w:r"))
    return _extract_run_text(child)


def _build_variant_table_element(paragraph, asset: ImageAsset):
    insertions = resolve_image_insertions(asset)
    if not insertions:
        return None
    tbl = OxmlElement("w:tbl")
    tbl_pr = OxmlElement("w:tblPr")
    tbl.append(tbl_pr)

    tbl_grid = OxmlElement("w:tblGrid")
    for _ in range(len(insertions)):
        grid_col = OxmlElement("w:gridCol")
        tbl_grid.append(grid_col)
    tbl.append(tbl_grid)

    row = OxmlElement("w:tr")
    tbl.append(row)

    add_picture_kwargs = _build_picture_size_kwargs(asset)
    for label, image_bytes in insertions:
        cell = OxmlElement("w:tc")
        cell_properties = OxmlElement("w:tcPr")
        cell.append(cell_properties)

        image_paragraph = OxmlElement("w:p")
        paragraph_properties = OxmlElement("w:pPr")
        alignment = OxmlElement("w:jc")
        alignment.set(qn("w:val"), "center")
        paragraph_properties.append(alignment)
        image_paragraph.append(paragraph_properties)

        image_run = OxmlElement("w:r")
        Run(image_run, paragraph).add_picture(BytesIO(image_bytes), **add_picture_kwargs)
        if label:
            _set_picture_description(image_run, label)

        image_paragraph.append(image_run)
        cell.append(image_paragraph)
        row.append(cell)

    table = Table(tbl, paragraph._parent)
    _configure_variant_table_layout(table)
    return tbl


def _configure_variant_table_layout(table) -> None:
    table.autofit = True
    table_properties = table._element.tblPr
    if table_properties is None:
        table_properties = OxmlElement("w:tblPr")
        table._element.insert(0, table_properties)

    borders = _find_child_element(table_properties, "tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        table_properties.append(borders)
    else:
        for child in list(borders):
            borders.remove(child)

    for edge_name in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{edge_name}")
        border.set(qn("w:val"), "nil")
        borders.append(border)


def _set_picture_description(run_element, description: str) -> None:
    if not description:
        return

    doc_properties = run_element.xpath(".//wp:docPr")
    if not doc_properties:
        return

    doc_properties[-1].set("descr", description)

def resolve_final_image_bytes(asset: ImageAsset) -> bytes:
    if asset.selected_compare_variant:
        if asset.selected_compare_variant == "original":
            return asset.original_bytes
        selected_variant = asset.comparison_variants.get(asset.selected_compare_variant)
        selected_bytes = get_image_variant_bytes(selected_variant)
        if selected_bytes:
            return selected_bytes
    if asset.final_variant == "redrawn" and asset.redrawn_bytes:
        return asset.redrawn_bytes
    if asset.final_variant == "safe" and asset.safe_bytes:
        return asset.safe_bytes
    return asset.original_bytes


def resolve_image_insertions(asset: ImageAsset) -> list[tuple[str | None, bytes]]:
    if getattr(asset, "validation_status", None) == "compared" and getattr(asset, "comparison_variants", None):
        insertions: list[tuple[str | None, bytes]] = []
        for mode in ["safe", "semantic_redraw_direct", "semantic_redraw_structured"]:
            variant = asset.comparison_variants.get(mode)
            variant_bytes = get_image_variant_bytes(variant)
            if variant_bytes:
                insertions.append((COMPARE_ALL_VARIANT_LABELS[mode], variant_bytes))
        if insertions:
            return insertions

    if bool(getattr(getattr(asset, "metadata", None), "preserve_all_variants_in_docx", False)):
        # Manual review mode keeps the conservative safe result plus every
        # generated semantic candidate so fallback decisions can be inspected in
        # the final DOCX without rerunning the pipeline.
        insertions: list[tuple[str | None, bytes]] = []
        if asset.safe_bytes:
            insertions.append((MANUAL_REVIEW_SAFE_LABEL, asset.safe_bytes))
        for variant in list(getattr(asset, "attempt_variants", []))[:2]:
            variant_label = str(getattr(variant, "mode", "")).strip() or None
            variant_bytes = get_image_variant_bytes(variant)
            if variant_label and variant_bytes:
                insertions.append((variant_label, variant_bytes))
        if insertions:
            return insertions

    final_bytes = resolve_final_image_bytes(asset)
    if not final_bytes:
        return []
    return [(None, final_bytes)]


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
            heading_level = 2
            heading_source = "heuristic"
    role = classify_paragraph_role(text, style_name, heading_level=heading_level)
    list_metadata = _extract_paragraph_list_metadata(paragraph, text, style_name, role)
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
    try:
        source_bytes = read_uploaded_file_bytes(uploaded_file)
    except ValueError as exc:
        raise ValueError("Не удалось прочитать содержимое DOCX-файла.") from exc
    return source_bytes


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


def _is_probable_heading(paragraph, text: str, normalized_style: str) -> bool:
    stripped_text = text.strip()
    if not stripped_text or len(stripped_text) > 140:
        return False
    word_count = len(stripped_text.split())
    if word_count > 18:
        return False
    if stripped_text.endswith(("!", "?", ";")):
        return False
    if stripped_text.endswith(".") and word_count > 10:
        return False
    if stripped_text.count(".") > 1:
        return False
    has_strong_format = _paragraph_has_strong_heading_format(paragraph)
    if normalized_style in {"body text", "normal"} and not has_strong_format:
        return False
    if not has_strong_format:
        return False
    return _has_heading_text_signal(stripped_text)


def _has_heading_text_signal(text: str) -> bool:
    stripped_text = text.strip()
    word_count = len(stripped_text.split())
    lower_text = stripped_text.lower()

    if re.match(r"^(?:глава|раздел|часть|приложение|chapter|section|appendix)\b", lower_text):
        return True
    if re.match(r"^\d+(?:\.\d+){0,4}(?:[\):]|\s)", stripped_text):
        return True
    if ":" in stripped_text and word_count <= 12 and not stripped_text.endswith("."):
        return True
    if word_count <= 4 and stripped_text[-1:] not in ".!?;:" and stripped_text[:1].isupper():
        return True
    return False


def _paragraph_has_strong_heading_format(paragraph) -> bool:
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    alignment = _find_child_element(paragraph_properties, "jc")
    alignment_value = _get_xml_attribute(alignment, "val") if alignment is not None else None
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


def _normalize_output_paragraph(document, paragraph, source_paragraph: ParagraphUnit) -> None:
    if source_paragraph.role == "heading":
        level = min(max(source_paragraph.heading_level or 1, 1), 6)
        heading_style = f"Heading {level}"
        if _style_exists(document, heading_style):
            paragraph.style = document.styles[heading_style]
        return

    if source_paragraph.role == "caption":
        if _style_exists(document, "Caption"):
            paragraph.style = document.styles["Caption"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return

    if source_paragraph.role == "image":
        if _style_exists(document, "Normal"):
            paragraph.style = document.styles["Normal"]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        return

    if source_paragraph.role == "list":
        if _style_exists(document, "List Paragraph"):
            paragraph.style = document.styles["List Paragraph"]
        return

    if _style_exists(document, "Body Text"):
        paragraph.style = document.styles["Body Text"]
    elif _style_exists(document, "Normal"):
        paragraph.style = document.styles["Normal"]


def _restore_list_numbering_for_mapped_paragraphs(document, mapping_pairs: list[tuple[ParagraphUnit, Paragraph]]) -> list[dict[str, object]]:
    numbering_root = _get_target_numbering_root(document)
    decisions: list[dict[str, object]] = []
    if numbering_root is None:
        for source_paragraph, _ in mapping_pairs:
            if source_paragraph.role != "list":
                continue
            decisions.append(
                {
                    "paragraph_id": source_paragraph.paragraph_id,
                    "text_preview": _paragraph_preview(source_paragraph.text),
                    "action": "target_numbering_part_missing",
                }
            )
        return decisions

    numbering_id_map: dict[tuple[str, str, str, str], tuple[int, int]] = {}
    next_abstract_num_id = _next_numbering_identifier(numbering_root, "abstractNum", "abstractNumId")
    next_num_id = _next_numbering_identifier(numbering_root, "num", "numId")

    for source_paragraph, target_paragraph in mapping_pairs:
        if source_paragraph.role != "list":
            continue
        if not source_paragraph.list_num_xml or not source_paragraph.list_abstract_num_xml:
            decisions.append(
                {
                    "paragraph_id": source_paragraph.paragraph_id,
                    "text_preview": _paragraph_preview(source_paragraph.text),
                    "action": "missing_source_numbering_xml",
                    "list_kind": source_paragraph.list_kind,
                    "list_level": source_paragraph.list_level,
                }
            )
            continue

        mapping_key = (
            source_paragraph.list_num_id or "",
            source_paragraph.list_abstract_num_id or "",
            source_paragraph.list_num_xml,
            source_paragraph.list_abstract_num_xml,
        )
        mapped_ids = numbering_id_map.get(mapping_key)
        if mapped_ids is None:
            abstract_num_id = next_abstract_num_id
            num_id = next_num_id
            next_abstract_num_id += 1
            next_num_id += 1
            if not _append_numbering_definition(numbering_root, source_paragraph, abstract_num_id, num_id):
                decisions.append(
                    {
                        "paragraph_id": source_paragraph.paragraph_id,
                        "text_preview": _paragraph_preview(source_paragraph.text),
                        "action": "append_definition_failed",
                        "list_kind": source_paragraph.list_kind,
                        "list_level": source_paragraph.list_level,
                    }
                )
                continue
            mapped_ids = (abstract_num_id, num_id)
            numbering_id_map[mapping_key] = mapped_ids

        _apply_list_numbering_to_paragraph(target_paragraph, list_level=source_paragraph.list_level, num_id=mapped_ids[1])
        decisions.append(
            {
                "paragraph_id": source_paragraph.paragraph_id,
                "text_preview": _paragraph_preview(source_paragraph.text),
                "action": "restored",
                "list_kind": source_paragraph.list_kind,
                "list_level": source_paragraph.list_level,
                "target_num_id": mapped_ids[1],
                "target_abstract_num_id": mapped_ids[0],
            }
        )

    return decisions


def _get_target_numbering_root(document):
    numbering_part = getattr(document.part, "numbering_part", None)
    return getattr(numbering_part, "element", None)


def _next_numbering_identifier(numbering_root, tag_name: str, attribute_name: str) -> int:
    max_identifier = 0
    for child in numbering_root:
        if _xml_local_name(child.tag) != tag_name:
            continue
        value = _get_xml_attribute(child, attribute_name)
        try:
            max_identifier = max(max_identifier, int(value or "0"))
        except ValueError:
            continue
    return max_identifier + 1


def _append_numbering_definition(numbering_root, source_paragraph: ParagraphUnit, abstract_num_id: int, num_id: int) -> bool:
    try:
        abstract_num_element = parse_xml(source_paragraph.list_abstract_num_xml or "")
        num_element = parse_xml(source_paragraph.list_num_xml or "")
    except Exception:
        return False

    abstract_num_element.set(qn("w:abstractNumId"), str(abstract_num_id))
    num_element.set(qn("w:numId"), str(num_id))

    abstract_num_id_element = _find_child_element(num_element, "abstractNumId")
    if abstract_num_id_element is None:
        abstract_num_id_element = OxmlElement("w:abstractNumId")
        num_element.insert(0, abstract_num_id_element)
    abstract_num_id_element.set(qn("w:val"), str(abstract_num_id))

    numbering_root.append(abstract_num_element)
    numbering_root.append(num_element)
    return True


def _apply_list_numbering_to_paragraph(paragraph, *, list_level: int, num_id: int) -> None:
    paragraph_properties = _ensure_paragraph_properties(paragraph)
    existing_num_pr = _find_child_element(paragraph_properties, "numPr")
    if existing_num_pr is not None:
        paragraph_properties.remove(existing_num_pr)

    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(max(0, list_level)))
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num_id_element)
    paragraph_properties.append(num_pr)


def _style_exists(document, style_name: str) -> bool:
    try:
        document.styles[style_name]
    except KeyError:
        return False
    return True


def _apply_preserved_paragraph_properties(paragraph, preserved_ppr_xml: tuple[str, ...]) -> None:
    if not preserved_ppr_xml:
        return

    paragraph_properties = _ensure_paragraph_properties(paragraph)
    for child in list(paragraph_properties):
        if _xml_local_name(child.tag) in PRESERVED_PARAGRAPH_PROPERTY_NAMES:
            paragraph_properties.remove(child)

    for xml_fragment in preserved_ppr_xml:
        try:
            paragraph_properties.append(parse_xml(xml_fragment))
        except Exception:
            continue


def _ensure_paragraph_properties(paragraph):
    paragraph_properties = _find_child_element(paragraph._element, "pPr")
    if paragraph_properties is not None:
        return paragraph_properties

    paragraph_properties = OxmlElement("w:pPr")
    paragraph._element.insert(0, paragraph_properties)
    return paragraph_properties


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
                f"img_{image_index:03d}",
                placeholder,
                image_blob,
                mime_type,
                image_index - 1,
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
    if role != "list":
        return metadata

    explicit_kind = _detect_explicit_list_kind(text)
    if explicit_kind is not None:
        metadata["list_kind"] = explicit_kind
        # Still try to capture Word numbering XML so DOCX list restoration works
        # even when the source paragraph already has visible text markers in its text.
        # Per spec: numbered lists must be restored as real Word lists even if visible
        # markdown markers are present.
        num_pr = _resolve_paragraph_num_pr(paragraph)
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

    style_level = _extract_style_list_level(style_name)
    num_pr = _resolve_paragraph_num_pr(paragraph)
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
