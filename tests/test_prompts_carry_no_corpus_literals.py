"""Spec 066 FR-005: no prompt resource reproduces a title or a heading of a corpus book.

Constitution VII forbids per-book literals in the product, and a prompt example is product:
it is sent to the model on every matching block of every book. Until spec 066 the TOC example
quoted real chapter titles of a validation-corpus book ("Introduction: Making Versus Taking").

The rule is keyed on coincidence with the corpus, not on a word list: the phrases are read from
the corpus books themselves (the ``[[documents]]`` of ``corpus_registry.toml`` and the DOCX twin
of each ``source_path``) -- their heading-styled paragraphs, their core-properties title and
their authors. A heading or title is split at its punctuation into segments ("Introduction:
Making versus Taking" -> "Making versus Taking"); every segment of at least three words, and
every full author name, must not occur as a contiguous word sequence (case-insensitive) in any
``resources/prompts/**/*.txt``. Translated reuse (a Russian rendering of a corpus paragraph) is
out of reach of this rule; it is caught by review, as A-6 was.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS_DIR = _ROOT / "src" / "docxaicorrector" / "resources" / "prompts"
_WORD = re.compile(r"[^\W_]+")
_SEGMENT_SPLIT = re.compile(r"[:.;?!()\[\]«»\"—–]+")
_MIN_PHRASE_WORDS = 3
_HEADING_STYLE_PREFIXES = ("heading", "title", "toc")


def _words(text: str) -> tuple[str, ...]:
    return tuple(word.lower() for word in _WORD.findall(text))


def _segments(text: str) -> list[tuple[str, ...]]:
    return [_words(part) for part in _SEGMENT_SPLIT.split(text)]


def _corpus_books() -> list[Path]:
    registry = tomllib.loads((_ROOT / "corpus_registry.toml").read_text(encoding="utf-8"))
    return [
        (_ROOT / document["source_path"]).with_suffix(".docx")
        for document in registry["documents"]
        if document.get("source_path")
    ]


def _corpus_phrases() -> dict[tuple[str, ...], str]:
    from docx import Document

    phrases: dict[tuple[str, ...], str] = {}
    for book in _corpus_books():
        if not book.is_file():
            pytest.skip(f"corpus DOCX twin is absent: {book}")
        document = Document(str(book))
        texts = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip() and paragraph.style is not None
            and str(paragraph.style.name).lower().startswith(_HEADING_STYLE_PREFIXES)
        ]
        texts.append(document.core_properties.title or "")
        for text in texts:
            for segment in _segments(text):
                if len(segment) >= _MIN_PHRASE_WORDS:
                    phrases.setdefault(segment, f"{book.name}: {text.strip()}")
        for author in re.split(r"[;,&]", document.core_properties.author or ""):
            name = _words(author)
            if len(name) >= 2:
                phrases.setdefault(name, f"{book.name}: author {author.strip()}")
    return phrases


def _contains(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    width = len(needle)
    return any(haystack[index : index + width] == needle for index in range(len(haystack) - width + 1))


def test_the_rule_reads_real_phrases_from_the_corpus() -> None:
    """Anti-vacuum: the guard below is only as strong as the phrase set it reads."""
    phrases = _corpus_phrases()

    assert len(_corpus_books()) >= 4
    assert len(phrases) >= 100
    assert ("making", "versus", "taking") in phrases
    assert _contains(_words("Introduction: Making Versus Taking ........ 1"), ("making", "versus", "taking"))


def test_no_prompt_resource_reproduces_a_corpus_title_or_heading() -> None:
    phrases = _corpus_phrases()
    prompt_files = sorted(_PROMPTS_DIR.rglob("*.txt"))
    assert prompt_files

    found: list[str] = []
    for prompt in prompt_files:
        for line_number, line in enumerate(prompt.read_text(encoding="utf-8").splitlines(), start=1):
            line_words = _words(line)
            for phrase, origin in phrases.items():
                if _contains(line_words, phrase):
                    found.append(f"{prompt.relative_to(_ROOT)}:{line_number}: {' '.join(phrase)!r} <- {origin}")

    assert not found, "prompt resources quote corpus books:\n" + "\n".join(found)


# --- spec 067 P6: the same phrase set over the code and its tests -----------------------------
#
# A rule keyed on a corpus line is not a rule (Constitution VII), and neither is a test that only
# holds on the corpus line it quotes: its synthetic twin of the same form is the proof the rule is
# by form. Spec 067's audit found book lines quoted as fixtures in tests and as examples in the
# docstrings of ``src/``. The same phrase set as above is therefore checked against every
# ``src/**/*.py`` and ``tests/**/*.py``, comments and strings included.
#
# What stays readable on purpose:
#
# * a book's NAME -- the segments of its core-properties title ("the value of everything") --
#   because "measured on <book>" is the provenance a comment owes (spec 067 P6); a heading or
#   an author of the book is not exempt;
# * ``_CODE_SCAN_EXEMPT``, each with its reason.
#
# What this does NOT see: a body word or a body sentence of a book (a coined place name, a note,
# a definition) -- the phrase set is headings, titles and authors only. Those are caught by
# review, as the P6 inventory was.

_CODE_ROOTS = (_ROOT / "src", _ROOT / "tests")
_CODE_SCAN_EXEMPT = {
    # The real-document runner names the corpus books, profiles and run ids by design.
    "tests/artifacts/real_document_pipeline/run_lietaer_validation.py",
    # This guard: its anti-vacuum test must name a real corpus phrase.
    "tests/test_prompts_carry_no_corpus_literals.py",
}
# Recorded-run inputs (a run's JSON, a golden DOCX) are data a run produced, not code; nothing
# under it is a ``.py`` file today, and the scan keeps it out should one appear.
_CODE_SCAN_EXEMPT_DIRS = ("tests/fixtures/",)

# Test fixtures written before spec 064 (2026-04-22 .. spec 063) that quote corpus headings or
# authors, found when this scan was first run (2026-11-08, spec 067 P6). They are NOT
# accepted: the owner decides per file whether it is
# rewritten in synthetic text of the same form or kept as a recorded characterization. Until then
# a file listed here may hold the listed phrases and no other; an entry that no longer occurs
# fails ``test_pending_corpus_phrases_are_not_stale``, so the list only shrinks.
_PENDING_OWNER_DECISION: dict[str, frozenset[tuple[str, ...]]] = {
    "tests/test_document_extraction.py": frozenset({
        ("banks", "and", "financial", "markets", "become", "allies"),
        ("common", "critiques", "of", "value", "extraction"),
        ("gdp", "facit", "saltus"),
        ("mariana", "mazzucato"),
        ("meet", "the", "production", "boundary"),
        ("patching", "up", "the", "national", "accounts", "isn", "t", "enough"),
        ("something", "odd", "about", "the", "national", "accounts"),
        ("the", "banking", "problem"),
        ("what", "is", "value"),
    }),
    "tests/test_document_pipeline.py": frozenset({
        ("the", "competitive", "society"),
    }),
    "tests/test_document_pipeline_output_validation.py": frozenset({
        ("why", "this", "report", "now"),
    }),
    "tests/test_document_structure_blocks.py": frozenset({
        ("about", "the", "authors"),
        ("bernard", "lietaer"),
        ("making", "versus", "taking"),
        ("the", "economics", "of", "hope"),
    }),
    "tests/test_format_restoration.py": frozenset({
        ("a", "brief", "history", "of", "value"),
        ("how", "it", "really", "works"),
        ("making", "versus", "taking"),
        ("our", "available", "future"),
        ("the", "cooperative", "society"),
        ("truth", "and", "consequences", "lessons", "learned"),
        ("what", "is", "value"),
    }),
    "tests/test_generation.py": frozenset({
        ("bernard", "lietaer"),
        ("sally", "goerner"),
    }),
    "tests/test_late_phases_characterization.py": frozenset({
        ("the", "competitive", "society"),
    }),
    "tests/test_output_display_hygiene.py": frozenset({
        ("making", "economic", "paradigms", "explicit"),
        ("monetary", "and", "banking", "instability"),
        ("why", "this", "report", "now"),
    }),
    "tests/test_paragraph_boundary_normalization.py": frozenset({
        ("meet", "the", "production", "boundary"),
        ("the", "structure", "of", "the", "book"),
        ("why", "value", "theory", "matters"),
    }),
    "tests/test_pdf_text_layer_logical_import.py": frozenset({
        ("a", "brief", "history", "of", "value"),
        ("a", "proposal", "for", "a", "global", "trade"),
        ("extracting", "value", "through", "the", "innovation", "economy"),
        ("honoring", "our", "elders", "caring", "for", "children"),
        ("measuring", "the", "wealth", "of", "nations"),
        ("minding", "the", "community", "s", "business"),
        ("part", "one", "scarcity"),
        ("strategies", "for", "governments"),
        ("the", "community", "currency", "how", "to", "manual"),
        ("the", "competitive", "society"),
        ("the", "failure", "of", "money"),
        ("trade", "and", "treasure"),
        ("why", "this", "report", "now"),
    }),
    "tests/test_pdf_text_layer_quality.py": frozenset({
        ("national", "currency", "crisis", "solution"),
    }),
    "tests/test_preserve_authored_tables.py": frozenset({
        ("bernard", "lietaer"),
        ("mariana", "mazzucato"),
    }),
    "tests/test_quality_gate_hygiene_channel_operations.py": frozenset({
        ("the", "competitive", "society"),
    }),
    "tests/test_reader_cleanup_mvp.py": frozenset({
        ("the", "united", "states"),
        ("trade", "and", "treasure"),
    }),
    "tests/test_real_document_pipeline_validation.py": frozenset({
        ("bernard", "lietaer"),
        ("measuring", "the", "wealth", "of", "nations"),
        ("the", "creative", "economy"),
    }),
    "tests/test_real_document_validation_corpus.py": frozenset({
        ("a", "brief", "history", "of", "value"),
        ("trade", "and", "treasure"),
    }),
    "tests/test_structure_validation.py": frozenset({
        ("making", "economic", "paradigms", "explicit"),
        ("monetary", "and", "banking", "instability"),
        ("why", "this", "report", "now"),
    }),
}


def _title_phrases() -> frozenset[tuple[str, ...]]:
    from docx import Document

    titles: set[tuple[str, ...]] = set()
    for book in _corpus_books():
        if not book.is_file():
            pytest.skip(f"corpus DOCX twin is absent: {book}")
        for segment in _segments(Document(str(book)).core_properties.title or ""):
            if len(segment) >= _MIN_PHRASE_WORDS:
                titles.add(segment)
    return frozenset(titles)


def _code_files() -> list[Path]:
    files = []
    for root in _CODE_ROOTS:
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(_ROOT).as_posix()
            if relative in _CODE_SCAN_EXEMPT or relative.startswith(_CODE_SCAN_EXEMPT_DIRS):
                continue
            files.append(path)
    return files


def _code_hits() -> list[tuple[str, int, tuple[str, ...], str]]:
    titles = _title_phrases()
    phrases = {phrase: origin for phrase, origin in _corpus_phrases().items() if phrase not in titles}
    hits = []
    for path in _code_files():
        relative = path.relative_to(_ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line_words = _words(line)
            for phrase, origin in phrases.items():
                if _contains(line_words, phrase):
                    hits.append((relative, line_number, phrase, origin))
    return hits


def test_the_code_scan_reads_real_phrases_and_spares_only_book_names() -> None:
    """Anti-vacuum for the scan below: a heading phrase is caught, a book's name is not."""
    titles = _title_phrases()
    assert ("the", "value", "of", "everything") in titles
    assert ("making", "versus", "taking") not in titles
    assert ("making", "versus", "taking") in _corpus_phrases()
    assert any(path.as_posix().endswith("src/docxaicorrector/text/glossary_pass.py") for path in _code_files())
    assert not any(path.relative_to(_ROOT).as_posix() in _CODE_SCAN_EXEMPT for path in _code_files())


def test_no_code_or_test_file_reproduces_a_corpus_heading_or_author() -> None:
    found = [
        f"{relative}:{line_number}: {' '.join(phrase)!r} <- {origin}"
        for relative, line_number, phrase, origin in _code_hits()
        if phrase not in _PENDING_OWNER_DECISION.get(relative, frozenset())
    ]

    assert not found, "code or tests quote corpus books (write synthetic text of the same form):\n" + "\n".join(found)


def test_pending_corpus_phrases_are_not_stale() -> None:
    present: dict[str, set[tuple[str, ...]]] = {}
    for relative, _, phrase, _ in _code_hits():
        present.setdefault(relative, set()).add(phrase)
    stale = [
        f"{relative}: {' '.join(phrase)!r}"
        for relative, phrases in _PENDING_OWNER_DECISION.items()
        for phrase in phrases
        if phrase not in present.get(relative, set())
    ]

    assert not stale, "remove from _PENDING_OWNER_DECISION, no longer quoted:\n" + "\n".join(stale)
