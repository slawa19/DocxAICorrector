import re

from models import ParagraphUnit


CAPTION_PREFIX_PATTERN = re.compile(r"^(?:рис\.?|рисунок|figure|fig\.?|табл\.?|таблица|table)\b", re.IGNORECASE)
HEADING_STYLE_PATTERN = re.compile(r"^(?:heading|заголовок)\s*(\d+)?$", re.IGNORECASE)
IMAGE_ONLY_PATTERN = re.compile(r"^(?:\s*\[\[DOCX_IMAGE_img_\d+\]\]\s*)+$")
INLINE_HTML_TAG_PATTERN = re.compile(r"</?(?:u|sup|sub)>", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^\)]+\)")


def classify_paragraph_role(text: str, style_name: str, *, heading_level: int | None = None) -> str:
    normalized_style = style_name.strip().lower()
    stripped_text = text.lstrip()

    if is_image_only_text(text):
        return "image"

    if heading_level is not None:
        return "heading"

    if is_caption_style(normalized_style):
        return "caption"

    if "list" in normalized_style or "спис" in normalized_style:
        return "list"

    if stripped_text.startswith(("- ", "* ", "• ")):
        return "list"

    if re.match(r"^\d+[\.)]\s+", stripped_text):
        return "list"

    return "body"


def infer_role_confidence(
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
        return "explicit" if is_caption_style(normalized_style) else "heuristic"
    if role == "list":
        if "list" in normalized_style or "спис" in normalized_style or detect_explicit_list_kind(text) is not None:
            return "explicit"
    return "heuristic"


def extract_explicit_heading_level(paragraph, style_name: str) -> int | None:
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

    outline_level = resolve_paragraph_outline_level(paragraph)
    if outline_level is not None:
        return outline_level
    return None


def resolve_paragraph_outline_level(paragraph) -> int | None:
    outline_element = _find_paragraph_property_element(paragraph, "outlineLvl")
    outline_value = get_xml_attribute(outline_element, "val") if outline_element is not None else None
    try:
        if outline_value is None:
            return None
        return max(1, min(int(outline_value) + 1, 6))
    except (TypeError, ValueError):
        return None


def resolve_paragraph_alignment(paragraph) -> str | None:
    alignment = _find_paragraph_property_element(paragraph, "jc")
    return get_xml_attribute(alignment, "val") if alignment is not None else None


def infer_heuristic_heading_level(text: str) -> int:
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


def is_probable_heading(paragraph, text: str, normalized_style: str) -> bool:
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
    has_strong_format = paragraph_has_strong_heading_format(paragraph)
    if normalized_style in {"body text", "normal"} and not has_strong_format:
        return False
    if not has_strong_format:
        return False
    if is_caption_style(normalized_style):
        return False
    resolved_alignment = resolve_paragraph_alignment(paragraph)
    if word_count <= 8 and len(stripped_text) <= 100:
        if resolved_alignment == "center" and word_count > 2 and not _has_heading_text_signal(stripped_text):
            return False
        return _has_heading_text_signal(stripped_text) or resolved_alignment == "center"
    return _has_heading_text_signal(stripped_text)


def has_heading_text_signal(text: str) -> bool:
    return _has_heading_text_signal(text)


def paragraph_has_strong_heading_format(paragraph) -> bool:
    alignment_value = resolve_paragraph_alignment(paragraph)
    if alignment_value == "center":
        return True
    return _paragraph_is_effectively_bold(paragraph)


def paragraph_is_effectively_bold(paragraph) -> bool:
    return _paragraph_is_effectively_bold(paragraph)


def paragraph_is_effectively_italic(paragraph) -> bool:
    visible_runs = [run for run in paragraph.runs if run.text and run.text.strip()]
    if not visible_runs:
        return False

    italic_runs = [run for run in visible_runs if bool(run.italic)]
    if len(italic_runs) == len(visible_runs):
        return True

    visible_chars = sum(len(run.text.strip()) for run in visible_runs)
    italic_chars = sum(len(run.text.strip()) for run in italic_runs)
    return bool(italic_runs) and visible_chars > 0 and (italic_chars / visible_chars) >= 0.5


def is_image_only_text(text: str) -> bool:
    return IMAGE_ONLY_PATTERN.fullmatch(text.strip()) is not None


def is_caption_style(normalized_style: str) -> bool:
    return normalized_style in {"caption", "подпись"} or "caption" in normalized_style or "подпись" in normalized_style


def is_likely_caption_text(text: str) -> bool:
    stripped_text = text.strip()
    if not stripped_text or len(stripped_text) > 140:
        return False
    return CAPTION_PREFIX_PATTERN.match(stripped_text) is not None


def resolve_effective_paragraph_font_size(paragraph) -> float | None:
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


def promote_short_standalone_headings(paragraphs: list[ParagraphUnit]) -> None:
    if len(paragraphs) < 3:
        return

    for index in range(1, len(paragraphs) - 1):
        paragraph = paragraphs[index]
        if paragraph.role != "body":
            continue
        if paragraph.role_confidence == "ai":
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

        candidate_font_size = paragraph.font_size_pt
        if candidate_font_size is None:
            continue

        context_font_sizes: list[float] = []
        previous_font_size = paragraphs[index - 1].font_size_pt
        if previous_font_size is not None:
            context_font_sizes.append(previous_font_size)
        next_font_size = paragraphs[index + 1].font_size_pt
        if next_font_size is not None:
            context_font_sizes.append(next_font_size)
        if not context_font_sizes:
            continue

        required_delta = 1.0 if _paragraph_unit_has_strong_heading_format(paragraph) else 1.5
        if candidate_font_size < max(context_font_sizes) + required_delta:
            continue

        paragraph.role = "heading"
        paragraph.structural_role = "heading"
        paragraph.role_confidence = "heuristic"
        paragraph.heading_source = "heuristic"
        paragraph.heading_level = _infer_contextual_heading_level(paragraphs, index)


def normalize_front_matter_display_title(paragraphs: list[ParagraphUnit]) -> None:
    scan_limit = min(len(paragraphs), 12)
    if scan_limit == 0:
        return

    candidate_index = _find_front_matter_display_title_candidate(paragraphs[:scan_limit])
    if candidate_index is None:
        return

    candidate = paragraphs[candidate_index]
    candidate.role = "heading"
    candidate.structural_role = "heading"
    candidate.role_confidence = "heuristic"
    candidate.heading_source = "heuristic"
    candidate.heading_level = 1

    candidate_font_size = candidate.font_size_pt
    for index in range(scan_limit):
        if index == candidate_index:
            continue
        paragraph = paragraphs[index]
        if paragraph.role != "heading":
            continue
        if not _is_front_matter_metadata_heading_candidate(paragraph, candidate_font_size):
            continue

        paragraph.role = "body"
        paragraph.structural_role = "body"
        paragraph.role_confidence = "heuristic"
        paragraph.heading_source = None
        paragraph.heading_level = None


def reclassify_adjacent_captions(paragraphs: list[ParagraphUnit]) -> None:
    for index, paragraph in enumerate(paragraphs):
        if index == 0:
            continue
        previous_paragraph = paragraphs[index - 1]
        if previous_paragraph.role not in {"image", "table"}:
            continue
        if paragraph.role == "caption":
            continue
        if is_likely_caption_text(paragraph.text):
            if paragraph.role == "heading" and paragraph.heading_source != "heuristic":
                continue
            paragraph.role = "caption"
            paragraph.structural_role = "caption"
            paragraph.role_confidence = "adjacent"
            paragraph.heading_level = None
            paragraph.heading_source = None


def detect_explicit_list_kind(text: str) -> str | None:
    stripped_text = text.lstrip()
    if stripped_text.startswith(("- ", "* ", "• ")):
        return "unordered"
    if re.match(r"^\d+[\.)]\s+", stripped_text):
        return "ordered"
    return None


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def find_child_element(parent, local_name: str):
    if parent is None:
        return None
    for child in parent:
        if xml_local_name(child.tag) == local_name:
            return child
    return None


def get_xml_attribute(element, attribute_name: str) -> str | None:
    if element is None:
        return None
    for key, value in element.attrib.items():
        if xml_local_name(key) == attribute_name:
            return value
    return None


def _find_paragraph_property_element(paragraph, local_name: str):
    paragraph_properties = find_child_element(paragraph._element, "pPr")
    element = find_child_element(paragraph_properties, local_name)
    if element is not None:
        return element

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = find_child_element(getattr(style, "_element", None), "pPr")
        element = find_child_element(style_properties, local_name)
        if element is not None:
            return element
        style = getattr(style, "base_style", None)
    return None


def _normalize_text_for_heading_heuristics(text: str) -> str:
    normalized = MARKDOWN_LINK_PATTERN.sub(r"\1", text)
    normalized = INLINE_HTML_TAG_PATTERN.sub("", normalized)
    normalized = normalized.replace("**", "").replace("*", "")
    return normalized.strip()


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


def _paragraph_is_effectively_bold(paragraph) -> bool:
    visible_runs = [run for run in paragraph.runs if run.text and run.text.strip()]
    if not visible_runs:
        return False

    bold_runs = [run for run in visible_runs if bool(run.bold)]
    if len(bold_runs) == len(visible_runs):
        return True

    visible_chars = sum(len(run.text.strip()) for run in visible_runs)
    bold_chars = sum(len(run.text.strip()) for run in bold_runs)
    return bool(bold_runs) and visible_chars > 0 and (bold_chars / visible_chars) >= 0.5


def _paragraph_unit_has_strong_heading_format(paragraph: ParagraphUnit) -> bool:
    return paragraph.paragraph_alignment == "center" or paragraph.is_bold


def _is_short_standalone_heading_text(text: str) -> bool:
    stripped_text = _normalize_text_for_heading_heuristics(text)
    if not stripped_text or len(stripped_text) > 80:
        return False
    if is_likely_caption_text(stripped_text):
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


def _infer_contextual_heading_level(paragraphs: list[ParagraphUnit], index: int) -> int:
    for previous_index in range(index - 1, -1, -1):
        previous_paragraph = paragraphs[previous_index]
        if previous_paragraph.role != "heading" or previous_paragraph.heading_level is None:
            continue
        if previous_paragraph.heading_level <= 1:
            return 2
        return previous_paragraph.heading_level
    return 2


def _find_front_matter_display_title_candidate(paragraphs: list[ParagraphUnit]) -> int | None:
    best_index: int | None = None
    best_score: tuple[float, int, int] | None = None

    for index, paragraph in enumerate(paragraphs):
        if not _is_front_matter_display_title_candidate(paragraph):
            continue

        normalized = _normalize_text_for_heading_heuristics(paragraph.text)
        alpha_chars = sum(1 for char in normalized if char.isalpha())
        font_size = float(paragraph.font_size_pt or 0.0)
        score = (font_size, alpha_chars, len(normalized))
        if best_score is None or score > best_score:
            best_index = index
            best_score = score

    return best_index


def _is_front_matter_display_title_candidate(paragraph: ParagraphUnit) -> bool:
    if paragraph.role in {"image", "table", "caption", "list"}:
        return False
    if paragraph.attached_to_asset_id is not None:
        return False
    if paragraph.structural_role in {"toc_header", "toc_entry", "image", "table", "caption"}:
        return False

    normalized = _normalize_text_for_heading_heuristics(paragraph.text)
    if not normalized or len(normalized) > 180:
        return False
    if is_likely_caption_text(normalized):
        return False
    if normalized.endswith((".", ";", "!", "?")):
        return False

    alpha_chars = sum(1 for char in normalized if char.isalpha())
    if alpha_chars < 8:
        return False
    if all(not char.isalpha() for char in normalized):
        return False

    font_size = paragraph.font_size_pt
    if font_size is None or font_size < 18.0:
        return False
    return True


def _is_front_matter_metadata_heading_candidate(paragraph: ParagraphUnit, title_font_size: float | None) -> bool:
    if paragraph.heading_level != 1:
        return False

    normalized = _normalize_text_for_heading_heuristics(paragraph.text)
    if not normalized:
        return False
    if _has_heading_text_signal(normalized):
        return False
    if len(normalized.split()) > 6:
        return False

    alpha_chars = sum(1 for char in normalized if char.isalpha())
    if alpha_chars == 0:
        return False
    if title_font_size is not None and paragraph.font_size_pt is not None and paragraph.font_size_pt > title_font_size:
        return False
    return True
