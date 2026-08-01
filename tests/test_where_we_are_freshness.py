"""Static guard: ``docs/WHERE_WE_ARE.md`` must not pin values that go stale.

Why this file exists
--------------------
``docs/WHERE_WE_ARE.md`` was created on 2026-07-31 as the cure for documentation
that had drifted away from the code for months. Its first revision opened with
``main = `14b8f49``` and reported project health as "2296 passed / 9 skipped".
Both statements were false the next day: the first merge after it landed moved
``main`` and added tests. The document written against staleness went stale in
under 24 hours, in exactly the way it was supposed to prevent.

The fix was editorial, not mechanical: the file now stores the *command* that
produces a value instead of the value, and numbers that have a real owner in the
repository stay with their owner (the pyright baseline, for instance, is
``_ERROR_BASELINE`` in ``tests/test_typecheck.py``, and that test fails in both
directions, so it cannot disagree with reality).

This guard exists so the editorial decision survives the next editor. It checks
only the two concrete shapes that actually went stale — a test-result count and a
pinned ``main`` commit. It deliberately does NOT try to judge whether the prose is
still true; no test can do that, and pretending otherwise would be the false green
this repository has been burned by before.

Historical commit references ("the UI shipped in `58aaf2a` on 2026-07-13") are
fine and are not flagged: the past does not go stale. Only a hash presented as
"this is where ``main`` is right now" is rejected.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WHERE_WE_ARE_PATH = REPO_ROOT / "docs" / "WHERE_WE_ARE.md"

pytestmark = pytest.mark.static_workflow


# A pytest result tally: "2296 passed", "9 skipped", "30 passed in 14:55", and the
# Russian forms the document is written in.
_TEST_COUNT_PATTERN = re.compile(
    r"\b\d+\s*(?:passed|failed|skipped|errors?|тест(?:а|ов)?\b)",
    re.IGNORECASE,
)

# "main = `14b8f49`", "`main` — `0062493`": a commit hash presented as the current
# position of the branch. The hash must be backticked (the repository convention)
# and must contain a digit, so ordinary hexadecimal-looking words are not flagged.
_PINNED_HEAD_PATTERN = re.compile(
    r"`?main`?\s*(?:=|—|–|:|\bat\b)\s*`(?=[0-9a-f]*\d)[0-9a-f]{7,40}`",
    re.IGNORECASE,
)

# Anti-vacuum anchors: the document must keep the verification commands that
# replaced the numbers. Without them the two guards above would pass on a file
# that simply says nothing.
_REQUIRED_ANCHORS = (
    "scripts/test.sh",
    "git log",
)

_FIX_HINT = (
    "\n\ndocs/WHERE_WE_ARE.md is navigation, and values that change on every merge "
    "do not belong in it — its first revision pinned both and was wrong within a "
    "day. Store the command that produces the value instead, or point at the file "
    "that owns the number (e.g. _ERROR_BASELINE in tests/test_typecheck.py). If a "
    "count really has to be quoted, quote it inside a spec under specs/, which is "
    "dated and historical by nature."
)


def _document_text() -> str:
    return WHERE_WE_ARE_PATH.read_text(encoding="utf-8")


def _offending_lines(pattern: re.Pattern[str]) -> list[str]:
    return [
        f"  line {number}: {line.strip()}"
        for number, line in enumerate(_document_text().splitlines(), start=1)
        if pattern.search(line)
    ]


def test_navigation_document_exists_and_keeps_its_verification_commands() -> None:
    """Anti-vacuum: the guards below must not pass because the file went empty."""
    assert WHERE_WE_ARE_PATH.is_file(), (
        f"{WHERE_WE_ARE_PATH.relative_to(REPO_ROOT).as_posix()} is missing. It is the "
        "navigation document this guard and tests/test_spec_status_consistency.py "
        "both cross-check."
    )
    text = _document_text()
    missing = [anchor for anchor in _REQUIRED_ANCHORS if anchor not in text]
    assert not missing, (
        "docs/WHERE_WE_ARE.md no longer contains the verification commands it is "
        f"built around (missing: {', '.join(missing)}). The whole point of the file "
        "is that a reader can re-derive the project's state in a minute instead of "
        "trusting a number someone typed in weeks ago."
    )


def test_navigation_document_quotes_no_test_result_counts() -> None:
    """Health is reported as a command to run, never as a tally that rots."""
    offenders = _offending_lines(_TEST_COUNT_PATTERN)
    assert not offenders, (
        "docs/WHERE_WE_ARE.md quotes test-result counts:\n"
        + "\n".join(offenders)
        + _FIX_HINT
    )


def test_navigation_document_does_not_pin_the_current_head_commit() -> None:
    """A "main is at <sha>" claim is false as soon as anything is merged."""
    offenders = _offending_lines(_PINNED_HEAD_PATTERN)
    assert not offenders, (
        "docs/WHERE_WE_ARE.md pins the current position of `main` to a commit hash:\n"
        + "\n".join(offenders)
        + "\n\nDrop it — `git log --oneline -5 main` answers the question and cannot "
        "be wrong. A hash named as a historical fact (\"the UI shipped in `58aaf2a`\") "
        "is fine and is not what this guard looks for."
    )


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        # The exact wordings that went stale, plus the shapes near them.
        ("полный набор **2296 passed / 9 skipped / 0 failed**", True),
        ("канонический гейт — **30 passed**, включая все четыре книги", True),
        ("46 из 2296 тестов в CI не выполняются никогда", True),
        ("static tier 58 passed", True),
        # Legitimate prose that must NOT be flagged.
        ("bash scripts/test.sh tests/ -q  # полный набор тестов", False),
        ("ни один из 30 потерянных заголовков не имел шрифта крупнее соседей", False),
        ("эталон pyright живёт в `_ERROR_BASELINE`", False),
    ],
)
def test_test_count_pattern_matches_only_result_tallies(text: str, flagged: bool) -> None:
    assert bool(_TEST_COUNT_PATTERN.search(text)) is flagged


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("**Обновлено: 2026-07-31.** `main` = `14b8f49` (слияние PR #6).", True),
        ("main = `0062493`", True),
        ("`main` — `cc5b622`", True),
        # Historical references and ordinary command lines must survive.
        ("Он сделан спекой 013 (коммит `58aaf2a`, 2026-07-13)", False),
        ("git log --oneline main --grep=\"spec 043\"", False),
        ("git log --oneline main..<branch>", False),
        ("git merge-base --is-ancestor <commit> main", False),
    ],
)
def test_pinned_head_pattern_matches_only_a_current_head_claim(
    text: str, flagged: bool
) -> None:
    assert bool(_PINNED_HEAD_PATTERN.search(text)) is flagged
