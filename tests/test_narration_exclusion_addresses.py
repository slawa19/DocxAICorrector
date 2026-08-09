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
"""

from __future__ import annotations

import ast
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

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


def test_recorded_run_narration_notice_names_the_paragraphs_it_lost() -> None:
    """The measured message. 8 paragraphs / 4 455 characters left the audiobook, and until
    this spec that was the whole of it. The addresses exist — four of the eight give a
    searchable fragment and four are two characters long — so the message owes the reader
    both numbers and the four fragments."""
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
        message_key_family="result.narration_omitted_paragraphs_excluded",
        count=8,
        chars=4455,
    )

    assert notice is not None
    assert notice["kind"] == "narration"
    assert notice["level"] == "warning"
    assert notice["message_key"] == "result.narration_omitted_paragraphs_excluded_with_unanchored"
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
    assert notice["message_key"] == "result.source_text_delivered_with_addresses_in_narration"
    assert _params(notice) == {"count": 10, "blocks": 4, "chars": 5050, "elsewhere": 8}


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
    message — every ``translate``/``edit`` run — the document message is byte-identical to
    what the recorded run published, six anchors and all."""
    published = _recorded_notice("result.source_text_delivered")

    facts = quality_gate.build_source_text_delivery_facts(
        _recorded_blocks(), delivered_markdown=_recorded_delivered_markdown()
    )

    assert facts["reported_in_narration_paragraph_count"] == 0
    assert facts["anchors"] == published["anchors"]
    assert facts["unanchored_paragraph_count"] == 4

    notice = quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
    assert notice is not None
    assert notice["message_key"] == published["message_key"]
    assert _params(notice) == published["params"]
    assert _anchors(notice) == published["anchors"]


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
            message_key_family="result.narration_source_fallback_excluded",
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
        message_key_family="result.narration_omitted_paragraphs_excluded",
        count=2,
        chars=7,
    )

    assert notice is not None
    assert notice["message_key"] == "result.narration_omitted_paragraphs_excluded_without_anchors"
    assert _params(notice) == {"count": 2, "chars": 7, "unanchored": 2}
    assert _anchors(notice) == []


def test_an_address_the_delivered_document_no_longer_contains_is_withheld() -> None:
    """The reader is sent to the DOCX to find what the audio lost, so an anchor that reader
    cleanup deleted or rewrote is a WRONG address — worse than none, because the reader
    spends the trip. The paragraph is still counted; only its address is withheld."""
    records = [
        {"paragraph_id": "p1", "text": "Footnotes 1 Lietaer and Kennedy on complementary currencies."},
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
            "Once upon a time in a small village.",
            (_disposition("p1", "Once upon a time in a small village.", "source_restored"),),
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
    assert len(expected) == 20, sorted(expected)

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
