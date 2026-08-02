"""Count the reader-visible defects in a book before and after the reader-cleanup pass.

Why this exists
---------------
The reader-cleanup report counts OPERATIONS. An owner does not read operations; they read
the book. "39 accepted operations" and "0.09% of characters changed" answer neither "is the
book better" nor "is the book worse", and the pass has previously done both at once.

This stand counts the five defect classes the owner named, in the delivered markdown, with
detectors written to fire on what a person notices when reading — a title welded to the
first sentence, a bullet with nothing after it, a footnote digit stuck to a word, a page
header sitting in the middle of a sentence, a paragraph that stops mid-phrase. It reports
each class before and after, the per-block delta, worked before/after examples, and a
separate harm ledger.

Precision over recall, deliberately. Every detector is written to under-report rather than
to guess: an ALL-CAPS run has to be at least two long words before it counts as a running
header, a footnote digit has to be welded to a letter with no space. The same detector runs
on both sides, so a constant blind spot cancels out of the delta; a loose detector would
not, because the pass changes exactly the kind of text a loose detector guesses about.

What the harm ledger is for
---------------------------
Known real damage from the recorded run: the pass cut the filename out of a WHO citation
(``.../whr00_en.pdf?ua=1`` became ``.../ .pdf?ua=1``). The bibliography is not protected.
So every deletion is diffed at character level and classified: furniture (a page number, a
running header, a duplicated fragment) is the pass doing its job; anything else — a word, a
piece of a URL, a digit inside a citation — is recorded as harm with its full context.

Usage (WSL, repo root)::

    . .venv/bin/activate
    export PYTHONPATH="$PWD/src:$PWD"
    python scripts/measure-reader-cleanup-visible-defects.py \
        --run-dir .run/reader_cleanup_live_run/<timestamp>
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent

DEFECT_CLASSES = (
    "fused_heading",
    "broken_list_item",
    "glued_footnote_marker",
    "inline_page_furniture",
    "broken_sentence",
    # A sixth class, not on the owner's list. It is here because it turned out to be what
    # the pass spends most of one book's operations on: an image anchor sharing a block
    # with its caption, which in the delivered DOCX puts the picture and the caption text
    # in a single paragraph. Reporting only the five named classes would have shown that
    # book as "12 operations, nothing measurably changed".
    "caption_fused_with_image_anchor",
)


# --------------------------------------------------------------------------------------
# Block model
# --------------------------------------------------------------------------------------

def split_blocks(markdown_text: str) -> list[str]:
    """Same segmentation the pass itself uses: blank-line separated blocks."""
    normalized = str(markdown_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    return [part.strip("\n") for part in re.split(r"\n\s*\n+", normalized) if part.strip()]


_IMAGE_ONLY = re.compile(r"^\s*(?:\[\[DOCX_IMAGE_[^\]]+\]\]\s*)+$")
_HEADING_LINE = re.compile(r"^\s{0,3}(#{1,6})\s+(\S.*)$")
_LIST_MARKER = re.compile(r"^\s{0,3}(?:[-*+•–—]|\d{1,3}[.)])\s+")
_BARE_LIST_MARKER = re.compile(r"^\s{0,3}(?:[-*+•]|\d{1,3}[.)])\s*$")
_TABLE_ROW = re.compile(r"^\s*\|")

_CAPS_WORD = r"[А-ЯЁA-Z][А-ЯЁA-Ź]{2,}"
# Two or more consecutive ALL-CAPS words of >=3 letters. Single acronyms (ВВП, НКО, ISBN)
# never match; "ПЕРЕОСМЫСЛЕНИЕ ДЕНЕГ" and "ГЛАВА 1. ЭКОНОМИКА ДОВЕРИЯ" do.
_CAPS_RUN = re.compile(rf"{_CAPS_WORD}(?:[\s.,:]+(?:\d{{1,3}}[.]?\s*)?{_CAPS_WORD}){{1,}}")

_TERMINAL_CHARS = ".!?…:;»\"'”’)»"


def visible_text(block: str) -> str:
    """The block as a reader sees it: one line, no markdown scaffolding, no image anchors."""
    text = re.sub(r"\[\[DOCX_IMAGE_[^\]]+\]\]", " ", block)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)[*_](?=\S)", "", text)
    text = re.sub(r"(?<=\S)[*_](?!\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def is_image_only(block: str) -> bool:
    return bool(_IMAGE_ONLY.match(block.strip()))


def is_list_item(block: str) -> bool:
    return bool(_LIST_MARKER.match(block.strip()))


def is_table(block: str) -> bool:
    return bool(_TABLE_ROW.match(block.strip()))


def is_pure_heading(block: str) -> bool:
    """A markdown heading and nothing else — the shape a fused heading is NOT."""
    lines = [line for line in block.strip().splitlines() if line.strip()]
    return len(lines) == 1 and bool(_HEADING_LINE.match(lines[0]))


# --------------------------------------------------------------------------------------
# Class 1: fused headings
# --------------------------------------------------------------------------------------

def find_fused_headings(blocks: list[str], index: int) -> list[dict[str, str]]:
    """A title welded to a paragraph — the reader cannot tell where the heading ends.

    Reader test: you see something that looks like a heading, and the body text starts
    without a paragraph break. Four shapes, all observed in these books:

    * a ``#`` heading line with prose lines under it *in the same block*;
    * a bold run (``**ПРЕДИСЛОВИЕ**``) followed on the same line by a sentence;
    * an ALL-CAPS title followed on the same line by ordinary sentence case;
    * a ``#`` heading CUT MID-PHRASE, whose remaining words open the next block and are
      themselves welded to that paragraph — ``### РАЗРЫВ МЕЖДУ НАШИМ МЫШЛЕНИЕМ И`` /
      ``ТЕМ, КАК УСТРОЕНА ПРИРОДА. Кооперативные валюты долгое время...``. This one was
      invisible to the first version of the detector and turned out to be the single most
      common shape in the corpus, and the one the pass spends most of its operations on.

    The torn-heading shape is counted ONCE, on the heading block, and the caps-title rule
    is suppressed on the block that carries the tail, so one defect is one count.
    """
    findings: list[dict[str, str]] = []
    block = blocks[index]
    stripped = block.strip()
    if is_image_only(stripped) or is_table(stripped):
        return findings

    lines = [line for line in stripped.splitlines() if line.strip()]

    if is_pure_heading(stripped) and index + 1 < len(blocks):
        heading_text = visible_text(stripped)
        nxt = blocks[index + 1].strip()
        tail = re.match(rf"^\s*({_CAPS_WORD}(?:[\s,:.]+(?:{_CAPS_WORD}|[а-яёa-z]{{1,3}}\b))*)", visible_text(nxt))
        if heading_text and heading_text[-1] not in ".!?" and tail and len(visible_text(nxt)) > len(tail.group(1)) + 30:
            findings.append({"shape": "heading_torn_then_body_fused",
                             "heading": heading_text[:120],
                             "body": visible_text(nxt)[:180]})
            return findings

    # The tail of a torn heading is already counted on the heading block above.
    if index > 0 and is_pure_heading(blocks[index - 1].strip()):
        previous = visible_text(blocks[index - 1])
        if previous and previous[-1] not in ".!?" and re.match(rf"^\s*{_CAPS_WORD}", visible_text(stripped)):
            return findings
    if len(lines) > 1 and _HEADING_LINE.match(lines[0]):
        body = " ".join(lines[1:]).strip()
        if len(visible_text(body)) >= 40:
            findings.append({"shape": "heading_line_with_body_in_same_block",
                             "heading": visible_text(lines[0])[:120],
                             "body": visible_text(body)[:160]})
            return findings

    first_line = visible_text(lines[0]) if lines else ""
    whole = visible_text(stripped)

    # A bold title anywhere in the block with a sentence running straight on from it. Not
    # anchored to the block start on purpose: the worst instance in these books is a title
    # welded into the MIDDLE of the contents block ("... Об авторах 261 **ПРЕДИСЛОВИЕ**
    # Джон Перкинс, автор книги ...").
    bold = re.search(r"\*{2}([^*\n]{3,120})\*{2}[ \t]*(\S[^\n]{30,})", stripped)
    if bold and not bold.group(2).lstrip().startswith("**"):
        findings.append({"shape": "bold_title_then_sentence",
                         "heading": bold.group(1).strip()[:120],
                         "body": visible_text(bold.group(2))[:160]})
        return findings

    # ALL-CAPS opener followed by sentence case on the same line. The opener must end
    # before a lowercase word starts; that transition is the thing the eye catches.
    # Single-letter Cyrillic prepositions ("С", "И", "В") are allowed INSIDE the caps run:
    # without them "СОЗДАНИЕ БОГАТСТВА ... С ПОМОЩЬЮ ЛОКАЛЬНЫХ ВАЛЮТ Гвендолин Холлсмит и
    # Бернар Лиетар" — a title with the authors welded on — did not match at all.
    # The trailing ``[?!.]?`` is not cosmetic. Without it every question- or
    # exclamation-titled section was invisible: "ЧТО ТАКОЕ СТОИМОСТЬ? Стоимость можно
    # определить..." and "ОТКУДА БЕРУТСЯ ИННОВАЦИИ? Прежде чем..." are fused headings that
    # the pass fixes, and the first version of this detector scored that book "0 better".
    caps_open = re.match(
        rf"^\s*((?:{_CAPS_WORD}|\d{{1,3}}[.)]?)(?:[\s.,:]+(?:{_CAPS_WORD}|\d{{1,3}}[.)]?|[А-ЯЁA-Z]\b)){{1,14}}[?!.]?)"
        rf"\s+([А-ЯЁA-Z][а-яёa-z].{{20,}})$",
        first_line,
    )
    if caps_open and len(caps_open.group(1)) <= 120 and re.search(_CAPS_WORD, caps_open.group(1)):
        findings.append({"shape": "caps_title_then_sentence",
                         "heading": caps_open.group(1).strip()[:120],
                         "body": caps_open.group(2)[:160]})
        return findings

    # "Глава 7. Заголовок Первое предложение..." — chapter opener welded to the body.
    chapter = re.match(
        r"^\s*((?:Глава|ГЛАВА|Часть|ЧАСТЬ|Приложение|Введение|Заключение)\s+[IVXLC\d]{1,5}[.)]?\s*[^.!?]{0,80}?)\s+"
        r"([А-ЯЁ][а-яё][^.!?]{30,}[.!?])",
        whole,
    )
    if chapter and not is_pure_heading(stripped):
        findings.append({"shape": "chapter_opener_then_sentence",
                         "heading": chapter.group(1).strip()[:120],
                         "body": chapter.group(2)[:160]})
    return findings


# --------------------------------------------------------------------------------------
# Class 2: broken list items
# --------------------------------------------------------------------------------------

def find_broken_list_items(blocks: list[str], index: int) -> list[dict[str, str]]:
    """Orphaned or torn list entries.

    Reader test: a bullet with nothing after it, a numbered entry that stops mid-phrase and
    resumes as an unmarked paragraph, or a bullet character sitting inside running prose.
    """
    findings: list[dict[str, str]] = []
    block = blocks[index].strip()
    if is_image_only(block):
        return findings

    if _BARE_LIST_MARKER.match(block):
        findings.append({"shape": "orphan_marker", "text": block[:80]})
        return findings

    text = visible_text(block)
    if is_list_item(block):
        marker_only_body = re.sub(_LIST_MARKER, "", block.strip()).strip()
        if len(visible_text(marker_only_body)) <= 2:
            findings.append({"shape": "orphan_marker", "text": block[:80]})
            return findings
        if text and text[-1] not in _TERMINAL_CHARS and index + 1 < len(blocks):
            nxt = blocks[index + 1].strip()
            nxt_text = visible_text(nxt)
            if nxt_text and not is_list_item(nxt) and not is_image_only(nxt) and nxt_text[0].islower():
                findings.append({"shape": "list_item_torn_across_blocks",
                                 "text": text[-90:], "continuation": nxt_text[:90]})

    if not is_list_item(block):
        for match in re.finditer(r"(?<=[а-яёa-zА-ЯЁA-Z,;:])\s+•\s+(?=\S)", block):
            findings.append({"shape": "inline_bullet_in_prose",
                             "text": visible_text(block[max(0, match.start() - 60): match.end() + 60])})
    return findings


# --------------------------------------------------------------------------------------
# Class 3: footnote markers glued to the text
# --------------------------------------------------------------------------------------

# A footnote digit welded to a word with no space: "институтами12", "системы.13 Далее".
# Anchored on a LETTER immediately before the digits, so years, page counts, "1990-х" and
# any digit that follows whitespace can never match. The trailing boundary excludes "-"
# (COVID-19) and "%" and further digits.
_GLUED_FOOTNOTE = re.compile(
    r"(?<=[а-яёa-zА-ЯЁA-Z])([.,)»”]?)(\d{1,3})(?=[\s.,;:!?)»\"'”’]|$)"
)


_URL_SPAN = re.compile(r"https?://\S+|www\s?\.\s?\S+|\S+\.(?:html?|pdf|php|aspx?|org|com|net|ru)\b")


def find_glued_footnote_markers(block: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if is_image_only(block) or is_table(block):
        return findings
    text = visible_text(block)
    # Digits inside a URL ("kung2.html", "whr00_en.pdf") are part of the address, not
    # footnote markers. Calibration found these were the only systematic false positives.
    url_spans = [(m.start(), m.end()) for m in _URL_SPAN.finditer(text)]
    for match in _GLUED_FOOTNOTE.finditer(text):
        if any(start <= match.start() < end for start, end in url_spans):
            continue
        window = text[max(0, match.start() - 60): match.end() + 60]
        findings.append({"shape": "digit_welded_to_word", "marker": match.group(0), "text": window})
    return findings


# --------------------------------------------------------------------------------------
# Class 4: page furniture inside prose
# --------------------------------------------------------------------------------------

def is_index_like(text: str) -> bool:
    """A contents page or a back-of-book index, where "term, 137" IS the content.

    Calibration found these blocks contributed the large majority of raw
    ``page_number_inside_prose`` hits in every book, and none of them is a defect: the
    reader expects page numbers there. The class is "page furniture *in prose*", so index
    and contents blocks are excluded rather than counted and then explained away.
    """
    words = len(re.findall(r"[А-ЯЁA-Za-zа-яё]+", text)) or 1
    number_groups = len(re.findall(r"\b\d{1,4}\b", text))
    return number_groups / words > 0.12 or len(re.findall(r"[,;]\s*\d{1,4}\b", text)) >= 4


def _normalize_caps_run(value: str) -> str:
    return re.sub(r"[\s\d.,:]+", " ", value).strip().casefold()


def collect_repeated_caps_runs(blocks: list[str], *, min_occurrences: int = 3) -> frozenset[str]:
    """The ALL-CAPS strings that REPEAT across the book — i.e. actual running headers.

    This is the precision fix that mattered. An ALL-CAPS run inside a paragraph is not by
    itself furniture: books contain acronym clusters ("WIR, LETS"), emphatic titles and
    scene datelines. A running header, by definition, repeats on every page of its section;
    calibration on lietaer showed the repetition test removes the acronym false positives
    while keeping every real header.
    """
    counts: dict[str, int] = {}
    for block in blocks:
        for match in _CAPS_RUN.finditer(visible_text(block)):
            counts[_normalize_caps_run(match.group(0))] = counts.get(_normalize_caps_run(match.group(0)), 0) + 1
    return frozenset(key for key, count in counts.items() if count >= min_occurrences and len(key) >= 8)


def _is_header_shaped(caps_run: str) -> bool:
    """Two or more real words, at least one long. Excludes acronym pairs like "WIR, LETS"."""
    words = re.findall(r"[А-ЯЁA-Z]{2,}", caps_run)
    return len(words) >= 2 and max((len(word) for word in words), default=0) >= 6


def find_inline_page_furniture(block: str, repeated_caps: frozenset[str] = frozenset()) -> list[dict[str, str]]:
    """A running header or page number sitting inside a sentence.

    Reader test: you are reading a paragraph and a page header or a bare page number
    appears in the middle of it. Three shapes, in descending order of how loud they are:

    * a page number immediately followed by a running header ("... ценностью. 156 ГЛАВА 1.
      ЭКОНОМИКА ДОВЕРИЯ Это соглашение ..."), which is a whole page break inlined;
    * a repeated ALL-CAPS header inside a paragraph;
    * a bare page number sitting between a finished sentence and the next one.

    A block that *is* nothing but a page number is a different, milder thing and is counted
    separately as ``standalone_page_number_block``. Contents and index blocks are excluded
    by ``is_index_like``: page numbers are their content, not furniture in prose.
    """
    findings: list[dict[str, str]] = []
    stripped = block.strip()
    if is_image_only(stripped) or is_table(stripped) or is_pure_heading(stripped):
        return findings
    text = visible_text(stripped)
    if len(text) < 80 or is_index_like(text):
        return findings

    claimed: list[tuple[int, int]] = []

    def _claim(start: int, end: int) -> bool:
        if any(s <= start < e for s, e in claimed):
            return False
        claimed.append((start, end))
        return True

    for match in re.finditer(rf"(?<=[\s.,;:!?»)])(\d{{1,3}})\s+({_CAPS_RUN.pattern})", text):
        if match.start() < 3 or not _is_header_shaped(match.group(2)):
            continue
        if _claim(match.start(), match.end()):
            findings.append({"shape": "page_number_and_running_header_inside_prose",
                             "furniture": match.group(0)[:90],
                             "text": text[max(0, match.start() - 70): match.end() + 70]})

    for match in _CAPS_RUN.finditer(text):
        if match.start() < 3 or not _is_header_shaped(match.group(0)):
            continue
        if _normalize_caps_run(match.group(0)) not in repeated_caps:
            continue
        before = text[:match.start()].rstrip()
        if len(before) < 40 or not re.search(r"[а-яёa-z]{3}\W*$", before):
            continue
        if _claim(match.start(), match.end()):
            findings.append({"shape": "running_header_inside_prose",
                             "furniture": match.group(0)[:80],
                             "text": text[max(0, match.start() - 70): match.end() + 70]})

    # A bare page number wedged at a sentence boundary. Anchored on the closing punctuation
    # of the previous sentence, so quantities ("за 100 BerkShares") and datelines
    # ("ТАИЛАНД, 6 ФЕВРАЛЯ") — both false positives during calibration — cannot match.
    for match in re.finditer(r"(?<=[.!?»])\s+(\d{1,3})\s+(?=[А-ЯЁA-Z])", text):
        if _claim(match.start(), match.end()):
            findings.append({"shape": "page_number_inside_prose",
                             "furniture": match.group(1),
                             "text": text[max(0, match.start() - 70): match.end() + 70]})
    return findings


_IMAGE_PLACEHOLDER = re.compile(r"\[\[DOCX_IMAGE_[^\]]+\]\]")


def find_caption_fused_with_image_anchor(block: str) -> list[dict[str, str]]:
    """An image anchor sharing its block with caption text.

    Reader test: in the built DOCX the picture and the words "РИСУНОК 1.2. ..." end up in
    the same paragraph, so the caption sits beside the image instead of under it.
    """
    stripped = block.strip()
    if not _IMAGE_PLACEHOLDER.search(stripped) or is_image_only(stripped):
        return []
    rest = visible_text(_IMAGE_PLACEHOLDER.sub(" ", stripped))
    if len(rest) < 5:
        return []
    return [{"shape": "image_anchor_shares_block_with_text",
             "anchor": (_IMAGE_PLACEHOLDER.search(stripped) or re.match("", "")).group(0)[:60],
             "text": rest[:160]}]


def is_standalone_page_number_block(block: str) -> bool:
    return bool(re.fullmatch(r"\[?\(?\d{1,3}\)?\]?", visible_text(block)))


# --------------------------------------------------------------------------------------
# Class 5: broken sentences across blocks
# --------------------------------------------------------------------------------------

# Words that cannot end a Russian sentence: prepositions and conjunctions. A paragraph
# ending on one of these — or on a comma — is torn mid-phrase however the next block opens.
_DANGLING_TAIL = (
    r"(?:,\s*|\s(?:и|а|но|или|в|во|на|с|со|к|ко|по|для|что|чтобы|как|из|от|до|при|о|об|обо|"
    r"за|под|над|между|через|про|без|перед|после|около|среди|вместе|потому|поскольку|"
    r"который|которая|которые|которых|его|её|их|этот|эта|это|эти|тот|та|те)\s*)$"
)


def find_broken_sentences(blocks: list[str], index: int) -> list[dict[str, str]]:
    """A paragraph that stops mid-phrase and continues in the next block.

    Reader test: the paragraph ends without a full stop, and the next paragraph opens in
    lower case — so the eye has to stitch them back together.
    """
    if index + 1 >= len(blocks):
        return []
    block = blocks[index].strip()
    nxt = blocks[index + 1].strip()
    if is_image_only(block) or is_image_only(nxt) or is_table(block) or is_table(nxt):
        return []
    if is_pure_heading(block) or is_pure_heading(nxt):
        return []
    if is_list_item(block) or is_list_item(nxt):
        return []  # torn list items are class 2, counted there
    text = visible_text(block)
    nxt_text = visible_text(nxt)
    # 12, not 40. A 40-char floor hid the exact damage this class exists to catch: the live
    # run split "ДЕННИС МЕДОУЗ — соавтор книг «Пределы роста»" into a 15-char stub ending in
    # a dash and a continuation opening in lower case, and the floor made it invisible.
    if len(text) < 12 or not nxt_text:
        return []
    if is_index_like(text) or is_index_like(nxt_text):
        return []  # index entries end on commas by design; that is not a torn sentence
    if text[-1] == "-":
        return []
    # Two independent reader signals, either is enough.
    #  * the paragraph has no closing punctuation and the next one opens in lower case, so
    #    the eye has to stitch them;
    #  * the paragraph ends on a comma or on a function word (a preposition, a conjunction)
    #    that cannot end a sentence in Russian — a break mid-phrase whatever comes next.
    unfinished_then_lowercase = (
        text[-1] not in _TERMINAL_CHARS and (nxt_text[0].islower() or nxt_text[0] in "—–")
    )
    dangling = bool(re.search(_DANGLING_TAIL, text))
    if not (unfinished_then_lowercase or dangling):
        return []
    return [{
        "shape": "paragraph_stops_mid_phrase" if unfinished_then_lowercase else "paragraph_ends_on_dangling_word",
        "text": text[-90:],
        "continuation": nxt_text[:90],
    }]


# --------------------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------------------

def measure(markdown_text: str, *, repeated_caps: frozenset[str] | None = None) -> dict[str, Any]:
    blocks = split_blocks(markdown_text)
    if repeated_caps is None:
        repeated_caps = collect_repeated_caps_runs(blocks)
    per_block: list[dict[str, list[dict[str, str]]]] = []
    standalone_page_numbers = 0
    for index, block in enumerate(blocks):
        findings = {
            "fused_heading": find_fused_headings(blocks, index),
            "broken_list_item": find_broken_list_items(blocks, index),
            "glued_footnote_marker": find_glued_footnote_markers(block),
            "inline_page_furniture": find_inline_page_furniture(block, repeated_caps),
            "broken_sentence": find_broken_sentences(blocks, index),
            "caption_fused_with_image_anchor": find_caption_fused_with_image_anchor(block),
        }
        per_block.append(findings)
        if is_standalone_page_number_block(block):
            standalone_page_numbers += 1
    counts = {name: sum(len(item[name]) for item in per_block) for name in DEFECT_CLASSES}
    counts["standalone_page_number_block"] = standalone_page_numbers
    return {
        "block_count": len(blocks),
        "visible_char_count": sum(len(visible_text(block)) for block in blocks),
        "counts": counts,
        "blocks": blocks,
        "per_block": per_block,
    }


# --------------------------------------------------------------------------------------
# Diff and harm ledger
# --------------------------------------------------------------------------------------

_BLOCK_SEPARATOR = " ‖ "
_FURNITURE_TOKEN = re.compile(rf"^(?:\d{{1,4}}|[.,;:!?\-–—()\[\]«»\"']|{_CAPS_WORD}|\s)+$")


def _classify_removal(removed: str, before_context: str, offset: int) -> str:
    """Is this deleted text furniture (the job) or content (harm)?

    ``offset`` is where the removal starts in ``before_context``; the neighbourhood is what
    decides. A bare number is furniture when it sits next to a running header or at the very
    edge of a block, and CONTENT when the thing after it is a proper noun — the live run
    turned ``235 Montgomery Street, Suite 650`` into ``Montgomery Street, Suite 650``,
    classified by the pass as ``page_number``. Without the neighbourhood test that deletion
    reads as furniture and the harm goes unrecorded.
    """
    text = removed.strip()
    if not text:
        return "whitespace"
    if _BLOCK_SEPARATOR.strip() in text and not re.sub(rf"[\s{re.escape(_BLOCK_SEPARATOR.strip())}]", "", text):
        # Only the marker this tool itself puts between blocks moved: a block boundary was
        # shifted, which is what normalize_heading_boundary is FOR, not deleted content.
        return "block_boundary_moved"
    if re.fullmatch(r"[\s.,;:!?\-–—()\[\]«»\"'*_#]+", text):
        return "punctuation_or_markup"
    # A whole block that reads only "(пусто)" is an importer placeholder for an empty
    # paragraph, not prose. Deleting it is junk removal; counting it as lost words would
    # overstate the harm on the one book where it happens (5 blocks).
    if re.fullmatch(r"\(\s*пусто\s*\)", text, flags=re.IGNORECASE) and text == before_context.strip():
        return "importer_placeholder_removed"
    # Anything cut out of a URL is harm, full stop — a broken link is not a cleaner book.
    for match in re.finditer(r"https?://\S+|www\s?\.\s?\S+|\S+\.(?:html?|pdf|php|aspx?)\b", before_context):
        if match.start() <= offset < match.end():
            return "harm_url_fragment"
    if re.search(r"[а-яё]{3}", text) or re.search(r"[a-z]{3}", text):
        return "harm_prose_words"
    if re.fullmatch(r"[\d\s.,\-–—]+", text):
        after = before_context[offset + len(removed):].lstrip()
        # A capitalised-but-not-shouting word after the number means the number belonged to
        # it: a street number, a figure number, a numbered clause.
        if re.match(r"[А-ЯЁA-Z][а-яёa-z]", after):
            return "harm_suspected_content_number"
        # Page numbers in these books are 1-3 digits. A four-digit number is a year, an
        # ISBN fragment or a sum — never furniture. The live run deleted "2012" out of
        # "2012 г." twice in one book and the remaining block reads just "г.".
        if re.search(r"\d{4}", text):
            return "harm_suspected_content_number"
        # A deletion that leaves a stump instead of a sentence is damage whatever the
        # deleted token was.
        remainder = (before_context[:offset] + before_context[offset + len(removed):]).strip()
        if len(re.sub(r"[\W\d_]+", "", remainder)) < 4:
            return "harm_leaves_stump"
        return "furniture"
    if _FURNITURE_TOKEN.fullmatch(text):
        return "furniture"
    return "harm_other"


def _diff_key(block: str) -> str:
    """Alignment key: the visible text PLUS the image anchor ids.

    ``visible_text`` strips ``[[DOCX_IMAGE_*]]``, so splitting "anchor + caption" into two
    blocks left the caption block's key unchanged and the freed anchor block's key empty —
    difflib then reported a bare insert of an empty string and the before/after pair for
    the actual change was never shown. The ids belong in the key.
    """
    anchors = " ".join(_IMAGE_PLACEHOLDER.findall(block))
    return f"{anchors}{visible_text(block)}"


def diff_blocks(before: list[str], after: list[str]) -> list[dict[str, Any]]:
    """Align before/after block lists and describe every change."""
    matcher = difflib.SequenceMatcher(a=[_diff_key(b) for b in before], b=[_diff_key(b) for b in after], autojunk=False)
    changes: list[dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append({
            "tag": tag,
            "before_indexes": list(range(i1, i2)),
            "after_indexes": list(range(j1, j2)),
            "before": [before[i] for i in range(i1, i2)],
            "after": [after[j] for j in range(j1, j2)],
        })
    return changes


_DANGLING_OPENER = re.compile(r"[«„\"(\[]\s*$")


def _structural_harm(change: dict[str, Any], repeated_caps: frozenset[str]) -> list[dict[str, Any]]:
    """Damage that leaves every character in place but puts the boundary in the wrong spot.

    Two checks, both from things the live run actually did:

    * a block that now ENDS on an opening quote, with its closing quote stranded at the
      start of the next block — the run split ``... ТОВАРНЫМИ АКТИВАМИ «Свободный банк
      Лакота» ...`` between the ``«`` and the name;
    * a changed region that comes out with MORE defects of a named class than it went in
      with — the run split three author bios ("ДЕННИС МЕДОУЗ — соавтор книг ...") into a
      dash-ending stub and a lower-case continuation.

    Neither shows up in a character diff, so neither would reach a ledger built only from
    deletions.
    """
    findings: list[dict[str, Any]] = []
    for block in change["after"]:
        if _DANGLING_OPENER.search(visible_text(block)):
            findings.append({
                "verdict": "harm_boundary_strands_opening_quote",
                "removed": "",
                "added": "",
                "before_context": " ‖ ".join(visible_text(b) for b in change["before"])[:260],
                "after_context": " ‖ ".join(visible_text(b) for b in change["after"])[:260],
                "before_block_indexes": change["before_indexes"],
            })
            break
    before_counts = _counts_for(list(change["before"]), repeated_caps)
    after_counts = _counts_for(list(change["after"]), repeated_caps)
    for name in DEFECT_CLASSES:
        if after_counts[name] > before_counts[name]:
            findings.append({
                "verdict": f"harm_defect_class_increase:{name}",
                "removed": "",
                "added": f"+{after_counts[name] - before_counts[name]}",
                "before_context": " ‖ ".join(visible_text(b) for b in change["before"])[:260],
                "after_context": " ‖ ".join(visible_text(b) for b in change["after"])[:260],
                "before_block_indexes": change["before_indexes"],
            })
    return findings


def build_harm_ledger(changes: list[dict[str, Any]], repeated_caps: frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for change in changes:
        ledger.extend(_structural_harm(change, repeated_caps))
        before_text = _BLOCK_SEPARATOR.join(visible_text(b) for b in change["before"])
        after_text = _BLOCK_SEPARATOR.join(visible_text(b) for b in change["after"])
        matcher = difflib.SequenceMatcher(a=before_text, b=after_text, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag not in {"delete", "replace"}:
                continue
            removed = before_text[i1:i2]
            added = after_text[j1:j2]
            verdict = _classify_removal(removed, before_text, i1)
            if not verdict.startswith("harm"):
                continue
            ledger.append({
                "verdict": verdict,
                "removed": removed,
                "added": added,
                "before_context": before_text[max(0, i1 - 110): i2 + 110],
                "after_context": after_text[max(0, j1 - 110): j2 + 110],
                "before_block_indexes": change["before_indexes"],
            })
    return ledger


def collect_examples(
    changes: list[dict[str, Any]],
    repeated_caps: frozenset[str] = frozenset(),
    limit_per_class: int = 6,
) -> dict[str, list[dict[str, str]]]:
    """Before/after pairs for the changed regions, bucketed by the class they touch."""
    examples: dict[str, list[dict[str, str]]] = {name: [] for name in DEFECT_CLASSES}
    for change in changes:
        before_blocks = list(change["before"])
        after_blocks = list(change["after"])
        before_counts = _counts_for(before_blocks, repeated_caps)
        after_counts = _counts_for(after_blocks, repeated_caps)
        for name in DEFECT_CLASSES:
            delta = after_counts[name] - before_counts[name]
            if delta == 0 or len(examples[name]) >= limit_per_class:
                continue
            examples[name].append({
                "delta": delta,
                "before": "\n\n".join(before_blocks)[:700],
                "after": "\n\n".join(after_blocks)[:700],
                "before_block_indexes": change["before_indexes"],
            })
    return examples


def _counts_for(blocks: list[str], repeated_caps: frozenset[str] = frozenset()) -> dict[str, int]:
    counts = {name: 0 for name in DEFECT_CLASSES}
    for index, block in enumerate(blocks):
        counts["fused_heading"] += len(find_fused_headings(blocks, index))
        counts["broken_list_item"] += len(find_broken_list_items(blocks, index))
        counts["glued_footnote_marker"] += len(find_glued_footnote_markers(block))
        counts["inline_page_furniture"] += len(find_inline_page_furniture(block, repeated_caps))
        counts["broken_sentence"] += len(find_broken_sentences(blocks, index))
        counts["caption_fused_with_image_anchor"] += len(find_caption_fused_with_image_anchor(block))
    return counts


# --------------------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------------------

def analyse_book(book: str, raw_path: Path, cleaned_path: Path) -> dict[str, Any]:
    raw = raw_path.read_text(encoding="utf-8")
    cleaned = cleaned_path.read_text(encoding="utf-8")
    # The running-header vocabulary is derived from the BEFORE document and reused for the
    # after one. Deriving it twice would let the pass change the yardstick by deleting a
    # header often enough to drop the rest below the repetition threshold.
    repeated_caps = collect_repeated_caps_runs(split_blocks(raw))
    before = measure(raw, repeated_caps=repeated_caps)
    after = measure(cleaned, repeated_caps=repeated_caps)
    changes = diff_blocks(before["blocks"], after["blocks"])
    harm = build_harm_ledger(changes, repeated_caps)
    examples = collect_examples(changes, repeated_caps)
    changed_before_blocks = sum(len(c["before_indexes"]) for c in changes)
    changed_after_blocks = sum(len(c["after_indexes"]) for c in changes)
    # Per-region verdict. This is the number an owner should be shown first: of the places
    # the pass touched, how many came out better, how many worse, how many neither.
    harmed_region_keys = {tuple(entry["before_block_indexes"]) for entry in harm}
    improved = worse = neutral = 0
    for change in changes:
        before_counts = _counts_for(list(change["before"]), repeated_caps)
        after_counts = _counts_for(list(change["after"]), repeated_caps)
        net = sum(after_counts[name] - before_counts[name] for name in DEFECT_CLASSES)
        harmed = tuple(change["before_indexes"]) in harmed_region_keys
        if harmed or net > 0:
            worse += 1
        elif net < 0:
            improved += 1
        else:
            neutral += 1
    return {
        "book": book,
        "before": {"block_count": before["block_count"], "visible_char_count": before["visible_char_count"], "counts": before["counts"]},
        "after": {"block_count": after["block_count"], "visible_char_count": after["visible_char_count"], "counts": after["counts"]},
        "delta": {name: after["counts"][name] - before["counts"][name] for name in sorted(after["counts"])},
        "changed_region_count": len(changes),
        "changed_block_count_before": changed_before_blocks,
        "changed_block_count_after": changed_after_blocks,
        "regions_improved": improved,
        "regions_worse": worse,
        "regions_no_measured_change": neutral,
        "visible_char_delta": after["visible_char_count"] - before["visible_char_count"],
        "harm_count": len(harm),
        "harm": harm,
        "examples": examples,
        "changes": changes,
    }


def _print_book(data: dict[str, Any]) -> None:
    print(f"=== {data['book']}")
    print(f"    blocks {data['before']['block_count']} -> {data['after']['block_count']}, "
          f"visible chars {data['before']['visible_char_count']} -> {data['after']['visible_char_count']} "
          f"({data['visible_char_delta']:+d})")
    print(f"    changed regions: {data['changed_region_count']} "
          f"({data['changed_block_count_before']} blocks in, {data['changed_block_count_after']} out)")
    print(f"    region verdicts: {data['regions_improved']} better, {data['regions_worse']} worse, "
          f"{data['regions_no_measured_change']} no measured change")
    print(f"    {'class':<32}{'before':>8}{'after':>8}{'delta':>8}")
    for name in sorted(data["before"]["counts"]):
        b = data["before"]["counts"][name]
        a = data["after"]["counts"][name]
        print(f"    {name:<32}{b:>8}{a:>8}{a - b:>+8}")
    print(f"    harm entries: {data['harm_count']}")
    for entry in data["harm"][:10]:
        print(f"        [{entry['verdict']}] removed {entry['removed']!r}")
        print(f"            before: ...{entry['before_context']}...")
        print(f"            after : ...{entry['after_context']}...")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="a live-run directory containing <book>/<book>.live.raw.md and .live.cleaned.md")
    parser.add_argument("--out", type=Path, default=None, help="where to write the JSON report (default: <run-dir>/visible_defects.json)")
    args = parser.parse_args(list(argv) if argv is not None else None)

    run_dir: Path = args.run_dir
    if not run_dir.is_dir():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 2

    books: dict[str, Any] = {}
    for book_dir in sorted(p for p in run_dir.iterdir() if p.is_dir()):
        raw_path = book_dir / f"{book_dir.name}.live.raw.md"
        cleaned_path = book_dir / f"{book_dir.name}.live.cleaned.md"
        if not raw_path.is_file() or not cleaned_path.is_file():
            continue
        data = analyse_book(book_dir.name, raw_path, cleaned_path)
        books[book_dir.name] = data
        _print_book(data)

    if not books:
        print(f"no book directories with .live.raw.md/.live.cleaned.md under {run_dir}", file=sys.stderr)
        return 2

    out_path: Path = args.out or (run_dir / "visible_defects.json")
    out_path.write_text(json.dumps({"run_dir": str(run_dir), "books": books}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport written to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
