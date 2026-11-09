"""Spec 069 FR-005 (c) -- the untranslated-body gate reads a run of chapter-end notes per ENTRY.

A notes run (spec 067 FR-001, ``output_validation.notes_run_parts``) mixes references, which
decision D1 of spec 063 keeps in the source language, and the author's commentary, which is
translated. Until this spec the gate judged such a paragraph WHOLE, so the result depended on
a whole-paragraph shortcut: with an address in it, a long run of correctly kept references
read as "not bibliography" and was counted (``quality_gate_text_detectors``, the URL branch
of ``_is_bibliography_or_url_dominant_text``); with three bibliographic hits and no address,
a real untranslated comment inside the run was hidden. Replayed on the bake-off of spec 063
(``research.md`` R4): Gemini variants of Money ch. III 1 993-2 036 characters, all of them
kept references.

The rule: for a delivered paragraph that is a notes run by form, the gate counts only its
UNTRANSLATED PART -- the lead and the entries whose letters are at least 80 % Latin (the share
the paragraph test uses) and which are not a reference by the per-entry test of spec 067
(``is_citation_form_paragraph`` AND ``has_citation_anchor``). The same floors apply to that
part (280 characters, 30 Latin words per sample; 2 000 characters and 2 % per document), and
the sample's ``char_count`` is its length. Every other paragraph takes the old path.

This rule SUBTRACTS from the defect count (Constitution VII), so it carries its anti-vacuum
half: a run whose commentary stayed English is still counted and still blocks the document.

All texts below are invented, of the same form as the bake-off paragraphs; no book text.
"""

from __future__ import annotations

from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline import quality_gate
from docxaicorrector.pipeline import quality_gate_text_detectors


class _Context:
    def __init__(self, operation: str = "translate") -> None:
        self.processing_operation = operation
        self.uploaded_filename = "book.docx"
        self.app_config = {"translation_output_quality_gate_policy": "advisory"}


def _report(*texts: str, operation: str = "translate") -> dict:
    entries = tuple(
        output_validation.FinalAssemblyEntry(
            text=text,
            block_index=1,
            paragraph_id=f"p{index:04d}",
            source_index=index,
            role="body",
            structural_role="body",
            from_registry=True,
        )
        for index, text in enumerate(texts)
    )
    assembly = output_validation.FinalMarkdownAssemblyResult(
        final_markdown="\n\n".join(entry.text for entry in entries),
        entries=entries,
        diagnostics=output_validation.FinalAssemblyDiagnostics(),
    )
    return quality_gate._build_translation_quality_report(
        context=_Context(operation),
        final_markdown=assembly.final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly,
        runtime_display_markdown=assembly.final_markdown,
    )


# --- invented texts --------------------------------------------------------------------------

_REFERENCE_ONE = "R. Hall, *The Harbour Ledger: Annual Review* (Kelbrook: Tidewater Press, 2011), p. 14."
_REFERENCE_THREE = "J. Smith and K. Lee, ‘Credit and the Tide’, *Journal of Harbour Studies* 12(3), pp. 4-19."
# Commentary of a note: running words, no citation anchor.
_COMMENT_EN = (
    "The lantern survey of the northern ports estimates the tonnage moved through the three quays at roughly "
    "four hundred million a year, a figure the guild never published and its own clerks disputed for a decade, "
    "arguing that half of the cargo was counted twice when it changed hands on the water and that the rest was "
    "never weighed at all, so the number should be read as a rough ceiling and not as a measurement."
)
_COMMENT_RU = (
    "По оценке обзора северных портов, через три причала проходит около четырёхсот миллионов тонн груза в год; "
    "гильдия эту цифру не публиковала, а её собственные писари оспаривали её десять лет."
)
# References kept by D1 + one English comment of 280+ characters (the form of a run whose
# comment the model left in the source language). No address, three bibliographic hits: the
# whole-paragraph test called it "bibliography" and counted nothing.
_RUN_WITH_ENGLISH_COMMENT = f"1 {_REFERENCE_ONE} 2 {_COMMENT_EN} 3 {_REFERENCE_THREE}"
_RUN_WITH_TRANSLATED_COMMENT = f"1 {_REFERENCE_ONE} 2 {_COMMENT_RU} 3 {_REFERENCE_THREE}"
# A run of references only, every one with a web address, 60+ words: correctly kept under D1,
# and counted whole by the URL branch until this spec.
_RUN_OF_REFERENCES_WITH_ADDRESSES = (
    "4 Bureau of Harbour Statistics, ‘Quarterly Bulletin of Port Traffic and Tonnage’, Kelbrook, March 2012, "
    "available at www.harbourstats.example.org/bulletin/quarterly. "
    "5 Northern Guild of Pilots, *Annual Register of Licensed Pilots and Their Vessels* (Kelbrook: Guild Press, 2010), "
    "pp. 12-40, www.pilotsguild.example.org/register. "
    "6 Tidewater Council, ‘Report of the Standing Committee on Harbour Dues and Mooring Charges’, "
    "Kelbrook, June 2011, www.tidewater.example.org/reports/dues. "
    f"7 {_REFERENCE_ONE[:-1]}, www.ledger.example.org."
)
# Form D of the bake-off: definitions quoted in a note and left in English, behind a
# translated lead-in. Two long commentary entries and one reference between them.
_DEFINITION_EN = (
    "in a systemic harbour crisis, the pilots, the merchants and the warehouse keepers of a port all miss their "
    "tides and their contracts at the same time, and the guild that stands behind them finds it very hard to "
    "settle its debts when they fall due. The price of a berth then falls for months on end, the charges for "
    "mooring rise sharply, and the deposits held by the harbour masters are drawn out faster than any single "
    "guild can replace them. In some ports the crisis starts with a run on the harbour treasury, in others with "
    "the slow failure of a few large trading houses that the smaller ones had trusted with their savings, and "
    "in a few it starts with nothing more than a rumour carried along the quays by the evening boats."
)
_NARROWED_EN = (
    "The council later narrowed the definition, because under the first wording almost every winter of the "
    "century would have counted as a crisis. It now asks for two things at once: that more than a third of the "
    "berths of a port stand empty for a whole season, and that the guild must borrow from another port to pay "
    "the pilots it already owes. Several of the older masters objected that this left out the quiet years in "
    "which the trade simply drifted away to the southern coast, and the council answered that such a drift was "
    "a decline and not a crisis, which is the distinction the rest of this chapter keeps in view."
)
_SECOND_DEFINITION_EN = (
    "A banking panic in the ports is defined more narrowly still: the moment when the depositors of a harbour "
    "treasury try, all on one morning, to take back in coin what they had left there as a promise, and the "
    "treasury can pay only the first few dozen of them before it closes its doors. The council counts such a "
    "morning even when the treasury opens again within the week, since the fear it leaves behind on the quays "
    "lasts much longer than the queue, and the pilots who stood in that queue remember it for the rest of "
    "their working lives and tell it to every apprentice who joins the guild after them. A morning on which "
    "the treasury pays everyone who asks, however long the queue, is not counted at all, and the council "
    "says so plainly in the margin of its own register."
)
_RUN_WITH_ENGLISH_DEFINITIONS = (
    f"8 Это определение Совета гаваней: “{_DEFINITION_EN}” "
    "9 R. Hall, *Tides of Credit* (London: Harbour Press, 2004), p. 85. "
    f"10 {_NARROWED_EN} "
    f"11 {_SECOND_DEFINITION_EN}"
)
# An ordinary paragraph of English prose with a web address and 40+ Latin words.
_PLAIN_PARAGRAPH_WITH_ADDRESS = (
    "The company kept the same policy for another year and nobody in the office was willing to explain why the "
    "numbers had moved so far away from the plan that everyone had signed in the spring, so the meeting ended "
    "without a decision and the team went back to work on the parts of the product that were still moving, "
    "as the minutes posted at www.example.org/minutes later confirmed for anyone who cared to read them."
)
_TRANSLATED_PROSE = "Гавань — не место, а договорённость между лоцманами считать часть воды укрытием от бури."


def _body_samples(report: dict) -> list[dict]:
    return list(report["untranslated_body_text_samples"])


# =============================================================================================
# A. Characterisation: what does NOT change (green before and after the rule)
# =============================================================================================


def test_the_floors_of_a_sample_and_of_the_document_are_unchanged() -> None:
    assert quality_gate_text_detectors._UNTRANSLATED_BODY_MIN_CHARS == 280
    assert quality_gate_text_detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS == 30
    assert quality_gate_text_detectors._UNTRANSLATED_BODY_FAIL_MIN_CHARS == 2000
    assert quality_gate_text_detectors._UNTRANSLATED_BODY_FAIL_RATIO == 0.02


def test_an_ordinary_paragraph_with_an_address_is_counted_whole_as_before() -> None:
    assert output_validation.notes_run_parts(_PLAIN_PARAGRAPH_WITH_ADDRESS) is None  # not a notes run
    report = _report(_TRANSLATED_PROSE, _PLAIN_PARAGRAPH_WITH_ADDRESS)

    samples = _body_samples(report)
    assert [sample["paragraph_id"] for sample in samples] == ["p0001"]
    assert samples[0]["char_count"] == len(_PLAIN_PARAGRAPH_WITH_ADDRESS)
    assert report["untranslated_body_text_chars"] == len(_PLAIN_PARAGRAPH_WITH_ADDRESS)
    assert "untranslated_body_text_review_required" in report["gate_reasons"]


def test_a_run_whose_comment_was_translated_gives_no_sample() -> None:
    assert output_validation.is_notes_run_paragraph(_RUN_WITH_TRANSLATED_COMMENT) is True
    report = _report(_TRANSLATED_PROSE, _RUN_WITH_TRANSLATED_COMMENT)

    assert _body_samples(report) == []
    assert report["untranslated_body_text_chars"] == 0


def test_anti_vacuum_a_run_with_english_definitions_still_blocks_the_document() -> None:
    """T5.4. Green before AND after the rule: the per-entry reading subtracts the kept
    reference and nothing else, and what remains still crosses both document thresholds.
    It fails on a gate that skips notes runs whole -- checked once with a temporary stub when
    the rule was built, and kept honest by the next test, which pins what the part holds."""
    assert output_validation.is_notes_run_paragraph(_RUN_WITH_ENGLISH_DEFINITIONS) is True
    report = _report(_TRANSLATED_PROSE, _RUN_WITH_ENGLISH_DEFINITIONS)

    samples = _body_samples(report)
    assert [sample["paragraph_id"] for sample in samples] == ["p0001"]
    assert samples[0]["char_count"] >= quality_gate_text_detectors._UNTRANSLATED_BODY_FAIL_MIN_CHARS
    assert report["untranslated_body_text_ratio"] >= quality_gate_text_detectors._UNTRANSLATED_BODY_FAIL_RATIO
    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]


def test_anti_vacuum_the_english_definitions_block_outside_a_document_of_prose_too() -> None:
    """The same run among several translated paragraphs: the ratio is taken over the whole
    delivered markdown, which this spec does not change."""
    report = _report(*([_TRANSLATED_PROSE] * 20), _RUN_WITH_ENGLISH_DEFINITIONS)

    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]


# =============================================================================================
# B. The new reading (red on main)
# =============================================================================================


def test_a_run_with_one_english_comment_is_counted_by_that_comment_only() -> None:
    """T5.2: the comment is a real defect and is counted; the references beside it are not."""
    assert len(_COMMENT_EN) >= quality_gate_text_detectors._UNTRANSLATED_BODY_MIN_CHARS
    report = _report(_TRANSLATED_PROSE, _RUN_WITH_ENGLISH_COMMENT)

    samples = _body_samples(report)
    assert [sample["paragraph_id"] for sample in samples] == ["p0001"]
    assert samples[0]["char_count"] == len(_COMMENT_EN)
    assert report["untranslated_body_text_chars"] == len(_COMMENT_EN)
    # The anchor a reviewer searches for is still the delivered paragraph.
    assert samples[0]["text"] == _RUN_WITH_ENGLISH_COMMENT
    assert "untranslated_body_text_review_required" in report["gate_reasons"]


def test_a_run_of_kept_references_with_addresses_gives_no_sample() -> None:
    """T5.3: references kept under D1 are the right answer, address or not."""
    assert len(quality_gate_text_detectors._LATIN_WORD_PATTERN.findall(_RUN_OF_REFERENCES_WITH_ADDRESSES)) >= 60
    assert output_validation.notes_run_reads_as_citations(_RUN_OF_REFERENCES_WITH_ADDRESSES) is True
    report = _report(_TRANSLATED_PROSE, _RUN_OF_REFERENCES_WITH_ADDRESSES)

    assert _body_samples(report) == []
    assert report["untranslated_body_text_chars"] == 0
    assert not {
        "untranslated_body_text_review_required",
        "untranslated_body_text_above_threshold",
    } & set(report["gate_reasons"])


def test_the_english_definitions_are_counted_without_the_reference_between_them() -> None:
    """The part counted for form D is exactly its two commentary entries."""
    report = _report(_TRANSLATED_PROSE, _RUN_WITH_ENGLISH_DEFINITIONS)

    part = output_validation.notes_run_untranslated_part(_RUN_WITH_ENGLISH_DEFINITIONS)
    assert part is not None
    assert "Tides of Credit" not in part
    assert _DEFINITION_EN in part and _NARROWED_EN in part
    assert _body_samples(report)[0]["char_count"] == len(part)


# --- the per-entry part, on its own ----------------------------------------------------------


def test_the_untranslated_part_is_the_english_comment_and_nothing_else() -> None:
    assert output_validation.notes_run_untranslated_part(_RUN_WITH_ENGLISH_COMMENT) == _COMMENT_EN
    assert output_validation.notes_run_untranslated_part(_RUN_WITH_TRANSLATED_COMMENT) == ""
    assert output_validation.notes_run_untranslated_part(_RUN_OF_REFERENCES_WITH_ADDRESSES) == ""


def test_the_untranslated_part_is_none_outside_a_notes_run() -> None:
    assert output_validation.notes_run_untranslated_part(_PLAIN_PARAGRAPH_WITH_ADDRESS) is None
    assert output_validation.notes_run_untranslated_part(_COMMENT_EN) is None


def test_an_english_label_in_front_of_the_run_is_part_of_what_is_counted() -> None:
    """The lead is not a reference unless it reads as one: a label of the apparatus is
    translated under D1, so left in English it belongs to the untranslated part."""
    labelled = f"Footnotes 1 {_REFERENCE_ONE} 2 {_COMMENT_EN} 3 {_REFERENCE_THREE}"
    assert output_validation.notes_run_untranslated_part(labelled) == f"Footnotes {_COMMENT_EN}"
