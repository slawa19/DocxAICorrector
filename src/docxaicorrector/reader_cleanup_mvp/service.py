from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast


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
    "split_block",
    "remove_inline_noise",
    "join_fragmented_paragraph",
    "normalize_heading_boundary",
}
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
    "heading_substring",
    "body_substring",
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


@dataclass(frozen=True)
class ReaderCleanupConfig:
    enabled: bool = False
    model: str = ""
    chunk_size: int = _DEFAULT_CLEANUP_CHUNK_SIZE
    overlap_blocks_before: int = _DEFAULT_OVERLAP_BLOCKS_BEFORE
    overlap_blocks_after: int = _DEFAULT_OVERLAP_BLOCKS_AFTER
    global_plan_enabled: bool = _DEFAULT_GLOBAL_PLAN_ENABLED
    keep_toc: bool = True
    drop_back_matter: bool = False
    max_delete_block_ratio: float = 0.03
    max_delete_char_ratio: float = 0.05
    max_consecutive_deleted_blocks: int = 3
    max_deleted_block_chars: int = 300
    policy: CleanupPolicy = "advisory"


@dataclass(frozen=True)
class CleanupBlock:
    index: int
    block_id: str
    text: str
    normalized_text: str
    text_hash: str
    char_count: int
    non_whitespace_char_count: int
    kind: str
    is_heading: bool
    is_toc_like: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.block_id,
            "text_hash": self.text_hash,
            "kind": self.kind,
            "char_count": self.char_count,
            "is_heading": self.is_heading,
            "is_toc_like": self.is_toc_like,
            "text": self.text,
        }


@dataclass(frozen=True)
class CleanupChunk:
    chunk_index: int
    start_index: int
    end_index: int
    blocks: tuple[CleanupBlock, ...]
    context_before: str
    context_after: str
    context_before_blocks: tuple[CleanupBlock, ...] = ()
    context_after_blocks: tuple[CleanupBlock, ...] = ()


@dataclass(frozen=True)
class CleanupOperation:
    block_id: str
    text_hash: str
    operation: str
    reason: str
    confidence: CleanupConfidence
    chunk_index: int
    evidence_before: str = ""
    expected_after_preview: str = ""
    safety_note: str = ""
    split_substrings: tuple[str, ...] = ()
    noise_substring: str = ""
    next_id: str = ""
    next_text_hash: str = ""
    heading_substring: str = ""
    body_substring: str = ""


class ReaderCleanupStageError(RuntimeError):
    def __init__(self, message: str, *, report_payload: Mapping[str, Any], raw_markdown: str) -> None:
        super().__init__(message)
        self.report_payload = dict(report_payload)
        self.raw_markdown = raw_markdown


@dataclass(frozen=True)
class ReaderCleanupResult:
    changed: bool
    raw_markdown: str
    cleaned_markdown: str
    report_payload: dict[str, Any]
    accepted_delete_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class AnchorRepairChunk:
    chunk: CleanupChunk
    anchors: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class AnchorRepairPassResult:
    cleaned_markdown: str
    warnings: tuple[str, ...]
    accepted_delete_blocks: tuple[dict[str, object], ...]
    accepted_cleanup_operations: tuple[dict[str, object], ...]
    ignored_cleanup_operations: tuple[dict[str, object], ...]
    chunk_results: tuple[dict[str, object], ...]
    deleted_char_count: int
    requested_anchor_count: int
    selected_anchor_count: int
    selected_window_block_count: int
    selected_anchors: tuple[dict[str, str], ...]


def resolve_reader_cleanup_config(*, app_config: Mapping[str, object], fallback_model: str) -> ReaderCleanupConfig:
    raw_policy = str(app_config.get("reader_cleanup_policy", "advisory") or "advisory").strip().lower()
    policy = raw_policy if raw_policy in _ALLOWED_POLICIES else "advisory"
    enabled = bool(app_config.get("reader_cleanup_enabled", False)) and policy != "off"
    model = str(app_config.get("reader_cleanup_model", "") or "").strip() or READER_CLEANUP_DEFAULT_SELECTOR
    return ReaderCleanupConfig(
        enabled=enabled,
        model=model,
        chunk_size=_coerce_int(
            app_config.get("reader_cleanup_chunk_size", _DEFAULT_CLEANUP_CHUNK_SIZE),
            default=_DEFAULT_CLEANUP_CHUNK_SIZE,
            minimum=3000,
        ),
        overlap_blocks_before=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_before", _DEFAULT_OVERLAP_BLOCKS_BEFORE),
            default=_DEFAULT_OVERLAP_BLOCKS_BEFORE,
            minimum=0,
        ),
        overlap_blocks_after=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_after", _DEFAULT_OVERLAP_BLOCKS_AFTER),
            default=_DEFAULT_OVERLAP_BLOCKS_AFTER,
            minimum=0,
        ),
        global_plan_enabled=_coerce_bool(
            app_config.get("reader_cleanup_global_plan_enabled", _DEFAULT_GLOBAL_PLAN_ENABLED),
            default=_DEFAULT_GLOBAL_PLAN_ENABLED,
        ),
        keep_toc=bool(app_config.get("reader_cleanup_keep_toc", True)),
        drop_back_matter=bool(app_config.get("reader_cleanup_drop_back_matter", False)),
        max_delete_block_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_block_ratio", 0.03), default=0.03),
        max_delete_char_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_char_ratio", 0.05), default=0.05),
        max_consecutive_deleted_blocks=_coerce_int(
            app_config.get("reader_cleanup_max_consecutive_deleted_blocks", 3),
            default=3,
            minimum=1,
        ),
        max_deleted_block_chars=_coerce_int(
            app_config.get("reader_cleanup_max_deleted_block_chars", 300),
            default=300,
            minimum=1,
        ),
        policy=cast(CleanupPolicy, policy),
    )


def build_reader_cleanup_system_prompt() -> str:
    return (
        "You are cleaning translated book Markdown for reading.\n"
        "Do not translate, rewrite, summarize, reorder, or reformat the book.\n"
        "Return JSON only with top-level fields cleanup_operations and warnings.\n"
        "Return only a single valid JSON object. Do not wrap it in markdown fences. Do not add prose before or after JSON.\n"
        'For no-op chunks, return exactly {"cleanup_operations":[],"warnings":[]} or the same object with string warnings.\n'
        "Allowed operations are delete_block, split_block, remove_inline_noise, join_fragmented_paragraph, and normalize_heading_boundary.\n"
        "Only blocks listed in editable_block_ids are mutation targets; readonly_context_blocks_before and readonly_context_blocks_after are context only and must not be edited.\n"
        "Do not reconstruct TOC or chapters as a structure-recognition task. Do not change semantic order or remove semantic content.\n"
        "For split_block, remove_inline_noise, join_fragmented_paragraph, and normalize_heading_boundary, provide only the minimal exact-match diff fields, not a rewritten document.\n"
        "Use delete_block only for non-semantic PDF/OCR/layout noise: repeated running headers, footers, "
        "page numbers, blank-page markers, orphaned footnote markers, and obvious extraction artifacts.\n"
        "Do not delete a standalone numeric block such as '8' or '12' by page_number reason unless nearby page-boundary context, repeated header/footer evidence, or explicit page-label evidence makes it safe.\n"
        "Use remove_inline_noise for exact page furniture/page number/running header substrings embedded before or inside a semantic paragraph.\n"
        "For remove_inline_noise, prefer reasons such as page_furniture_inline, page_furniture_heading, page_number, orphan_footnote_marker, or repeated_running_header when they match the exact residue being removed.\n"
        "If operation_selection_targets lists a duplicate_semantic_heading_text candidate, inspect that block first and use remove_inline_noise with reason duplicate_fragment only if the exact adjacent repeated phrase and full expected_after_preview are still valid.\n"
        "If operation_selection_targets lists a side_heading_island_candidate, classify it as a possible PDF/two-column side heading embedded in prose; first try split_block, then normalize_heading_boundary only when exact substrings can preserve all semantic text.\n"
        "Semantic heading islands are not noise. Do not delete semantic heading islands with remove_inline_noise; if exact structural split cannot preserve all semantic text, skip and add a warning.\n"
        "Use split_block for one block that should become 2-3 exact substrings from the original block.\n"
        "Use join_fragmented_paragraph only for adjacent blocks that are one paragraph split by a page/caption boundary.\n"
        "Use normalize_heading_boundary only to move an exact heading-like prefix into a separate heading block and keep exact body text as a paragraph.\n"
        "If the request pass_name is anchor_repair, operate only inside the listed anchor_targets and anchor_window_block_ids.\n"
        "For anchor_repair, every returned operation still needs full audit fields: evidence_before, expected_after_preview, and safety_note are never optional.\n"
        "For anchor_repair fragmented_paragraph targets, first inspect only adjacent payload blocks. Prefer one join_fragmented_paragraph operation when the current block and the next block are a single paragraph split by a page, caption, or image boundary.\n"
        "For anchor_repair join_fragmented_paragraph, copy next_id and next_text_hash exactly from the current payload block list; do not reuse stale ids or hashes from a prior raw/cleaned artifact.\n"
        "For anchor_repair fragmented_paragraph targets, do not propose delete_block duplicate_fragment unless the full candidate block is exact normalized text already preserved in one nearby payload block.\n"
        "For anchor_repair fragmented_paragraph targets, do not combine split_block and join_fragmented_paragraph on the same evidence unless split_substrings exactly cover one extraction-artifact block and the following join still uses adjacent current payload hashes.\n"
        "For anchor_repair page_furniture_inline targets, first propose remove_inline_noise for the exact non-semantic page-number/running-header prefix or island; do not use join_fragmented_paragraph or delete_block as a substitute for that cleanup.\n"
        "For inline endnote/page marker artifacts inside prose, such as a standalone digit between two words, use remove_inline_noise with the exact deleted span in noise_substring and the full post-removal block in expected_after_preview.\n"
        "For duplicate semantic heading text repeated inline, use remove_inline_noise with reason duplicate_fragment only when the deleted phrase is an exact adjacent repeated phrase and expected_after_preview is the full resulting block.\n"
        "If page furniture plus an image caption sits between two parts of one sentence, propose remove_inline_noise for the exact full noise span and then a separate join_fragmented_paragraph from the previous adjacent block to the cleaned anchor block.\n"
        "If one anchored block needs both page-furniture removal and heading/body repair, return two bounded exact-match operations on that same block instead of rewriting the block.\n"
        "If non-heading text remains before the heading candidate, such as a quote, caption, or footnote marker, do not use normalize_heading_boundary; use split_block with exact substrings instead.\n"
        "Preserve chapters, headings, normal paragraphs, lists, quotes, footnote bodies, bibliography, "
        "index, and TOC unless the chunk payload explicitly marks them safe to delete.\n"
        "Each cleanup_operations item must contain id, text_hash, operation, reason, confidence, evidence_before, expected_after_preview, and safety_note. Never omit confidence.\n"
        "split_block must include split_substrings; remove_inline_noise must include noise_substring; join_fragmented_paragraph must include next_id and next_text_hash; normalize_heading_boundary must include heading_substring and body_substring.\n"
        "For normalize_heading_boundary, use an exact heading prefix from the current block and copy body_substring verbatim as the full semantic body remainder after that boundary, not just a teaser; do not rewrite, retranslate, shorten, reorder, or normalize punctuation on either side.\n"
        "Use normalize_heading_boundary only when the heading is an exact prefix and body_substring is the exact full remaining semantic body text inside the same block.\n"
        "If a block starts with page number plus running-header prefix plus prose, always propose remove_inline_noise for the exact non-semantic prefix first.\n"
        "Do not use normalize_heading_boundary to remove a numeric running-header prefix; use it only after exact prefix cleanup has already isolated the heading/body boundary.\n"
        "If remove_inline_noise is also needed on the same block, heading_substring and body_substring for normalize_heading_boundary must match the exact post-prefix remainder, not the pre-cleanup text.\n"
        "For a genuine prefix heading plus normal narrative prose, heading_substring must be the complete exact heading prefix and body_substring must be the entire exact body remainder, including all later sentences in that same block.\n"
        "Uppercase heading plus normal narrative prose belongs to normalize_heading_boundary only when heading_substring is the full semantic heading from its first heading token and body_substring is the exact full prose tail that follows it.\n"
        "Uppercase heading with a colon plus narrative prose belongs to normalize_heading_boundary when the heading stays fully inside heading_substring and body_substring copies the full exact prose remainder from the first real prose sentence through the end of the block.\n"
        "Heading ending with a period plus narrative prose belongs to normalize_heading_boundary when the sentence after that period is real body prose rather than a subtitle, question, epigraph, TOC row, or list-like fragment.\n"
        "A short uppercase heading followed by narrative prose may still be a real heading, but only if body_substring copies the exact full semantic prose tail rather than a teaser or partial sentence.\n"
        "Do not return a partial heading tail from the middle or last words of a wrapped heading; copy the full remaining heading from its first semantic token.\n"
        "If body_substring is not copied verbatim from the current block text, or if it only copies the first few words instead of the full remaining semantic body text, do not propose normalize_heading_boundary.\n"
        "For normalize_heading_boundary, expected_after_preview must show the exact post-apply result for that same block with the heading first and the body remainder after a blank-line break; if you cannot provide that exact preview from the current block text, do not propose the operation.\n"
        "If a numeric prefix is followed by a semantic heading and body, do not widen remove_inline_noise to consume the semantic heading; keep prefix removal and heading/body normalization as separate exact operations.\n"
        "If a title-case running-header island with connector words or acronyms and a trailing page number interrupts semantic prose, use remove_inline_noise for only that exact island; do not widen into neighboring prose before or after it.\n"
        "Do not treat TOC-like rows, table-like rows, list rows, title+subtitle pairs, title+question pairs, or epigraph-only continuations as heading/body prose just because uppercase text appears first.\n"
        "If one block has multiple bounded operations, keep them separate; code applies them in canonical order remove_inline_noise, split_block, post-split remove_inline_noise, normalize_heading_boundary, then join_fragmented_paragraph.\n"
        "Examples for heading/body cleanup:\n"
        "- Sentence-style heading fused to prose: for 'ОБРАЗОВАНИЕ. Расходы на образование обычно ложатся на плечи федерального правительства.' use normalize_heading_boundary with heading_substring='ОБРАЗОВАНИЕ.' and body_substring='Расходы на образование обычно ложатся на плечи федерального правительства.'.\n"
        "- Uppercase heading with colon plus prose: for 'МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ В пилотном городе...' use normalize_heading_boundary with heading_substring='МЕСТНАЯ ПРОГРАММА: ОБЩЕСТВЕННАЯ ПОЛЬЗА БЕЗ ДОЛГОВ' and body_substring copying the full exact remainder from 'В пилотном городе...' through the end of that block.\n"
        "- Uppercase heading plus prose: use normalize_heading_boundary with heading_substring='СТРАТЕГИИ ДЛЯ ГОРОДСКИХ СЛУЖБ' and body_substring copying the full exact prose remainder after it.\n"
        "- Short uppercase heading plus narrative prose: for 'РАБОЧАЯ ГРУППА Во время пилотного проекта...' use normalize_heading_boundary with heading_substring='РАБОЧАЯ ГРУППА' and body_substring copying the full exact remainder from 'Во время пилотного проекта...'.\n"
        "- Heading ending with period plus prose: for 'ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ. Ключевые аспекты...' use normalize_heading_boundary with heading_substring='ПРОЗРАЧНОСТЬ И ПОДОТЧЕТНОСТЬ.' and body_substring copying the full exact remainder from 'Ключевые аспекты...'.\n"
        "- Uppercase section heading followed immediately by sentence-case prose: for 'БЕСПЛАТНЫЕ КЛИНИКИ И «ИТАКСКИЕ ЧАСЫ» Здравоохранение — критически важная проблема...' use normalize_heading_boundary with the full uppercase title as heading_substring and body_substring copying the full exact remainder from 'Здравоохранение — ...'.\n"
        "- Uppercase heading ending with a period followed by body prose: for 'ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР. Через призму...' use normalize_heading_boundary with heading_substring='ГРАЖДАНСКИЕ ИНИЦИАТИВЫ И НЕКОММЕРЧЕСКИЙ СЕКТОР.' and body_substring copying the full exact remainder from 'Через призму...'.\n"
        "- Leading page number or running header plus uppercase heading plus prose: first use remove_inline_noise for the exact non-semantic prefix, then normalize_heading_boundary for the remaining heading/body boundary when both exact previews are safe.\n"
        "- Running-header prefix plus semantic heading plus prose: after prefix cleanup, keep the full remaining semantic heading in heading_substring and put only the exact prose sentence start in body_substring; do not treat the whole semantic heading as removable noise and do not keep only the last heading words.\n"
        "- Do not keep only a trailing heading tail like 'И СПРАВЕДЛИВОСТЬ.' when the full semantic heading started earlier in the same block; heading_substring must begin at the first semantic heading token.\n"
        "- Semantic side-heading island operation choice: bad: remove_inline_noise \"Три мультинациональные валюты\". Good: split_block or normalize_heading_boundary that preserves both heading text and body text exactly; if exact preservation is not possible, skip.\n"
        "- Title-case running header island inside a sentence: for '... Полевой отчет НКО 167 развивающейся организации ...' use remove_inline_noise with noise_substring='Полевой отчет НКО 167 '.\n"
        "- Title-case running header with leading page number inside a sentence: for '... 3 Городское управление 201 особенно важно ...' use remove_inline_noise with noise_substring='3 Городское управление 201 '.\n"
        "- Title plus subtitle on one line is not automatically heading/body fusion; if the second segment is a short subtitle, subtitle question, or epigraph-like line rather than narrative prose, do not use normalize_heading_boundary just to force a split.\n"
        "- Title plus subtitle/question negative examples: 'ОТЧЕТ И ВЫВОДЫ: краткий обзор' and 'ГОРОДСКОЕ УПРАВЛЕНИЕ Что дальше?' may be title+subtitle/question rather than heading+body prose; do not force normalize_heading_boundary unless actual narrative prose starts after them.\n"
        "- TOC-like rows are not heading/body prose: rows such as '4 Практический раздел 57 5 Следующая глава...' or '73 6 Раздел для команд 95 7 Раздел для партнеров...' must not be split with normalize_heading_boundary.\n"
        "- Chapter heading plus epigraph in the same block: use split_block into exact substrings for chapter heading, epigraph, and body.\n"
        "- Section heading plus first sentence: use normalize_heading_boundary only if the heading comes first and the body remainder is exact.\n"
        "- Part title after a preceding quote: use split_block, not normalize_heading_boundary, because text exists before the heading.\n"
        "- Duplicate tail carryover as its own block: use delete_block with reason duplicate_fragment only when that full block is already preserved nearby as exact repeated text.\n"
        "For fragmented paragraph anchors, use neighbor context to decide whether a page or caption boundary split one paragraph across adjacent blocks, and use join_fragmented_paragraph only when the exact adjacent hashes match that evidence.\n"
        "- Anchor fragmented paragraph through caption/page boundary: if the anchored block ends mid-sentence and the immediately next payload block starts with lowercase continuation prose, use join_fragmented_paragraph with that next block's exact id/hash; do not split or delete.\n"
        "- Anchor fragmented paragraph that looks like a duplicate tail: if the full anchored block is not exact normalized text already preserved nearby, keep it and add a warning instead of delete_block duplicate_fragment.\n"
        "- Anchor fragmented paragraph with page furniture between prose: remove only the exact page-furniture substring or block when safe, then join only adjacent current payload blocks with exact hashes; if adjacency is unclear, keep the text.\n"
        "- Anchor page furniture prefix: for '190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ Особый интерес...' use remove_inline_noise with noise_substring='190 ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ ' and keep the following prose.\n"
        "- Anchor page furniture plus caption between sentence parts: remove exactly the page header and caption span, keep the lowercase prose continuation, then join the previous unfinished block to the cleaned anchor block with exact ids/hashes.\n"
        "A leading or inline number may be removed only when it is exact non-semantic page furniture or an orphan inline note marker; if the number is semantic content inside a sentence, date, quantity, title, or citation, keep it.\n"
        "Standalone numeric lines can be footnotes, citations, list markers, or semantic numbering; if page context is uncertain, keep them and add a warning.\n"
        "For obvious non-semantic noise such as standalone page numbers or lines like [[DOCX_IMAGE_img_001]], "
        'use confidence="high" instead of omitting the field.\n'
        "Preserve normal narrative wording and avoid semantic rewriting.\n"
        "Example valid response: "
        '{"cleanup_operations":[{"id":"b_000123","text_hash":"7f83b1657ff1fc53","operation":"delete_block","reason":"extraction_artifact","confidence":"high","evidence_before":"standalone image placeholder","expected_after_preview":"","safety_note":"non-semantic placeholder only"}],"warnings":[]}\n'
        "If uncertain, keep the text and add a warning."
    )


def build_reader_cleanup_schema_repair_system_prompt() -> str:
    return (
        "You repair JSON for reader cleanup chunk responses.\n"
        "Return JSON only with top-level fields cleanup_operations and warnings.\n"
        "Return only a single valid JSON object. Do not wrap it in markdown fences. Do not add prose before or after JSON.\n"
        'For no-op repairs, return exactly {"cleanup_operations":[],"warnings":[]} or the same object with string warnings.\n'
        "Do not return rewritten Markdown, cleaned Markdown, commentary, or extra top-level fields.\n"
        "You may only correct schema and field mistakes inside cleanup_operations and warnings.\n"
        "Repair every invalid cleanup operation item in the response, not only the first broken one.\n"
        "If the original response uses legacy delete_blocks, convert it into cleanup_operations with full audit fields instead of preserving the legacy shortcut.\n"
        "Keep the allowed operations unchanged: delete_block, split_block, remove_inline_noise, join_fragmented_paragraph, and normalize_heading_boundary.\n"
        "Do not invent new block ids, text hashes, or rewritten text. Use only exact ids and text_hash values already present in the request.\n"
        "If pass_name is anchor_repair, keep the repaired response limited to anchor_targets, anchor_window_block_ids, editable_block_ids, and exact evidence already present in the request.\n"
        "Drop or repair any operation that targets a readonly_context block instead of an editable_block_id.\n"
        "You may fill missing audit fields only from exact block text, context previews, anchor_targets, and the original response; do not fabricate rewritten prose.\n"
        "Each cleanup_operations item must contain id, text_hash, operation, reason, confidence, evidence_before, expected_after_preview, and safety_note.\n"
        "duplicate_fragment is an allowed delete_block reason only for exact nearby repeated carryover text that is already preserved elsewhere nearby.\n"
        "If a duplicate_fragment candidate is only similar to nearby prose but not an exact normalized nearby preserved block, drop it and add a warning instead of widening the deletion.\n"
        "For anchor_repair fragmented_paragraph items, keep a join_fragmented_paragraph operation only when next_id and next_text_hash are copied from an adjacent block in the current request payload; otherwise drop it and add a warning.\n"
        "For anchor_repair fragmented_paragraph items, do not convert a non-exact duplicate-looking tail into delete_block duplicate_fragment; drop unsafe deletion instead.\n"
        "For anchor_repair page_furniture_inline items, keep join_fragmented_paragraph only as a follow-up from the previous adjacent block to the page-furniture anchor block when the response also has exact remove_inline_noise on that anchor block.\n"
        "For remove_inline_noise, page_furniture_inline, page_furniture_heading, page_number, orphan_footnote_marker, duplicate_fragment, and repeated_running_header are the preferred bounded audit reasons.\n"
        "Do not widen remove_inline_noise to consume a semantic heading after a numeric running-header prefix; keep exact prefix removal separate from normalize_heading_boundary.\n"
        "If the original response already isolates a title-case running-header island with connector words or acronyms plus a trailing page number, keep it as remove_inline_noise instead of widening the substring into neighboring prose.\n"
        "split_block must include split_substrings; remove_inline_noise must include noise_substring; join_fragmented_paragraph must include next_id and next_text_hash; normalize_heading_boundary must include heading_substring and body_substring.\n"
        "For normalize_heading_boundary, keep exact copied substrings only; never invent a cleaner heading or shortened body.\n"
        "If one block needs composed cleanup, keep each operation separate and fully populated instead of merging them into rewritten Markdown.\n"
        "If an operation cannot be repaired safely, drop it and add a warning instead of inventing content."
    )


def build_reader_cleanup_global_plan_system_prompt() -> str:
    return (
        "You are planning an advisory reader cleanup pass over raw translated Markdown.\n"
        "Return compact JSON only. Do not rewrite, translate, delete, reorder, summarize, or reconstruct TOC/chapters.\n"
        "Your plan is advisory evidence for later bounded cleanup operations; it must not itself remove text.\n"
        "Find document-specific noise and reader-facing cleanup patterns from the full raw translated Markdown.\n"
        "Return fields repeated_noise_patterns, document_specific_running_headers, examples_do_not_delete, "
        "likely_heading_body_patterns, likely_fragmentation_patterns, and warnings.\n"
        "Each list item should be short and evidence-oriented. If uncertain, add a warning instead of inventing a pattern."
    )


def build_cleanup_blocks(markdown_text: str) -> list[CleanupBlock]:
    normalized_markdown = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized_markdown:
        return []

    raw_blocks = [part.strip("\n") for part in re.split(r"\n\s*\n+", normalized_markdown) if part.strip()]
    blocks: list[CleanupBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        normalized_text = _normalize_block_text(raw_block)
        kind = _detect_block_kind(normalized_text)
        blocks.append(
            CleanupBlock(
                index=index,
                block_id=f"b_{index:06d}",
                text=raw_block,
                normalized_text=normalized_text,
                text_hash=hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16],
                char_count=len(raw_block),
                non_whitespace_char_count=len(re.sub(r"\s+", "", raw_block)),
                kind=kind,
                is_heading=kind == "heading",
                is_toc_like=kind == "toc_like",
            )
        )
    return blocks


def _select_cleanup_blocks(*, blocks: Sequence[CleanupBlock], keep_toc: bool) -> tuple[list[CleanupBlock], list[str]]:
    if keep_toc:
        return list(blocks), []

    filtered_blocks = [block for block in blocks if not block.is_toc_like]
    ignored_toc_count = len(blocks) - len(filtered_blocks)
    warnings: list[str] = []
    if ignored_toc_count > 0:
        warnings.append(f"reader_cleanup_toc_blocks_ignored:{ignored_toc_count}")
    return filtered_blocks, warnings


def run_reader_cleanup(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    global_plan_provider: Callable[[dict[str, Any]], str] | None = None,
    anchor_operation_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    anchor_targets: Sequence[Mapping[str, object]] | None = None,
    model_resolution: Mapping[str, object] | None = None,
) -> ReaderCleanupResult:
    blocks = build_cleanup_blocks(markdown_text)
    cleanup_blocks, selection_warnings = _select_cleanup_blocks(blocks=blocks, keep_toc=config.keep_toc)
    raw_markdown = str(markdown_text or "")
    if not blocks:
        report_payload = {
            "version": 1,
            "policy": config.policy,
            "model": config.model,
            "cleanup_settings": _serialize_cleanup_settings(config),
            "stage_status": "completed",
            "changed": False,
            "warnings": ["reader_cleanup_skipped_empty_markdown"],
            "stats": {"raw_block_count": 0, "cleanup_chunk_count": 0},
            "global_plan": {"repeated_noise_patterns": [], "candidate_block_ids": [], "warnings": []},
            "accepted_delete_blocks": [],
            "ignored_cleanup_operations": [],
            "ignored_delete_blocks": [],
            "chunk_results": [],
        }
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=report_payload,
            accepted_delete_block_ids=(),
        )

    global_plan = _build_global_plan(
        blocks=cleanup_blocks,
        raw_markdown=raw_markdown,
        config=config,
        global_plan_provider=global_plan_provider,
    )
    chunks = _build_cleanup_chunks(
        blocks=cleanup_blocks,
        chunk_size=config.chunk_size,
        overlap_blocks_before=config.overlap_blocks_before,
        overlap_blocks_after=config.overlap_blocks_after,
    )
    all_operations: list[CleanupOperation] = []
    raw_global_warnings = global_plan.get("warnings")
    warnings: list[str] = list(selection_warnings)
    if isinstance(raw_global_warnings, list):
        warnings.extend(str(item) for item in raw_global_warnings)
    ignored_cleanup_operations: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []

    for chunk in chunks:
        request_payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
        request_payload_char_count = len(json.dumps(request_payload, ensure_ascii=False))
        started_at = time.perf_counter()
        raw_response = ""
        schema_validation_error = ""
        parse_error_message = ""
        repair_error = ""
        repair_attempted = False
        repair_status = "not_attempted"
        retry_attempted = False
        retry_status = "not_attempted"
        retry_error = ""
        ignored_chunk_operations: list[dict[str, object]] = []
        try:
            raw_response = operation_provider(request_payload, chunk.chunk_index, len(chunks))
            editable_blocks = {block.block_id: block for block in chunk.blocks}
            readonly_context_blocks = _readonly_context_blocks_by_id(chunk)
            try:
                operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                    raw_response=raw_response,
                    editable_blocks=editable_blocks,
                    readonly_context_blocks=readonly_context_blocks,
                    chunk_index=chunk.chunk_index,
                )
            except Exception as exc:
                parse_error_message = str(exc)
                original_response_payload = _load_cleanup_response_object(raw_response)
                if original_response_payload is None:
                    retry_attempted = True
                    retry_status = "attempted"
                    warnings.append(f"reader_cleanup_non_json_response_retry_attempted:{chunk.chunk_index}:{parse_error_message}")
                    try:
                        raw_response = operation_provider(request_payload, chunk.chunk_index, len(chunks))
                        operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                            raw_response=raw_response,
                            editable_blocks=editable_blocks,
                            readonly_context_blocks=readonly_context_blocks,
                            chunk_index=chunk.chunk_index,
                        )
                    except Exception as retry_exc:
                        retry_status = "failed"
                        retry_error = str(retry_exc)
                        parse_error_message = retry_error
                        warnings.append(f"reader_cleanup_non_json_response_retry_failed:{chunk.chunk_index}:{retry_error}")
                        raise
                    retry_status = "succeeded"
                    warnings.append(f"reader_cleanup_non_json_response_retry_succeeded:{chunk.chunk_index}")
                    original_response_payload = None
                if original_response_payload is None:
                    pass
                else:
                    schema_validation_error = str(exc)
                    repair_attempted = True
                    repair_status = "attempted"
                    warnings.append(f"reader_cleanup_schema_validation_failed:{chunk.chunk_index}:{schema_validation_error}")
                    warnings.append(f"reader_cleanup_schema_repair_attempted:{chunk.chunk_index}")
                    repaired_response = repair_provider(
                        _build_cleanup_schema_repair_payload(
                            request_payload=request_payload,
                            original_response=original_response_payload,
                            validation_error=schema_validation_error,
                        ),
                        chunk.chunk_index,
                        len(chunks),
                    ) if repair_provider is not None else None
                    if repaired_response is None:
                        raise
                    try:
                        operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                            raw_response=repaired_response,
                            editable_blocks=editable_blocks,
                            readonly_context_blocks=readonly_context_blocks,
                            chunk_index=chunk.chunk_index,
                        )
                    except Exception as repair_exc:
                        repair_status = "failed"
                        repair_error = str(repair_exc)
                        warnings.append(f"reader_cleanup_schema_repair_failed:{chunk.chunk_index}:{repair_error}")
                        raise
                    repair_status = "succeeded"
                    warnings.append(f"reader_cleanup_schema_repair_succeeded:{chunk.chunk_index}")
                if retry_status == "succeeded":
                    pass
                elif original_response_payload is None:
                    raise
        except Exception as exc:
            warning = f"reader_cleanup_chunk_failed:{chunk.chunk_index}:{exc}"
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
            chunk_results.append(
                {
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "readonly_context_before_count": len(chunk.context_before_blocks),
                    "readonly_context_after_count": len(chunk.context_after_blocks),
                    "elapsed_ms": elapsed_ms,
                    "proposed_cleanup_operation_count": 0,
                    "proposed_delete_block_count": 0,
                    "accepted_cleanup_operation_count": 0,
                    "accepted_delete_block_count": 0,
                    "ignored_cleanup_operation_count": 0,
                    "ignored_delete_block_count": 0,
                    "repair_attempted": repair_attempted,
                    "repair_status": repair_status,
                    "retry_attempted": retry_attempted,
                    "retry_status": retry_status,
                    "retry_error": retry_error,
                    "schema_validation_error": schema_validation_error,
                    "parse_error_message": parse_error_message or str(exc),
                    "repair_error": repair_error,
                    "failure_diagnostics": _build_failed_chunk_diagnostics(
                        chunk=chunk,
                        config=config,
                        request_payload_char_count=request_payload_char_count,
                        raw_response=raw_response,
                        parse_error_message=parse_error_message or str(exc),
                        retry_attempted=retry_attempted,
                        retry_status=retry_status,
                        retry_error=retry_error,
                        repair_attempted=repair_attempted,
                        repair_status=repair_status,
                        repair_error=repair_error,
                    ),
                    "warning": warning,
                }
            )
            warnings.append(warning)
            if config.policy == "strict":
                report_payload = _build_reader_cleanup_report_payload(
                    raw_markdown=raw_markdown,
                    config=config,
                    blocks=blocks,
                    global_plan=global_plan,
                    warnings=warnings,
                    accepted_delete_blocks=[],
                    accepted_cleanup_operations=[],
                    ignored_cleanup_operations=ignored_cleanup_operations,
                    chunk_results=chunk_results,
                    deleted_char_count=0,
                    changed=False,
                    model_resolution=model_resolution,
                    failure={
                        "kind": "chunk_failed",
                        "chunk_index": chunk.chunk_index,
                        "error_message": str(exc),
                    },
                )
                raise ReaderCleanupStageError(
                    f"reader_cleanup_chunk_failed:{chunk.chunk_index}:{exc}",
                    report_payload=report_payload,
                    raw_markdown=raw_markdown,
                ) from exc
            continue

        all_operations.extend(operations)
        warnings.extend(chunk_warnings)
        ignored_cleanup_operations.extend(ignored_chunk_operations)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        chunk_results.append(
            {
                "chunk_index": chunk.chunk_index,
                "status": "completed",
                "target_block_count": len(chunk.blocks),
                "target_chars": sum(block.char_count for block in chunk.blocks),
                "readonly_context_before_count": len(chunk.context_before_blocks),
                "readonly_context_after_count": len(chunk.context_after_blocks),
                "elapsed_ms": elapsed_ms,
                "proposed_cleanup_operation_count": len(operations) + len(ignored_chunk_operations),
                "proposed_delete_block_count": sum(1 for operation in operations if operation.operation == "delete_block"),
                "accepted_cleanup_operation_count": 0,
                "accepted_delete_block_count": 0,
                "ignored_cleanup_operation_count": 0,
                "ignored_delete_block_count": 0,
                "repair_attempted": repair_attempted,
                "repair_status": repair_status,
                "retry_attempted": retry_attempted,
                "retry_status": retry_status,
                "retry_error": retry_error,
                "schema_validation_error": schema_validation_error,
                "parse_error_message": parse_error_message,
                "repair_error": repair_error,
                "request_payload_char_count": request_payload_char_count,
            }
        )

    cleaned_markdown, accepted_ids, accepted_cleanup_operations, ignored = _apply_cleanup_operations(
        raw_markdown=raw_markdown,
        blocks=blocks,
        operations=all_operations,
        config=config,
        global_candidate_block_ids={
            str(block_id)
            for block_id in cast(Sequence[object], global_plan.get("candidate_block_ids") or [])
            if str(block_id).strip()
        },
    )
    ignored_cleanup_operations.extend(ignored)

    accepted_delete_blocks: list[dict[str, object]] = []
    accepted_counts_by_chunk: Counter[int] = Counter()
    for block_id, entry in accepted_ids.items():
        block = _block_by_id(blocks, block_id)
        chunk_index = _coerce_int(entry.get("chunk_index"), default=0, minimum=0)
        accepted_delete_blocks.append(
            {
                **_serialize_delete_block(block=block, reason=str(entry["reason"]), confidence=str(entry["confidence"])),
                "chunk_index": chunk_index,
                "after_state": "deleted",
            }
        )
        accepted_counts_by_chunk[chunk_index] += 1

    ignored_counts_by_chunk: Counter[int] = Counter()
    for entry in ignored_cleanup_operations:
        chunk_index = entry.get("chunk_index")
        if isinstance(chunk_index, int):
            ignored_counts_by_chunk[chunk_index] += 1

    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_result.get("status") != "completed":
            continue
        accepted_cleanup_count = sum(1 for entry in accepted_cleanup_operations if entry.get("chunk_index") == chunk_index)
        chunk_result["accepted_delete_block_count"] = accepted_counts_by_chunk.get(chunk_index, 0)
        chunk_result["accepted_cleanup_operation_count"] = accepted_cleanup_count
        chunk_result["ignored_delete_block_count"] = ignored_counts_by_chunk.get(chunk_index, 0)
        chunk_result["ignored_cleanup_operation_count"] = ignored_counts_by_chunk.get(chunk_index, 0)

    deleted_char_count = sum(_block_by_id(blocks, block_id).non_whitespace_char_count for block_id in accepted_ids)
    report_payload = _build_reader_cleanup_report_payload(
        raw_markdown=raw_markdown,
        config=config,
        blocks=blocks,
        global_plan=global_plan,
        warnings=warnings,
        accepted_delete_blocks=accepted_delete_blocks,
        accepted_cleanup_operations=accepted_cleanup_operations,
        ignored_cleanup_operations=ignored_cleanup_operations,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
        changed=cleaned_markdown != raw_markdown,
        model_resolution=model_resolution,
    )

    if anchor_operation_provider is not None and anchor_targets:
        anchor_pass_result = _run_anchor_repair_pass(
            markdown_text=cleaned_markdown,
            config=config,
            global_plan=global_plan,
            anchor_targets=anchor_targets,
            operation_provider=anchor_operation_provider,
            repair_provider=repair_provider,
        )
        cleaned_markdown = anchor_pass_result.cleaned_markdown
        report_payload = _merge_anchor_repair_pass_into_report(
            report_payload=report_payload,
            raw_markdown=raw_markdown,
            raw_blocks=blocks,
            anchor_pass_result=anchor_pass_result,
        )

    return ReaderCleanupResult(
        changed=cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=cleaned_markdown,
        report_payload=report_payload,
        accepted_delete_block_ids=tuple(accepted_ids.keys()),
    )


def run_reader_cleanup_anchor_repair(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    base_report_payload: Mapping[str, object],
    anchor_targets: Sequence[Mapping[str, object]],
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None = None,
    model_resolution: Mapping[str, object] | None = None,
) -> ReaderCleanupResult:
    raw_markdown = str(markdown_text or "")
    blocks = build_cleanup_blocks(raw_markdown)
    if not blocks:
        merged_report = dict(base_report_payload)
        existing_warnings = merged_report.get("warnings")
        if isinstance(existing_warnings, list):
            warnings_list: list[str] = [str(item) for item in existing_warnings]
        else:
            warnings_list = []
        merged_report["warnings"] = [
            *warnings_list,
            "reader_cleanup_anchor_repair_skipped_empty_markdown",
        ]
        return ReaderCleanupResult(
            changed=False,
            raw_markdown=raw_markdown,
            cleaned_markdown=raw_markdown,
            report_payload=merged_report,
            accepted_delete_block_ids=(),
        )

    base_report = dict(base_report_payload)
    base_global_plan = cast(Mapping[str, object], base_report.get("global_plan") or {})
    global_plan = {
        "repeated_noise_patterns": list(cast(Sequence[object], base_global_plan.get("repeated_noise_patterns") or [])),
        "candidate_block_ids": list(cast(Sequence[object], base_global_plan.get("candidate_block_ids") or [])),
        "document_specific_running_headers": list(
            cast(Sequence[object], base_global_plan.get("document_specific_running_headers") or [])
        ),
        "examples_do_not_delete": list(cast(Sequence[object], base_global_plan.get("examples_do_not_delete") or [])),
        "likely_heading_body_patterns": list(cast(Sequence[object], base_global_plan.get("likely_heading_body_patterns") or [])),
        "likely_fragmentation_patterns": list(cast(Sequence[object], base_global_plan.get("likely_fragmentation_patterns") or [])),
        "warnings": list(cast(Sequence[object], base_global_plan.get("warnings") or [])),
    }
    anchor_pass_result = _run_anchor_repair_pass(
        markdown_text=raw_markdown,
        config=config,
        global_plan=global_plan,
        anchor_targets=anchor_targets,
        operation_provider=operation_provider,
        repair_provider=repair_provider,
    )
    merged_report = _merge_anchor_repair_pass_into_report(
        report_payload=base_report,
        raw_markdown=raw_markdown,
        raw_blocks=blocks,
        anchor_pass_result=anchor_pass_result,
    )
    if model_resolution is not None:
        merged_report["model_resolution"] = dict(model_resolution)
    accepted_delete_block_ids = tuple(
        str(entry.get("id") or "")
        for entry in anchor_pass_result.accepted_delete_blocks
        if str(entry.get("id") or "").strip()
    )
    return ReaderCleanupResult(
        changed=anchor_pass_result.cleaned_markdown != raw_markdown,
        raw_markdown=raw_markdown,
        cleaned_markdown=anchor_pass_result.cleaned_markdown,
        report_payload=merged_report,
        accepted_delete_block_ids=accepted_delete_block_ids,
    )


def write_reader_cleanup_diagnostics(
    *,
    cleaned_artifact_paths: Mapping[str, str],
    raw_markdown: str,
    report_payload: Mapping[str, object],
) -> dict[str, str]:
    markdown_path = Path(str(cleaned_artifact_paths["markdown_path"]))
    if markdown_path.name.endswith(".result.md"):
        base_name = markdown_path.name[: -len(".result.md")]
    else:
        base_name = markdown_path.stem

    raw_markdown_path = markdown_path.with_name(f"{base_name}.raw.result.md")
    report_path = markdown_path.with_name(f"{base_name}.reader_cleanup_report.json")

    raw_markdown_path.write_text(raw_markdown, encoding="utf-8")
    try:
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        try:
            if raw_markdown_path.exists():
                raw_markdown_path.unlink()
        except OSError:
            pass
        raise

    return {
        "reader_cleanup_raw_markdown_path": str(raw_markdown_path),
        "reader_cleanup_report_path": str(report_path),
    }


def _build_cleanup_chunks(
    *,
    blocks: Sequence[CleanupBlock],
    chunk_size: int,
    overlap_blocks_before: int = 0,
    overlap_blocks_after: int = 0,
) -> list[CleanupChunk]:
    if not blocks:
        return []

    chunks: list[CleanupChunk] = []
    current_blocks: list[CleanupBlock] = []
    current_chars = 0
    chunk_start_position = 0
    for block_position, block in enumerate(blocks):
        separator_chars = 2 if current_blocks else 0
        projected_chars = current_chars + separator_chars + block.char_count
        if current_blocks and projected_chars > chunk_size:
            chunks.append(
                _make_cleanup_chunk(
                    blocks=blocks,
                    selected_blocks=current_blocks,
                    chunk_index=len(chunks) + 1,
                    start_position=chunk_start_position,
                    end_position=block_position - 1,
                    overlap_blocks_before=overlap_blocks_before,
                    overlap_blocks_after=overlap_blocks_after,
                )
            )
            chunk_start_position = block_position
            current_blocks = [block]
            current_chars = block.char_count
            continue

        current_blocks.append(block)
        current_chars = projected_chars

    if current_blocks:
        chunks.append(
            _make_cleanup_chunk(
                blocks=blocks,
                selected_blocks=current_blocks,
                chunk_index=len(chunks) + 1,
                start_position=chunk_start_position,
                end_position=len(blocks) - 1,
                overlap_blocks_before=overlap_blocks_before,
                overlap_blocks_after=overlap_blocks_after,
            )
        )
    return chunks


def _make_cleanup_chunk(
    *,
    blocks: Sequence[CleanupBlock],
    selected_blocks: Sequence[CleanupBlock],
    chunk_index: int,
    start_position: int,
    end_position: int,
    overlap_blocks_before: int = 0,
    overlap_blocks_after: int = 0,
) -> CleanupChunk:
    readonly_before = (
        tuple(blocks[max(0, start_position - overlap_blocks_before) : start_position])
        if overlap_blocks_before > 0
        else ()
    )
    readonly_after = (
        tuple(blocks[end_position + 1 : min(len(blocks), end_position + 1 + overlap_blocks_after)])
        if overlap_blocks_after > 0
        else ()
    )
    adjacent_before = blocks[start_position - 1].text if start_position > 0 else ""
    adjacent_after = blocks[end_position + 1].text if end_position + 1 < len(blocks) else ""
    context_before = "\n\n".join(block.text for block in readonly_before) if readonly_before else adjacent_before
    context_after = "\n\n".join(block.text for block in readonly_after) if readonly_after else adjacent_after
    return CleanupChunk(
        chunk_index=chunk_index,
        start_index=selected_blocks[0].index,
        end_index=selected_blocks[-1].index,
        blocks=tuple(selected_blocks),
        context_before=context_before,
        context_after=context_after,
        context_before_blocks=readonly_before,
        context_after_blocks=readonly_after,
    )


def _readonly_context_blocks_by_id(chunk: CleanupChunk) -> dict[str, CleanupBlock]:
    return {
        block.block_id: block
        for block in (*chunk.context_before_blocks, *chunk.context_after_blocks)
    }


def _normalize_anchor_targets(
    *,
    anchor_targets: Sequence[Mapping[str, object]],
    blocks: Sequence[CleanupBlock],
) -> tuple[list[dict[str, str]], list[str]]:
    block_by_id = {block.block_id: block for block in blocks}
    block_ids = set(block_by_id)
    normalized: list[dict[str, str]] = []
    warnings: list[str] = []
    seen_identity_keys: set[str] = set()
    for index, raw_target in enumerate(anchor_targets, start=1):
        category = str(raw_target.get("category") or "").strip()
        if category not in _ALLOWED_ANCHOR_REPAIR_CATEGORIES:
            warnings.append(f"reader_cleanup_anchor_target_ignored:{index}:unsupported_category")
            continue
        block_id = str(raw_target.get("block_id") or "").strip()
        if not block_id or block_id not in block_ids:
            warnings.append(f"reader_cleanup_anchor_target_ignored:{index}:unknown_block_id")
            continue
        anchor_id = str(raw_target.get("anchor_id") or "").strip()
        line_ref = str(raw_target.get("line_ref") or "").strip()
        snippet = str(raw_target.get("snippet") or "").strip()
        anchor_block = block_by_id[block_id]
        if snippet and snippet not in anchor_block.text:
            snippet_matches = [block for block in blocks if snippet in block.text]
            if len(snippet_matches) == 1:
                warnings.append(
                    f"reader_cleanup_anchor_target_reanchored_by_exact_snippet:{index}:{block_id}->{snippet_matches[0].block_id}"
                )
                block_id = snippet_matches[0].block_id
            elif category == "page_furniture_inline":
                resolved_block = _resolve_page_furniture_caption_anchor_block(
                    snippet=snippet,
                    anchor_block=anchor_block,
                    blocks=blocks,
                )
                if resolved_block is not None:
                    warnings.append(
                        "reader_cleanup_anchor_target_reanchored_by_page_caption_signal:"
                        f"{index}:{block_id}->{resolved_block.block_id}"
                    )
                    block_id = resolved_block.block_id
                else:
                    warnings.append(f"reader_cleanup_anchor_target_snippet_not_in_block:{index}:{block_id}")
            else:
                warnings.append(f"reader_cleanup_anchor_target_snippet_not_in_block:{index}:{block_id}")
        identity_key = anchor_id or f"{category}|{block_id}|{line_ref}|{snippet}"
        if identity_key in seen_identity_keys:
            continue
        seen_identity_keys.add(identity_key)
        normalized.append(
            {
                "anchor_id": anchor_id or f"anchor_{len(normalized) + 1:03d}",
                "category": category,
                "block_id": block_id,
                "line_ref": line_ref,
                "snippet": snippet,
            }
        )
    return normalized, warnings


def _resolve_page_furniture_caption_anchor_block(
    *,
    snippet: str,
    anchor_block: CleanupBlock,
    blocks: Sequence[CleanupBlock],
) -> CleanupBlock | None:
    if not _has_generic_caption_marker(snippet):
        return None

    start_index = max(0, anchor_block.index - 2)
    end_index = min(len(blocks) - 1, anchor_block.index + 2)
    candidates: list[tuple[int, int, CleanupBlock]] = []
    for block in blocks[start_index : end_index + 1]:
        if not _has_generic_caption_marker(block.text):
            continue
        overlap_score = _anchor_overlap_score(snippet=snippet, text=block.text)
        if overlap_score < 4:
            continue
        distance = abs(block.index - anchor_block.index)
        candidates.append((overlap_score, -distance, block))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def _has_generic_caption_marker(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in ("фото:", "photo:", "photo credit:", "caption:", "иллюстрация:", "рисунок:"))


def _anchor_overlap_score(*, snippet: str, text: str) -> int:
    snippet_tokens = set(_anchor_signal_tokens(snippet))
    if not snippet_tokens:
        return 0
    text_tokens = set(_anchor_signal_tokens(text))
    return len(snippet_tokens & text_tokens)


def _anchor_signal_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-zА-Яа-яЁё0-9]{4,}", text.lower())
    return [token for token in tokens if not token.isdigit()]


def _build_anchor_repair_chunks(
    *,
    blocks: Sequence[CleanupBlock],
    anchor_targets: Sequence[Mapping[str, str]],
    chunk_size: int,
) -> tuple[list[AnchorRepairChunk], int]:
    if not blocks or not anchor_targets:
        return [], 0

    block_by_id = {block.block_id: block for block in blocks}
    anchor_block_ids = {str(target.get("block_id") or "") for target in anchor_targets}
    selected_indexes: set[int] = set()
    for target in anchor_targets:
        anchor_block_id = str(target.get("block_id") or "")
        block = block_by_id.get(anchor_block_id)
        if block is None:
            continue
        category = str(target.get("category") or "")
        window_radius = 2 if category == "fragmented_paragraph" else 1
        start_index = max(0, block.index - window_radius)
        end_index = min(len(blocks) - 1, block.index + window_radius)
        selected_indexes.update(range(start_index, end_index + 1))

    selected_blocks = [block for block in blocks if block.index in selected_indexes]
    if not selected_blocks:
        return [], 0

    chunks: list[AnchorRepairChunk] = []
    current_blocks: list[CleanupBlock] = []
    current_chars = 0
    for block in selected_blocks:
        separator_chars = 2 if current_blocks else 0
        projected_chars = current_chars + separator_chars + block.char_count
        has_gap = bool(current_blocks) and block.index != current_blocks[-1].index + 1
        if current_blocks and (has_gap or projected_chars > chunk_size):
            base_chunk = _make_manual_cleanup_chunk(blocks=blocks, selected_blocks=current_blocks, chunk_index=len(chunks) + 1)
            chunk_anchor_block_ids = {selected_block.block_id for selected_block in current_blocks} & anchor_block_ids
            chunks.append(
                AnchorRepairChunk(
                    chunk=base_chunk,
                    anchors=tuple(
                        dict(target)
                        for target in anchor_targets
                        if str(target.get("block_id") or "") in chunk_anchor_block_ids
                    ),
                )
            )
            current_blocks = [block]
            current_chars = block.char_count
            continue
        current_blocks.append(block)
        current_chars = projected_chars

    if current_blocks:
        base_chunk = _make_manual_cleanup_chunk(blocks=blocks, selected_blocks=current_blocks, chunk_index=len(chunks) + 1)
        chunk_anchor_block_ids = {selected_block.block_id for selected_block in current_blocks} & anchor_block_ids
        chunks.append(
            AnchorRepairChunk(
                chunk=base_chunk,
                anchors=tuple(
                    dict(target) for target in anchor_targets if str(target.get("block_id") or "") in chunk_anchor_block_ids
                ),
            )
        )

    return chunks, len(selected_blocks)


def _make_manual_cleanup_chunk(
    *,
    blocks: Sequence[CleanupBlock],
    selected_blocks: Sequence[CleanupBlock],
    chunk_index: int,
) -> CleanupChunk:
    start_index = selected_blocks[0].index
    end_index = selected_blocks[-1].index
    return CleanupChunk(
        chunk_index=chunk_index,
        start_index=start_index,
        end_index=end_index,
        blocks=tuple(selected_blocks),
        context_before=blocks[start_index - 1].text if start_index > 0 else "",
        context_after=blocks[end_index + 1].text if end_index + 1 < len(blocks) else "",
    )


def _build_global_plan(
    *,
    blocks: Sequence[CleanupBlock],
    raw_markdown: str,
    config: ReaderCleanupConfig,
    global_plan_provider: Callable[[dict[str, Any]], str] | None,
) -> dict[str, object]:
    repeated_noise_patterns: list[dict[str, object]] = []
    candidate_block_ids: list[str] = []
    warnings: list[str] = []
    ai_plan: dict[str, object] = {
        "repeated_noise_patterns": [],
        "document_specific_running_headers": [],
        "examples_do_not_delete": [],
        "likely_heading_body_patterns": [],
        "likely_fragmentation_patterns": [],
        "warnings": [],
    }
    repeated_counter = Counter(
        block.normalized_text
        for block in blocks
        if 0 < block.char_count <= 120 and not block.is_heading and not block.is_toc_like
    )
    for block in blocks:
        normalized = block.normalized_text
        count = repeated_counter.get(normalized, 0)
        if count < 2:
            continue
        if normalized not in {entry["pattern"] for entry in repeated_noise_patterns}:
            repeated_noise_patterns.append(
                {
                    "pattern": normalized,
                    "reason": _heuristic_reason(block),
                    "confidence": "high" if count >= 3 else "medium",
                    "count": count,
                }
            )
        candidate_block_ids.append(block.block_id)

    if config.keep_toc:
        warnings.append("toc_blocks_protected_keep_toc_true")
    if config.drop_back_matter:
        warnings.append("drop_back_matter_unsupported_noop")

    if config.global_plan_enabled and global_plan_provider is not None:
        try:
            ai_plan = _parse_global_plan_response(
                global_plan_provider(
                    {
                        "raw_markdown": raw_markdown,
                        "block_count": len(blocks),
                        "blocks": [block.to_payload() for block in blocks],
                        "required_fields": list(ai_plan.keys()),
                    }
                )
            )
        except Exception as exc:
            warnings.append(f"reader_cleanup_global_plan_failed:{exc}")

    ai_warnings = ai_plan.get("warnings")
    if isinstance(ai_warnings, list):
        warnings.extend(str(item) for item in ai_warnings if str(item).strip())

    return {
        "repeated_noise_patterns": _coerce_string_list(ai_plan.get("repeated_noise_patterns")) + repeated_noise_patterns,
        "candidate_block_ids": candidate_block_ids,
        "document_specific_running_headers": _coerce_string_list(ai_plan.get("document_specific_running_headers")),
        "examples_do_not_delete": _coerce_string_list(ai_plan.get("examples_do_not_delete")),
        "likely_heading_body_patterns": _coerce_string_list(ai_plan.get("likely_heading_body_patterns")),
        "likely_fragmentation_patterns": _coerce_string_list(ai_plan.get("likely_fragmentation_patterns")),
        "warnings": warnings,
    }


def _parse_global_plan_response(raw_response: str) -> dict[str, object]:
    payload = json.loads(raw_response)
    if not isinstance(payload, dict):
        raise RuntimeError("reader_cleanup_global_plan_must_be_object")
    allowed_fields = {
        "repeated_noise_patterns",
        "document_specific_running_headers",
        "examples_do_not_delete",
        "likely_heading_body_patterns",
        "likely_fragmentation_patterns",
        "warnings",
    }
    unknown_fields = sorted(set(payload.keys()) - allowed_fields)
    if unknown_fields:
        raise RuntimeError(f"reader_cleanup_global_plan_unknown_fields:{','.join(unknown_fields)}")
    normalized: dict[str, object] = {}
    for field in allowed_fields:
        value = payload.get(field, [])
        if not isinstance(value, list):
            raise RuntimeError(f"reader_cleanup_global_plan_field_must_be_list:{field}")
        normalized[field] = value[:50]
    return normalized


def _build_chunk_request_payload(
    *,
    chunk: CleanupChunk,
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    readonly_before = [block.to_payload() for block in chunk.context_before_blocks]
    readonly_after = [block.to_payload() for block in chunk.context_after_blocks]
    operation_selection_targets = _build_operation_selection_targets(blocks=chunk.blocks)
    payload: dict[str, object] = {
        "policy": config.policy,
        "keep_toc": config.keep_toc,
        "drop_back_matter": config.drop_back_matter,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "output_format_requirements": {
            "format": "single_json_object",
            "markdown_fences_allowed": False,
            "prose_before_or_after_json_allowed": False,
            "noop_response": {"cleanup_operations": [], "warnings": []},
        },
        "response_contract": {
            "top_level_fields": ["cleanup_operations", "warnings"],
            "legacy_top_level_fields": ["delete_blocks"],
            "required_cleanup_operation_fields": [
                "id",
                "text_hash",
                "operation",
                "reason",
                "confidence",
                "evidence_before",
                "expected_after_preview",
                "safety_note",
            ],
            "allowed_operations": sorted(_ALLOWED_OPERATIONS),
            "allowed_delete_reasons": sorted(_ALLOWED_DELETE_REASONS),
            "reason_guidance_by_operation": {
                "delete_block": sorted(_ALLOWED_DELETE_REASONS),
                "remove_inline_noise": sorted(_REMOVE_INLINE_NOISE_REASON_GUIDANCE),
            },
            "allowed_confidence": ["low", "medium", "high"],
            "example": {
                "cleanup_operations": [
                    {
                        "id": "b_000123",
                        "text_hash": "7f83b1657ff1fc53",
                        "operation": "delete_block",
                        "reason": "extraction_artifact",
                        "confidence": "high",
                        "evidence_before": "standalone placeholder block",
                        "expected_after_preview": "",
                        "safety_note": "non-semantic extraction artifact only",
                    }
                ],
                "warnings": [],
            },
        },
        "editable_block_ids": [block.block_id for block in chunk.blocks],
        "context_before_preview": chunk.context_before[:240],
        "context_after_preview": chunk.context_after[:240],
        "global_plan": global_plan,
        "operation_selection_targets": operation_selection_targets,
        "blocks": [block.to_payload() for block in chunk.blocks],
    }
    if readonly_before or readonly_after:
        payload.update(
            {
                "readonly_context_block_ids": [block["id"] for block in readonly_before + readonly_after],
                "readonly_context_blocks_before": readonly_before,
                "readonly_context_blocks_after": readonly_after,
            }
        )
    return payload


def _build_operation_selection_targets(*, blocks: Sequence[CleanupBlock]) -> list[dict[str, object]]:
    targets: list[dict[str, object]] = []
    for block in blocks:
        duplicate_target = _build_duplicate_semantic_heading_target(block=block)
        if duplicate_target is not None:
            targets.append(duplicate_target)
        targets.extend(_build_side_heading_island_targets(block=block))
    return targets[:20]


def _build_duplicate_semantic_heading_target(*, block: CleanupBlock) -> dict[str, object] | None:
    duplicate = _find_adjacent_duplicate_phrase(block.text)
    if duplicate is None:
        return None
    noise_substring = duplicate["noise_substring"]
    return {
        "category": "duplicate_semantic_heading_text",
        "id": block.block_id,
        "text_hash": block.text_hash,
        "operation_hint": "remove_inline_noise",
        "reason_hint": "duplicate_fragment",
        "noise_substring": noise_substring,
        "expected_after_preview": _inline_noise_removed_text(current_text=block.text, noise=noise_substring),
        "safety_note": "Apply only if this exact adjacent repeated phrase is still present once in the editable block.",
    }


def _find_adjacent_duplicate_phrase(text: str) -> dict[str, str] | None:
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", text or ""))
    if len(tokens) < 4:
        return None
    for phrase_len in range(8, 1, -1):
        if len(tokens) < phrase_len * 2:
            continue
        for start in range(0, len(tokens) - (phrase_len * 2) + 1):
            first = tokens[start : start + phrase_len]
            second = tokens[start + phrase_len : start + (phrase_len * 2)]
            first_words = [match.group(0).lower() for match in first]
            second_words = [match.group(0).lower() for match in second]
            if first_words != second_words:
                continue
            noise_start = second[0].start()
            noise_end = second[-1].end()
            while noise_end < len(text) and text[noise_end].isspace():
                noise_end += 1
            return {"noise_substring": text[noise_start:noise_end]}
    return None


def _build_side_heading_island_targets(*, block: CleanupBlock) -> list[dict[str, object]]:
    if block.is_heading or block.is_toc_like or block.char_count < 40:
        return []
    targets: list[dict[str, object]] = []
    tokens = list(re.finditer(r"[A-Za-zА-Яа-яЁё]{2,}", block.text))
    if len(tokens) < 6:
        return []
    for phrase_len in range(3, 6):
        for start in range(1, len(tokens) - phrase_len):
            phrase_tokens = tokens[start : start + phrase_len]
            before_text = block.text[: phrase_tokens[0].start()]
            after_text = block.text[phrase_tokens[-1].end() :]
            if not _has_side_heading_left_context(before_text):
                continue
            if not _has_side_heading_right_context(after_text):
                continue
            phrase = block.text[phrase_tokens[0].start() : phrase_tokens[-1].end()]
            if not _looks_like_side_heading_phrase(phrase):
                continue
            targets.append(
                {
                    "category": "side_heading_island_candidate",
                    "id": block.block_id,
                    "text_hash": block.text_hash,
                    "heading_candidate": phrase,
                    "operation_hint": "preserve_heading_text_with_split_block_or_normalize_heading_boundary",
                    "preferred_operation_order": ["split_block", "normalize_heading_boundary"],
                    "forbidden_default_operation": "remove_inline_noise",
                    "safety_note": "Semantic heading islands are not noise. Do not delete with remove_inline_noise; preserve all semantic text with exact split_block or normalize_heading_boundary, or skip if boundaries are unclear.",
                }
            )
            if len(targets) >= 3:
                return targets
    return targets


def _has_side_heading_left_context(text: str) -> bool:
    before = str(text or "").rstrip()
    if not before:
        return False
    if before[-1] in ".!?;:…":
        return False
    return re.search(r"[a-zа-яё][,\s\"'«»“”„-]*$", before) is not None


def _has_side_heading_right_context(text: str) -> bool:
    after = str(text or "").lstrip()
    return re.match(r"[a-zа-яё]", after) is not None


def _looks_like_side_heading_phrase(phrase: str) -> bool:
    if re.search(r"\b(?:and|for|from|in|of|or|the|to|в|во|для|и|или|к|на|о|от|по|с|со|у)\b", phrase, re.IGNORECASE):
        return False
    words = _semantic_word_tokens(phrase)
    if len(words) < 3 or len(words) > 5:
        return False
    if any(word.isdigit() for word in words):
        return False
    if not words[0][0].isupper():
        return False
    uppercase_count = sum(1 for word in words if word[0].isupper())
    return uppercase_count == 1


def _build_failed_chunk_diagnostics(
    *,
    chunk: CleanupChunk,
    config: ReaderCleanupConfig,
    request_payload_char_count: int,
    raw_response: str,
    parse_error_message: str,
    retry_attempted: bool,
    retry_status: str,
    retry_error: str,
    repair_attempted: bool,
    repair_status: str,
    repair_error: str,
) -> dict[str, object]:
    stripped_response = str(raw_response or "").strip()
    return {
        "chunk_index": chunk.chunk_index,
        "primary_block_id_range": {
            "first": chunk.blocks[0].block_id if chunk.blocks else "",
            "last": chunk.blocks[-1].block_id if chunk.blocks else "",
        },
        "cleanup_model_selector": config.model,
        "request_payload_char_count": request_payload_char_count,
        "approx_prompt_input_char_count": request_payload_char_count,
        "raw_response_empty": not bool(stripped_response),
        "raw_response_char_count": len(raw_response or ""),
        "raw_response_preview": _preview_text(raw_response, limit=1000),
        "parse_error_message": parse_error_message,
        "retry_attempted": retry_attempted,
        "retry_status": retry_status,
        "retry_error": retry_error,
        "repair_attempted": repair_attempted,
        "repair_status": repair_status,
        "repair_error": repair_error,
    }


def _preview_text(value: object, *, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _build_anchor_repair_request_payload(
    *,
    chunk: CleanupChunk,
    anchors: Sequence[Mapping[str, str]],
    global_plan: Mapping[str, object],
    config: ReaderCleanupConfig,
) -> dict[str, object]:
    payload = _build_chunk_request_payload(chunk=chunk, global_plan=global_plan, config=config)
    payload.update(
        {
            "pass_name": "anchor_repair",
            "anchor_targets": [dict(anchor) for anchor in anchors],
            "anchor_window_block_ids": [block.block_id for block in chunk.blocks],
        }
    )
    return payload


def _build_cleanup_stats(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
) -> dict[str, object]:
    total_non_whitespace_chars = sum(block.non_whitespace_char_count for block in blocks)
    failed_chunk_count = sum(1 for entry in chunk_results if entry.get("status") == "failed")
    proposed_cleanup_operation_count = sum(
        _coerce_int(
            entry.get("proposed_cleanup_operation_count", entry.get("proposed_delete_block_count")),
            default=0,
            minimum=0,
        )
        for entry in chunk_results
    )
    proposed_delete_block_count = sum(
        _coerce_int(entry.get("proposed_delete_block_count"), default=0, minimum=0) for entry in chunk_results
    )
    return {
        "raw_block_count": len(blocks),
        "raw_char_count": len(raw_markdown),
        "cleanup_chunk_count": len(chunk_results),
        "failed_chunk_count": failed_chunk_count,
        "proposed_cleanup_operation_count": proposed_cleanup_operation_count,
        "proposed_delete_block_count": proposed_delete_block_count,
        "accepted_cleanup_operation_count": len(accepted_cleanup_operations),
        "accepted_delete_block_count": len(accepted_delete_blocks),
        "ignored_cleanup_operation_count": len(ignored_cleanup_operations),
        "ignored_delete_block_count": len(ignored_cleanup_operations),
        "deleted_non_whitespace_char_count": deleted_char_count,
        "deleted_char_ratio": 0.0 if total_non_whitespace_chars <= 0 else round(deleted_char_count / total_non_whitespace_chars, 6),
    }


def _serialize_cleanup_settings(config: ReaderCleanupConfig) -> dict[str, object]:
    return {
        "model_selector": config.model,
        "chunk_size": config.chunk_size,
        "overlap_blocks_before": config.overlap_blocks_before,
        "overlap_blocks_after": config.overlap_blocks_after,
        "global_plan_enabled": config.global_plan_enabled,
    }


def _build_reader_cleanup_report_payload(
    *,
    raw_markdown: str,
    config: ReaderCleanupConfig,
    blocks: Sequence[CleanupBlock],
    global_plan: Mapping[str, object],
    warnings: Sequence[str],
    accepted_delete_blocks: Sequence[Mapping[str, object]],
    accepted_cleanup_operations: Sequence[Mapping[str, object]] = (),
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
    chunk_results: Sequence[Mapping[str, object]],
    deleted_char_count: int,
    changed: bool,
    model_resolution: Mapping[str, object] | None = None,
    failure: Mapping[str, object] | None = None,
) -> dict[str, object]:
    stats = _build_cleanup_stats(
        raw_markdown=raw_markdown,
        blocks=blocks,
        accepted_delete_blocks=accepted_delete_blocks,
        accepted_cleanup_operations=accepted_cleanup_operations,
        ignored_cleanup_operations=ignored_cleanup_operations,
        chunk_results=chunk_results,
        deleted_char_count=deleted_char_count,
    )
    report_payload = {
        "version": 1,
        "policy": config.policy,
        "model": config.model,
        "cleanup_settings": _serialize_cleanup_settings(config),
        "stage_status": "failed_preserved_base_result" if failure is not None else "completed",
        "changed": changed,
        "warnings": list(warnings),
        "stats": stats,
        "global_plan": dict(global_plan),
        "model_resolution": dict(model_resolution or {}),
        "accepted_cleanup_operations": list(accepted_cleanup_operations),
        "accepted_delete_blocks": list(accepted_delete_blocks),
        "ignored_cleanup_operations": list(ignored_cleanup_operations),
        "ignored_delete_blocks": list(ignored_cleanup_operations),
        "heading_boundary_application_diagnostics": _build_heading_boundary_application_diagnostics(
            accepted_cleanup_operations=accepted_cleanup_operations,
            ignored_cleanup_operations=ignored_cleanup_operations,
        ),
        "chunk_results": [dict(entry) for entry in chunk_results],
    }
    if failure is not None:
        report_payload["failure"] = dict(failure)
    return report_payload


def _build_heading_boundary_application_diagnostics(
    *,
    accepted_cleanup_operations: Sequence[Mapping[str, object]],
    ignored_cleanup_operations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    accepted_heading_operations = [
        dict(entry) for entry in accepted_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_heading_operations = [
        dict(entry) for entry in ignored_cleanup_operations if entry.get("operation") == "normalize_heading_boundary"
    ]
    ignored_reason_counts: Counter[str] = Counter(
        str(entry.get("ignored_reason") or "unknown") for entry in ignored_heading_operations
    )
    return {
        "accepted_count": len(accepted_heading_operations),
        "ignored_count": len(ignored_heading_operations),
        "ignored_reason_counts": dict(sorted(ignored_reason_counts.items())),
        "ignored_examples": [
            _build_heading_boundary_diagnostic_example(entry)
            for entry in ignored_heading_operations[:5]
        ],
    }


def _build_heading_boundary_diagnostic_example(entry: Mapping[str, object]) -> dict[str, object]:
    preview = str(entry.get("raw_text_preview") or entry.get("evidence_before") or "").replace("\n", " ").strip()
    if len(preview) > 180:
        preview = preview[:177].rstrip() + "..."
    heading = str(entry.get("heading_substring") or "").replace("\n", " ").strip()
    body = str(entry.get("body_substring") or "").replace("\n", " ").strip()
    if len(body) > 180:
        body = body[:177].rstrip() + "..."
    return {
        "chunk_index": _coerce_int(entry.get("chunk_index"), default=0, minimum=0),
        "ignored_reason": str(entry.get("ignored_reason") or "unknown"),
        "reason": str(entry.get("reason") or ""),
        "preview": preview,
        "heading_substring": heading,
        "body_substring_preview": body,
    }


def _load_cleanup_response_object(raw_response: str) -> dict[str, object] | None:
    try:
        payload = _load_cleanup_response_payload(raw_response)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return cast(dict[str, object], payload)


def _load_cleanup_response_payload(raw_response: str) -> object:
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        extracted = _extract_first_json_object_text(raw_response)
        if extracted is None:
            raise
        return json.loads(extracted)


def _extract_first_json_object_text(raw_response: str) -> str | None:
    text = str(raw_response or "")
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _build_cleanup_schema_repair_payload(
    *,
    request_payload: Mapping[str, object],
    original_response: Mapping[str, object],
    validation_error: str,
) -> dict[str, object]:
    payload = {
        "task": "repair_cleanup_response_schema",
        "pass_name": str(request_payload.get("pass_name") or "first_pass"),
        "response_contract": dict(cast(Mapping[str, object], request_payload.get("response_contract") or {})),
        "editable_block_ids": [str(item) for item in cast(Sequence[object], request_payload.get("editable_block_ids") or [])],
        "context_before_preview": str(request_payload.get("context_before_preview") or ""),
        "context_after_preview": str(request_payload.get("context_after_preview") or ""),
        "blocks": [dict(cast(Mapping[str, object], item)) for item in cast(Sequence[object], request_payload.get("blocks") or []) if isinstance(item, Mapping)],
        "validation_error": validation_error,
        "original_response": dict(original_response),
    }
    for key in ("readonly_context_block_ids", "readonly_context_blocks_before", "readonly_context_blocks_after"):
        value = request_payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            payload[key] = [
                dict(cast(Mapping[str, object], item)) if isinstance(item, Mapping) else str(item)
                for item in value
            ]
    anchor_targets = request_payload.get("anchor_targets")
    if isinstance(anchor_targets, Sequence) and not isinstance(anchor_targets, (str, bytes, bytearray)):
        payload["anchor_targets"] = [
            dict(cast(Mapping[str, object], item))
            for item in anchor_targets
            if isinstance(item, Mapping)
        ]
    anchor_window_block_ids = request_payload.get("anchor_window_block_ids")
    if isinstance(anchor_window_block_ids, Sequence) and not isinstance(anchor_window_block_ids, (str, bytes, bytearray)):
        payload["anchor_window_block_ids"] = [str(item) for item in anchor_window_block_ids]
    return payload


def _run_anchor_repair_pass(
    *,
    markdown_text: str,
    config: ReaderCleanupConfig,
    global_plan: Mapping[str, object],
    anchor_targets: Sequence[Mapping[str, object]],
    operation_provider: Callable[[dict[str, Any], int, int], str],
    repair_provider: Callable[[dict[str, Any], int, int], str] | None,
) -> AnchorRepairPassResult:
    raw_markdown = str(markdown_text or "")
    blocks = build_cleanup_blocks(raw_markdown)
    normalized_targets, warnings = _normalize_anchor_targets(anchor_targets=anchor_targets, blocks=blocks)
    anchor_chunks, selected_window_block_count = _build_anchor_repair_chunks(
        blocks=blocks,
        anchor_targets=normalized_targets,
        chunk_size=config.chunk_size,
    )
    if not anchor_chunks:
        return AnchorRepairPassResult(
            cleaned_markdown=raw_markdown,
            warnings=tuple(warnings),
            accepted_delete_blocks=(),
            accepted_cleanup_operations=(),
            ignored_cleanup_operations=(),
            chunk_results=(),
            deleted_char_count=0,
            requested_anchor_count=len(anchor_targets),
            selected_anchor_count=len(normalized_targets),
            selected_window_block_count=selected_window_block_count,
            selected_anchors=tuple(normalized_targets),
        )

    all_operations: list[CleanupOperation] = []
    ignored_cleanup_operations: list[dict[str, object]] = []
    chunk_results: list[dict[str, object]] = []
    for anchor_chunk in anchor_chunks:
        chunk = anchor_chunk.chunk
        request_payload = _build_anchor_repair_request_payload(
            chunk=chunk,
            anchors=anchor_chunk.anchors,
            global_plan=global_plan,
            config=config,
        )
        started_at = time.perf_counter()
        raw_response = ""
        schema_validation_error = ""
        repair_error = ""
        repair_attempted = False
        repair_status = "not_attempted"
        ignored_chunk_operations: list[dict[str, object]] = []
        try:
            raw_response = operation_provider(request_payload, chunk.chunk_index, len(anchor_chunks))
            editable_blocks = {block.block_id: block for block in chunk.blocks}
            try:
                operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                    raw_response=raw_response,
                    editable_blocks=editable_blocks,
                    chunk_index=chunk.chunk_index,
                )
            except Exception as exc:
                original_response_payload = _load_cleanup_response_object(raw_response)
                if repair_provider is None or original_response_payload is None:
                    raise
                schema_validation_error = str(exc)
                repair_attempted = True
                repair_status = "attempted"
                warnings.append(
                    f"reader_cleanup_anchor_schema_validation_failed:{chunk.chunk_index}:{schema_validation_error}"
                )
                warnings.append(f"reader_cleanup_anchor_schema_repair_attempted:{chunk.chunk_index}")
                repaired_response = repair_provider(
                    _build_cleanup_schema_repair_payload(
                        request_payload=request_payload,
                        original_response=original_response_payload,
                        validation_error=schema_validation_error,
                    ),
                    chunk.chunk_index,
                    len(anchor_chunks),
                )
                try:
                    operations, chunk_warnings, ignored_chunk_operations = _parse_cleanup_response(
                        raw_response=repaired_response,
                        editable_blocks=editable_blocks,
                        chunk_index=chunk.chunk_index,
                    )
                except Exception as repair_exc:
                    repair_status = "failed"
                    repair_error = str(repair_exc)
                    warnings.append(f"reader_cleanup_anchor_schema_repair_failed:{chunk.chunk_index}:{repair_error}")
                    raise
                repair_status = "succeeded"
                warnings.append(f"reader_cleanup_anchor_schema_repair_succeeded:{chunk.chunk_index}")
        except Exception as exc:
            warnings.append(f"reader_cleanup_anchor_chunk_failed:{chunk.chunk_index}:{exc}")
            chunk_results.append(
                {
                    "pass_name": "anchor_repair",
                    "chunk_index": chunk.chunk_index,
                    "status": "failed",
                    "target_block_count": len(chunk.blocks),
                    "target_chars": sum(block.char_count for block in chunk.blocks),
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    "proposed_cleanup_operation_count": 0,
                    "proposed_delete_block_count": 0,
                    "accepted_cleanup_operation_count": 0,
                    "accepted_delete_block_count": 0,
                    "ignored_cleanup_operation_count": 0,
                    "ignored_delete_block_count": 0,
                    "repair_attempted": repair_attempted,
                    "repair_status": repair_status,
                    "schema_validation_error": schema_validation_error,
                    "repair_error": repair_error,
                    "anchor_ids": [str(anchor.get("anchor_id") or "") for anchor in anchor_chunk.anchors],
                    "warning": f"reader_cleanup_anchor_chunk_failed:{chunk.chunk_index}:{exc}",
                }
            )
            continue

        operations, scope_ignored_operations = _filter_anchor_repair_operations_to_anchor_targets(
            operations=operations,
            anchors=anchor_chunk.anchors,
            editable_blocks=editable_blocks,
        )
        all_operations.extend(operations)
        warnings.extend(chunk_warnings)
        ignored_cleanup_operations.extend(ignored_chunk_operations)
        ignored_cleanup_operations.extend(scope_ignored_operations)
        chunk_results.append(
            {
                "pass_name": "anchor_repair",
                "chunk_index": chunk.chunk_index,
                "status": "completed",
                "target_block_count": len(chunk.blocks),
                "target_chars": sum(block.char_count for block in chunk.blocks),
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 3),
                "proposed_cleanup_operation_count": len(operations)
                + len(ignored_chunk_operations)
                + len(scope_ignored_operations),
                "proposed_delete_block_count": sum(1 for operation in operations if operation.operation == "delete_block")
                + sum(1 for operation in scope_ignored_operations if operation.get("operation") == "delete_block"),
                "accepted_cleanup_operation_count": 0,
                "accepted_delete_block_count": 0,
                "ignored_cleanup_operation_count": 0,
                "ignored_delete_block_count": 0,
                "repair_attempted": repair_attempted,
                "repair_status": repair_status,
                "schema_validation_error": schema_validation_error,
                "repair_error": repair_error,
                "anchor_ids": [str(anchor.get("anchor_id") or "") for anchor in anchor_chunk.anchors],
            }
        )

    cleaned_markdown, accepted_ids, accepted_cleanup_operations, apply_ignored_cleanup_operations = _apply_cleanup_operations(
        raw_markdown=raw_markdown,
        blocks=blocks,
        operations=all_operations,
        config=config,
        global_candidate_block_ids={block.block_id for anchor_chunk in anchor_chunks for block in anchor_chunk.chunk.blocks},
    )
    ignored_cleanup_operations.extend(apply_ignored_cleanup_operations)
    accepted_counts_by_chunk: Counter[int] = Counter()
    accepted_delete_blocks: list[dict[str, object]] = []
    for block_id, entry in accepted_ids.items():
        block = _block_by_id(blocks, block_id)
        chunk_index = _coerce_int(entry.get("chunk_index"), default=0, minimum=0)
        accepted_delete_blocks.append(
            {
                **_serialize_delete_block(block=block, reason=str(entry["reason"]), confidence=str(entry["confidence"])),
                "pass_name": "anchor_repair",
                "chunk_index": chunk_index,
                "after_state": "deleted",
            }
        )
        accepted_counts_by_chunk[chunk_index] += 1

    ignored_counts_by_chunk: Counter[int] = Counter()
    for entry in ignored_cleanup_operations:
        chunk_index = entry.get("chunk_index")
        if isinstance(chunk_index, int):
            ignored_counts_by_chunk[chunk_index] += 1

    normalized_accepted_cleanup_operations = [
        {**entry, "pass_name": "anchor_repair"} for entry in accepted_cleanup_operations
    ]
    normalized_ignored_cleanup_operations = [{**entry, "pass_name": "anchor_repair"} for entry in ignored_cleanup_operations]

    for chunk_result in chunk_results:
        chunk_index = chunk_result.get("chunk_index")
        if not isinstance(chunk_index, int) or chunk_result.get("status") != "completed":
            continue
        accepted_cleanup_count = sum(
            1 for entry in normalized_accepted_cleanup_operations if entry.get("chunk_index") == chunk_index
        )
        chunk_result["accepted_delete_block_count"] = accepted_counts_by_chunk.get(chunk_index, 0)
        chunk_result["accepted_cleanup_operation_count"] = accepted_cleanup_count
        chunk_result["ignored_delete_block_count"] = ignored_counts_by_chunk.get(chunk_index, 0)
        chunk_result["ignored_cleanup_operation_count"] = ignored_counts_by_chunk.get(chunk_index, 0)

    deleted_char_count = sum(_block_by_id(blocks, block_id).non_whitespace_char_count for block_id in accepted_ids)
    return AnchorRepairPassResult(
        cleaned_markdown=cleaned_markdown,
        warnings=tuple(warnings),
        accepted_delete_blocks=tuple(accepted_delete_blocks),
        accepted_cleanup_operations=tuple(normalized_accepted_cleanup_operations),
        ignored_cleanup_operations=tuple(normalized_ignored_cleanup_operations),
        chunk_results=tuple(chunk_results),
        deleted_char_count=deleted_char_count,
        requested_anchor_count=len(anchor_targets),
        selected_anchor_count=len(normalized_targets),
        selected_window_block_count=selected_window_block_count,
        selected_anchors=tuple(normalized_targets),
    )


def _filter_anchor_repair_operations_to_anchor_targets(
    *,
    operations: Sequence[CleanupOperation],
    anchors: Sequence[Mapping[str, str]],
    editable_blocks: Mapping[str, CleanupBlock],
) -> tuple[list[CleanupOperation], list[dict[str, object]]]:
    anchor_categories_by_block: dict[str, set[str]] = {}
    for anchor in anchors:
        block_id = str(anchor.get("block_id") or "")
        category = str(anchor.get("category") or "")
        if block_id and category:
            anchor_categories_by_block.setdefault(block_id, set()).add(category)
    anchor_block_ids = set(anchor_categories_by_block)
    page_anchor_block_ids = {
        block_id
        for block_id, categories in anchor_categories_by_block.items()
        if "page_furniture_inline" in categories
    }
    page_anchor_blocks_with_noise_removal = {
        operation.block_id
        for operation in operations
        if operation.operation == "remove_inline_noise"
        and operation.block_id in page_anchor_block_ids
        and operation.reason in _INLINE_NOISE_REASON_GUIDANCE
    }

    filtered_operations: list[CleanupOperation] = []
    ignored_operations: list[dict[str, object]] = []
    for operation in operations:
        ignored_reason = ""
        if operation.block_id not in anchor_block_ids and not _is_allowed_page_anchor_followup_join(
            operation=operation,
            page_anchor_blocks_with_noise_removal=page_anchor_blocks_with_noise_removal,
            editable_blocks=editable_blocks,
        ):
            ignored_reason = "anchor_repair_operation_outside_anchor_targets"
        elif (
            "page_furniture_inline" in anchor_categories_by_block.get(operation.block_id, set())
            and operation.operation in {"delete_block", "join_fragmented_paragraph"}
            and not _is_allowed_page_anchor_followup_join(
                operation=operation,
                page_anchor_blocks_with_noise_removal=page_anchor_blocks_with_noise_removal,
                editable_blocks=editable_blocks,
            )
        ):
            ignored_reason = "anchor_repair_page_furniture_requires_remove_inline_noise"

        if not ignored_reason:
            filtered_operations.append(operation)
            continue

        block = editable_blocks.get(operation.block_id)
        if block is None:
            ignored_operations.append(
                {
                    "id": operation.block_id,
                    "text_hash": operation.text_hash,
                    "operation": operation.operation,
                    "reason": operation.reason,
                    "confidence": operation.confidence,
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": ignored_reason,
                }
            )
            continue
        ignored_operations.append(
            {
                **_serialize_cleanup_operation(operation=operation, block=block),
                "chunk_index": operation.chunk_index,
                "ignored_reason": ignored_reason,
            }
        )
    return filtered_operations, ignored_operations


def _is_allowed_page_anchor_followup_join(
    *,
    operation: CleanupOperation,
    page_anchor_blocks_with_noise_removal: set[str],
    editable_blocks: Mapping[str, CleanupBlock],
) -> bool:
    if operation.operation != "join_fragmented_paragraph":
        return False
    block = editable_blocks.get(operation.block_id)
    next_block = editable_blocks.get(operation.next_id)
    if block is None or next_block is None:
        return False
    if next_block.index != block.index + 1:
        return False
    return operation.next_id in page_anchor_blocks_with_noise_removal or operation.block_id in page_anchor_blocks_with_noise_removal


def _merge_anchor_repair_pass_into_report(
    *,
    report_payload: Mapping[str, object],
    raw_markdown: str,
    raw_blocks: Sequence[CleanupBlock],
    anchor_pass_result: AnchorRepairPassResult,
) -> dict[str, object]:
    merged_report = dict(report_payload)
    first_pass_stats = dict(cast(Mapping[str, object], merged_report.get("stats") or {}))
    first_pass_chunk_results = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("chunk_results") or [])
    ]
    first_pass_accepted_cleanup_operations = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("accepted_cleanup_operations") or [])
    ]
    first_pass_accepted_delete_blocks = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(Sequence[Mapping[str, object]], merged_report.get("accepted_delete_blocks") or [])
    ]
    first_pass_ignored_cleanup_operations = [
        {**dict(entry), "pass_name": str(dict(entry).get("pass_name") or "first_pass")}
        for entry in cast(
            Sequence[Mapping[str, object]],
            merged_report.get("ignored_cleanup_operations") or merged_report.get("ignored_delete_blocks") or [],
        )
    ]

    combined_chunk_results = first_pass_chunk_results + [dict(entry) for entry in anchor_pass_result.chunk_results]
    combined_accepted_cleanup_operations = first_pass_accepted_cleanup_operations + [
        dict(entry) for entry in anchor_pass_result.accepted_cleanup_operations
    ]
    combined_accepted_delete_blocks = first_pass_accepted_delete_blocks + [
        dict(entry) for entry in anchor_pass_result.accepted_delete_blocks
    ]
    combined_ignored_cleanup_operations = first_pass_ignored_cleanup_operations + [
        dict(entry) for entry in anchor_pass_result.ignored_cleanup_operations
    ]
    combined_deleted_char_count = _coerce_int(
        cast(Mapping[str, object], merged_report.get("stats") or {}).get("deleted_non_whitespace_char_count"),
        default=0,
        minimum=0,
    ) + anchor_pass_result.deleted_char_count
    merged_report["warnings"] = list(cast(Sequence[str], merged_report.get("warnings") or [])) + list(anchor_pass_result.warnings)
    merged_report["accepted_cleanup_operations"] = combined_accepted_cleanup_operations
    merged_report["accepted_delete_blocks"] = combined_accepted_delete_blocks
    merged_report["ignored_cleanup_operations"] = combined_ignored_cleanup_operations
    merged_report["ignored_delete_blocks"] = combined_ignored_cleanup_operations
    merged_report["heading_boundary_application_diagnostics"] = _build_heading_boundary_application_diagnostics(
        accepted_cleanup_operations=combined_accepted_cleanup_operations,
        ignored_cleanup_operations=combined_ignored_cleanup_operations,
    )
    merged_report["chunk_results"] = combined_chunk_results
    merged_report["stats"] = _build_cleanup_stats(
        raw_markdown=raw_markdown,
        blocks=raw_blocks,
        accepted_delete_blocks=combined_accepted_delete_blocks,
        accepted_cleanup_operations=combined_accepted_cleanup_operations,
        ignored_cleanup_operations=combined_ignored_cleanup_operations,
        chunk_results=combined_chunk_results,
        deleted_char_count=combined_deleted_char_count,
    )
    merged_report["passes"] = {
        "first_pass": {
            "stats": first_pass_stats,
        },
        "anchor_repair_pass": {
            "requested_anchor_count": anchor_pass_result.requested_anchor_count,
            "selected_anchor_count": anchor_pass_result.selected_anchor_count,
            "selected_window_block_count": anchor_pass_result.selected_window_block_count,
            "selected_anchors": [dict(anchor) for anchor in anchor_pass_result.selected_anchors],
            "warnings": list(anchor_pass_result.warnings),
            "stats": _build_cleanup_stats(
                raw_markdown=anchor_pass_result.cleaned_markdown,
                blocks=build_cleanup_blocks(anchor_pass_result.cleaned_markdown),
                accepted_delete_blocks=anchor_pass_result.accepted_delete_blocks,
                accepted_cleanup_operations=anchor_pass_result.accepted_cleanup_operations,
                ignored_cleanup_operations=anchor_pass_result.ignored_cleanup_operations,
                chunk_results=anchor_pass_result.chunk_results,
                deleted_char_count=anchor_pass_result.deleted_char_count,
            ),
            "chunk_results": [dict(entry) for entry in anchor_pass_result.chunk_results],
        },
    }
    return merged_report


def _parse_cleanup_response(
    *,
    raw_response: str,
    editable_blocks: Mapping[str, CleanupBlock],
    readonly_context_blocks: Mapping[str, CleanupBlock] | None = None,
    chunk_index: int,
) -> tuple[list[CleanupOperation], list[str], list[dict[str, object]]]:
    payload = _load_cleanup_response_payload(raw_response)
    if not isinstance(payload, dict):
        raise RuntimeError("reader_cleanup_response_must_be_object")

    unknown_top_level = sorted(set(payload.keys()) - _TOP_LEVEL_RESPONSE_FIELDS)
    if unknown_top_level:
        raise RuntimeError(f"reader_cleanup_unknown_top_level_fields:{','.join(unknown_top_level)}")

    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        raise RuntimeError("reader_cleanup_warnings_must_be_string_list")

    delete_blocks = payload.get("delete_blocks", [])
    if not isinstance(delete_blocks, list):
        raise RuntimeError("reader_cleanup_delete_blocks_must_be_list")

    cleanup_operations = payload.get("cleanup_operations")
    cleanup_source = "cleanup_operations"
    if cleanup_operations is None:
        if delete_blocks:
            raise RuntimeError("reader_cleanup_legacy_delete_blocks_require_schema_repair")
        cleanup_items = delete_blocks
        cleanup_source = "legacy_delete_blocks"
    else:
        cleanup_items = cleanup_operations
    if not isinstance(cleanup_items, list):
        raise RuntimeError("reader_cleanup_operations_must_be_list")

    operations: list[CleanupOperation] = []
    ignored_operations: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for item in cleanup_items:
        if not isinstance(item, dict):
            raise RuntimeError("reader_cleanup_operation_item_must_be_object")
        item_with_operation = dict(item)
        if "operation" not in item_with_operation:
            item_with_operation["operation"] = "delete_block"
        normalized_item, normalization_warnings = _normalize_delete_block_item(
            item=item_with_operation,
            editable_blocks=editable_blocks,
            cleanup_source=cleanup_source,
        )
        if "operation" not in normalized_item:
            normalized_item["operation"] = "delete_block"
        warnings.extend(normalization_warnings)

        block_id = _require_nonempty_str(normalized_item, "id")
        text_hash = _require_nonempty_str(normalized_item, "text_hash")
        operation_name = _require_nonempty_str(normalized_item, "operation")
        reason = _require_nonempty_str(normalized_item, "reason")
        confidence = _require_nonempty_str(normalized_item, "confidence").lower()
        if operation_name == "delete_block":
            unknown_block_fields = sorted(
                set(item.keys()) - (_BLOCK_RESPONSE_FIELDS | {"operation", "evidence_before", "expected_after_preview", "safety_note"})
            )
        else:
            unknown_block_fields = sorted(set(item.keys()) - _OPERATION_RESPONSE_FIELDS)
        if unknown_block_fields:
            raise RuntimeError(f"reader_cleanup_unknown_operation_fields:{','.join(unknown_block_fields)}")

        if operation_name not in _ALLOWED_OPERATIONS:
            raise RuntimeError(f"reader_cleanup_unknown_operation:{operation_name}")
        if operation_name == "delete_block" and reason not in _ALLOWED_DELETE_REASONS:
            raise RuntimeError(f"reader_cleanup_unknown_reason:{reason}")
        if confidence not in _ALLOWED_CONFIDENCE:
            raise RuntimeError(f"reader_cleanup_unknown_confidence:{confidence}")
        split_substrings = normalized_item.get("split_substrings")
        readonly_context_block = (readonly_context_blocks or {}).get(block_id)
        if block_id not in editable_blocks:
            if readonly_context_block is None:
                raise RuntimeError(f"reader_cleanup_block_outside_chunk:{block_id}")
            ignored_operation = CleanupOperation(
                block_id=block_id,
                text_hash=text_hash,
                operation=operation_name,
                reason=reason,
                confidence=cast(CleanupConfidence, confidence),
                chunk_index=chunk_index,
                evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                expected_after_preview=str(normalized_item.get("expected_after_preview") or "").strip(),
                safety_note=str(normalized_item.get("safety_note") or "").strip(),
                split_substrings=tuple(
                    str(part).strip() for part in split_substrings if str(part).strip()
                )
                if isinstance(split_substrings, list)
                else (),
                noise_substring=str(normalized_item.get("noise_substring") or ""),
                next_id=str(normalized_item.get("next_id") or "").strip(),
                next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                heading_substring=str(normalized_item.get("heading_substring") or ""),
                body_substring=str(normalized_item.get("body_substring") or ""),
            )
            ignored_operations.append(
                {
                    **_serialize_cleanup_operation(operation=ignored_operation, block=readonly_context_block),
                    "chunk_index": chunk_index,
                    "ignored_reason": "readonly_context_block",
                }
            )
            warnings.append(f"reader_cleanup_readonly_context_operation_ignored:{chunk_index}:{block_id}")
            continue
        for required_field in ("evidence_before", "safety_note"):
            if not str(normalized_item.get(required_field) or "").strip():
                raise RuntimeError(f"reader_cleanup_operation_missing_required_field:{block_id}:{required_field}")

        seen_ids.add(block_id)
        if operation_name == "delete_block":
            if "expected_after_preview" not in normalized_item:
                normalized_item = dict(normalized_item)
                normalized_item["expected_after_preview"] = ""
                warnings.append(
                    f"reader_cleanup_expected_after_preview_recovered:{chunk_index}:{block_id}:{operation_name}"
                )
        elif not str(normalized_item.get("expected_after_preview") or "").strip():
            if operation_name in {"remove_inline_noise", "normalize_heading_boundary"}:
                raise RuntimeError(f"reader_cleanup_operation_missing_required_field:{block_id}:expected_after_preview")
            recovered_preview = _recover_expected_after_preview(
                operation_name=operation_name,
                normalized_item=normalized_item,
                block=editable_blocks[block_id],
                editable_blocks=editable_blocks,
            )
            if recovered_preview is None:
                ignored_operation = CleanupOperation(
                    block_id=block_id,
                    text_hash=text_hash,
                    operation=operation_name,
                    reason=reason,
                    confidence=cast(CleanupConfidence, confidence),
                    chunk_index=chunk_index,
                    evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                    expected_after_preview="",
                    safety_note=str(normalized_item.get("safety_note") or "").strip(),
                    split_substrings=tuple(
                        str(part).strip() for part in split_substrings if str(part).strip()
                    )
                    if isinstance(split_substrings, list)
                    else (),
                    noise_substring=str(normalized_item.get("noise_substring") or ""),
                    next_id=str(normalized_item.get("next_id") or "").strip(),
                    next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                    heading_substring=str(normalized_item.get("heading_substring") or ""),
                    body_substring=str(normalized_item.get("body_substring") or ""),
                )
                ignored_operations.append(
                    {
                        **_serialize_cleanup_operation(operation=ignored_operation, block=editable_blocks[block_id]),
                        "chunk_index": chunk_index,
                        "ignored_reason": "expected_after_preview_missing_unrecoverable",
                    }
                )
                warnings.append(
                    f"reader_cleanup_expected_after_preview_ignored:{chunk_index}:{block_id}:{operation_name}"
                )
                continue
            normalized_item = dict(normalized_item)
            normalized_item["expected_after_preview"] = recovered_preview
            warnings.append(
                f"reader_cleanup_expected_after_preview_recovered:{chunk_index}:{block_id}:{operation_name}"
            )

        normalized_item, exact_field_warnings = _recover_missing_operation_exact_fields(
            operation_name=operation_name,
            normalized_item=normalized_item,
            block=editable_blocks[block_id],
            chunk_index=chunk_index,
            block_id=block_id,
        )
        warnings.extend(exact_field_warnings)

        operations.append(
            CleanupOperation(
                block_id=block_id,
                text_hash=text_hash,
                operation=operation_name,
                reason=reason,
                confidence=cast(CleanupConfidence, confidence),
                chunk_index=chunk_index,
                evidence_before=str(normalized_item.get("evidence_before") or "").strip(),
                expected_after_preview=str(normalized_item.get("expected_after_preview") or "").strip(),
                safety_note=str(normalized_item.get("safety_note") or "").strip(),
                split_substrings=tuple(
                    str(part).strip() for part in split_substrings if str(part).strip()
                )
                if isinstance(split_substrings, list)
                else (),
                noise_substring=str(normalized_item.get("noise_substring") or ""),
                next_id=str(normalized_item.get("next_id") or "").strip(),
                next_text_hash=str(normalized_item.get("next_text_hash") or "").strip(),
                heading_substring=str(normalized_item.get("heading_substring") or ""),
                body_substring=str(normalized_item.get("body_substring") or ""),
            )
        )

    return operations, [str(item) for item in warnings], ignored_operations


def _recover_expected_after_preview(
    *,
    operation_name: str,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
    editable_blocks: Mapping[str, CleanupBlock],
) -> str | None:
    current_text = block.text
    if operation_name == "delete_block":
        return ""
    if operation_name == "split_block":
        raw_parts = normalized_item.get("split_substrings")
        if not isinstance(raw_parts, list):
            return None
        parts = [str(part).strip() for part in raw_parts if str(part).strip()]
        if len(parts) not in {2, 3}:
            return None
        pos = 0
        for part in parts:
            idx = current_text.find(part, pos)
            if idx == -1:
                return None
            if current_text[pos:idx].strip():
                return None
            pos = idx + len(part)
        if current_text[pos:].strip():
            return None
        return "\n\n".join(parts)
    if operation_name == "join_fragmented_paragraph":
        next_id = str(normalized_item.get("next_id") or "").strip()
        next_text_hash = str(normalized_item.get("next_text_hash") or "").strip()
        next_block = editable_blocks.get(next_id)
        if not next_id or not next_text_hash or next_block is None:
            return None
        if next_block.index != block.index + 1:
            return None
        if next_block.text_hash != next_text_hash:
            return None
        return f"{current_text.rstrip()} {next_block.text.lstrip()}"
    return None


def _inline_noise_removed_text(*, current_text: str, noise: str) -> str:
    noise_index = current_text.find(noise)
    if noise_index < 0:
        return re.sub(r"\s{2,}", " ", current_text.replace(noise, "", 1)).strip()
    before = current_text[:noise_index].rstrip()
    after = current_text[noise_index + len(noise) :].lstrip()
    joiner = " " if before and after else ""
    return re.sub(r"\s{2,}", " ", f"{before}{joiner}{after}").strip()


def _recover_inline_noise_substring_from_preview(
    *,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
) -> str | None:
    current_text = block.text.strip()
    expected_after = str(normalized_item.get("expected_after_preview") or "")
    expected_after = expected_after.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not current_text or not expected_after or expected_after == current_text:
        return None

    prefix_len = 0
    max_prefix_len = min(len(current_text), len(expected_after))
    while prefix_len < max_prefix_len and current_text[prefix_len] == expected_after[prefix_len]:
        prefix_len += 1

    suffix_len = 0
    max_suffix_len = min(len(current_text) - prefix_len, len(expected_after) - prefix_len)
    while (
        suffix_len < max_suffix_len
        and current_text[len(current_text) - suffix_len - 1]
        == expected_after[len(expected_after) - suffix_len - 1]
    ):
        suffix_len += 1

    candidate_end = len(current_text) - suffix_len
    candidate = current_text[prefix_len:candidate_end]
    if not candidate.strip():
        return None
    if current_text.count(candidate) != 1:
        return None
    reason = str(normalized_item.get("reason") or "").strip()
    if not _is_recoverable_inline_noise_substring_from_preview(
        noise=candidate,
        current_text=current_text,
        reason=reason,
    ):
        return None
    if _inline_noise_removed_text(current_text=current_text, noise=candidate) != expected_after:
        return None
    return candidate


def _is_recoverable_inline_noise_substring_from_preview(*, noise: str, current_text: str, reason: str) -> bool:
    normalized_noise = str(noise or "").strip()
    if not normalized_noise:
        return False
    if _SAFE_INLINE_NOISE_PATTERN.fullmatch(normalized_noise) is not None:
        return True
    return _looks_like_duplicate_inline_fragment_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    )


def _recover_missing_operation_exact_fields(
    *,
    operation_name: str,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
    chunk_index: int,
    block_id: str,
) -> tuple[dict[str, object], list[str]]:
    if operation_name == "remove_inline_noise":
        if str(normalized_item.get("noise_substring") or ""):
            return dict(normalized_item), []
        evidence_before = str(normalized_item.get("evidence_before") or "").strip()
        reason = str(normalized_item.get("reason") or "").strip()
        if (
            evidence_before
            and evidence_before in block.text
            and block.text.count(evidence_before) == 1
            and _is_safe_inline_noise_substring(noise=evidence_before, current_text=block.text, reason=reason)
        ):
            recovered = dict(normalized_item)
            recovered["noise_substring"] = evidence_before
            return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]
        preview_noise = _recover_inline_noise_substring_from_preview(
            normalized_item=normalized_item,
            block=block,
        )
        if preview_noise is not None:
            recovered = dict(normalized_item)
            recovered["noise_substring"] = preview_noise
            return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]
        return dict(normalized_item), []
    if operation_name != "normalize_heading_boundary":
        return dict(normalized_item), []
    if str(normalized_item.get("heading_substring") or "").strip() and str(
        normalized_item.get("body_substring") or ""
    ).strip():
        return dict(normalized_item), []

    recovered_parts = _recover_heading_boundary_parts_from_preview(
        normalized_item=normalized_item,
        block=block,
    )
    if recovered_parts is None:
        return dict(normalized_item), []
    heading, body = recovered_parts

    recovered = dict(normalized_item)
    if not str(recovered.get("heading_substring") or "").strip():
        recovered["heading_substring"] = heading
    if not str(recovered.get("body_substring") or "").strip():
        recovered["body_substring"] = body
    return recovered, [f"reader_cleanup_exact_fields_recovered:{chunk_index}:{block_id}:{operation_name}"]


def _recover_heading_boundary_parts_from_preview(
    *,
    normalized_item: Mapping[str, object],
    block: CleanupBlock,
) -> tuple[str, str] | None:
    preview = str(normalized_item.get("expected_after_preview") or "").replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n", preview, maxsplit=1) if part.strip()]
    if len(parts) != 2:
        return None
    heading, body_preview = parts
    if not heading or not body_preview:
        return None

    current_text = block.text.strip()
    heading_start = current_text.find(heading)
    if heading_start < 0 or current_text.count(heading) != 1:
        return None
    prefix = current_text[:heading_start]
    if prefix.strip() and not _is_safe_inline_noise_substring(
        noise=prefix,
        current_text=current_text,
        reason=str(normalized_item.get("reason") or ""),
    ):
        return None

    remainder = current_text[heading_start + len(heading) :].lstrip()
    body_prefix = _strip_preview_ellipsis(body_preview)
    if not body_prefix or not remainder.startswith(body_prefix):
        return None
    if len(re.sub(r"\s+", "", body_prefix)) < 8:
        return None
    return heading, remainder


def _strip_preview_ellipsis(value: str) -> str:
    text = str(value or "").strip()
    while text.endswith(("...", "…")):
        text = text[:-3].rstrip() if text.endswith("...") else text[:-1].rstrip()
    return text


def _normalize_delete_block_item(
    *,
    item: Mapping[str, object],
    editable_blocks: Mapping[str, CleanupBlock],
    cleanup_source: str,
) -> tuple[dict[str, object], list[str]]:
    normalized_item = dict(item)
    warnings: list[str] = []
    confidence = normalized_item.get("confidence")

    block_id = normalized_item.get("id")
    reason = normalized_item.get("reason")
    if not isinstance(block_id, str) or not block_id.strip():
        return normalized_item, warnings
    if not isinstance(reason, str) or not reason.strip():
        return normalized_item, warnings

    block = editable_blocks.get(block_id.strip())
    if not isinstance(confidence, str) or not confidence.strip():
        expected_kind = _SAFE_CONFIDENCE_INFERENCE.get(reason.strip())
        if block is not None and expected_kind is not None and block.kind == expected_kind:
            normalized_item["confidence"] = "high"
            warnings.append(f"reader_cleanup_missing_confidence_inferred:{block.block_id}:high")

    return normalized_item, warnings


def _apply_cleanup_operations(
    *,
    raw_markdown: str,
    blocks: Sequence[CleanupBlock],
    operations: Sequence[CleanupOperation],
    config: ReaderCleanupConfig,
    global_candidate_block_ids: set[str],
) -> tuple[str, dict[str, dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    if not operations:
        return raw_markdown, {}, [], []

    protected_ids = _build_protected_block_ids(blocks=blocks, keep_toc=config.keep_toc)
    accepted: dict[str, dict[str, object]] = {}
    accepted_cleanup_operations: list[dict[str, object]] = []
    ignored: list[dict[str, object]] = []
    same_block_operation_history: dict[str, list[str]] = {}
    same_block_applied_history: dict[str, list[str]] = {}
    rewritten_blocks: list[str | None] = [block.text for block in blocks]
    operations_by_index = _canonicalize_cleanup_operation_sequence(blocks=blocks, operations=operations)

    for _, _, _, operation, sequence_decision in operations_by_index:
        block = _block_by_id(blocks, operation.block_id)
        previous_encountered = same_block_operation_history.get(block.block_id, [])
        previous_applied = same_block_applied_history.get(block.block_id, [])
        sequence_ignore_reason = _validate_same_block_operation_sequence(
            previous_encountered=previous_encountered,
            previous_applied=previous_applied,
            operation=operation,
        )
        same_block_operation_history.setdefault(block.block_id, []).append(operation.operation)
        if sequence_ignore_reason is not None:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": sequence_ignore_reason,
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        ignore_reason = _validate_operation(
            blocks=blocks,
            block=block,
            operation=operation,
            protected_ids=protected_ids,
            config=config,
            global_candidate_block_ids=global_candidate_block_ids,
        )
        if ignore_reason is not None:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": ignore_reason,
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue

        applied, after_state, apply_ignore_reason = _apply_single_operation_to_blocks(
            blocks=blocks,
            rewritten_blocks=rewritten_blocks,
            operation=operation,
            block=block,
        )
        if not applied:
            ignored.append(
                {
                    **_serialize_cleanup_operation(operation=operation, block=block),
                    "chunk_index": operation.chunk_index,
                    "ignored_reason": apply_ignore_reason or "operation_not_applicable_exact_match",
                    **({"sequence_decision": sequence_decision} if sequence_decision else {}),
                }
            )
            continue
        if operation.operation == "delete_block":
            accepted[block.block_id] = {
                "reason": operation.reason,
                "confidence": operation.confidence,
                "chunk_index": operation.chunk_index,
            }
        accepted_cleanup_operations.append(
            {
                **_serialize_cleanup_operation(operation=operation, block=block),
                "chunk_index": operation.chunk_index,
                "after_state": after_state,
                **({"sequence_decision": sequence_decision} if sequence_decision else {}),
            }
        )
        same_block_applied_history.setdefault(block.block_id, []).append(operation.operation)

    if not accepted_cleanup_operations:
        return raw_markdown, {}, [], ignored

    if _violates_global_safety(blocks=blocks, accepted_ids=tuple(accepted.keys()), config=config):
        for block_id, metadata in list(accepted.items()):
            block = _block_by_id(blocks, block_id)
            ignored.append(
                {
                    **_serialize_delete_block(block=block, reason=str(metadata["reason"]), confidence=str(metadata["confidence"])),
                    "chunk_index": metadata["chunk_index"],
                    "ignored_reason": "global_safety_limit_exceeded",
                }
            )
            accepted.pop(block_id, None)
        accepted_cleanup_operations = [entry for entry in accepted_cleanup_operations if entry.get("operation") != "delete_block"]

    if not accepted_cleanup_operations:
        return raw_markdown, {}, [], ignored

    kept_blocks = [block_text for block_text in rewritten_blocks if block_text is not None and block_text.strip()]
    cleaned_markdown = "\n\n".join(kept_blocks)
    if not cleaned_markdown.strip():
        return raw_markdown, {}, [], ignored
    return cleaned_markdown, accepted, accepted_cleanup_operations, ignored


def _apply_single_operation_to_blocks(
    *,
    blocks: Sequence[CleanupBlock],
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    current_text = rewritten_blocks[block.index]
    if current_text is None:
        if operation.operation == "normalize_heading_boundary":
            return _apply_heading_boundary_to_joined_previous_block(
                rewritten_blocks=rewritten_blocks,
                operation=operation,
                block=block,
            )
        return False, "", "block_already_removed"
    if operation.operation == "delete_block":
        if operation.reason == "duplicate_fragment":
            duplicate_fragment_ignore_reason = _validate_duplicate_fragment_delete(
                blocks=blocks,
                rewritten_blocks=rewritten_blocks,
                block=block,
                current_text=current_text,
            )
            if duplicate_fragment_ignore_reason is not None:
                return False, "", duplicate_fragment_ignore_reason
        rewritten_blocks[block.index] = None
        return True, "deleted", None
    if operation.operation == "split_block":
        parts = list(operation.split_substrings)
        if len(parts) not in {2, 3}:
            return False, "", "split_substrings_count_invalid"
        pos = 0
        for part in parts:
            idx = block.text.find(part, pos)
            if idx == -1 or block.text[pos:idx].strip():
                return False, "", "split_substrings_not_exact_block_cover"
            pos = idx + len(part)
        if block.text[pos:].strip():
            return False, "", "split_substrings_not_exact_block_cover"
        rewritten_blocks[block.index] = "\n\n".join(parts)
        return True, "split", None
    if operation.operation == "remove_inline_noise":
        noise = operation.noise_substring
        if not noise or noise not in current_text:
            return False, "", "noise_substring_not_found"
        if not _is_safe_inline_noise_substring(noise=noise, current_text=current_text, reason=operation.reason):
            return False, "", "remove_inline_noise_not_exact_noise_pattern"
        if current_text.count(noise) != 1:
            return False, "", "remove_inline_noise_substring_ambiguous"
        replacement = _inline_noise_removed_text(current_text=current_text, noise=noise)
        if not replacement or len(re.sub(r"\s+", "", replacement)) < 20:
            return False, "", "remove_inline_noise_would_drop_semantic_body"
        rewritten_blocks[block.index] = replacement
        return True, "inline_noise_removed", None
    if operation.operation == "join_fragmented_paragraph":
        if not operation.next_id or not operation.next_text_hash:
            return False, "", "join_missing_next_block_reference"
        try:
            next_block = _block_by_id(blocks, operation.next_id)
        except KeyError:
            return False, "", "join_next_block_missing"
        if next_block.index != block.index + 1:
            return False, "", "join_blocks_not_adjacent"
        if operation.next_text_hash != next_block.text_hash:
            return False, "", "join_next_text_hash_mismatch"
        next_text = rewritten_blocks[next_block.index]
        if next_text is None:
            return False, "", "join_next_block_already_removed"
        rewritten_blocks[block.index] = f"{current_text.rstrip()} {next_text.lstrip()}"
        rewritten_blocks[next_block.index] = None
        return True, "joined_with_next", None
    if operation.operation == "normalize_heading_boundary":
        applied_text, ignore_reason = _apply_heading_boundary_to_text(
            current_text=current_text,
            operation=operation,
        )
        if applied_text is None:
            adjacent_applied, adjacent_after_state, _adjacent_ignore_reason = (
                _apply_heading_boundary_across_adjacent_block(
                    rewritten_blocks=rewritten_blocks,
                    operation=operation,
                    block=block,
                )
            )
            if adjacent_applied:
                return True, adjacent_after_state, None
            return False, "", ignore_reason or "heading_boundary_not_applicable"
        rewritten_blocks[block.index] = applied_text
        return True, "heading_boundary_normalized", None
    return False, "", "unsupported_operation"


def _apply_heading_boundary_to_joined_previous_block(
    *,
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    if block.index <= 0:
        return False, "", "block_already_removed"
    previous_text = rewritten_blocks[block.index - 1]
    if previous_text is None:
        return False, "", "block_already_removed"
    evidence = operation.evidence_before.strip()
    if evidence and evidence not in previous_text:
        return False, "", "block_already_removed"
    applied_text, ignore_reason = _apply_heading_boundary_to_text(
        current_text=previous_text,
        operation=operation,
    )
    if applied_text is None:
        return False, "", ignore_reason or "block_already_removed"
    rewritten_blocks[block.index - 1] = applied_text
    return True, "heading_boundary_normalized_after_join", None


def _apply_heading_boundary_across_adjacent_block(
    *,
    rewritten_blocks: list[str | None],
    operation: CleanupOperation,
    block: CleanupBlock,
) -> tuple[bool, str, str | None]:
    if block.index + 1 >= len(rewritten_blocks):
        return False, "", "heading_boundary_adjacent_body_missing"
    current_text = rewritten_blocks[block.index]
    next_text = rewritten_blocks[block.index + 1]
    if current_text is None or next_text is None:
        return False, "", "heading_boundary_adjacent_body_missing"

    heading = operation.heading_substring.strip()
    body = operation.body_substring.strip()
    current_prefix = current_text.strip()
    next_remainder = next_text.lstrip()
    if not heading or not body or not current_prefix or not next_remainder:
        return False, "", "heading_boundary_missing_exact_parts"
    if not heading.startswith(current_prefix):
        return False, "", "heading_boundary_unaccounted_text"
    if body not in next_text:
        return False, "", "heading_boundary_substrings_not_found"

    heading_tail = heading[len(current_prefix) :].lstrip()
    if heading_tail and not next_remainder.startswith(heading_tail):
        return False, "", "heading_boundary_substrings_not_found"
    if not heading_tail and not next_remainder.startswith(body):
        return False, "", "heading_boundary_substrings_not_found"

    combined_text = f"{current_prefix} {next_remainder}"
    applied_text, ignore_reason = _apply_heading_boundary_to_text(
        current_text=combined_text,
        operation=operation,
    )
    if applied_text is None:
        return False, "", ignore_reason or "heading_boundary_not_applicable"
    rewritten_blocks[block.index] = applied_text
    rewritten_blocks[block.index + 1] = None
    return True, "heading_boundary_normalized_across_adjacent_block", None


def _apply_heading_boundary_to_text(
    *,
    current_text: str,
    operation: CleanupOperation,
) -> tuple[str | None, str | None]:
    heading = operation.heading_substring.strip()
    body = operation.body_substring.strip()
    if not heading or not body:
        return None, "heading_boundary_missing_exact_parts"
    if heading not in current_text or body not in current_text:
        return None, "heading_boundary_substrings_not_found"
    if current_text.count(heading) > 1:
        return None, "heading_boundary_heading_ambiguous"
    if current_text.count(body) > 1:
        return None, "heading_boundary_body_ambiguous"
    heading_start = current_text.find(heading)
    body_start = current_text.find(body)
    if heading_start > body_start:
        return None, "heading_boundary_order_invalid"
    body_end = body_start + len(body)
    if heading_start == 0 and body_start > heading_start:
        preserved_body = current_text[body_start:].strip()
        gap = current_text[len(heading) : body_start].strip()
        if gap and len(re.sub(r"\s+", "", gap)) > 12:
            return None, "heading_boundary_unaccounted_text"
        return f"{heading}\n\n{preserved_body}", None
    remainder = f"{current_text[:heading_start]}{current_text[len(heading):body_start]}{current_text[body_end:]}".strip()
    if remainder and len(re.sub(r"\s+", "", remainder)) > 12:
        return None, "heading_boundary_unaccounted_text"
    return f"{heading}\n\n{body}", None


def _is_safe_inline_noise_substring(*, noise: str, current_text: str, reason: str) -> bool:
    normalized_noise = str(noise or "").strip()
    if not normalized_noise:
        return False
    if _SAFE_INLINE_NOISE_PATTERN.fullmatch(normalized_noise) is not None:
        return True
    if _looks_like_numeric_uppercase_running_header_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
    ):
        return True
    if _looks_like_page_furniture_caption_bridge_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if _looks_like_inline_caption_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if _looks_like_duplicate_inline_fragment_noise(
        normalized_noise=normalized_noise,
        current_text=current_text,
        reason=reason,
    ):
        return True
    if reason not in _INLINE_NOISE_REASON_GUIDANCE:
        return False
    return _looks_like_title_case_running_header_noise(normalized_noise=normalized_noise, current_text=current_text)


def _looks_like_duplicate_inline_fragment_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "duplicate_fragment":
        return False
    candidate = normalized_noise.strip()
    if not candidate or "\n" in candidate:
        return False

    candidate_words = _semantic_word_tokens(candidate)
    if len(candidate_words) < 2 or len(candidate_words) > 8:
        return False
    if any(token.isdigit() for token in candidate_words):
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    before_words = _semantic_word_tokens(current_text[:noise_index])
    after_words = _semantic_word_tokens(current_text[noise_index + len(candidate) :])
    candidate_lower = [word.lower() for word in candidate_words]
    return (
        len(before_words) >= len(candidate_words)
        and [word.lower() for word in before_words[-len(candidate_words) :]] == candidate_lower
    ) or (
        len(after_words) >= len(candidate_words)
        and [word.lower() for word in after_words[: len(candidate_words)]] == candidate_lower
    )


def _semantic_word_tokens(value: str) -> list[str]:
    return re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", value or "")


def _looks_like_page_furniture_caption_bridge_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "page_furniture_inline":
        return False
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    noise_end_index = noise_index + len(candidate)
    continuation = current_text[noise_end_index:].lstrip()
    if not continuation or not continuation[0].islower():
        return False

    header_match = re.match(r"^\s*(?:\d{1,4}\s+){1,2}(?:[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,})(?:\s+[A-ZА-ЯЁ][A-ZА-ЯЁ-]{2,}){0,5}\b", candidate)
    if header_match is None:
        return False
    header = header_match.group(0).strip().rstrip(_RUNNING_HEADER_TRAILING_PUNCTUATION)
    if _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN.fullmatch(header) is None:
        return False
    caption_tail = candidate[header_match.end():].strip()
    if len(caption_tail) < 24:
        return False
    caption_tail_lower = caption_tail.lower()
    if not any(marker in caption_tail_lower for marker in ("фото:", "photo:", "photo credit:", "caption:", "иллюстрация:", "рисунок:")):
        return False
    return True


def _looks_like_inline_caption_noise(*, normalized_noise: str, current_text: str, reason: str) -> bool:
    if reason != "page_furniture_inline":
        return False
    candidate = normalized_noise.strip()
    if len(candidate) < 24 or not _has_generic_caption_marker(candidate):
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    before = current_text[:noise_index].rstrip()
    after = current_text[noise_index + len(candidate) :].lstrip()
    if after and after[0].islower():
        return True
    return _has_continuation_signal_before_inline_noise(before)


def _has_continuation_signal_before_inline_noise(text: str) -> bool:
    candidate = str(text or "").rstrip()
    if not candidate:
        return False
    if candidate.endswith(("«", "“", "„", "(", "[", "...", "…", ",", ";", ":", "—", "-")):
        return True
    if candidate.endswith((".", "!", "?", "»", "”", '"')):
        return False
    trailing_token_match = re.search(r"([A-Za-zА-Яа-яЁё]{1,12})\s*$", candidate)
    if trailing_token_match is None:
        return False
    return trailing_token_match.group(1).lower() in {
        "a",
        "an",
        "and",
        "as",
        "at",
        "for",
        "from",
        "if",
        "in",
        "of",
        "or",
        "that",
        "the",
        "to",
        "в",
        "во",
        "и",
        "или",
        "к",
        "ко",
        "на",
        "но",
        "о",
        "об",
        "от",
        "по",
        "с",
        "со",
        "что",
    }


def _looks_like_numeric_uppercase_running_header_noise(*, normalized_noise: str, current_text: str) -> bool:
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    shape_candidate = candidate.rstrip(_RUNNING_HEADER_TRAILING_PUNCTUATION).rstrip()
    if not shape_candidate or _NUMERIC_UPPERCASE_RUNNING_HEADER_PATTERN.fullmatch(shape_candidate) is None:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False
    if noise_index > 0 and current_text[noise_index - 1].isalnum():
        return False
    noise_end_index = noise_index + len(candidate)
    if noise_end_index < len(current_text) and current_text[noise_end_index].isalnum():
        return False

    tokens = [token.strip("()[]{}\"'.,:;!?«»") for token in shape_candidate.split() if token.strip()]
    number_tokens: list[str] = []
    while tokens and tokens[0].isdigit():
        number_tokens.append(tokens.pop(0))
    if not number_tokens or not tokens:
        return False
    if len(number_tokens) > 2:
        return False

    phrase_tokens = [token.lower() for token in tokens if token]
    has_generic_header_token = any(token in _GENERIC_RUNNING_HEADER_TOKENS for token in phrase_tokens)
    has_page_number_shape = any(len(token) >= 3 for token in number_tokens)
    if not has_generic_header_token and not has_page_number_shape:
        return False
    if not has_generic_header_token and len(tokens) > _NUMERIC_UPPERCASE_MAX_TOKENS_WITHOUT_GENERIC_HEADER:
        return False
    return all(token.isupper() for token in tokens)


def _looks_like_title_case_running_header_noise(*, normalized_noise: str, current_text: str) -> bool:
    candidate = normalized_noise.strip()
    if not candidate:
        return False

    noise_index = current_text.find(candidate)
    if noise_index < 0:
        return False

    if noise_index > 0 and current_text[noise_index - 1].isalnum():
        return False
    noise_end_index = noise_index + len(candidate)
    if noise_end_index < len(current_text) and current_text[noise_end_index].isalnum():
        return False

    leading_marker_match = re.match(r"^\d{1,3}\s+", candidate)
    if leading_marker_match is not None:
        candidate = candidate[leading_marker_match.end():].strip()
    if not candidate:
        return False

    header_match = re.fullmatch(r"(.+?)\s+(\d{1,4})", candidate)
    if header_match is None:
        return False
    phrase = header_match.group(1).strip()
    tokens = [token for token in phrase.split() if token]
    if not 2 <= len(tokens) <= 6:
        return False

    capitalized_tokens = 0
    for token in tokens:
        cleaned = token.strip("()[]{}\"'.,:;!?«»")
        if not cleaned:
            return False
        lowered = cleaned.lower()
        if lowered in _HEADER_CONNECTOR_WORDS:
            continue
        if len(cleaned) > 24:
            return False
        if cleaned.isupper() and len(cleaned) >= 2:
            capitalized_tokens += 1
            continue
        if cleaned[0].isupper():
            capitalized_tokens += 1
            continue
        if not cleaned.isalpha():
            return False

    last_cleaned = tokens[-1].strip("()[]{}\"'.,:;!?«»").lower()
    if last_cleaned in _HEADER_CONNECTOR_WORDS:
        return False
    return capitalized_tokens >= 1


def _violates_global_safety(
    *,
    blocks: Sequence[CleanupBlock],
    accepted_ids: Sequence[str],
    config: ReaderCleanupConfig,
) -> bool:
    if not accepted_ids:
        return False

    total_blocks = len(blocks)
    total_chars = sum(block.non_whitespace_char_count for block in blocks)
    deleted_blocks = [_block_by_id(blocks, block_id) for block_id in accepted_ids]
    deleted_char_count = sum(block.non_whitespace_char_count for block in deleted_blocks)
    if total_blocks > 0 and (len(deleted_blocks) / total_blocks) > config.max_delete_block_ratio:
        return True
    if total_chars > 0 and (deleted_char_count / total_chars) > config.max_delete_char_ratio:
        return True

    sorted_indexes = sorted(block.index for block in deleted_blocks)
    longest_run = 1
    current_run = 1
    for previous, current in zip(sorted_indexes, sorted_indexes[1:]):
        if current == previous + 1:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 1
    return longest_run > config.max_consecutive_deleted_blocks


def _build_protected_block_ids(*, blocks: Sequence[CleanupBlock], keep_toc: bool) -> set[str]:
    protected_ids: set[str] = set()
    nonempty_blocks = [block for block in blocks if block.text.strip()]
    if nonempty_blocks:
        # The MVP intentionally stays stricter than the minimum spec wording here:
        # the first and last non-empty blocks are always protected.
        protected_ids.add(nonempty_blocks[0].block_id)
        protected_ids.add(nonempty_blocks[-1].block_id)
    if keep_toc:
        protected_ids.update(block.block_id for block in blocks if block.is_toc_like)
    return protected_ids


def _validate_operation(
    *,
    blocks: Sequence[CleanupBlock],
    block: CleanupBlock,
    operation: CleanupOperation,
    protected_ids: set[str],
    config: ReaderCleanupConfig,
    global_candidate_block_ids: set[str],
) -> str | None:
    if operation.text_hash != block.text_hash:
        return "text_hash_mismatch"
    if operation.confidence == "low":
        return "low_confidence"
    if operation.operation != "delete_block":
        if block.kind == "footnote_body":
            return "footnote_body_protected"
        if block.is_toc_like:
            return "toc_protected"
        if block.block_id in protected_ids:
            return "protected_block"
        return None
    if operation.reason == "page_number" and block.kind != "page_number":
        return "reason_kind_incompatible"
    if operation.reason == "blank_page_marker" and block.kind != "blank_page_marker":
        return "reason_kind_incompatible"
    if operation.reason == "orphan_footnote_marker" and block.kind != "orphan_footnote_marker":
        return "reason_kind_incompatible"
    if operation.reason == "extraction_artifact" and block.kind != "extraction_artifact":
        return "reason_kind_incompatible"
    if block.kind == "footnote_body":
        return "footnote_body_protected"
    if operation.reason == "repeated_running_header":
        if block.block_id not in global_candidate_block_ids:
            return "missing_repetition_evidence"
        if block.kind not in {"paragraph", "page_number", "blank_page_marker", "orphan_footnote_marker", "extraction_artifact"}:
            return "reason_kind_incompatible"
    if operation.reason == "page_furniture_heading":
        if block.kind != "heading":
            return "reason_kind_incompatible"
        if operation.confidence != "high":
            return "heading_protected"
    if block.is_heading and not (
        operation.reason in {"repeated_running_header", "page_furniture_heading"}
        and operation.confidence == "high"
    ):
        return "heading_protected"
    if block.block_id in protected_ids:
        return "protected_block"
    if operation.reason == "page_number" and not _has_safe_standalone_number_delete_context(
        blocks=blocks,
        block=block,
        global_candidate_block_ids=global_candidate_block_ids,
    ):
        return "standalone_number_delete_requires_page_context"
    if block.char_count > config.max_deleted_block_chars:
        return "block_char_limit_exceeded"
    return None


def _has_safe_standalone_number_delete_context(
    *,
    blocks: Sequence[CleanupBlock],
    block: CleanupBlock,
    global_candidate_block_ids: set[str],
) -> bool:
    text = block.normalized_text.strip()
    if not re.fullmatch(r"\d{1,4}", text):
        return True

    nearby_blocks = [
        candidate
        for candidate in blocks
        if candidate.block_id != block.block_id and abs(candidate.index - block.index) <= 1
    ]
    return any(
        candidate.block_id in global_candidate_block_ids
        or candidate.kind in {"blank_page_marker", "extraction_artifact"}
        for candidate in nearby_blocks
    )


def _validate_same_block_operation_sequence(
    *,
    previous_encountered: Sequence[str],
    previous_applied: Sequence[str],
    operation: CleanupOperation,
) -> str | None:
    if not previous_encountered:
        return None
    if list(previous_encountered) != list(previous_applied):
        return "prior_same_block_operation_not_applied"
    candidate_sequence = tuple(previous_applied) + (operation.operation,)
    if "delete_block" in candidate_sequence and len(candidate_sequence) > 1:
        return "duplicate_operation_incompatible"

    seen_split = False
    seen_split_count = 0
    seen_normalize_count = 0
    seen_join_count = 0
    previous_phase = 0
    previous_operation = ""
    for operation_name in candidate_sequence:
        phase = _same_block_operation_phase(operation_name=operation_name, seen_split=seen_split)
        if phase < previous_phase:
            return "duplicate_operation_incompatible"
        if phase == previous_phase and operation_name != "remove_inline_noise":
            return "duplicate_operation_incompatible"
        if operation_name == "split_block":
            seen_split_count += 1
            if seen_split_count > 1:
                return "duplicate_operation_incompatible"
            seen_split = True
        elif operation_name == "normalize_heading_boundary":
            seen_normalize_count += 1
            if seen_normalize_count > 1:
                return "duplicate_operation_incompatible"
        elif operation_name == "join_fragmented_paragraph":
            seen_join_count += 1
            if seen_join_count > 1:
                return "duplicate_operation_incompatible"
        if previous_operation == "join_fragmented_paragraph":
            return "duplicate_operation_incompatible"
        previous_phase = phase
        previous_operation = operation_name
    return None


def _same_block_operation_phase(*, operation_name: str, seen_split: bool) -> int:
    if operation_name == "remove_inline_noise":
        return 3 if seen_split else 1
    if operation_name == "split_block":
        return 2
    if operation_name == "normalize_heading_boundary":
        return 4
    if operation_name == "join_fragmented_paragraph":
        return 5
    if operation_name == "delete_block":
        return 6
    return 99


def _canonicalize_cleanup_operation_sequence(
    *,
    blocks: Sequence[CleanupBlock],
    operations: Sequence[CleanupOperation],
) -> list[tuple[int, int, int, CleanupOperation, str | None]]:
    block_index_by_id = {block.block_id: block.index for block in blocks}
    split_index_by_block_id: dict[str, int] = {}
    inline_noise_operation_block_ids = {
        operation.block_id for operation in operations if operation.operation == "remove_inline_noise"
    }
    original_indexes_by_block_id: dict[str, list[int]] = {}
    mixed_delete_block_ids: set[str] = set()
    for operation_index, operation in enumerate(operations):
        original_indexes_by_block_id.setdefault(operation.block_id, []).append(operation_index)
        if operation.operation == "split_block" and operation.block_id not in split_index_by_block_id:
            split_index_by_block_id[operation.block_id] = operation_index

    sequenced_entries: list[tuple[int, int, int, CleanupOperation, str | None]] = []
    reordered_block_ids: set[str] = set()
    per_block_entries: dict[str, list[tuple[int, int, CleanupOperation]]] = {}
    for operation_index, operation in enumerate(operations):
        phase = _same_block_original_phase(
            operation=operation,
            operation_index=operation_index,
            split_index_by_block_id=split_index_by_block_id,
        )
        per_block_entries.setdefault(operation.block_id, []).append((phase, operation_index, operation))

    for block_id, entries in per_block_entries.items():
        operation_names = {operation.operation for _, _, operation in entries}
        if "delete_block" in operation_names and len(operation_names) > 1:
            mixed_delete_block_ids.add(block_id)
            continue
        original_order = [operation_index for _, operation_index, _ in entries]
        canonical_order = [
            operation_index
            for _, operation_index, _ in sorted(entries, key=lambda item: (item[0], item[1]))
        ]
        if canonical_order != original_order:
            reordered_block_ids.add(block_id)

    for operation_index, operation in enumerate(operations):
        if operation.block_id in mixed_delete_block_ids:
            phase = 0 if operation.operation == "delete_block" else 1
        else:
            phase = _same_block_original_phase(
                operation=operation,
                operation_index=operation_index,
                split_index_by_block_id=split_index_by_block_id,
            )
        block_index = block_index_by_id[operation.block_id]
        if operation.operation == "join_fragmented_paragraph" and operation.next_id in inline_noise_operation_block_ids:
            block_index = max(block_index, block_index_by_id.get(operation.next_id, block_index))
            phase = max(phase, _same_block_operation_phase(operation_name="join_fragmented_paragraph", seen_split=False))
        sequence_decision = "operation_sequence_reordered" if operation.block_id in reordered_block_ids else None
        sequenced_entries.append((block_index, phase, operation_index, operation, sequence_decision))

    return sorted(sequenced_entries, key=lambda item: (item[0], item[1], item[2]))


def _same_block_original_phase(
    *,
    operation: CleanupOperation,
    operation_index: int,
    split_index_by_block_id: Mapping[str, int],
) -> int:
    split_index = split_index_by_block_id.get(operation.block_id)
    if operation.operation == "remove_inline_noise" and split_index is not None and operation_index > split_index:
        return 3
    return _same_block_operation_phase(operation_name=operation.operation, seen_split=False)


def _validate_duplicate_fragment_delete(
    *,
    blocks: Sequence[CleanupBlock],
    rewritten_blocks: Sequence[str | None],
    block: CleanupBlock,
    current_text: str,
) -> str | None:
    candidate = _normalize_block_text(current_text)
    candidate_non_whitespace = len(re.sub(r"\s+", "", candidate))
    if candidate_non_whitespace < _DUPLICATE_FRAGMENT_MIN_NON_WHITESPACE_CHARS:
        return "duplicate_fragment_too_short"

    nearby_matches = 0
    for other_block in blocks:
        if other_block.block_id == block.block_id:
            continue
        if abs(other_block.index - block.index) > _DUPLICATE_FRAGMENT_MAX_NEARBY_BLOCK_DISTANCE:
            continue
        other_text = rewritten_blocks[other_block.index]
        if other_text is None:
            continue
        other_normalized = _normalize_block_text(other_text)
        if not other_normalized:
            continue
        if candidate == other_normalized or candidate in other_normalized or other_normalized.endswith(candidate):
            nearby_matches += 1
            if nearby_matches > 1:
                return "duplicate_fragment_ambiguous_neighbor_match"

    if nearby_matches != 1:
        return "duplicate_fragment_unique_continuation"
    return None


def _detect_block_kind(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return "empty"
    first_line = stripped.splitlines()[0].strip()
    if first_line.startswith("#"):
        return "heading"
    if _PAGE_NUMBER_PATTERN.fullmatch(stripped):
        return "page_number"
    if _BLANK_PAGE_PATTERN.fullmatch(stripped):
        return "blank_page_marker"
    if _ORPHAN_FOOTNOTE_PATTERN.fullmatch(stripped):
        return "orphan_footnote_marker"
    if _FOOTNOTE_BODY_PATTERN.match(stripped):
        return "footnote_body"
    if _EXTRACTION_ARTIFACT_PATTERN.fullmatch(stripped):
        return "extraction_artifact"
    if _TOC_LIKE_PATTERN.search(stripped):
        return "toc_like"
    if first_line.startswith(">"):
        return "blockquote"
    if re.match(r"^(?:[-*]|\d+\.)\s+", first_line):
        return "list"
    return "paragraph"


def _heuristic_reason(block: CleanupBlock) -> str:
    stripped = block.normalized_text
    if _PAGE_NUMBER_PATTERN.fullmatch(stripped):
        return "page_number"
    if _BLANK_PAGE_PATTERN.fullmatch(stripped):
        return "blank_page_marker"
    if _ORPHAN_FOOTNOTE_PATTERN.fullmatch(stripped):
        return "orphan_footnote_marker"
    if _EXTRACTION_ARTIFACT_PATTERN.fullmatch(stripped):
        return "extraction_artifact"
    if block.is_heading:
        return "page_furniture_heading"
    return "repeated_running_header"


def _normalize_block_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")]
    return "\n".join(lines).strip()


def _require_nonempty_str(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"reader_cleanup_missing_field:{key}")
    return value.strip()


def _serialize_delete_block(*, block: CleanupBlock, reason: str, confidence: str) -> dict[str, object]:
    preview = block.text.replace("\n", " ").strip()
    if len(preview) > 160:
        preview = preview[:157].rstrip() + "..."
    return {
        "id": block.block_id,
        "text_hash": block.text_hash,
        "reason": reason,
        "confidence": confidence,
        "raw_text_preview": preview,
        "char_count": block.char_count,
        "kind": block.kind,
    }


def _serialize_cleanup_operation(*, operation: CleanupOperation, block: CleanupBlock) -> dict[str, object]:
    payload = _serialize_delete_block(block=block, reason=operation.reason, confidence=operation.confidence)
    payload.update(
        {
            "operation": operation.operation,
            "evidence_before": operation.evidence_before,
            "expected_after_preview": operation.expected_after_preview,
            "safety_note": operation.safety_note,
        }
    )
    if operation.split_substrings:
        payload["split_substrings"] = list(operation.split_substrings)
    if operation.noise_substring:
        payload["noise_substring"] = operation.noise_substring
    if operation.next_id:
        payload["next_id"] = operation.next_id
    if operation.next_text_hash:
        payload["next_text_hash"] = operation.next_text_hash
    if operation.heading_substring:
        payload["heading_substring"] = operation.heading_substring
    if operation.body_substring:
        payload["body_substring"] = operation.body_substring
    return payload


def _block_by_id(blocks: Sequence[CleanupBlock], block_id: str) -> CleanupBlock:
    for block in blocks:
        if block.block_id == block_id:
            return block
    raise KeyError(block_id)


def _coerce_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _coerce_int(value: object, *, default: int, minimum: int) -> int:
    try:
        return max(int(cast(Any, value)), minimum)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in {"1", "true", "yes", "on"}:
            return True
        if stripped in {"0", "false", "no", "off"}:
            return False
        if not stripped:
            return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _coerce_float(value: object, *, default: float) -> float:
    try:
        return float(cast(Any, value))
    except (TypeError, ValueError):
        return default
