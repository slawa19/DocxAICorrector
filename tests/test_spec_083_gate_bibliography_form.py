"""Spec 083 -- what the three-hits bibliography shortcut hides becomes a REVIEW finding; the fatal count is unchanged.

``quality_gate_text_detectors._is_bibliography_or_url_dominant_text`` skips any paragraph with three
bibliographic hits -- a four-digit number counts as one -- so an English prose paragraph that mentions three
years and came back untranslated is not counted. Three rounds of form rules tried to make the FATAL count see it
and every round made a correctly kept reference list fail a correct translation (acceptance reviews of spec 083,
rounds 1 and 2). So the fatal count stays exactly as it was, and the paragraphs the shortcut hides that read as
prose by the existing share test are LISTED for a person: the existing non-fatal reason
``untranslated_body_text_review_required`` (``warn`` at most) and one review item per paragraph.

All texts are invented.
"""

from __future__ import annotations

from types import SimpleNamespace

from docxaicorrector.core.models import PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline import quality_gate
from docxaicorrector.pipeline import quality_gate_text_detectors as detectors

_POSSIBLE = quality_gate.UNTRANSLATED_BODY_POSSIBLE_SAMPLE_REASON

# English prose that mentions three years: no address, no numbered chain, nothing else bibliographic.
_PROSE_WITH_YEARS = (
    "The harbour guild of Kelbrook rebuilt its northern quay in 1987, after a winter of storms had left half of "
    "the old timber piles leaning into the channel. The new stone wall held for a long time, but the pilots kept "
    "complaining that the entrance was too narrow for the larger boats, and in 1994 the council finally agreed to "
    "widen it. The work dragged on for years and was only finished in 2003, when the last of the old moorings was "
    "pulled out and sold for firewood."
)
_PROSE_WITH_YEARS_RU = (
    "Гильдия гавани Келбрука перестроила северный причал в 1987 году, после зимы штормов, когда половина старых "
    "деревянных свай накренилась в сторону фарватера. Новая каменная стена держалась долго, но лоцманы всё "
    "жаловались, что вход слишком узок для больших лодок, и в 1994 году совет наконец согласился его расширить. "
    "Работы тянулись годами и закончились лишь в 2003 году, когда последние старые причальные тумбы выдернули и "
    "продали на дрова."
)
# A note made of references as D1 keeps it: names, capitalised titles, places, publishers, years and pages.
_REFERENCES_NOTE = (
    "See A. Marlow, Report of the Committee on Harbour Dues and Moorings (Kelbrook: Harbour Press, 1998), "
    "pp. 12-40; B. Okafor and C. Lind, Pilots, Guilds and Credit in the Coastal Towns of the North, Journal of "
    "Maritime History 14(2) (2006), pp. 101-29; D. Varga, *Stone and Timber: Building the Quays of Kelbrook* "
    "(London: Saltmarsh Books, 2011), ch. 3; and E. Brandt, The Harbour Masters of the Western Isles "
    "(Oxford: Quayside Press, 2015)."
)
# Reference lists kept in the source language whose titles are plain sentence-case text: prose by share. The
# acceptance reviews built these shapes to show that a FATAL form rule blocks a correct translation; here each
# must stay out of the fatal count (it may be listed for review -- the accepted cost).
_REFERENCE_SHAPES = {
    "author, title (year), publisher;": (
        "M. Ferrow, How small harbour towns pay for their ferries and keep the lights on during long winters of "
        "falling trade (2009), Saltmarsh Books; T. Okonkwo, Why coastal guilds lend to fishing crews and protect the "
        "jobs of the older pilots (2013), Quayside Press; L. Brandt, How the northern ports share their dues with "
        "the villages that keep the channel clear for everyone (2016), Saltmarsh Books."
    ),
    "Author. Title. Publisher, year.": (
        "Ferrow, Marta. How small harbour towns pay for their ferries and keep the lights on during long winters of "
        "falling trade. Saltmarsh Books, 2009. Okonkwo, Tobi. Why coastal guilds lend to fishing crews and protect "
        "the jobs of the older pilots. Quayside Press, 2013. Brandt, Lena. How the northern ports share their dues "
        "with the villages that keep the channel clear. Saltmarsh Books, 2016."
    ),
    "initials inside the title": (
        "Ferrow, M. (2009). J. R. Moor and the harbour dues: how small towns paid for their ferries in long "
        "winters. Saltmarsh Books. Okonkwo, T. (2013). E. L. Vance and the guild: why coastal lenders kept the "
        "older pilots at work. Quayside Press. Brandt, L. (2016). A. K. Dunn and the channel: how the northern "
        "ports shared their dues with the villages. Saltmarsh Books."
    ),
    "archive shelf marks": (
        "County Archives, records of the harbour board and of its dues, R/2009/12, box 4, file 7; Municipal "
        "Archives, papers of the northern council on the ferries, R/2013/18, box 5, file 9; National Archives, "
        "registers of the coastal commission for the villages, R/2016/22, box 6, file 10; Kelbrook Record Office, "
        "minutes of the pilots' meetings, R/2018/4, box 2, file 3."
    ),
    "Name, I. 2009. Title. Place: Publisher.": (
        "Ferrow, M. 2009. How small harbour towns pay for their ferries and keep the lights on during long "
        "winters. Kelbrook: Saltmarsh Books. Okonkwo, T. 2013. Why coastal guilds lend to fishing crews and "
        "protect the jobs of the older pilots. Kelbrook: Quayside Press. Brandt, L. 2016. How the northern ports "
        "share their dues with the villages that keep the channel clear. Kelbrook: Saltmarsh Books."
    ),
    "n.d. entries": (
        "Ferrow, M. n.d. How small harbour towns pay for their ferries and keep the lights on during long "
        "winters. Kelbrook: Saltmarsh Books. Okonkwo, T. 2013. Why coastal guilds lend to fishing crews and "
        "protect the jobs of the older pilots. Kelbrook: Quayside Press. Brandt, L. n.d. How the northern ports "
        "share their dues with the villages along the channel. Kelbrook: Saltmarsh Books. Moor, E. 2016. How the "
        "tides were measured in the old harbour. Kelbrook: Tidewater Press."
    ),
}
# Numbered prose (the spec 079 shape): the counting path reads it piece by piece and counts it.
_NUMBERED_PROSE = " ".join(
    f"{number} "
    + "The pilots agreed that the old quay needed a second survey before the boats could moor there again for "
    "the winter season. " * 4
    + f"The survey closed ({1990 + number})."
    for number in range(1, 4)
)


def _entry(text: str, status: str = "translated", **extra: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "role": "body", "structural_role": "body", "text": text, "controlled_fallback": False,
        "paragraph_status": status, "paragraph_id": "p0001",
    }
    fields.update(extra)
    return SimpleNamespace(**fields)


def _listed(text: str, status: str = "translated", **extra: object) -> list[int]:
    samples = quality_gate._collect_possibly_untranslated_body_samples(
        final_markdown=text, assembly_entries=[_entry(text, status, **extra)]
    )
    return [sample.char_count for sample in samples]


def _counted(text: str) -> list[int]:
    samples = quality_gate._collect_untranslated_body_samples(final_markdown=text, assembly_entries=[_entry(text)])
    return [sample.char_count for sample in samples]


class _Context:
    def __init__(self, operation: str = "translate", policy: str = "advisory") -> None:
        self.processing_operation = operation
        self.uploaded_filename = "book.docx"
        self.app_config = {"translation_output_quality_gate_policy": policy}


def _report(*texts: str, operation: str = "translate", policy: str = "advisory") -> dict:
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
        context=_Context(operation, policy),
        final_markdown=assembly.final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly,
        runtime_display_markdown=assembly.final_markdown,
    )


def _possible_items(report: dict) -> list[dict]:
    return [item for item in report["formatting_review_items"] if item["reason"] == _POSSIBLE]


# --- the fatal count is the count of main 07f26fe -------------------------------------------------


def test_prose_with_three_years_stays_out_of_the_fatal_count_and_is_listed_for_review() -> None:
    text = _PROSE_WITH_YEARS
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) == 3
    assert detectors._is_bibliography_or_url_dominant_text(text) is True  # the shortcut, as on main
    assert quality_gate._untranslated_body_char_count(text) == 0
    assert _counted(text) == []
    assert detectors._is_possibly_untranslated_prose_behind_bibliography_hits(text) is True
    assert _listed(text) == [len(text)]


def test_the_finding_is_review_only_and_names_each_paragraph() -> None:
    translated = [_PROSE_WITH_YEARS_RU] * 4
    report = _report(*(translated + [_PROSE_WITH_YEARS] * 5))
    # 5 x 466 characters, far above 2 000 and 2 % -- still no fatal reason, no fail
    assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]
    assert report["gate_reasons"].count("untranslated_body_text_review_required") == 1
    assert report["quality_status"] == "warn"
    assert report["untranslated_body_text_count"] == 0
    items = _possible_items(report)
    assert [item["severity"] for item in items] == ["review"] * 5
    assert [item["sample"]["paragraph_id"] for item in items] == [f"p{index:04d}" for index in range(4, 9)]
    assert {item["sample"]["char_count"] for item in items} == {len(_PROSE_WITH_YEARS)}
    assert items[0]["sample"]["text"].startswith("The harbour guild of Kelbrook")


def test_the_finding_never_turns_pass_into_fail_even_under_the_strict_policy() -> None:
    report = _report(*([_PROSE_WITH_YEARS_RU] * 2 + [_PROSE_WITH_YEARS] * 12), policy="strict")
    assert report["quality_status"] == "warn"
    assert not any(reason in quality_gate._FATAL_DOCUMENT_GATE_REASONS for reason in report["gate_reasons"])
    items = _possible_items(report)
    assert len(items) == 8 and items[0]["aggregate_count"] == 12  # capped like the other review lists


def test_every_reference_shape_of_the_reviews_gives_no_fatal_reason() -> None:
    translated = [_PROSE_WITH_YEARS_RU] * 200
    for name, shape in _REFERENCE_SHAPES.items():
        assert detectors._is_bibliography_or_url_dominant_text(shape) is True, name
        assert quality_gate._untranslated_body_char_count(shape) == 0, name
        for paragraphs in ([shape] * 6, [" ".join([shape] * 6)]):
            report = _report(*(translated + paragraphs))
            assert report["untranslated_body_text_chars"] == 0, name
            assert "untranslated_body_text_above_threshold" not in report["gate_reasons"], name
            assert report["quality_status"] != "fail", name


def test_a_reference_list_with_plain_titles_is_listed_the_accepted_cost() -> None:
    """The cost the spec names: such a list reads as prose by share, so it is LISTED for review (a line a
    reviewer dismisses), instead of blocking the book as the fatal form rules of rounds 0-2 did."""
    shape = _REFERENCE_SHAPES["author, title (year), publisher;"]
    assert detectors._reads_as_prose_by_share(shape) is True
    assert _listed(shape) == [len(shape)]


# --- what is not listed -----------------------------------------------------------------------------


def test_a_bibliography_by_share_is_not_listed() -> None:
    text = _REFERENCES_NOTE
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert detectors._reads_as_prose_by_share(text) is False
    assert _listed(text) == []


def test_translated_text_is_not_listed() -> None:
    assert detectors._reads_as_prose_by_share(_PROSE_WITH_YEARS_RU) is True  # prose in any cased script
    assert _listed(_PROSE_WITH_YEARS_RU) == []
    report = _report(*([_PROSE_WITH_YEARS_RU] * 6))
    assert report["quality_status"] == "pass"
    assert _possible_items(report) == []


def test_a_mostly_translated_paragraph_is_not_listed() -> None:
    """The Latin share floor: enough English words, but most letters are Cyrillic."""
    text = _PROSE_WITH_YEARS + " " + _PROSE_WITH_YEARS_RU + " " + _PROSE_WITH_YEARS_RU
    assert len(detectors._LATIN_WORD_PATTERN.findall(text)) >= detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS
    assert detectors._latin_letter_ratio(text) < 0.8
    assert _listed(text) == []


def test_a_short_paragraph_is_not_listed() -> None:
    text = (
        "The guild rebuilt the quay in 1987 and the pilots said the new wall was far too low for the big boats "
        "that came in 1994, and the council did not act until 2003, when the old wall fell and the town paid."
    )
    assert len(text) < detectors._UNTRANSLATED_BODY_MIN_CHARS
    assert len(detectors._LATIN_WORD_PATTERN.findall(text)) >= detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS
    assert detectors._reads_as_prose_by_share(text) is True
    assert _listed(text) == []


def test_a_paragraph_of_few_latin_words_is_not_listed() -> None:
    text = (
        "the-harbour-guild-of-kelbrook rebuilt-its-northern-quay in 1987 after-a-winter-of-long-storms; "
        "the-pilots-of-the-town complained-for-years-about-the-narrow-entrance and in 1994 "
        "the-council-of-the-harbour agreed-at-last-to-widen-it, finishing-the-long-work in 2003 "
        "when-the-last-of-the-old-moorings was-pulled-out-and-sold-for-firewood by-the-quiet-river-men."
    )
    assert len(text) >= detectors._UNTRANSLATED_BODY_MIN_CHARS
    assert len(detectors._LATIN_WORD_PATTERN.findall(text)) < detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS
    assert detectors._reads_as_prose_by_share(text) is True
    assert _listed(text) == []


def test_a_paragraph_with_an_address_is_left_to_the_address_branch() -> None:
    text = (
        "The guild rebuilt its quay in 1987, widened the entrance in 1994 and closed the old moorings in 2003, "
        "and the minutes of every one of those meetings are kept online by the municipal council for anybody "
        "interested, published at www.harbourcouncil.example.org/minutes indefinitely, free."
    )
    assert len(text) >= detectors._UNTRANSLATED_BODY_MIN_CHARS
    assert detectors._URL_OR_DOMAIN_PATTERN.search(text) is not None
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
    assert detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS <= len(detectors._LATIN_WORD_PATTERN.findall(text)) < 40
    assert detectors._reads_as_prose_by_share(text) is True
    assert _listed(text) == []


def test_prose_with_fewer_than_three_hits_is_counted_not_listed() -> None:
    text = _PROSE_WITH_YEARS.replace(" in 2003,", ",")
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) == 2
    assert _counted(text) == [len(text)]
    assert _listed(text) == []


def test_numbered_prose_is_counted_by_the_chain_reading_not_listed() -> None:
    text = _NUMBERED_PROSE
    assert output_validation.notes_run_untranslated_part(text) is not None
    assert detectors._is_possibly_untranslated_prose_behind_bibliography_hits(text) is True
    assert _counted(text) and _counted(text)[0] > 0
    assert _listed(text) == []


def test_kept_by_policy_headings_and_fallbacks_are_not_listed() -> None:
    text = _PROSE_WITH_YEARS
    assert _listed(text, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE) == []
    assert _listed(text, role="heading") == []
    assert _listed(text, structural_role="caption") == []
    assert _listed(text, controlled_fallback=True) == []


def test_the_review_reason_is_not_repeated() -> None:
    """With untranslated body already counted below the fatal thresholds, the reason is there once."""
    counted = _PROSE_WITH_YEARS.replace(" in 2003,", ",")
    report = _report(*([_PROSE_WITH_YEARS_RU] * 20 + [counted, _PROSE_WITH_YEARS]))
    assert report["untranslated_body_text_count"] == 1
    assert report["gate_reasons"].count("untranslated_body_text_review_required") == 1
    assert len(_possible_items(report)) == 1


def test_outside_translate_nothing_is_listed() -> None:
    report = _report(*([_PROSE_WITH_YEARS] * 3), operation="edit")
    assert _possible_items(report) == []
