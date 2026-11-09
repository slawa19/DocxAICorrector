"""Spec 070 FR-003: which paragraph of an audiobook is NOT narrated, and why.

A pure function of what the document layer already knows about ONE paragraph: its roles, its
region, the back-matter section it sits in, the spec 067 notes-in-body mark, and the FORM of its
text. No word list and no per-book literal (Constitution VII): the only thing read off the text
is how much of it is letters, and how long its letter runs are.

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

# The roles whose paragraphs are never judged by the fragment rule (plan deviation O-1).
FRAGMENT_RULE_EXEMPT_ROLES = frozenset({"heading", "epigraph", "attribution", "dedication"})

_TOC_ROLES = frozenset({"toc_header", "toc_entry"})

# A run of letters (Unicode category L*), nothing else. Digits and the underscore are not
# letters: ``[^\W\d_]`` is "a word character that is neither a digit nor an underscore".
_LETTER_RUN_PATTERN = re.compile(r"[^\W\d_]+")
_MIN_CONNECTED_LETTER_RUN = 3


def _without_combining_marks(text: str) -> str:
    """Drop combining marks (Unicode category M*): a diacritic belongs to its letter, so it is
    neither a letter run of its own nor a non-letter that dilutes the share of letters."""
    return "".join(character for character in text if not unicodedata.category(character).startswith("M"))


def is_fragment_without_connected_text(text: str) -> bool:
    """The form rule of spec 070 FR-003, exactly as the spec words it.

    True when the text has no letter run of three or more letters, OR when its letters are
    fewer than half of its non-space characters. Text with no non-space character at all is a
    fragment too: there is nothing to say. Exactly half is NOT a fragment, and a run of exactly
    three letters is NOT one either (both boundaries are pinned by tests).
    """
    cleaned = _without_combining_marks(str(text or ""))
    non_space = [character for character in cleaned if not character.isspace()]
    if not non_space:
        return True
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
        # Outside the fragment rule -- but a paragraph with nothing in it at all has nothing to
        # narrate under any role, and a request must never carry an empty paragraph.
        return NARRATION_EXCLUSION_FRAGMENT if not str(text or "").strip() else None
    if is_fragment_without_connected_text(text):
        return NARRATION_EXCLUSION_FRAGMENT
    return None
