"""Narration / audiobook artifact (spec 031 Cluster J; the second pass was removed by spec 070).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the narration-text
builder and the artifact-text review pass (reference-identifier checks). Narration text is
produced only by the standalone ``audiobook`` operation; the optional second LLM pass over
``translate``/``edit`` output and the intonation-tag checks no longer exist. Since spec 070
FR-007 the text is assembled from the per-paragraph records of the block phase, by id and
preparation role, with the deterministic sentence joins counted by id pair. ``late_phases``
re-exports these names so ``late_phases.<name>`` keeps resolving for the test namespace and
the still-in-``late_phases`` ``finalize_processing_success`` caller. No module-level mutable
state; all patterns are immutable compiled constants.

**The artifact check is review DATA, not a verdict gate (spec 054 Finding 4, binding).**
It used to raise, and one match anywhere in a whole book's narration failed the standalone
``audiobook`` run outright — no artifact at all, after the entire LLM run was paid for.
Measured on 2026-08-04, four of the six patterns fired on ordinary prose: a parenthetical
``(Германия, 1923)`` reads as an inline citation, and the bare words ``ISBN`` / ``arXiv``
read as identifiers. Re-measured here over the four corpus books' imported narration text:
``inline_citation`` 4 / 65 / 178 / 191 hits per book. Constitution VII settles the shape of
the fix — a check whose residual is treated as a HARD failure "MUST emit the residual as
review data" — and it also forbids the name / city / publisher lists it would take to make
``inline_citation`` precise. So the check reports, the artifact ships, and a human decides.
The imprecision is now a spare line in a review log instead of a destroyed run.
"""

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord, is_audiobook_operation
from docxaicorrector.pipeline.contracts import LatePhaseStopped


# Space, ASCII hyphen and the Unicode dash block U+2010..U+2015 — the separators a printed
# ISBN is broken with. Form, not a literal: no per-book string enters the rule.
_ISBN_SEPARATOR = r"[ \t‐-―\-]"
_NARRATION_DISALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("doi", re.compile(r"\bdoi\s*[:/]?\s*10\.\d{4,9}/\S+", re.IGNORECASE)),
    # Keyed on the IDENTIFIER, the same form-based shape as ``doi`` above — not on the bare
    # word. ``\bisbn\b`` / ``\barxiv\b`` matched a book that merely TALKS about publishing
    # ("Издательство присвоило книге ISBN и отправило её в печать.", "Он опубликовал
    # препринт на arXiv…"), which is narratable prose and exactly what a listener wants
    # read out. What is not narratable is the number itself, so the number is what the
    # rules require: at least ten ISBN digits after the label, or a real arXiv id.
    # Measured 2026-08-04 over the four corpus books' imported narration text: the bare word
    # ``isbn`` hit 1 / 0 / 3 / 0 times per book and ``isbn_identifier`` hits 1 / 0 / 3 / 0 —
    # every real ISBN is still reported, and every hit is a genuine printed identifier
    # ("ISBN 978-1-60994-296-0"). ``arxiv`` never fired on this corpus in either form, so the
    # tightening cannot have lost signal there; the form mirrors ``doi``, which does fire (7
    # hits on Mazzucato) and is the same shape of rule.
    ("isbn_identifier", re.compile(r"\bisbn(?:-1[03])?\b[^\n\d]{0,8}\d(?:" + _ISBN_SEPARATOR + r"?\d){8,}" + _ISBN_SEPARATOR + r"?[\dXx]", re.IGNORECASE)),
    ("arxiv_identifier", re.compile(r"\barxiv\b\s*[:/]?\s*(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7})", re.IGNORECASE)),
    ("inline_citation", re.compile(r"\((?:ibid\.|там же|[A-ZА-ЯЁ][^()]{0,80}?,\s*(?:19|20)\d{2})[^()]*\)", re.IGNORECASE)),
    # NO superscript-digit rule. A raised digit is not evidence of a footnote marker: the
    # PDF importer emits Unicode superscripts for every small raised digit welded to the
    # text before it, and a mathematical exponent ("x\u00B2", "m\u00B2") is welded exactly like a
    # reference ("\u2026Rome.\u2075", "as Smith notes\u00B9"). Telling them apart needs to understand the
    # formula, which this pipeline deliberately does not do. Removing reference markers is
    # the audiobook prompt's job (rule 1); a model that correctly KEEPS an exponent used to
    # fail this gate, which drops the optional narration on edit/translate and fails a
    # standalone audiobook run outright \u2014 losing the whole artifact over one glyph that TTS
    # would simply read as a number.
)
# A whole book's narration can match one rule hundreds of times (measured: 191 and 178
# ``inline_citation`` hits on two corpus books). The review record carries the COUNT plus a
# few truncated examples — enough to judge the class, small enough for a log line.
_NARRATION_REVIEW_SAMPLE_LIMIT = 3
_NARRATION_REVIEW_SAMPLE_CHARS = 120


# Spec 070 FR-007 / research R8: the ``.tts.txt`` is assembled from the per-paragraph records the
# block phase left (``pipeline.audiobook_pass``), by paragraph id and by the role the PREPARATION
# gave the paragraph -- never by re-reading Markdown the model returned. One rule touches the
# separator between two records: a sentence torn across a paragraph break is rejoined.
#
# What the join is for. 81 of the 83 such boundaries measured on the four-book corpus of
# 2026-08-06 arrive from IMPORT: a PDF line wrap became a paragraph break, both halves are
# there, only the separator is wrong, and a TTS engine reads a paragraph break as a pause in
# the middle of a sentence. Joining changes ``\n\n`` into a space and nothing else.
#
# The test is FORM plus the preparation's ROLE (Constitution VII: no word list, no length):
# * both records have the role ``body`` -- a heading, a list item, an epigraph or an attribution
#   legitimately ends without punctuation and is never welded to what follows;
# * the first ends on a character that is not sentence-terminal (``.!?…:;``), not a closing
#   quote or bracket, and NOT A DIGIT (measured: allowing a digit ending joins rows of an index,
#   which end in a page number);
# * the second begins with a LOWERCASE letter -- "the rest of this sentence", not "whatever
#   comes next".
# Every join is recorded as the pair of ids it closed, counted apart from anything the model
# did: the model cannot merge paragraphs (an answer with another number of markers is refused).
_NARRATION_BODY_ROLE = "body"
_NARRATION_HEADING_ROLE = "heading"
_NARRATION_SENTENCE_TERMINALS = ".!?…:;"
_NARRATION_CLOSING_MARKS = "»”’\"')]}"
NARRATION_BOUNDARY_CHECK_OK = "ok"
NARRATION_BOUNDARY_CHECK_MISMATCH = "mismatch"


@dataclass(frozen=True)
class NarrationGroup:
    """One paragraph of the ``.tts.txt``: the records the deterministic joins put into it (spec 072 FR-001).

    ``text`` is exactly the string the ``.tts.txt`` is joined from, so the TXT and every other
    projection (the narration DOCX) are two views of ONE list of groups. ``role`` and
    ``heading_level`` are the first record's; a joined group is always ``body`` + ``body``
    (``narration_paragraph_continues``), so a heading group is a single record.
    """

    paragraph_ids: tuple[str, ...]
    role: str
    heading_level: int | None
    text: str


@dataclass(frozen=True)
class NarrationAssembly:
    text: str
    join_pairs: tuple[tuple[str, str], ...]
    boundary_check: str
    parsed_paragraph_count: int
    first_mismatch_paragraph_id: str | None
    groups: tuple[NarrationGroup, ...] = ()


def narration_paragraph_continues(*, previous_role: str, previous_text: str, following_role: str, following_text: str) -> bool:
    """Is ``following`` the rest of a sentence ``previous`` was cut off in the middle of?"""

    if previous_role != _NARRATION_BODY_ROLE or following_role != _NARRATION_BODY_ROLE:
        return False
    tail = previous_text.rstrip()
    head = following_text.lstrip()
    if not tail or not head:
        return False
    last = tail[-1]
    if last.isdigit() or last in _NARRATION_SENTENCE_TERMINALS or last in _NARRATION_CLOSING_MARKS:
        return False
    first = head[0]
    return first.isalpha() and first.islower()


def _first_expected_id_difference(record_ids: Sequence[str], expected_ids: Sequence[str]) -> str | None:
    """The first id where the assembled sequence departs from the expected denominator, or ``None``."""

    for delivered, expected in zip(record_ids, expected_ids):
        if delivered != expected:
            return delivered
    if len(record_ids) > len(expected_ids):
        return record_ids[len(expected_ids)]
    if len(record_ids) < len(expected_ids):
        return expected_ids[len(record_ids)]
    return None


def assemble_narration_records(
    records: Sequence[NarrationParagraphRecord],
    expected_paragraph_ids: Sequence[str] | None = None,
) -> NarrationAssembly:
    """The ``.tts.txt`` text from the records, and the check that it parses back into them.

    Paragraphs are joined by ``"\\n\\n"``; a deterministic join (see above) puts one space
    instead. The check reads the FINAL text back: split on ``"\\n\\n"`` it must give exactly
    ``records - joins`` paragraphs, and each must be its records' texts in order. A mismatch
    is a defect of this code (a record text carrying a blank line), never of the model.

    ``expected_paragraph_ids`` is the run's fixed denominator (``narration_expected_paragraph_ids``):
    when it is given, the SEQUENCE of the records' ids, with multiplicity, must equal it (a record
    without an id is not compared, as before). A reorder, a duplicate or a loss is a mismatch.
    """

    groups: list[list[NarrationParagraphRecord]] = []
    join_pairs: list[tuple[str, str]] = []
    for record in records:
        if groups and narration_paragraph_continues(
            previous_role=groups[-1][-1].role,
            previous_text=groups[-1][-1].text,
            following_role=record.role,
            following_text=record.text,
        ):
            join_pairs.append((groups[-1][-1].paragraph_id, record.paragraph_id))
            groups[-1].append(record)
            continue
        groups.append([record])
    group_texts = [" ".join(member.text.strip() for member in group) for group in groups]
    text = "\n\n".join(group_texts)

    parsed = text.split("\n\n")
    mismatch = False
    first_mismatch: str | None = None
    if len(parsed) != len(records) - len(join_pairs):
        mismatch = True
        first_mismatch = next(
            (group[0].paragraph_id for group, group_text in zip(groups, group_texts) if "\n\n" in group_text or not group_text.strip()),
            groups[0][0].paragraph_id if groups else None,
        )
    else:
        for paragraph, group in zip(parsed, groups):
            cursor = 0
            for member in group:
                member_text = member.text.strip()
                position = paragraph.find(member_text, cursor) if member_text else -1
                if position < 0:
                    mismatch = True
                    first_mismatch = member.paragraph_id
                    break
                cursor = position + len(member_text)
            if mismatch:
                break
    if not mismatch and expected_paragraph_ids:
        record_ids = [record.paragraph_id for record in records if record.paragraph_id]
        difference = _first_expected_id_difference(record_ids, [str(item) for item in expected_paragraph_ids])
        if difference is not None:
            mismatch = True
            first_mismatch = difference
    return NarrationAssembly(
        text=text,
        join_pairs=tuple(join_pairs),
        boundary_check=NARRATION_BOUNDARY_CHECK_MISMATCH if mismatch else NARRATION_BOUNDARY_CHECK_OK,
        parsed_paragraph_count=len(parsed),
        first_mismatch_paragraph_id=first_mismatch,
        groups=tuple(
            NarrationGroup(
                paragraph_ids=tuple(member.paragraph_id for member in group),
                role=group[0].role,
                heading_level=(
                    group[0].heading_level if str(group[0].role or "").strip().casefold() == _NARRATION_HEADING_ROLE else None
                ),
                text=group_text,
            )
            for group, group_text in zip(groups, group_texts)
        ),
    )


def _build_narration_text(*, context: Any, dependencies: Any, emitters: Any, state: Any, final_generated_paragraph_registry: Sequence[object] | None = None) -> str | None:
    stop_predicate = getattr(dependencies, "should_stop_processing", None) if dependencies is not None else None
    if callable(stop_predicate) and stop_predicate(getattr(context, "runtime", None)):
        raise LatePhaseStopped()
    if not is_audiobook_operation(getattr(context, "processing_operation", None)):
        return None
    records = [
        record
        for record in (getattr(state, "narration_paragraphs", None) or ())
        if isinstance(record, NarrationParagraphRecord) and record.text.strip()
    ]
    if not records:
        return None
    assembly = assemble_narration_records(records, getattr(state, "narration_expected_paragraph_ids", None))
    state.narration_joined_sentence_continuation_count = len(assembly.join_pairs)
    state.narration_joined_paragraph_id_pairs = list(assembly.join_pairs)
    state.narration_paragraph_boundary_check = assembly.boundary_check
    # Spec 072 FR-001: the groups the text was joined from, for the narration DOCX (a second projection of them).
    state.narration_groups = list(assembly.groups)
    if assembly.boundary_check != NARRATION_BOUNDARY_CHECK_OK:
        log_event = getattr(dependencies, "log_event", None)
        if callable(log_event):
            # A defect of the assembly, not of the model; delivery is not blocked (Anti-regression 2).
            log_event(
                logging.ERROR,
                "audiobook_paragraph_boundary_mismatch",
                "Итоговый текст озвучки не разбирается обратно в абзацы по их ID.",
                filename=getattr(context, "uploaded_filename", None),
                expected_paragraph_count=len(getattr(state, "narration_expected_paragraph_ids", None) or ()),
                delivered_paragraph_count=len(records),
                deterministic_join_count=len(assembly.join_pairs),
                parsed_paragraph_count=assembly.parsed_paragraph_count,
                first_mismatch_paragraph_id=assembly.first_mismatch_paragraph_id,
            )
    return assembly.text


def _collect_narration_artifact_review_findings(narration_text: str) -> list[dict[str, object]]:
    """Report what the finished narration still carries, as review DATA for a human.

    Replaces ``_validate_narration_artifact_text``, which raised. Returns one entry per rule
    that matched — rule name, how many times, and up to
    ``_NARRATION_REVIEW_SAMPLE_LIMIT`` truncated samples so the reader can judge the match
    without the log carrying the model payload (LOGGING_AND_ARTIFACT_RETENTION §1.5).
    An empty list means nothing to review; it is never an error either way.
    """
    findings: list[dict[str, object]] = []
    for name, pattern in _NARRATION_DISALLOWED_PATTERNS:
        matches = [match.group(0) for match in pattern.finditer(narration_text)]
        if not matches:
            continue
        findings.append(
            {
                "rule": name,
                "match_count": len(matches),
                "samples": [
                    _truncate_narration_review_sample(match)
                    for match in matches[:_NARRATION_REVIEW_SAMPLE_LIMIT]
                ],
            }
        )
    return findings


def _truncate_narration_review_sample(sample: str) -> str:
    collapsed = " ".join(str(sample).split())
    if len(collapsed) <= _NARRATION_REVIEW_SAMPLE_CHARS:
        return collapsed
    return collapsed[:_NARRATION_REVIEW_SAMPLE_CHARS] + "…"


def _summarize_narration_review_findings(
    findings: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Flatten review findings into the counters every observable surface publishes."""
    rules = [str(finding.get("rule", "")) for finding in findings]
    match_count = 0
    for finding in findings:
        raw_count = finding.get("match_count", 0)
        match_count += raw_count if isinstance(raw_count, int) and not isinstance(raw_count, bool) else 0
    return {
        "review_finding_count": len(findings),
        "review_match_count": match_count,
        "review_rules": rules,
    }
