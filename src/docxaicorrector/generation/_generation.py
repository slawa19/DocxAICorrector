import logging
import re
import tempfile
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence, Sized
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import lxml.etree as etree
import pypandoc
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from docxaicorrector.core.logger import log_event
from docxaicorrector.core.model_accounting import (
    PARAGRAPH_DISPOSITION_STATUSES,
    STAGE_TEXT_GENERATION,
    get_run_model_accounting_ledger,
    record_degradation_ladder,
    record_marker_chunk_merge_retry,
    record_model_call_usage,
    record_model_output_discarded,
    record_paragraph_disposition,
    record_retry_attempt,
    record_text_removal,
)
from docxaicorrector.image.shared import call_responses_create_with_retry, drop_rejected_optional_param, is_retryable_error
from docxaicorrector.generation.marker_attempt_capture import capture_rejected_marker_attempt
from docxaicorrector.generation.openai_response_utils import collect_response_text_traversal, read_response_field
from collections.abc import Callable, Mapping

from docxaicorrector.core.model_accounting import record_text_api_path
from docxaicorrector.generation.model_response import (
    API_PATH_ANTHROPIC_MESSAGES,
    API_PATH_CHAT_COMPLETIONS,
    API_PATH_RESPONSES,
    CollapsedOutput,
    EmptyResponse,
    IncompleteResponse,
    ModelResponse,
    NonCompletedResponse,
    anthropic_stop_is_complete,
    chat_completion_finish_is_complete,
)
# The generation layer raises the pipeline's existing cooperative-stop signal rather than
# inventing a second one (spec 061 FR-022). ``pipeline.contracts`` imports nothing from the
# pipeline itself, so this edge cannot form an import cycle.
from docxaicorrector.pipeline.contracts import LatePhaseStopped
# Spec 065 FR-006: the answer-form rule lives with the other answer-form rules. Like
# ``pipeline.contracts`` above, ``pipeline.output_validation`` reaches nothing in the
# generation layer, so the edge cannot close a cycle.
from docxaicorrector.pipeline.output_validation import structural_meta_comment

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument
    from openai import OpenAI


# The generator's one text-DELETING point, named for ``record_text_removal``'s ``site``.
TEXT_REMOVAL_SITE_CONTEXT_LEAKAGE_BOUNDARY_TRIM = "context_leakage_boundary_trim"

_PARAGRAPH_MARKER_PATTERN = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]")
_IMAGE_ONLY_TARGET_PATTERN = re.compile(r"^(?:\s*\[\[DOCX_IMAGE_img_\d+\]\]\s*)+$")
_WORD_TOKEN_PATTERN = re.compile(r"\w+(?:[-']\w+)*", re.UNICODE)
_INLINE_HTML_SUP_PATTERN = re.compile(r"<sup>(.*?)</sup>", re.IGNORECASE | re.DOTALL)
_INLINE_HTML_SUB_PATTERN = re.compile(r"<sub>(.*?)</sub>", re.IGNORECASE | re.DOTALL)
_INLINE_HTML_BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
_INLINE_HTML_UNDERLINE_PATTERN = re.compile(
    r"(?P<prefix>\\*!?)<u>(?P<content>.*?)</u>", re.IGNORECASE | re.DOTALL
)
_PANDOC_SPAN_SPECIAL_PATTERN = re.compile(r"[\\\[\]]")
_NARRATION_INTERNAL_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_[A-Za-z0-9_]+\]\]")
_NARRATION_MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
_NARRATION_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s*(.*)$")
_NARRATION_TAGGED_HEADING_PATTERN = re.compile(r"^(\s*(?:\[[^\]\n]+\]\s*)+)#{1,6}\s*(.*)$")
_NARRATION_BLOCKQUOTE_PATTERN = re.compile(r"^\s{0,3}>\s?(.*)$")
# A list marker is not speech. Markdown's own markers were already dropped; the printed
# bullet GLYPH was not, and the audiobook prompt's rule against lists does not bind the
# model — measured on the 2026-08-04 Money & Sustainability narration artifact, 116 of them
# reached the text a TTS engine would read aloud, 113 at the start of their own line and 3
# behind an ElevenLabs tag. The glyph set is the repository's existing bullet lexicon
# (``output_validation._BULLET_GLYPH_PATTERN``, which produced that same count of 116), not
# a new one: of its four glyphs only ``•`` occurs in the artifact, and the other three are
# carried because they are the same form, not because a book showed them. This is not a
# guess about structure — a bullet glyph is simply not speech, and the item's own text is
# kept.
# A separator after the glyph is required, so a glyph welded inside a token ("4●5") is left
# alone, exactly as ``_WELDED_BULLET_GLYPH_PATTERN`` leaves it alone in the quality gate.
_NARRATION_LIST_MARKER = r"(?:[-*+●•◦‣]\s+|\d+\.\s+)"
_NARRATION_LIST_PATTERN = re.compile(r"^\s{0,3}" + _NARRATION_LIST_MARKER + r"(.*)$")
# The same marker behind an ElevenLabs tag prefix, which the narration keeps: "[serious] • …"
# is the tagged twin of "• …" and has to lose the glyph the same way, or the tagged lines
# would be the only ones a listener hears a bullet in.
_NARRATION_TAGGED_LIST_PATTERN = re.compile(
    r"^(\s*(?:\[[^\]\n]+\]\s*)+)" + _NARRATION_LIST_MARKER + r"(.*)$"
)
_NARRATION_STRONG_PATTERN = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_NARRATION_EMPHASIS_PATTERN = re.compile(r"(\*|_)(?=\S)(.+?)(?<=\S)\1")
_NARRATION_RAW_URL_PATTERN = re.compile(r"(?:https?://\S+|www\.\S+)", re.IGNORECASE)
_NARRATION_INTERNAL_WHITESPACE_PATTERN = re.compile(r"[\t ]+")
# The structural kind a narration paragraph's markdown declared, kept only long enough for
# the sentence-continuation join to read it. See ``_narration_paragraphs``.
_NARRATION_KIND_BODY = "body"
_NARRATION_KIND_HEADING = "heading"
_NARRATION_KIND_LIST = "list"
_NARRATION_KIND_QUOTE = "quote"
# Where a sentence is allowed to have ended. Punctuation classes, not words: a paragraph
# closing on one of these was finished, and the paragraph after it starts something new.
_NARRATION_SENTENCE_TERMINALS = ".!?…:;"
_NARRATION_CLOSING_MARKS = "»”’\"')]}"
# A returned marker chunk that keeps this little of its own source paragraph is a stub,
# not an edit or a translation. Calibrated on the 1761 recorded pairs of the 2026-08-03
# literary-edit run: the 7 "(Пусто)" stubs sit at 0.008–0.135, the next real edit above
# them at 0.207, and every one of the 609 genuine edits stays far above the floor.
_COLLAPSED_MARKER_CHUNK_RATIO = 0.15
# Below this the source paragraph is itself a fragment ("г.", ".htm.") where a length
# ratio carries no signal.
_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS = 40
# A neighbour — on EITHER side — counts as the one that swallowed the collapsed paragraph
# when it grew by at least this share of what the collapsed paragraph lost.
_ABSORBING_NEIGHBOUR_RATIO = 0.5
# Spec 065 FR-005: the mirror of the collapse above. A SHORT source paragraph whose answer
# came back more than ``_SHORT_SOURCE_ABSORPTION_RATIO`` times its length took in text that
# belongs to a neighbour -- typically a note the importer tore in two, which the model
# restores in full under the first piece while the next piece (often in the NEXT block, seen
# only as context) is delivered again. Only translate jobs ask for it (the caller decides;
# an audiobook answer is told to expand abbreviations and has no such bound). A source
# that is a markdown heading is exempt: a title is a label with no sentence to run on, and
# its translation legitimately grows ("Scope" -> "Сфера применения", an acronym spelled out).
#
# A second, lower bound for the shape that defect actually has: a NUMBERED entry ("22. G.
# Morgenson, 'Challenging …',") torn before its end -- no sentence end, or a sentence that
# stops on a single-letter initial ("in L. H.") -- of at least
# ``_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS``. Its continuation is the neighbour by
# construction, so an answer past ``_TORN_ENTRY_ABSORPTION_RATIO`` holds it.
#
# Measured on the four books of the third translate run (2026-11-07, 6 981 answered pairs,
# every flag read by eye): the 3x bound flags 11 answers outside headings, all absorptions
# (the 3 above it among headings are genuine translations); the torn-entry bound adds 10, all
# absorptions duplicated by the next paragraph, out of 314 torn numbered entries. The highest
# genuine translation among those 314 sits at 1.89x (a quoted title kept with its translation
# added), the lowest absorption at 2.14x. Spec 065's Changelog has the lists.
#
# Two floors under BOTH bounds (Codex acceptance review of spec 065, P0). The ratios were
# calibrated on space-separated prose translated EN -> RU, and the product also accepts
# ``source_language = auto``: a correct short translation ("你好。" -> "Здравствуйте.", 3 -> 13
# characters) would read as an absorption, be refused on every retry and by the ladder, and
# ship its source. So a source is measured only when it carries enough to measure:
#
# * at least ``_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS`` visible characters -- the floor the
#   collapse above already uses, for the same reason ("a fragment where a length ratio
#   carries no signal");
# * at least ``_SHORT_SOURCE_ABSORPTION_MIN_SOURCE_TOKENS`` whitespace-separated tokens. In
#   space-separated text 40 characters are six or seven words, so the two floors agree there;
#   a script written without word spaces (Chinese, Japanese) yields one or two tokens per
#   sentence and is skipped whole, which is right, since a character ratio across such
#   scripts means nothing. Tokens are counted, no language or script is detected.
#
# Cost on the third run: 3 of the 21 hits fall under the floors -- VoE p1621 "2014), p. 1860."
# (15 characters, 3 tokens) and two index lines of RM, p1845 "52– 53" and p1847 "Charity, 150"
# (6 and 12 characters, 2 tokens each). The lowest surviving hit has 49 characters and 9 tokens.
_SHORT_SOURCE_ABSORPTION_MAX_SOURCE_CHARS = 200
_SHORT_SOURCE_ABSORPTION_MIN_SOURCE_TOKENS = 6
_SHORT_SOURCE_ABSORPTION_RATIO = 3.0
_TORN_ENTRY_ABSORPTION_RATIO = 2.0
_MARKDOWN_HEADING_LINE_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s")
_NUMBERED_ENTRY_PATTERN = re.compile(r"^\s{0,3}(?:[-*+]\s+)?\d{1,4}[.)]\s")
_ENTRY_CLOSERS = r"\"”’»)\]*_"
_SENTENCE_END_PATTERN = re.compile(rf"[.!?…][{_ENTRY_CLOSERS}]*\s*$")
_TRAILING_INITIAL_PATTERN = re.compile(rf"(?<![^\W\d_])[^\W\d_]\.[{_ENTRY_CLOSERS}]*\s*$")
# Spec 068 FR-001: a NUMBER in a paragraph's answer that its own source paragraph does not carry,
# but a neighbouring paragraph of the block or the context around the block does, is text taken
# from elsewhere -- the model completed a torn line from the paragraph after it (an index entry
# whose continuation it saw in [CONTEXT AFTER]), and that continuation is delivered again under
# its own marker. A number is read as a run of digits after these normalisations, applied to
# both sides alike: superscript digits are folded to plain digits and stand apart from the word
# they touch (a footnote reference); a range torn by the extractor ("113-1 14") is rejoined; a
# thousands group joined to its number ("1,500", "4 000"); an abbreviated range ("2007-8",
# "223-24") expanded ("2007-2008", "223-224"). In the ANSWER only a free-standing number counts
# -- digits glued to a letter are part of a name ("B2B", "CO2"); every source side keeps all
# its digits, so a footnote reference the source glued to a word still belongs to it. A number
# of the answer that is a substring of a number of its source is not foreign either: "1,5" for
# "1,500" (a reformatted magnitude), "2009" and "19" for "200919" (a footnote reference the
# source glued to a year). A number a neighbour of the same block carries counts only when that
# neighbour's own answer carries it too -- delivered twice; a number the model MOVED from a
# torn neighbour into the sentence it belongs to ("in January," + "1999. During ...") is
# delivered once.
_NUMBER_LEAK_SUPERSCRIPT_RUN_PATTERN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_NUMBER_LEAK_TORN_RANGE_PATTERN = re.compile(r"([‐‑‒–—―-]\s?\d{1,3}) (\d{1,3})(?!\d)")
_NUMBER_LEAK_THOUSANDS_PATTERN = re.compile(r"(?<=\d)[,\u00a0\u202f\u2009 ](?=\d{3}(?!\d))")
_NUMBER_LEAK_RANGE_PATTERN = re.compile(r"(\d+)\s?[‐‑‒–—―-]\s?(\d+)")
_NUMBER_LEAK_DIGITS_PATTERN = re.compile(r"\d+")
# Bounded by a non-alphanumeric on both sides: a lookbehind that forbade only a LETTER let the
# match start INSIDE a digit run glued to a letter ("ISO9001" -> "001"; Codex review 2026-11-08).
_NUMBER_LEAK_FREE_STANDING_DIGITS_PATTERN = re.compile(r"(?<![^\W_])\d+(?![^\W_])")
_INCOMPLETE_RESPONSE_RETRY_MIN_OUTPUT_TOKENS = 1024
_INCOMPLETE_RESPONSE_RECOVERY_MIN_OUTPUT_TOKENS = 1536
# The hard upper bound on ``max_output_tokens`` this generator will ever ask for. Named
# rather than repeated as a literal in three places because the degradation ladder DERIVES
# its division threshold from it: a block whose answer does not fit under this number is
# not a block that needs another retry, it is a block that needs to be smaller, and
# ``_boost_request_output_budget`` cannot make it fit no matter how many times it doubles.
_MODEL_OUTPUT_TOKEN_CEILING = 16384
_CONTEXT_LEAKAGE_RETRY_WARNING = (
    "IMPORTANT: Your previous answer included text from the surrounding context. "
    "Use ONLY the text that belongs to [TARGET BLOCK]."
)


class ContextLeakageError(RuntimeError):
    pass


# --- spec 056 E: what happened to ONE paragraph, said out loud ----------------------
# A block used to be all-or-nothing, so one paragraph the model could not answer for
# discarded every good translation next to it. These four statuses are the whole
# vocabulary; anything a paragraph can end up as is one of them, and the counts are
# published per run (``model_accounting.paragraph_disposition_counts``).
PARAGRAPH_STATUS_ACCEPTED = "accepted"
"""The model's own text for this paragraph is what ships."""
PARAGRAPH_STATUS_OMITTED = "omitted"
"""The model returned nothing for it: the source stands in the DOCX, the narration skips it."""
PARAGRAPH_STATUS_SOURCE_RESTORED = "source_restored"
"""The model's text was discarded (a visible merge) and this paragraph's source re-instated."""
PARAGRAPH_STATUS_RETRY_REQUIRED = "retry_required"
"""Unresolved: there is retry budget left, so the block is asked again. Never ships."""
# A status assigned here but absent from the report's vocabulary would be counted into a
# bucket nobody documented, so the two lists are held together at import time rather than
# by a comment. ``tests/test_generation.py`` asserts the same equality from the outside.
assert sorted(
    (
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_OMITTED,
        PARAGRAPH_STATUS_SOURCE_RESTORED,
        PARAGRAPH_STATUS_RETRY_REQUIRED,
    )
) == sorted(PARAGRAPH_DISPOSITION_STATUSES)


@dataclass(frozen=True)
class ParagraphDisposition:
    """One paragraph of a marker-preserved block, and what became of it."""

    paragraph_id: str
    text: str
    status: str


class MarkerPreservedBlockText(str):
    """The block's markdown, which also remembers what happened to each paragraph.

    A ``str`` subclass rather than a new return type on purpose. ``generate_markdown_block``
    is reached through the ``MarkdownGenerator`` protocol and its result flows through
    assembly, narration, classification and the UI as plain text; changing the type would
    touch every one of those and every test double that returns a string.

    **The subclass is a transport, never a place to compute.** Any ``str`` operation on it
    — ``.strip()``, a slice, an ``f``-string — returns a plain ``str`` and the record is
    gone, and the loss is invisible because ``build_processed_paragraph_registry_entries``
    re-splits on ``\\n\\n`` and finds the same paragraph COUNT. That is how a review found
    English being read aloud with every check green (``_trim_boundary_context_leakage``
    built its result with ``.strip()`` and a slice). So the block's text is derived from the
    dispositions and never the other way round: ``_marker_preserved_block_text`` is the only
    constructor used inside the generator, and every terminal return in marker mode goes
    through ``_deliver_marker_preserved_block``, which RAISES if the record did not survive.
    """

    paragraph_dispositions: tuple[ParagraphDisposition, ...]

    def __new__(
        cls,
        text: str,
        dispositions: Sequence[ParagraphDisposition] = (),
    ) -> "MarkerPreservedBlockText":
        instance = super().__new__(cls, text)
        instance.paragraph_dispositions = tuple(dispositions)
        return instance

    def __reduce__(self) -> tuple[object, ...]:
        # Without this, ``copy.deepcopy`` and ``pickle`` reconstruct through
        # ``cls.__new__(cls, text)`` and lose the record — silently, and only in whichever
        # code path happens to copy a processed block.
        return (self.__class__, (str(self), self.paragraph_dispositions))


class MarkerParagraphRecordLost(RuntimeError):
    """The per-paragraph record was expected on this value and is not there.

    Not a ``MarkerValidationError``: the model did nothing wrong, the code did. It is
    therefore NOT retryable — resending the same request cannot put the record back — and
    it must not be confused with a rejected answer in the retry accounting. Raised so that
    a transport degradation is a stopped block with a named cause instead of source-language
    text delivered quietly under a green classification.
    """

    def __init__(self, stage: str) -> None:
        super().__init__(f"marker_paragraph_record_lost:{stage}")
        self.stage = stage


def marker_paragraph_dispositions(value: object) -> tuple[ParagraphDisposition, ...] | None:
    """The per-paragraph record carried by a processed block, or ``None`` if it has none."""

    dispositions = getattr(value, "paragraph_dispositions", None)
    if not isinstance(dispositions, tuple):
        return None
    if not all(isinstance(item, ParagraphDisposition) for item in dispositions):
        return None
    return dispositions


def _marker_preserved_block_text(
    dispositions: Sequence[ParagraphDisposition],
) -> MarkerPreservedBlockText:
    """The ONLY way the generator builds a marker-preserved block.

    The text is derived from the record, so the two cannot disagree and no code path can
    produce the text without the record.
    """

    return MarkerPreservedBlockText(
        "\n\n".join(disposition.text for disposition in dispositions),
        dispositions,
    )


def _deliver_marker_preserved_block(value: str, *, marker_mode: bool, stage: str) -> str:
    """Every terminal return of a marker-mode ANSWER passes through here.

    Two jobs, both of which have to happen exactly once per block and exactly at the end:

    * the record must still be attached — a plain ``str`` arriving here means some string
      operation upstream dropped it, and that is raised, not tolerated;
    * the per-paragraph counters are recorded HERE rather than where the statuses are
      resolved, because a status resolved on an attempt that is then rejected (context
      leakage, an outer retry) never ships. Counting it made the run report count attempts:
      a two-paragraph block that succeeded once after two rejected attempts reported
      ``accepted: 6``.
    """

    if not marker_mode:
        return value
    dispositions = marker_paragraph_dispositions(value)
    if dispositions is None:
        raise MarkerParagraphRecordLost(stage)
    _record_paragraph_dispositions(dispositions)
    return value


class MarkerValidationError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        *,
        raw_markdown: str,
        expected_paragraph_ids: Sequence[str],
        found_paragraph_ids: Sequence[str] | None = None,
        leading_text: str | None = None,
        collapsed_paragraph_ids: Sequence[str] | None = None,
        absorbing_paragraph_ids: Sequence[str] | None = None,
    ) -> None:
        super().__init__(f"paragraph_marker_validation_failed:{error_code}")
        self.error_code = error_code
        # The FULL answer, kept alongside the preview. The preview feeds prompts and log
        # payloads, which must stay small; the full text feeds the attempt-capture artifact
        # (spec 056 D'), whose only purpose is that a rejected answer can be replayed
        # offline instead of being re-bought. One block's answer, one exception.
        self.raw_markdown = raw_markdown
        self.raw_markdown_preview = raw_markdown[:1000]
        self.expected_paragraph_ids = tuple(expected_paragraph_ids)
        self.found_paragraph_ids = tuple(found_paragraph_ids or ())
        self.leading_text = leading_text or ""
        self.leading_text_preview = (leading_text or "")[:400]
        # ``merged_marker_chunk`` (spec 061 FR-001): WHICH paragraph collapsed and which
        # neighbour visibly took its text; ``number_leak_marker_chunk`` (spec 068 FR-001): the
        # paragraphs whose answers carry a number taken from elsewhere, as absorbers. Empty for
        # every other code.
        self.collapsed_paragraph_ids = tuple(collapsed_paragraph_ids or ())
        self.absorbing_paragraph_ids = tuple(absorbing_paragraph_ids or ())


# A paragraph the model visibly merged into its neighbour, raised whenever something is
# still left to ask (spec 061 FR-001/002). A ``MarkerValidationError`` like every other
# marker-contract code, so the attempt loop retries it, spec 056 D' captures its answer and
# the degradation ladder takes it as a ``marker_contract`` trigger without a line of their
# own. The pair is repaired to ``source_restored`` (FR-003) only where nothing is left: the
# last attempt and the recovery call of a block with NO ladder, and — when the ladder rescued
# nothing — by ``_merged_pair_repair_fallback`` from the recovery call's own answer.
MERGED_MARKER_CHUNK_ERROR_CODE = "merged_marker_chunk"
# Spec 068 FR-001: a paragraph's answer carries a number taken from a neighbour or from the
# context around the block (``_find_number_leaks``). A ``MarkerValidationError`` too, so the
# attempt loop retries it and spec 056 D' captures its answer; raised only while attempts
# remain. When nothing is left the answer stands -- it is translated, and shipping the source
# would trade a duplicated number for a paragraph in the wrong language.
NUMBER_LEAK_MARKER_CHUNK_ERROR_CODE = "number_leak_marker_chunk"


@lru_cache(maxsize=1)
def ensure_pandoc_available() -> None:
    try:
        pypandoc.get_pandoc_version()
    except OSError as exc:
        raise RuntimeError(
            "Pandoc не найден в текущем WSL runtime. Для штатного workflow установите его внутри WSL, "
            "например через: sudo apt-get install -y pandoc"
        ) from exc


def normalize_model_output(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :].strip()
        else:
            cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def strip_markdown_for_narration(text: str) -> str:
    """The narration text alone. See ``strip_markdown_for_narration_with_stats``."""

    return strip_markdown_for_narration_with_stats(text)[0]


def strip_markdown_for_narration_with_stats(text: str) -> tuple[str, int]:
    """The narration text, and how many paragraph boundaries were closed inside a sentence.

    The count is returned rather than logged here because this function is pure and is
    called on both narration entry points; the caller records it on the run state so the
    saved-artifact log line can state it (Constitution V, and zero is a statement).
    """

    paragraphs = _narration_paragraphs(text)
    merged, joined_count = _join_narration_sentence_continuations(paragraphs)
    return "\n\n".join("\n".join(lines) for lines, _ in merged).strip(), joined_count


def _narration_paragraphs(text: str) -> list[tuple[list[str], str]]:
    """The narration's paragraphs, each with the STRUCTURAL KIND its markdown declared.

    The kind is carried out of this loop on purpose. It is the only place in the assembly
    where a heading is still a heading and a list item is still a list item — one line
    later the ``#`` and the bullet are gone and a heading is indistinguishable from a short
    sentence. The join rule needs that distinction and must not re-derive it from shape.
    """

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _NARRATION_INTERNAL_PLACEHOLDER_PATTERN.sub("", normalized)
    normalized = _NARRATION_MARKDOWN_LINK_PATTERN.sub(r"\1", normalized)

    paragraphs: list[tuple[list[str], str]] = []
    open_index: int | None = None
    for raw_line in normalized.split("\n"):
        line_source = raw_line
        kind = _NARRATION_KIND_BODY

        tagged_heading_match = _NARRATION_TAGGED_HEADING_PATTERN.match(line_source)
        if tagged_heading_match is not None:
            kind = _NARRATION_KIND_HEADING
            tag_prefix = _NARRATION_INTERNAL_WHITESPACE_PATTERN.sub(" ", tagged_heading_match.group(1)).strip()
            heading_text = tagged_heading_match.group(2).strip()
            line_source = f"{tag_prefix} {heading_text}".strip()
        else:
            heading_match = _NARRATION_HEADING_PATTERN.match(line_source)
            if heading_match is not None:
                kind = _NARRATION_KIND_HEADING
                line_source = heading_match.group(1)
            else:
                blockquote_match = _NARRATION_BLOCKQUOTE_PATTERN.match(line_source)
                if blockquote_match is not None:
                    kind = _NARRATION_KIND_QUOTE
                    line_source = blockquote_match.group(1)
                else:
                    list_match = _NARRATION_LIST_PATTERN.match(line_source)
                    if list_match is not None:
                        kind = _NARRATION_KIND_LIST
                        line_source = list_match.group(1)
                    else:
                        tagged_list_match = _NARRATION_TAGGED_LIST_PATTERN.match(line_source)
                        if tagged_list_match is not None:
                            kind = _NARRATION_KIND_LIST
                            tag_prefix = _NARRATION_INTERNAL_WHITESPACE_PATTERN.sub(
                                " ", tagged_list_match.group(1)
                            ).strip()
                            item_text = tagged_list_match.group(2).strip()
                            line_source = f"{tag_prefix} {item_text}".strip()

        line = line_source.replace("`", "")
        line = _strip_narration_inline_emphasis(line)
        line = _NARRATION_RAW_URL_PATTERN.sub("", line)
        line = _NARRATION_INTERNAL_WHITESPACE_PATTERN.sub(" ", line).strip()
        if not line:
            open_index = None
            continue
        if open_index is None:
            paragraphs.append(([line], kind))
            open_index = len(paragraphs) - 1
        else:
            lines, open_kind = paragraphs[open_index]
            lines.append(line)
            # A paragraph that holds a heading, a list item or a quote among its lines is
            # not body text, whatever its first line looked like.
            if kind != _NARRATION_KIND_BODY and open_kind == _NARRATION_KIND_BODY:
                paragraphs[open_index] = (lines, kind)
        if kind == _NARRATION_KIND_HEADING:
            # A heading has always closed its paragraph here — the blank line after it is
            # what this used to append, and a paragraph break is now that same blank line.
            open_index = None
    return paragraphs


def _narration_paragraph_continues(
    previous: tuple[list[str], str], following: tuple[list[str], str]
) -> bool:
    """Is ``following`` the rest of a sentence that ``previous`` was cut off in the middle of?

    **What this is for.** 81 of the 83 such boundaries measured on the four-book corpus of
    2026-08-06 arrive from IMPORT: the source paragraph itself ends without any punctuation
    because a PDF line wrap became a paragraph break. Both halves are translated and nothing
    is missing — only the separator is wrong, and a TTS engine reads a paragraph break as a
    pause in the middle of a sentence. Joining them changes a ``\\n\\n`` into a space and
    nothing else.

    **The test is the FORM of the assembly's own output**, which is the same class of rule as
    the bullet-glyph strip above and is what Constitution VII allows: no word list, no
    length threshold, no per-book string.

    * Both paragraphs must be BODY. The kind comes from the markdown the model returned
      (``_narration_paragraphs``), not from the shape of the text, so a heading is never
      welded to the prose under it and a list item never to its neighbour — a list of
      items and a heading legitimately end without punctuation.
    * The first must end on a character that is not sentence-terminal (``.!?…:;``), not a
      closing quote or bracket, and NOT A DIGIT. The digit is the load-bearing one and it
      was measured, not guessed: allow a digit ending and the only two boundaries that
      appear on the whole corpus are rows of Rethinking Money's index (``Страх, 4`` +
      ``в Юте, 201; …``), which end in a page number and are legitimately unpunctuated.
    * The second must begin with a LOWERCASE letter. This is what separates "the rest of
      this sentence" from "whatever happens to come next", and it is what keeps an epigraph
      attribution or an index row from being glued to the paragraph after it: those are
      followed by something that starts a new sentence, a name or a tag. An audio tag
      (``[serious] …``) begins with ``[`` and therefore also stops the join, which is
      right — a new tag is a new speech unit.
    """

    previous_lines, previous_kind = previous
    following_lines, following_kind = following
    if previous_kind != _NARRATION_KIND_BODY or following_kind != _NARRATION_KIND_BODY:
        return False
    tail = previous_lines[-1].rstrip()
    head = following_lines[0].lstrip()
    if not tail or not head:
        return False
    last = tail[-1]
    if last.isdigit() or last in _NARRATION_SENTENCE_TERMINALS or last in _NARRATION_CLOSING_MARKS:
        return False
    first = head[0]
    return first.isalpha() and first.islower()


def _join_narration_sentence_continuations(
    paragraphs: Sequence[tuple[list[str], str]],
) -> tuple[list[tuple[list[str], str]], int]:
    merged: list[tuple[list[str], str]] = []
    joined_count = 0
    for lines, kind in paragraphs:
        if merged and _narration_paragraph_continues(merged[-1], (lines, kind)):
            previous_lines, previous_kind = merged[-1]
            previous_lines[-1] = f"{previous_lines[-1].rstrip()} {lines[0].lstrip()}"
            previous_lines.extend(lines[1:])
            merged[-1] = (previous_lines, previous_kind)
            joined_count += 1
            continue
        merged.append((list(lines), kind))
    return merged, joined_count


def _strip_narration_inline_emphasis(text: str) -> str:
    stripped = text
    while True:
        updated = _NARRATION_STRONG_PATTERN.sub(r"\2", stripped)
        updated = _NARRATION_EMPHASIS_PATTERN.sub(r"\2", updated)
        if updated == stripped:
            return updated
        stripped = updated


def _normalize_context_text(text: str | None) -> str:
    if text is None:
        return "[no context]"
    cleaned = text.strip()
    return cleaned or "[no context]"


_CONTEXT_IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\[\[DOCX_IMAGE_img_\d+\]\]")


def _strip_image_placeholders(text: str) -> str:
    """Remove DOCX image placeholder tokens from context strings.

    Image placeholders must not appear in context_before / context_after because
    the model consistently returns empty responses when it encounters them in the
    surrounding context (as opposed to the target block, where they must be
    preserved for later image reinsertion).
    """
    return _CONTEXT_IMAGE_PLACEHOLDER_PATTERN.sub("", text).strip()


def _strip_prompt_internal_tokens(text: str) -> str:
    without_images = _CONTEXT_IMAGE_PLACEHOLDER_PATTERN.sub("", text)
    without_markers = _PARAGRAPH_MARKER_PATTERN.sub("", without_images)
    return without_markers.strip()


def _should_passthrough_target(target_text: str) -> bool:
    stripped_target = target_text.strip()
    if not stripped_target:
        return True
    if _IMAGE_ONLY_TARGET_PATTERN.fullmatch(stripped_target):
        return True
    return not _strip_prompt_internal_tokens(target_text)


def _validate_prompt_inputs(target_text: str, context_before: str, context_after: str) -> list[str]:
    warnings: list[str] = []
    if not target_text.strip():
        warnings.append("empty_target_text")
    elif _IMAGE_ONLY_TARGET_PATTERN.fullmatch(target_text.strip()):
        warnings.append("image_only_target_text")
    elif not _strip_prompt_internal_tokens(target_text):
        warnings.append("placeholder_only_target_text")

    if not context_before.strip():
        warnings.append("empty_context_before")
    if not context_after.strip():
        warnings.append("empty_context_after")
    return warnings


def _build_standard_user_prompt(*, target_text: str, context_before: str, context_after: str) -> str:
    return (
        "Below is a target document block and surrounding context.\n"
        "Use the surrounding context only to understand meaning, terminology, and continuity.\n"
        "Process only the target block according to the system instructions and return only its final text.\n\n"
        f"[CONTEXT BEFORE]\n{context_before}\n\n"
        f"[TARGET BLOCK]\n{target_text}\n\n"
        f"[CONTEXT AFTER]\n{context_after}"
    )


def _build_marker_preserving_user_prompt(*, target_text: str, context_before: str, context_after: str) -> str:
    return (
        "Below is a target document block with required paragraph markers of the form [[DOCX_PARA_...]].\n"
        "Preserve every marker exactly, in the same quantity and order.\n"
        "Do not delete, duplicate, rename, or reorder markers.\n"
        "Do not merge paragraphs across markers and do not split one marker into multiple paragraphs.\n"
        "Every marker must be followed by the processed text of ITS OWN paragraph. If you believe a "
        "paragraph continues the previous one, still return that paragraph's own text under its own "
        "marker, unchanged. Never answer with a placeholder, a stub, a dash, or a note about what you "
        "did (for example \"(Пусто)\", \"(Empty)\", \"(see above)\").\n"
        "Process only the text after each marker according to the system instructions and return the whole block together with the markers.\n"
        "Use the surrounding context only for meaning and terminology.\n\n"
        f"[CONTEXT BEFORE]\n{context_before}\n\n"
        f"[TARGET BLOCK WITH MARKERS]\n{target_text}\n\n"
        f"[CONTEXT AFTER]\n{context_after}"
    )


def _build_empty_response_recovery_user_prompt(*, target_text: str) -> str:
    return (
        "The previous attempt returned an empty answer.\n"
        "Repeat the processing, ignore all external context, and work only with the target block below.\n"
        "Preserve the full meaning, structure, and facts of the block.\n"
        "Return only the final processed block text with no explanation, no Markdown fence, and no empty answer.\n\n"
        f"[TARGET BLOCK ONLY]\n{target_text}"
    )
def _build_marker_recovery_user_prompt(
    *,
    target_text: str,
    expected_paragraph_ids: Sequence[str] | None = None,
    last_error: Exception | None = None,
) -> str:
    required_marker_lines = ""
    if expected_paragraph_ids:
        rendered_markers = "\n".join(f"[[DOCX_PARA_{paragraph_id}]]" for paragraph_id in expected_paragraph_ids)
        required_marker_lines = f"Required marker sequence:\n{rendered_markers}\n\n"

    previous_output_lines = ""
    if isinstance(last_error, MarkerValidationError):
        previous_output_lines = (
            f"Previous marker validation error: {last_error.error_code}.\n"
            f"Expected marker ids: {', '.join(last_error.expected_paragraph_ids) or '[none]'}.\n"
            f"Found marker ids: {', '.join(last_error.found_paragraph_ids) or '[none]'}.\n"
        )
        if last_error.leading_text_preview:
            previous_output_lines += f"Unexpected prefix preview:\n{last_error.leading_text_preview}\n\n"
        if last_error.raw_markdown_preview:
            previous_output_lines += f"Previous invalid output preview:\n{last_error.raw_markdown_preview}\n\n"

    return (
        "The previous attempt violated the paragraph marker contract.\n"
        "Repeat the processing strictly according to the rules below.\n"
        "Preserve every marker [[DOCX_PARA_...]] exactly as it appears and in the same order.\n"
        "Do not delete markers, add new ones, or reorder them.\n"
        "Each marker must correspond to exactly one paragraph of text after it.\n"
        "A marker whose paragraph you would rather merge into its neighbour must still carry that "
        "paragraph's own text, unchanged — never a placeholder, a stub, or a note.\n"
        "The response must begin with the first required marker and contain no explanation.\n\n"
        f"{required_marker_lines}"
        f"{previous_output_lines}"
        f"[TARGET BLOCK WITH MARKERS ONLY]\n{target_text}"
    )


def split_marker_preserved_paragraph_dispositions(
    markdown: str,
    expected_paragraph_ids: Sequence[str],
) -> list[ParagraphDisposition]:
    """Split a marker-preserved answer into ONE typed record per paragraph.

    Spec 056 E. The predecessor returned a list of strings and raised on the first bad
    paragraph, which made a block all-or-nothing: on the 2026-08-04 audiobook run block 274
    held ten paragraphs and every one of them was discarded — replaced by the block's own
    English source in a Russian narration — because paragraph ``p1336``, whose entire text
    is ``14``, came back empty. Nine good translations were thrown away with it.

    What stays block-fatal, unchanged, because these are the checks that detect REAL loss:

    - ``markers_missing`` — no marker at all;
    - ``marker_order_or_identity`` — a marker missing, duplicated or reordered. On the same
      run this caught the model deleting a paragraph TOGETHER with its marker, losing the
      heading (a bold label ending in a spaced colon) outright;
    - ``unexpected_prefix`` — text before the first marker, which has no owner.

    What changes: an EMPTY chunk under an exact marker sequence is no longer a block
    failure. It becomes ``retry_required`` — the caller decides whether there is budget
    left to ask again (``resolve_marker_paragraph_dispositions``). Emptiness is what the
    audiobook prompt ORDERS for a paragraph that is pure reference apparatus, while the
    user prompt forbids a stub in its place, so the contract left the model no legal move
    and the block paid for it.

    ``paragraph_split_detected`` — a blank line INSIDE one chunk — is relaxed only where
    the relaxation is provable, and that is the single-marker block; see
    ``_collapse_single_marker_paragraph_break``.
    """

    matches = list(_PARAGRAPH_MARKER_PATTERN.finditer(markdown))
    if not matches:
        raise MarkerValidationError(
            "markers_missing",
            raw_markdown=markdown,
            expected_paragraph_ids=expected_paragraph_ids,
        )

    found_ids = [match.group(1) for match in matches]
    expected_ids = list(expected_paragraph_ids)
    if found_ids != expected_ids:
        raise MarkerValidationError(
            "marker_order_or_identity",
            raw_markdown=markdown,
            expected_paragraph_ids=expected_paragraph_ids,
            found_paragraph_ids=found_ids,
        )

    leading_text = markdown[: matches[0].start()].strip()
    if leading_text:
        raise MarkerValidationError(
            "unexpected_prefix",
            raw_markdown=markdown,
            expected_paragraph_ids=expected_paragraph_ids,
            found_paragraph_ids=found_ids,
            leading_text=leading_text,
        )

    dispositions: list[ParagraphDisposition] = []
    for index, match in enumerate(matches):
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        chunk = markdown[match.end() : content_end].strip()
        if "\n\n" in chunk:
            if len(matches) != 1 or _has_structural_output_line(chunk):
                raise MarkerValidationError(
                    "paragraph_split_detected",
                    raw_markdown=markdown,
                    expected_paragraph_ids=expected_paragraph_ids,
                    found_paragraph_ids=found_ids,
                )
            chunk = _collapse_single_marker_paragraph_break(chunk, paragraph_id=found_ids[index])
        dispositions.append(
            ParagraphDisposition(
                paragraph_id=found_ids[index],
                text=chunk,
                status=(PARAGRAPH_STATUS_ACCEPTED if chunk else PARAGRAPH_STATUS_RETRY_REQUIRED),
            )
        )
    return dispositions


_STRUCTURAL_OUTPUT_LINE_PATTERN = re.compile(
    r"^\s{0,3}(?:#{1,6}(?:\s|$)|[-*+]\s|\d{1,9}[.)]\s|```|~~~)"
)


def _has_structural_output_line(chunk: str) -> bool:
    """Does the MODEL'S OWN answer for this paragraph contain a structural line?

    A markdown heading, a list item or a code fence. Joining the pieces of a broken chunk
    with a space is only safe for prose: ``## Заголовок`` welded to the sentence after it
    stops being a heading, and ``- пункт`` welded to the text before it stops being a list
    item — the collapse would then repair a split by destroying a structural role, which is
    Constitution VII rule 7 exactly (content survived, its role did not).

    This inspects the shape of the model's OUTPUT, not the shape of the source document, so
    it is not the structure-guessing VII forbids: nothing is inferred about what the
    paragraph "really" is, only whether the answer is written in a form that a space would
    destroy. And the fallback is today's behaviour — refusing to collapse leaves the break
    ``paragraph_split_detected``, exactly as before spec 056 — so the guard is bounded above
    by "no worse than the previous release".

    Measured on the 504 recorded model answers of the 2026-08-04 audiobook run and the
    2026-08-03 literary-edit run: every one of the single-marker breaks the collapse rescues
    is prose, and none of them contains such a line, so the guard costs nothing that was
    being gained.
    """

    return any(
        _STRUCTURAL_OUTPUT_LINE_PATTERN.match(line) is not None
        for line in chunk.splitlines()
    )


def _collapse_single_marker_paragraph_break(chunk: str, *, paragraph_id: str) -> str:
    """Join a paragraph the model broke in two — ONLY where ONE paragraph was asked for.

    Two callers, and both satisfy that condition by construction: a block whose marker
    sequence holds exactly one id, and one unit of the degradation ladder, whose request
    carried a single paragraph and no markers at all. The reasoning below is written for the
    first and applies unchanged to the second.

    With a single marker there is no neighbour to steal from and no neighbour to steal for:
    ``unexpected_prefix`` already forbids a fragment before the marker, and every character
    after it belongs to this paragraph because the block contains no other. The collapse is
    provable, not plausible.

    With two or more markers it is NOT, and no rule was found that makes it so. The model
    can place text BEFORE a marker:

    .. code-block:: text

        [[DOCX_PARA_p1]]
        Перевод первого абзаца.

        ## Безопасность
        [[DOCX_PARA_p2]]
        [short pause]

    Marker identity and order are exact, both chunks are non-empty, and ``p2``'s source is
    under ``_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS`` so the collapse-restore is skipped.
    Collapsing ``p1``'s chunk would hand ``p2``'s heading to ``p1`` with every remaining
    check passing — trading a DETECTED failure for a silent corruption. Attributing the
    trailing fragment would mean comparing it against a source in another language, or
    keying on how it looks; both are the per-document heuristics Constitution VII forbids.
    Restricting the collapse to the last chunk does not help either: the mirror case, where
    an earlier paragraph's text was pushed down past its own marker, has exactly the same
    shape. So for two or more markers the break stays block-fatal, and that is a recorded
    accepted outcome rather than a rule that was not found yet.

    Measured on the 2026-08-04 run: of the three ``paragraph_split_detected`` blocks, 118
    is a single-marker block (one 4 095-character quotation the importer welded together)
    and is rescued here; 164 and 185 hold two and three markers and stay fatal.

    The pieces are joined with a space rather than kept apart, because the contract is one
    marker — one paragraph, and the registry maps one paragraph id to one paragraph.
    """

    parts = [part.strip() for part in re.split(r"\n\s*\n", chunk) if part.strip()]
    collapsed = " ".join(parts)
    log_event(
        logging.INFO,
        "marker_chunk_paragraph_break_collapsed",
        "Модель разбила единственный абзац блока на несколько; части склеены обратно в один абзац.",
        paragraph_id=paragraph_id,
        part_count=len(parts),
        collapsed_chars=len(collapsed),
    )
    return collapsed


def resolve_marker_paragraph_dispositions(
    dispositions: Sequence[ParagraphDisposition],
    *,
    source_paragraph_chunks: Sequence[str] | None = None,
    allow_unresolved_paragraphs: bool,
    raw_markdown: str | None = None,
    allow_merge_repair: bool | None = None,
    detect_short_source_absorption: bool = False,
    context_texts: Sequence[str] = (),
) -> list[ParagraphDisposition]:
    """Turn ``retry_required`` paragraphs into a final status, or ask for another attempt.

    While there is retry budget left an unresolved paragraph still raises
    ``empty_marker_chunk`` — the same error code, the same retry accounting and the same
    resend as before. That is deliberate: of the seven bare-number paragraphs recorded on
    the 2026-08-04 run, two WERE rescued by a resend, and giving that up to save a call
    would trade real text for money.

    On the last attempt the block is no longer thrown away. Each paragraph the model
    emptied becomes ``omitted``: its own SOURCE text stands in the document, so nothing is
    lost from the DOCX and the paragraph-per-marker mapping the restorer depends on still
    holds, and it is excluded from the narration, where source-language text is exactly
    what spec 054 says must not reach a listener. Every other paragraph keeps its
    translation.

    The collapse-restore runs FIRST, on the raw texts, so an emptied paragraph whose text
    was visibly absorbed by a neighbour is still repaired as a pair (``source_restored``)
    instead of being re-instated on its own and shipped twice.

    A MERGE follows the same budget rule as an omission (spec 061 FR-001, FR-003). Until
    2026-11-06 it did not: the pair was reverted to its source on the FIRST attempt, so
    ``empty_marker_chunk`` never fired and the retry loop never saw a problem — the block
    shipped two paragraphs in the source language under ``valid``, once per book on four of
    five recorded audiobook runs. Now, while budget remains, a visible merge raises
    ``merged_marker_chunk`` and the block is asked again; ``source_restored`` is reached
    only when nothing is left to ask. The detector itself is unchanged — only WHEN its
    verdict ships.

    "Nothing left" is not the same moment for the two failures, so the merge has a flag of
    its own. An omission has no better remedy than the last attempt; a merge does — the
    degradation ladder asks each paragraph alone, without markers, where merging is
    impossible by construction. ``allow_merge_repair`` therefore stays ``False`` through the
    last attempt and the recovery call whenever the ladder is available, and defaults to
    ``allow_unresolved_paragraphs`` for every caller that has no ladder to hand the block to.

    Spec 065 FR-006: a paragraph answered with a parenthetical meta-comment about the book's
    structure (``output_validation.structural_meta_comment``) is an answer that says nothing
    about the paragraph, so it is treated exactly as an EMPTY one -- asked again while budget
    remains, ``omitted`` with its source on the last attempt -- and the rejection is logged
    with the paragraph id and the comment.

    Spec 065 FR-005: ``detect_short_source_absorption`` (translate jobs) adds the overgrown
    short paragraph to the merges ``_find_marker_chunk_merges`` reports, so it takes the same
    road a visible merge takes: a retry while anything is left to ask, its source on repair.

    Spec 068 FR-001: under the same flag (translate jobs) a paragraph whose answer carries a
    number taken from a neighbour or from ``context_texts`` (the block's [CONTEXT BEFORE] and
    [CONTEXT AFTER]; ``_find_number_leaks`` holds the form) raises
    ``number_leak_marker_chunk`` while attempts remain (``allow_unresolved_paragraphs`` is
    False). On the last attempt the answer stands, with a WARNING naming the paragraphs and the
    numbers: the text is translated, and its source would be worse than the duplicate.
    """

    if allow_merge_repair is None:
        allow_merge_repair = allow_unresolved_paragraphs

    texts = [disposition.text for disposition in dispositions]
    statuses = list(disposition.status for disposition in dispositions)
    paragraph_ids = [disposition.paragraph_id for disposition in dispositions]

    if source_paragraph_chunks is not None and len(source_paragraph_chunks) == len(texts):
        for index, text in enumerate(texts):
            if not text:
                continue
            comment = structural_meta_comment(text, source_paragraph_chunks[index])
            if comment is None:
                continue
            log_event(
                logging.WARNING,
                "marker_chunk_meta_comment_rejected",
                "Модель вернула вместо абзаца скобочный комментарий о структуре книги; ответ отклонён как пустой.",
                paragraph_id=paragraph_ids[index],
                comment_text=comment,
                answer_chars=len(text),
            )
            texts[index] = ""

    def _answer_as_received() -> str:
        # The model's ACTUAL answer when the caller has it (spec 056 D' captures the
        # exception's ``raw_markdown`` verbatim, and a reconstruction would not replay).
        if raw_markdown is not None:
            return raw_markdown
        return "\n\n".join(
            f"[[DOCX_PARA_{disposition.paragraph_id}]]\n{disposition.text}"
            for disposition in dispositions
        )

    if source_paragraph_chunks is not None:
        merges = _find_marker_chunk_merges(
            texts,
            source_paragraph_chunks,
            expected_paragraph_ids=paragraph_ids,
            detect_short_source_absorption=detect_short_source_absorption,
        )
        if merges and not allow_merge_repair:
            collapsed_ids = [
                paragraph_ids[merge.collapsed_index] for merge in merges if merge.collapsed_index is not None
            ]
            absorbing_ids = list(
                dict.fromkeys(
                    paragraph_ids[index] for merge in merges for index in merge.absorbing_indexes
                )
            )
            # Counted HERE, not as a discard: nothing reaches the document from this answer.
            # The block is always asked again after this raise — a retry while attempts
            # remain, then the recovery call, then the ladder — because
            # ``generate_markdown_block`` withholds the repair only while one of those is
            # still ahead.
            record_marker_chunk_merge_retry()
            log_event(
                logging.WARNING,
                "marker_chunk_merge_retry_requested",
                "Модель слила абзац с соседним; исходник не подставляется, блок будет запрошен снова.",
                collapsed_paragraph_ids=collapsed_ids,
                absorbing_paragraph_ids=absorbing_ids,
                # Spec 065 FR-005: absorbers with no collapsed partner in this block -- a
                # short paragraph that grew past the ratio.
                overgrown_paragraph_ids=_overgrown_paragraph_ids(merges, paragraph_ids),
                paragraph_count=len(dispositions),
            )
            raise MarkerValidationError(
                MERGED_MARKER_CHUNK_ERROR_CODE,
                raw_markdown=_answer_as_received(),
                expected_paragraph_ids=paragraph_ids,
                found_paragraph_ids=paragraph_ids,
                collapsed_paragraph_ids=collapsed_ids,
                absorbing_paragraph_ids=absorbing_ids,
            )
        restored_texts = _restore_marker_chunk_merges(
            list(texts), source_paragraph_chunks, merges, expected_paragraph_ids=paragraph_ids
        )
        for index, (before, after) in enumerate(zip(texts, restored_texts)):
            if before != after:
                statuses[index] = PARAGRAPH_STATUS_SOURCE_RESTORED
        texts = restored_texts

    unresolved_indexes = [
        index
        for index, text in enumerate(texts)
        if not text and statuses[index] != PARAGRAPH_STATUS_SOURCE_RESTORED
    ]
    if unresolved_indexes and not allow_unresolved_paragraphs:
        raise MarkerValidationError(
            "empty_marker_chunk",
            raw_markdown=_answer_as_received(),
            expected_paragraph_ids=paragraph_ids,
            found_paragraph_ids=paragraph_ids,
        )

    for index in unresolved_indexes:
        statuses[index] = PARAGRAPH_STATUS_OMITTED
        if source_paragraph_chunks is not None and index < len(source_paragraph_chunks):
            texts[index] = source_paragraph_chunks[index]

    # The detector reads what the block DELIVERS: a neighbour whose answer was empty or thrown
    # away ships its source, so its numbers are delivered -- a leak of them is a duplicate, not
    # a move. Read on the raw answers, an empty neighbour made every number of its source look
    # moved, and the duplicate left without a word (Codex review 2026-11-08). Hence this runs
    # after the omitted paragraphs took their source; a source checked against itself has no
    # foreign number, so the restored paragraphs are never flagged themselves.
    if detect_short_source_absorption and source_paragraph_chunks is not None:
        leaks = _find_number_leaks(texts, source_paragraph_chunks, context_texts=context_texts)
        if leaks:
            leak_paragraph_ids = [paragraph_ids[index] for index in leaks]
            leaked_numbers = {paragraph_ids[index]: list(numbers) for index, numbers in leaks.items()}
            if not allow_unresolved_paragraphs:
                log_event(
                    logging.WARNING,
                    "marker_chunk_number_leak_retry_requested",
                    "В ответе абзаца есть число соседнего абзаца или контекста; блок будет запрошен снова.",
                    leak_paragraph_ids=leak_paragraph_ids,
                    leaked_numbers=leaked_numbers,
                    paragraph_count=len(dispositions),
                )
                raise MarkerValidationError(
                    NUMBER_LEAK_MARKER_CHUNK_ERROR_CODE,
                    raw_markdown=_answer_as_received(),
                    expected_paragraph_ids=paragraph_ids,
                    found_paragraph_ids=paragraph_ids,
                    absorbing_paragraph_ids=leak_paragraph_ids,
                )
            log_event(
                logging.WARNING,
                "marker_chunk_number_leak_kept",
                "Повторы исчерпаны: в ответе абзаца осталось число соседнего абзаца или контекста; перевод оставлен как есть.",
                leak_paragraph_ids=leak_paragraph_ids,
                leaked_numbers=leaked_numbers,
                paragraph_count=len(dispositions),
            )

    resolved = [
        ParagraphDisposition(paragraph_id=disposition.paragraph_id, text=text, status=status)
        for disposition, text, status in zip(dispositions, texts, statuses)
    ]
    if unresolved_indexes:
        # The run report must be able to say WHICH paragraphs the model produced nothing
        # for, and HOW MUCH text stops being spoken because of it. The owner's metric for
        # spec 054 is a share of CHARACTERS, so a count of paragraphs alone cannot be
        # compared against it: a WARNING reading "1 paragraph" hid 3 000 characters of
        # prose on the measurement that prompted this.
        log_event(
            logging.WARNING,
            "marker_paragraph_omitted",
            "Модель не вернула текст для отдельных абзацев блока; в документе остаётся исходный текст, в озвучку они не попадают.",
            omitted_paragraph_ids=[resolved[index].paragraph_id for index in unresolved_indexes],
            omitted_paragraph_count=len(unresolved_indexes),
            omitted_source_chars=sum(len(resolved[index].text) for index in unresolved_indexes),
            paragraph_count=len(resolved),
        )
    return resolved


def _record_paragraph_dispositions(dispositions: Sequence[ParagraphDisposition]) -> None:
    counts: dict[str, int] = {}
    for disposition in dispositions:
        counts[disposition.status] = counts.get(disposition.status, 0) + 1
    for status, count in counts.items():
        record_paragraph_disposition(status=status, count=count)


def _split_marker_preserved_markdown(markdown: str, expected_paragraph_ids: Sequence[str]) -> list[str]:
    """Strict split, used on the SOURCE text where every chunk is a real paragraph.

    The source is built by the pipeline, not by the model, so an empty or broken chunk here
    is a pipeline defect and not a contract the model could not satisfy. It keeps raising.
    """

    dispositions = split_marker_preserved_paragraph_dispositions(markdown, expected_paragraph_ids)
    for disposition in dispositions:
        if not disposition.text:
            raise MarkerValidationError(
                "empty_marker_chunk",
                raw_markdown=markdown,
                expected_paragraph_ids=expected_paragraph_ids,
                found_paragraph_ids=[item.paragraph_id for item in dispositions],
            )
    return [disposition.text for disposition in dispositions]


def _visible_marker_chunk_length(chunk: str) -> int:
    return len(_strip_prompt_internal_tokens(chunk))


@dataclass(frozen=True)
class _MarkerChunkMerge:
    """One VISIBLE merge: the paragraph that collapsed and the neighbour(s) holding its text.

    ``collapsed_index`` is ``None`` for a short paragraph that outgrew its source (spec 065
    FR-005): the absorber is known, the paragraph it absorbed may be in another block.
    """

    collapsed_index: int | None
    absorbing_indexes: tuple[int, ...]


def restore_collapsed_marker_paragraphs(
    paragraph_chunks: list[str],
    source_paragraph_chunks: Sequence[str],
    *,
    expected_paragraph_ids: Sequence[str] | None = None,
) -> list[str]:
    """Re-instate the SOURCE text of a paragraph the model MERGED into a neighbour.

    Contract: one marker — one paragraph, and a paragraph's content stays in its own
    paragraph. When the model merges a paragraph into its neighbour it is forbidden to
    delete the emptied marker, so it fills it with an invented stub ("(Пусто)") that ships
    to the reader as literal garbage (7 occurrences on the 2026-08-03 literary-edit run).

    A shrunken chunk on its own is NOT evidence of a merge, and restoring on shrinkage
    alone silently reverts work the model was ASKED to do: a legitimately tightened
    sentence, or — in audiobook mode, where the prompt orders reference and bibliography
    paragraphs to be dropped — exactly the paragraphs that must not reach the narration.
    So a restore requires the merge to be VISIBLE: a neighbour that grew by at least half
    of what this paragraph holds, i.e. an identified place the text went to. No identified
    absorber, no restore.

    The absorber is searched on BOTH sides. The model merges forward as readily as back
    (``[stub for A, "text A text B"]``), and looking only at ``index - 1`` restored A while
    leaving A's text inside the next chunk — shipping A twice.

    A collapse is length-only and therefore operation-agnostic (``edit`` AND ``translate``):
    no translation turns an 861-character paragraph into 7 characters.

    Replayed over the 1761 recorded pairs of that run: all 7 stubs have an absorbing
    neighbour and are still repaired; the single collapse WITHOUT one (a 655-character
    quote) turned out not to be a merge at all — the model had shifted a whole endnote
    region, and that quote was already shipping five markers earlier, so re-instating it
    delivered the quote twice.

    Since spec 061 FR-001 detection and repair are two steps: ``resolve_marker_paragraph_dispositions``
    detects first (``_find_marker_chunk_merges``) and repairs (``_restore_marker_chunk_merges``)
    only when no retry budget is left, because a repair ships source-language text. This
    function performs both at once and is kept for callers with no budget to consult.
    """

    merges = _find_marker_chunk_merges(
        paragraph_chunks, source_paragraph_chunks, expected_paragraph_ids=expected_paragraph_ids
    )
    return _restore_marker_chunk_merges(
        paragraph_chunks,
        source_paragraph_chunks,
        merges,
        expected_paragraph_ids=expected_paragraph_ids,
    )


def _find_marker_chunk_merges(
    paragraph_chunks: Sequence[str],
    source_paragraph_chunks: Sequence[str],
    *,
    expected_paragraph_ids: Sequence[str] | None = None,
    detect_short_source_absorption: bool = False,
) -> list[_MarkerChunkMerge]:
    """The merges ``restore_collapsed_marker_paragraphs`` would repair — found, not repaired.

    Pure detection, apart from the INFO line for a shrunken paragraph nobody absorbed (that
    answer stands either way, so there is nothing to defer). No counter is touched here:
    whether the merge becomes a discard or a retry is the caller's decision.

    With ``detect_short_source_absorption`` (spec 065 FR-005) a short paragraph whose answer
    outgrew its source past ``_SHORT_SOURCE_ABSORPTION_RATIO`` is reported too, as an
    absorber with no collapsed partner (``collapsed_index=None``): the paragraph it absorbed
    may sit in the next block, which this block only ever saw as context, so nothing here
    collapses. ``_is_short_source_absorption`` holds the form.
    """

    if not source_paragraph_chunks or len(source_paragraph_chunks) != len(paragraph_chunks):
        return []

    merges = _find_collapsed_marker_chunk_merges(
        paragraph_chunks, source_paragraph_chunks, expected_paragraph_ids=expected_paragraph_ids
    )
    if not detect_short_source_absorption:
        return merges
    already_absorbing = {index for merge in merges for index in merge.absorbing_indexes}
    for index, (answer, source) in enumerate(zip(paragraph_chunks, source_paragraph_chunks)):
        if index in already_absorbing or not _is_short_source_absorption(source, answer):
            continue
        merges.append(_MarkerChunkMerge(collapsed_index=None, absorbing_indexes=(index,)))
    return merges


def _is_short_source_absorption(source_chunk: str, answer_chunk: str) -> bool:
    """Spec 065 FR-005: did a SHORT paragraph's answer take in text that belongs elsewhere?

    The source paragraph must be shorter than ``_SHORT_SOURCE_ABSORPTION_MAX_SOURCE_CHARS``
    visible characters and not a markdown heading, and it must be long enough to measure: at
    least ``_COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS`` visible characters AND at least
    ``_SHORT_SOURCE_ABSORPTION_MIN_SOURCE_TOKENS`` whitespace-separated tokens (a script
    without word spaces has too few and is never measured). Then the answer is an absorption when it
    is more than ``_SHORT_SOURCE_ABSORPTION_RATIO`` times the source's length -- or more than
    ``_TORN_ENTRY_ABSORPTION_RATIO`` times when the source is a torn numbered entry
    (``_is_torn_numbered_entry``). Length, markdown form and punctuation only -- no word of
    either text is read (Constitution VII).
    """

    source = _strip_prompt_internal_tokens(source_chunk)
    source_length = len(source)
    if source_length == 0 or source_length >= _SHORT_SOURCE_ABSORPTION_MAX_SOURCE_CHARS:
        return False
    if source_length < _COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS:
        return False
    if len(source.split()) < _SHORT_SOURCE_ABSORPTION_MIN_SOURCE_TOKENS:
        return False
    if _MARKDOWN_HEADING_LINE_PATTERN.match(source):
        return False
    answer_length = _visible_marker_chunk_length(answer_chunk)
    if answer_length > source_length * _SHORT_SOURCE_ABSORPTION_RATIO:
        return True
    return _is_torn_numbered_entry(source) and answer_length > source_length * _TORN_ENTRY_ABSORPTION_RATIO


def _is_torn_numbered_entry(source: str) -> bool:
    """A numbered entry ("22. …") that stops before a sentence ends, or on an initial ("L. H.")."""

    if _NUMBERED_ENTRY_PATTERN.match(source) is None:
        return False
    return _SENTENCE_END_PATTERN.search(source) is None or _TRAILING_INITIAL_PATTERN.search(source) is not None


def _number_leak_tokens(text: str, *, free_standing: bool = False) -> Counter[str]:
    """Spec 068 FR-001: the numbers of a text with their counts, normalised the same way on both
    sides of a comparison (see ``_NUMBER_LEAK_SUPERSCRIPT_RUN_PATTERN`` and its neighbours); with
    ``free_standing`` (an answer) digits glued to a letter are left out. Digits and letter
    classes only -- no word of the text is read (Constitution VII)."""

    text = _strip_prompt_internal_tokens(text)
    text = _NUMBER_LEAK_SUPERSCRIPT_RUN_PATTERN.sub(
        lambda match: f" {unicodedata.normalize('NFKC', match.group(0))} ", text
    )
    text = unicodedata.normalize("NFKC", text)
    text = _NUMBER_LEAK_TORN_RANGE_PATTERN.sub(r"\1\2", text)
    text = _NUMBER_LEAK_THOUSANDS_PATTERN.sub("", text)
    pattern = _NUMBER_LEAK_FREE_STANDING_DIGITS_PATTERN if free_standing else _NUMBER_LEAK_DIGITS_PATTERN
    tokens: Counter[str] = Counter(pattern.findall(text))
    for match in _NUMBER_LEAK_RANGE_PATTERN.finditer(text):
        start, end = match.group(1), match.group(2)
        if len(end) < len(start) and tokens[end] > 0:
            expanded = start[: len(start) - len(end)] + end
            if int(expanded) > int(start):
                tokens[end] -= 1
                tokens[expanded] += 1
    return +tokens


def _find_number_leaks(
    paragraph_chunks: Sequence[str],
    source_paragraph_chunks: Sequence[str],
    *,
    context_texts: Sequence[str] = (),
) -> dict[int, tuple[str, ...]]:
    """Spec 068 FR-001: per paragraph index, the numbers its answer took from elsewhere.

    A number of the answer is foreign when its own source paragraph does not carry it, not even
    as a part of a longer number. A foreign number that a neighbouring paragraph of the same
    block carries in its source more often than in its answer was MOVED, not copied ("in
    January," + "1999. During ..." answered as "in January 1999" + "During ..."): it is
    delivered once and is no leak, whatever the context holds. Otherwise it is a LEAK when the
    context around the block (``context_texts``: [CONTEXT BEFORE] and [CONTEXT AFTER], which the
    block's answer never delivers) carries it, or when a neighbour of the same block carries it
    in its source and keeps it in its answer -- the number is then delivered twice. A foreign
    number found nowhere else is the model's own (a year it supplied, a number the source wrote
    out in words) and is not read as a leak. Paragraphs with an empty answer are skipped --
    emptiness has its own road."""

    if not source_paragraph_chunks or len(source_paragraph_chunks) != len(paragraph_chunks):
        return {}
    source_tokens = [_number_leak_tokens(chunk) for chunk in source_paragraph_chunks]
    answer_tokens = [_number_leak_tokens(chunk, free_standing=True) for chunk in paragraph_chunks]
    context_tokens = {token for text in context_texts for token in _number_leak_tokens(text)}
    leaks: dict[int, tuple[str, ...]] = {}
    for index, answer in enumerate(paragraph_chunks):
        if not answer:
            continue
        own = source_tokens[index]
        foreign = [
            token
            for token in answer_tokens[index]
            if token not in own and not any(token in source_token for source_token in own)
        ]
        if not foreign:
            continue
        neighbours = [other for other in range(len(paragraph_chunks)) if other != index]
        moved = {
            token
            for other in neighbours
            for token, count in source_tokens[other].items()
            if answer_tokens[other][token] < count
        }
        delivered_twice = {
            token for other in neighbours for token in source_tokens[other] if answer_tokens[other][token]
        }
        elsewhere = (context_tokens | delivered_twice) - moved
        leaked = tuple(sorted((token for token in foreign if token in elsewhere), key=lambda t: (len(t), t)))
        if leaked:
            leaks[index] = leaked
    return leaks


def _overgrown_paragraph_ids(
    merges: Sequence["_MarkerChunkMerge"], paragraph_ids: Sequence[str] | None
) -> list[str]:
    return [
        _marker_paragraph_id(paragraph_ids, index)
        for merge in merges
        if merge.collapsed_index is None
        for index in merge.absorbing_indexes
    ]


def _find_collapsed_marker_chunk_merges(
    paragraph_chunks: Sequence[str],
    source_paragraph_chunks: Sequence[str],
    *,
    expected_paragraph_ids: Sequence[str] | None = None,
) -> list[_MarkerChunkMerge]:
    """The collapse half of ``_find_marker_chunk_merges``: a paragraph that shrank into a neighbour."""

    source_lengths = [_visible_marker_chunk_length(chunk) for chunk in source_paragraph_chunks]
    returned_lengths = [_visible_marker_chunk_length(chunk) for chunk in paragraph_chunks]

    collapsed_indexes: list[int] = []
    for index in range(len(paragraph_chunks)):
        source_length = source_lengths[index]
        if returned_lengths[index] == 0:
            # An EMPTY answer is an omission, not a merge, and it has a status of its own
            # (``omitted``). Until spec 056 E an empty chunk raised ``empty_marker_chunk``
            # before this function was ever reached, so this is the input domain the
            # restorer was calibrated on — nothing that legitimately restored before stops
            # restoring. Letting empties in was measurably wrong: the merge evidence is "a
            # neighbour grew by at least half of what this paragraph holds", and a Russian
            # translation of an English paragraph is routinely 1.5x its source, so an
            # ordinary neighbour looked like an absorber. The block then reverted the
            # emptied paragraph AND its perfectly good neighbour to English, marked both
            # ``source_restored`` — a status the narration filter keeps — and read 227
            # characters of English aloud under a ``valid`` classification.
            continue
        if source_length < _COLLAPSED_MARKER_CHUNK_MIN_SOURCE_CHARS:
            continue
        if returned_lengths[index] > source_length * _COLLAPSED_MARKER_CHUNK_RATIO:
            continue
        collapsed_indexes.append(index)

    if not collapsed_indexes:
        return []

    merges: list[_MarkerChunkMerge] = []
    kept_indexes: list[int] = []
    for index in collapsed_indexes:
        required_growth = source_lengths[index] * _ABSORBING_NEIGHBOUR_RATIO
        absorbing_indexes = [
            neighbour_index
            for neighbour_index in (index - 1, index + 1)
            if 0 <= neighbour_index < len(paragraph_chunks)
            and returned_lengths[neighbour_index] - source_lengths[neighbour_index] >= required_growth
        ]
        if not absorbing_indexes:
            # No neighbour grew to hold this text: nothing shows a merge happened, so the
            # answer is a short answer and the model's output stands.
            kept_indexes.append(index)
            continue
        merges.append(
            _MarkerChunkMerge(collapsed_index=index, absorbing_indexes=tuple(absorbing_indexes))
        )

    if kept_indexes:
        log_event(
            logging.INFO,
            "marker_chunk_shrunk_without_absorber_kept",
            "Возвращённый абзац сильно короче исходного, но поглотивший его сосед не найден; ответ модели сохранён.",
            shrunken_paragraph_ids=[
                _marker_paragraph_id(expected_paragraph_ids, index) for index in kept_indexes
            ],
            paragraph_count=len(paragraph_chunks),
        )
    return merges


def _restore_marker_chunk_merges(
    paragraph_chunks: list[str],
    source_paragraph_chunks: Sequence[str],
    merges: Sequence[_MarkerChunkMerge],
    *,
    expected_paragraph_ids: Sequence[str] | None = None,
) -> list[str]:
    """Ship the SOURCE of every merged pair, and say so. Called only once nothing is left to ask."""

    if not merges:
        return paragraph_chunks

    restored = list(paragraph_chunks)
    restored_indexes: list[int] = []
    for merge in merges:
        collapsed = () if merge.collapsed_index is None else (merge.collapsed_index,)
        for restore_index in (*collapsed, *merge.absorbing_indexes):
            restored[restore_index] = source_paragraph_chunks[restore_index]
            restored_indexes.append(restore_index)

    # The run report must show these paragraphs: the block still logs ``OK``, so without a
    # counter the reader believes a paragraph was edited when in fact its edit was thrown
    # away and the source was shipped instead. Recorded only HERE, where the source really
    # ships (spec 061 FR-005); a merge sent back for a retry is
    # ``marker_chunk_merge_retry_count`` instead.
    record_model_output_discarded(
        reason="marker_chunk_collapse",
        paragraph_count=len(set(restored_indexes)),
    )
    log_event(
        logging.WARNING,
        "marker_chunk_collapse_source_restored",
        "Возвращённый абзац схлопнулся в соседний; восстановлен исходный текст обоих абзацев.",
        collapsed_paragraph_ids=[
            _marker_paragraph_id(expected_paragraph_ids, merge.collapsed_index)
            for merge in merges
            if merge.collapsed_index is not None
        ],
        overgrown_paragraph_ids=_overgrown_paragraph_ids(merges, expected_paragraph_ids),
        restored_paragraph_count=len(set(restored_indexes)),
        paragraph_count=len(paragraph_chunks),
    )
    return restored


def _marker_paragraph_id(expected_paragraph_ids: Sequence[str] | None, index: int) -> str:
    if expected_paragraph_ids and index < len(expected_paragraph_ids):
        return expected_paragraph_ids[index]
    return str(index)


def _strip_paragraph_markers_from_source(
    target_text: str,
    expected_paragraph_ids: Sequence[str] | None,
    *,
    marker_mode: bool,
) -> str:
    """Drop the markers from the block's OWN source text.

    Separate from the model-output path on purpose. The source is not an answer: it has no
    disposition, it must not be counted in the run's per-paragraph statuses (counting it
    would report every source paragraph as ``accepted``), and an empty chunk here is a
    pipeline defect rather than a contract the model could not satisfy — so it keeps
    raising, exactly as before.
    """

    if not marker_mode:
        return target_text
    if not expected_paragraph_ids:
        raise RuntimeError("paragraph_marker_validation_failed:missing_expected_ids")
    return "\n\n".join(_split_marker_preserved_markdown(target_text, expected_paragraph_ids))


def _strip_and_validate_paragraph_markers(
    markdown: str,
    expected_paragraph_ids: Sequence[str] | None,
    *,
    marker_mode: bool,
    source_paragraph_chunks: Sequence[str] | None = None,
    allow_unresolved_paragraphs: bool = False,
    allow_merge_repair: bool | None = None,
    detect_short_source_absorption: bool = False,
    context_texts: Sequence[str] = (),
) -> str:
    if not marker_mode:
        return markdown
    if not expected_paragraph_ids:
        raise RuntimeError("paragraph_marker_validation_failed:missing_expected_ids")
    dispositions = resolve_marker_paragraph_dispositions(
        split_marker_preserved_paragraph_dispositions(markdown, expected_paragraph_ids),
        source_paragraph_chunks=source_paragraph_chunks,
        allow_unresolved_paragraphs=allow_unresolved_paragraphs,
        raw_markdown=markdown,
        allow_merge_repair=allow_merge_repair,
        detect_short_source_absorption=detect_short_source_absorption,
        context_texts=context_texts,
    )
    # The joined string still carries exactly one paragraph per marker — an ``omitted``
    # paragraph contributes its own source text — so everything downstream that counts
    # paragraphs keeps counting the same number. What rides along is WHY each one is
    # there, which is what the registry needs and could never recover from the join.
    return _marker_preserved_block_text(dispositions)


def _normalize_leakage_comparison_text(text: str) -> str:
    return " ".join(match.group(0).lower() for match in _WORD_TOKEN_PATTERN.finditer(text))


def _detect_context_leakage(
    response_text: str,
    target_text: str,
    context_before: str,
    context_after: str,
    *,
    min_word_sequence: int = 6,
) -> str | None:
    response_tokens = list(_WORD_TOKEN_PATTERN.finditer(response_text))
    if len(response_tokens) < min_word_sequence:
        return None

    normalized_target = _normalize_leakage_comparison_text(target_text)
    normalized_contexts = [
        normalized_context
        for normalized_context in (
            _normalize_leakage_comparison_text(context_before),
            _normalize_leakage_comparison_text(context_after),
        )
        if normalized_context
    ]
    if not normalized_contexts:
        return None

    for start_index in range(0, len(response_tokens) - min_word_sequence + 1):
        end_index = start_index + min_word_sequence
        fragment = response_text[
            response_tokens[start_index].start() : response_tokens[end_index - 1].end()
        ]
        normalized_fragment = _normalize_leakage_comparison_text(fragment)
        if not normalized_fragment or normalized_fragment in normalized_target:
            continue
        if any(normalized_fragment in normalized_context for normalized_context in normalized_contexts):
            return fragment
    return None


_LEAKAGE_TRIM_STRIP_CHARS = " \t\r\n-–—,:;.!?"


def _trim_boundary_context_leakage(response_text: str, leaked_fragment: str) -> tuple[str, bool]:
    trimmed_response = response_text.strip()
    if not trimmed_response or leaked_fragment not in trimmed_response:
        return response_text, False

    matches = list(re.finditer(re.escape(leaked_fragment), trimmed_response))
    if not matches:
        return response_text, False
    if any(match.start() != 0 and match.end() != len(trimmed_response) for match in matches):
        return response_text, False

    updated_text = trimmed_response
    changed = False
    while updated_text.startswith(leaked_fragment):
        updated_text = updated_text[len(leaked_fragment) :].lstrip(_LEAKAGE_TRIM_STRIP_CHARS)
        changed = True
    while updated_text.endswith(leaked_fragment):
        updated_text = updated_text[: -len(leaked_fragment)].rstrip(_LEAKAGE_TRIM_STRIP_CHARS)
        changed = True

    if not changed or not updated_text:
        return response_text, False
    return updated_text, True


def _trim_marker_preserved_boundary_leakage(
    value: str,
    leaked_fragment: str,
) -> tuple[str, bool]:
    """The boundary trim, applied to the RECORD instead of to the joined string.

    ``_trim_boundary_context_leakage`` builds its answer with ``.strip()`` and slices, which
    return a plain ``str``. Running it on a ``MarkerPreservedBlockText`` therefore threw the
    per-paragraph record away inside the generator, before the value ever reached a caller —
    the one degradation ``__reduce__`` cannot protect against — and the paragraph COUNT still
    matched afterwards, so nothing downstream noticed and an ``omitted`` paragraph's English
    source went into the narration.

    The leak is at a boundary of the whole answer by construction (the string-level function
    refuses to trim anything else), so it belongs to the first paragraph that has text or to
    the last one. Both are trimmed with the same rule, and the result is re-derived from the
    record. If the two do not agree character for character the trim could not be attributed
    to a paragraph — the answer is then rejected as a marker failure and retried, rather than
    shipped with a record that no longer describes it.
    """

    dispositions = marker_paragraph_dispositions(value)
    if dispositions is None:
        plain_trimmed, plain_was_trimmed = _trim_boundary_context_leakage(value, leaked_fragment)
        if plain_was_trimmed:
            record_text_removal(
                site=TEXT_REMOVAL_SITE_CONTEXT_LEAKAGE_BOUNDARY_TRIM,
                chars=max(0, len(value) - len(plain_trimmed)),
            )
        return plain_trimmed, plain_was_trimmed

    trimmed_text, was_trimmed = _trim_boundary_context_leakage(str(value), leaked_fragment)
    if not was_trimmed:
        return value, False

    texts = [disposition.text for disposition in dispositions]
    populated_indexes = [index for index, text in enumerate(texts) if text]
    if populated_indexes:
        first_index = populated_indexes[0]
        while texts[first_index].startswith(leaked_fragment):
            texts[first_index] = texts[first_index][len(leaked_fragment) :].lstrip(
                _LEAKAGE_TRIM_STRIP_CHARS
            )
        last_index = populated_indexes[-1]
        while texts[last_index].endswith(leaked_fragment):
            texts[last_index] = texts[last_index][: -len(leaked_fragment)].rstrip(
                _LEAKAGE_TRIM_STRIP_CHARS
            )

    rebuilt = _marker_preserved_block_text(
        [
            ParagraphDisposition(
                paragraph_id=disposition.paragraph_id,
                text=text,
                status=disposition.status,
            )
            for disposition, text in zip(dispositions, texts)
        ]
    )
    if str(rebuilt) != trimmed_text:
        raise MarkerValidationError(
            "context_leakage_trim_unattributable",
            raw_markdown=str(value),
            expected_paragraph_ids=[disposition.paragraph_id for disposition in dispositions],
            found_paragraph_ids=[disposition.paragraph_id for disposition in dispositions],
        )
    # Recorded only past the attribution check, because before it nothing has shipped: an
    # unattributable trim raises and the block is retried, so counting there would count a
    # removal that never reached the document.
    #
    # The review named this site as the one that could ship an EMPTY paragraph still
    # recorded ``accepted``. Measured, that shape does not get out: the string-level trim
    # strips the boundary whitespace it removed with the leak, so a record whose first or
    # last paragraph went empty no longer rebuilds to the same characters and the check
    # above raises instead of delivering. ``emptied_units`` is computed anyway and is the
    # tripwire for that guard — it can only ever be non-zero here if the guard stops
    # holding, and it is zero on every trim that ships today.
    record_text_removal(
        site=TEXT_REMOVAL_SITE_CONTEXT_LEAKAGE_BOUNDARY_TRIM,
        chars=sum(
            max(0, len(disposition.text) - len(text))
            for disposition, text in zip(dispositions, texts)
        ),
        emptied_units=sum(
            1
            for disposition, text in zip(dispositions, texts)
            if disposition.text and not text
        ),
    )
    return rebuilt, True


def _inject_context_leakage_retry_warning(request_kwargs: dict[str, object]) -> dict[str, object]:
    updated_request = dict(request_kwargs)
    payload = updated_request.get("input")
    if not isinstance(payload, list):
        return updated_request

    updated_payload: list[object] = []
    for index, message in enumerate(payload):
        if index != 1 or not isinstance(message, dict):
            updated_payload.append(message)
            continue

        updated_message = dict(message)
        content_items = list(updated_message.get("content", []))
        if content_items and isinstance(content_items[0], dict):
            updated_content = dict(content_items[0])
            text = updated_content.get("text")
            if isinstance(text, str) and _CONTEXT_LEAKAGE_RETRY_WARNING not in text:
                updated_content["text"] = f"{_CONTEXT_LEAKAGE_RETRY_WARNING}\n\n{text}"
                content_items[0] = updated_content
        updated_message["content"] = content_items
        updated_payload.append(updated_message)

    updated_request["input"] = updated_payload
    return updated_request


def _finalize_generated_markdown(
    markdown: str,
    *,
    target_text: str,
    context_before: str,
    context_after: str,
    expected_paragraph_ids: Sequence[str] | None,
    marker_mode: bool,
    allow_persistent_context_leakage: bool,
    source_paragraph_chunks: Sequence[str] | None = None,
    allow_unresolved_paragraphs: bool = False,
    allow_merge_repair: bool | None = None,
    detect_short_source_absorption: bool = False,
) -> str:
    cleaned_markdown = _strip_and_validate_paragraph_markers(
        markdown,
        expected_paragraph_ids,
        marker_mode=marker_mode,
        source_paragraph_chunks=source_paragraph_chunks,
        allow_unresolved_paragraphs=allow_unresolved_paragraphs,
        allow_merge_repair=allow_merge_repair,
        detect_short_source_absorption=detect_short_source_absorption,
        context_texts=(context_before, context_after),
    )
    return _deliver_after_context_leakage_check(
        cleaned_markdown,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        marker_mode=marker_mode,
        allow_persistent_context_leakage=allow_persistent_context_leakage,
        stage="finalize",
    )


def _deliver_after_context_leakage_check(
    cleaned_markdown: str,
    *,
    target_text: str,
    context_before: str,
    context_after: str,
    marker_mode: bool,
    allow_persistent_context_leakage: bool,
    stage: str,
    unattributable_trim_fails_open: bool = False,
) -> str:
    """The context-leakage check every delivered ANSWER passes, wherever it is delivered.

    One copy, because a second delivery path that skipped it (the merge pair repair after
    the ladder, review finding F6) shipped a neighbour's sentence inside a paragraph the
    model had otherwise answered well. ``unattributable_trim_fails_open`` is for callers that
    are themselves the last fallback: there a trim that cannot be attributed to a paragraph
    leaves the answer as it is, logged, instead of raising past every remaining fallback.
    """

    leaked_fragment = _detect_context_leakage(
        cleaned_markdown,
        target_text,
        context_before,
        context_after,
    )
    if leaked_fragment is None:
        return _deliver_marker_preserved_block(
            cleaned_markdown, marker_mode=marker_mode, stage=f"{stage}_clean"
        )

    try:
        trimmed_markdown, was_trimmed = _trim_marker_preserved_boundary_leakage(
            cleaned_markdown, leaked_fragment
        )
    except MarkerValidationError:
        if not unattributable_trim_fails_open:
            raise
        trimmed_markdown, was_trimmed = cleaned_markdown, False
    if was_trimmed:
        return _deliver_marker_preserved_block(
            trimmed_markdown, marker_mode=marker_mode, stage=f"{stage}_leakage_trimmed"
        )

    if allow_persistent_context_leakage:
        log_event(
            logging.WARNING,
            "context_leakage_persisted",
            "После последней попытки генерации сохранилась verbatim-протечка текста из соседнего контекста; возвращаю fail-open результат.",
            leaked_fragment=leaked_fragment,
            target_chars=len(target_text),
            marker_mode=marker_mode,
        )
        return _deliver_marker_preserved_block(
            cleaned_markdown, marker_mode=marker_mode, stage=f"{stage}_leakage_persisted"
        )

    raise ContextLeakageError(f"context_leakage_detected:{leaked_fragment}")


def _extract_response_output_text(response: object) -> str:
    traversal = collect_response_text_traversal(
        response,
        unsupported_message="Модель вернула ответ в неподдерживаемом формате (unsupported_response_shape).",
    )
    if traversal.collected_texts:
        return "\n".join(traversal.collected_texts)
    if traversal.raw_output_text is not None:
        return traversal.raw_output_text
    if not traversal.saw_output_items or traversal.saw_supported_text_shape or traversal.saw_empty_content_container:
        return ""
    raise RuntimeError("Модель вернула ответ в неподдерживаемом формате (unsupported_response_shape).")


def _log_empty_response_shape(response: object, raw_output_text: str, *, error_code: str) -> None:
    output_items = read_response_field(response, "output")
    output_items_len = len(output_items) if isinstance(output_items, Sized) else None

    first_item_summary: dict[str, object] | None = None
    if isinstance(output_items, Iterable) and not isinstance(output_items, (str, bytes)):
        for item in output_items:
            item_type = read_response_field(item, "type")
            refusal = read_response_field(item, "refusal")
            status = read_response_field(item, "status")
            content_items = read_response_field(item, "content")
            content_types: list[str] = []
            if isinstance(content_items, Iterable) and not isinstance(content_items, (str, bytes)):
                content_types = [
                    str(read_response_field(c, "type") or type(c).__name__)
                    for c in content_items
                ]
            first_item_summary = {
                "type": item_type,
                "refusal": refusal,
                "status": status,
                "content_types": content_types,
            }
            break

    log_event(
        logging.WARNING,
        "model_empty_response_shape",
        "Модель вернула пустой или схлопнувшийся текстовый ответ",
        error_code=error_code,
        has_output_text_attr=getattr(response, "output_text", None) is not None,
        raw_output_len=len(raw_output_text),
        output_items_type=type(output_items).__name__ if output_items is not None else "None",
        output_items_len=output_items_len,
        response_status=read_response_field(response, "status"),
        first_output_item=first_item_summary,
    )


_EMPTY_RESPONSE_MESSAGE = "Модель вернула пустой ответ (empty_response)."
_COLLAPSED_OUTPUT_MESSAGE = "Модель вернула ответ, который схлопнулся после нормализации (collapsed_output)."
_INCOMPLETE_RESPONSE_MESSAGE = "Модель не завершила генерацию (incomplete_response)."


def _require_complete_markdown(model_response: ModelResponse) -> str:
    """The ONE place an incomplete answer is refused, whichever API produced it (FR-011).

    Raising here, rather than in each extractor, is what makes the three paths behave
    identically: a truncated answer whose markers happen to be intact is still a truncated
    answer, and the attempt loop retries it with a larger budget on every path.
    """

    if model_response.incomplete:
        raise IncompleteResponse(_INCOMPLETE_RESPONSE_MESSAGE)
    return model_response.text


def _read_responses_model_response(response: object) -> ModelResponse:
    response_status = read_response_field(response, "status")
    if response_status == "incomplete":
        _log_empty_response_shape(response, "", error_code="incomplete_response")
        incomplete_reason = read_response_field(read_response_field(response, "incomplete_details"), "reason")
        return ModelResponse(
            text="",
            incomplete=True,
            stop_reason=incomplete_reason if isinstance(incomplete_reason, str) else None,
        )
    if isinstance(response_status, str) and response_status != "completed":
        _log_empty_response_shape(response, "", error_code="non_completed_response")
        raise NonCompletedResponse(
            f"Модель вернула неожиданный статус ответа: {response_status} (non_completed_response)."
        )

    raw_output_text = _extract_response_output_text(response)
    markdown = normalize_model_output(raw_output_text)
    if markdown:
        return ModelResponse(text=markdown)
    error_code = "collapsed_output" if raw_output_text else "empty_response"
    _log_empty_response_shape(response, raw_output_text, error_code=error_code)
    if raw_output_text:
        raise CollapsedOutput(_COLLAPSED_OUTPUT_MESSAGE)
    raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)


def _extract_normalized_markdown(response: object) -> str:
    return _require_complete_markdown(_read_responses_model_response(response))


def _call_responses_create(
    client: "OpenAI",
    request_kwargs: dict[str, Any],
    *,
    usage_stage: str = STAGE_TEXT_GENERATION,
) -> object:
    return call_responses_create_with_retry(
        client,
        request_kwargs,
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
        retryable_optional_params={"temperature", "max_output_tokens"},
        usage_stage=usage_stage,
    )


def _is_openrouter_client(client: object) -> bool:
    base_url = getattr(client, "base_url", None)
    if base_url is None:
        return False
    return "openrouter" in str(base_url).lower()


def _is_anthropic_client(client: object) -> bool:
    return callable(getattr(getattr(client, "messages", None), "create", None)) and not callable(
        getattr(getattr(client, "responses", None), "create", None)
    )


def _is_openrouter_responses_compatibility_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code not in {400, 404, 422}:
        return False
    error_text = str(exc).lower()
    return any(
        marker in error_text
        for marker in (
            "/responses",
            "responses api unsupported",
            "responses endpoint",
            "chat.completions",
            "unsupported parameter",
            "unsupported field",
            "unknown parameter",
            "unknown field",
        )
    )


def _canonicalize_model_selector_for_client(*, client: object, model: str) -> str:
    stripped_model = str(model).strip()
    if not stripped_model:
        return stripped_model
    if ":" in stripped_model:
        provider_name, _, model_id = stripped_model.partition(":")
        normalized_provider = provider_name.strip().lower()
        if normalized_provider in {"openai", "openrouter", "anthropic"} and model_id.strip():
            return f"{normalized_provider}:{model_id.strip()}"
    provider_name = "anthropic" if _is_anthropic_client(client) else "openrouter" if _is_openrouter_client(client) else "openai"
    return f"{provider_name}:{stripped_model}"


_DOTTED_VERSION_SEPARATOR_PATTERN = re.compile(r"(?<=\d)\.(?=\d)")


def _normalize_anthropic_model_id(model: str) -> str:
    """The id the Anthropic Messages API accepts, by form rather than by a table of models.

    Spec 066 B-3: the provider prefix (``anthropic:`` selector or ``anthropic/`` OpenRouter
    form) is dropped, and a dotted version number (``…-N.M``, ``claude-N.M-…``) is written
    with a dash (``…-N-M``), as Anthropic spells its ids. An id that is already canonical
    passes through unchanged.
    """

    model_id = str(model).strip()
    for prefix in ("anthropic:", "anthropic/"):
        if model_id.startswith(prefix):
            model_id = model_id[len(prefix) :].strip()
            break
    return _DOTTED_VERSION_SEPARATOR_PATTERN.sub("-", model_id)


def _extract_chat_messages_from_request(request_kwargs: dict[str, object]) -> list[dict[str, str]]:
    raw_input = request_kwargs.get("input")
    if not isinstance(raw_input, list):
        raise RuntimeError("OpenRouter Chat Completions fallback не может собрать messages из request input.")

    messages: list[dict[str, str]] = []
    for item in raw_input:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip() or "user"
        raw_content = item.get("content")
        if isinstance(raw_content, list):
            text_parts = [
                str(content_item.get("text") or "")
                for content_item in raw_content
                if isinstance(content_item, dict) and content_item.get("type") == "input_text"
            ]
            content_text = "\n".join(part for part in text_parts if part)
        else:
            content_text = str(raw_content or "")
        messages.append({"role": role, "content": content_text})

    if not messages:
        raise RuntimeError("OpenRouter Chat Completions fallback не может собрать ни одного message.")
    return messages


def _call_chat_completions_create(
    client: "OpenAI",
    request_kwargs: dict[str, object],
    *,
    should_stop: Callable[[], bool] | None = None,
    usage_stage: str = STAGE_TEXT_GENERATION,
) -> object:
    chat_completions = getattr(getattr(client, "chat", None), "completions", None)
    create = getattr(chat_completions, "create", None)
    if not callable(create):
        raise RuntimeError("Provider 'openrouter' не поддерживает required text API surface для selector '<runtime>'.")

    payload: dict[str, object] = {
        "model": request_kwargs["model"],
        "messages": _extract_chat_messages_from_request(request_kwargs),
        "temperature": request_kwargs.get("temperature"),
    }
    max_output_tokens = request_kwargs.get("max_output_tokens")
    if isinstance(max_output_tokens, int) and not isinstance(max_output_tokens, bool):
        payload["max_tokens"] = max_output_tokens

    removable_optional_params = {"temperature", "max_tokens"}
    while True:
        # Each pass is a paid SDK call (review finding F7): Stop is honoured before it.
        _raise_if_stop_requested(should_stop)
        try:
            response = create(**payload)
        except TypeError as exc:
            if drop_rejected_optional_param(exc, payload, removable_optional_params, stage=usage_stage):
                continue
            raise
        except Exception as exc:
            if drop_rejected_optional_param(exc, payload, removable_optional_params, stage=usage_stage):
                continue
            raise
        else:
            record_model_call_usage(stage=usage_stage, response=response)
            return response


def _response_item_text(item: object) -> str:
    """The text of one content item, whether it arrived as a mapping or as an SDK object.

    FR-013: branch on the item's KIND. The previous ``getattr(item, "text", "") or
    item.get("text")`` reached ``.get`` whenever ``.text`` was empty, so an SDK object with
    an empty text and no ``get`` raised ``AttributeError`` instead of contributing nothing.
    """

    if isinstance(item, Mapping):
        return str(item.get("text") or "")
    return str(getattr(item, "text", "") or "")


def _joined_response_item_texts(content: Iterable[object]) -> str:
    text_parts = [
        _response_item_text(item)
        for item in content
        if isinstance(item, Mapping) or hasattr(item, "text")
    ]
    return "\n".join(part for part in text_parts if part)


def _read_chat_completion_model_response(response: object) -> ModelResponse:
    choices = getattr(response, "choices", None)
    if not isinstance(choices, list) or not choices:
        # No choice at all is an answer with no text, and it takes the empty-response road
        # (retry, recovery, controlled fallback). An untyped ``RuntimeError`` here matched
        # none of the typed classes and ended the run.
        raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)
    first_choice = choices[0]
    finish_reason = getattr(first_choice, "finish_reason", None)
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        raw_text = content
    elif isinstance(content, list):
        raw_text = _joined_response_item_texts(content)
    else:
        raw_text = ""
    markdown = normalize_model_output(raw_text)
    # Completeness is read BEFORE emptiness, as on the Responses path: an answer cut off at
    # its first token is a budget problem, and only the incomplete path raises the budget.
    if not chat_completion_finish_is_complete(finish_reason):
        return ModelResponse(text=markdown, incomplete=True, stop_reason=str(finish_reason))
    if markdown:
        return ModelResponse(
            text=markdown,
            stop_reason=finish_reason if isinstance(finish_reason, str) else None,
        )
    if isinstance(content, str):
        raise CollapsedOutput(_COLLAPSED_OUTPUT_MESSAGE)
    raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)


def _extract_chat_completion_markdown(response: object) -> str:
    return _require_complete_markdown(_read_chat_completion_model_response(response))


def _extract_anthropic_messages_payload(request_kwargs: dict[str, object]) -> tuple[str, list[dict[str, str]]]:
    raw_input = request_kwargs.get("input")
    if not isinstance(raw_input, list):
        raise RuntimeError("Provider 'anthropic' не может собрать messages из request input.")

    system_parts: list[str] = []
    messages: list[dict[str, str]] = []
    for item in raw_input:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user").strip() or "user"
        raw_content = item.get("content")
        if isinstance(raw_content, list):
            text = "\n".join(
                str(content_item.get("text") or "")
                for content_item in raw_content
                if isinstance(content_item, dict) and content_item.get("type") == "input_text"
            )
        else:
            text = str(raw_content or "")
        if not text.strip():
            continue
        if role == "system":
            system_parts.append(text)
        else:
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": text})

    if not messages:
        raise RuntimeError("Provider 'anthropic' не может собрать ни одного message.")
    return "\n\n".join(system_parts), messages


def _call_anthropic_messages_create(
    client: object,
    request_kwargs: dict[str, object],
    *,
    should_stop: Callable[[], bool] | None = None,
    usage_stage: str = STAGE_TEXT_GENERATION,
) -> object:
    create = getattr(getattr(client, "messages", None), "create", None)
    if not callable(create):
        raise RuntimeError("Provider 'anthropic' не поддерживает required text API surface для selector '<runtime>'.")

    system_prompt, messages = _extract_anthropic_messages_payload(request_kwargs)
    payload: dict[str, object] = {
        "model": _normalize_anthropic_model_id(str(request_kwargs["model"])),
        "messages": messages,
        "max_tokens": request_kwargs.get("max_output_tokens"),
    }
    if system_prompt:
        payload["system"] = system_prompt
    temperature = request_kwargs.get("temperature")
    if temperature is not None:
        payload["temperature"] = temperature

    removable_optional_params = {"temperature"}
    while True:
        _raise_if_stop_requested(should_stop)
        try:
            response = create(**payload)
        except TypeError as exc:
            if drop_rejected_optional_param(exc, payload, removable_optional_params, stage=usage_stage):
                continue
            raise
        except Exception as exc:
            if drop_rejected_optional_param(exc, payload, removable_optional_params, stage=usage_stage):
                continue
            raise
        else:
            # Anthropic reports ``usage.input_tokens``/``output_tokens`` but no cost, so
            # this path deliberately leaves cost unknown instead of applying a price list.
            record_model_call_usage(stage=usage_stage, response=response)
            return response


def _read_anthropic_model_response(response: object) -> ModelResponse:
    stop_reason = getattr(response, "stop_reason", None)
    content = getattr(response, "content", None)
    markdown = (
        normalize_model_output(_joined_response_item_texts(content))
        if isinstance(content, list)
        else ""
    )
    if not anthropic_stop_is_complete(stop_reason):
        return ModelResponse(text=markdown, incomplete=True, stop_reason=str(stop_reason))
    if markdown:
        return ModelResponse(
            text=markdown,
            stop_reason=stop_reason if isinstance(stop_reason, str) else None,
        )
    raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)


def _extract_anthropic_message_markdown(response: object) -> str:
    return _require_complete_markdown(_read_anthropic_model_response(response))


def _estimate_max_output_tokens(target_text: str) -> int:
    estimated_output_tokens = max((len(target_text) // 3) * 4, 512)
    return min(estimated_output_tokens, _MODEL_OUTPUT_TOKEN_CEILING)


def _build_request_kwargs(*, model: str, system_prompt: str, user_prompt: str, target_text: str) -> dict[str, object]:
    payload: Any = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_prompt}],
        },
    ]
    return {
        "model": model,
        "input": payload,
        "temperature": 0.4,
        "max_output_tokens": _estimate_max_output_tokens(target_text),
    }


def _boost_request_output_budget(
    request_kwargs: dict[str, object],
    *,
    minimum_tokens: int,
) -> dict[str, object]:
    boosted_request = dict(request_kwargs)
    current_value = boosted_request.get("max_output_tokens")
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        boosted_request["max_output_tokens"] = min(
            max(current_value * 2, minimum_tokens), _MODEL_OUTPUT_TOKEN_CEILING
        )
        return boosted_request
    boosted_request["max_output_tokens"] = min(
        max(minimum_tokens, 512), _MODEL_OUTPUT_TOKEN_CEILING
    )
    return boosted_request


def _call_markdown_request_with_sdk_fallback(
    client: "OpenAI",
    request_kwargs: dict[str, object],
    *,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[str, bool]:
    # Each branch records which API answered BEFORE extracting, so a call that answered and
    # was then refused (empty, truncated) still counts against the path that served it.
    # The Assumptions of spec 061 need this number: how often the default provider really
    # falls back to Chat Completions is unknown until it is counted.
    if _is_anthropic_client(client):
        response = _call_anthropic_messages_create(client, request_kwargs, should_stop=should_stop)
        record_text_api_path(API_PATH_ANTHROPIC_MESSAGES)
        return _extract_anthropic_message_markdown(response), False
    try:
        response = _call_responses_create(client, cast(dict[str, Any], request_kwargs))
        record_text_api_path(API_PATH_RESPONSES)
        return _extract_normalized_markdown(response), False
    except Exception as exc:
        if not _is_openrouter_client(client) or not _is_openrouter_responses_compatibility_error(exc):
            raise
        log_event(
            logging.WARNING,
            "provider_text_api_fallback_engaged",
            "Responses API для text path отклонён provider-совместимостью; переключаюсь на Chat Completions fallback.",
            provider="openrouter",
            model=str(request_kwargs.get("model") or ""),
            model_selector=str(request_kwargs.get("model") or ""),
            canonical_model_selector=_canonicalize_model_selector_for_client(
                client=client,
                model=str(request_kwargs.get("model") or ""),
            ),
            api_surface="chat.completions",
            fallback_reason=str(exc),
        )
        # The compatibility fallback is a SECOND SDK call inside one generation attempt, and
        # the user may have pressed Stop while the first one was being refused.
        chat_response = _call_chat_completions_create(client, request_kwargs, should_stop=should_stop)
        record_text_api_path(API_PATH_CHAT_COMPLETIONS)
        return _extract_chat_completion_markdown(chat_response), True


def request_text_completion(
    client: Any,
    request_kwargs: dict[str, object],
    *,
    usage_stage: str,
    should_stop: Callable[[], bool] | None = None,
) -> str:
    """One auxiliary text call through the SAME provider path as the block calls.

    Spec 063 P2: the run glossary is fixed by one call of the run's text model. It goes the
    way every block goes — Anthropic Messages for an Anthropic client, otherwise the Responses
    API with the OpenRouter Chat Completions fallback on a compatibility refusal — but its
    tokens are booked under ``usage_stage`` and it does NOT touch ``api_path_counts``: that
    counter answers "what served each block" (spec 061), and a service call would skew it.
    Returns the complete answer text; an incomplete or empty answer raises like a block's would.
    """

    if _is_anthropic_client(client):
        response = _call_anthropic_messages_create(
            client, request_kwargs, should_stop=should_stop, usage_stage=usage_stage
        )
        return _extract_anthropic_message_markdown(response)
    _raise_if_stop_requested(should_stop)
    try:
        response = _call_responses_create(client, cast(dict[str, Any], request_kwargs), usage_stage=usage_stage)
        return _extract_normalized_markdown(response)
    except Exception as exc:
        if not _is_openrouter_client(client) or not _is_openrouter_responses_compatibility_error(exc):
            raise
        chat_response = _call_chat_completions_create(
            client, request_kwargs, should_stop=should_stop, usage_stage=usage_stage
        )
        return _extract_chat_completion_markdown(chat_response)


def _recover_from_persistent_empty_response(
    *,
    client: "OpenAI",
    model: str,
    system_prompt: str,
    target_text: str,
    expected_paragraph_ids: Sequence[str] | None = None,
    marker_mode: bool = False,
    minimum_output_tokens: int | None = None,
    last_exception: Exception | None = None,
    allow_merge_repair: bool = True,
    should_stop: Callable[[], bool] | None = None,
    detect_short_source_absorption: bool = False,
) -> str:
    log_event(
        logging.WARNING,
        "markdown_empty_response_recovery_started",
        "Обычные retry исчерпаны; запускаю recovery-вызов без соседнего контекста.",
        model=model,
        target_chars=len(target_text),
    )
    request_kwargs = _build_request_kwargs(
        model=model,
        system_prompt=system_prompt,
        user_prompt=(
            _build_marker_recovery_user_prompt(
                target_text=target_text,
                expected_paragraph_ids=expected_paragraph_ids,
                last_error=last_exception,
            )
            if marker_mode
            else _build_empty_response_recovery_user_prompt(target_text=target_text)
        ),
        target_text=target_text,
    )
    if minimum_output_tokens is not None:
        request_kwargs = _boost_request_output_budget(
            request_kwargs,
            minimum_tokens=minimum_output_tokens,
        )
    markdown = _call_markdown_request_with_sdk_fallback(client, request_kwargs, should_stop=should_stop)[0]
    cleaned_markdown = _strip_and_validate_paragraph_markers(
        markdown,
        expected_paragraph_ids,
        marker_mode=marker_mode,
        source_paragraph_chunks=(
            _split_marker_preserved_markdown(target_text, expected_paragraph_ids)
            if marker_mode and expected_paragraph_ids
            else None
        ),
        # The recovery call is the last chance there is; there is nothing left to retry for.
        allow_unresolved_paragraphs=True,
        # ...except for a merge, when the caller still has a ladder to hand it to.
        allow_merge_repair=allow_merge_repair,
        detect_short_source_absorption=detect_short_source_absorption,
    )
    if not cleaned_markdown.strip():
        raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)
    return _deliver_marker_preserved_block(
        cleaned_markdown, marker_mode=marker_mode, stage="recovery"
    )


def _block_source_fallback_result(
    target_text_for_leakage: str,
    *,
    expected_paragraph_ids: Sequence[str] | None,
    source_paragraph_chunks: Sequence[str] | None,
    marker_mode: bool,
) -> str:
    """The block-level fallback — every paragraph reverted to its own source — WITH a record.

    The four block-level fallbacks used to return a bare string, so a marker-mode block could
    leave the generator with no per-paragraph record for a perfectly ordinary reason. That
    made "no record" ambiguous downstream, and an ambiguous invariant cannot be enforced.
    Now every marker-mode exit carries one, which is what lets ``generate_markdown_block``
    refuse to hand back a block whose record went missing.

    The TEXT is unchanged: ``_strip_paragraph_markers_from_source`` builds
    ``target_text_for_leakage`` by joining exactly these chunks with a blank line.
    ``source_restored`` is also the truthful status — the model's answer was discarded and
    the source re-instated — and the counter for it was already being recorded by hand on
    one of the four paths.
    """

    if not marker_mode or not expected_paragraph_ids or source_paragraph_chunks is None:
        return target_text_for_leakage
    if len(source_paragraph_chunks) != len(expected_paragraph_ids):
        return target_text_for_leakage
    return _deliver_marker_preserved_block(
        _marker_preserved_block_text(
            [
                ParagraphDisposition(
                    paragraph_id=paragraph_id,
                    text=chunk,
                    status=PARAGRAPH_STATUS_SOURCE_RESTORED,
                )
                for paragraph_id, chunk in zip(expected_paragraph_ids, source_paragraph_chunks)
            ]
        ),
        marker_mode=marker_mode,
        stage="block_source_fallback",
    )


def _non_completed_response_source_fallback(
    target_text_for_leakage: str,
    *,
    model: str,
    expected_paragraph_ids: Sequence[str] | None,
    source_paragraph_chunks: Sequence[str] | None,
    marker_mode: bool,
) -> str:
    """The ``non_completed_response`` controlled fallback, ONE copy for both places it fires:
    the attempts ending on that class, and the recovery call ending on it."""

    record_model_output_discarded(reason="non_completed_response_source_fallback", block_count=1)
    log_event(
        logging.WARNING,
        "markdown_non_completed_response_source_fallback",
        "Модель повторно вернула non_completed_response; сохраняю исходный текст блока как controlled fallback.",
        model=model,
        target_chars=len(target_text_for_leakage),
        marker_mode=marker_mode,
    )
    return _block_source_fallback_result(
        target_text_for_leakage,
        expected_paragraph_ids=expected_paragraph_ids,
        source_paragraph_chunks=source_paragraph_chunks,
        marker_mode=marker_mode,
    )


def _merged_pair_repair_fallback(
    exc: BaseException | None,
    *,
    expected_paragraph_ids: Sequence[str] | None,
    source_paragraph_chunks: Sequence[str] | None,
    marker_mode: bool,
    target_text_for_leakage: str,
    context_before: str,
    context_after: str,
    detect_short_source_absorption: bool = False,
) -> str | None:
    """The merge repair the last attempt used to do, applied AFTER the ladder (FR-002/003).

    Reached only when the recovery call raised ``merged_marker_chunk`` and the ladder
    rescued nothing. The exception holds the recovery call's answer as received (spec 056
    D'), so the repair is the SAME function over the SAME answer it would have run on a
    block with no ladder: the merged pair ships its source as ``source_restored`` with the
    ``marker_chunk_collapse`` counter and event, an emptied paragraph becomes ``omitted``,
    and every other paragraph keeps its translation. ``None`` for any other exception, so
    the block-level fallbacks below see exactly what they saw before.

    The kept paragraphs are the model's text and pass the same context-leakage check every
    delivered answer passes (``_deliver_after_context_leakage_check``), fail-open because
    nothing is left behind this fallback but the whole-block source.
    """

    if (
        not marker_mode
        or not isinstance(exc, MarkerValidationError)
        or exc.error_code != MERGED_MARKER_CHUNK_ERROR_CODE
        or not expected_paragraph_ids
        or source_paragraph_chunks is None
    ):
        return None
    log_event(
        logging.WARNING,
        "marker_chunk_merge_pair_repair_after_ladder",
        "Слияние абзацев не исправлено ни повтором, ни переспросом по абзацам (переспрос не спас ни одного абзаца или не был применим); исходный текст получает только слитая пара.",
        collapsed_paragraph_ids=list(exc.collapsed_paragraph_ids),
        absorbing_paragraph_ids=list(exc.absorbing_paragraph_ids),
        paragraph_count=len(expected_paragraph_ids),
    )
    return _deliver_after_context_leakage_check(
        _strip_and_validate_paragraph_markers(
            exc.raw_markdown,
            expected_paragraph_ids,
            marker_mode=True,
            source_paragraph_chunks=source_paragraph_chunks,
            allow_unresolved_paragraphs=True,
            allow_merge_repair=True,
            # The same detection that raised, so the repair restores the paragraph it named.
            detect_short_source_absorption=detect_short_source_absorption,
            context_texts=(context_before, context_after),
        ),
        target_text=target_text_for_leakage,
        context_before=context_before,
        context_after=context_after,
        marker_mode=True,
        allow_persistent_context_leakage=True,
        stage="merge_pair_repair",
        unattributable_trim_fails_open=True,
    )


def _merged_marker_chunk_error(exc: BaseException | None) -> MarkerValidationError | None:
    if isinstance(exc, MarkerValidationError) and exc.error_code == MERGED_MARKER_CHUNK_ERROR_CODE:
        return exc
    return None


def _ladder_exception_for_block(
    recovery_exc: Exception, last_exception: Exception | None, *, marker_mode: bool
) -> Exception:
    """WHICH failure the ladder answers, when the attempts and the recovery call disagree.

    A merge comes first, from whichever call produced it, because only a merge tells the
    ladder which paragraphs to re-ask (F1): the rest of that answer is kept. Otherwise the
    recovery call's failure, as before — unless it is no trigger at all (an EMPTY recovery
    answer after the attempts broke the marker contract, review finding F5), in which case
    the attempts' marker-contract failure still is one, and skipping the ladder there would
    ship source text no per-paragraph call was ever asked for.
    """

    for candidate in (recovery_exc, last_exception):
        merged = _merged_marker_chunk_error(candidate)
        if merged is not None:
            return merged
    if _degradation_ladder_trigger(recovery_exc, marker_mode=marker_mode) is not None:
        return recovery_exc
    if (
        marker_mode
        and last_exception is not None
        and _is_retryable_marker_validation_error(last_exception)
    ):
        return last_exception
    return recovery_exc


# FR-012: every generation failure class below is decided by the exception's TYPE. Reading
# a substring of the message is how ``collapsed_output`` came to be retried by one predicate
# and unknown to the next, so that after recovery it escaped as an exception where
# ``empty_response`` took a controlled fallback. The marker-validation predicate further
# down still keys on its message prefix: that class has two raise sites that are bare
# ``RuntimeError``s, and it is not one of the four classes this rule converts.


def _is_incomplete_response_error(exc: BaseException) -> bool:
    return isinstance(exc, IncompleteResponse)


def _can_fallback_to_source_text_after_incomplete_response(target_text: str) -> bool:
    return bool(target_text.strip())


def _can_fallback_to_source_text_after_marker_validation_failure(target_text: str, *, marker_mode: bool) -> bool:
    return marker_mode and bool(target_text.strip())


def _is_empty_or_collapsed_response_error(exc: BaseException) -> bool:
    """An answer with no usable text. One class for the fallback: whether the text was
    absent or collapsed to nothing under normalisation, the block has no translation."""

    return isinstance(exc, (EmptyResponse, CollapsedOutput))


def _can_fallback_to_source_text_after_empty_response(target_text: str) -> bool:
    return bool(target_text.strip())


def _is_non_completed_response_error(exc: BaseException) -> bool:
    return isinstance(exc, NonCompletedResponse)


def _can_fallback_to_source_text_after_non_completed_response(target_text: str) -> bool:
    return bool(target_text.strip())


def _is_retryable_empty_generation_error(exc: BaseException) -> bool:
    return isinstance(exc, (EmptyResponse, CollapsedOutput, IncompleteResponse))


def _raise_if_stop_requested(should_stop: Callable[[], bool] | None) -> None:
    """FR-022: the Stop button is honoured before a model call, not only between blocks.

    Checked before every attempt, the recovery call and — through the nested call each
    ladder step makes — every ladder step, so one block's retries can no longer keep buying
    calls after the user pressed Stop. ``LatePhaseStopped`` derives from ``BaseException``,
    which is what carries it past every ``except Exception`` between here and the block loop.
    """

    if should_stop is not None and should_stop():
        raise LatePhaseStopped()


def _is_retryable_marker_validation_error(exc: Exception) -> bool:
    return isinstance(exc, RuntimeError) and "paragraph_marker_validation_failed" in str(exc)


def _is_retryable_context_leakage_error(exc: Exception) -> bool:
    return isinstance(exc, ContextLeakageError)


def _classify_retry_reason(exc: Exception) -> str:
    """Name WHY a block was retried, so the run report is diagnosable, not just a count."""

    if _is_retryable_context_leakage_error(exc):
        return "context_leakage"
    if _is_retryable_marker_validation_error(exc):
        return "marker_validation"
    if _is_incomplete_response_error(exc):
        return "incomplete_response"
    if _is_non_completed_response_error(exc):
        return "non_completed_response"
    if _is_retryable_empty_generation_error(exc):
        return "empty_generation"
    if is_retryable_error(exc):
        return "transient_api_error"
    return "other"


def _capture_marker_attempt_failure(
    exc: Exception,
    *,
    block_index: int | None,
    attempt: int,
    max_attempts: int,
    stage: str,
    target_chars: int,
) -> str | None:
    """Persist a rejected marker answer, if this failure carries one. Never raises.

    Only ``MarkerValidationError`` is captured: it is the only failure that HOLDS the
    model's answer together with the expected/found marker ids. A transient API error has
    no answer to keep, and an empty response has nothing to replay.
    """

    if not isinstance(exc, MarkerValidationError):
        return None
    try:
        return capture_rejected_marker_attempt(
            block_index=block_index,
            attempt=attempt,
            max_attempts=max_attempts,
            stage=stage,
            error_code=exc.error_code,
            expected_paragraph_ids=exc.expected_paragraph_ids,
            found_paragraph_ids=exc.found_paragraph_ids,
            raw_response=exc.raw_markdown,
            leading_text=exc.leading_text,
            target_chars=target_chars,
        )
    except Exception:
        return None


# --- The degradation ladder: DIVIDE the block instead of substituting its source -------
#
# Step 1 of the ladder is the retry loop above and is unchanged. Steps 2 and 3 live here.
# Both exist because the four controlled fallbacks below answer "the model did not give an
# accepted answer for this BLOCK" by delivering the block's own source-language text — and
# the owner's requirement is that prose be translated in full. Substituting the source is
# not a translation, and dropping the substitution without replacing it would be worse
# still: it would lose the text outright. So the answer is to ask for LESS at a time.
#
# **Step 2 — the marker contract was violated → ask each paragraph on its own, with no
# markers.** The marker contract exists to map N paragraphs onto ONE call; when the mapping
# fails, the thing to remove is the batching, not the translation. With ``marker_mode=False``
# the whole error class is unreachable by construction, not by promise:
# ``_strip_and_validate_paragraph_markers`` returns the answer untouched, and one input maps
# to one output trivially.
#
# **Step 3 — ``incomplete_response`` → divide, because the failure is one of SIZE.**
# ``_boost_request_output_budget`` doubles the budget but ``min``s it with
# ``_MODEL_OUTPUT_TOKEN_CEILING``, so a block whose answer does not fit under the ceiling is
# never answered whole however often it is retried. Division is the only remedy that changes
# the quantity the failure is about. Above one paragraph, division IS step 2. Below one
# paragraph there is no marker, so sentences are re-joined into the SAME paragraph and the
# paragraph count is invariant by construction.
#
# **Termination, by construction rather than by inspection.** The ladder is reached only
# under ``allow_controlled_source_fallback``, and every call it makes passes
# ``allow_controlled_source_fallback=False`` — which disables both the ladder and the four
# fallbacks, so a nested call either answers or raises. The sentence split is performed
# HERE, iteratively, not by a second level of nesting. Depth is therefore exactly one, and
# the calls one block can cost are bounded by
# ``(paragraphs + sentence_groups) * (max_retries + 1)``.
#
# **Nothing is ever lost.** A unit the ladder could not translate keeps its own SOURCE text
# — exactly today's outcome, but for that unit alone instead of the whole block — and the
# unit count is preserved either way, so the paragraph-per-marker mapping the formatting
# restorer depends on still holds. A rejected model answer is still never delivered: the
# ladder ships only answers that passed the ordinary validation of their own call.

_DEGRADATION_LADDER_TRIGGER_MARKER_CONTRACT = "marker_contract"
_DEGRADATION_LADDER_TRIGGER_INCOMPLETE_RESPONSE = "incomplete_response"

# The calls ONE ``generate_markdown_block`` makes beyond its ``max_retries`` attempts before
# it either answers or raises: the informed recovery call. Every call the ladder makes is a
# nested ``generate_markdown_block`` with ladders and fallbacks off, so it costs the same
# ``max_retries + this``.
MODEL_CALLS_PER_GENERATION_BEYOND_RETRIES = 1


def max_model_calls_per_block(
    *, max_retries: int, ladder_paragraph_count: int, ladder_sentence_group_count: int = 0
) -> int:
    """The arithmetic ceiling on model calls for ONE block (spec 061 FR-004; spec 059 a-r 9).

    ``max_retries`` attempts and one recovery for the block, then one ladder step: one nested
    generation per paragraph, plus one per sentence group of a paragraph that came back
    ``incomplete_response`` again. Every nested generation is bounded the same way and none
    can open a ladder of its own, so the ceiling is a product, not a recursion.

    The unit is a GENERATION ATTEMPT — one request the attempt loop, the recovery call or a
    ladder step makes. It is not an SDK call: on OpenRouter a Responses request refused for
    compatibility is re-sent to Chat Completions inside the same attempt, so one attempt may
    cost up to TWO SDK calls (``api_path_counts`` counts the answers served, one per
    attempt that got one). Parameter-removal re-sends inside one SDK dispatch are likewise
    not counted here.

    A merged paragraph (``merged_marker_chunk``, FR-001/002) travels the SAME road every other
    marker-contract failure already did — the block's attempts, its recovery call, one ladder
    step — and its pair-repair fallback after the ladder makes no call at all, so it does not
    appear here. The tests that pin this ceiling are what keep it that way.
    """

    calls_per_generation = max_retries + MODEL_CALLS_PER_GENERATION_BEYOND_RETRIES
    ladder_generations = max(0, ladder_paragraph_count) + max(0, ladder_sentence_group_count)
    return calls_per_generation * (1 + ladder_generations)

# Where a sentence ends, for the purpose of dividing one paragraph. A strict SUBSET of
# ``_NARRATION_SENTENCE_TERMINALS``: a colon and a semicolon join clauses rather than close
# a sentence, and cutting a translation unit at one of them would hand the model half a
# thought. Punctuation classes only — Constitution VII forbids word lists, and no list of
# abbreviations is consulted. An abbreviation is recognised by its FORM instead (see
# ``_ladder_boundary_is_abbreviation``), so "et al. (2004)" and "т. д. и" stay whole; an
# abbreviation of another form ("U.S. Treasury", "approx. 5") can still be split at the wrong
# place. That mis-split costs coherence inside ONE paragraph on the last resort before
# shipping English, and it cannot move text between paragraphs: the pieces are re-joined
# into the same paragraph.
_LADDER_SENTENCE_TERMINALS = ".!?…"
# Characters that may OPEN the text after a boundary before its first letter or digit, as
# the bracket in "et al. (2004)" does. Punctuation only.
_LADDER_OPENING_MARKS = "«“‘\"'([{"
# The token in front of a dot: a run of letters not preceded by another letter. Its LENGTH
# and CASE are what the abbreviation rule reads; the letters themselves are never compared
# to anything.
_LADDER_DOT_TOKEN_PATTERN = re.compile(r"(?<![^\W\d_])([^\W\d_]+)\.$")
# The longest lowercase token the abbreviation rule treats as shortened ("al.", "pp.",
# "т."); "approx." is longer and still splits — an accepted tail, not a list entry.
_LADDER_ABBREVIATION_MAX_LETTERS = 3
# Two fixed-width look-behinds rather than one with an optional class: Python's ``re``
# rejects a variable-width look-behind outright.
_LADDER_SENTENCE_BOUNDARY_PATTERN = re.compile(
    r"(?:(?<=["
    + re.escape(_LADDER_SENTENCE_TERMINALS)
    + r"])|(?<=["
    + re.escape(_LADDER_SENTENCE_TERMINALS)
    + r"]["
    + re.escape(_NARRATION_CLOSING_MARKS)
    + r"]))\s+"
)
# The most SOURCE characters whose answer can still be BUDGETED under the provider ceiling.
# Derived from the two functions that own the budget rather than chosen: with
# ``_estimate_max_output_tokens`` asking for ``len // 3 * 4`` tokens, a unit longer than
# this is clamped by ``_MODEL_OUTPUT_TOKEN_CEILING`` and no amount of doubling raises it.
_LADDER_BUDGETABLE_SOURCE_CHARS = _MODEL_OUTPUT_TOKEN_CEILING * 3 // 4


def _ladder_source_units(text: str) -> list[str]:
    """The paragraphs of a block that carries no marker record.

    Split on the literal blank line, and NOT on ``\\n\\s*\\n``, because the paragraph count
    of a marker-free block is read back downstream by
    ``block_execution.build_processed_paragraph_registry_entries``, which splits on exactly
    ``"\\n\\n"``. A looser split here would let the ladder emit a paragraph count the
    registry then rejects as a mismatch — same text, different arithmetic.
    """

    return [unit.strip() for unit in text.split("\n\n") if unit.strip()]


def _ladder_boundary_is_abbreviation(before: str, after: str) -> bool:
    """Whether the dot in front of a boundary shortens a word rather than ends a sentence.

    A FORM rule, not a list (Constitution VII): the dot follows a lowercase token of at most
    ``_LADDER_ABBREVIATION_MAX_LETTERS`` letters, AND the text after the boundary begins —
    past any opening bracket or quote — with a lowercase letter or a digit, which a new
    sentence does not. Both halves are required: "the end. Then" splits on the second, a
    long word before the dot splits on the first. A dot INSIDE a token ("p.325", "e.g")
    was never a boundary — the boundary needs whitespace after the terminal.

    Measured cause: the 2026-11-07 ``20261107T_061_audio_money`` run printed "Reinhart
    et al." as the address of a paragraph whose first sentence is "Reinhart et al. (2004).".
    """

    token = _LADDER_DOT_TOKEN_PATTERN.search(before)
    if token is None:
        return False
    letters = token.group(1)
    if len(letters) > _LADDER_ABBREVIATION_MAX_LETTERS or not letters.islower():
        return False
    head = after.lstrip(_LADDER_OPENING_MARKS)
    if not head:
        return False
    first = head[0]
    return first.isdigit() or (first.isalpha() and first.islower())


def _ladder_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for boundary in _LADDER_SENTENCE_BOUNDARY_PATTERN.finditer(text):
        # Small slices, not the whole text on each side: the rule reads one token on each
        # side, and full slices per boundary of a long paragraph would make the split
        # quadratic. A slice one letter longer than the limit shows a token is too long.
        before = text[max(0, boundary.start() - _LADDER_ABBREVIATION_MAX_LETTERS - 2) : boundary.start()]
        after = text[boundary.end() : boundary.end() + len(_LADDER_OPENING_MARKS) + 1]
        if _ladder_boundary_is_abbreviation(before, after):
            continue
        sentences.append(text[start : boundary.start()])
        start = boundary.end()
    sentences.append(text[start:])
    return [part.strip() for part in sentences if part.strip()]


def _ladder_sentence_groups(text: str) -> list[str]:
    """Two or more sentence groups of *text*, or ``[]`` when it cannot be divided.

    The group limit is ``min(budgetable, half the unit)``: the first half of the pair keeps
    a group answerable under the ceiling, the second guarantees that a divisible unit is
    ACTUALLY divided rather than re-asked whole, which would be a paid call that changes
    nothing. Returning ``[]`` is how the ladder declines, and declining is what keeps a
    single-sentence paragraph from costing a duplicate call.

    A unit whose own text carries a structural line is not divided at all. The guard is
    ``_has_structural_output_line``, the same one ``split_marker_preserved_paragraph_dispositions``
    uses: a heading welded to the sentence after it stops being a heading, and repairing
    size by destroying a structural role is Constitution VII rule 7 exactly.
    """

    if _has_structural_output_line(text):
        return []
    sentences = _ladder_sentences(text)
    if len(sentences) < 2:
        return []
    group_limit = min(_LADDER_BUDGETABLE_SOURCE_CHARS, (len(text) + 1) // 2)
    groups: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}" if current else sentence
        if current and len(candidate) > group_limit:
            groups.append(current)
            current = sentence
            continue
        current = candidate
    if current:
        groups.append(current)
    return groups if len(groups) >= 2 else []


def _ladder_model_answer(
    *,
    client: "OpenAI",
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
    block_index: int | None,
    unit_label: str,
    should_stop: Callable[[], bool] | None = None,
    detect_short_source_absorption: bool = False,
) -> str:
    """One ladder call, for ONE paragraph, answered as one paragraph. Raises otherwise.

    ``allow_controlled_source_fallback=False`` is what makes the call honest AND what makes
    the ladder terminate: without it the nested call would answer a rejection by returning
    the source text, which the ladder cannot distinguish from a translation, and it would
    be free to open a ladder of its own.

    Two things the ordinary non-marker validation does not check, because outside the ladder
    nothing promised them, and inside it both are load-bearing:

    * **Paragraph markers are stripped.** There are none to keep in this mode, so a marker
      in the answer is the model echoing a token out of the block this unit was cut from,
      and an internal identifier must never reach the reader.
    * **The answer must be ONE paragraph.** The request carried one, and the block's
      paragraph count is the invariant the whole ladder rests on — a two-paragraph answer
      dropped into one paragraph's slot would ship three paragraphs under two markers. The
      break is treated exactly as ``split_marker_preserved_paragraph_dispositions`` treats
      it for a one-marker block: collapsed when the pieces are prose, and rejected when the
      answer carries a structural line, because welding ``## Заголовок`` to the sentence
      after it repairs a split by destroying a role (Constitution VII rule 7).

    And the two answer rules of the marker path, because a ladder call is not exempt from
    them (spec 065): a parenthetical meta-comment about the book's structure is an empty
    answer (FR-006), and -- with ``detect_short_source_absorption`` -- a short paragraph that
    outgrew its source took in a neighbour's text (FR-005). Either way the unit is not
    rescued and keeps its source, as any unit the ladder cannot translate does.
    """

    answer = generate_markdown_block(
        client=client,
        model=model,
        system_prompt=system_prompt,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        max_retries=max_retries,
        expected_paragraph_ids=None,
        marker_mode=False,
        block_index=block_index,
        allow_controlled_source_fallback=False,
        # The nested call checks this before each of its attempts, so every ladder step is
        # preceded by a stop check without the ladder growing one of its own (FR-022).
        should_stop=should_stop,
    )
    cleaned = _PARAGRAPH_MARKER_PATTERN.sub("", answer).strip()
    if not cleaned:
        raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)
    if re.search(r"\n\s*\n", cleaned):
        if _has_structural_output_line(cleaned):
            raise RuntimeError(f"ladder_answer_paragraph_split:{unit_label}")
        cleaned = _collapse_single_marker_paragraph_break(cleaned, paragraph_id=unit_label)
    comment = structural_meta_comment(cleaned, target_text)
    if comment is not None:
        log_event(
            logging.WARNING,
            "marker_chunk_meta_comment_rejected",
            "Модель вернула вместо абзаца скобочный комментарий о структуре книги; ответ отклонён как пустой.",
            paragraph_id=unit_label,
            comment_text=comment,
            answer_chars=len(cleaned),
        )
        raise EmptyResponse(_EMPTY_RESPONSE_MESSAGE)
    if detect_short_source_absorption and _is_short_source_absorption(target_text, cleaned):
        log_event(
            logging.WARNING,
            "degradation_ladder_short_source_absorption_rejected",
            "Ответ на короткий абзац во много раз длиннее исходника — вобрал текст соседа; абзац остаётся исходным.",
            paragraph_id=unit_label,
            source_chars=_visible_marker_chunk_length(target_text),
            answer_chars=_visible_marker_chunk_length(cleaned),
        )
        raise RuntimeError(f"ladder_answer_short_source_absorption:{unit_label}")
    return cleaned


@dataclass
class _LadderUnitOutcome:
    """What became of one unit, and what dividing it below the paragraph cost."""

    text: str | None = None
    sentence_split: bool = False
    oversized_sentences: int = 0


def _ladder_translate_unit(
    *,
    client: "OpenAI",
    model: str,
    system_prompt: str,
    unit_text: str,
    unit_label: str,
    context_before: str,
    context_after: str,
    max_retries: int,
    block_index: int | None,
    should_stop: Callable[[], bool] | None = None,
    detect_short_source_absorption: bool = False,
) -> _LadderUnitOutcome:
    """Translate ONE paragraph, dividing it by sentences if its size is what failed.

    All-or-nothing per paragraph on purpose. A paragraph assembled from some translated
    sentence groups and some source ones would ship a NEW defect shape — a paragraph in two
    languages — in exchange for less English. Reverting the whole paragraph keeps the
    outcome one a reader can recognise, and it is exactly what today's code already does for
    the entire block.
    """

    outcome = _LadderUnitOutcome()
    try:
        outcome.text = _ladder_model_answer(
            client=client,
            model=model,
            system_prompt=system_prompt,
            target_text=unit_text,
            context_before=context_before,
            context_after=context_after,
            max_retries=max_retries,
            block_index=block_index,
            unit_label=unit_label,
            should_stop=should_stop,
            detect_short_source_absorption=detect_short_source_absorption,
        )
        return outcome
    except Exception as exc:
        if not _is_incomplete_response_error(exc):
            return outcome

    groups = _ladder_sentence_groups(unit_text)
    if not groups:
        if len(unit_text) > _LADDER_BUDGETABLE_SOURCE_CHARS:
            outcome.oversized_sentences = 1
            log_event(
                logging.WARNING,
                "degradation_ladder_sentence_exceeds_output_ceiling",
                "Абзац не помещается в потолок max_output_tokens и не делится ниже одного "
                "предложения; в документе остаётся его исходный текст.",
                paragraph_chars=len(unit_text),
                budgetable_chars=_LADDER_BUDGETABLE_SOURCE_CHARS,
            )
        return outcome

    outcome.sentence_split = True
    log_event(
        logging.INFO,
        "degradation_ladder_sentence_split",
        "Абзац снова вернулся incomplete_response; делю его по предложениям и склеиваю обратно в тот же абзац.",
        paragraph_chars=len(unit_text),
        group_count=len(groups),
    )
    translated_groups: list[str] = []
    for index, group in enumerate(groups):
        if len(group) > _LADDER_BUDGETABLE_SOURCE_CHARS:
            outcome.oversized_sentences += 1
            log_event(
                logging.WARNING,
                "degradation_ladder_sentence_exceeds_output_ceiling",
                "Одно предложение само превышает потолок max_output_tokens; глубже деления нет, "
                "спрашиваю его как есть.",
                paragraph_chars=len(unit_text),
                sentence_chars=len(group),
                budgetable_chars=_LADDER_BUDGETABLE_SOURCE_CHARS,
            )
        try:
            translated_groups.append(
                _ladder_model_answer(
                    client=client,
                    model=model,
                    system_prompt=system_prompt,
                    target_text=group,
                    context_before=groups[index - 1] if index > 0 else context_before,
                    context_after=groups[index + 1] if index + 1 < len(groups) else context_after,
                    max_retries=max_retries,
                    block_index=block_index,
                    unit_label=unit_label,
                    should_stop=should_stop,
                    detect_short_source_absorption=detect_short_source_absorption,
                )
            )
        except Exception:
            return outcome
    # One paragraph in, one paragraph out: the groups are re-joined with a space, the same
    # way ``_collapse_single_marker_paragraph_break`` re-joins a paragraph the model broke.
    outcome.text = " ".join(translated_groups)
    return outcome


def _degradation_ladder_trigger(exc: Exception, *, marker_mode: bool) -> str | None:
    if _is_incomplete_response_error(exc):
        return _DEGRADATION_LADDER_TRIGGER_INCOMPLETE_RESPONSE
    if marker_mode and _is_retryable_marker_validation_error(exc):
        return _DEGRADATION_LADDER_TRIGGER_MARKER_CONTRACT
    return None


def _degradation_ladder_divides(units: Sequence[str], *, trigger: str) -> bool:
    """Would the ladder actually ask for LESS than the call that just failed?

    The anti-vacuum guard, and the reason a first-try block costs exactly one call and a
    single-sentence block costs no extra one. For the marker contract the answer is always
    yes: dropping the contract changes the request even for a one-paragraph block, and that
    is the whole remedy. For ``incomplete_response`` the request only gets smaller if there
    is more than one paragraph, or if the one paragraph divides by sentences.
    """

    if not units:
        return False
    if trigger == _DEGRADATION_LADDER_TRIGGER_MARKER_CONTRACT:
        return True
    if len(units) > 1:
        return True
    return bool(_ladder_sentence_groups(units[0]))


def _degradation_ladder_block_result(
    outcomes: Sequence[_LadderUnitOutcome | None],
    *,
    source_units: Sequence[str],
    expected_paragraph_ids: Sequence[str] | None,
    marker_mode: bool,
    kept_dispositions: Mapping[int, ParagraphDisposition] | None = None,
    leakage_context: tuple[str, str, str] | None = None,
) -> str:
    """Assemble the ladder's answers into ONE block, with the per-paragraph record.

    Built exactly the way ``_block_source_fallback_result`` builds the source fallback —
    ``_marker_preserved_block_text`` from one ``ParagraphDisposition`` per expected id — so
    the record cannot disagree with the text and ``_deliver_marker_preserved_block`` can
    still refuse a block that lost it. What differs is the status.

    ``accepted`` for a paragraph the ladder translated. **``omitted``, not
    ``source_restored``, for one it could not** — and the choice is forced by what the two
    statuses actually DO, which is the only thing they differ in downstream:
    ``narration_projection_for_processed_block`` withholds ``omitted`` and speaks
    ``source_restored``. The block-level fallback this ladder stands in front of is dropped
    from the narration whole (``block_execution.fallback_delivered_source_text``), so
    marking a leftover paragraph ``source_restored`` would make a PARTIAL rescue read more
    source-language text aloud than no rescue at all — the one paragraph the ladder failed
    on would become the only thing a listener hears in English. ``omitted`` is also the
    truthful description of the outcome it names: the paragraph's own source stands in the
    DOCX, so nothing is lost and the paragraph-per-marker mapping holds, and the narration
    skips it, which is spec 054's rule. It is already wired end to end — counters, the
    ``narration_omitted_paragraphs_excluded`` notice and its characters.

    Since spec 061 FR-006 the narration difference holds only on ``edit``: in a
    language-changing operation the projection withholds ``source_restored`` too, so there
    the choice no longer changes what is spoken. It still changes what is TRUE — the ladder
    did not repair a merge, it failed to translate — which is why ``omitted`` stays.

    ``kept_dispositions`` are paragraphs the ladder did NOT re-ask (a merge scopes it to the
    merged paragraphs, review finding F1): they keep the record they arrived with, and a
    ``None`` outcome stands in their slot. ``leakage_context`` — ``(target, before, after)``
    — runs the kept model text through the same context-leakage check as any answer.
    """

    kept = kept_dispositions or {}

    def _translated(index: int) -> str | None:
        outcome = outcomes[index]
        return outcome.text if outcome is not None else None

    resolved: list[str] = []
    for index, source in enumerate(source_units):
        translated = _translated(index)
        if index in kept:
            resolved.append(kept[index].text)
        elif translated is not None:
            resolved.append(translated)
        else:
            resolved.append(source)
    source_restored_count = sum(
        1 for index in range(len(outcomes)) if index not in kept and _translated(index) is None
    )
    if source_restored_count:
        record_model_output_discarded(
            reason="degradation_ladder_paragraph_source_fallback",
            paragraph_count=source_restored_count,
        )
    if not marker_mode:
        return "\n\n".join(resolved)
    # ``_attempt_degradation_ladder`` refuses to run in marker mode without one source chunk
    # per expected id, so this pairing is total. It is checked rather than assumed because
    # the failure it guards against — a marker-mode block leaving with a bare string — is
    # exactly the silent state ``MarkerParagraphRecordLost`` was introduced to make loud,
    # and an ``assert`` disappears under ``-O``.
    if expected_paragraph_ids is None or len(expected_paragraph_ids) != len(resolved):
        raise MarkerParagraphRecordLost("degradation_ladder")
    block = _marker_preserved_block_text(
        [
            kept[index]
            if index in kept
            else ParagraphDisposition(
                paragraph_id=paragraph_id,
                text=text,
                status=(
                    PARAGRAPH_STATUS_ACCEPTED
                    if _translated(index) is not None
                    else PARAGRAPH_STATUS_OMITTED
                ),
            )
            for index, (paragraph_id, text) in enumerate(zip(expected_paragraph_ids, resolved))
        ]
    )
    if leakage_context is None:
        return _deliver_marker_preserved_block(block, marker_mode=marker_mode, stage="degradation_ladder")
    target_text, context_before, context_after = leakage_context
    return _deliver_after_context_leakage_check(
        block,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        marker_mode=marker_mode,
        allow_persistent_context_leakage=True,
        stage="degradation_ladder",
        unattributable_trim_fails_open=True,
    )


def _merge_ladder_scope(
    exc: Exception,
    *,
    expected_paragraph_ids: Sequence[str],
    source_paragraph_chunks: Sequence[str],
) -> tuple[list[int], dict[int, ParagraphDisposition]] | None:
    """For a ``merged_marker_chunk``: which paragraphs to re-ask, and what the rest keep.

    Review finding F1. Re-asking the WHOLE block for a merge of two paragraphs threw away
    every other paragraph's good translation: a paragraph the merge never touched, re-asked
    and failed, shipped its source — so a ladder that rescued ONE paragraph made the block
    worse than a ladder that rescued none (whose pair fallback keeps them). The merge names
    its paragraphs (the collapsed one and its absorber), and only those are re-asked; every
    other paragraph keeps the model's answer from the exception as received — ``accepted``,
    or ``omitted`` with its source when that chunk was empty, the last-attempt rule. A chunk
    that is a parenthetical meta-comment counts as empty here too (spec 065 FR-006): it was
    rejected as one when the answer was resolved, and keeping it would ship it.

    ``None`` — the whole block is re-asked, as before — for any other trigger, or when the
    answer cannot be re-read paragraph by paragraph.
    """

    merged = _merged_marker_chunk_error(exc)
    if merged is None:
        return None
    affected_ids = set(merged.collapsed_paragraph_ids) | set(merged.absorbing_paragraph_ids)
    affected = [index for index, paragraph_id in enumerate(expected_paragraph_ids) if paragraph_id in affected_ids]
    if not affected:
        return None
    try:
        answered = split_marker_preserved_paragraph_dispositions(merged.raw_markdown, expected_paragraph_ids)
    except MarkerValidationError:
        return None
    kept: dict[int, ParagraphDisposition] = {}
    for index, disposition in enumerate(answered):
        if index in affected:
            continue
        answered_text = disposition.text
        if answered_text and structural_meta_comment(answered_text, source_paragraph_chunks[index]) is not None:
            answered_text = ""
        kept[index] = (
            ParagraphDisposition(
                paragraph_id=disposition.paragraph_id,
                text=answered_text,
                status=PARAGRAPH_STATUS_ACCEPTED,
            )
            if answered_text
            else ParagraphDisposition(
                paragraph_id=disposition.paragraph_id,
                text=source_paragraph_chunks[index],
                status=PARAGRAPH_STATUS_OMITTED,
            )
        )
    return affected, kept


def _attempt_degradation_ladder(
    exc: Exception,
    *,
    client: "OpenAI",
    model: str,
    system_prompt: str,
    max_retries: int,
    block_index: int | None,
    marker_mode: bool,
    expected_paragraph_ids: Sequence[str] | None,
    source_paragraph_chunks: Sequence[str] | None,
    target_text_for_leakage: str,
    context_before: str,
    context_after: str,
    allow_controlled_source_fallback: bool,
    should_stop: Callable[[], bool] | None = None,
    detect_short_source_absorption: bool = False,
) -> str | None:
    """Steps 2 and 3, or ``None`` when the ladder declines or rescues nothing.

    ``None`` hands the block back to the four controlled fallbacks below completely
    unchanged — same text, same event, same counter. So the worst the ladder can do is cost
    calls; it can never make the delivered block worse than it is today.
    """

    if not allow_controlled_source_fallback:
        return None
    trigger = _degradation_ladder_trigger(exc, marker_mode=marker_mode)
    if trigger is None:
        return None

    if marker_mode:
        # In marker mode the units MUST be the marker chunks, one per expected id. Splitting
        # the joined text instead could yield a different count, and the assembly below would
        # then return a bare string for a marker-mode block — the exact ambiguity
        # ``_deliver_marker_preserved_block`` exists to make impossible. Declining is the
        # safe answer: the block falls through to today's fallback with its record intact.
        if (
            not expected_paragraph_ids
            or source_paragraph_chunks is None
            or len(source_paragraph_chunks) != len(expected_paragraph_ids)
        ):
            return None
        units = list(source_paragraph_chunks)
        scope = _merge_ladder_scope(
            exc,
            expected_paragraph_ids=expected_paragraph_ids,
            source_paragraph_chunks=source_paragraph_chunks,
        )
    else:
        units = _ladder_source_units(target_text_for_leakage)
        scope = None
    if not _degradation_ladder_divides(units, trigger=trigger):
        return None
    asked_indexes = scope[0] if scope is not None else list(range(len(units)))
    kept_dispositions = scope[1] if scope is not None else {}

    ledger = get_run_model_accounting_ledger()
    calls_before = ledger.model_call_count()
    log_event(
        logging.WARNING,
        "degradation_ladder_started",
        "Блок отвергнут после recovery; вместо подстановки исходника переспрашиваю его частями.",
        trigger=trigger,
        block_index=block_index,
        unit_count=len(asked_indexes),
        block_unit_count=len(units),
        marker_mode=marker_mode,
    )
    outcomes: list[_LadderUnitOutcome | None] = [None] * len(units)
    for index in asked_indexes:
        unit_text = units[index]
        outcomes[index] = (
            _ladder_translate_unit(
                client=client,
                model=model,
                system_prompt=system_prompt,
                unit_text=unit_text,
                unit_label=_marker_paragraph_id(expected_paragraph_ids, index),
                # The neighbouring paragraph is the context that was already there. Handing
                # the model "[no context]" instead would make the divided call weaker than
                # the batched one it replaces.
                context_before=units[index - 1] if index > 0 else context_before,
                context_after=units[index + 1] if index + 1 < len(units) else context_after,
                max_retries=max_retries,
                block_index=block_index,
                should_stop=should_stop,
                detect_short_source_absorption=detect_short_source_absorption,
            )
        )

    asked_outcomes = [outcome for outcome in outcomes if outcome is not None]
    translated_count = sum(1 for outcome in asked_outcomes if outcome.text is not None)
    record_degradation_ladder(
        trigger=trigger,
        model_call_count=ledger.model_call_count() - calls_before,
        translated_paragraph_count=translated_count,
        unrescued_paragraph_count=len(asked_outcomes) - translated_count,
        sentence_split_paragraph_count=sum(1 for outcome in asked_outcomes if outcome.sentence_split),
        oversized_sentence_count=sum(outcome.oversized_sentences for outcome in asked_outcomes),
    )
    log_event(
        logging.WARNING,
        "degradation_ladder_completed",
        "Переспрос блока частями завершён.",
        trigger=trigger,
        block_index=block_index,
        unit_count=len(asked_outcomes),
        translated_unit_count=translated_count,
        unrescued_unit_count=len(asked_outcomes) - translated_count,
        model_call_count=ledger.model_call_count() - calls_before,
    )
    if not translated_count:
        return None
    return _degradation_ladder_block_result(
        outcomes,
        source_units=units,
        expected_paragraph_ids=expected_paragraph_ids,
        marker_mode=marker_mode,
        kept_dispositions=kept_dispositions,
        leakage_context=(
            (target_text_for_leakage, context_before, context_after) if kept_dispositions else None
        ),
    )


def generate_markdown_block(
    client: "OpenAI",
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
    expected_paragraph_ids: Sequence[str] | None = None,
    marker_mode: bool = False,
    block_index: int | None = None,
    *,
    allow_controlled_source_fallback: bool = True,
    should_stop: Callable[[], bool] | None = None,
    detect_short_source_absorption: bool = False,
) -> str:
    """Process ONE block, retrying, then dividing, and only then substituting its source.

    ``allow_controlled_source_fallback`` is internal to the degradation ladder and no
    pipeline caller passes it. ``False`` means "answer or raise": both the ladder and the
    four controlled source fallbacks are off, so the caller can tell a translation from a
    silently substituted source — and, because the ladder only ever calls with ``False``,
    the ladder cannot re-enter itself and the recursion depth is exactly one.

    ``should_stop``, when given, is asked before every model call this block makes — each
    attempt, the recovery call and each ladder step — and a ``True`` raises
    ``LatePhaseStopped`` instead of making the call (spec 061 FR-022).

    ``detect_short_source_absorption`` (spec 065 FR-005) is the caller's statement that this
    block is a translation, where a short paragraph's answer has a bounded length: an answer
    past ``_SHORT_SOURCE_ABSORPTION_RATIO`` is then handled as a merge -- asked again, re-asked
    alone by the ladder, its source on repair. Off by default, so every other caller (the
    audiobook operation, which is told to spell abbreviations out, and the post-processing
    passes) is unchanged.
    """

    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries должен быть целым числом.")
    if max_retries < 1:
        raise ValueError("max_retries должен быть не меньше 1.")

    if _should_passthrough_target(target_text):
        log_event(
            logging.WARNING,
            "image_only_target_passthrough",
            "Целевой блок не содержит редактируемого текста; возвращаю его без вызова модели.",
            target_chars=len(target_text),
            marker_mode=marker_mode,
        )
        return target_text

    context_before_text = _normalize_context_text(_strip_image_placeholders(context_before))
    context_after_text = _normalize_context_text(_strip_image_placeholders(context_after))
    prompt_warnings = _validate_prompt_inputs(target_text, context_before_text, context_after_text)
    if prompt_warnings:
        log_event(
            logging.WARNING,
            "prompt_quality_warning",
            "Входные данные prompt содержат потенциально проблемный shape.",
            warnings=prompt_warnings,
            target_chars=len(target_text),
            context_before_chars=len(context_before_text),
            context_after_chars=len(context_after_text),
            marker_mode=marker_mode,
        )

    request_kwargs = _build_request_kwargs(
        model=model,
        system_prompt=system_prompt,
        user_prompt=(
            _build_marker_preserving_user_prompt(
                target_text=target_text,
                context_before=context_before_text,
                context_after=context_after_text,
            )
            if marker_mode
            else _build_standard_user_prompt(
                target_text=target_text,
                context_before=context_before_text,
                context_after=context_after_text,
            )
        ),
        target_text=target_text,
    )
    target_text_for_leakage = _strip_paragraph_markers_from_source(
        target_text,
        expected_paragraph_ids,
        marker_mode=marker_mode,
    )
    source_paragraph_chunks = (
        _split_marker_preserved_markdown(target_text, expected_paragraph_ids)
        if marker_mode and expected_paragraph_ids
        else None
    )
    last_exception: Exception | None = None
    # A block that needed a second attempt is invisible today: every retry is silent and
    # the block still reports ``OK``. Count the attempts, the blocks and — in marker mode,
    # where the mapping is exact — the paragraphs those blocks carried.
    block_paragraph_count = len(expected_paragraph_ids) if marker_mode and expected_paragraph_ids else 0
    block_was_retried = False

    for attempt in range(1, max_retries + 1):
        # Outside the ``try`` on purpose: a stop is not a failed attempt to classify.
        _raise_if_stop_requested(should_stop)
        try:
            markdown = _call_markdown_request_with_sdk_fallback(
                client, request_kwargs, should_stop=should_stop
            )[0]
            return _finalize_generated_markdown(
                markdown,
                target_text=target_text_for_leakage,
                context_before=context_before_text,
                context_after=context_after_text,
                expected_paragraph_ids=expected_paragraph_ids,
                marker_mode=marker_mode,
                allow_persistent_context_leakage=attempt >= max_retries,
                source_paragraph_chunks=source_paragraph_chunks,
                # Same shape as the leakage fail-open one line above: while budget remains
                # an unanswered paragraph is worth asking about again (2 of 7 bare-number
                # paragraphs were rescued that way on the 2026-08-04 run), and on the last
                # attempt the answer stands with a per-paragraph status instead of the
                # whole block being replaced by its own source.
                allow_unresolved_paragraphs=attempt >= max_retries,
                # A merge has one more remedy than an omission: the ladder (FR-002). With
                # the ladder available the last attempt raises ``merged_marker_chunk`` and
                # the block goes on to the recovery call and then the ladder; without it
                # (a nested ladder call, or a caller that turned fallbacks off) the last
                # attempt repairs the pair, exactly as before.
                allow_merge_repair=attempt >= max_retries and not allow_controlled_source_fallback,
                detect_short_source_absorption=detect_short_source_absorption,
            )
        except Exception as exc:
            last_exception = exc
            # Spec 056 D': write the rejected answer down HERE, before anything decides
            # whether to retry or to fall back. Every other place is too late — a controlled
            # fallback returns a plain string and the call site never sees this exception.
            _capture_marker_attempt_failure(
                exc,
                block_index=block_index,
                attempt=attempt,
                max_attempts=max_retries,
                stage="attempt",
                target_chars=len(target_text),
            )
            should_retry = attempt < max_retries and (
                is_retryable_error(exc)
                or _is_retryable_empty_generation_error(exc)
                or _is_retryable_marker_validation_error(exc)
                or _is_retryable_context_leakage_error(exc)
                or _is_non_completed_response_error(exc)
            )
            if not should_retry:
                break
            record_retry_attempt(
                reason=_classify_retry_reason(exc),
                paragraph_count=block_paragraph_count,
                first_retry_for_block=not block_was_retried,
            )
            block_was_retried = True
            if _is_incomplete_response_error(exc):
                request_kwargs = _boost_request_output_budget(
                    request_kwargs,
                    minimum_tokens=_INCOMPLETE_RESPONSE_RETRY_MIN_OUTPUT_TOKENS,
                )
            if _is_retryable_context_leakage_error(exc):
                request_kwargs = _inject_context_leakage_retry_warning(request_kwargs)
            time.sleep(min(2 ** (attempt - 1), 8))

    if last_exception is not None and (
        _is_retryable_empty_generation_error(last_exception)
        or _is_retryable_marker_validation_error(last_exception)
    ):
        _raise_if_stop_requested(should_stop)
        record_retry_attempt(
            reason="recovery_after_exhausted_retries",
            paragraph_count=block_paragraph_count,
            first_retry_for_block=not block_was_retried,
        )
        block_was_retried = True
        try:
            return _recover_from_persistent_empty_response(
                client=client,
                model=model,
                system_prompt=system_prompt,
                target_text=target_text,
                expected_paragraph_ids=expected_paragraph_ids,
                marker_mode=marker_mode,
                minimum_output_tokens=(
                    _INCOMPLETE_RESPONSE_RECOVERY_MIN_OUTPUT_TOKENS
                    if _is_incomplete_response_error(last_exception)
                    else None
                ),
                last_exception=last_exception,
                allow_merge_repair=not allow_controlled_source_fallback,
                should_stop=should_stop,
                detect_short_source_absorption=detect_short_source_absorption,
            )
        except Exception as recovery_exc:
            # The recovery call is the LAST answer the model gives for this block, and the
            # one whose rejection sends the block's own English source into the artifact.
            # It is the single most valuable attempt to have on disk.
            _capture_marker_attempt_failure(
                recovery_exc,
                block_index=block_index,
                attempt=max_retries + 1,
                max_attempts=max_retries + 1,
                stage="recovery",
                target_chars=len(target_text),
            )
            # Steps 2 and 3 of the ladder stand HERE, ahead of every controlled fallback:
            # substituting the source is the last resort, not the first answer to a
            # rejection. ``None`` leaves each branch below exactly as it was.
            ladder_result = _attempt_degradation_ladder(
                _ladder_exception_for_block(recovery_exc, last_exception, marker_mode=marker_mode),
                client=client,
                model=model,
                system_prompt=system_prompt,
                max_retries=max_retries,
                block_index=block_index,
                marker_mode=marker_mode,
                expected_paragraph_ids=expected_paragraph_ids,
                source_paragraph_chunks=source_paragraph_chunks,
                target_text_for_leakage=target_text_for_leakage,
                context_before=context_before_text,
                context_after=context_after_text,
                allow_controlled_source_fallback=allow_controlled_source_fallback,
                should_stop=should_stop,
                detect_short_source_absorption=detect_short_source_absorption,
            )
            if ladder_result is not None:
                return ladder_result
            if not allow_controlled_source_fallback:
                raise recovery_exc
            # A merge the ladder could not rescue falls back to the PAIR, not the block:
            # the two paragraphs get their source, every other paragraph keeps the model's
            # own answer. Shipping the whole block's source here would make a failed ladder
            # cost more source-language text than having no ladder at all. The recovery
            # call's answer is preferred; if IT failed some other way, the last attempt's
            # merged answer is still the one the block shipped before the ladder could see
            # merges, so it is used rather than dropping to the whole-block fallback.
            for merged_exc in (recovery_exc, last_exception):
                merged_pair_repair = _merged_pair_repair_fallback(
                    merged_exc,
                    expected_paragraph_ids=expected_paragraph_ids,
                    source_paragraph_chunks=source_paragraph_chunks,
                    marker_mode=marker_mode,
                    target_text_for_leakage=target_text_for_leakage,
                    context_before=context_before_text,
                    context_after=context_after_text,
                    detect_short_source_absorption=detect_short_source_absorption,
                )
                if merged_pair_repair is not None:
                    return merged_pair_repair
            if _is_incomplete_response_error(recovery_exc) and _can_fallback_to_source_text_after_incomplete_response(target_text):
                record_model_output_discarded(reason="incomplete_response_source_fallback", block_count=1)
                log_event(
                    logging.WARNING,
                    "markdown_incomplete_response_source_fallback",
                    "Recovery для блока снова завершился incomplete_response; сохраняю исходный текст блока как controlled fallback.",
                    model=model,
                    target_chars=len(target_text_for_leakage),
                    marker_mode=marker_mode,
                )
                return _block_source_fallback_result(
                    target_text_for_leakage,
                    expected_paragraph_ids=expected_paragraph_ids,
                    source_paragraph_chunks=source_paragraph_chunks,
                    marker_mode=marker_mode,
                )
            if _is_retryable_marker_validation_error(recovery_exc) and _can_fallback_to_source_text_after_marker_validation_failure(
                target_text_for_leakage,
                marker_mode=marker_mode,
            ):
                record_model_output_discarded(reason="marker_validation_source_fallback", block_count=1)
                log_event(
                    logging.WARNING,
                    "markdown_marker_validation_source_fallback",
                    "Recovery для блока снова завершился marker validation error; сохраняю исходный текст блока как controlled fallback.",
                    model=model,
                    target_chars=len(target_text_for_leakage),
                    marker_mode=marker_mode,
                    marker_error=str(recovery_exc),
                )
                return _block_source_fallback_result(
                    target_text_for_leakage,
                    expected_paragraph_ids=expected_paragraph_ids,
                    source_paragraph_chunks=source_paragraph_chunks,
                    marker_mode=marker_mode,
                )
            # ``collapsed_output`` lands here too (FR-012): an answer that was an empty code
            # fence is as untranslated as no answer, and until the classes were types it
            # escaped this branch and took the run down instead.
            if _is_empty_or_collapsed_response_error(recovery_exc) and _can_fallback_to_source_text_after_empty_response(
                target_text
            ):
                record_model_output_discarded(reason="empty_response_source_fallback", block_count=1)
                log_event(
                    logging.WARNING,
                    "markdown_empty_response_source_fallback",
                    "Recovery для блока снова завершился empty_response; сохраняю исходный текст блока как controlled fallback.",
                    model=model,
                    target_chars=len(target_text_for_leakage),
                    marker_mode=marker_mode,
                    recovery_error=str(recovery_exc),
                )
                return _block_source_fallback_result(
                    target_text_for_leakage,
                    expected_paragraph_ids=expected_paragraph_ids,
                    source_paragraph_chunks=source_paragraph_chunks,
                    marker_mode=marker_mode,
                )
            # A recovery call the provider failed or cancelled (``NonCompletedResponse``)
            # after the attempts were spent on another class — e.g. ``incomplete_response``
            # three times, then ``status="failed"``. The branch below the ``try`` keys on
            # ``last_exception`` and cannot see this one, so without this line the run died
            # after the blocks it had already paid for.
            if _is_non_completed_response_error(recovery_exc) and _can_fallback_to_source_text_after_non_completed_response(
                target_text
            ):
                return _non_completed_response_source_fallback(
                    target_text_for_leakage,
                    model=model,
                    expected_paragraph_ids=expected_paragraph_ids,
                    source_paragraph_chunks=source_paragraph_chunks,
                    marker_mode=marker_mode,
                )
            if _is_retryable_empty_generation_error(recovery_exc) or _is_retryable_marker_validation_error(recovery_exc):
                raise recovery_exc
            raise recovery_exc

    if (
        last_exception is not None
        and allow_controlled_source_fallback
        and _is_non_completed_response_error(last_exception)
        and _can_fallback_to_source_text_after_non_completed_response(target_text)
    ):
        return _non_completed_response_source_fallback(
            target_text_for_leakage,
            model=model,
            expected_paragraph_ids=expected_paragraph_ids,
            source_paragraph_chunks=source_paragraph_chunks,
            marker_mode=marker_mode,
        )

    if last_exception is not None:
        raise last_exception

    raise RuntimeError("Не удалось получить ответ модели.")


_THEME_RELATIONSHIP_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
)
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def convert_markdown_to_docx_bytes(
    markdown_text: str,
    *,
    body_font: str | None = None,
    heading_font: str | None = None,
) -> bytes:
    """Convert *markdown_text* to DOCX bytes via Pandoc.

    *body_font* and *heading_font* are optional overrides for the reference
    document. Body-facing styles are updated directly because python-docx writes
    them as explicit ``w:rFonts`` values; heading styles additionally require a
    theme patch because Word gives ``w:asciiTheme=majorHAnsi`` precedence over
    the direct font name. When both are ``None`` (the default) the python-docx
    built-in theme is left unchanged.
    """
    ensure_pandoc_available()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markdown_path = temp_path / "result.md"
            docx_path = temp_path / "result.docx"
            reference_docx_path = temp_path / "reference.docx"
            markdown_path.write_text(_preprocess_markdown_for_docx(markdown_text), encoding="utf-8")
            _build_reference_docx(reference_docx_path, body_font=body_font, heading_font=heading_font)
            pypandoc.convert_file(
                str(markdown_path),
                to="docx",
                format="markdown+raw_html+superscript+subscript",
                outputfile=str(docx_path),
                extra_args=[f"--reference-doc={reference_docx_path}"],
            )
            return docx_path.read_bytes()
    except Exception as exc:
        raise RuntimeError(f"Ошибка при сборке DOCX: {exc}") from exc


def _preprocess_markdown_for_docx(markdown_text: str) -> str:
    """Convert extractor-emitted inline HTML into Pandoc-friendly markdown.

    The extraction layer preserves semantic inline signals as HTML-like tags
    such as ``<sup>``, ``<sub>``, ``<u>``, and ``<br/>``. Pandoc's DOCX writer does
    not preserve those shapes reliably through the default markdown path, so we
    translate them into markdown extensions that round-trip into OOXML.
    """
    # Underline runs FIRST. Its escaping must not see the backslashes that
    # _escape_pandoc_script_spaces injects for ^…^/~…~: doubling those would turn
    # the escaped space into a literal backslash and demote the script role.
    # Nested tags survive because ``<sup>``/``<sub>``/``<br/>`` carry no span
    # metacharacters, so the later passes still rewrite them inside the span.
    processed = _INLINE_HTML_UNDERLINE_PATTERN.sub(_render_pandoc_underline_span, markdown_text)
    processed = _INLINE_HTML_SUP_PATTERN.sub(
        lambda match: f"^{_escape_pandoc_script_spaces(match.group(1))}^", processed
    )
    processed = _INLINE_HTML_SUB_PATTERN.sub(
        lambda match: f"~{_escape_pandoc_script_spaces(match.group(1))}~", processed
    )
    processed = _INLINE_HTML_BREAK_PATTERN.sub("\\\n", processed)
    return processed


def _render_pandoc_underline_span(match: "re.Match[str]") -> str:
    """Wrap underlined content into Pandoc's ``[…]{.underline}`` span, escaped.

    The span delimiters are markdown syntax, so unescaped ``[``/``]``/``\\`` in
    the *content* terminate or escape them early and the construct collapses:
    an underlined run reading ``1]`` (DOCX splits runs anywhere, so a trailing
    footnote bracket easily lands in its own underlined run) produced
    ``[1]]{.underline}`` and the reader saw the literal markup in the delivered
    text. Escaping keeps the characters as body text and the underline as a role.
    """
    prefix = _neutralize_pandoc_span_prefix(match.group("prefix"))
    content = _PANDOC_SPAN_SPECIAL_PATTERN.sub(lambda special: f"\\{special.group(0)}", match.group("content"))
    return f"{prefix}[{content}]{{.underline}}"


def _neutralize_pandoc_span_prefix(prefix: str) -> str:
    """Stop the character in front of the span from consuming its opening ``[``.

    ``!`` immediately before ``[`` starts Pandoc's image syntax and an odd run of
    backslashes escapes the bracket outright; either way the span degrades to
    literal ``[…]{.underline}`` in the document. Both are neutralized without
    changing the text the reader sees.
    """
    if prefix.endswith("!"):
        backslashes = prefix[:-1]
        if len(backslashes) % 2 == 1:
            # Already escaped by the preceding backslash: cannot open an image.
            return prefix
        return f"{backslashes}\\!"
    if len(prefix) % 2 == 1:
        return f"{prefix}\\"
    return prefix


def _escape_pandoc_script_spaces(content: str) -> str:
    """Escape spaces so ``^…^`` / ``~…~`` stay real superscript/subscript.

    Pandoc's superscript and subscript may not contain unescaped spaces, so
    ``<sup>note 1</sup>`` would otherwise translate into a literal ``^note 1^``
    that reaches the reader as raw carets. Escaping keeps the vertical-alignment
    role; leaving such content untranslated keeps the text but silently demotes
    it to ordinary body text. The escaped space arrives in OOXML as a
    non-breaking space, which is the accepted cost of preserving the role.
    """
    return content.replace(" ", "\\ ")


def _patch_reference_theme_fonts(
    reference_document: "DocxDocument",
    *,
    body_font: str | None,
    heading_font: str | None,
) -> None:
    """Overwrite the major/minor font slots in the reference document's theme.

    Word resolves ``w:asciiTheme="majorHAnsi"`` (used by all built-in Heading
    styles) and ``w:asciiTheme="minorHAnsi"`` (body/list/caption) by looking
    up the document's embedded ``theme1.xml``.  python-docx's default template
    maps those slots to Calibri (major) and Cambria (minor).

    Patching the theme here means every ``w:asciiTheme`` reference in every
    style automatically picks up the configured font **without** touching
    individual style ``w:rFonts`` elements — this is the OOXML-idiomatic
    approach and the only reliable way to override heading fonts given that
    python-docx's ``Style.font.name`` setter leaves ``w:asciiTheme`` intact.

    Called only when at least one font is configured; both arguments may be
    ``None`` to skip their respective slot.
    """
    try:
        theme_part = reference_document.part.part_related_by(_THEME_RELATIONSHIP_TYPE)
    except KeyError:
        return  # Template has no theme part — nothing to patch.

    root = etree.fromstring(theme_part.blob)

    if heading_font is not None:
        for el in root.findall(f".//{{{_DRAWINGML_NS}}}majorFont/{{{_DRAWINGML_NS}}}latin"):
            el.set("typeface", heading_font)

    if body_font is not None:
        for el in root.findall(f".//{{{_DRAWINGML_NS}}}minorFont/{{{_DRAWINGML_NS}}}latin"):
            el.set("typeface", body_font)

    theme_part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _build_reference_docx(
    reference_docx_path: Path,
    *,
    body_font: str | None = None,
    heading_font: str | None = None,
) -> None:
    reference_document = Document()
    styles = reference_document.styles

    body_baseline = {
        "font_name": body_font,
        "font_size": 11,
        "space_after": 8,
        "line_spacing": 1.15,
    }

    _configure_paragraph_style(styles["Normal"], **body_baseline)

    if "Body Text" in styles:
        _configure_paragraph_style(styles["Body Text"], **body_baseline)

    heading_specs = (
        ("Heading 1", 18, 18, 8),
        ("Heading 2", 16, 16, 7),
        ("Heading 3", 14, 14, 6),
        ("Heading 4", 13, 12, 5),
        ("Heading 5", 12, 10, 4),
        ("Heading 6", 11, 8, 3),
    )
    for style_name, font_size, space_before, space_after in heading_specs:
        if style_name not in styles:
            continue
        _configure_paragraph_style(
            styles[style_name],
            font_name=heading_font,
            font_size=font_size,
            bold=True,
            space_before=space_before,
            space_after=space_after,
            line_spacing=1.1,
            keep_with_next=True,
        )

    if "Caption" in styles:
        _configure_paragraph_style(
            styles["Caption"],
            font_name=body_font,
            font_size=10,
            italic=True,
            space_before=4,
            space_after=10,
            alignment=WD_ALIGN_PARAGRAPH.CENTER,
        )

    if "List Paragraph" in styles:
        _configure_paragraph_style(
            styles["List Paragraph"],
            font_name=body_font,
            font_size=11,
            space_before=0,
            space_after=4,
            line_spacing=1.1,
        )

    if "Table Grid" in styles:
        table_grid_style = cast(Any, styles["Table Grid"])
        if body_font is not None:
            table_grid_style.font.name = body_font
        table_grid_style.font.size = Pt(10)

    _ensure_reference_numbering_definitions(reference_document, body_font=body_font)

    # Patch theme fonts only when explicitly configured. This is required for
    # heading styles, whose built-in w:asciiTheme bindings outrank the direct
    # font name, and keeps theme-bound fallback slots aligned with explicit
    # style overrides.
    if body_font is not None or heading_font is not None:
        _patch_reference_theme_fonts(reference_document, body_font=body_font, heading_font=heading_font)

    reference_document.save(str(reference_docx_path))


def _ensure_reference_numbering_definitions(
    reference_document: "DocxDocument",
    *,
    body_font: str | None = None,
) -> None:
    numbering_part = reference_document.part.numbering_part
    numbering = numbering_part.element
    baseline_specs = (
        {
            "num_fmt": "decimal",
            "level_text_patterns": ("%1.", "%1.%2.", "%1.%2.%3."),
        },
        {
            "num_fmt": "bullet",
            "level_text_patterns": (chr(0x2022), chr(0x25E6), chr(0x25AA)),
        },
    )

    for spec in baseline_specs:
        baseline_abstract_num = _find_reference_baseline_abstract_num(
            numbering,
            num_fmt=spec["num_fmt"],
            level_text_patterns=spec["level_text_patterns"],
            body_font=body_font,
        )
        if baseline_abstract_num is None:
            abstract_num_id = _next_numbering_id(numbering, "w:abstractNum", "abstractNumId")
            _append_multilevel_numbering_definition(
                numbering,
                abstract_num_id=abstract_num_id,
                num_fmt=spec["num_fmt"],
                level_text_patterns=spec["level_text_patterns"],
                body_font=body_font,
            )
            baseline_abstract_num = _find_abstract_num_by_id(numbering, abstract_num_id)
            if baseline_abstract_num is None:
                raise RuntimeError("Не удалось создать baseline numbering definition.")

        abstract_num_id = int(baseline_abstract_num.get(qn("w:abstractNumId")))
        if not _num_instance_exists(numbering, abstract_num_id=abstract_num_id):
            num_id = _next_numbering_id(numbering, "w:num", "numId")
            _append_num_instance(numbering, num_id=num_id, abstract_num_id=abstract_num_id)


def _find_reference_baseline_abstract_num(
    numbering,
    *,
    num_fmt: str,
    level_text_patterns: tuple[str, ...],
    body_font: str | None,
):
    for abstract_num in numbering.xpath('./*[local-name()="abstractNum"]'):
        if _abstract_num_matches_reference_baseline(
            abstract_num,
            num_fmt=num_fmt,
            level_text_patterns=level_text_patterns,
            body_font=body_font,
        ):
            return abstract_num
    return None


def _find_abstract_num_by_id(numbering, abstract_num_id: int):
    matches = numbering.xpath(
        f'./*[local-name()="abstractNum" and @*[local-name()="abstractNumId"]="{abstract_num_id}"]'
    )
    return matches[0] if matches else None


def _iter_num_instances(numbering):
    return numbering.xpath('./*[local-name()="num"]')


def _num_instance_abstract_num_id(num_instance) -> str | None:
    abstract_num_id_values = num_instance.xpath(
        './*[local-name()="abstractNumId"]/@*[local-name()="val"]'
    )
    if not abstract_num_id_values:
        return None
    return str(abstract_num_id_values[0])


def _abstract_num_matches_reference_baseline(
    abstract_num,
    *,
    num_fmt: str,
    level_text_patterns: tuple[str, ...],
    body_font: str | None,
) -> bool:
    levels = abstract_num.xpath('./*[local-name()="lvl"]')
    if len(levels) != len(level_text_patterns):
        return False

    for ilvl, level_text in enumerate(level_text_patterns):
        level_matches = [level for level in levels if level.get(qn("w:ilvl")) == str(ilvl)]
        if len(level_matches) != 1:
            return False
        if not _level_matches_reference_baseline(
            level_matches[0],
            num_fmt=num_fmt,
            level_text=level_text,
            ilvl=ilvl,
            body_font=body_font,
        ):
            return False
    return True


def _level_matches_reference_baseline(
    level,
    *,
    num_fmt: str,
    level_text: str,
    ilvl: int,
    body_font: str | None,
) -> bool:
    num_fmt_values = level.xpath('./*[local-name()="numFmt"]/@*[local-name()="val"]')
    level_text_values = level.xpath('./*[local-name()="lvlText"]/@*[local-name()="val"]')
    left_values = level.xpath('./*[local-name()="pPr"]/*[local-name()="ind"]/@*[local-name()="left"]')
    hanging_values = level.xpath('./*[local-name()="pPr"]/*[local-name()="ind"]/@*[local-name()="hanging"]')
    after_values = level.xpath('./*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="after"]')
    line_values = level.xpath('./*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="line"]')
    line_rule_values = level.xpath('./*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="lineRule"]')
    ascii_fonts = level.xpath('./*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="ascii"]')
    hansi_fonts = level.xpath('./*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="hAnsi"]')
    cs_fonts = level.xpath('./*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="cs"]')

    expected_fonts = [] if body_font is None else [body_font]

    return (
        num_fmt_values == [num_fmt]
        and level_text_values == [level_text]
        and left_values == [str(720 + (ilvl * 360))]
        and hanging_values == ["360"]
        and after_values == ["80"]
        and line_values == ["264"]
        and line_rule_values == ["auto"]
        and ascii_fonts == expected_fonts
        and hansi_fonts == expected_fonts
        and cs_fonts == expected_fonts
    )


def _num_instance_exists(numbering, *, abstract_num_id: int) -> bool:
    expected_abstract_num_id = str(abstract_num_id)
    return any(
        _num_instance_abstract_num_id(num_instance) == expected_abstract_num_id
        for num_instance in _iter_num_instances(numbering)
    )


def _next_numbering_id(numbering, element_name: str, attr_name: str) -> int:
    existing_ids = []
    local_name = element_name.split(":", 1)[1]
    for element in numbering.xpath(f'./*[local-name()="{local_name}"]'):
        value = element.get(qn(f"w:{attr_name}"))
        if value is not None:
            existing_ids.append(int(value))
    return (max(existing_ids) + 1) if existing_ids else 0


def _append_multilevel_numbering_definition(
    numbering,
    *,
    abstract_num_id: int,
    num_fmt: str,
    level_text_patterns: tuple[str, str, str],
    body_font: str | None,
) -> None:
    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), str(abstract_num_id))

    nsid = OxmlElement("w:nsid")
    nsid.set(qn("w:val"), f"{abstract_num_id + 1:08X}")
    abstract_num.append(nsid)

    multi_level_type = OxmlElement("w:multiLevelType")
    multi_level_type.set(qn("w:val"), "multilevel")
    abstract_num.append(multi_level_type)

    template_code = OxmlElement("w:tmpl")
    template_code.set(qn("w:val"), f"{abstract_num_id + 257:08X}")
    abstract_num.append(template_code)

    for ilvl, level_text in enumerate(level_text_patterns):
        abstract_num.append(
            _build_numbering_level(
                ilvl=ilvl,
                num_fmt=num_fmt,
                level_text=level_text,
                body_font=body_font,
            )
        )

    numbering.append(abstract_num)


def _build_numbering_level(*, ilvl: int, num_fmt: str, level_text: str, body_font: str | None):
    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), str(ilvl))

    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    level.append(start)

    num_fmt_element = OxmlElement("w:numFmt")
    num_fmt_element.set(qn("w:val"), num_fmt)
    level.append(num_fmt_element)

    level_text_element = OxmlElement("w:lvlText")
    level_text_element.set(qn("w:val"), level_text)
    level.append(level_text_element)

    level_jc = OxmlElement("w:lvlJc")
    level_jc.set(qn("w:val"), "left")
    level.append(level_jc)

    paragraph_properties = OxmlElement("w:pPr")
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), str(720 + (ilvl * 360)))
    ind.set(qn("w:hanging"), "360")
    paragraph_properties.append(ind)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "80")
    spacing.set(qn("w:line"), "264")
    spacing.set(qn("w:lineRule"), "auto")
    paragraph_properties.append(spacing)
    level.append(paragraph_properties)

    if body_font is not None:
        run_properties = OxmlElement("w:rPr")
        run_fonts = OxmlElement("w:rFonts")
        run_fonts.set(qn("w:ascii"), body_font)
        run_fonts.set(qn("w:hAnsi"), body_font)
        run_fonts.set(qn("w:cs"), body_font)
        run_properties.append(run_fonts)
        level.append(run_properties)

    return level


def _append_num_instance(numbering, *, num_id: int, abstract_num_id: int) -> None:
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_num_id_element = OxmlElement("w:abstractNumId")
    abstract_num_id_element.set(qn("w:val"), str(abstract_num_id))
    num.append(abstract_num_id_element)
    numbering.append(num)


def _configure_paragraph_style(
    style,
    *,
    font_name: str | None,
    font_size: int,
    bold: bool | None = None,
    italic: bool | None = None,
    space_before: int | None = None,
    space_after: int | None = None,
    line_spacing: float | None = None,
    keep_with_next: bool | None = None,
    alignment=None,
) -> None:
    if font_name is not None:
        style.font.name = font_name
    style.font.size = Pt(font_size)
    if bold is not None:
        style.font.bold = bold
    if italic is not None:
        style.font.italic = italic

    paragraph_format = style.paragraph_format
    if space_before is not None:
        paragraph_format.space_before = Pt(space_before)
    if space_after is not None:
        paragraph_format.space_after = Pt(space_after)
    if line_spacing is not None:
        paragraph_format.line_spacing = line_spacing
    if keep_with_next is not None:
        paragraph_format.keep_with_next = keep_with_next
    if alignment is not None:
        paragraph_format.alignment = alignment


def build_output_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.docx"


def build_markdown_filename(filename: str) -> str:
    return f"{Path(filename).stem}_edited.md"
