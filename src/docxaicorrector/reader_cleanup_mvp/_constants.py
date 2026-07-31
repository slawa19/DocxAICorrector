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
# Spec 052 item 6. The old pattern was ``(?:\.{3,}|…{2,}|\s\d{1,4}\s*$)`` and a TOC-like
# block is immune to every operation, so both of its branches leaked prose:
#
#   * ``\s\d{1,4}\s*$`` made ANY paragraph ending in a space and a number TOC-like —
#     e.g. lietaer b_000871, 922 characters of prose ending "...миллениалов 2000".
#   * ``\.{3,}`` fired on an ellipsis typed as three periods, so lietaer b_000006 — the
#     3 481-character block of jacket endorsements containing "разрушительный рост..." —
#     was TOC-like too. That is the block the spec cites.
#
# Both branches now require what actually distinguishes a contents line: a PAGE NUMBER.
# A leader must be followed by one; a bare trailing number is accepted only on a single
# line short enough to be one entry. Longer real contents/index runs do exist (lietaer's
# table of contents is 140-163 chars, its subject index runs to 900), and they are
# recovered by the page-reference density rule in ``_utils._is_toc_like_text`` — length
# does not separate them from prose, page-number density does.
_TOC_ENTRY_MAX_CHARS = 100
_TOC_LIKE_PATTERN = re.compile(
    r"(?:(?:\.{3,}|…{2,})\s*\d{1,4}|\A(?=.{1," + str(_TOC_ENTRY_MAX_CHARS) + r"}\Z).*\s\d{1,4}\s*\Z)"
)
# A contents/index run: it carries contents punctuation (a trailing page number or a
# leader), AND page references are dense enough that it cannot be read as a sentence.
# Prose that merely ends in a number, or merely contains an ellipsis, clears one bar but
# never both.
_TOC_PAGE_REFERENCE_TAIL_PATTERN = re.compile(r"(?:\s\d{1,4}\s*\Z|\.{3,}|…{2,})")
_TOC_PAGE_REFERENCE_TOKEN_PATTERN = re.compile(r"\d{1,4}")
_TOC_MIN_PAGE_REFERENCE_TOKENS = 3
_TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO = 0.15
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
