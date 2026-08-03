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
# The operation set a run gets when nothing says otherwise. NOT the full vocabulary:
# the first live run (2026-08-02, three books, spec 052) measured
# normalize_heading_boundary + join_fragmented_paragraph at 18 visible defects removed
# against 4 damaged, and remove_inline_noise + delete_block at 0 removed against 12
# damaged — silent data loss inside URLs, author names, bibliography years. The owner
# narrowed the default to the heading pair; the other operations stay in the code and
# still work when a config or run profile names them explicitly. An EMPTY set keeps its
# old meaning, "every operation" (`_allowed_operations_for_config`), which is how a
# research run re-enables the rest.
# Kept identical to reader_cleanup_allowed_operations in resources/config.toml.
_DEFAULT_ALLOWED_OPERATIONS: tuple[str, ...] = (
    "normalize_heading_boundary",
    "join_fragmented_paragraph",
)
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
# ``toc_like`` means "pass this block through untouched": it is immune to every cleanup
# operation. Contents, index, bibliography and front matter are all pass-through material
# (Constitution VII), so telling them apart from EACH OTHER buys nothing — a mislabel
# inside reference material is harmless by construction. Only two properties matter, and
# the rule is the smallest one that holds both:
#
#   * ordinary prose must NOT become immune, or the pass silently does nothing on the body
#     of the book (that was the defect: "a line ending in a number" was sufficient, which
#     made "Он родился в 1990" and "In 1990 value was 5 and in 2000 rose to 10" immune);
#   * reference material must be roughly protected, so cleanup operations do not chew
#     through a contents list or a subject index. Rough is enough; precise is not the goal.
#
# Length is not the discriminator — lietaer's real contents lines run to 163 characters and
# its subject index to 784. WHERE the numbers sit is. Four shapes qualify:
#
#   1. a dotted leader terminated by a page number ("Введение ......... 12");
#   2. a block that is nothing but page numbers, ranges and separators ("99, 102",
#      "179– 180") — an index column continued across a page break;
#   3. an index run: at least three page references introduced by a comma or semicolon
#      ("Куритиба, 142; устойчивое, 5–6, 55, 224") or written as page ranges, dense enough
#      against the word count that the block cannot be read as a sentence;
#   4. a contents run: at least three whitespace-delimited bare page numbers, EVERY one of
#      them at an entry boundary — followed by the next entry's number, by the capitalised
#      start of the next title, or by the end of the block. Front matter is paginated in
#      lowercase roman numerals, so a roman page number counts here too, on the terms below.
#
# Every narrow spelling below is paid for by a measured PROSE false positive, not by
# tidiness inside reference material: requiring a space after the comma in (3) keeps
# Russian decimal commas out ("Он заплатил 0,72 доллара в 1990 г."); capping the page
# reference at three digits keeps comma-separated year lists out ("Кризисы 1929, 1987,
# 2008, 2020 и 2023 годов"); the density ratio keeps statistics-heavy paragraphs out
# (lietaer b_000091, "; 49 процентов ... , 18 процентов ... , 26 процентов" — 3 references
# in 165 words; and creating_wealth b_000734, 3 in 315); requiring the tokens in (4) to be
# whitespace-delimited keeps endnote superscripts glued to a full stop out
# ("непроизводительными.54 Тем не менее"); and requiring the word after the boundary to be
# a plain capitalised word keeps currency amounts out ("зачисляется 10 L15, а со счета").
#
# The leader alternatives are written to run in LINEAR time, and the spelling is load-bearing.
# ``(?:\.{3,}|…{2,})\s*\d{1,4}\s*\Z`` searched unanchored is quadratic: on a run of N dots the
# engine restarts at every one of the N offsets and rescans the rest of the run from each, so an
# OCR artefact of 100 000 dots — a single block in a single book — took 93 seconds to classify,
# before one token was spent on the model. Two spellings make the cost linear without changing
# which strings match:
#
#   * a leader may not start in the middle of its own run (``(?<!\.)`` / ``(?<!…)``), so all but
#     the first offset of a run fail in O(1). The lookbehind is per-branch on purpose: a shared
#     ``(?<![.…])`` would also reject "Раздел…...4", where a dot run legitimately begins right
#     after an ellipsis character;
#   * the run is consumed possessively (``{3,}+`` / ``{2,}+``). Giving dots back can never help —
#     what follows a shorter run is another dot, and neither ``\s`` nor ``\d`` matches one — so
#     the backtracking it removes was pure waste.
#
# Acceptance is therefore identical to the greedy unanchored form; only the match offset inside a
# run differs, and the sole caller (``_is_toc_like_text``) reads the result as a boolean.
_TOC_LEADER_ENTRY_PATTERN = re.compile(r"(?:(?<!\.)\.{3,}+|(?<!…)…{2,}+)\s*\d{1,4}\s*\Z")
_TOC_PAGE_REFERENCE_RUN_PATTERN = re.compile(r"[\d\s.,;:–—−-]+")
_TOC_PAGE_REFERENCE_TOKEN_PATTERN = re.compile(r"\d{1,4}")
# "..., 142", "...; 5", "..., 226n13" — a page reference introduced by index punctuation.
# The trailing ``(?!\w)`` is what tells "1d, 2a, 2b, 2c" (a figure-step list) from an index.
_TOC_INDEX_PAGE_REFERENCE_PATTERN = re.compile(r"[,;]\s+\d{1,3}(?:[nн]\d{1,3})?(?!\w)")
_TOC_PAGE_RANGE_PATTERN = re.compile(r"(?<!\w)\d{1,3}\s*[–—−]\s*\d{1,3}(?!\w)")
_TOC_MIN_PAGE_REFERENCE_TOKENS = 3
_TOC_MIN_PAGE_REFERENCE_TOKEN_RATIO = 0.15
_TOC_MIN_CONTENTS_ENTRY_TOKENS = 3
_TOC_ENTRY_BOUNDARY_TRIM_CHARS = "«»\"'“”„‟()[]{}.,;:!?—–-*_"
# A contents line that crosses the roman→arabic pagination seam ("Предисловие ix Введение:
# ... 1", lietaer b_000020) carries only two page references — one short of the bare-number
# count above — so the roman one has to be readable as a page number for the line to be
# recognised at all. Nothing lexical decides that: no list of numerals, of look-alike words
# or of book lines is consulted. Two properties do, and both are about form and place.
#
#   * MAGNITUDE. Front matter does not run past its ninety-ninth page, so its numerals are
#     spelled from i, v, x and l alone; the hundreds and thousands symbols are not part of
#     the grammar. That is the same species of cap as the three-digit limit on an arabic
#     page reference above, and it is what stops "mix", "ci", "di" and "mi" (1009, 101, 501
#     and 1001) from being page numbers at all — by arithmetic, not by vocabulary. Measured:
#     lift the cap and lietaer b_001398 ("Rivista di Storia Economica 1, no. 1 (Турин,
#     1936)") reads as a contents line. A single letter is excluded for the same formal
#     reason a bare "1" is not an index entry: one character carries no shape ("i", "v" and
#     "x" stand alone in prose as words and list markers).
#   * POSITION. A roman token is counted only where an arabic page number would be counted
#     — at an entry boundary — and only in a block that ALREADY carries an arabic page
#     number at an entry boundary. So the roman numeral can corroborate a contents run; it
#     can never establish one. What survives the magnitude cap and is still a word ("vi",
#     "li") therefore has to sit at an entry boundary in a block that is already paginated
#     to matter, which is a bibliography or a foreign-language title at worst — reference
#     material, which this pass ignores rather than polishes, so the mislabel costs nothing.
_TOC_ROMAN_PAGE_NUMBER_PATTERN = re.compile(r"(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})")
_TOC_MIN_ROMAN_PAGE_NUMBER_CHARS = 2
_TOC_MIN_CONTENTS_ENTRY_TOKENS_WITH_ROMAN = 2
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
