"""Spec 070 FR-003: which paragraph of an audiobook is NOT narrated, and why.

A pure function of what the document layer already knows about ONE paragraph: its roles, its
region, the back-matter section it sits in, the spec 067 notes-in-body mark, and the FORM of its
text. No word list and no per-book literal (Constitution VII): the only things read off the text
are how much of it is letters, how long its letter runs are, and whether it ends as a sentence.

Roles and regions decide first. A paragraph the preparation recognised as an image, a table, a
caption, a table-of-contents line, an index or other reference apparatus is not read aloud and is
never sent to the model. The last rule is the one that looks at the text: a *fragment without
connected text* (a lone page number, ``(i)``, ``11 vv``, a ``* * *`` rule) has nothing to say.

Paragraphs the author wrote as a heading, an epigraph, an attribution or a dedication are
outside that last rule (plan deviation O-1): by form ``III`` or ``- A. Writer`` is a fragment, and
it is also exactly what a chapter number and a signature look like -- the role is the signal that
tells them apart, and the role is a property of the preparation, not of the words.
"""

from __future__ import annotations

import re
import unicodedata

from docxaicorrector.core.models import (
    NARRATION_EXCLUSION_APPARATUS,
    NARRATION_EXCLUSION_CAPTION,
    NARRATION_EXCLUSION_FRAGMENT,
    NARRATION_EXCLUSION_IMAGE,
    NARRATION_EXCLUSION_INDEX,
    NARRATION_EXCLUSION_NOTES_IN_BODY,
    NARRATION_EXCLUSION_TABLE,
    NARRATION_EXCLUSION_TOC,
    PARAGRAPH_REGION_BACK_MATTER,
    PARAGRAPH_REGION_TOC,
    BACK_MATTER_SECTION_INDEX,
)
from docxaicorrector.text.narration_forms import without_combining_marks as _without_combining_marks

# The roles whose paragraphs are never judged by the fragment rule (plan deviation O-1).
FRAGMENT_RULE_EXEMPT_ROLES = frozenset({"heading", "epigraph", "attribution", "dedication"})

_TOC_ROLES = frozenset({"toc_header", "toc_entry"})

# A run of letters (Unicode category L*), nothing else. Digits and the underscore are not
# letters: ``[^\W\d_]`` is "a word character that is neither a digit nor an underscore".
_LETTER_RUN_PATTERN = re.compile(r"[^\W\d_]+")
_MIN_CONNECTED_LETTER_RUN = 3


# Spec 070 fix-1 (Codex acceptance review, finding 2): a paragraph that has a letter and ENDS
# a sentence is connected speech, however short -- "Да.", "Go!", "你好。", "От 10 до 20.".
# The terminal marks are read off the Unicode character database, not listed: every
# punctuation character (category P*) whose Unicode NAME says it is a full stop, a question
# or exclamation mark, an ellipsis or a danda, in any script -- except the inverted and
# initial forms, which open a sentence rather than end it. Read from the runtime's
# ``unicodedata``, the same pinned data the rest of the narration code reads.
_SENTENCE_TERMINAL_NAME_PARTS = ("FULL STOP", "QUESTION MARK", "EXCLAMATION MARK", "ELLIPSIS", "DANDA")
_SENTENCE_OPENING_NAME_PARTS = ("INVERTED", "INITIAL")


def _is_sentence_terminal(character: str) -> bool:
    if not unicodedata.category(character).startswith("P"):
        return False
    name = unicodedata.name(character, "")
    return any(part in name for part in _SENTENCE_TERMINAL_NAME_PARTS) and not any(
        part in name for part in _SENTENCE_OPENING_NAME_PARTS
    )


def _may_follow_a_terminal(character: str) -> bool:
    """What may stand after the terminal mark of a sentence: white space, a closing bracket or
    quote (categories Pe, Pf, Pi -- Pi closes in some typographies), a straight quote or an
    apostrophe, and the importer's own emphasis markup (``*``, ``_``)."""
    if character.isspace() or character in "*_":
        return True
    if unicodedata.category(character) in {"Pe", "Pf", "Pi"}:
        return True
    name = unicodedata.name(character, "")
    return "QUOTATION MARK" in name or name == "APOSTROPHE"


def ends_as_a_sentence(text: str) -> bool:
    """True when ``text`` has at least one letter and its last mark, past any closing quote,
    bracket or emphasis marker, is a sentence terminal of any script."""
    value = str(text or "")
    if not any(character.isalpha() for character in value):
        return False
    end = len(value)
    while end > 0 and _may_follow_a_terminal(value[end - 1]):
        end -= 1
    return end > 0 and _is_sentence_terminal(value[end - 1])


def quotation_and_signature(text: str) -> tuple[str, str] | None:
    """Spec 077: ``(quotation, signature)`` when ``text`` -- emphasis markers removed -- has the form
    of an epigraph with its attribution: a sentence (``ends_as_a_sentence``), then a dash (Unicode
    category Pd) standing between spaces, then a signature with a letter ("“The tide waits.” –
    K. L. Tollan"). The LAST such dash splits it, so a dash inside the quotation stays in the
    quotation, and a hyphen inside a name ("Lee-Tollan") is no dash at all. ``None`` otherwise.
    Read off the characters only: no list of words, no name (Constitution VII)."""
    value = str(text or "").replace("*", "").replace("_", "").strip()
    for index in range(len(value) - 2, 0, -1):
        if (
            unicodedata.category(value[index]) == "Pd"
            and value[index - 1].isspace()
            and value[index + 1].isspace()
        ):
            quotation = value[:index].strip()
            signature = value[index + 1 :].strip()
            if ends_as_a_sentence(quotation) and any(character.isalpha() for character in signature):
                return quotation, signature
            return None
    return None


def follows_a_sentence_end(text: str, offset: int) -> bool:
    """Spec 077: ``text[:offset]``, past white space and the closing marks ``_may_follow_a_terminal``
    allows, ends on a sentence terminal of any script -- where a note number OPENS an entry of a
    notes run ("... p. 85. 3 J. Smith"). An abbreviation's full stop counts too ("e.g. 10 Units"):
    there is no list of abbreviations (Constitution VII). Spec 077 narrates a paragraph only when
    this is False for every note number of its entry, so such a stop can only leave a paragraph
    excluded as it was before spec 077, never exclude one more.

    White space BETWEEN the terminal and a closing mark is skipped too ("... next. ” 3 We"): the
    loop once stopped at it and read such an opener as running text (Codex acceptance review of
    the batch, finding 2)."""
    prefix = str(text or "")[: max(offset, 0)]
    end = len(prefix)
    while end > 0 and _may_follow_a_terminal(prefix[end - 1]):
        end -= 1
    return end > 0 and _is_sentence_terminal(prefix[end - 1])


def has_no_letter_or_digit(text: str) -> bool:
    """True when ``text`` has not one letter or digit: empty, white space, or only signs (``***``)."""
    return not any(character.isalnum() for character in str(text or ""))


def is_scene_break_text(text: str) -> bool:
    """The FORM of a scene separator (spec 073 FR-006): a non-empty text, past white space, with no
    letter and no digit -- ``***``, ``# %``, ``— — —``. A lone ``1`` or ``I`` is not one."""
    value = str(text or "")
    return value.strip() != "" and has_no_letter_or_digit(value)


def is_fragment_without_connected_text(text: str) -> bool:
    """The form rule of spec 070 FR-003.

    A text that has a letter and ends as a sentence (``ends_as_a_sentence``) is connected text
    and never a fragment: the short reply "Да." or "Go!" is speech (Codex acceptance review,
    finding 2). Otherwise it is a fragment when it has no letter run of three or more letters,
    OR when its letters are fewer than half of its non-space characters. Text with no non-space
    character at all is a fragment too: there is nothing to say. Exactly half is NOT a fragment,
    and a run of exactly three letters is NOT one either (both boundaries are pinned by tests).
    """
    cleaned = _without_combining_marks(str(text or ""))
    non_space = [character for character in cleaned if not character.isspace()]
    if not non_space:
        return True
    if ends_as_a_sentence(cleaned):
        return False
    letter_count = sum(1 for character in non_space if character.isalpha())
    if letter_count * 2 < len(non_space):
        return True
    return not any(len(run) >= _MIN_CONNECTED_LETTER_RUN for run in _LETTER_RUN_PATTERN.findall(cleaned))


def resolve_narration_exclusion_reason(
    *,
    structural_role: str,
    region: str,
    back_matter_section: str | None,
    in_notes_in_body: bool,
    text: str,
    paragraph_role: str = "",
) -> str | None:
    """The reason this paragraph is not narrated (``core.models.NARRATION_EXCLUSION_REASONS``),
    or ``None`` when it is.

    ``structural_role`` is the effective structural role of the paragraph and ``paragraph_role``
    its basic role (``ParagraphUnit.role``); a paragraph carries the one or the other depending
    on how far preparation has gone, so either one names it. ``region`` is the paragraph's
    document region, ``back_matter_section`` the section of the back-matter block it sits in
    (``None`` outside the region), ``in_notes_in_body`` the spec 067 FR-001 mark.

    Priority is fixed: image, table, caption, toc, index, apparatus, notes in the body,
    fragment. The front-matter region by itself excludes nothing (spec 070 Non-goals): its
    detector calls everything up to the first run of long prose front matter, and an epigraph
    or the first lines of a chapter would be lost with it.
    """
    roles = {str(structural_role or "").strip().lower(), str(paragraph_role or "").strip().lower()}
    if "image" in roles:
        return NARRATION_EXCLUSION_IMAGE
    if "table" in roles:
        return NARRATION_EXCLUSION_TABLE
    if "caption" in roles:
        return NARRATION_EXCLUSION_CAPTION
    if roles & _TOC_ROLES or region == PARAGRAPH_REGION_TOC:
        return NARRATION_EXCLUSION_TOC
    if region == PARAGRAPH_REGION_BACK_MATTER:
        return (
            NARRATION_EXCLUSION_INDEX
            if back_matter_section == BACK_MATTER_SECTION_INDEX
            else NARRATION_EXCLUSION_APPARATUS
        )
    if in_notes_in_body:
        return NARRATION_EXCLUSION_NOTES_IN_BODY
    if roles & FRAGMENT_RULE_EXEMPT_ROLES:
        # Outside the fragment rule -- but a paragraph without a single letter or digit has
        # nothing to narrate under any role: empty, or a separator such as ``***`` that the
        # import styled as a heading (FR-009 run 2026-11-10: the model rightly answered it
        # empty, and the empty-answer rule then narrated the asterisks from source). A request
        # must never carry an empty paragraph either.
        return NARRATION_EXCLUSION_FRAGMENT if has_no_letter_or_digit(text) else None
    if is_fragment_without_connected_text(text):
        return NARRATION_EXCLUSION_FRAGMENT
    return None
