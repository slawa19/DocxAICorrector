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
