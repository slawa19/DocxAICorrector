"""Spec 083 -- the untranslated-body gate tells a bibliography from prose by FORM, not by a count of years.

``quality_gate_text_detectors._is_bibliography_or_url_dominant_text`` skipped any paragraph with three
bibliographic hits -- a four-digit number counts as one -- so an English prose paragraph that mentions
three years and came back untranslated was invisible to the gate. The hits now count as bibliography only
when the paragraph is not prose by the share half of the repository's prose-form test
(``output_validation.prose_form_word_counts`` / ``PROSE_FORM_MIN_RESIDUE_SHARE``).

Both directions are pinned: untranslated prose with years is counted and can block a translate run; a note
made of references, kept in the source language as D1 asks, is still skipped; so is a reference with an
address (that branch is unchanged on purpose -- spec 083 Non-goals). All texts are invented.
"""

from __future__ import annotations

from types import SimpleNamespace

from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline import quality_gate
from docxaicorrector.pipeline import quality_gate_text_detectors as detectors

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
# A note made of references, as D1 keeps it: names, titles, places, publishers, years and pages. Too many
# running words for the per-note citation form (so spec 064 FR-006 would not relabel it), yet few of them.
_REFERENCES_NOTE = (
    "See A. Marlow, Report of the Committee on Harbour Dues and Moorings (Kelbrook: Harbour Press, 1998), "
    "pp. 12-40; B. Okafor and C. Lind, Pilots, Guilds and Credit in the Coastal Towns of the North, Journal of "
    "Maritime History 14(2) (2006), pp. 101-29; D. Varga, *Stone and Timber: Building the Quays of Kelbrook* "
    "(London: Saltmarsh Books, 2011), ch. 3; and E. Brandt, The Harbour Masters of the Western Isles "
    "(Oxford: Quayside Press, 2015)."
)
# A note of the author's commentary that cites as it goes: D1 asks for it to be translated.
_COMMENTARY_NOTE = (
    "In 1981 the guild estimated that the work done on the quays without pay was worth almost as much as the "
    "fees it collected, and a second survey in 1998 put the figure even higher, because it counted the hours "
    "the pilots' families spent mending nets and keeping the lamps lit through the winter nights; neither "
    "survey was ever published, and the clerks who made them left no notes on their method. See R. Hall, "
    "*The Harbour Ledger* (Kelbrook: Tidewater Press, 2004), p. 14."
)
# A reference with an address and a title longer than a title span, in sentence case: prose by the share
# (the long title is read as running words), and still a reference. The address branch decides it.
_REFERENCE_WITH_ADDRESS = (
    "Harbour Council of Kelbrook, ‘a report on the supply of mooring services by the northern guilds to the "
    "small and medium-sized fishing crews working within the outer harbour and along the river mouth’ (2012), "
    "a summary is online at www.harbourcouncil.example.org/reports/moorings.htm"
)


def _entry(text: str, status: str = "translated") -> SimpleNamespace:
    return SimpleNamespace(
        role="body", structural_role="body", text=text, controlled_fallback=False, paragraph_status=status,
        paragraph_id="p0001",
    )


def _collected(text: str) -> list[int]:
    samples = quality_gate._collect_untranslated_body_samples(final_markdown=text, assembly_entries=[_entry(text)])
    return [sample.char_count for sample in samples]


def _residue_share(text: str) -> float:
    residue, total = output_validation.prose_form_word_counts(text)
    return residue / total


def _reaches_whole_paragraph_path(text: str) -> bool:
    """Long enough, Latin, enough words, not a numbered chain: only the bibliography shortcut decides."""
    return (
        len(text) >= detectors._UNTRANSLATED_BODY_MIN_CHARS
        and detectors._latin_letter_ratio(text) >= 0.8
        and len(detectors._LATIN_WORD_PATTERN.findall(text)) >= detectors._UNTRANSLATED_BODY_MIN_LATIN_WORDS
        and output_validation.notes_run_untranslated_part(text) is None
    )


def test_untranslated_prose_with_three_years_is_counted() -> None:
    text = _PROSE_WITH_YEARS
    # The premises: three hits (the years), no address, and nothing else in the way of the count.
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) == 3
    assert detectors._URL_OR_DOMAIN_PATTERN.search(text) is None
    assert _reaches_whole_paragraph_path(text)
    assert _residue_share(text) >= output_validation.PROSE_FORM_MIN_RESIDUE_SHARE

    assert detectors._is_bibliography_or_url_dominant_text(text) is False
    assert detectors._is_untranslated_body_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == len(text)
    assert _collected(text) == [len(text)]


def test_untranslated_prose_with_years_now_blocks_a_translate_run() -> None:
    """End to end: enough of it crosses the document thresholds (2 000 characters and 2 %)."""
    translated = [_PROSE_WITH_YEARS_RU] * 4
    untranslated = [_PROSE_WITH_YEARS] * 5
    report = _report(*(translated + untranslated))
    assert report["untranslated_body_text_count"] == 5
    assert report["untranslated_body_text_chars"] == 5 * len(_PROSE_WITH_YEARS)
    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]


def test_a_note_of_references_kept_in_the_source_stays_skipped() -> None:
    """Anti-vacuum: the shortcut still does its job for a bibliography."""
    text = _REFERENCES_NOTE
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
    assert detectors._URL_OR_DOMAIN_PATTERN.search(text) is None
    assert _reaches_whole_paragraph_path(text)
    # Not a citation by the per-note form (too many running words), so the model-kept relabelling of spec 064
    # FR-006 would leave it to the gate -- and still not prose by the share.
    assert output_validation.is_citation_form_paragraph(text) is False
    assert _residue_share(text) < output_validation.PROSE_FORM_MIN_RESIDUE_SHARE

    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0
    assert _collected(text) == []


def test_a_commentary_note_left_in_the_source_language_is_counted() -> None:
    text = _COMMENTARY_NOTE
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
    assert _reaches_whole_paragraph_path(text)
    assert _residue_share(text) >= output_validation.PROSE_FORM_MIN_RESIDUE_SHARE
    assert quality_gate._untranslated_body_char_count(text) == len(text)


def test_translated_prose_with_years_is_not_counted() -> None:
    """The language test is unchanged: prose by form in another script is prose, and it is not untranslated."""
    assert detectors._reads_as_prose_by_share(_PROSE_WITH_YEARS_RU) is True
    assert detectors._latin_letter_ratio(_PROSE_WITH_YEARS_RU) < 0.8
    assert quality_gate._untranslated_body_char_count(_PROSE_WITH_YEARS_RU) == 0
    assert _collected(_PROSE_WITH_YEARS_RU) == []


def test_three_numbers_without_words_keep_the_old_shortcut() -> None:
    """No word with a letter: no share to read, the paragraph stays skipped as before."""
    assert output_validation.prose_form_word_counts("1999 2000 2001") == (0, 0)
    assert detectors._reads_as_prose_by_share("1999 2000 2001") is False
    assert detectors._is_bibliography_or_url_dominant_text("1999 2000 2001") is True


def test_the_address_branch_is_unchanged() -> None:
    """Spec 083 leaves the address branch alone: by the share this reference reads as prose (its long
    sentence-case title is running words), and guarding the branch with it would count a reference the
    translation correctly kept -- measured on a delivered translation of the corpus (spec 083)."""
    text = _REFERENCE_WITH_ADDRESS
    assert _reaches_whole_paragraph_path(text)
    assert detectors._URL_OR_DOMAIN_PATTERN.search(text) is not None
    assert len(detectors._LATIN_WORD_PATTERN.findall(text)) < 40
    assert detectors._reads_as_prose_by_share(text) is True

    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0


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
