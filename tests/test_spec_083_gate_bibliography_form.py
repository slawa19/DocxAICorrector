"""Spec 083 -- the untranslated-body gate tells a bibliography from prose by FORM, not by a count of years.

``quality_gate_text_detectors._is_bibliography_or_url_dominant_text`` skipped any paragraph with three
bibliographic hits -- a four-digit number counts as one -- so an English prose paragraph that mentions
three years and came back untranslated was invisible to the gate. The hits now count as bibliography unless
the paragraph is prose by the share half of the repository's prose-form test
(``output_validation.prose_form_word_counts`` / ``PROSE_FORM_MIN_RESIDUE_SHARE``) AND one of its sentences
is prose by that share with no reference mark of its own (acceptance review round 1: a list of references
with plain sentence-case titles is prose by share, and counting it gave a false fatal verdict).

Both directions are pinned: untranslated prose with years is counted and can block a translate run; a note
made of references, kept in the source language as D1 asks, is still skipped, whatever the case of its titles;
so is a reference with an address (that branch is unchanged on purpose -- spec 083 Non-goals). All texts are
invented.
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
# Review round 1 -- reference lists whose titles are neither emphasised nor quoted and are written in sentence
# case: prose by share, each entry with its own mark. They must stay skipped.
# (a) author, title (year), publisher; ... -- the mark is the year in brackets.
_PLAIN_TITLE_REFERENCES = (
    "M. Ferrow, How small harbour towns pay for their ferries and keep the lights on during long winters of "
    "falling trade (2009), Saltmarsh Books; T. Okonkwo, Why coastal guilds lend to fishing crews and protect the "
    "jobs of the older pilots (2013), Quayside Press; L. Brandt, How the northern ports share their dues with the "
    "villages that keep the channel clear for everyone (2016), Saltmarsh Books."
)
# (b) ..., publisher, year; ... -- the mark is the year in the date field after a comma.
_DATE_FIELD_REFERENCES = (
    "M. Ferrow, How small harbour towns pay for their ferries and keep the lights on during long winters of "
    "falling trade, Saltmarsh Books, 2009; T. Okonkwo, Why coastal guilds lend to fishing crews and protect the "
    "jobs of the older pilots, Quayside Press, 2013; L. Brandt, How the northern ports share their dues with the "
    "villages that keep the channel clear, Saltmarsh Books, 2016."
)
# (c) ..., journal, Month year; ... -- the date field holds a month or a season before the year.
_MONTH_FIELD_REFERENCES = (
    "M. Ferrow, how small harbour towns pay for their ferries and keep the lights on during long winters, "
    "Harbour Review, Spring 2009; T. Okonkwo, why coastal guilds lend to fishing crews and protect the jobs of "
    "older pilots, Coastal Affairs, March 2013; L. Brandt, how the northern ports share their dues with the "
    "villages along the channel, Harbour Review, Autumn 2016."
)
# (d) Name, I. (year) Title. Place: Publisher. -- entries as sentences; the place and publisher stand in a
# sentence of their own, which is not prose by share.
_SENTENCE_ENTRY_REFERENCES = (
    "Ferrow, M. (2009) How small harbour towns pay for their ferries and keep the lights on during long winters. "
    "Kelbrook: Saltmarsh Books. Okonkwo, T. (2013) Why coastal guilds lend to fishing crews and protect the jobs "
    "of the older pilots. Kelbrook: Quayside Press. Brandt, L. (2016) How the northern ports share their dues "
    "with the villages along the channel. Kelbrook: Saltmarsh Books."
)
# (e) Name, I. (year). Title. Publisher. -- the author-date style: the title is a sentence of its own,
# right after the sentence that carries the year in brackets.
_AUTHOR_DATE_REFERENCES = (
    "Ferrow, M. (2009). How small harbour towns pay for their ferries and keep the lights on during long "
    "winters. Saltmarsh Books. Okonkwo, T. (2013). Why coastal guilds lend to fishing crews and protect the jobs "
    "of the older pilots. Quayside Press. Brandt, L. (2016). How the northern ports share their dues with the "
    "villages along the channel. Saltmarsh Books."
)
# (f) Review round 2 -- the year as a sentence of its own: Name, I. 2009. Title. Place: Publisher. and the
# full-name variant; then a range and a letter suffix.
_YEAR_SENTENCE_INITIALS = (
    "Ferrow, M. 2009. How small harbour towns pay for their ferries and keep the lights on during long winters. "
    "Kelbrook: Saltmarsh Books. Okonkwo, T. 2013. Why coastal guilds lend to fishing crews and protect the jobs "
    "of the older pilots. Kelbrook: Quayside Press. Brandt, L. 2016. How the northern ports share their dues with "
    "the villages that keep the channel clear. Kelbrook: Saltmarsh Books."
)
_YEAR_SENTENCE_FULL_NAMES = _YEAR_SENTENCE_INITIALS.replace("Ferrow, M.", "Ferrow, Marta.").replace(
    "Okonkwo, T.", "Okonkwo, Tobi."
).replace("Brandt, L.", "Brandt, Lena.")
_YEAR_RANGE_REFERENCES = _YEAR_SENTENCE_FULL_NAMES.replace("Marta. 2009.", "Marta. 2009–2011.").replace(
    "Tobi. 2013.", "Tobi. 2013-2014."
)
_YEAR_SUFFIX_REFERENCES = (
    "Ferrow, Marta. 2009a. How small harbour towns pay for their ferries and keep the lights on during long "
    "winters. Kelbrook: Saltmarsh Books. Ferrow, Marta. 2009b. Why coastal guilds lend to fishing crews and "
    "protect the jobs of the older pilots. Kelbrook: Quayside Press. Okonkwo, Tobi. 2013. How the northern ports "
    "share their dues with the villages along the channel. Kelbrook: Saltmarsh Books. Brandt, Lena. 2016. How "
    "the tides were measured in the old harbour. Kelbrook: Saltmarsh Books."
)
# Prose whose sentences END in a year, every other one: the year follows a word, the sentence is not only a
# year -- if it marked the sentence, each following sentence would be read with it and nothing would count.
_PROSE_ENDING_IN_YEARS = (
    "The last great storm came to the northern quay in 1987. The council did nothing for years, and the pilots "
    "repaired the timber themselves every spring. The old lighthouse fell into the channel in 1994. Nobody "
    "rebuilt it, and the channel silted up within a decade. It happened in 1998. The town never recovered, and "
    "the last boats left for the river in 2003."
)
# Prose whose sentences OPEN with a year: the year runs on into the sentence, it is not a sentence of its own.
_PROSE_OPENING_WITH_YEARS = (
    "Storms came to the northern quay almost every winter of that century. 1987 was the worst of them all, and "
    "half of the old timber piles were lost in a single night. The council did nothing for years. 1994 brought "
    "another storm, and the lighthouse at the end of the quay fell into the channel. Nobody rebuilt it. 2003 saw "
    "the last of the boats leave the harbour for the towns along the river."
)
# A chronicle: a year, then ONE sentence, then the next year -- the form of the author-date list.
_CHRONICLE_ONE_SENTENCE_PER_YEAR = (
    "1998. The harbour closed after the winter storms, and the pilots were told to look for work in the south. "
    "1999. The ferries stopped, and the villages on the far shore were cut off for most of the year. 2000. The "
    "council sold the old quay to a trading company that never came back to use it. 2001. The last of the "
    "pilots left the town with their families and their boats."
)
# A chronicle with two sentences per year: the second sentence follows an unmarked one and is running text.
_CHRONICLE_TWO_SENTENCES_PER_YEAR = (
    "1998. The harbour closed after the winter storms. The pilots were told to look for work in the south, and "
    "most of them went. 1999. The ferries stopped for good. The villages on the far shore were cut off for most "
    "of the year, and the school there closed. 2000. The council sold the old quay. Nobody ever came back to use "
    "it, and the timber rotted where it stood."
)
# Prose whose three years include one in brackets: one sentence carries a mark, the others do not.
_PROSE_WITH_ONE_BRACKETED_YEAR = (
    "The harbour guild of Kelbrook rebuilt its northern quay in 1987, after a winter of storms had left half of "
    "the old timber piles leaning into the channel. The council minutes of that spring (1988) record the cost, "
    "and the pilots kept complaining for years that the entrance was too narrow for the larger boats. The work "
    "to widen it was only finished in 2003, when the last of the old moorings was pulled out and sold."
)
# A reference followed by the author's annotation: D1 asks for the annotation to be translated.
_ANNOTATED_REFERENCE = (
    "M. Ferrow, How small harbour towns pay for their ferries (Kelbrook: Saltmarsh Books, 2009), pp. 12-40. "
    "The book follows the accounts of three ferry companies over twenty years and shows that the winter "
    "crossings were always paid for by the summer trade. It is the only study that looks at the ferries from "
    "the side of the crews rather than the owners, and its last chapter on the 1998 strike and the settlement "
    "of 2004 is still quoted."
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


def _premises_of_a_plain_title_list(text: str) -> None:
    """What makes the review's case dangerous: on the whole-paragraph path, prose by share, three hits, and
    nothing else (no address, no chain, not a citation by the per-note form) that would skip it."""
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
    assert detectors._URL_OR_DOMAIN_PATTERN.search(text) is None
    assert _reaches_whole_paragraph_path(text)
    assert output_validation.is_citation_form_paragraph(text) is False
    assert _residue_share(text) >= output_validation.PROSE_FORM_MIN_RESIDUE_SHARE


def test_references_with_plain_sentence_case_titles_do_not_block_a_correct_translation() -> None:
    """Acceptance review round 1 (P2): such a list, kept in the source language, was counted whole, and six
    of them -- or one long one -- gave the FATAL verdict on a correct translation."""
    text = _PLAIN_TITLE_REFERENCES
    _premises_of_a_plain_title_list(text)
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0
    assert _collected(text) == []

    translated = [_PROSE_WITH_YEARS_RU] * 200
    report = _report(*(translated + [text] * 6))
    assert report["untranslated_body_text_chars"] == 0
    assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]
    long_list = " ".join([text[:-1] + ";"] * 6)[:-1] + "."
    assert len(long_list) >= detectors._UNTRANSLATED_BODY_FAIL_MIN_CHARS
    report = _report(*(translated + [long_list]))
    assert report["untranslated_body_text_chars"] == 0
    assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]


def test_a_year_in_the_date_field_marks_an_entry() -> None:
    for text in (_DATE_FIELD_REFERENCES, _MONTH_FIELD_REFERENCES):
        _premises_of_a_plain_title_list(text)
        assert output_validation.has_hard_reference_mark(text) is False  # only the date field marks these entries
        assert detectors._is_bibliography_or_url_dominant_text(text) is True
        assert quality_gate._untranslated_body_char_count(text) == 0


def test_a_place_and_publisher_sentence_is_not_running_text() -> None:
    text = _SENTENCE_ENTRY_REFERENCES
    _premises_of_a_plain_title_list(text)
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0


def test_a_title_in_the_sentence_after_the_year_belongs_to_its_entry() -> None:
    """Author-date entries: the title sentence follows the sentence with the year in brackets."""
    text = _AUTHOR_DATE_REFERENCES
    _premises_of_a_plain_title_list(text)
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0


def test_a_year_standing_as_a_sentence_marks_its_entry() -> None:
    """Review round 2: ``Name, I. 2009. Title. Place: Publisher.`` and ``Name, First. 2009. ...`` -- both
    exempt before spec 083 -- do not give the FATAL verdict on a correct translation, even as one long paragraph."""
    translated = [_PROSE_WITH_YEARS_RU] * 200
    for text in (_YEAR_SENTENCE_INITIALS, _YEAR_SENTENCE_FULL_NAMES):
        _premises_of_a_plain_title_list(text)
        assert output_validation.has_hard_reference_mark(text) is False
        assert detectors._DATE_FIELD_YEAR_PATTERN.search(text) is None
        assert detectors._is_bibliography_or_url_dominant_text(text) is True
        long_list = " ".join([text] * 6)
        assert len(long_list) >= 2351
        report = _report(*(translated + [long_list]))
        assert report["untranslated_body_text_chars"] == 0
        assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]


def test_a_year_range_or_a_lettered_year_stands_as_a_sentence_too() -> None:
    for text in (_YEAR_RANGE_REFERENCES, _YEAR_SUFFIX_REFERENCES):
        _premises_of_a_plain_title_list(text)
        assert detectors._is_bibliography_or_url_dominant_text(text) is True
        assert quality_gate._untranslated_body_char_count(text) == 0


def test_a_sentence_ending_or_opening_with_a_year_is_still_running_text() -> None:
    for text in (_PROSE_ENDING_IN_YEARS, _PROSE_OPENING_WITH_YEARS):
        assert _reaches_whole_paragraph_path(text)
        assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
        assert quality_gate._untranslated_body_char_count(text) == len(text)


def test_a_chronicle_with_one_sentence_per_year_reads_as_a_list() -> None:
    """The accepted cost of the year-as-sentence mark (spec 083, review round 2): a chronicle left in English
    whose every year is followed by ONE sentence is not counted -- exactly as before spec 083, when its three
    years hid it. A chronicle whose years carry two sentences is counted."""
    hidden = _CHRONICLE_ONE_SENTENCE_PER_YEAR
    assert _reaches_whole_paragraph_path(hidden)
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(hidden)) >= 3
    assert quality_gate._untranslated_body_char_count(hidden) == 0
    counted = _CHRONICLE_TWO_SENTENCES_PER_YEAR
    assert _reaches_whole_paragraph_path(counted)
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(counted)) >= 3
    # the leading "1998. " is read as a list-item prefix and stripped before counting
    assert quality_gate._untranslated_body_char_count(counted) == len(detectors._strip_structural_markdown_prefix(counted))


def test_a_reference_note_with_a_short_pointer_stays_skipped() -> None:
    """The whole-paragraph share still comes first: a note of references with one short pointer sentence
    ("See also ...") is not prose as a whole and stays skipped, as before spec 083 (on the corpus eight
    reference notes have such a sentence)."""
    text = "For the older work on the ferries and the dues, see the following. " + _REFERENCES_NOTE
    assert _reaches_whole_paragraph_path(text)
    assert _residue_share(text) < output_validation.PROSE_FORM_MIN_RESIDUE_SHARE
    assert detectors._has_unmarked_running_sentence(text) is True
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0


def test_a_sentence_of_names_is_not_running_text() -> None:
    """A sentence is running text by the SHARE of its lowercase words, not by their number: an archive line
    of names joined by "of", "the" and "and" is not prose and needs no mark."""
    archive = (
        "Unpublished Papers of the Harbour Council, the Northern Guild of Pilots, the Western Isles Trust and "
        "the Saltmarsh Ferry Company, Kelbrook Record Office."
    )
    residue, total = output_validation.prose_form_word_counts(archive)
    assert residue >= output_validation.PROSE_FORM_MIN_RESIDUE_WORDS
    assert residue / total < output_validation.PROSE_FORM_MIN_RESIDUE_SHARE
    text = _PLAIN_TITLE_REFERENCES + " " + archive
    _premises_of_a_plain_title_list(text)
    assert detectors._is_bibliography_or_url_dominant_text(text) is True
    assert quality_gate._untranslated_body_char_count(text) == 0


def test_one_bracketed_year_does_not_hide_the_other_sentences() -> None:
    """The marks are read sentence by sentence: one sentence of prose that cites does not make the rest a list."""
    text = _PROSE_WITH_ONE_BRACKETED_YEAR
    assert output_validation.has_hard_reference_mark(text) is True
    assert _reaches_whole_paragraph_path(text)
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
    assert quality_gate._untranslated_body_char_count(text) == len(text)


def test_a_reference_does_not_shield_its_annotation() -> None:
    """The sentence after a cited one is read with it, one step only: the second sentence of an annotation is
    running text again, and D1 asks for it to be translated."""
    text = _ANNOTATED_REFERENCE
    assert _reaches_whole_paragraph_path(text)
    assert len(detectors._BIBLIOGRAPHY_LIKE_PATTERN.findall(text)) >= 3
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
