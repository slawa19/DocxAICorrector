"""Narration / audiobook artifact (spec 031 Cluster J; the second pass was removed by spec 070).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the narration-text
builder and the artifact-text review pass (reference-identifier checks). Narration text is
produced only by the standalone ``audiobook`` operation; the optional second LLM pass over
``translate``/``edit`` output and the intonation-tag checks no longer exist. ``late_phases``
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

import re
from collections.abc import Mapping, Sequence
from typing import Any

from docxaicorrector.generation._generation import strip_markdown_for_narration_with_stats
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


def _build_narration_text(*, context: Any, dependencies: Any, emitters: Any, state: Any, final_generated_paragraph_registry: Sequence[object] | None = None) -> str | None:
    stop_predicate = getattr(dependencies, "should_stop_processing", None) if dependencies is not None else None
    if callable(stop_predicate) and stop_predicate(getattr(context, "runtime", None)):
        raise LatePhaseStopped()
    if context.processing_operation != "audiobook":
        return None
    narration_source = "\n\n".join(_collect_narration_chunks(state=state))
    if not narration_source:
        return None
    return _assemble_narration_recording_joins(narration_source, state=state)


def _assemble_narration_recording_joins(narration_source: str, *, state: Any) -> str:
    """Assemble the narration and record how many sentence continuations were rejoined.

    The narration text is assembled here, and the counter means the same thing as the
    exclusion counters beside it do (anti-regression 3 of spec 054).
    """

    narration_text, joined_count = strip_markdown_for_narration_with_stats(narration_source)
    if state is not None:
        state.narration_joined_sentence_continuation_count = int(
            getattr(state, "narration_joined_sentence_continuation_count", 0) or 0
        ) + joined_count
    return narration_text


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


def _collect_narration_chunks(*, state: Any) -> list[str]:
    return [str(chunk).strip() for chunk in getattr(state, "narration_chunks", []) if str(chunk).strip()]
