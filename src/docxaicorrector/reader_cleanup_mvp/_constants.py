from __future__ import annotations

import re
from typing import Literal


CleanupPolicy = Literal["off", "advisory", "strict"]
CleanupConfidence = Literal["low", "medium", "high"]

# Last-resort selector, used only when app_config carries no reader_cleanup_model at
# all. Kept identical to resources/config.toml so model resolution has ONE answer:
# the selector all three measured replay runs used (spec 052 item 1).
READER_CLEANUP_DEFAULT_SELECTOR = "openrouter:anthropic/claude-haiku-4.5"
_ALLOWED_POLICIES = {"off", "advisory", "strict"}
_ALLOWED_CONFIDENCE = {"low", "medium", "high"}
_ALLOWED_DELETE_REASONS = {
    "blank_page_marker",
    "duplicate_fragment",
    "extraction_artifact",
    "orphan_footnote_marker",
    "page_furniture_heading",
    "page_number",
    "repeated_running_header",
}
_INLINE_NOISE_REASON_GUIDANCE = {
    "page_furniture_inline",
    "page_furniture_heading",
    "page_number",
    "repeated_running_header",
}
_REMOVE_INLINE_NOISE_REASON_GUIDANCE = _INLINE_NOISE_REASON_GUIDANCE | {
    "duplicate_fragment",
    "orphan_footnote_marker",
}
_ALLOWED_OPERATIONS = {
    "delete_block",
    "extract_side_heading_and_reattach_body",
    "split_block",
    "remove_inline_noise",
    "join_fragmented_paragraph",
    "normalize_heading_boundary",
}
_ALLOWED_REANNOTATION_ROLES = {"heading", "body", "list_item", "caption", "footnote"}
_TOP_LEVEL_RESPONSE_FIELDS = {"cleanup_operations", "delete_blocks", "warnings"}
_BLOCK_RESPONSE_FIELDS = {"id", "text_hash", "reason", "confidence"}
_OPERATION_RESPONSE_FIELDS = {
    "id",
    "text_hash",
    "operation",
    "reason",
    "confidence",
    "evidence_before",
    "expected_after_preview",
    "safety_note",
    "split_substrings",
    "noise_substring",
    "next_id",
    "next_text_hash",
    "pre_body_stub",
    "heading_substring",
    "body_substring",
    "post_body_continuation",
}
_SAFE_CONFIDENCE_INFERENCE = {
    "page_number": "page_number",
    "blank_page_marker": "blank_page_marker",
    "orphan_footnote_marker": "orphan_footnote_marker",
    "extraction_artifact": "extraction_artifact",
}
_PAGE_NUMBER_PATTERN = re.compile(r"^(?:\(?\d{1,4}\)?|[Pp]age\s+\d{1,4}|стр\.\s*\d{1,4})$")
_BLANK_PAGE_PATTERN = re.compile(r"^(?:blank\s+page|this page intentionally left blank)$", re.IGNORECASE)
_ORPHAN_FOOTNOTE_PATTERN = re.compile(r"^(?:\[?\d{1,3}\]?|\(\d{1,3}\))$")
_FOOTNOTE_BODY_PATTERN = re.compile(r"^(?:\[\d{1,3}\]|\(\d{1,3}\))\s+\S")
# A ``toc_like`` block is immune to EVERY cleanup operation, so every branch below has to
# earn that immunity. Spec 052 item 6 narrowed the rule to "a page number is required",
# but kept "one line of at most 100 characters ending in a number" as a SUFFICIENT signal,
# and that still let ordinary prose in: "Он родился в 1990", "Стоимость выросла до 10",
# "In 1990 value was 5 and in 2000 rose to 10" were all TOC-like, i.e. the pass silently
# did nothing on them. Measured on the three recorded books, that branch alone accounted
# for every one of creating_wealth's 15 "TOC" blocks (all of them prose or a notes-section
# "Глава N" header), 15 of lietaer's 68 and all 4 of mazzucato's.
#
# Length was never the discriminator — lietaer's real contents lines run to 163 characters
# and its subject index to 784. What separates contents/index material from prose is WHERE
# the numbers sit, so a bare trailing number is no longer sufficient on its own. Four
# shapes qualify, each requiring a page reference in a position prose does not produce:
#
#   1. a dotted leader terminated by a page number ("Введение ......... 12");
#   2. a block that is nothing but page numbers, ranges and separators ("99, 102",
#      "179– 180") — an index column continued across a page break;
#   3. an index run: page references introduced by a comma or semicolon ("Куритиба, 142;
#      устойчивое, 5–6, 55, 224") or written as page ranges, at least three of them and
#      dense against the word count; plus the single short entry ("Апокалипсис, 14"),
#      which needs the reference to TERMINATE the block;
#   4. a contents run: several whitespace-delimited bare page numbers, nearly all of them
#      at an entry boundary — followed by the capitalised start of the next title, by the
#      next entry's number, or by the end of the block.
#
# The narrow spellings matter and each one is paid for by a measured false positive:
# requiring a space after the comma in (3) keeps Russian decimal commas ("0,72 в 1990 г.")
# out; capping the page reference at three digits keeps bibliography years ("Forbes,
# 2017") out; requiring the contents-run tokens in (4) to be whitespace-delimited keeps
# endnote superscripts glued to a full stop ("непроизводительными.54 Тем не менее") out;
# and requiring the word after the boundary to be a plain capitalised word keeps currency
# amounts ("зачисляется 10 L15, а со счета") out.
_TOC_LEADER_ENTRY_PATTERN = re.compile(r"(?:\.{3,}|…{2,})\s*\d{1,4}\s*\Z")
_TOC_PAGE_REFERENCE_RUN_PATTERN = re.compile(r"[\d\s.,;:–—−-]+")
_TOC_PAGE_REFERENCE_TOKEN_PATTERN = re.compile(r"\d{1,4}")
# "..., 142", "...; 5", "..., 226n13" — a page reference introduced by index punctuation.
# The trailing ``(?!\w)`` is what tells "1d, 2a, 2b, 2c" (a figure-step list) from an index.
_TOC_INDEX_PAGE_REFERENCE_PATTERN = re.compile(r"[,;]\s+\d{1,3}(?:[nн]\d{1,3})?(?!\w)")
_TOC_PAGE_RANGE_PATTERN = re.compile(r"(?<!\w)\d{1,3}\s*[–—−]\s*\d{1,3}(?!\w)")
_TOC_INDEX_ENTRY_TAIL_PATTERN = re.compile(r"[,;]\s+\d{1,3}(?:\s*[–—−]\s*\d{1,3})?\s*\Z")
_TOC_MIN_PAGE_REFERENCE_TOKENS = 3
_TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO = 0.15
_TOC_SHORT_INDEX_ENTRY_MAX_WORDS = 6
# Front matter is paginated in lowercase roman numerals, and a contents line that carries
# one ("Предисловие ix Введение: ... 1", lietaer b_000020) has only two page references —
# too few for the bare-number count below, so a roman numeral lowers the bar to two. The
# numeral grammar alone is not enough: "di", "mi", "vi", "ci", "li" and "mix" are all
# well-formed roman numerals AND ordinary words, and "di" in an Italian book title was
# enough to make a bibliography line look like a contents run.
_TOC_ROMAN_PAGE_NUMBER_PATTERN = re.compile(r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{1,3})")
_TOC_ROMAN_PAGE_NUMBER_LOOKALIKE_WORDS = frozenset({"ci", "di", "li", "mi", "mix", "vi"})
_TOC_MIN_CONTENTS_ENTRY_TOKENS = 3
_TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN = 2
_TOC_MIN_CONTENTS_ENTRY_BOUNDARY_RATIO = 0.8
_TOC_ENTRY_BOUNDARY_TRIM_CHARS = "«»\"'“”„‟()[]{}.,;:!?—–-*_"
_EXTRACTION_ARTIFACT_PATTERN = re.compile(
    r"^(?:\[\[DOCX_[A-Za-z0-9_]+\]\]|\[\[IMAGE_[A-Za-z0-9_]+\]\]|<\/?placeholder>|---+|===+)$",
    re.IGNORECASE,
)
# Spec 052 item 4. ``_EXTRACTION_ARTIFACT_PATTERN`` above matches ``[[DOCX_IMAGE_*]]``
# too, and on the three measured books EVERY block it classified was an image anchor
# (43/43, 55/55, 24/24). ``extraction_artifact`` is an allowed delete reason while the
# prompt forbids touching anchors, so payload and prompt contradicted each other and the
# only thing standing between the model and 20-37 lost images per book was a single
# validator check. Anchors now carry their own kind, which is on no deletion list.
_DOCX_IMAGE_ANCHOR_KIND = "docx_image_anchor"
_DOCX_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]")
_DOCX_IMAGE_PLACEHOLDER_ONLY_PATTERN = re.compile(r"^\s*\[\[DOCX_IMAGE_[A-Za-z0-9_]+\]\]\s*$")
_SAFE_INLINE_NOISE_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:\(?\d{1,4}\)?|[Pp]age\s+\d{1,4}|стр\.\s*\d{1,4})"
    r"|(?:\[\d{1,3}\]|\(\d{1,3}\)|\d{1,3})"
    r")\s*$"
)
_NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN = re.compile(
    r"^\s*(?:\d{1,4}\s+){1,2}(?:[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,})(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,}){0,5}\s*$"
)
_RUNNING_HEADER_TRAILING_PUNCTUATION = ".,:;!?\"'«»“”„‟"
_NUMERIC_UPPERCASE_MAX_TOKENS_WITHOUT_GENERIC_HEADER = 2
_HEADER_CONNECTOR_WORDS = {
    "a",
    "an",
    "and",
    "de",
    "del",
    "der",
    "des",
    "dla",
    "do",
    "for",
    "from",
    "i",
    "in",
    "la",
    "na",
    "of",
    "on",
    "the",
    "to",
    "von",
    "в",
    "для",
    "до",
    "и",
    "к",
    "мы",
    "на",
    "о",
    "от",
    "по",
    "с",
    "со",
    "у",
}
_GENERIC_RUNNING_HEADER_TOKENS = {
    "appendix",
    "book",
    "chapter",
    "document",
    "part",
    "section",
    "appendix",
    "глава",
    "документ",
    "книга",
    "раздел",
    "часть",
}
_ALLOWED_ANCHOR_REPAIR_CATEGORIES = {
    "heading_fused_with_body",
    "page_furniture_inline",
    "fragmented_paragraph",
}
_DUPLICATE_FRAGMENT_MIN_NON_WHITESPACE_CHARS = 24
_DUPLICATE_FRAGMENT_MAX_NEARBY_BLOCK_DISTANCE = 3
_DEFAULT_CLEANUP_CHUNK_SIZE = 8000
_DEFAULT_OVERLAP_BLOCKS_BEFORE = 3
_DEFAULT_OVERLAP_BLOCKS_AFTER = 3
_DEFAULT_GLOBAL_PLAN_ENABLED = False
# Spec 052 item 2. At the previous 1.0 the abort only triggered when literally every
# chunk failed, so 106 of 107 failures still reported stage_status="completed".
_DEFAULT_MAX_FAILED_CHUNK_RATIO = 0.1
