"""Spec 059 — the warning about what left the AUDIOBOOK carries addresses, not only a count.

Measured defect (paid run ``20260809T_059_audio_money``, Money & Sustainability, en→ru,
``processing_operation=audiobook``, git 1b52ded): the screen published

    result.narration_omitted_paragraphs_excluded   {count: 8, chars: 4455}

with no address at all, while the message next to it about the DOCUMENT
(``result.source_text_delivered_with_unanchored``, ``{count: 10, blocks: 4, chars: 5050,
unanchored: 4}``) carried six searchable fragments for the very same paragraphs. A reader
who read only the audio warning knew the quantity and not the place.

Everything here is read off the run's own record — ``artifacts/audio_path_run_2026-08-09/``,
distilled from ``runtime.state.processed_paragraph_registry`` of the 97 MB report — and
asserted structurally: counts, set relations, catalog presence. Not one word of the book is
a rule (Constitution VII).

Spec 070 (research R7) changed what the audio channel reports. The audiobook no longer
withholds an empty answer or a restored paragraph — it narrates the paragraph's own source and
marks it ``needs_review`` — so the two loss families are gone and the audio notice is
``result.audiobook_needs_review``. The address machinery, its floor and the anti-duplication
rule against the document notice are the same and are tested here on the same recorded run.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

import docxaicorrector.pipeline.quality_gate as quality_gate
from docxaicorrector.generation._generation import (
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.ui import i18n

REPO_ROOT = Path(__file__).resolve().parents[1]
RECORDED_RUN = REPO_ROOT / "artifacts" / "audio_path_run_2026-08-09" / "money_sustainability"


# ---------------------------------------------------------------------------------------
# the recorded run, as data
# ---------------------------------------------------------------------------------------


def _recorded_paragraphs() -> list[dict[str, str]]:
    return json.loads((RECORDED_RUN / "source_text_paragraphs.json").read_text(encoding="utf-8"))


def _recorded_notice(message_key_prefix: str) -> dict[str, object]:
    notices = json.loads((RECORDED_RUN / "result_notices_before.json").read_text(encoding="utf-8"))
    return next(
        notice for notice in notices if str(notice["message_key"]).startswith(message_key_prefix)
    )


def _recorded_blocks() -> list[MarkerPreservedBlockText]:
    """The recorded paragraphs put back into the shape the pipeline hands finalization.

    One :class:`MarkerPreservedBlockText` per recorded ``block_index``, carrying exactly the
    per-paragraph record ``quality_gate.build_source_text_delivery_facts`` reads. The
    paragraphs the run ACCEPTED are not in the fixture and do not need to be: they contribute
    nothing to either channel, and the numbers below prove the reconstruction is faithful.
    """
    by_block: dict[int, list[ParagraphDisposition]] = {}
    for record in _recorded_paragraphs():
        by_block.setdefault(int(record["block_index"]), []).append(
            ParagraphDisposition(
                paragraph_id=str(record["paragraph_id"]),
                text=str(record["text"]),
                status=str(record["paragraph_status"]),
            )
        )
    return [
        MarkerPreservedBlockText(
            "\n\n".join(item.text for item in dispositions), tuple(dispositions)
        )
        for _, dispositions in sorted(by_block.items())
    ]


def _recorded_delivered_markdown() -> str:
    """A stand-in for the delivered markdown that contains every recorded paragraph.

    The real one is 512 458 characters of the book. What the anchor check asks of it is a
    single property — "is this paragraph still in what the reader will open" — and the
    recorded paragraph text IS the text the delivered markdown carries for that paragraph
    (both come from the same disposition), so joining them exercises the check on the same
    material without committing the whole book.
    """
    return "\n\n".join(str(record["text"]) for record in _recorded_paragraphs())


def _narration_records(status: str) -> list[dict[str, str]]:
    return [
        {"paragraph_id": str(record["paragraph_id"]), "text": str(record["text"])}
        for record in _recorded_paragraphs()
        if record["paragraph_status"] == status
    ]


def _disposition(paragraph_id: str, text: str, status: str) -> ParagraphDisposition:
    return ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=status)


def _params(notice: Mapping[str, object]) -> Mapping[str, object]:
    params = notice["params"]
    assert isinstance(params, Mapping)
    return params


def _anchors(notice: Mapping[str, object]) -> list[str]:
    anchors = notice.get("anchors") or []
    assert isinstance(anchors, Sequence)
    return [str(anchor) for anchor in anchors]


# ---------------------------------------------------------------------------------------
# the defect itself: the audio warning names what it lost
# ---------------------------------------------------------------------------------------


def test_recorded_run_narration_notice_names_the_paragraphs_to_check() -> None:
    """The measured message. 8 paragraphs / 4 455 characters left the audiobook then, with no
    address. Under spec 070 the same paragraphs are narrated and marked ``needs_review``, and
    the notice owes the reader the addresses — four of the eight give a searchable fragment and
    four are two characters long."""
    records = _narration_records("omitted")
    assert len(records) == 8
    assert sum(len(record["text"]) for record in records) == 4455

    facts = quality_gate.build_narration_exclusion_facts(
        records, delivered_markdown=_recorded_delivered_markdown()
    )

    assert facts["paragraph_count"] == 8
    assert facts["chars"] == 4455
    assert len(facts["anchors"]) == 4  # type: ignore[arg-type]
    assert facts["unanchored_paragraph_count"] == 4
    assert facts["anchors_dropped_not_in_delivered"] == 0

    notice = quality_gate.build_narration_exclusion_notice(
        facts,
        message_key_family=quality_gate.AUDIOBOOK_NEEDS_REVIEW_MESSAGE_KEY_FAMILY,
        count=8,
        chars=4455,
    )

    assert notice is not None
    assert notice["kind"] == "narration"
    assert notice["level"] == "warning"
    assert notice["message_key"] == "result.audiobook_needs_review_with_unanchored"
    assert _params(notice) == {"count": 8, "chars": 4455, "unanchored": 4}
    assert len(_anchors(notice)) == 4


def test_recorded_run_document_notice_hands_the_audio_addresses_over() -> None:
    """The duplication decision, on the run that forced it.

    Every paragraph the audiobook lost is also a paragraph of the DOCUMENT fact — ``omitted``
    is one of the two statuses that channel counts — so without a rule the two messages print
    the same fragments one after the other. The rule is ownership by PARAGRAPH: the message
    about the artifact with no editor between it and its consumer names the address, the
    document message keeps the paragraphs nobody else named and says where the rest are. Both
    counts stay whole: 10 paragraphs is still the truth about the DOCX.
    """
    claimed = {record["paragraph_id"] for record in _narration_records("omitted")}

    facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(),
        delivered_markdown=_recorded_delivered_markdown(),
        paragraph_ids_reported_in_narration=claimed,
    )

    assert facts["paragraph_count"] == 10
    assert facts["chars"] == 5050
    assert facts["block_count"] == 4
    assert facts["reported_in_narration_paragraph_count"] == 8
    assert len(facts["anchors"]) == 2  # type: ignore[arg-type]
    assert facts["unanchored_paragraph_count"] == 0

    notice = quality_gate.build_source_text_delivery_notice(
        facts, processing_operation="audiobook"
    )

    assert notice is not None
    # Spec 070 FR-001: the audiobook does not change the language, so a paragraph the model
    # gave back unchanged is UNEDITED, not untranslated -- the same family ``edit`` uses.
    assert notice["message_key"] == "result.unedited_text_delivered_with_addresses_in_narration"
    assert _params(notice) == {"count": 10, "blocks": 4, "chars": 5050, "elsewhere": 8}


def _replayed_audiobook_records() -> list[object]:
    """The recorded blocks put through the PRODUCTION audiobook finalization (spec 070).

    Each block is rebuilt as the document layer would hand it over: its source per paragraph
    and the FR-003 reason of each paragraph by the real form rule (the two-digit page numbers
    are fragments without connected text). No repair call is possible offline, so a paragraph
    with residue also carries ``repair_failed`` -- the first reason is the one asserted.
    """
    from docxaicorrector.document.narration_exclusion import is_fragment_without_connected_text
    from docxaicorrector.pipeline.audiobook_pass import (
        audiobook_block_paragraph_inputs,
        finalize_audiobook_block,
    )

    records: list[object] = []
    for block_index, block in enumerate(_recorded_blocks(), start=1):
        dispositions = block.paragraph_dispositions
        payload = SimpleNamespace(
            paragraph_ids=[item.paragraph_id for item in dispositions],
            target_text_with_markers="\n\n".join(
                f"[[DOCX_PARA_{item.paragraph_id}]]\n{item.text}" for item in dispositions
            ),
            narration_exclusion_reasons=[
                "fragment" if is_fragment_without_connected_text(item.text) else None for item in dispositions
            ],
        )
        finalized = finalize_audiobook_block(
            block_index=block_index,
            paragraphs=audiobook_block_paragraph_inputs(payload=payload, processed_chunk=block),
            repair=None,
        )
        records.extend(finalized.records)
    return records


def test_recorded_run_replayed_narrates_every_paragraph_it_used_to_withhold() -> None:
    """Spec 061 FR-006/008 and spec 070 R7 on the run that measured the defect.

    ``20260809T_059_audio_money`` withheld eight ``omitted`` paragraphs and spoke two
    ``source_restored`` ones. Replayed through today's audiobook pass, the four two-digit page
    numbers are ``fragment`` exclusions decided BEFORE the model (FR-003) and the other six are
    narrated from their own text, each with ``needs_review`` naming why, and each addressed
    once -- by the audio message, which the document message then defers to.
    """
    from docxaicorrector.document.narration_exclusion import is_fragment_without_connected_text

    records = _replayed_audiobook_records()

    first_reasons = [record.needs_review_reasons[0] for record in records]  # type: ignore[attr-defined]
    assert sorted(first_reasons) == sorted(["empty_answer"] * 4 + ["source_restored"] * 2)
    recorded_ids = {
        str(record["paragraph_id"])
        for record in _recorded_paragraphs()
        if not is_fragment_without_connected_text(str(record["text"]))
    }
    assert {record.paragraph_id for record in records} == recorded_ids  # type: ignore[attr-defined]

    paragraphs = [{"paragraph_id": r.paragraph_id, "text": r.text} for r in records]  # type: ignore[attr-defined]
    delivered = "\n\n".join(item["text"] for item in paragraphs)
    facts = quality_gate.build_narration_exclusion_facts(paragraphs, delivered_markdown=delivered)
    assert facts["paragraph_count"] == 6
    assert len(facts["anchors"]) == 6  # type: ignore[arg-type]

    document_facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(),
        delivered_markdown=_recorded_delivered_markdown(),
        paragraph_ids_reported_in_narration={item["paragraph_id"] for item in paragraphs},
    )
    # The document fact is still counted whole; its addresses defer to the audio message.
    assert document_facts["paragraph_count"] == 10
    assert document_facts["reported_in_narration_paragraph_count"] == 6


def test_the_two_messages_never_print_the_same_fragment_twice() -> None:
    """Two messages in a row carrying the same quotes read as an interface bug. On the
    recorded run the six addressable paragraphs split 4 (audio) + 2 (document only), and the
    two lists are disjoint by construction, not by luck."""
    delivered = _recorded_delivered_markdown()
    narration_facts = quality_gate.build_narration_exclusion_facts(
        _narration_records("omitted"), delivered_markdown=delivered
    )
    document_facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(),
        delivered_markdown=delivered,
        paragraph_ids_reported_in_narration={
            record["paragraph_id"] for record in _narration_records("omitted")
        },
    )

    narration_anchors = [str(anchor) for anchor in narration_facts["anchors"]]  # type: ignore[union-attr]
    document_anchors = [str(anchor) for anchor in document_facts["anchors"]]  # type: ignore[union-attr]

    assert not set(narration_anchors) & set(document_anchors)
    # ...and together they still address every paragraph that HAS an address: 6 of 10.
    assert len(narration_anchors) + len(document_anchors) == 6


def test_recorded_run_without_narration_publishes_every_address_in_the_document_notice() -> None:
    """The other side of the same rule (anti-regression): with nothing claimed by an audio
    message — every ``translate``/``edit`` run — the document message keeps ALL SIX addresses,
    the same key and the same numbers the recorded run published.

    The anchor TEXTS are deliberately not byte-identical any more: each is now its
    paragraph's first sentence. That is asserted as a relation to the recorded value —
    same paragraph, shortened — rather than dropped, because "we still address exactly the
    paragraphs the run addressed" is the property this test exists to hold.
    """
    published = _recorded_notice("result.source_text_delivered")
    published_anchors = [str(anchor) for anchor in published["anchors"]]  # type: ignore[union-attr]

    facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(), delivered_markdown=_recorded_delivered_markdown()
    )

    assert facts["reported_in_narration_paragraph_count"] == 0
    assert facts["unanchored_paragraph_count"] == 4
    anchors = [str(anchor) for anchor in facts["anchors"]]  # type: ignore[union-attr]
    assert len(anchors) == len(published_anchors) == 6
    for anchor, recorded in zip(anchors, published_anchors):
        assert recorded.startswith(anchor)

    notice = quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
    assert notice is not None
    assert notice["message_key"] == published["message_key"]
    assert _params(notice) == published["params"]


# ---------------------------------------------------------------------------------------
# anti-vacuum, both directions
# ---------------------------------------------------------------------------------------


def test_nothing_left_the_audiobook_means_no_message_at_all() -> None:
    """A message that is always on screen is noise. Zero excluded paragraphs is the ABSENCE
    of the notice, never a notice carrying a zero — the same shape the block-level twin has
    had since spec 054. On the recorded run the block-level family is exactly this case."""
    summary = (RECORDED_RUN / "run_summary.txt").read_text(encoding="utf-8")
    assert "narration_excluded_source_fallback_block_count=0" in summary

    facts = quality_gate.build_narration_exclusion_facts([])

    assert facts["paragraph_count"] == 0
    assert facts["chars"] == 0
    assert (
        quality_gate.build_narration_exclusion_notice(
            facts,
            message_key_family=quality_gate.AUDIOBOOK_NEEDS_REVIEW_MESSAGE_KEY_FAMILY,
            count=0,
            chars=0,
        )
        is None
    )


def test_a_lost_paragraph_with_no_usable_fragment_is_counted_not_printed() -> None:
    """Constitution VII / anti-regression #14: no address is invented. Four of the eight
    paragraphs of the recorded run are two characters long, which is below the SAME usability
    floor the document message uses, so they are counted and never printed as empty «»."""
    records = [
        {"paragraph_id": "p1", "text": "44"},
        {"paragraph_id": "p2", "text": "**a**"},
    ]

    facts = quality_gate.build_narration_exclusion_facts(records)

    assert facts["paragraph_count"] == 2
    assert facts["anchors"] == []
    assert facts["unanchored_paragraph_count"] == 2

    notice = quality_gate.build_narration_exclusion_notice(
        facts,
        message_key_family=quality_gate.AUDIOBOOK_NEEDS_REVIEW_MESSAGE_KEY_FAMILY,
        count=2,
        chars=7,
    )

    assert notice is not None
    assert notice["message_key"] == "result.audiobook_needs_review_without_anchors"
    assert _params(notice) == {"count": 2, "chars": 7, "unanchored": 2}
    assert _anchors(notice) == []


def test_the_anchor_is_the_first_sentence_not_the_whole_paragraph() -> None:
    """An address the reader cannot use is not an address.

    The recorded run's longest excluded paragraph is 2 686 characters, and printing it whole
    turned "search for this" into a second hunt — and a warning that long is a warning nobody
    finishes reading, which is the invisibility this spec exists to end, re-created by another
    route. The cut is a SENTENCE boundary — a structural fact — and the splitter is the one
    the degradation ladder already owns (``generation._ladder_sentences``), not a length.
    """
    records = [
        {
            "paragraph_id": "p1",
            "text": (
                "Footnotes 1 Marchant and Keswick on coastal lanterns. "
                "2 For examples at a harbour scale, see in particular the later volume. "
                "3 Odell and Varnham on the same question."
            ),
        }
    ]

    facts = quality_gate.build_narration_exclusion_facts(records)

    assert facts["anchors"] == ["Footnotes 1 Marchant and Keswick on coastal lanterns."]
    # ...and the paragraph is still counted in full: what was shortened is the ADDRESS.
    assert facts["chars"] == len(records[0]["text"])


def test_an_abbreviation_does_not_shorten_the_address() -> None:
    """The ``20261107T_061_audio_money`` run printed an eight-letter surname and "et al." —
    15 characters, cut at the abbreviation — as the address of a paragraph whose first sentence runs on to the
    year. The splitter now reads the abbreviation's FORM (short lowercase token, lowercase or
    digit after it), so the address is the whole first sentence and is still found in the
    delivered text, emphasis and all."""
    text = (
        "Marchant *et al.* (2004). 7 Ansel Varden-Keswick and Peter Odell, "
        "‘Sailing Beyond Harbour III’."
    )
    records = [{"paragraph_id": "p1", "text": text}]

    facts = quality_gate.build_narration_exclusion_facts(records, delivered_markdown=text)

    assert facts["anchors"] == ["Marchant et al. (2004)."]
    assert facts["unanchored_paragraph_count"] == 0


def test_recorded_run_anchors_are_each_exactly_one_sentence() -> None:
    """The same rule on the material that forced it. Structural assertion, no length
    literal: every anchor the recorded run would print is one sentence, and the longest
    address is now shorter than the longest paragraph it addresses."""
    from docxaicorrector.generation._generation import _ladder_sentences

    delivered = _recorded_delivered_markdown()
    narration_facts = quality_gate.build_narration_exclusion_facts(
        _narration_records("omitted"), delivered_markdown=delivered
    )
    document_facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(),
        delivered_markdown=delivered,
        paragraph_ids_reported_in_narration={
            record["paragraph_id"] for record in _narration_records("omitted")
        },
    )
    anchors = [str(anchor) for anchor in narration_facts["anchors"]] + [  # type: ignore[union-attr]
        str(anchor)
        for anchor in document_facts["anchors"]  # type: ignore[union-attr]
    ]

    assert len(anchors) == 6
    for anchor in anchors:
        assert _ladder_sentences(anchor) == [anchor]
    longest_paragraph = max(len(str(record["text"])) for record in _recorded_paragraphs())
    assert max(len(anchor) for anchor in anchors) < longest_paragraph


def test_a_first_sentence_below_the_usability_floor_is_counted_not_printed() -> None:
    """The floor is applied AFTER the shortening, and it is the same floor: a first sentence
    of two visible characters is not printed as a stub, it goes to the counter. The order
    matters — checking the floor first would pass a paragraph on the strength of characters
    the printed address does not contain."""
    records = [{"paragraph_id": "p1", "text": "A. Then a sentence that would have passed."}]

    facts = quality_gate.build_narration_exclusion_facts(records)

    assert facts["anchors"] == []
    assert facts["unanchored_paragraph_count"] == 1


def test_a_paragraph_that_is_one_long_sentence_keeps_that_sentence_whole() -> None:
    """The declared edge. Nothing is cut INSIDE a sentence, however long it is, because every
    mid-sentence cut needs a length and every length here would be a number picked by eye
    (Constitution VII). Borrowing the ladder's own budget constant was considered and
    refused: it measures what a MODEL can be asked to answer, not what a human can search
    for. A single enormous sentence therefore prints whole — visibly odd, honestly odd, and
    it never invents an address."""
    one_sentence = "A single clause that runs on and on and never reaches a full stop"
    records = [{"paragraph_id": "p1", "text": one_sentence}]

    facts = quality_gate.build_narration_exclusion_facts(records)

    assert facts["anchors"] == [one_sentence]


def test_the_delivered_check_is_applied_to_the_address_that_is_printed() -> None:
    """The check asks "will the reader's search succeed", so it asks it of the SHORTENED
    form. A paragraph whose tail cleanup rewrote is still findable by its first sentence; a
    paragraph whose first sentence is gone is not offered at all."""
    tail_rewritten = {
        "paragraph_id": "p1",
        "text": "Footnotes 1 Marchant and Keswick. A tail that cleanup rewrote entirely.",
    }
    deleted = {"paragraph_id": "p2", "text": "A paragraph cleanup deleted. With two sentences."}

    facts = quality_gate.build_narration_exclusion_facts(
        [tail_rewritten, deleted],
        delivered_markdown="Footnotes 1 Marchant and Keswick. Кое-что ещё.",
    )

    assert facts["anchors"] == ["Footnotes 1 Marchant and Keswick."]
    assert facts["unanchored_paragraph_count"] == 1
    assert facts["anchors_dropped_not_in_delivered"] == 1


# A delivered document in which an UNPAIRED asterisk in one paragraph (a literal "2*n") sits
# before an emphasised title in the next. Emphasis never crosses a blank line in markdown,
# but the stripper, run over the whole document as one string, pairs the first paragraph's
# asterisk with the title's closing one and leaves the title's opening asterisk behind —
# the shape of the ``20261107T_061_audio_money`` miss (a two-word title delivered with its
# opening asterisk, bare in the anchor; the title here is synthetic).
_STRAY_ASTERISK_DELIVERED = (
    "A formula with a literal 2*n in it.\n\n"
    "Footnotes 1 Quoted in Mara Keswick, *No Tide* (2000), p.325. 2 See Appendix A."
)


def test_the_delivered_text_is_normalised_paragraph_by_paragraph() -> None:
    """The anchor is sanitised one paragraph at a time, so the delivered text it is looked
    up in must be too — otherwise the stripper pairs asterisks across paragraphs and a
    perfectly usable first sentence is reported as an address the document no longer has."""
    records = [
        {
            "paragraph_id": "p1",
            "text": "Footnotes 1 Quoted in Mara Keswick, *No Tide* (2000), p.325. 2 See Appendix A.",
        }
    ]

    facts = quality_gate.build_narration_exclusion_facts(
        records, delivered_markdown=_STRAY_ASTERISK_DELIVERED
    )

    assert facts["anchors"] == ["Footnotes 1 Quoted in Mara Keswick, No Tide (2000), p.325."]
    assert facts["unanchored_paragraph_count"] == 0
    assert facts["anchors_dropped_not_in_delivered"] == 0


def test_the_stray_asterisk_fixture_really_breaks_whole_string_normalisation() -> None:
    """Counter-proof that the test above is not vacuous: normalising the same delivered text
    as ONE string — the previous behaviour — does leave the stray asterisk, so the anchor is
    absent from it."""
    whole = quality_gate._review_anchor_visible_text(" ".join(_STRAY_ASTERISK_DELIVERED.split()))

    assert "*No Tide" in whole
    assert "Footnotes 1 Quoted in Mara Keswick, No Tide (2000), p.325." not in whole


def test_per_paragraph_normalisation_still_withholds_an_address_that_is_gone() -> None:
    """Anti-vacuum: normalising per paragraph must not turn the delivered check into a
    pass-everything. An anchor that is genuinely absent from the delivered text is still
    withheld and still counted."""
    records = [
        {
            "paragraph_id": "p1",
            "text": "Footnotes 1 Quoted in Mara Keswick, *No Tide* (2000), p.325. 2 See Appendix A.",
        },
        {"paragraph_id": "p2", "text": "A *paragraph* reader cleanup removed. Its second sentence."},
    ]

    facts = quality_gate.build_narration_exclusion_facts(
        records, delivered_markdown=_STRAY_ASTERISK_DELIVERED
    )

    assert facts["anchors"] == ["Footnotes 1 Quoted in Mara Keswick, No Tide (2000), p.325."]
    assert facts["unanchored_paragraph_count"] == 1
    assert facts["anchors_dropped_not_in_delivered"] == 1


def test_an_address_the_delivered_document_no_longer_contains_is_withheld() -> None:
    """The reader is sent to the DOCX to find what the audio lost, so an anchor that reader
    cleanup deleted or rewrote is a WRONG address — worse than none, because the reader
    spends the trip. The paragraph is still counted; only its address is withheld."""
    records = [
        {"paragraph_id": "p1", "text": "Footnotes 1 Marchant and Keswick on coastal lanterns."},
        {"paragraph_id": "p2", "text": "A paragraph reader cleanup removed from the document."},
    ]

    facts = quality_gate.build_narration_exclusion_facts(
        records, delivered_markdown=records[0]["text"]
    )

    assert facts["paragraph_count"] == 2
    assert len(facts["anchors"]) == 1  # type: ignore[arg-type]
    assert facts["unanchored_paragraph_count"] == 1
    assert facts["anchors_dropped_not_in_delivered"] == 1


def test_a_fully_narrated_run_leaves_the_document_message_untouched() -> None:
    """The claim is a claim, not a default: when the audio message names nothing, the
    document message keeps every anchor and its existing key."""
    blocks = [
        MarkerPreservedBlockText(
            "Long ago and far off in a village.",
            (_disposition("p1", "Long ago and far off in a village.", "source_restored"),),
        )
    ]

    facts = quality_gate.build_source_text_delivery_facts(
        blocks, paragraph_ids_reported_in_narration=()
    )
    notice = quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")

    assert facts["reported_in_narration_paragraph_count"] == 0
    assert notice is not None
    assert notice["message_key"] == "result.source_text_delivered"


# ---------------------------------------------------------------------------------------
# one mechanism, not two
# ---------------------------------------------------------------------------------------


def _quality_gate_module_ast() -> ast.Module:
    source = Path(quality_gate.__file__).read_text(encoding="utf-8")
    return ast.parse(source)


def _functions_calling(name: str) -> set[str]:
    module = _quality_gate_module_ast()
    callers: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
                if inner.func.id == name:
                    callers.add(node.name)
    return callers


def test_both_channels_share_one_sanitizer_and_one_usability_floor() -> None:
    """The audio message reuses the machinery the document message already had; a second
    sanitiser or a second threshold in the repository would be the defect, not the fix.

    Written as a structural guard rather than a comment because "we reused it" is exactly
    the claim that rots: the two builders must both go through the one collector.
    """
    assert _functions_calling("_collect_paragraph_anchor_facts") == {
        "build_source_text_delivery_facts",
        "build_narration_exclusion_facts",
    }
    # The floor and the sanitiser are reachable from exactly two places: the formatting
    # review item (which predates both channels) and the shared collector.
    assert _functions_calling("_review_anchor_visible_char_count") == {
        "_build_formatting_review_item",
        "_collect_paragraph_anchor_facts",
    }
    assert _functions_calling("_sanitize_review_anchor_text") == {
        "_build_formatting_review_item",
        "_collect_paragraph_anchor_facts",
    }
    # The sentence boundary is the degradation ladder's, reached by IMPORT and not by copy —
    # a third way of dividing text in this repository would be the same defect one level
    # down, and a copied regex would drift silently.
    from docxaicorrector.generation import _generation

    assert quality_gate._ladder_sentences is _generation._ladder_sentences
    assert _functions_calling("_ladder_sentences") == {"_collect_paragraph_anchor_facts"}


# ---------------------------------------------------------------------------------------
# the catalogs see every key, including the ones no literal `t("…")` mentions
# ---------------------------------------------------------------------------------------


def _catalog(name: str) -> dict[str, str]:
    path = Path(i18n.__file__).resolve().parent / "locales" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_every_message_key_the_two_channels_can_emit_exists_in_both_catalogs() -> None:
    """The old guard collects keys with a regex over ``t("literal")`` and cannot see a key
    the pipeline assembles from a family and a suffix — it would stay green while the screen
    printed ``result.narration_omitted_paragraphs_excluded_with_unanchored`` verbatim. The
    families and the suffixes are a closed enumeration owned by ``quality_gate``; the guard
    enumerates them from there (same shape as the acceptance-check guard, FR-B3)."""
    expected = set(quality_gate.result_notice_message_keys())
    assert len(expected) == 17, sorted(expected)

    ru = _catalog("ru.json")
    en = _catalog("en.json")
    assert not sorted(expected - set(ru)), sorted(expected - set(ru))
    assert not sorted(expected - set(en)), sorted(expected - set(en))


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_every_message_key_renders_the_params_its_builder_sends(
    monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:
    """A template whose placeholders do not match the emitted params ships raw braces."""
    monkeypatch.setattr(i18n, "get_ui_language", lambda: lang)
    i18n.clear_catalog_cache()
    try:
        for key in quality_gate.result_notice_message_keys():
            message = i18n.t(
                key, count=8, chars=4455, blocks=4, unanchored=4, elsewhere=8, anchors="«X»"
            )
            assert "{" not in message, key
            assert message != key, key
    finally:
        i18n.clear_catalog_cache()
