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
the two concrete shapes that actually went stale — a test-result count and a
pinned ``main`` commit — plus enough structure to know that a document is still
there to check. It deliberately does NOT try to judge whether the prose is still
true; no test can do that, and pretending otherwise would be the false green this
repository has been burned by before.

The structural half was added on 2026-08-02 after an external review (Codex,
gpt-5.6-sol) showed the anti-vacuum check passing vacuously: it asked only that
the strings ``scripts/test.sh`` and ``git log`` appear *somewhere*, so a two-line
file containing nothing but those two words satisfied every test in this module.
The commands must now sit inside a fenced code block, and the file must still
have the shape of navigation — sections, runnable blocks, and the one heading
``tests/test_spec_status_consistency.py`` reads by name.

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
#
# Substring presence alone was NOT enough, and an external review (Codex,
# gpt-5.6-sol, 2026-08-02) demonstrated it: a two-line file reading
# "scripts/test.sh / git log" satisfied every check in this module. The guard
# built against emptiness passed vacuously on an empty document. So the anchors
# must now sit inside a fenced code block — where a reader can copy and run
# them — and the document must still have the shape of navigation.
_REQUIRED_COMMAND_ANCHORS = (
    "scripts/test.sh",
    "git log",
)

# The one section another test reads by name: tests/test_spec_status_consistency.py
# requires every open spec to be mentioned under it. If it disappears, that guard
# starts passing for the wrong reason, so it is checked from this side too.
_CROSS_CHECKED_SECTION = "## Что открыто"

# Structural floors, set well below what the document actually carries (12 `##`
# sections, 4 fenced blocks, ~200 lines) so ordinary editing never trips them.
# They are counts and positions only. This module still refuses to judge whether
# the PROSE is true — no test can, and a guard that pretended to would be exactly
# the false green this repository keeps getting burned by. The floors answer one
# narrower question: is there a document here at all, or only the keywords the
# guards look for?
_MIN_SECTIONS = 5
_MIN_FENCED_BLOCKS = 2
_MIN_NON_EMPTY_LINES = 40

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


def _fenced_code_blocks(text: str) -> list[str]:
    """The bodies of the ``` fenced blocks, in order."""
    return re.findall(r"^```[^\n]*\n(.*?)^```", text, flags=re.DOTALL | re.MULTILINE)


def _section_bodies(text: str) -> dict[str, str]:
    """Each ``## `` heading mapped to the text under it, up to the next ``## ``."""
    parts = re.split(r"^(## .+)$", text, flags=re.MULTILINE)
    return {
        parts[index].strip(): parts[index + 1]
        for index in range(1, len(parts) - 1, 2)
    }


def test_navigation_document_exists_and_keeps_its_verification_commands() -> None:
    """Anti-vacuum: the guards below must not pass because the file went empty."""
    assert WHERE_WE_ARE_PATH.is_file(), (
        f"{WHERE_WE_ARE_PATH.relative_to(REPO_ROOT).as_posix()} is missing. It is the "
        "navigation document this guard and tests/test_spec_status_consistency.py "
        "both cross-check."
    )
    runnable = "\n".join(_fenced_code_blocks(_document_text()))
    missing = [anchor for anchor in _REQUIRED_COMMAND_ANCHORS if anchor not in runnable]
    assert not missing, (
        "docs/WHERE_WE_ARE.md no longer carries its verification commands inside a "
        f"fenced code block (missing there: {', '.join(missing)}). The whole point of "
        "the file is that a reader can copy a command and re-derive the project's "
        "state in a minute instead of trusting a number someone typed in weeks ago — "
        "a command mentioned in passing in a sentence is not that."
        + _FIX_HINT
    )


def test_navigation_document_still_has_the_shape_of_navigation() -> None:
    """A file containing only the keywords the guards look for is not a document.

    Counts and positions only — see the note next to the floors. This exists
    because the previous anti-vacuum check passed on a two-line file.
    """
    text = _document_text()
    sections = _section_bodies(text)
    blocks = _fenced_code_blocks(text)
    non_empty_lines = [line for line in text.splitlines() if line.strip()]

    shortfalls = []
    if len(sections) < _MIN_SECTIONS:
        shortfalls.append(f"{len(sections)} `## ` sections (need at least {_MIN_SECTIONS})")
    if len(blocks) < _MIN_FENCED_BLOCKS:
        shortfalls.append(f"{len(blocks)} fenced code blocks (need at least {_MIN_FENCED_BLOCKS})")
    if len(non_empty_lines) < _MIN_NON_EMPTY_LINES:
        shortfalls.append(
            f"{len(non_empty_lines)} non-empty lines (need at least {_MIN_NON_EMPTY_LINES})"
        )

    assert not shortfalls, (
        "docs/WHERE_WE_ARE.md has been hollowed out: " + "; ".join(shortfalls) + ".\n\n"
        "These floors sit far below what the document normally carries, so ordinary "
        "editing does not trip them. They only answer 'is there a document here at "
        "all' — the question the earlier version of this guard failed to ask, which "
        "is how a two-line file could satisfy every check in this module."
    )


def test_navigation_document_keeps_the_open_work_section_other_tooling_reads() -> None:
    """`## Что открыто` is a cross-file contract, not decoration.

    ``tests/test_spec_status_consistency.py`` asserts that every spec whose status
    means "still open" is mentioned under this heading. Delete the heading and that
    guard has nothing to check; leave it empty and it has nothing to find. Both are
    checked from this side so neither can go quietly green.
    """
    sections = _section_bodies(_document_text())
    assert _CROSS_CHECKED_SECTION in sections, (
        f"docs/WHERE_WE_ARE.md no longer has a `{_CROSS_CHECKED_SECTION}` section. "
        "tests/test_spec_status_consistency.py reads it by name to check that open "
        "specs are listed somewhere a reader will look; without it that guard passes "
        "vacuously."
    )
    body = [line for line in sections[_CROSS_CHECKED_SECTION].splitlines() if line.strip()]
    assert body, (
        f"`{_CROSS_CHECKED_SECTION}` in docs/WHERE_WE_ARE.md is empty. If nothing is "
        "genuinely open, say so in a sentence — an empty section reads as an omission, "
        "and tests/test_spec_status_consistency.py cannot tell the two apart."
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
