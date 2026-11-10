"""Spec 071: one back-matter reference detector for every operation.

Spec 070 fix-1 guarded the audiobook only: a reference title WITHOUT a heading level that closes
its block anchors a back-matter section only behind a finished sentence; otherwise it is one more
row of an untagged table of contents. The job fields translate and edit read
(``paragraph_regions``, ``back_matter_section``) kept the unguarded detector, so on translate the
prose behind such a row was treated as reference apparatus (spec 063 D1 keeps it in the source
language). The guard now lives in the shared detector.

The examples are invented and carry the FORM of the measured case only (Constitution VII).
"""

from __future__ import annotations

import pytest

from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    PARAGRAPH_REGION_BACK_MATTER,
    DocumentBlock,
    ParagraphUnit,
)
from docxaicorrector.document.semantic_blocks import build_editing_jobs

_PROSE = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)


def _unit(text: str, pid: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
    return ParagraphUnit(text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=role)


def _fields_by_id(blocks: list[DocumentBlock], operation: str) -> dict[str, tuple[str, str | None]]:
    """paragraph id -> (region, back-matter section of its block) on the jobs of ``operation``."""
    fields: dict[str, tuple[str, str | None]] = {}
    for job in build_editing_jobs(blocks, max_chars=3000, processing_operation=operation):
        section = job["back_matter_section"]
        assert section is None or isinstance(section, str)
        for pid, region in zip(job["paragraph_ids"], job["paragraph_regions"]):  # type: ignore[call-overload]
            fields[str(pid)] = (str(region), section)
    return fields


def _untagged_contents_then_prose() -> list[DocumentBlock]:
    """A contents list the import did not tag as one: section names as body rows WITHOUT a heading
    level, the last of which names a reference section, closing its block behind an unfinished
    row. The author's front sections follow, and only later the real, levelled reference section."""
    return [
        DocumentBlock(paragraphs=[_unit(_PROSE, "p0000")]),
        DocumentBlock(
            paragraphs=[
                _unit("Appendices", "p0001", role="heading", level=3),
                _unit("**Acknowledgements**", "p0002"),
                _unit("**Our team**", "p0003"),
                _unit("**Bibliography**", "p0004"),
            ]
        ),
        DocumentBlock(
            paragraphs=[_unit("Foreword", "p0005", role="heading", level=3), _unit(_PROSE, "p0006"), _unit(_PROSE, "p0007")]
        ),
        DocumentBlock(paragraphs=[_unit("Preface", "p0008", role="heading", level=2), _unit(_PROSE, "p0009")]),
        DocumentBlock(paragraphs=[_unit("Chapter One", "p0010", role="heading", level=1), _unit(_PROSE, "p0011")]),
        DocumentBlock(paragraphs=[_unit("Bibliography", "p0012", role="heading", level=2)]),
        DocumentBlock(paragraphs=[_unit("Harbour, A. *Tides*. London, 2004.", "p0013", role="list")]),
    ]


@pytest.mark.parametrize("operation", ["translate", "edit", "audiobook"])
def test_a_contents_row_naming_a_reference_section_opens_no_back_matter_for_any_operation(operation: str) -> None:
    fields = _fields_by_id(_untagged_contents_then_prose(), operation)

    # The row and every front section behind it are not back matter: no region, no section kind --
    # on translate this is what keeps the prose out of the spec 063 apparatus policy.
    for pid in (f"p{n:04d}" for n in range(0, 12)):
        region, section = fields[pid]
        assert region != PARAGRAPH_REGION_BACK_MATTER, pid
        assert section is None, pid
    # Anti-vacuum: the real section, whose title carries a heading level, still anchors.
    assert fields["p0012"] == (PARAGRAPH_REGION_BACK_MATTER, BACK_MATTER_SECTION_REFERENCES)
    assert fields["p0013"] == (PARAGRAPH_REGION_BACK_MATTER, BACK_MATTER_SECTION_REFERENCES)


def test_the_same_row_without_emphasis_markup_is_refused_the_same_way_on_translate() -> None:
    # The guard reads the paragraph in FRONT of the title (does it end a sentence?), not the bold
    # markup of the rows.
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit(paragraph.text.strip("*"), str(paragraph.paragraph_id), role=paragraph.role, level=paragraph.heading_level)
                for paragraph in block.paragraphs
            ]
        )
        for block in _untagged_contents_then_prose()
    ]

    fields = _fields_by_id(blocks, "translate")

    assert all(fields[f"p{n:04d}"][1] is None for n in range(0, 12))
    assert fields["p0013"] == (PARAGRAPH_REGION_BACK_MATTER, BACK_MATTER_SECTION_REFERENCES)


@pytest.mark.parametrize("operation", ["translate", "edit", "audiobook"])
def test_an_unlevelled_title_behind_a_finished_sentence_still_anchors_for_every_operation(operation: str) -> None:
    # Counter-proof of the guard: the tail case the anchor was built for -- a reference title
    # without a level, last in its block, behind the chapter's last FINISHED sentence -- still
    # opens the section, and its entries up to the next heading are back matter.
    blocks = [
        DocumentBlock(
            paragraphs=[
                _unit("Closing thoughts", "p0000", role="heading", level=1),
                _unit(_PROSE, "p0001"),
                _unit("**Notes**", "p0002"),
            ]
        ),
        DocumentBlock(paragraphs=[_unit("1. Harbour Ledger, 2010.", "p0003", role="list")]),
        DocumentBlock(paragraphs=[_unit("2. Pilots' Almanac, 1999.", "p0004", role="list")]),
        DocumentBlock(paragraphs=[_unit("Acknowledgements", "p0005", role="heading", level=1), _unit(_PROSE, "p0006")]),
    ]

    fields = _fields_by_id(blocks, operation)

    assert fields["p0003"] == (PARAGRAPH_REGION_BACK_MATTER, BACK_MATTER_SECTION_NOTES)
    assert fields["p0004"] == (PARAGRAPH_REGION_BACK_MATTER, BACK_MATTER_SECTION_NOTES)
    assert fields["p0006"][0] != PARAGRAPH_REGION_BACK_MATTER
    assert fields["p0006"][1] is None
