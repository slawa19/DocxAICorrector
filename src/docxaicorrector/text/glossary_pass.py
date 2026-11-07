"""Spec 063 P2 (FR-013…FR-016): the per-run glossary — candidates by FORM, one model call.

Every text call of a book translates its block alone, so an author's own term gets as many
renderings as there were blocks that met it (spec 063 M-1: *bank-debt money* seven ways,
*resilience* and *sustainability* collapsed into one Russian word; M-4: one name, two
transliterations). This module is the pure half of the remedy:

1. ``select_glossary_source_units`` — the paragraphs THIS run will send to the model, in the
   prose and front-matter regions (the bibliography would flood the name family; the title page
   is exactly where an author's name is written in full);
2. ``extract_glossary_candidates`` — candidates by form only: typography (capitals not opening a
   sentence, italics or quotes at first use), the document's own statistics (inverse document
   frequency, the document's own upper/lower-case counts, Dunning's log-likelihood for
   collocations) and the grammar of an English definition. There is no list of terms, and no
   string from any book, anywhere in this file (Constitution VII; spec 063 Non-goals);
3. ``build_glossary_request`` / ``parse_glossary_response`` — the contract of the ONE model
   call that fixes the renderings. An answer is accepted only for a term the request carried:
   the model chooses and renders, it never invents an entry.

The pipeline half (when to run, the call itself, the artifact, the events) lives in
``pipeline/glossary_phase.py``. Why the pass runs in the pipeline and not in preparation, and why
the result is appended to the document context prompt rather than written into the prepared
profile, is argued in ``specs/063-translation-fidelity/research.md`` (R1, R2).
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.document.segments import GLOSSARY_TERM_KINDS, GlossaryTerm
from docxaicorrector.text.translation_domains import build_terminology_plan


GLOSSARY_SOURCE_REGIONS = frozenset({"prose", "front_matter"})
DEFAULT_GLOSSARY_CANDIDATE_LIMIT = 400
DEFAULT_GLOSSARY_MAX_TERMS = 60
GLOSSARY_CONTEXT_CHARS = 100
# Spec 063 P2, two calls by role plus one for collisions (orchestrator decision 4, third pass).
GLOSSARY_ROLE_REQUIRED = "required"
GLOSSARY_ROLE_OPTIONAL = "optional"
GLOSSARY_ROLE_DISTINGUISH = "distinguish"
GLOSSARY_PROMPT_FILES = {
    GLOSSARY_ROLE_REQUIRED: "glossary_required.txt",
    GLOSSARY_ROLE_OPTIONAL: "glossary_optional.txt",
    GLOSSARY_ROLE_DISTINGUISH: "glossary_distinguish.txt",
}
RUN_GLOSSARY_SECTION_HEADER = (
    "ГЛОССАРИЙ ЭТОЙ КНИГИ (построен по документу для текущего запуска; передавайте эти термины "
    "и имена так во всех блоках, склоняя по правилам языка перевода, если не сказано иное):"
)

FAMILY_MARKED = "marked"
FAMILY_NAME = "name"
FAMILY_COLLOCATION = "collocation"
FAMILY_HEAD = "head"
FAMILY_HEADING = "heading"
_FAMILY_ORDER = (FAMILY_MARKED, FAMILY_NAME, FAMILY_HEADING, FAMILY_COLLOCATION, FAMILY_HEAD)
# Shares of the candidate limit per family, after the head family's small fixed slice. Measured
# on the four corpus books (research R3): 74 of the reviewers' 85 key terms land in a list of
# ~400 split 20/50/30; tripling the name share adds none.
_FAMILY_SHARES = ((FAMILY_MARKED, 0.2), (FAMILY_NAME, 0.45), (FAMILY_HEADING, 0.1), (FAMILY_COLLOCATION, 0.25))
# A heading word or phrase is a candidate only when the BODY uses it at least this often: a word
# the author put in a title and then keeps using is a subject of the book (spec 063 P2, decision
# 2 of the third pass); a heading word the body never repeats is not.
_HEADING_MIN_BODY_COUNT = 3
_HEADING_SOURCE_LEVELS = frozenset({1, 2})
# The inclusion rule's "recurring": at least this many occurrences in at least two chapters.
_REQUIRED_MIN_COUNT = 3
_REQUIRED_MIN_CHAPTERS = 2
_HEAD_SHARE_DIVISOR = 25
_HEAD_MAX = 16
_HEAD_MIN_MEMBERSHIP = 3

_MAX_TERM_WORDS = 4
_SPREAD_BINS = 10
_MIN_COLLOCATION_COUNT = 3
_MIN_COLLOCATION_EDGE_LETTERS = 4
_MAX_JOINER_LETTERS = 3

_LETTER = r"[^\W\d_]"
_WORD = _LETTER + r"(?:" + _LETTER + r"|['’\-])*" + _LETTER + r"|" + _LETTER
_WORD_RE = re.compile(_WORD)
_TOKEN_RE = re.compile(_WORD + r"|[.!?:;,\"“”‘’()\[\]—–•]")
_ITALIC_RE = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]{1,80}?)(?<!\s)\*(?![*\w])")
_BOLD_RE = re.compile(r"\*\*([^*\n]{1,80}?)\*\*")
_QUOTE_RE = re.compile(r"[“\"‘]([^“”\"‘’\n]{1,60}?)[”\"’](?!" + _LETTER + r")")
_EMPHASIS_MARKS_RE = re.compile(r"\*+")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\S*[A-Za-z0-9]\.[A-Za-z]{2,}/\S*")
_ROMAN_NUMERAL_RE = re.compile(r"^[IVXLCDM]+$")
_SENTENCE_BREAKS = frozenset(".!?:;\"“”‘(—–[•")
_CLAUSE_SPLIT_RE = re.compile(r"[.!?:;,()\[\]—–\"“”‘’•]")
_LEADING_ARTICLE_RE = re.compile(r"^\s*(?:a|an|the)\s+", re.IGNORECASE)
_LEADING_MARKED_SPAN_RE = (
    re.compile(r"\s*\*([^*]{1,80}?)\*"),
    re.compile(r"\s*[“\"‘]([^”\"’]{1,60})[”\"’]"),
)
# The grammar of an English definition — six verbs, no term. The constitution's acknowledged
# class of language resource ("general across books and extensible per language, NOT a per-book
# literal"); a source language without these constructions simply has no definitional signal and
# the three other families still work (research R3).
_DEFINITION_PATTERNS = (
    re.compile(r"\brefer(?:s|red)?\s+to\s+[^.;:!?]{0,60}?\s+as\s+(?P<tail>.{1,80})", re.IGNORECASE),
    re.compile(
        r"\b(?:we|I)\s+(?:will\s+|shall\s+)?(?:call|term|dub|name)\s+(?:this|it|them|these)?\s*(?P<tail>.{1,80})",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:called|termed|dubbed|known\s+as|defined\s+as|so-called)\s+(?P<tail>.{1,80})", re.IGNORECASE),
)


class GlossaryResponseError(RuntimeError):
    """The glossary call answered with something that is not a usable glossary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class GlossarySourceUnit:
    unit_id: str
    text: str
    is_heading: bool = False
    heading_level: int | None = None


@dataclass(frozen=True)
class GlossaryCandidate:
    source_term: str
    key: tuple[str, ...]
    family: str
    signals: tuple[str, ...]
    occurrence_count: int
    unit_count: int
    spread: int
    first_unit_id: str
    context: str
    score: float
    # Spec 063 P2, inclusion rule: the AUTHOR marked or defined this expression (or it heads a
    # family of at least three candidates), so it enters the glossary by rule — the model is
    # asked only for its rendering, never whether to include it.
    required: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "term": self.source_term,
            "family": self.family,
            "required": self.required,
            "signals": list(self.signals),
            "count": self.occurrence_count,
            "unit_count": self.unit_count,
            "spread": self.spread,
            "first_unit_id": self.first_unit_id,
            "context": self.context,
        }


@dataclass(frozen=True)
class GlossaryParseResult:
    terms: tuple[GlossaryTerm, ...]
    rejected_counts: dict[str, int]


@dataclass
class _Draft:
    key: tuple[str, ...]
    surface: str
    proper: bool
    signals: set[str] = field(default_factory=set)
    count: int = 0
    units: set[int] = field(default_factory=set)
    score: float = 0.0
    family: str = ""
    # Where the author introduced the term (a definition, or italics/quotes at first use): the
    # model reads THIS context, not an incidental first mention, to choose the rendering.
    signal_unit: int | None = None
    chapters: int = 0
    heading_unit: int | None = None
    heading_weight: int = 0
    marked_count: int = 0
    heads_required_member: bool = False


# --- unit selection --------------------------------------------------------------------------


def select_glossary_source_units(
    jobs: Sequence[Mapping[str, object]],
    source_paragraphs: Sequence[object] | None,
) -> tuple[GlossarySourceUnit, ...]:
    """The paragraphs this run will send to the model, in the prose and front-matter regions.

    A job without ``paragraph_regions`` (an old caller) counts as prose: the region is a filter,
    and its absence must not silently empty the glossary.
    """

    paragraphs_by_id: dict[str, object] = {}
    for paragraph in source_paragraphs or ():
        paragraph_id = str(getattr(paragraph, "paragraph_id", "") or "").strip()
        if paragraph_id:
            paragraphs_by_id[paragraph_id] = paragraph

    units: list[GlossarySourceUnit] = []
    seen: set[str] = set()
    for job_index, job in enumerate(jobs):
        if str(job.get("job_kind", "llm") or "llm") != "llm":
            continue
        raw_ids = job.get("paragraph_ids")
        paragraph_ids = [str(item) for item in raw_ids] if isinstance(raw_ids, (list, tuple)) else []
        raw_regions = job.get("paragraph_regions")
        regions = [str(item) for item in raw_regions] if isinstance(raw_regions, (list, tuple)) else []
        if not paragraph_ids or not paragraphs_by_id:
            text = str(job.get("target_text", "") or "").strip()
            if text:
                units.append(GlossarySourceUnit(unit_id=f"job{job_index}", text=text))
            continue
        for position, paragraph_id in enumerate(paragraph_ids):
            region = regions[position] if position < len(regions) else "prose"
            if region not in GLOSSARY_SOURCE_REGIONS or paragraph_id in seen:
                continue
            paragraph = paragraphs_by_id.get(paragraph_id)
            if paragraph is None or str(getattr(paragraph, "role", "") or "") == "image":
                continue
            text = str(getattr(paragraph, "text", "") or "").strip()
            if not text:
                continue
            seen.add(paragraph_id)
            units.append(
                GlossarySourceUnit(
                    unit_id=paragraph_id,
                    text=text,
                    is_heading=str(getattr(paragraph, "role", "") or "") == "heading",
                    heading_level=_heading_level(paragraph),
                )
            )
    return tuple(units)


def _heading_level(paragraph: object) -> int | None:
    if str(getattr(paragraph, "role", "") or "") != "heading":
        return None
    level = getattr(paragraph, "heading_level", None)
    return level if isinstance(level, int) and not isinstance(level, bool) else None


# --- normalisation ---------------------------------------------------------------------------


def _fold_word(word: str) -> str:
    """One word with its English plural and possessive folded; acronyms are left alone."""

    folded = word.replace("’", "'")
    if folded.endswith("'s"):
        folded = folded[:-2]
    lowered = folded.lower()
    if folded.isupper():
        return folded
    if len(lowered) > 4 and lowered.endswith("ies"):
        return folded[:-3] + "y"
    if len(lowered) > 3 and lowered.endswith("s") and not lowered.endswith("ss"):
        return folded[:-1]
    return folded


def normalize_glossary_key(term: str) -> tuple[str, ...]:
    """The case-insensitive identity of a term, used to match a model answer to a candidate."""

    return tuple(_fold_word(word).lower() for word in _WORD_RE.findall(str(term or "")))


def _plain(text: str) -> str:
    return _URL_RE.sub(" ", _EMPHASIS_MARKS_RE.sub("", text))


# --- extraction ------------------------------------------------------------------------------


def _capitalised_runs(plain: str) -> list[list[str]]:
    """Runs of capitalised words; a run that opens a sentence is marked with a leading ``None``.

    Short lowercase joiners (``of``, ``for``) are kept inside a run when a capitalised word
    follows them, so an institution's name stays one candidate.
    """

    tokens = [match.group(0) for match in _TOKEN_RE.finditer(plain)]
    runs: list[list[str]] = []
    index = 0
    sentence_start = True
    while index < len(tokens):
        token = tokens[index]
        if not _WORD_RE.fullmatch(token):
            if token in _SENTENCE_BREAKS:
                sentence_start = True
            index += 1
            continue
        if not token[:1].isupper():
            sentence_start = False
            index += 1
            continue
        run = [token]
        cursor = index + 1
        while cursor < len(tokens):
            following = tokens[cursor]
            if _WORD_RE.fullmatch(following) and following[:1].isupper():
                run.append(following)
                cursor += 1
                continue
            if (
                _WORD_RE.fullmatch(following)
                and following.islower()
                and len(following) <= _MAX_JOINER_LETTERS
                and cursor + 1 < len(tokens)
                and _WORD_RE.fullmatch(tokens[cursor + 1])
                and tokens[cursor + 1][:1].isupper()
            ):
                run.append(following)
                cursor += 1
                continue
            break
        if not sentence_start:
            if len(run) <= _MAX_TERM_WORDS:
                runs.append(run)
        elif len(run) >= 2 and run[1][:1].isupper():
            if len(run) - 1 <= _MAX_TERM_WORDS:
                runs.append(run[1:])
            if len(run) <= _MAX_TERM_WORDS:
                runs.append([""] + run)  # the whole run, admitted later only by its first word
        index = cursor
        sentence_start = False
    return runs


def _defined_term_words(tail: str) -> list[str]:
    tail = _LEADING_ARTICLE_RE.sub(" ", tail)
    for pattern in _LEADING_MARKED_SPAN_RE:
        match = pattern.match(tail)
        if match:
            return _WORD_RE.findall(match.group(1))
    words: list[str] = []
    for match in _TOKEN_RE.finditer(_EMPHASIS_MARKS_RE.sub("", tail)):
        token = match.group(0)
        if not _WORD_RE.fullmatch(token):
            return words
        words.append(token)
        if len(words) > _MAX_TERM_WORDS - 1:
            return []
    return []


def _trim_joiners(words: Sequence[str]) -> list[str]:
    """A marked span without the short words at its edges ("The problem" -> "problem").

    Up to three letters at the START ("the", "of", "as a"), only up to two at the END ("of",
    "to"): a three-letter word that ends an expression is usually its noun ("tallow gap").
    """

    trimmed = list(words)
    while trimmed and len(trimmed[0]) <= _MAX_JOINER_LETTERS and not trimmed[0].isupper():
        trimmed.pop(0)
    while trimmed and len(trimmed[-1]) <= _MAX_JOINER_LETTERS - 1 and not trimmed[-1].isupper():
        trimmed.pop()
    return trimmed


def _log_likelihood_term(k: float, n: float) -> float:
    return k * math.log(k / n) if k > 0 and n > 0 else 0.0


def _dunning_g2(joint: int, left: int, right: int, total: int) -> float:
    k11, k12, k21 = joint, left - joint, right - joint
    k22 = total - left - right + joint
    return 2.0 * (
        _log_likelihood_term(k11, k11 + k12)
        + _log_likelihood_term(k12, k11 + k12)
        + _log_likelihood_term(k21, k21 + k22)
        + _log_likelihood_term(k22, k21 + k22)
        - _log_likelihood_term(k11 + k21, total)
        - _log_likelihood_term(k12 + k22, total)
    )


def _is_acronym_like(words: Sequence[str]) -> bool:
    content = [word for word in words if not (word.islower() and len(word) <= _MAX_JOINER_LETTERS)]
    return bool(content) and all(word.isupper() and len(word) >= 2 for word in content)


def _family_quotas(limit: int) -> dict[str, int]:
    limit = max(0, int(limit))
    head = min(_HEAD_MAX, limit // _HEAD_SHARE_DIVISOR)
    rest = limit - head
    quotas = {family: int(round(rest * share)) for family, share in _FAMILY_SHARES}
    quotas[FAMILY_COLLOCATION] = max(
        0, rest - quotas[FAMILY_MARKED] - quotas[FAMILY_NAME] - quotas[FAMILY_HEADING]
    )
    quotas[FAMILY_HEAD] = head
    return quotas


def extract_glossary_candidates(
    units: Sequence[GlossarySourceUnit],
    *,
    limit: int = DEFAULT_GLOSSARY_CANDIDATE_LIMIT,
) -> tuple[GlossaryCandidate, ...]:
    """Glossary candidates of a document, by form only (spec 063 FR-013; research R3).

    Deterministic: the same units give the same candidates in the same order.
    """

    unit_count = len(units)
    if unit_count == 0 or limit <= 0:
        return ()
    plains = [_plain(unit.text) for unit in units]
    marked_sources = [_URL_RE.sub(" ", unit.text) for unit in units]
    folded_tokens = [[_fold_word(word) for word in _WORD_RE.findall(plain)] for plain in plains]

    hits_exact: dict[tuple[str, ...], list[int]] = defaultdict(list)
    hits_folded_case: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for unit_index, words in enumerate(folded_tokens):
        for size in range(1, _MAX_TERM_WORDS + 1):
            for start in range(len(words) - size + 1):
                gram = tuple(words[start : start + size])
                hits_exact[gram].append(unit_index)
                hits_folded_case[tuple(word.lower() for word in gram)].append(unit_index)

    raw_case_counts = Counter(word for plain in plains for word in _WORD_RE.findall(plain))
    body_indexes = [index for index, unit in enumerate(units) if not unit.is_heading]

    drafts: dict[tuple[str, ...], _Draft] = {}
    marked_units: dict[tuple[str, ...], set[int]] = defaultdict(set)
    defined_units: dict[tuple[str, ...], set[int]] = defaultdict(set)
    capitalised_noninitial: Counter[tuple[str, ...]] = Counter()

    def admit(raw_words: Sequence[str], signal: str, unit_index: int, *, proper: bool) -> None:
        words = [_fold_word(word) for word in raw_words]
        if not words or len(words) > _MAX_TERM_WORDS:
            return
        if len(words) == 1 and (len(words[0]) < 2 or _ROMAN_NUMERAL_RE.match(words[0])):
            return
        key = tuple(words) if proper else tuple(word.lower() for word in words)
        if signal in {"emphasis", "quoted"}:
            marked_units[key].add(unit_index)
        if signal == "defined":
            defined_units[key].add(unit_index)
        if signal == "capitalised":
            capitalised_noninitial[key] += 1
        draft = drafts.get(key)
        if draft is None:
            draft = drafts[key] = _Draft(key=key, surface=" ".join(raw_words), proper=proper)
        draft.signals.add(signal)

    word_counts: Counter[str] = Counter()
    total_words = 0
    for unit_index in body_indexes:
        word_counts.update(word.lower() for word in folded_tokens[unit_index])
        total_words += len(folded_tokens[unit_index])

    # Chapters: the stretches between headings of level 1 or 2. A document with fewer than two
    # such headings falls back to tenths of the text, so "recurs in two chapters" still means
    # "recurs in two separate places".
    chapter_of: list[int] = []
    chapter_index = 0
    top_headings = sum(1 for unit in units if unit.is_heading and unit.heading_level in _HEADING_SOURCE_LEVELS)
    for unit_index, unit in enumerate(units):
        if top_headings >= 2:
            if unit.is_heading and unit.heading_level in _HEADING_SOURCE_LEVELS:
                chapter_index += 1
            chapter_of.append(chapter_index)
        else:
            chapter_of.append(unit_index * _SPREAD_BINS // unit_count)

    def admit_marked(words: Sequence[str], signal: str, unit_index: int) -> None:
        trimmed = _trim_joiners(words)
        if not trimmed:
            return
        admit(trimmed, signal, unit_index, proper=False)

    for unit_index in body_indexes:
        plain = plains[unit_index]
        source = marked_sources[unit_index]
        for run in _capitalised_runs(plain):
            if run[0] == "":
                run = run[1:]
                first = run[0]
                first_is_name = raw_case_counts[first] > raw_case_counts[first.lower()]
                if not (first.isupper() and len(first) >= 2) and not first_is_name:
                    continue
            admit(run, "capitalised", unit_index, proper=True)
        emphasis_free = _EMPHASIS_MARKS_RE.sub("", source)
        for pattern, signal, text in (
            (_ITALIC_RE, "emphasis", source),
            (_BOLD_RE, "emphasis", source),
            (_QUOTE_RE, "quoted", emphasis_free),
        ):
            for match in pattern.finditer(text):
                span = match.group(1)
                words = _WORD_RE.findall(span)
                if 1 <= len(words) <= _MAX_TERM_WORDS and len(span) < 0.8 * len(text):
                    admit_marked(words, signal, unit_index)
        for pattern in _DEFINITION_PATTERNS:
            for match in pattern.finditer(source):
                words = _defined_term_words(match.group("tail"))
                if words:
                    admit_marked(words, "defined", unit_index)

    body_index_set = set(body_indexes)
    for unit_index, unit in enumerate(units):
        if not unit.is_heading or unit.heading_level not in _HEADING_SOURCE_LEVELS:
            continue
        heading_words = _WORD_RE.findall(plains[unit_index])
        for size in (1, 2, 3):
            for start in range(len(heading_words) - size + 1):
                phrase = heading_words[start : start + size]
                if _trim_joiners(phrase) != phrase:
                    continue
                if size == 1 and len(phrase[0]) <= _MAX_JOINER_LETTERS:
                    continue
                key = tuple(_fold_word(word).lower() for word in phrase)
                body_hits = [hit for hit in hits_folded_case.get(key, []) if hit in body_index_set]
                if len(body_hits) < _HEADING_MIN_BODY_COUNT:
                    continue
                draft = drafts.get(key)
                if draft is None:
                    draft = drafts[key] = _Draft(key=key, surface=" ".join(word.lower() for word in phrase), proper=False)
                draft.signals.add("heading")
                # A level-1 heading (chapter, title) weighs twice a level-2 one; the phrase's
                # weight is what ranks it among heading candidates, ahead of its body frequency.
                draft.heading_weight += 2 if unit.heading_level == 1 else 1
                if draft.heading_unit is None:
                    draft.heading_unit = unit_index

    gram_counts: Counter[tuple[str, ...]] = Counter()
    for unit_index in body_indexes:
        for clause in _CLAUSE_SPLIT_RE.split(plains[unit_index]):
            raw = _WORD_RE.findall(clause)
            for size in (2, 3):
                for start in range(len(raw) - size + 1):
                    gram = raw[start : start + size]
                    if not all(word.islower() for word in gram):
                        continue
                    if len(gram[0]) < _MIN_COLLOCATION_EDGE_LETTERS or len(gram[-1]) < _MIN_COLLOCATION_EDGE_LETTERS:
                        continue
                    if size == 3 and len(gram[1]) > _MAX_JOINER_LETTERS:
                        continue
                    gram_counts[tuple(_fold_word(word) for word in gram)] += 1
    collocation_scores: dict[tuple[str, ...], float] = {}
    for gram, joint in gram_counts.items():
        if joint < _MIN_COLLOCATION_COUNT:
            continue
        left, right = word_counts[gram[0]], word_counts[gram[-1]]
        if joint * total_words <= left * right:  # PMI <= 0: not an association at all
            continue
        collocation_scores[gram] = _dunning_g2(joint, left, right, total_words)
        drafts.setdefault(gram, _Draft(key=gram, surface=" ".join(gram), proper=False)).signals.add("collocation")

    def bin_of(unit_index: int) -> int:
        return unit_index * _SPREAD_BINS // unit_count

    def first_unit_of_bin(bin_index: int) -> int:
        return -(-bin_index * unit_count // _SPREAD_BINS)

    families: dict[str, list[_Draft]] = defaultdict(list)
    for key, draft in drafts.items():
        hits = hits_exact.get(key, []) if draft.proper else hits_folded_case.get(key, [])
        units_hit = set(hits)
        if len(units_hit) < 2:
            continue
        idf = math.log(unit_count / len(units_hit))
        if idf <= 0:
            continue
        draft.count = len(hits)
        draft.units = units_hit
        if key in marked_units:
            # First-use marking: the marked occurrence opens its stretch of the book. A word
            # italicised for stress somewhere in the middle is not a term being introduced.
            first_use_units = sorted(
                marked
                for marked in marked_units[key]
                if not any(first_unit_of_bin(bin_of(marked)) <= unit < marked for unit in units_hit)
            )
            if first_use_units:
                draft.signal_unit = first_use_units[0]
                draft.marked_count = len(marked_units[key])
            else:
                draft.signals -= {"emphasis", "quoted"}
        if defined_units.get(key):
            draft.signal_unit = min(defined_units[key])
        if "capitalised" in draft.signals and not _is_acronym_like(key):
            # The document's own case test: a capitalised form is a name only when the lowercase
            # form is rarer than the capitalised one mid-sentence ("This", "Bank", "Money" fail).
            lowercase_hits = len(hits_folded_case.get(tuple(word.lower() for word in key), [])) - draft.count
            if lowercase_hits >= capitalised_noninitial[key]:
                draft.signals.discard("capitalised")
        if not draft.signals:
            continue
        spread = len({bin_of(unit) for unit in units_hit})
        draft.chapters = len({chapter_of[unit] for unit in units_hit})
        if draft.signals & {"emphasis", "quoted", "defined"}:
            draft.family = FAMILY_MARKED
        elif "capitalised" in draft.signals:
            draft.family = FAMILY_NAME
        elif "heading" in draft.signals:
            draft.family = FAMILY_HEADING
        else:
            draft.family = FAMILY_COLLOCATION
        if draft.family == FAMILY_COLLOCATION:
            draft.score = collocation_scores.get(key, 0.0)
        elif draft.family == FAMILY_HEADING:
            draft.score = draft.heading_weight * math.log2(1 + draft.count) * idf
        else:
            draft.score = math.log2(1 + draft.count) * idf * (1 + spread / _SPREAD_BINS)
        families[draft.family].append(draft)

    quotas = _family_quotas(limit)

    def ranked(family: str) -> list[_Draft]:
        return sorted(families[family], key=lambda draft: (-draft.score, draft.key))

    membership: Counter[str] = Counter()
    required_membership: set[str] = set()
    for family in (FAMILY_MARKED, FAMILY_NAME, FAMILY_HEADING, FAMILY_COLLOCATION):
        for draft in ranked(family)[: quotas[family]]:
            if len(draft.key) >= 2:
                # Only a word at the EDGE of a member counts: "value" in "value creation" and
                # "surplus value" heads a family; a word inside an expression does not.
                for word in {draft.key[0].lower(), draft.key[-1].lower()}:
                    if len(word) >= _MIN_COLLOCATION_EDGE_LETTERS:
                        membership[word] += 1
                        if _included_by_rule(draft):
                            required_membership.add(word)
    for word, members in membership.items():
        if members < _HEAD_MIN_MEMBERSHIP:
            continue
        key = (word,)
        existing = drafts.get(key)
        if existing is not None and existing.family:
            continue
        units_hit = set(hits_folded_case.get(key, []))
        if len(units_hit) < 2:
            continue
        head = drafts.setdefault(key, _Draft(key=key, surface=word, proper=False))
        head.signals.add("family_head")
        head.family = FAMILY_HEAD
        head.count = len(hits_folded_case.get(key, []))
        head.units = units_hit
        head.score = float(members) + head.count / (head.count + 1.0)
        head.heads_required_member = word in required_membership
        families[FAMILY_HEAD].append(head)

    selected: list[_Draft] = []
    seen_keys: set[tuple[str, ...]] = set()
    for family in _FAMILY_ORDER:
        for draft in ranked(family)[: quotas[family]]:
            identity = tuple(word.lower() for word in draft.key)
            if identity in seen_keys:
                continue
            seen_keys.add(identity)
            selected.append(draft)

    candidates: list[GlossaryCandidate] = []
    for draft in selected[:limit]:
        first_unit = min(draft.units)
        if draft.family == FAMILY_MARKED and draft.signal_unit is not None:
            context_unit = draft.signal_unit
        elif draft.family == FAMILY_HEADING and draft.heading_unit is not None:
            context_unit = draft.heading_unit
        else:
            context_unit = first_unit
        candidates.append(
            GlossaryCandidate(
                source_term=draft.surface,
                key=draft.key,
                family=draft.family,
                signals=tuple(sorted(draft.signals)),
                occurrence_count=draft.count,
                unit_count=len(draft.units),
                spread=len({bin_of(unit) for unit in draft.units}),
                first_unit_id=units[first_unit].unit_id,
                context=_context_snippet(plains[context_unit], draft.surface),
                score=round(draft.score, 4),
                required=_included_by_rule(draft),
            )
        )
    return tuple(candidates)


def _included_by_rule(draft: _Draft) -> bool:
    """Which candidates the author put in the glossary, by form (spec 063 P2 inclusion rule).

    MARKED AND RECURRING. A definition is the author's own act of naming a concept and is
    required however rare. Italics or bold at first use (and quotes around an expression) are
    required only when the term then RECURS — at least ``_REQUIRED_MIN_COUNT`` occurrences in at
    least ``_REQUIRED_MIN_CHAPTERS`` chapters — AND the marking itself is not a one-off stress:
    the author marks it at least twice, or marks it where it first appears in the text. A word
    stressed once in passing is not promoted to a term (it may stay an optional candidate). A family head stands for at least three
    candidates (``_HEAD_MIN_MEMBERSHIP``) and is required when at least one member is. Quotes
    around ONE word are left to the model.
    """

    if draft.family == FAMILY_HEAD:
        # A head is required when it heads a family (>= 3 members) one of whose members the
        # author marked; a head of grammatical collocations ("have been", "they have") is not.
        return draft.heads_required_member
    if draft.family != FAMILY_MARKED:
        return False
    if "defined" in draft.signals:
        return True
    marked = "emphasis" in draft.signals or ("quoted" in draft.signals and len(draft.key) > 1)
    recurring = draft.count >= _REQUIRED_MIN_COUNT and draft.chapters >= _REQUIRED_MIN_CHAPTERS
    # An ordinary word recurs anyway; what recurs for a TERM is the author's marking of it.
    # Marked once, the expression must be marked where it first appears in the whole text.
    marking_recurs = draft.marked_count >= 2 or draft.signal_unit == min(draft.units, default=-1)
    return marked and recurring and marking_recurs


def _context_snippet(plain: str, surface: str) -> str:
    flat = " ".join(plain.split())
    first_word = (_WORD_RE.findall(surface) or [""])[0]
    match = re.search(re.escape(first_word), flat, re.IGNORECASE) if first_word else None
    anchor = match.start() if match else 0
    start = max(0, anchor - GLOSSARY_CONTEXT_CHARS // 2)
    return flat[start : start + GLOSSARY_CONTEXT_CHARS]


# --- the domain glossary as one input among others (FR-016) ------------------------------------


def glossary_terms_from_plan(plan_text: str) -> tuple[GlossaryTerm, ...]:
    """``A -> B`` lines of a terminology plan as glossary entries; anything else is skipped."""

    terms: list[GlossaryTerm] = []
    for line in str(plan_text or "").splitlines():
        normalized_line = line.strip()
        if not normalized_line or "->" not in normalized_line:
            continue
        source_term, target_term = normalized_line.split("->", 1)
        source_term = source_term.strip()
        target_term = target_term.strip()
        if not source_term or not target_term:
            continue
        terms.append(GlossaryTerm(source_term=source_term, target_term=target_term, confidence="medium"))
    return tuple(terms)


def domain_glossary_terms(*, source_text: str, translation_domain: str) -> tuple[GlossaryTerm, ...]:
    """The translation domain's fixed terms for this text — unchanged by spec 063 (FR-016)."""

    return glossary_terms_from_plan(
        build_terminology_plan(source_text=source_text, translation_domain=translation_domain)
    )


# --- the model call's contract ---------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_glossary_instructions(role: str) -> str:
    return (PROMPTS_DIR / GLOSSARY_PROMPT_FILES[role]).read_text(encoding="utf-8").strip()


def _request_envelope(*, model: str, instructions: str, payload: Mapping[str, object], max_output_tokens: int) -> dict[str, object]:
    return {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(payload, ensure_ascii=False)}],
            },
        ],
        "temperature": 0.2,
        "max_output_tokens": max_output_tokens,
    }


def request_candidates(
    candidates: Sequence[GlossaryCandidate],
    fixed_terms: Sequence[GlossaryTerm],
) -> tuple[GlossaryCandidate, ...]:
    """Candidates left for the model once the domain's fixed terms are taken out."""

    fixed_keys = {normalize_glossary_key(term.source_term) for term in fixed_terms}
    return tuple(candidate for candidate in candidates if normalize_glossary_key(candidate.source_term) not in fixed_keys)


def glossary_max_output_tokens(max_terms: int) -> int:
    return max(1024, min(8192, 60 * max(1, int(max_terms))))


def build_glossary_request(
    *,
    model: str,
    candidates: Sequence[GlossaryCandidate],
    fixed_terms: Sequence[GlossaryTerm],
    source_language: str,
    target_language: str,
    max_terms: int,
    sample_text: str = "",
    role: str = GLOSSARY_ROLE_OPTIONAL,
    already_fixed: Sequence[GlossaryTerm] = (),
) -> dict[str, object]:
    """One glossary request, in the Responses ``input`` shape every provider helper accepts.

    ``role="required"`` asks only for renderings of what the author introduced (call A);
    ``role="optional"`` asks for the model's own choices plus anything call A left out, and
    shows what is ``already_fixed`` so no optional entry takes a rendering already in use (B).
    """

    source_label = describe_source_language(source_language, sample_text=sample_text)
    instructions = _load_glossary_instructions(role).format(
        source_language=source_label,
        target_language=str(target_language or ""),
        max_terms=int(max_terms),
    )
    payload: dict[str, object] = {
        "source_language": source_label,
        "target_language": str(target_language or ""),
        "fixed_terms": [
            {"source_term": term.source_term, "target_term": term.target_term} for term in fixed_terms
        ],
        "candidates": [
            {
                "id": index + 1,
                "term": candidate.source_term,
                "family": candidate.family,
                "required": candidate.required,
                "signals": list(candidate.signals),
                "count": candidate.occurrence_count,
                "context": candidate.context,
            }
            for index, candidate in enumerate(candidates)
        ],
    }
    if role == GLOSSARY_ROLE_OPTIONAL:
        payload["max_terms"] = int(max_terms)
        payload["already_fixed"] = [
            {"source_term": term.source_term, "target_term": term.target_term} for term in already_fixed
        ]
    entry_budget = len(candidates) if role == GLOSSARY_ROLE_REQUIRED else int(max_terms) + sum(
        1 for candidate in candidates if candidate.required
    )
    return _request_envelope(
        model=model,
        instructions=instructions,
        payload=payload,
        max_output_tokens=glossary_max_output_tokens(entry_budget),
    )


def normalize_rendering(target_term: str) -> tuple[str, ...]:
    """A rendering's identity for the collision check: case, «ё», punctuation and endings off.

    Each word is cut to its first ``max(3, len - 3)`` letters — the same stem rule as the
    consistency script — so «устойчивость» and «устойчивости» are one rendering, while
    «жизнестойкость» is another.
    """

    words = re.findall(_LETTER + r"+", str(target_term or "").lower().replace("ё", "е"))
    return tuple(word[: max(3, len(word) - 3)] for word in words)


def find_rendering_collisions(terms: Sequence[GlossaryTerm]) -> list[list[GlossaryTerm]]:
    """Groups of entries whose DIFFERENT source terms share one rendering (decision 3)."""

    by_rendering: dict[tuple[str, ...], dict[tuple[str, ...], GlossaryTerm]] = defaultdict(dict)
    for term in terms:
        rendering = normalize_rendering(term.target_term)
        if not rendering:
            continue
        by_rendering[rendering].setdefault(normalize_glossary_key(term.source_term), term)
    return [list(group.values()) for group in by_rendering.values() if len(group) >= 2]


def build_distinction_request(
    *,
    model: str,
    groups: Sequence[Sequence[GlossaryTerm]],
    contexts: Mapping[tuple[str, ...], str],
    source_language: str,
    target_language: str,
    sample_text: str = "",
) -> dict[str, object]:
    """Call C: one request for every collision group, with each term's context."""

    source_label = describe_source_language(source_language, sample_text=sample_text)
    instructions = _load_glossary_instructions(GLOSSARY_ROLE_DISTINGUISH).format(
        source_language=source_label,
        target_language=str(target_language or ""),
        max_terms=0,
    )
    payload = {
        "source_language": source_label,
        "target_language": str(target_language or ""),
        "groups": [
            {
                "current_rendering": group[0].target_term,
                "terms": [
                    {
                        "term": term.source_term,
                        "context": contexts.get(normalize_glossary_key(term.source_term), ""),
                    }
                    for term in group
                ],
            }
            for group in groups
        ],
    }
    return _request_envelope(
        model=model,
        instructions=instructions,
        payload=payload,
        max_output_tokens=glossary_max_output_tokens(sum(len(group) for group in groups)),
    )


_SOURCE_LANGUAGE_UNKNOWN = "the source language of the text"


def describe_source_language(source_language: str, *, sample_text: str = "") -> str:
    """A language the model can be told, never the literal setting ``auto``.

    ``auto`` is a UI choice, not a language. The product's only detector is the script
    assessment of ``text/transform_assessment.py``, which names a language only when the
    script settles it (Cyrillic today); otherwise the instruction says what is known.
    """

    normalized = str(source_language or "").strip().lower()
    if normalized and normalized != "auto":
        return normalized
    if sample_text:
        from docxaicorrector.text.transform_assessment import assess_text_transform_excerpt

        detected = assess_text_transform_excerpt(sample_text, target_language="")["dominant_language"]
        if detected:
            return str(detected)
    return _SOURCE_LANGUAGE_UNKNOWN


def missing_required_candidates(
    candidates: Sequence[GlossaryCandidate],
    terms: Sequence[GlossaryTerm],
) -> tuple[GlossaryCandidate, ...]:
    """Required candidates the answer gave no rendering for."""

    rendered = {normalize_glossary_key(term.source_term) for term in terms}
    return tuple(
        candidate
        for candidate in candidates
        if candidate.required and normalize_glossary_key(candidate.source_term) not in rendered
    )


def order_required_first(
    candidates: Sequence[GlossaryCandidate],
    terms: Sequence[GlossaryTerm],
) -> tuple[GlossaryTerm, ...]:
    """Rule-included entries first (in candidate order), then the model's own choices.

    The prompt budget cuts from the END, so a rule-included term is never the one dropped
    to make room for an optional one.
    """

    by_key: dict[tuple[str, ...], list[GlossaryTerm]] = defaultdict(list)
    for term in terms:
        by_key[normalize_glossary_key(term.source_term)].append(term)
    ordered: list[GlossaryTerm] = []
    for candidate in candidates:
        if candidate.required:
            ordered.extend(by_key.pop(normalize_glossary_key(candidate.source_term), []))
    for term in terms:
        if normalize_glossary_key(term.source_term) in by_key:
            ordered.append(term)
    return tuple(ordered)


def _load_json_object(raw_text: str) -> dict[str, object]:
    text = str(raw_text or "").strip()
    if not text:
        raise GlossaryResponseError("empty_response", "glossary call returned no text")
    if text.startswith("```"):
        text = text.strip("`")
        newline = text.find("\n")
        text = text[newline + 1 :] if newline != -1 else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise GlossaryResponseError("no_json", "glossary call returned no JSON object")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GlossaryResponseError("invalid_json", f"glossary call returned invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise GlossaryResponseError("invalid_json", "glossary call did not return a JSON object")
    return payload


def parse_glossary_response(
    raw_text: str,
    *,
    candidates: Sequence[GlossaryCandidate],
    max_terms: int,
) -> GlossaryParseResult:
    """Accept only renderings of terms the request carried (contract: ``contracts/glossary.md``)."""

    payload = _load_json_object(raw_text)
    # Two lists (required renderings, then the model's own choices) make the model answer
    # both halves; a single "terms" list is still accepted.
    entries: list[object] = []
    found_list = False
    for list_key in ("required_terms", "other_terms", "terms"):
        value = payload.get(list_key)
        if isinstance(value, list):
            entries.extend(value)
            found_list = True
    if not found_list:
        raise GlossaryResponseError("invalid_shape", "glossary JSON has no list of terms")
    surface_by_key = {}
    required_keys: set[tuple[str, ...]] = set()
    for candidate in candidates:
        candidate_key = normalize_glossary_key(candidate.source_term)
        surface_by_key.setdefault(candidate_key, candidate.source_term)
        if candidate.required:
            required_keys.add(candidate_key)
    rejected = {"not_a_candidate": 0, "empty_target": 0, "duplicate_sense": 0, "over_limit": 0}
    accepted: list[GlossaryTerm] = []
    optional_count = 0
    notes_by_key: dict[tuple[str, ...], list[str]] = defaultdict(list)
    limit = max(0, int(max_terms))
    for entry in entries:
        if not isinstance(entry, Mapping):
            rejected["not_a_candidate"] += 1
            continue
        key = normalize_glossary_key(str(entry.get("source_term", "") or ""))
        if not key or key not in surface_by_key:
            rejected["not_a_candidate"] += 1
            continue
        target_term = " ".join(str(entry.get("target_term", "") or "").split())
        if not target_term:
            rejected["empty_target"] += 1
            continue
        note = " ".join(str(entry.get("note", "") or "").split())
        previous_notes = notes_by_key[key]
        if previous_notes and (len(previous_notes) >= 2 or not note or note in previous_notes):
            rejected["duplicate_sense"] += 1
            continue
        is_required = key in required_keys
        if not is_required and optional_count >= limit:
            # ``max_terms`` bounds the model's OWN choices; a rule-included term is never
            # refused for lack of room (spec 063 P2 inclusion rule).
            rejected["over_limit"] += 1
            continue
        if not is_required:
            optional_count += 1
        kind = str(entry.get("kind", "") or "").strip().lower()
        previous_notes.append(note)
        accepted.append(
            GlossaryTerm(
                source_term=surface_by_key[key],
                target_term=target_term,
                confidence="medium",
                kind=kind if kind in GLOSSARY_TERM_KINDS else "term",
                note=note,
            )
        )
    return GlossaryParseResult(terms=tuple(accepted), rejected_counts=rejected)


__all__ = [
    "DEFAULT_GLOSSARY_CANDIDATE_LIMIT",
    "DEFAULT_GLOSSARY_MAX_TERMS",
    "GLOSSARY_SOURCE_REGIONS",
    "GlossaryCandidate",
    "GlossaryParseResult",
    "GlossaryResponseError",
    "GlossarySourceUnit",
    "RUN_GLOSSARY_SECTION_HEADER",
    "build_glossary_request",
    "build_distinction_request",
    "describe_source_language",
    "find_rendering_collisions",
    "domain_glossary_terms",
    "extract_glossary_candidates",
    "glossary_max_output_tokens",
    "glossary_terms_from_plan",
    "missing_required_candidates",
    "normalize_glossary_key",
    "normalize_rendering",
    "order_required_first",
    "parse_glossary_response",
    "request_candidates",
    "select_glossary_source_units",
]
