"""Spec 063 FR-005 / FR-006: a footnote reference the import recognised survives the model.

Since ``6cb7a6e`` the PDF import renders a footnote reference as Unicode superscript digits
(``pdf_import/text_layer_quality.py``), so the reference reaches the model inside the
prose — "…for the first time in history.¹²". Measured on the four translated corpus books
of 2026-11-07, the model dropped 8/5/22/26 of them, and nothing in the pipeline noticed: no
prompt mentioned them and no check compared them.

This module is that comparison. After a block is generated and accepted, the multiset of
superscript-digit runs in each paragraph's SOURCE is compared with the same multiset in its
translation. A reference the translation lost is put back — at the end of the sentence with
the same ordinal when the translation kept the source's sentence count, at the end of the
paragraph otherwise — and counted. One measured exception comes first: the model often KEEPS
a reference but writes it in plain digits welded to the word ("контракты»34." for
"contracts.”³⁴" — 11 of the 61 losses on the four books); those digits are turned back into
the glyph where they stand, because inserting one would print the reference twice. A loss
is never a block failure: the translation is good text missing one glyph, and rejecting it
would cost the whole block for that glyph.

What the module deliberately does NOT do:

* It compares only glyphs present in the SOURCE. A superscript the translation introduced on
  its own ("м²" for "m2") is not a reference that was lost, and is never touched.
* It never removes anything, never reorders anything already in the translation, and never
  edits a paragraph whose references all survived — that paragraph comes back unchanged
  (the anti-vacuum half of FR-005).
* It reads no list of words and no book: the marker is a typographic form, a sentence end is
  terminal punctuation followed by space and a capital (Constitution VII).
* It does not run for the narration operation, whose prompt orders footnote markers REMOVED
  (``resources/prompts/operation_audiobook.txt``, rule 1). Restoring them there would undo
  the operation's own contract.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from docxaicorrector.core.model_accounting import record_footnote_markers
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    MarkerPreservedBlockText,
    MarkerValidationError,
    ParagraphDisposition,
    marker_paragraph_dispositions,
    split_marker_preserved_paragraph_dispositions,
)


# Exactly the glyphs ``text_layer_quality._SUPERSCRIPT_DIGIT_TABLE`` writes. One maximal run
# is one reference: "¹²" is reference twelve, not references one and two.
SUPERSCRIPT_MARKER_PATTERN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+")
_SUPERSCRIPT_DIGITS = frozenset("⁰¹²³⁴⁵⁶⁷⁸⁹")
# A sentence ends at terminal punctuation, optionally followed by closing quotes, brackets,
# Markdown emphasis and the references that annotate it, then by whitespace and the start of
# the next sentence — a capital letter or a digit, possibly behind opening quotes, brackets,
# emphasis or a dash — or by the end of the paragraph. The capital is what keeps "U.S.
# college" one sentence. An abbreviation followed by a capital ("Mr. Smith") still splits;
# that only ever changes the COUNT, and a count that differs from the source's sends the
# reference to the end of the paragraph instead — the safe direction.
_SENTENCE_END_PATTERN = re.compile(r"[.!?…]+[\"'»”’)\]*_]*[⁰¹²³⁴⁵⁶⁷⁸⁹]*(?=\s|$)")
_SENTENCE_OPENERS = "«\"“‘'([*_—–-"

# Separates a restored reference from one already standing where it goes, so "¹²" and "³"
# stay two references rather than reading as "¹²³".
_ADJACENT_MARKER_SEPARATOR = ","

PLACEMENT_SENTENCE = "sentence"
PLACEMENT_PARAGRAPH_END = "paragraph_end"
PLACEMENT_CONVERTED = "converted_plain_digits"
_SUPERSCRIPT_TO_ASCII = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
NARRATION_OPERATION = "audiobook"


def superscript_markers(text: str) -> list[str]:
    """Every reference in ``text``, in reading order."""
    return SUPERSCRIPT_MARKER_PATTERN.findall(text or "")


def _starts_sentence(text: str, position: int) -> bool:
    """True when the text from ``position`` opens a sentence (or there is nothing left)."""
    rest = text[position:].lstrip()
    rest = rest.lstrip(_SENTENCE_OPENERS).lstrip()
    return not rest or rest[0].isupper() or rest[0].isdigit()


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` of each sentence; ``end`` is just past its terminal group."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END_PATTERN.finditer(text):
        end = match.end()
        if not _starts_sentence(text, end):
            continue
        if text[start:end].strip():
            spans.append((start, end))
        start = end
    tail = text[start:].rstrip()
    if tail.strip():
        spans.append((start, start + len(tail)))
    return spans


def _sentence_ordinal(spans: Sequence[tuple[int, int]], position: int) -> int:
    for ordinal, (start, end) in enumerate(spans):
        if start <= position < end:
            return ordinal
    return len(spans) - 1


def _markers_by_sentence(text: str, spans: Sequence[tuple[int, int]]) -> list[list[str]]:
    by_sentence: list[list[str]] = [[] for _ in spans]
    if not spans:
        return by_sentence
    for match in SUPERSCRIPT_MARKER_PATTERN.finditer(text):
        by_sentence[_sentence_ordinal(spans, match.start())].append(match.group(0))
    return by_sentence


def _insert_at(text: str, position: int, markers: Sequence[str]) -> str:
    pieces: list[str] = []
    previous = text[position - 1] if position > 0 else ""
    for marker in markers:
        if previous in _SUPERSCRIPT_DIGITS:
            pieces.append(_ADJACENT_MARKER_SEPARATOR)
        pieces.append(marker)
        previous = marker[-1]
    following = text[position] if position < len(text) else ""
    if following in _SUPERSCRIPT_DIGITS:
        pieces.append(_ADJACENT_MARKER_SEPARATOR)
    return text[:position] + "".join(pieces) + text[position:]


@dataclass(frozen=True)
class ParagraphMarkerOutcome:
    """What the check found in ONE paragraph, and what it did."""

    text: str
    source_marker_count: int
    kept_marker_count: int
    restored_markers: tuple[str, ...] = ()
    placement: str = ""


def restore_lost_footnote_markers(source_text: str, translated_text: str) -> ParagraphMarkerOutcome:
    """Put back the references ``translated_text`` lost from ``source_text``.

    The comparison is a multiset, so a reference the model MOVED to another sentence is
    kept, not restored a second time.
    """
    source_markers = superscript_markers(source_text)
    if not source_markers:
        return ParagraphMarkerOutcome(text=translated_text, source_marker_count=0, kept_marker_count=0)
    translated_counter = Counter(superscript_markers(translated_text))
    missing = Counter(source_markers) - translated_counter
    kept_count = len(source_markers) - sum(missing.values())
    if not missing:
        return ParagraphMarkerOutcome(
            text=translated_text,
            source_marker_count=len(source_markers),
            kept_marker_count=kept_count,
        )

    # First, a reference the model KEPT but wrote in plain digits: "контракты»34." for
    # "contracts.”³⁴". Inserting a glyph there would print the reference twice, so the
    # digits are turned back into the glyph where they stand.
    restored: list[str] = []
    placements: list[str] = []
    for marker in source_markers:
        if missing[marker] <= 0:
            continue
        converted = _convert_welded_plain_digits(translated_text, source_text, marker)
        if converted is not None:
            translated_text = converted
            missing[marker] -= 1
            restored.append(marker)
            if PLACEMENT_CONVERTED not in placements:
                placements.append(PLACEMENT_CONVERTED)

    insertions: dict[int, list[str]] = {}
    source_spans = _sentence_spans(source_text)
    translated_spans = _sentence_spans(translated_text)
    if sum(missing.values()) and source_spans and len(source_spans) == len(translated_spans):
        source_by_sentence = _markers_by_sentence(source_text, source_spans)
        translated_by_sentence = _markers_by_sentence(translated_text, translated_spans)
        for ordinal, sentence_markers in enumerate(source_by_sentence):
            lost_here = Counter(sentence_markers) - Counter(translated_by_sentence[ordinal])
            for marker in sentence_markers:
                if lost_here[marker] > 0 and missing[marker] > 0:
                    lost_here[marker] -= 1
                    missing[marker] -= 1
                    insertions.setdefault(translated_spans[ordinal][1], []).append(marker)
                    restored.append(marker)
                    if PLACEMENT_SENTENCE not in placements:
                        placements.append(PLACEMENT_SENTENCE)
    # Whatever the per-sentence reading could not place — a different sentence count, or a
    # reference the model moved within the paragraph while dropping another — goes to the
    # end of the paragraph, in source order.
    leftovers: list[str] = []
    for marker in source_markers:
        if missing[marker] > 0:
            missing[marker] -= 1
            leftovers.append(marker)
    if leftovers:
        insertions.setdefault(len(translated_text.rstrip()), []).extend(leftovers)
        restored.extend(leftovers)
        placements.append(PLACEMENT_PARAGRAPH_END)

    text = translated_text
    for position in sorted(insertions, reverse=True):
        text = _insert_at(text, position, insertions[position])
    return ParagraphMarkerOutcome(
        text=text,
        source_marker_count=len(source_markers),
        kept_marker_count=kept_count,
        restored_markers=tuple(restored),
        placement="+".join(placements),
    )


def _welded_plain_digit_pattern(digits: str) -> re.Pattern[str]:
    """``digits`` as a reference would sit: welded to a word or a closing mark, alone.

    Preceded, with no space, by a letter or one of the closing marks a reference follows;
    not part of a longer number on either side ("2034", "34.5", "34,000").
    """
    return re.compile(
        r"(?<=[^\W\d_]|[.!?:;)\]}»”\"'’*_])" + re.escape(digits) + r"(?![\d]|[.,]\d)"
    )


def _convert_welded_plain_digits(translated_text: str, source_text: str, marker: str) -> str | None:
    """Turn the model's plain-digit copy of ``marker`` back into the glyph, or ``None``.

    Only when the evidence is unambiguous: the translation holds EXACTLY ONE such welded run
    of the marker's digits, and the source holds none of its own — so the run cannot be a
    number the source itself carried that way.
    """
    digits = marker.translate(_SUPERSCRIPT_TO_ASCII)
    pattern = _welded_plain_digit_pattern(digits)
    if pattern.search(source_text):
        return None
    matches = list(pattern.finditer(translated_text))
    if len(matches) != 1:
        return None
    match = matches[0]
    return translated_text[: match.start()] + marker + translated_text[match.end() :]


@dataclass(frozen=True)
class BlockMarkerOutcome:
    processed_chunk: str
    paragraphs: tuple[tuple[str, ParagraphMarkerOutcome], ...]

    @property
    def source_marker_count(self) -> int:
        return sum(outcome.source_marker_count for _, outcome in self.paragraphs)

    @property
    def kept_marker_count(self) -> int:
        return sum(outcome.kept_marker_count for _, outcome in self.paragraphs)

    @property
    def restored_marker_count(self) -> int:
        return sum(len(outcome.restored_markers) for _, outcome in self.paragraphs)


def _source_text_by_paragraph_id(
    source_text_with_markers: str, paragraph_ids: Sequence[str]
) -> dict[str, str] | None:
    try:
        records = split_marker_preserved_paragraph_dispositions(source_text_with_markers, paragraph_ids)
    except MarkerValidationError:
        return None
    return {record.paragraph_id: record.text for record in records}


def restore_block_footnote_markers(
    processed_chunk: str,
    *,
    source_text_with_markers: str,
    paragraph_ids: Sequence[str],
) -> BlockMarkerOutcome:
    """Apply :func:`restore_lost_footnote_markers` to every ACCEPTED paragraph of a block.

    Only a block that carries its per-paragraph record is checked: without it there is no
    paragraph to compare against, and re-splitting text to guess one is what spec 056 E
    removed. ``omitted`` and ``source_restored`` paragraphs ship their source, references
    included, and are not the model's text to repair.
    """
    dispositions = marker_paragraph_dispositions(processed_chunk)
    if dispositions is None:
        return BlockMarkerOutcome(processed_chunk=processed_chunk, paragraphs=())
    source_by_id = _source_text_by_paragraph_id(source_text_with_markers, paragraph_ids)
    if source_by_id is None:
        return BlockMarkerOutcome(processed_chunk=processed_chunk, paragraphs=())

    outcomes: list[tuple[str, ParagraphMarkerOutcome]] = []
    rebuilt: list[ParagraphDisposition] = []
    changed = False
    for disposition in dispositions:
        source_text = source_by_id.get(disposition.paragraph_id)
        if disposition.status != PARAGRAPH_STATUS_ACCEPTED or source_text is None:
            rebuilt.append(disposition)
            continue
        outcome = restore_lost_footnote_markers(source_text, disposition.text)
        if outcome.source_marker_count:
            outcomes.append((disposition.paragraph_id, outcome))
        if outcome.restored_markers:
            changed = True
            rebuilt.append(
                ParagraphDisposition(
                    paragraph_id=disposition.paragraph_id,
                    text=outcome.text,
                    status=disposition.status,
                )
            )
        else:
            rebuilt.append(disposition)
    if not changed:
        return BlockMarkerOutcome(processed_chunk=processed_chunk, paragraphs=tuple(outcomes))
    # Derived from the record, never the other way round — the transport rule of
    # ``MarkerPreservedBlockText``.
    return BlockMarkerOutcome(
        processed_chunk=MarkerPreservedBlockText(
            "\n\n".join(disposition.text for disposition in rebuilt), rebuilt
        ),
        paragraphs=tuple(outcomes),
    )


def preserve_footnote_markers_for_block(
    *,
    processed_chunk: str,
    payload: Any,
    processing_operation: Any,
    block_index: int,
    log_event: Callable[..., Any] | None,
    filename: Any = None,
) -> str:
    """The pipeline's one entry point: check, restore, count, and say so per paragraph."""
    if str(processing_operation or "").strip().casefold() == NARRATION_OPERATION:
        return processed_chunk
    paragraph_ids = getattr(payload, "paragraph_ids", None)
    if not isinstance(paragraph_ids, list) or not paragraph_ids:
        return processed_chunk
    outcome = restore_block_footnote_markers(
        processed_chunk,
        source_text_with_markers=str(getattr(payload, "target_text_with_markers", "") or ""),
        paragraph_ids=paragraph_ids,
    )
    if not outcome.paragraphs:
        return processed_chunk
    record_footnote_markers(
        source_count=outcome.source_marker_count,
        kept_count=outcome.kept_marker_count,
        restored_count=outcome.restored_marker_count,
    )
    for paragraph_id, paragraph in outcome.paragraphs:
        if not paragraph.restored_markers or log_event is None:
            continue
        log_event(
            logging.WARNING,
            "footnote_markers_restored",
            "Модель потеряла ссылки на сноски; они восстановлены в переводе абзаца.",
            filename=filename,
            block_index=block_index,
            paragraph_id=paragraph_id,
            restored_markers=list(paragraph.restored_markers),
            source_marker_count=paragraph.source_marker_count,
            placement=paragraph.placement,
        )
    return outcome.processed_chunk
