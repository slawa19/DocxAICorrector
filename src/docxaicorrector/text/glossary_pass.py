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
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import lru_cache

from docxaicorrector.core.constants import PROMPTS_DIR
from docxaicorrector.document.segments import GLOSSARY_TERM_KINDS, GlossaryTerm


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
# Spec 065 FR-002: a word heads the author's terms -- and is a candidate as one lowercase word --
# only when at least this many of its members are required. Measured on the four corpus books
# (2026-11-08): with one, *public* and *economics* (The Value of Everything) and *monetary* and
# *system* (Money) stood as required entries on a single marked member each; with two, *value*,
# *economy*, *economic* and *growth* stay.
_HEAD_MIN_REQUIRED_MEMBERS = 2
# Spec 065 FR-002: one lowercase word the author marked (defined, or set in italics or quotes
# where it first appears) is a candidate only when it occurs at least this often -- the same
# "recurring" as ``_REQUIRED_MIN_COUNT``. A word used once or twice cannot be rendered two ways
# across the book; "called him a loser" in a quotation is not a term.
_SINGLE_WORD_MIN_COUNT = 3
# Spec 065 FR-002, the split-word tail ("effi ciency", ``_split_word_tails``): a whole word opens
# a clause somewhere or follows one of the document's own this-many commonest words.
_COMMONEST_WORDS = 20
# Spec 065 FR-003: an expression built on a term of the glossary is its own candidate from this
# many occurrences on.
_PHRASE_MIN_COUNT = 3

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
# Spec 064 FR-009: the importer closes and reopens emphasis at every word it set as its own run
# ("called a *growth* *hierarchy*"); two marked runs with only a space between them are ONE
# marked expression. Bold first, so "**a** **b**" is not read as two italics.
_ADJACENT_BOLD_RE = re.compile(r"(?<=[^\s*])\*\*(\s+)\*\*(?=[^\s*])")
_ADJACENT_ITALIC_RE = re.compile(r"(?<=[^\s*])\*(\s+)\*(?=[^\s*])")
# Spec 067 FR-011 (b): "**" between a letter (or a word's hyphen) and a letter -- an italic run
# closed and reopened inside one word, as the importer writes "*wink-**nods*".
_EMPHASIS_INSIDE_WORD_RE = re.compile(r"(?<=[^\W\d_]|-)\*\*(?=[^\W\d_])")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+|\S*[A-Za-z0-9]\.[A-Za-z]{2,}/\S*")
_ROMAN_NUMERAL_RE = re.compile(r"^[IVXLCDM]+$")
_DIGIT_AFTER_RE = re.compile(r"[ \t ]*\d")
_POSSESSIVE_RE = re.compile(r"[’']s$")
_SENTENCE_BREAKS = frozenset(".!?:;\"“”‘(—–[•")
_CLAUSE_SPLIT_RE = re.compile(r"[.!?:;,()\[\]—–\"“”‘’•]")
_LEADING_ARTICLE_RE = re.compile(r"^\s*(?:a|an|the)\s+", re.IGNORECASE)
_LEADING_MARKED_SPAN_RE = (
    re.compile(r"\s*\*([^*]{1,80}?)\*"),
    re.compile(r"\s*[“\"‘]([^”\"’]{1,60})[”\"’]"),
)
# Spec 064 FR-009: "call X 'Y'" -- one unmarked word (the object of the verb: "itself",
# "landlords") and then the marked name the author gives it. The marking says which is the term.
# Spec 065 FR-002: an article may stand between them ("called them the 'tidal class'"); it
# used to end the unmarked fallback, and "them the" became a required entry. ``_WORD`` is an
# alternation and must be grouped: ungrouped, its first branch matched any word with no
# lookahead at all.
_OBJECT_THEN_MARKED_SPAN_RE = re.compile(
    r"\s*(?:" + _WORD + r")(?:\s+(?:a|an|the))?(?=\s+[*“\"‘])", re.IGNORECASE
)
_OPENING_QUOTES = frozenset("“\"‘")
_CONTINUING_WORD_RE = re.compile(r"\s*\*?" + _LETTER)
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
    # Spec 064 FR-009: the full form of the name this short form belongs to ("Zorvane Pettish"
    # for "Pettish"), decided by form in ``extract_glossary_candidates``; empty otherwise.
    name_head: str = ""
    # Spec 067 FR-010: the other surfaces of this candidate -- the same words in another order
    # or with a hyphen ("added yield", "yield-added" for "yield added"). They are not asked for
    # on their own; the rendering of ``source_term`` covers them.
    spellings: tuple[str, ...] = ()
    # Spec 067 FR-009: the candidates the book sets against this one -- the same last word,
    # other words before it, side by side in the same paragraphs (``_contrast_partners``).
    contrasts: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
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
        if self.name_head:
            payload["name_head"] = self.name_head
        if self.spellings:
            payload["spellings"] = list(self.spellings)
        if self.contrasts:
            payload["contrasts"] = list(self.contrasts)
        return payload


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
    in_h1: bool = False
    marked_count: int = 0
    heads_required_member: bool = False
    # Spec 065 FR-003: an expression built on a required word inherits its requiredness.
    phrase_of_required: bool = False
    # The document writes this one-word term capitalised more often than lowercase (the same
    # case test the name family uses); spec 064 FR-009 rule "capital letter".
    capitalised_form: bool = False


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


def _join_adjacent_emphasis(text: str) -> str:
    joined = _ADJACENT_ITALIC_RE.sub(r"\1", _ADJACENT_BOLD_RE.sub(r"\1", text))
    # Spec 067 FR-011 (b): emphasis closed and reopened INSIDE one word ("called *wink-**nods*")
    # cut the defined word in two, and "wink" became a required entry; the word is one.
    return _EMPHASIS_INSIDE_WORD_RE.sub("", joined)


# --- extraction ------------------------------------------------------------------------------


def _capitalised_runs(plain: str, numbered: list[bool] | None = None) -> list[list[str]]:
    """Runs of capitalised words; a run that opens a sentence is marked with a leading ``None``.

    Short lowercase joiners (``of``, ``for``) are kept inside a run when a capitalised word
    follows them, so an institution's name stays one candidate. ``numbered``, when given,
    receives one flag per returned run: the run is directly followed by a digit ("Chapter 13",
    "Figure 2" -- spec 067 FR-011).
    """

    matches = list(_TOKEN_RE.finditer(plain))
    tokens = [match.group(0) for match in matches]
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
        before = len(runs)
        if not sentence_start:
            if len(run) <= _MAX_TERM_WORDS:
                runs.append(run)
        elif len(run) >= 2 and run[1][:1].isupper():
            if len(run) - 1 <= _MAX_TERM_WORDS:
                runs.append(run[1:])
            if len(run) <= _MAX_TERM_WORDS:
                runs.append([""] + run)  # the whole run, admitted later only by its first word
        if numbered is not None:
            followed_by_digit = bool(_DIGIT_AFTER_RE.match(plain, matches[cursor - 1].end()))
            numbered.extend([followed_by_digit] * (len(runs) - before))
        index = cursor
        sentence_start = False
    return runs


def _defined_term_words(tail: str) -> list[str]:
    tail = _LEADING_ARTICLE_RE.sub(" ", tail)
    for pattern in _LEADING_MARKED_SPAN_RE:
        match = pattern.match(tail)
        if match:
            return _WORD_RE.findall(match.group(1))
    object_word = _OBJECT_THEN_MARKED_SPAN_RE.match(tail)
    if object_word:
        rest = tail[object_word.end() :]
        for pattern in _LEADING_MARKED_SPAN_RE:
            match = pattern.match(rest)
            # The marked span must END the phrase: in "called it 'real' money" the quotes
            # mark a word inside an expression, not a name given to the object.
            if match and not _CONTINUING_WORD_RE.match(rest[match.end() :]):
                return _WORD_RE.findall(match.group(1))
    words: list[str] = []
    for match in _TOKEN_RE.finditer(_EMPHASIS_MARKS_RE.sub("", tail)):
        token = match.group(0)
        if token in _OPENING_QUOTES:
            # Spec 065 FR-002: the definition goes on to a quoted name ("called them the 'tallow
            # class' and ..."); the unmarked words before it are the verb's object, not a term.
            return []
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
    marked_sources = [_join_adjacent_emphasis(_URL_RE.sub(" ", unit.text)) for unit in units]
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
    # Spec 067 FR-011 (a): two capitals that say nothing about how the document writes a word.
    # A paragraph whose letters are ALL capitals (a part title, a heading set in capitals): every
    # word in it is a capital. A word directly before a number ("in Chapter 13", "see
    # Figure 2"): the capital of a numbered label is the label's convention -- Creating Wealth
    # writes "Chapter N" 15 times mid-sentence and "chapter" 14 times, and *chapter* became a
    # capitalised form, then a required h1 entry. Such runs still count as names for the name
    # test, but not as the case evidence ``_Draft.capitalised_form`` reads (``cased_capitalised``).
    set_in_capitals = {index for index in body_indexes if _set_in_capitals(plains[index])}
    cased_capitalised: Counter[tuple[str, ...]] = Counter()

    def admit(
        raw_words: Sequence[str], signal: str, unit_index: int, *, proper: bool, numbered_label: bool = False
    ) -> None:
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
            if unit_index not in set_in_capitals and not numbered_label:
                cased_capitalised[key] += 1
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

    commonest_words = {word for word, _ in word_counts.most_common(_COMMONEST_WORDS)}

    def admit_marked(words: Sequence[str], signal: str, unit_index: int) -> None:
        trimmed = _trim_joiners(words)
        if signal == "defined" and trimmed != list(words) and _defined_expression_is_whole(words, trimmed):
            trimmed = list(words)
        if not trimmed:
            return
        admit(trimmed, signal, unit_index, proper=False)

    def _defined_expression_is_whole(words: Sequence[str], trimmed: Sequence[str]) -> bool:
        """Spec 067 FR-011 (b): the defined expression keeps a short edge word it is written with.

        "known as ebb and flow" lost "ebb" (three letters) and then "and" to ``_trim_joiners``,
        and the candidate became the one word "flow". By form, a definition's untrimmed
        expression of several words is the term when the document writes it whole at least
        ``_SINGLE_WORD_MIN_COUNT`` times AND the outermost word the trim took at each trimmed
        edge is not one of the document's ``_COMMONEST_WORDS`` commonest words (counted, not
        listed: "the", "as", "of" are; "ebb" is not -- the "and" after it went only because
        "ebb" had gone). "called him a lostling" -- written once -- is trimmed as before.
        """

        if len(words) < 2 or not trimmed:
            return False
        key = tuple(_fold_word(word).lower() for word in words)
        if len(hits_folded_case.get(key, ())) < _SINGLE_WORD_MIN_COUNT:
            return False
        trimmed_start = list(words[: len(trimmed)]) != list(trimmed)
        trimmed_end = list(words[-len(trimmed) :]) != list(trimmed)
        edges = [words[0]] * trimmed_start + [words[-1]] * trimmed_end
        return not any(word.lower() in commonest_words for word in edges)

    for unit_index in body_indexes:
        plain = plains[unit_index]
        source = marked_sources[unit_index]
        numbered: list[bool] = []
        for run, followed_by_digit in zip(_capitalised_runs(plain, numbered), numbered):
            if run[0] == "":
                run = run[1:]
                first = run[0]
                first_is_name = raw_case_counts[first] > raw_case_counts[first.lower()]
                if not (first.isupper() and len(first) >= 2) and not first_is_name:
                    continue
            admit(run, "capitalised", unit_index, proper=True, numbered_label=followed_by_digit and len(run) == 1)
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
                # Lowercased before the edge test: a heading in capitals ("STRATEGIES FOR
                # BUSINESS") must lose its short joiners exactly like a heading in title case.
                lowered = [word.lower() for word in phrase]
                if len(lowered[0]) <= _MAX_JOINER_LETTERS or len(lowered[-1]) <= _MAX_JOINER_LETTERS:
                    continue  # "monetary and", "for business": a joiner at either edge
                if any(len(word) <= 4 and word.isupper() and _ROMAN_NUMERAL_RE.match(word) for word in phrase):
                    continue  # "Chapter VII": a chapter number, not a subject
                key = tuple(_fold_word(word).lower() for word in phrase)
                body_hits = [hit for hit in hits_folded_case.get(key, []) if hit in body_index_set]
                if len(body_hits) < _HEADING_MIN_BODY_COUNT:
                    continue
                draft = drafts.get(key)
                if draft is None:
                    draft = drafts[key] = _Draft(
                        key=key, surface=" ".join(_POSSESSIVE_RE.sub("", word.lower()) for word in phrase), proper=False
                    )
                draft.signals.add("heading")
                # A level-1 heading (chapter, title) weighs twice a level-2 one; the phrase's
                # weight is what ranks it among heading candidates, ahead of its body frequency.
                draft.heading_weight += 2 if unit.heading_level == 1 else 1
                if unit.heading_level == 1:
                    draft.in_h1 = True
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
    capitalised_by_lower: Counter[str] = Counter()
    for capitalised_key, capitalised_times in cased_capitalised.items():
        if len(capitalised_key) == 1:
            capitalised_by_lower[capitalised_key[0].lower()] += capitalised_times
    for key, draft in drafts.items():
        hits = hits_exact.get(key, []) if draft.proper else hits_folded_case.get(key, [])
        units_hit = set(hits)
        # A definition is the author naming a concept, required however rare (see
        # ``_included_by_rule``); the frequency cuts below are for everything else. Before this
        # (Codex acceptance finding 4) a term defined in ONE unit was dropped here, before the
        # rule ever saw it.
        defined = bool(defined_units.get(key))
        if not units_hit or (len(units_hit) < 2 and not defined):
            continue
        idf = math.log(unit_count / len(units_hit))
        if idf <= 0 and not defined:
            continue
        idf = max(idf, 0.0)
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
        if len(key) == 1:
            # The name family's own case test, on the body: capitalised in mid-sentence at least
            # as often as lowercase. Headings are left out -- title case is not the word's case.
            # Spec 065 (Codex acceptance review, P1): EVERY capitalised spelling counts, not only
            # "Word" and "WORD" -- the CamelCase name "InspirePay" counted as never capitalised --
            # and a TIE is a capitalised form: a word the document capitalises mid-sentence as
            # often as it writes it lowercase is not "a word the document writes in lowercase"
            # ("Regeltante", 1 : 1, was dropped as one by the FR-002 count rule). A spelling
            # with a capital after its first letter is a name's form on its own.
            lower = key[0].lower()
            capitalised_count = capitalised_by_lower[lower] if lower != lower.upper() else 0
            lowercase_count = sum(1 for unit in hits_exact.get((lower,), []) if unit in body_index_set)
            draft.capitalised_form = _has_inner_capital(draft.surface) or (
                capitalised_count > 0 and capitalised_count >= lowercase_count
            )
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
    required_members: Counter[str] = Counter()
    for family in (FAMILY_MARKED, FAMILY_NAME, FAMILY_HEADING, FAMILY_COLLOCATION):
        for draft in ranked(family)[: quotas[family]]:
            if len(draft.key) >= 2:
                # Only a word at the EDGE of a member counts: "value" in "value creation" and
                # "surplus value" heads a family; a word inside an expression does not.
                for word in {draft.key[0].lower(), draft.key[-1].lower()}:
                    if len(word) >= _MIN_COLLOCATION_EDGE_LETTERS:
                        membership[word] += 1
                        if _included_by_rule(draft):
                            required_members[word] += 1
    required_membership = {word for word, count in required_members.items() if count >= _HEAD_MIN_REQUIRED_MEMBERS}
    for word, members in membership.items():
        if members < _HEAD_MIN_MEMBERSHIP:
            continue
        key = (word,)
        existing = drafts.get(key)
        if existing is not None and existing.family:
            # Spec 064 FR-009: a word another route already found (an h2 heading word, a
            # one-word marked term) still heads its family. Before, finding it elsewhere
            # skipped the head rule, and The Value of Everything's head word of three required
            # phrases (spec 064 FR-009) stayed optional.
            if word in required_membership and existing.family != FAMILY_HEAD:
                existing.signals.add("family_head")
                existing.heads_required_member = True
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

    # A DEFINED term is never cut for room — not by its family's quota, not by ``limit``
    # (Codex acceptance finding 4): the definition is the one mark the rule calls required
    # "however rare", and a rare term ranks low. Other required candidates (marked and
    # recurring, h1 phrases, heads) still compete inside their family's quota -- a narrowing
    # recorded in the spec with its counts, because lifting it doubles the required set.
    split_tails = _split_word_tails([plains[index] for index in body_indexes])
    selected: list[_Draft] = []
    seen_keys: set[tuple[str, ...]] = set()
    for family in _FAMILY_ORDER:
        # Spec 065 FR-002: a one-word lowercase draft that fails the form rule takes no place
        # in its family's quota; the room goes to the next candidate.
        admitted = [draft for draft in ranked(family) if _single_word_admitted(draft, split_tails=split_tails)]
        for rank, draft in enumerate(admitted):
            if rank >= quotas[family] and not _is_defined(draft):
                continue
            identity = tuple(word.lower() for word in draft.key)
            if identity in seen_keys:
                continue
            seen_keys.add(identity)
            selected.append(draft)
    # Spec 065 FR-002: a word of a heading alone stays an OPTIONAL candidate (rule 3 of
    # ``_single_word_admitted``) -- the ones its family quota admitted before spec 065 -- but
    # outside the quota and ``limit``: measured on the four books (2026-11-08), letting them
    # back into the quota pushed out required h1 phrases ("money and sustainability") and,
    # through ``limit``, optional terms ("monetary system", "financial system").
    heading_words = [
        draft
        for draft in ranked(FAMILY_HEADING)[: quotas[FAMILY_HEADING]]
        if _heading_word_only(draft) and draft.key[0] not in split_tails
    ]
    # ``limit`` then cuts optional candidates only: a defined term riding over its quota must
    # not push out a required family head that its quota admitted (measured: it did, five
    # heads on CW / RM / VoE, while the bypass covered only defined terms here).
    optional_room = max(0, limit - sum(1 for draft in selected if _included_by_rule(draft)))
    kept: list[_Draft] = []
    for draft in selected:
        if _included_by_rule(draft):
            kept.append(draft)
        elif optional_room > 0:
            optional_room -= 1
            kept.append(draft)
    for draft in heading_words:
        if draft.key not in seen_keys:
            seen_keys.add(draft.key)
            kept.append(draft)

    # Spec 065 FR-003: an expression built on a term the glossary keeps -- a word the author
    # marked, or a required word (the ANCHOR) -- is a candidate of its own, placed right before
    # that word: "public value" and "value-based" have senses of their own, and the word's
    # rendering must not leak into them. It contains the anchor as a word or as a part of a
    # hyphenated word, occurs at least ``_PHRASE_MIN_COUNT`` times in two units, and is one of
    # what the document itself sets apart:
    #   - an expression the author marked or put in a heading (the marked and heading drafts
    #     the family quota cut: "rent extraction", "value-based pricing"), unless one of its
    #     other words is GLUE -- the edge of ``_HEAD_MIN_MEMBERSHIP`` or more candidates none of
    #     which is required (a span the author quoted can start at "from");
    #   - a hyphenated word ("value-based", "non-market");
    #   - a recurring lowercase collocation of TWO words whose other word is the edge of a
    #     REQUIRED candidate -- a word of the book's own vocabulary of terms ("public" of
    #     "public goods"), not a word that stands next to everything. Measured on The Value of
    #     Everything (2026-11-08): neither the Dunning score ("about value" 77.6, "public
    #     value" 34.4) nor the word's frequency rank ("public" 42nd) separates them; this test
    #     keeps "public value" and drops "that value", "about value", "value from". Three-word
    #     collocations here were coordinations of two terms ("productive and unproductive",
    #     "income and wealth"), rendered by their parts.
    # Neither the family quota nor ``limit`` cuts them: the room was the defect (spec 065 G-1,
    # G-3); an expression already a candidate just gets the "phrase" signal. An
    # expression of a REQUIRED anchor is required too, so the longer entry reaches the prompt
    # section ahead of the word it contains.
    kept_by_key = {tuple(word.lower() for word in draft.key): draft for draft in kept if not draft.proper}
    kept_identities = {tuple(word.lower() for word in draft.key) for draft in kept}
    anchors = [
        draft
        for draft in kept
        if _is_single_lowercase_word(draft) and (draft.family == FAMILY_MARKED or _included_by_rule(draft))
    ]
    phrases_before: dict[int, list[_Draft]] = defaultdict(list)
    if anchors:
        by_score = sorted(drafts.items(), key=lambda item: (-item[1].score, item[0]))
        authored = [
            key
            for key, draft in by_score
            if draft.family in (FAMILY_MARKED, FAMILY_HEADING) and not draft.proper and (len(key) > 1 or "-" in "".join(key))
        ]
        compounds = sorted((word,) for word, count in word_counts.items() if "-" in word and count >= _PHRASE_MIN_COUNT)
        collocations = sorted(collocation_scores, key=lambda gram: (-collocation_scores[gram], gram))

        def holds(key: tuple[str, ...], anchor_word: str) -> bool:
            return any(anchor_word == part or anchor_word in part.split("-") for part in key)

        def partners(key: tuple[str, ...], anchor_word: str) -> list[str]:
            return [word for word in key if word != anchor_word and len(word) > _MAX_JOINER_LETTERS]

        def of_terms(gram: tuple[str, ...], anchor_word: str) -> bool:
            # At least one partner: a folded "this" ("thi") is as short as a joiner.
            others = partners(gram, anchor_word)
            return bool(others) and all(required_members[word] >= 1 for word in others)

        def glue(word: str) -> bool:
            return membership[word] >= _HEAD_MIN_MEMBERSHIP and required_members[word] == 0

        for anchor in anchors:
            anchor_word = anchor.key[0].lower()
            pool = [
                *(key for key in authored if holds(key, anchor_word) and not any(glue(word) for word in partners(key, anchor_word))),
                *(key for key in compounds if holds(key, anchor_word)),
                *(gram for gram in collocations if len(gram) == 2 and anchor_word in gram and of_terms(gram, anchor_word)),
            ]
            for key in pool:
                if key in kept_identities:
                    # Already a candidate on its own (a collocation within its quota, a marked
                    # expression): it is still an expression of this anchor.
                    present = kept_by_key.get(key)
                    if present is not None and present is not anchor:
                        present.signals.add("phrase")
                        present.phrase_of_required = present.phrase_of_required or _included_by_rule(anchor)
                    continue
                hits = hits_folded_case.get(key, [])
                units_hit = set(hits)
                if len(hits) < _PHRASE_MIN_COUNT or len(units_hit) < 2:
                    continue
                phrase = drafts.setdefault(key, _Draft(key=key, surface=" ".join(key), proper=False))
                if not phrase.family:
                    phrase.family = FAMILY_COLLOCATION
                    phrase.count = len(hits)
                    phrase.units = units_hit
                    phrase.chapters = len({chapter_of[unit] for unit in units_hit})
                    phrase.score = collocation_scores.get(key, 0.0)
                phrase.signals.add("phrase")
                phrase.phrase_of_required = _included_by_rule(anchor)
                kept_identities.add(key)
                kept_by_key[key] = phrase
                phrases_before[id(anchor)].append(phrase)
    if phrases_before:
        kept = [phrase for draft in kept for phrase in (*phrases_before.get(id(draft), ()), draft)]

    body_lowercase_words = Counter(
        word for unit_index in body_indexes for word in _WORD_RE.findall(plains[unit_index]) if word.islower()
    )
    name_heads = _name_family_heads(kept, lowercase_words=body_lowercase_words)
    written_forms: dict[str, Counter[str]] = defaultdict(Counter)
    for unit_index in body_indexes:
        for word in _WORD_RE.findall(plains[unit_index]):
            written_forms[_fold_word(word.lower())][word.lower()] += 1
    def surface_of(draft: _Draft) -> str:
        return draft.surface if draft.proper else _written_surface(draft.surface, written_forms)

    candidates: list[GlossaryCandidate] = []
    candidate_units: list[set[int]] = []
    name_family_ids = {id(member) for member in name_heads} | {id(head) for head in name_heads.values()}

    def written_as_name(draft: _Draft) -> bool:
        if id(draft) in name_family_ids:
            return True
        if len(draft.key) == 1:
            return draft.capitalised_form
        words = draft.surface.split()
        if _has_inner_capital(draft.surface):
            return True
        capital_key = tuple(_fold_word(word[:1].upper() + word[1:]) for word in words)
        lower_key = tuple(_fold_word(word.lower()) for word in words)
        capitalised = capitalised_noninitial.get(capital_key, 0)
        return capitalised > 0 and capitalised >= len(hits_exact.get(lower_key, ()))

    for group in _permutation_groups(kept, written_as_name=written_as_name):
        # Spec 067 FR-010: one candidate per group, named by its most used surface (the first
        # on a tie); the others are its spellings. The group's uses and units add up, and it
        # is required when any of its surfaces is.
        draft = max(enumerate(group), key=lambda item: (item[1].count, -item[0]))[1]
        group_units = set().union(*(member.units for member in group))
        first_unit = min(group_units)
        if draft.family == FAMILY_MARKED and draft.signal_unit is not None:
            context_unit = draft.signal_unit
        elif draft.family == FAMILY_HEADING and draft.heading_unit is not None:
            context_unit = draft.heading_unit
        else:
            context_unit = min(draft.units)
        candidates.append(
            GlossaryCandidate(
                source_term=surface_of(draft),
                key=draft.key,
                family=draft.family,
                signals=tuple(sorted(set().union(*(member.signals for member in group)))),
                occurrence_count=sum(member.count for member in group),
                unit_count=len(group_units),
                spread=len({bin_of(unit) for unit in group_units}),
                first_unit_id=units[first_unit].unit_id,
                context=_context_snippet(plains[context_unit], draft.surface),
                score=round(draft.score, 4),
                required=any(_included_by_rule(member) for member in group),
                name_head=name_heads[id(draft)].surface if id(draft) in name_heads else "",
                spellings=tuple(surface_of(member) for member in group if member is not draft),
            )
        )
        candidate_units.append(group_units)
    contrasted = _contrast_partners(candidates, candidate_units)
    return tuple(
        replace(candidate, contrasts=contrasted[index]) if index in contrasted else candidate
        for index, candidate in enumerate(candidates)
    )


# Spec 067 FR-009: two candidates the author sets against each other stand side by side in at
# least this many paragraphs. Measured on the fourth run's books (2026-11-08): the contrasted
# pair of Rethinking Money (spec 067 G-2) shares 5 paragraphs. Over the
# glossary entries of the four books (a survey of all paragraphs, before the joiner and
# narrowing exclusions) pairs sharing >= 1 paragraph number 22 / 31 / 9 / 18 (Money / CW / RM /
# VoE) and >= 2 -- 13 / 15 / 5 / 6: one shared paragraph is mostly a passing mention, and the
# mark costs prompt characters on every block call.
_CONTRAST_MIN_SHARED_UNITS = 2


def _contrast_partners(
    candidates: Sequence[GlossaryCandidate],
    units_of: Sequence[set[int]],
) -> dict[int, tuple[str, ...]]:
    """Candidates the book contrasts with each candidate, by form (spec 067 FR-009, G-2).

    Rethinking Money fixed a rendering for one entry of a contrasted pair (spec 067 G-2), and in
    12 of 93 paragraphs about the other entry the translation then used that rendering -- the
    rendering of one entry leaked into its neighbour. Two candidates
    are a contrasted pair when, by form:
      - each has at least two words and no joiner inside (a word of up to
        ``_MAX_JOINER_LETTERS`` letters between the first and the last: in "theory of quills"
        the last word is not the head);
      - they share the LAST word and differ before it, and neither ends with the other
        ("tallow quills" in "red tallow quills" is the same thing narrowed, which
        spec 065 FR-003 already orders);
      - they stand together in at least ``_CONTRAST_MIN_SHARED_UNITS`` paragraphs.
    No list of words: the head word, the paragraphs and the counts are the document's own.
    Partners come most shared paragraphs first, then by use.
    """

    shapes: dict[int, tuple[str, ...]] = {}
    for index, candidate in enumerate(candidates):
        words = tuple(word.lower() for word in candidate.key)
        if len(words) < 2 or any(len(word) <= _MAX_JOINER_LETTERS for word in words[1:-1]):
            continue
        shapes[index] = words
    by_last: dict[str, list[int]] = defaultdict(list)
    for index, words in shapes.items():
        by_last[words[-1]].append(index)
    found: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
    for members in by_last.values():
        for position, first in enumerate(members):
            for second in members[position + 1 :]:
                a, b = shapes[first], shapes[second]
                shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
                if longer[-len(shorter) :] == shorter:
                    continue
                shared = len(units_of[first] & units_of[second])
                if shared < _CONTRAST_MIN_SHARED_UNITS:
                    continue
                found[first].append((shared, candidates[second].occurrence_count, candidates[second].source_term))
                found[second].append((shared, candidates[first].occurrence_count, candidates[first].source_term))
    return {
        index: tuple(term for _, _, term in sorted(pairs, key=lambda item: (-item[0], -item[1], item[2])))
        for index, pairs in found.items()
    }


def _permutation_key(key: Sequence[str]) -> tuple[str, ...] | None:
    """The words of ``key`` in sorted order, hyphens split; ``None`` for a single plain word.

    Spec 067 FR-010: "yield added", "added yield" and "yield-added" all give ``("added",
    "yield")``.
    """

    parts = sorted(part for word in key for part in word.lower().split("-") if part)
    return tuple(parts) if len(parts) >= 2 else None


def _permutation_groups(
    drafts: Sequence[_Draft],
    *,
    written_as_name: Callable[[_Draft], bool] = lambda draft: False,
) -> list[list[_Draft]]:
    """The drafts in order, those with one multiset of words collapsed into one group.

    Spec 067 FR-010 (G-3): The Value of Everything had one term as three entries -- its words,
    the same words in the other order, and the hyphenated form (34 of 34 of the first rendered
    as fixed) -- and the model gave the last two renderings it then never used (0 of 9) --
    three entries for one term, two of them wrong.
    Candidates whose words form the same multiset once hyphens are split (``_permutation_key``)
    are one term -- but only when, by form (Codex acceptance review of spec 067, P0):
      - at most ONE of them is the author's own (marked or defined: the marked family); the
        others are unmarked collocations or phrases of it. Two expressions the author marked
        or defined each ("house boat" and "boat house") are two concepts and stay two
        candidates; an identical rendering of the two is call C's collision (spec 064 FR-009);
      - none of them is written as a name: a capitalised form by the document's own case
        count (``_Draft.capitalised_form``; for several words, the capitalised expression
        mid-sentence at least as often as the lowercase one), a mixed-case spelling, or a
        member or head of a name family. "North Harbour" and "Harbour North" are two places.
    A name keeps its own case-sensitive identity and is never grouped here: its spellings are
    the name family's business (spec 064 FR-009). A group that fails the form falls apart into
    its members, each where it stood; a group that holds stands where its first member stood,
    so a phrase still comes before the word it contains.
    """

    by_permutation: dict[tuple[str, ...], list[_Draft]] = defaultdict(list)
    for draft in drafts:
        permutation = None if draft.proper else _permutation_key(draft.key)
        if permutation is not None:
            by_permutation[permutation].append(draft)

    def holds(group: Sequence[_Draft]) -> bool:
        authored = sum(1 for member in group if member.family == FAMILY_MARKED)
        return authored <= 1 and not any(written_as_name(member) for member in group)

    group_of: dict[int, list[_Draft]] = {}
    for group in by_permutation.values():
        if len(group) >= 2 and holds(group):
            for member in group:
                group_of[id(member)] = group
    groups: list[list[_Draft]] = []
    for draft in drafts:
        group = group_of.get(id(draft))
        if group is None:
            groups.append([draft])
        elif group[0] is draft:
            groups.append(group)
    return groups


def _written_surface(surface: str, written_forms: Mapping[str, Counter[str]]) -> str:
    """``surface`` with every word the document never writes replaced by the word it does write.

    Spec 067 FR-008 (the clause about a word with its final ``s`` cut off). A collocation, a
    phrase and a family head are keyed by FOLDED words (``_fold_word``: the plural ``s`` off),
    and their surface was built from the key -- "census" became "censu", "crisis" "crisi",
    "this" "thi". Measured on the fourth run's books: 11 candidates, one to four per book
    (spec 067 FR-008). The spec took one of them for a split-word tail; it is not one -- the
    word is written whole three times. A word of
    the surface that the body writes (in any case) stays; one it never writes becomes the
    commonest written word that folds to it. The key, and so every match, is unchanged.
    """

    words = surface.split(" ")
    for index, word in enumerate(words):
        forms = written_forms.get(word)
        if forms and word not in forms:
            words[index] = forms.most_common(1)[0][0]
    return " ".join(words)


def _name_words(draft: _Draft) -> list[str] | None:
    """The words of a candidate written as a personal or place name: 1-3 capitalised words.

    Not an abbreviation ("US GDP"), not a possessive ("Silicon Valley's"), no lowercase joiner
    ("Bank of England", "Smith and Ricardo" -- an institution or two people, not one name).
    """

    if draft.family not in (FAMILY_NAME, FAMILY_MARKED):
        return None
    words = draft.surface.split()
    if not 1 <= len(words) <= 3:
        return None
    for word in words:
        if not _WORD_RE.fullmatch(word) or not word[:1].isupper() or _POSSESSIVE_RE.search(word):
            return None
        if len(word) > 1 and word.isupper():
            return None
    return words


def _name_family_heads(drafts: Sequence[_Draft], *, lowercase_words: Counter[str]) -> dict[int, _Draft]:
    """Short forms of a name and the full form each belongs to (spec 064 FR-009, R-9).

    Money rendered a co-author's surname as one transliteration while Creating Wealth rendered
    his full name as another: a surname asked for on its own is transliterated on its own. By
    form, a name candidate whose words END a longer name candidate ("Pettish" in "Zorvane
    Pettish", "Marlow Keswick" in "Tobias Marlow Keswick") is a member of its family; the
    longest form is the head. The words the head adds must be names themselves -- the body
    never writes them in lowercase: "Central Kelbrook", "Great Thaw", "New Marrow" add ordinary
    words ("central", "great", "new") and are other entities, not a fuller form of "Kelbrook".
    A short form that ends two different longer names ("Wren" in "Tobias Wren" and "Ansel
    Wren"; "Marrow" in "North Marrow" and "South Marrow", whichever of them qualifies) is
    ambiguous; it, and a REQUIRED short form, stay candidates of their own.
    """

    named = []
    for draft in drafts:
        words = _name_words(draft)
        if words:
            named.append((draft, [word.casefold() for word in words]))
    heads_of: dict[int, _Draft] = {}
    for draft, words in named:
        if _included_by_rule(draft):
            continue
        size = len(words)
        longer = [(other, other_words) for other, other_words in named if len(other_words) > size and other_words[-size:] == words]
        heads = [
            (other, other_words)
            for other, other_words in longer
            if all(lowercase_words[word] == 0 for word in other_words[:-size])
        ]
        if not heads:
            continue
        head, head_words = max(heads, key=lambda item: (len(item[1]), item[0].count))
        if any(head_words[-len(other_words) :] != other_words for _, other_words in longer):
            continue
        heads_of[id(draft)] = head
    return heads_of


def _is_defined(draft: _Draft) -> bool:
    """The author defined this term in the text ("we call this …", "known as …")."""

    return draft.family == FAMILY_MARKED and "defined" in draft.signals


def _included_by_rule(draft: _Draft) -> bool:
    """Which candidates the author put in the glossary, by form (spec 063 P2 inclusion rule).

    MARKED AND RECURRING. A definition is the author's own act of naming a concept and is
    required however rare. Italics or bold at first use (and quotes around an expression) are
    required only when the term then RECURS — at least ``_REQUIRED_MIN_COUNT`` occurrences in at
    least ``_REQUIRED_MIN_CHAPTERS`` chapters — AND the marking itself is not a one-off stress:
    the author marks it at least twice, or marks it where it first appears in the text. A word
    stressed once in passing is not promoted to a term (it may stay an optional candidate). A
    phrase of the title or an h1 heading that the body keeps using is required. A family head stands for at least three
    candidates (``_HEAD_MIN_MEMBERSHIP``) and is required when at least one member is. Quotes
    around ONE word are left to the model.
    """

    if draft.phrase_of_required:
        # Spec 065 FR-003: an expression built on a required word ("public value" on *value*).
        return True
    if draft.in_h1 and not _is_single_lowercase_word(draft):
        # Fourth pass (orchestrator decision): a phrase of the book's title or of a chapter
        # (h1) heading that the body uses at least ``_HEADING_MIN_BODY_COUNT`` times — the
        # condition under which it became a candidate at all — is the strongest mark an author
        # makes. h2 phrases stay optional. Spec 065 FR-002: ONE lowercase word of a heading
        # ("making", "today", "versus") is not such a mark -- titles are written in ordinary
        # words.
        return True
    if draft.heads_required_member:
        # A head is required when it heads a family (>= 3 members) one of whose members the
        # author marked; a head of grammatical collocations ("have been", "they have") is not.
        # Spec 064: this holds for a word another route found first, too.
        return True
    if draft.family != FAMILY_MARKED:
        return False
    if _is_defined(draft):
        return True
    if _is_lowercase_single_marked(draft):
        # Spec 064 FR-009: one lowercase word under italics is how an author STRESSES a
        # word as often as how they introduce a term ("after", "taxes"); alone it does not
        # make a term. It stays an optional candidate, ranked by use x marking.
        return False
    marked = "emphasis" in draft.signals or ("quoted" in draft.signals and len(draft.key) > 1)
    recurring = draft.count >= _REQUIRED_MIN_COUNT and draft.chapters >= _REQUIRED_MIN_CHAPTERS
    # An ordinary word recurs anyway; what recurs for a TERM is the author's marking of it.
    # Marked once, the expression must be marked where it first appears in the whole text.
    marking_recurs = draft.marked_count >= 2 or draft.signal_unit == min(draft.units, default=-1)
    return marked and recurring and marking_recurs


def _is_lowercase_single_marked(draft: _Draft) -> bool:
    """A marked candidate of ONE word that the document writes in lowercase, not defined.

    Spec 064 FR-009: "marked and recurring" makes a candidate required only when it also has
    a form of its own -- several words, a capital letter (by the document's own case counts:
    the capitalised form outnumbers the lowercase one), or a definition.
    """

    return (
        draft.family == FAMILY_MARKED
        and len(draft.key) == 1
        and not draft.capitalised_form
        and not _is_defined(draft)
    )


def _has_inner_capital(surface: str) -> bool:
    """A word of ``surface`` has an upper-case letter after its first one ("InspirePay", "eBay").

    Spec 065: such a spelling is a name's form whatever the document's case counts say.
    Spec 067 FR-011 (a): a word set entirely in capitals ("HARBOURAGE", taken from a line in
    capitals) is not such a spelling -- its case is the typesetting's, not the word's. The rule
    is for mixed case: some letter after the first is upper-case AND some letter is lower-case.
    """

    return any(
        any(char.isupper() for char in word[1:]) and any(char.islower() for char in word)
        for word in _WORD_RE.findall(surface)
    )


def _set_in_capitals(text: str) -> bool:
    """Every letter of ``text`` is upper-case (and it has at least two): a line set in capitals."""

    letters = [char for char in text if char.isalpha()]
    return len(letters) >= 2 and all(char.isupper() for char in letters)


def _is_single_lowercase_word(draft: _Draft) -> bool:
    """ONE word that the document writes in lowercase: no hyphen, no capital by its own counts.

    A hyphenated word ("value-based", "rent-seeking") is a compound -- an expression -- and a
    word the document capitalises mid-sentence more often than not is written as a name
    (``_Draft.capitalised_form``); neither is a single lowercase word.
    """

    return (
        len(draft.key) == 1
        and not draft.proper
        and not draft.capitalised_form
        and "-" not in draft.key[0]
        and draft.key[0].lower() == draft.key[0]
    )


def _single_word_admitted(draft: _Draft, *, split_tails: Collection[str]) -> bool:
    """Spec 065 FR-002: ONE lowercase word is a candidate only by one of these forms.

    1. PART OF THE AUTHOR'S TERMS: it heads a family (``_HEAD_MIN_MEMBERSHIP`` candidates
       sharing it at an edge) of which at least ``_HEAD_MIN_REQUIRED_MEMBERS`` are required --
       *yield* of "surplus yield", "yield added".
    2. MARKED AND RECURRING: the author defined it, or set it in italics or quotes where it
       first appears (the marked family), and it occurs at least ``_SINGLE_WORD_MIN_COUNT``
       times. A borrowing or a coined word ("demurrage") is introduced exactly this way.
    3. A WORD OF A HEADING the body keeps using (``_heading_word_only``) -- but only as an
       OPTIONAL candidate, added outside the family quota and ``limit`` by
       ``extract_glossary_candidates`` (this function says no to it, so it takes no room):
       ``_included_by_rule`` never makes it required ("making", "today", "versus" were
       required through an h1 and forced wrong renderings, spec 065 G-2), and
       ``order_glossary_entries`` puts it last, where the budget cuts first. Removing it
       would decide for the model; Money's *sustainability* (its title word, 114 uses) is the
       term its *resilience* is contrasted with (G-4).
    Nothing else: a head of unmarked collocations ("have" of "have been"), a word marked once
    or twice. A name is a capitalised form and a phrase is several words; neither is decided
    here. The tail of a word the extraction split ("effi ciency" -> ``ciency``;
    ``_split_word_tails``) is never a candidate.

    Measured on the four corpus books (2026-11-08) and recorded in spec 065: no form the
    document gives tells an everyday word the author marks once (20 and 45 occurrences) from
    a term the author defines (15) -- the share of marked occurrences, the chapter the
    word lives in, the first use and the derived word forms each lose a real term of another
    book -- so the everyday word stays a candidate; the model decides its rendering.
    """

    if not _is_single_lowercase_word(draft):
        return True
    if draft.key[0] in split_tails:
        return False
    if draft.heads_required_member:
        return True
    return draft.family == FAMILY_MARKED and draft.count >= _SINGLE_WORD_MIN_COUNT


def _heading_word_only(draft: _Draft) -> bool:
    """One lowercase word that is a candidate through a heading alone (spec 065 FR-002, rule 3)."""

    return draft.family == FAMILY_HEADING and _is_single_lowercase_word(draft) and not draft.heads_required_member


def _split_word_tails(plains: Sequence[str]) -> frozenset[str]:
    """Lowercase tokens that are the second half of a word the extraction split, by form.

    A WHOLE word opens a clause somewhere, or follows one of the document's own
    ``_COMMONEST_WORDS`` commonest words ("the", "of", "a" -- counted, not listed). A FRAGMENT
    ("effi", "suffi") never ends a clause, and every word that follows it is not whole
    ("ciency", "cient"). A TAIL is a word that is not whole, occurs at least
    ``_SINGLE_WORD_MIN_COUNT`` times, at least half of the time right after a fragment, and
    after at least two different fragments: a word ending that several split words share
    ("effi ciency", "suffi ciency"). The second word of a fixed pair ("fossil fuels") follows
    one word only and is not a tail. Spec 065 FR-002; no list of fragments or ligatures.
    """

    seen: Counter[str] = Counter()
    followers: dict[str, set[str]] = defaultdict(set)
    clause_ends: set[str] = set()
    clauses: list[list[str]] = []
    for plain in plains:
        for clause in _CLAUSE_SPLIT_RE.split(plain):
            words = [word.lower() for word in _WORD_RE.findall(clause)]
            if not words:
                continue
            clauses.append(words)
            clause_ends.add(words[-1])
            for index, word in enumerate(words):
                seen[word] += 1
                if index + 1 < len(words):
                    followers[word].add(words[index + 1])
    commonest = {word for word, _ in seen.most_common(_COMMONEST_WORDS)}
    whole: set[str] = set()
    for words in clauses:
        whole.add(words[0])
        whole.update(words[index] for index in range(1, len(words)) if words[index - 1] in commonest)
    fragments = {
        word
        for word, following in followers.items()
        if word not in clause_ends and following and not (following & whole)
    }
    after_fragment: Counter[str] = Counter()
    fragments_before: dict[str, set[str]] = defaultdict(set)
    for words in clauses:
        for index in range(1, len(words)):
            if words[index - 1] in fragments:
                after_fragment[words[index]] += 1
                fragments_before[words[index]].add(words[index - 1])
    return frozenset(
        word
        for word, count in after_fragment.items()
        if word.islower()
        and word not in whole
        and seen[word] >= _SINGLE_WORD_MIN_COUNT
        and 2 * count >= seen[word]
        and len(fragments_before[word]) >= 2
    )


def _context_snippet(plain: str, surface: str) -> str:
    flat = " ".join(plain.split())
    first_word = (_WORD_RE.findall(surface) or [""])[0]
    match = re.search(re.escape(first_word), flat, re.IGNORECASE) if first_word else None
    anchor = match.start() if match else 0
    start = max(0, anchor - GLOSSARY_CONTEXT_CHARS // 2)
    return flat[start : start + GLOSSARY_CONTEXT_CHARS]


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


# The completion budget of one glossary call (spec 064, 2026-11-08). The old flat 60 tokens per
# entry was a guess, and on Creating Wealth (third run) call A spent 4 436 of its 4 440 tokens on
# 74 entries and was cut off. Measured on the seven successful glossary stages of the two
# 2026-11-07 runs (19 calls, 1 018 answer entries; per-call usage was not recorded, so the
# stage totals were decomposed): one entry costs 26.7 tokens by least squares over the stages
# (30.7 with no per-call term), with a per-call overhead of 212; entry by entry, the answer JSON
# rebuilt from the artifact and converted at each stage's own tokens-per-character ratio gives
# p50 30.0, p95 38.7, max 47.3 tokens. The budget is the measured MAX doubled (the failed call
# shows a model can answer at ~60 tokens an entry) plus the overhead rounded up. A budget only
# caps: tokens are paid as generated, so the headroom costs nothing on a normal answer.
GLOSSARY_OUTPUT_TOKENS_PER_ENTRY = 96
GLOSSARY_OUTPUT_TOKENS_ENVELOPE = 256
GLOSSARY_OUTPUT_TOKENS_MIN = 1024
# The same ceiling every block call of the run already sends to this provider
# (``generation._generation._MODEL_OUTPUT_TOKEN_CEILING``); a list longer than it fits is the
# phase's to split (``pipeline/glossary_phase.py``, call A in halves), not the budget's.
GLOSSARY_OUTPUT_TOKENS_CEILING = 16384


def glossary_max_output_tokens(entry_count: int) -> int:
    """``max_output_tokens`` for a glossary answer of ``entry_count`` entries."""

    budget = GLOSSARY_OUTPUT_TOKENS_ENVELOPE + GLOSSARY_OUTPUT_TOKENS_PER_ENTRY * max(1, int(entry_count))
    return max(GLOSSARY_OUTPUT_TOKENS_MIN, min(GLOSSARY_OUTPUT_TOKENS_CEILING, budget))


def split_candidates_in_halves(
    candidates: Sequence[GlossaryCandidate],
) -> tuple[tuple[GlossaryCandidate, ...], tuple[GlossaryCandidate, ...]]:
    """The two halves call A is retried with after an unusable answer, in request order."""

    middle = (len(candidates) + 1) // 2
    return tuple(candidates[:middle]), tuple(candidates[middle:])


def build_glossary_request(
    *,
    model: str,
    candidates: Sequence[GlossaryCandidate],
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
        "candidates": [
            {
                "id": index + 1,
                "term": candidate.source_term,
                "family": candidate.family,
                "required": candidate.required,
                "signals": list(candidate.signals),
                "count": candidate.occurrence_count,
                "context": candidate.context,
                # Spec 067 FR-010: the same expression written otherwise; one rendering covers all.
                **({"spellings": list(candidate.spellings)} if candidate.spellings else {}),
                # Spec 067 FR-009: expressions the book sets against this one.
                **({"contrast_with": list(candidate.contrasts)} if candidate.contrasts else {}),
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


def _spelling_identity(source_term: str) -> str:
    """A source term with case, periods and a plural ``s`` taken off ("U.S." = "US", "TRCs" = "TRC").

    Only a LOWERCASE final ``s`` is a plural: in "BIS" the ``S`` is a letter of the name.
    """

    letters = re.sub(r"[.\s]", "", str(source_term or ""))
    if len(letters) > 2 and letters.endswith("s"):
        letters = letters[:-1]
    return letters.casefold()


def same_spelling_family(first: str, second: str) -> bool:
    """Two source terms that are one name written two ways (spec 064 FR-009), by form only.

    Equal once case, periods and a plural ``s`` are taken off ("US" / "U.S.", "TRC" / "TRCs").
    Such a pair sharing a rendering is not a collision: there is nothing to tell apart.

    Two DIFFERENT abbreviations are not one spelling, however alike: "GDP" / "GDPR" are two
    concepts, and "US" / "USA" is one pair, not a class of form (Codex review 2026-11-07,
    Constitution VII). Such a pair goes to call C, whose answer may say "the same thing
    written another way" (``find_rendering_collisions``'s ``declared_same``).
    """

    first_identity, second_identity = _spelling_identity(first), _spelling_identity(second)
    return bool(first_identity) and first_identity == second_identity


def _collision_rendering_key(term: GlossaryTerm) -> tuple[str, ...]:
    # A rendering that IS its source term (a name kept in its own script: "WIR", "Wired") is
    # compared whole. The stem rule cuts a short word to three letters, and two different
    # names kept as written then looked like one rendering (spec 064 R-9: RM "WIR" / "Wired").
    target = " ".join(str(term.target_term or "").split())
    if target and target.casefold() == " ".join(str(term.source_term or "").split()).casefold():
        return ("\0verbatim", target.casefold())
    return normalize_rendering(term.target_term)


def find_rendering_collisions(
    terms: Sequence[GlossaryTerm],
    *,
    declared_same: Collection[frozenset[tuple[str, ...]]] = (),
) -> list[list[GlossaryTerm]]:
    """Groups of entries whose DIFFERENT source terms share one rendering (decision 3).

    Two source terms of one spelling family (``same_spelling_family``) are one term here: a
    group whose members all belong to one such family is not a collision. So are two source
    terms ``declared_same`` -- pairs of keys call C answered as one thing written two ways
    (the kept rendering returned for the other member, with a note saying why).
    """

    def same(first: GlossaryTerm, second: GlossaryTerm) -> bool:
        if same_spelling_family(first.source_term, second.source_term):
            return True
        pair = frozenset((normalize_glossary_key(first.source_term), normalize_glossary_key(second.source_term)))
        return pair in declared_same


    by_rendering: dict[tuple[str, ...], dict[tuple[str, ...], GlossaryTerm]] = defaultdict(dict)
    for term in terms:
        rendering = _collision_rendering_key(term)
        if not rendering:
            continue
        by_rendering[rendering].setdefault(normalize_glossary_key(term.source_term), term)
    collisions: list[list[GlossaryTerm]] = []
    for group in by_rendering.values():
        members = list(group.values())
        families: list[list[GlossaryTerm]] = []
        for member in members:
            family = next(
                (
                    known
                    for known in families
                    if any(same(member, other) for other in known)
                ),
                None,
            )
            if family is None:
                families.append([member])
            else:
                family.append(member)
        if len(families) >= 2:
            collisions.append(members)
    return collisions


def order_collision_group(
    group: Sequence[GlossaryTerm],
    counts: Mapping[tuple[str, ...], int],
) -> list[GlossaryTerm]:
    """The group with the source term the book uses MOST first: it keeps the rendering.

    Spec 064 FR-009 (R-9): call C renamed Money's *sustainability* (129 of 144 delivered pairs
    say «устойчив-») to «жизнеспособность» and left the rare *resilience* «устойчивость». The
    rendering stays with the frequent term; the rarer ones are asked for a new one. Ties keep
    the glossary's order.
    """

    return sorted(group, key=lambda term: -int(counts.get(normalize_glossary_key(term.source_term), 0)))


def collision_keepers(group: Sequence[GlossaryTerm]) -> list[GlossaryTerm]:
    """The members of an ordered group that keep the rendering: the first and its spellings."""

    if not group:
        return []
    head = group[0]
    return [term for term in group if term is head or same_spelling_family(term.source_term, head.source_term)]


def declared_spellings(
    groups: Sequence[Sequence[GlossaryTerm]],
    answer: Sequence[GlossaryTerm],
) -> set[frozenset[tuple[str, ...]]]:
    """Pairs call C answered as ONE thing written two ways (Codex review 2026-11-07, finding 6).

    The distinction prompt says: an expression that really is the kept one written another way
    gets current_rendering too, with a note saying so. Such an answer is a resolution, not a
    failure to tell the terms apart: the pair (kept term, that member) is returned, and
    ``find_rendering_collisions(..., declared_same=...)`` no longer counts it. An answer that
    repeats the shared rendering WITHOUT a note says nothing and stays a collision.
    """

    answers: dict[tuple[str, ...], list[GlossaryTerm]] = defaultdict(list)
    for entry in answer:
        answers[normalize_glossary_key(entry.source_term)].append(entry)
    declared: set[frozenset[tuple[str, ...]]] = set()
    for group in groups:
        keepers = collision_keepers(group)
        if not keepers:
            continue
        kept = keepers[0]
        kept_key = normalize_glossary_key(kept.source_term)
        for participant in group:
            if any(participant is keeper for keeper in keepers):
                continue
            participant_key = normalize_glossary_key(participant.source_term)
            for entry in answers.get(participant_key, []):
                if entry.note and normalize_rendering(entry.target_term) == normalize_rendering(kept.target_term):
                    declared.add(frozenset((kept_key, participant_key)))
    return declared


def build_distinction_request(
    *,
    model: str,
    groups: Sequence[Sequence[GlossaryTerm]],
    contexts: Mapping[tuple[str, ...], str],
    source_language: str,
    target_language: str,
    sample_text: str = "",
    counts: Mapping[tuple[str, ...], int] | None = None,
) -> dict[str, object]:
    """Call C: one request for every collision group, with each term's context.

    ``groups`` come ordered by ``order_collision_group``: the first member (and its spellings)
    KEEPS ``current_rendering`` and is marked ``"keep": true``; every term carries how often the
    book uses it. The phase applies the answer to the other members only, whatever the model
    returns for the kept ones (``pipeline/glossary_phase._apply_distinction``).
    """

    source_label = describe_source_language(source_language, sample_text=sample_text)
    instructions = _load_glossary_instructions(GLOSSARY_ROLE_DISTINGUISH).format(
        source_language=source_label,
        target_language=str(target_language or ""),
        max_terms=0,
    )
    counts = counts or {}

    def group_payload(group: Sequence[GlossaryTerm]) -> dict[str, object]:
        keepers = collision_keepers(group)
        return {
            "current_rendering": group[0].target_term,
            "terms": [
                {
                    "term": term.source_term,
                    "count": int(counts.get(normalize_glossary_key(term.source_term), 0)),
                    "keep": any(term is keeper for keeper in keepers),
                    "context": contexts.get(normalize_glossary_key(term.source_term), ""),
                    # The sense this entry stands for, when the term has more than one
                    # (FR-013): without it the model cannot tell which of them collided.
                    **({"note": term.note} if term.note else {}),
                }
                for term in group
            ],
        }

    payload = {
        "source_language": source_label,
        "target_language": str(target_language or ""),
        "groups": [group_payload(group) for group in groups],
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


@dataclass(frozen=True)
class NameFamilyMember:
    """A short form of a name ("Pettish") and the full form it inherits from ("Zorvane Pettish")."""

    member: GlossaryCandidate
    head: GlossaryCandidate


def split_name_families(
    candidates: Sequence[GlossaryCandidate],
) -> tuple[tuple[GlossaryCandidate, ...], tuple[NameFamilyMember, ...]]:
    """Take the short forms of a name out of the request; they inherit the full form's rendering.

    Which short form belongs to which full form is decided at extraction, by form
    (``GlossaryCandidate.name_head``; ``_name_family_heads``). A short form the book never uses
    on its own -- every occurrence is inside the full form ("Pettish" counted only within
    "Zorvane Pettish") -- is part of the full name, not an entry: it is neither sent nor
    inherited. Returns the candidates to send -- each head carrying its family's count, so the
    model sees how much rests on it -- and the members that stand alone.
    """

    by_surface = {candidate.source_term: candidate for candidate in candidates}
    family = [
        NameFamilyMember(member=candidate, head=by_surface[candidate.name_head])
        for candidate in candidates
        if candidate.name_head and candidate.name_head in by_surface and not candidate.required
    ]
    member_ids = {id(member.member) for member in family}
    forms_by_head: dict[int, list[GlossaryCandidate]] = defaultdict(list)
    for member in family:
        forms_by_head[id(member.head)].append(member.member)
    family_counts: dict[int, int] = defaultdict(int)
    members: list[NameFamilyMember] = []
    for member in family:
        # Codex review 2026-11-07 (finding 5): every form of the family is a suffix of the
        # head, so the forms that contain this one are nested; the occurrences it has on its
        # own are its count minus the count of the NEXT longer form (whose count already holds
        # the longer ones). Summed over the family this telescopes to the count of its
        # shortest form -- the family's real number of mentions, with nothing counted twice.
        words = str(member.member.source_term).casefold().split()
        containing = [
            form
            for form in (member.head, *forms_by_head[id(member.head)])
            if len(str(form.source_term).split()) > len(words)
            and str(form.source_term).casefold().split()[-len(words) :] == words
        ]
        next_longer = min(containing, key=lambda form: len(str(form.source_term).split()))
        standalone = member.member.occurrence_count - next_longer.occurrence_count
        if standalone > 0:
            family_counts[id(member.head)] += standalone
            members.append(member)
    requested = tuple(
        replace(candidate, occurrence_count=candidate.occurrence_count + family_counts[id(candidate)])
        if id(candidate) in family_counts
        else candidate
        for candidate in candidates
        if id(candidate) not in member_ids
    )
    return requested, tuple(members)


def _first_letter(word: str) -> str:
    return next((char for char in word if char.isalpha()), "")


def _latin_base(char: str) -> str:
    """The Latin base letter of ``char`` ("é" -> "e"), or "" when it is not a Latin letter."""

    base = unicodedata.normalize("NFD", char)[:1]
    return base.casefold() if base and unicodedata.name(base, "").startswith("LATIN") else ""


def _is_word_for_word_name_rendering(source_words: Sequence[str], rendering_words: Sequence[str]) -> bool:
    """A rendering whose words stand for the source's words one by one, in order (finding 4).

    By form: as many words as the source, and EVERY rendered word capitalised -- a rendered
    proper name («Бернар Лиетар»); «Женевское озеро» for "Lake Geneva" fails on «озеро», whose
    last word is not the name. Where a rendered word is in the source's (Latin) script, it
    must begin with its source word's letter, which catches a swapped order ("Lietaer
    Bernard"). Across scripts the order cannot be checked without a transliteration table,
    which the repository does not keep (Constitution VII): there the rule trusts the order.
    """

    if len(rendering_words) != len(source_words):
        return False
    for source_word, rendered_word in zip(source_words, rendering_words):
        rendered_letter = _first_letter(rendered_word)
        if not rendered_letter or not rendered_letter.isupper():
            return False
        rendered_base, source_base = _latin_base(rendered_letter), _latin_base(_first_letter(source_word))
        if rendered_base and source_base and rendered_base != source_base:
            return False
    return True


def inherit_name_renderings(
    terms: Sequence[GlossaryTerm],
    members: Sequence[NameFamilyMember],
) -> tuple[tuple[GlossaryTerm, ...], list[dict[str, str]]]:
    """Give each short form the matching end of its head's rendering, right after the head.

    "Zorvane Pettish -> Зорвейн Петтиш" gives "Pettish -> Петтиш". Only when the rendering is a
    word-for-word name rendering (``_is_word_for_word_name_rendering``); otherwise the short
    form gets no entry and the head's entry stands for the family (the phase records it in
    ``uninherited_name_members`` -- the calls are spent, so it cannot be asked for any more);
    so it does when the head was kept as written. Returns the terms and what was inherited.
    """

    rendered = {normalize_glossary_key(term.source_term) for term in terms}
    derived_by_head: dict[tuple[str, ...], list[GlossaryTerm]] = defaultdict(list)
    inherited: list[dict[str, str]] = []
    head_terms = {}
    for term in terms:
        head_terms.setdefault(normalize_glossary_key(term.source_term), term)
    for family_member in members:
        member_key = normalize_glossary_key(family_member.member.source_term)
        head_key = normalize_glossary_key(family_member.head.source_term)
        head_term = head_terms.get(head_key)
        if head_term is None or member_key in rendered:
            continue
        if " ".join(str(head_term.target_term).split()).casefold() == " ".join(
            str(family_member.head.source_term).split()
        ).casefold():
            # A full form kept as written is not a transliteration to share: "Plan-It
            # Newburgh" left in Latin says nothing about how the city "Newburgh" is written.
            continue
        head_words = str(family_member.head.source_term).split()
        member_words = str(family_member.member.source_term).split()
        rendering_words = str(head_term.target_term).split()
        if not _is_word_for_word_name_rendering(head_words, rendering_words):
            continue
        derived = GlossaryTerm(
            source_term=family_member.member.source_term,
            target_term=" ".join(rendering_words[-len(member_words) :]),
            confidence=head_term.confidence,
            kind=head_term.kind,
        )
        derived_by_head[head_key].append(derived)
        rendered.add(member_key)
        inherited.append(
            {
                "source_term": derived.source_term,
                "target_term": derived.target_term,
                "from": head_term.source_term,
            }
        )
    result: list[GlossaryTerm] = []
    placed: set[tuple[str, ...]] = set()
    for term in terms:
        result.append(term)
        key = normalize_glossary_key(term.source_term)
        if key in derived_by_head and key not in placed:
            placed.add(key)
            result.extend(derived_by_head[key])
    return tuple(result), inherited


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


def is_single_lowercase_entry(term: GlossaryTerm) -> bool:
    """An entry of ONE lowercase word with no note: the last class of the prompt section.

    Spec 065 FR-001. A hyphenated word ("value-based"), a capital ("Terra", "GDP"), a name and
    an entry with a note on its sense are each a form of their own and rank with the phrases.
    Spec 067 FR-008: an optional entry of this class is the only one the section budget cuts.
    """

    source = str(term.source_term or "").strip()
    words = _WORD_RE.findall(source)
    return (
        len(words) == 1
        and "-" not in source
        and source == source.lower()
        and term.kind != "name"
        and not str(term.note or "").strip()
    )


def order_glossary_entries(
    candidates: Sequence[GlossaryCandidate],
    terms: Sequence[GlossaryTerm],
) -> tuple[GlossaryTerm, ...]:
    """The glossary in the order of its value to the reader, not the order it was built in.

    Spec 065 FR-001 (G-1: the budget cut The Value of Everything's "production boundary",
    "value extraction" and "national accounts" while "public", "market" and "them the" kept
    their room). Two tiers: every entry of a REQUIRED candidate first -- the budget never cuts
    them (``pipeline/glossary_phase.render_run_glossary_section``) -- then the model's own
    choices. Within a tier, by form: names, phrases, hyphenated, capitalised and noted entries
    before single lowercase words (``is_single_lowercase_entry``); within a class, the
    candidate's occurrence count, highest first; ties keep the order the entries came in, so a
    term's two senses stay together. The budget cut then takes the tail: rare single words of
    the model's own choice first, and nothing else (spec 067 FR-008: an optional entry of a
    form of its own extends the budget like a required one).

    Finally an entry that CONTAINS a single-word entry ("public value" and "value", "value-based"
    and "value") is moved right before that word when it came after it -- the longer entry
    wins (spec 065 FR-003) and is read first; moved ahead of a required word, it rides inside
    the part the budget never cuts.
    """

    required_keys = {normalize_glossary_key(candidate.source_term) for candidate in candidates if candidate.required}
    counts: dict[tuple[str, ...], int] = {}
    for candidate in candidates:
        counts.setdefault(normalize_glossary_key(candidate.source_term), int(candidate.occurrence_count))

    def rank(item: tuple[int, GlossaryTerm]) -> tuple[bool, bool, int, int]:
        index, term = item
        key = normalize_glossary_key(term.source_term)
        return (key not in required_keys, is_single_lowercase_entry(term), -counts.get(key, 0), index)

    ordered = [term for _, term in sorted(enumerate(terms), key=rank)]
    for word_term in [term for term in ordered if len(normalize_glossary_key(term.source_term)) == 1]:
        word = normalize_glossary_key(word_term.source_term)[0]
        if "-" in word:
            continue
        position = next(index for index, term in enumerate(ordered) if term is word_term)
        later = [
            term
            for term in ordered[position + 1 :]
            if term is not word_term and _contains_word(normalize_glossary_key(term.source_term), word)
        ]
        if not later:
            continue
        rest = [term for term in ordered if not any(term is moved for moved in later)]
        position = next(index for index, term in enumerate(rest) if term is word_term)
        ordered = [*rest[:position], *later, *rest[position:]]
    return tuple(ordered)


def _contains_word(key: Sequence[str], word: str) -> bool:
    """``key`` is longer than one word, or hyphenated, and holds ``word`` as a word or a part."""

    if len(key) == 1 and "-" not in key[0]:
        return False
    return any(part == word or word in part.split("-") for part in key)


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
    "NameFamilyMember",
    "RUN_GLOSSARY_SECTION_HEADER",
    "build_glossary_request",
    "build_distinction_request",
    "collision_keepers",
    "declared_spellings",
    "describe_source_language",
    "find_rendering_collisions",
    "inherit_name_renderings",
    "order_collision_group",
    "same_spelling_family",
    "split_name_families",
    "extract_glossary_candidates",
    "GLOSSARY_OUTPUT_TOKENS_CEILING",
    "GLOSSARY_OUTPUT_TOKENS_ENVELOPE",
    "GLOSSARY_OUTPUT_TOKENS_MIN",
    "GLOSSARY_OUTPUT_TOKENS_PER_ENTRY",
    "glossary_max_output_tokens",
    "missing_required_candidates",
    "normalize_glossary_key",
    "normalize_rendering",
    "is_single_lowercase_entry",
    "order_glossary_entries",
    "parse_glossary_response",
    "select_glossary_source_units",
    "split_candidates_in_halves",
]
