"""Paragraph-break (mid-sentence split) detection satellite (spec 035, Step 1).

Extracted verbatim from ``pipeline/output_validation.py``: the ``ParagraphBreakSample``
record, the ``_PARAGRAPH_BREAK_*`` constants, the ``_paragraph_break_*`` helpers, and
``collect_paragraph_break_samples``. Behaviour is unchanged; ``output_validation``
re-exports these names so ``output_validation.<name>`` keeps resolving.

The one shared primitive this cluster needs, ``_SENTENCE_TERMINAL_PATTERN``, STAYS in
``output_validation`` and is reached via a function-local import inside
``_paragraph_break_ends_without_terminal`` (avoids relocating a widely-shared constant
and avoids a module-level import cycle).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docxaicorrector.validation.formatting_coverage import resolve_main_content_scope


@dataclass(frozen=True)
class ParagraphBreakSample:
    """One paragraph that a PDF-import mis-tag split into two mid-sentence halves.

    The two halves share one source paragraph (``origin_raw_indexes``/``source_index``);
    ``text`` is the first half's preview and ``next_text`` the second half's.
    """

    source_index: int | None
    text: str
    next_text: str


# Language-general continuation starts (spec 008 FR-001): a second fragment that
# resumes with a closing or joining mark (", and", "; или") is a continuation, not a
# new sentence. Kept MINIMAL and word-list-free — the primary rule is "starts lowercase".
_PARAGRAPH_BREAK_CONTINUATION_STARTS = frozenset(")]},.;:!?»”’")
# ``list_kind`` values that mark a structural list boundary (spec 008 FR-003).
_PARAGRAPH_BREAK_LIST_KINDS = frozenset({"ordered", "unordered", "list"})


def _paragraph_break_ends_without_terminal(text: str) -> bool:
    """True when ``text`` ends mid-sentence (no sentence-terminal punctuation).

    Reuses ``_SENTENCE_TERMINAL_PATTERN`` so a closing quote/bracket counts as terminal
    only when it follows terminal punctuation. A trailing footnote-marker digit or
    superscript (e.g. "…²") is therefore already non-terminal — the digit is the final
    character and the terminal pattern does not match it (spec 008 edge case).
    """

    from docxaicorrector.pipeline.output_validation import _SENTENCE_TERMINAL_PATTERN

    stripped = text.strip()
    if not stripped:
        return False
    return _SENTENCE_TERMINAL_PATTERN.search(stripped) is None


def _paragraph_break_starts_continuation(text: str) -> bool:
    """True when ``text`` starts as a continuation: a lowercase letter or joining mark.

    Unicode-aware (Latin, Cyrillic, and any cased script) via ``str.islower`` — no word
    list. The lowercase rule is primary; a leading continuation mark is the only addition.
    """

    stripped = text.strip()
    if not stripped:
        return False
    first = stripped[0]
    if first.isalpha():
        return first.islower()
    return first in _PARAGRAPH_BREAK_CONTINUATION_STARTS


def _paragraph_break_entry_is_heading_or_list(entry: Mapping[str, Any]) -> bool:
    """True when the entry is a heading or a list item (a structural boundary, not a split)."""

    if entry.get("heading_level") is not None:
        return True
    if entry.get("role") == "heading" or entry.get("structural_role") == "heading":
        return True
    list_kind = entry.get("list_kind")
    if isinstance(list_kind, str) and list_kind.strip().lower() in _PARAGRAPH_BREAK_LIST_KINDS:
        return True
    return False


def _paragraph_break_raw_key(entry: Mapping[str, Any]) -> tuple[object, ...] | None:
    """The entry's ``origin_raw_indexes`` as a tuple, or None when absent/empty."""

    raw = entry.get("origin_raw_indexes")
    if isinstance(raw, Sequence) and not isinstance(raw, str) and raw:
        return tuple(raw)
    return None


def _paragraph_break_shares_source_paragraph(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> bool:
    """True when both entries came from the same source paragraph (spec 008 FR-001/FR-002).

    The primary signal is equal, non-empty ``origin_raw_indexes`` (same raw PDF block).
    Only when BOTH entries lack raw indexes does it fall back to equal ``source_index``.
    A boundary with no shared-source signal is never a split ("no source signal").
    """

    first_raw = _paragraph_break_raw_key(first)
    second_raw = _paragraph_break_raw_key(second)
    if first_raw is not None and second_raw is not None:
        return first_raw == second_raw
    if first_raw is None and second_raw is None:
        first_index = first.get("source_index")
        second_index = second.get("source_index")
        return isinstance(first_index, int) and first_index == second_index
    return False


def _paragraph_break_source_index(entry: Mapping[str, Any]) -> int | None:
    value = entry.get("source_index")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _paragraph_break_out_of_main_content(
    entry: Mapping[str, Any],
    *,
    front_matter_boundary: int | None,
    references_region_start: int | None,
    bounded_toc_region: tuple[int, int] | None,
) -> bool:
    """True when the pair's FIRST entry falls OUTSIDE the main-content span (FR-007).

    Mirrors the per-entry region test in ``classify_heading_demotions``: skip a source
    index that is in the front matter (``< front_matter_boundary``), in the back-matter
    references/notes/index region (``>= references_region_start``), or inside the bounded
    TOC region. An entry with no integer ``source_index`` cannot be region-placed, so it
    is NOT excluded here (the shared-source / form gates still apply).
    """

    index = _paragraph_break_source_index(entry)
    if index is None:
        return False
    if front_matter_boundary is not None and index < front_matter_boundary:
        return True
    if references_region_start is not None and index >= references_region_start:
        return True
    if bounded_toc_region is not None and bounded_toc_region[0] <= index <= bounded_toc_region[1]:
        return True
    return False


def collect_paragraph_break_samples(
    source_registry: Sequence[Mapping[str, Any]],
    preparation_diagnostic_snapshot: Mapping[str, object] | None = None,
) -> list[ParagraphBreakSample]:
    """Flag paragraphs split mid-sentence by the PDF-import ``toc_entry`` mis-tag (spec 008).

    ADVISORY detection only — changes no delivered bytes. An adjacent ordered pair of
    ``source_registry`` entries is flagged when ALL hold (Constitution VII: structural
    provenance ∩ language-general form, no word lists, no per-book literals):

    * the first entry's ``source_index`` is inside the MAIN-CONTENT span
      ``[front_matter_boundary … references_region_start)`` and outside the bounded TOC
      region (FR-007) — the SAME region provenance ``classify_heading_demotions`` uses,
      via :func:`resolve_main_content_scope`, so TOC page-refs and back-of-book index
      entries are excluded by REGION, never by a per-book literal;
    * they share one source paragraph — equal ``origin_raw_indexes`` (or equal
      ``source_index`` when raw indexes are absent on both) (FR-001/FR-002);
    * neither entry is a heading or a list item (FR-003);
    * the first entry's ``text_preview`` ends without sentence-terminal punctuation; and
    * the second entry's ``text_preview`` starts lowercase / as a continuation.
    """

    entries = [entry for entry in source_registry if isinstance(entry, Mapping)]
    front_matter_boundary, references_region_start, bounded_toc_region = resolve_main_content_scope(
        entries, preparation_diagnostic_snapshot
    )
    ordered = sorted(
        enumerate(entries),
        key=lambda item: (
            _paragraph_break_source_index(item[1]) is None,
            _paragraph_break_source_index(item[1]) or 0,
            item[0],
        ),
    )
    samples: list[ParagraphBreakSample] = []
    for (_, first), (_, second) in zip(ordered, ordered[1:]):
        if _paragraph_break_out_of_main_content(
            first,
            front_matter_boundary=front_matter_boundary,
            references_region_start=references_region_start,
            bounded_toc_region=bounded_toc_region,
        ):
            continue
        if _paragraph_break_entry_is_heading_or_list(first) or _paragraph_break_entry_is_heading_or_list(second):
            continue
        if not _paragraph_break_shares_source_paragraph(first, second):
            continue
        first_text = str(first.get("text_preview") or "")
        second_text = str(second.get("text_preview") or "")
        if not _paragraph_break_ends_without_terminal(first_text):
            continue
        if not _paragraph_break_starts_continuation(second_text):
            continue
        samples.append(
            ParagraphBreakSample(
                source_index=_paragraph_break_source_index(first),
                text=first_text.strip(),
                next_text=second_text.strip(),
            )
        )
    return samples
