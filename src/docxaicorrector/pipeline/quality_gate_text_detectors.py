"""Pure text/language-detection predicates for the document quality gate.

Byte-identical satellite extraction from ``pipeline/quality_gate.py`` (mirrors the
spec 035 output_validation pattern): the stateless regex constants and pure
string/sample predicates that decide language, bibliography/URL dominance, and
citation-form list-fragment residue. No behaviour change -- ``quality_gate``
re-exports every name so ``quality_gate.<name>`` / ``late_phases.<name>`` keep
resolving for callers and the test namespace.
"""

import re


_STANDALONE_NUMERIC_CONTINUATION_PATTERN = re.compile(r"^\s*\d{1,6}\.\s*$")


_UNTRANSLATED_BODY_MIN_CHARS = 280
_UNTRANSLATED_BODY_MIN_LATIN_WORDS = 30
_UNTRANSLATED_BODY_FAIL_MIN_CHARS = 2000
_UNTRANSLATED_BODY_FAIL_RATIO = 0.02


_LATIN_LETTER_PATTERN = re.compile(r"[A-Za-z]")
_LATIN_WORD_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z'’-]{2,}\b")
_CYRILLIC_LETTER_PATTERN = re.compile(r"[А-Яа-яЁё]")
_MARKDOWN_STRUCTURAL_PREFIX_PATTERN = re.compile(r"^\s*(?:#{1,6}\s+|>\s+|[-*]\s+|\d+\.\s+)+")
_URL_OR_DOMAIN_PATTERN = re.compile(r"(?:https?://|www\.|\b[A-Za-z0-9.-]+\.(?:com|org|net|edu|gov|info|io|co)\b)", re.IGNORECASE)
_BIBLIOGRAPHY_LIKE_PATTERN = re.compile(
    r"(?:\b(?:doi|isbn|issn|references|bibliography|press|journal|vol\.|pp\.)\b|\(\d{4}\)|\b\d{4}\b)",
    re.IGNORECASE,
)


def _strip_structural_markdown_prefix(text: str) -> str:
    stripped = str(text or "").strip()
    return _MARKDOWN_STRUCTURAL_PREFIX_PATTERN.sub("", stripped).strip()


def _is_untranslated_structural_text(text: str) -> bool:
    stripped = _strip_structural_markdown_prefix(text)
    if not stripped or _CYRILLIC_LETTER_PATTERN.search(stripped):
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    latin_letters = [char for char in letters if _LATIN_LETTER_PATTERN.fullmatch(char)]
    if len(latin_letters) / len(letters) < 0.8:
        return False
    latin_words = _LATIN_WORD_PATTERN.findall(stripped)
    if len(latin_words) >= 2:
        return True
    if len(latin_words) == 1:
        word = latin_words[0]
        return len(word) >= 6 and word.isupper()
    return False


def _latin_letter_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return 0.0
    latin_letters = [char for char in letters if _LATIN_LETTER_PATTERN.fullmatch(char)]
    return len(latin_letters) / len(letters)


def _is_bibliography_or_url_dominant_text(text: str) -> bool:
    stripped = _strip_structural_markdown_prefix(text)
    if not stripped:
        return False
    if _URL_OR_DOMAIN_PATTERN.search(stripped):
        words = _LATIN_WORD_PATTERN.findall(stripped)
        return len(words) < 40
    bibliography_hits = len(_BIBLIOGRAPHY_LIKE_PATTERN.findall(stripped))
    if bibliography_hits >= 3:
        return True
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if lines and sum(1 for line in lines if re.match(r"^\s*(?:\[\d+\]|\d+[.)])\s+", line)) / len(lines) >= 0.5:
        return True
    return False


def _is_untranslated_body_text(text: str) -> bool:
    stripped = _strip_structural_markdown_prefix(text)
    if len(stripped) < _UNTRANSLATED_BODY_MIN_CHARS:
        return False
    if _CYRILLIC_LETTER_PATTERN.search(stripped):
        return False
    if _is_bibliography_or_url_dominant_text(stripped):
        return False
    if _latin_letter_ratio(stripped) < 0.8:
        return False
    if len(_LATIN_WORD_PATTERN.findall(stripped)) < _UNTRANSLATED_BODY_MIN_LATIN_WORDS:
        return False
    return True


def _is_standalone_numeric_continuation_sample(sample: object) -> bool:
    text = str(getattr(sample, "text", "") or "").strip()
    return bool(_STANDALONE_NUMERIC_CONTINUATION_PATTERN.fullmatch(text))


_REFERENCES_BIB_MARKER_PATTERN = re.compile(
    r"\bстр\.|\bс\.\s*\d|\bpp?\.\s*\d|\bvol\.|\bт\.\s*\d|\bтом\s+\d|№\s*\d|\b\d{4}\s*г\.",
    re.IGNORECASE,
)
# Two or more footnote-number markers ("… 42 … 43 …") introducing a citation clause.
_MULTI_FOOTNOTE_MARKER_PATTERN = re.compile(r"(?<!\d)\d{1,3}(?=\s+[«*“\"A-ZА-ЯЁ])")


def _is_citation_form_list_fragment_sample(sample: object) -> bool:
    """A FORM-based credit for a list-fragment residue line: creditable as review, not a
    hard-fail. True for standalone-numeric footnote / page numbers (existing 1‑A crediting)
    OR a citation/notes-form line carrying at least two citation signals (quoted titles
    «…», years, "стр."/journal markers, multiple footnote markers). This does NOT verify
    the sample sits in the references region — `QualityIssueSample` carries only a markdown
    line number, no source index. The anti-vacuum property is purely form-based: a
    bullet-led or plain continuation line with no citation signal is never credited, so a
    real broken body list fragment still hard-fails."""
    if _is_standalone_numeric_continuation_sample(sample):
        return True
    text = str(getattr(sample, "text", "") or "").strip()
    if not text or text[:2] in ("- ", "* ") or text.startswith(("#", ">")):
        return False
    signals = 0
    if _BIBLIOGRAPHY_LIKE_PATTERN.search(text) is not None:
        signals += 1
    if "«" in text or "»" in text:
        signals += 1
    if _REFERENCES_BIB_MARKER_PATTERN.search(text) is not None:
        signals += 1
    if len(_MULTI_FOOTNOTE_MARKER_PATTERN.findall(text)) >= 2:
        signals += 1
    return signals >= 2
