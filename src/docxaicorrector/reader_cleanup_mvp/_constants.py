from __future__ import annotations

import re
from typing import Literal


CleanupPolicy = Literal["off", "advisory", "strict"]
CleanupConfidence = Literal["low", "medium", "high"]

READER_CLEANUP_DEFAULT_SELECTOR = "openrouter:google/gemini-3-flash-preview"
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
    "reclassify_role",
}
_ALLOWED_RECLASSIFY_TARGET_ROLES = {"heading", "body", "attribution", "caption"}
_ALLOWED_REANNOTATION_ROLES = {"heading", "body", "list_item", "caption", "footnote"}
_RECLASSIFY_MARKDOWN_HEADING_PREFIX = "## "
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
    "target_role",
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
_TOC_LIKE_PATTERN = re.compile(r"(?:\.{3,}|…{2,}|\s\d{1,4}\s*$)")
_EXTRACTION_ARTIFACT_PATTERN = re.compile(
    r"^(?:\[\[DOCX_[A-Za-z0-9_]+\]\]|\[\[IMAGE_[A-Za-z0-9_]+\]\]|<\/?placeholder>|---+|===+)$",
    re.IGNORECASE,
)
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
