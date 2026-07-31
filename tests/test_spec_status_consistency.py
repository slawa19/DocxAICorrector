"""Static guard: spec ``Status:`` headers must be honest and must agree with the
navigation document ``docs/WHERE_WE_ARE.md``.

Why this file exists
--------------------
On 2026-07-31 a session planned the next step from a document that said "next up:
the UI slice" — the UI had in fact shipped a month earlier (spec 013). The root
cause was systemic, not a one-off typo: the ``Status:`` field in
``specs/NNN-*/spec.md`` had been drifting for months (12 specs were marked as not
done while their code was already merged; two literally said "merging is not
recommended"), and nothing checked it. ``tests/test_documentation_links.py`` only
proves links resolve — it says nothing about whether the words are still true.

Why this guard does NOT look at git
-----------------------------------
The obvious check — "if Status is PLANNED there must be no commits about this spec
in ``git log main``" — is a trap. ``actions/checkout@v4`` in
``.github/workflows/ci.yml`` runs with the default ``fetch-depth: 1``, so CI has a
shallow clone with no history: every history query would come back empty and the
guard would go *vacuously green* — exactly the class of false green this project
has already been burned by. So this guard is purely static: it reads files and
cross-checks two documents that are obliged to agree.

What it enforces
----------------
1. Every ``specs/NNN-*/spec.md`` has a parseable status line whose value is in the
   controlled vocabulary below (the vocabulary was derived from what the specs
   actually say — specs are not rewritten to fit it).
2. Every spec whose status means "work is still OPEN" is mentioned in the
   "Что открыто" section of ``docs/WHERE_WE_ARE.md``.

The reverse direction is deliberately NOT enforced: the navigation section also
mentions closed specs as context (e.g. "spec 049 showed what happens when...") and
that is legitimate.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SPECS_ROOT = REPO_ROOT / "specs"
WHERE_WE_ARE_PATH = REPO_ROOT / "docs" / "WHERE_WE_ARE.md"

# The heading of the section of docs/WHERE_WE_ARE.md that lists unfinished work.
OPEN_SECTION_HEADING = "## Что открыто"

pytestmark = pytest.mark.static_workflow


# --------------------------------------------------------------------------- #
# Controlled vocabulary
# --------------------------------------------------------------------------- #
# Collected from the actual headers of specs 001-051 on 2026-07-31 — the point is
# to describe what the repository says, not to force the specs into a new format.
# Two categories only, because only one distinction matters for navigation:
# is there work left to do, or not?
#
# When you introduce a new status wording, add it here WITH its category. An
# unknown status fails the first test with the list of accepted values.

# "Work is closed" — finished, superseded, deliberately shelved, or decided
# against. Nothing is expected to happen next.
CLOSED_STATUSES: dict[str, str] = {
    "IMPLEMENTED": "code landed",
    "DONE": "code landed and merged",
    "IMPLEMENTED THEN SUPERSEDED": "landed, later replaced by a newer spec",
    "PARTIALLY IMPLEMENTED": "the remainder was carried into a later spec, not into this one",
    "CLOSED": "closed without code — e.g. CLOSED — NOT NEEDED, diagnosis reversed",
    "NOT MERGED": "deliberately shelved; the spec documents why it was abandoned",
    "DECISION RECORD": "records a product decision; no code change was ever intended",
    "MEASURED": "hypothesis was implemented, measured, disproven and reverted",
    "SHELVED": "deliberately abandoned",
    "SUPERSEDED": "replaced by a newer spec",
    "REJECTED": "decided against",
    "OBSOLETE": "no longer applicable",
}

# "Work is open" — someone is expected to do something. Every spec in this
# category must be findable in docs/WHERE_WE_ARE.md.
OPEN_STATUSES: dict[str, str] = {
    "BACKLOG": "logged, not scheduled",
    "CONCEPT": "concept only — e.g. CONCEPT — NOT A SOLUTION SPEC; needs an experiment first",
    "PLANNED": "planned, not started",
    "DRAFT": "being written",
    "PROPOSED": "awaiting a go/no-go decision",
    "ACTIVE": "in flight",
    "IN PROGRESS": "in flight",
    "TODO": "not started",
    "BLOCKED": "waiting on something",
    "NEEDS DECISION": "waiting on an owner decision",
    "READY": "specified and ready to implement",
    # Parked by an owner decision, with no date. Still OPEN on purpose: the whole
    # point of parking it here rather than deleting the spec is that the question
    # stays visible in docs/WHERE_WE_ARE.md instead of being quietly forgotten.
    "DEFERRED": "parked by owner decision; keep it visible, do not schedule it",
}

KNOWN_STATUSES: dict[str, str] = {**CLOSED_STATUSES, **OPEN_STATUSES}


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
# Both header dialects are in use and both are accepted:
#     Status: IMPLEMENTED (2026-07-16). ...
#     **Status**: **IMPLEMENTED (2026-07-20) — merged to `main` ...**
_STATUS_LINE = re.compile(r"^\s*(?:[*_]{0,2})status(?:[*_]{0,2})\s*:\s*(?P<value>.+?)\s*$", re.IGNORECASE)

# The status line is prose: a short verdict followed by dates, commit hashes and a
# narrative. Only the verdict is the machine-readable part, so cut at the first
# character that starts the narrative.
_NARRATIVE_DELIMITERS = "(.,:;`"

# The verdict itself may be a dashed phrase ("CLOSED — NOT NEEDED"). Splitting on
# the dash lets us try the long phrase first and fall back to its head.
_DASH_SPLIT = re.compile(r"\s*[—–]\s*|\s+-\s+")

# How far into a spec we look for its status header.
_HEADER_SCAN_LINES = 40


def _spec_files() -> list[Path]:
    """Every ``specs/NNN-*/spec.md``, sorted by spec number."""
    return sorted(
        path
        for path in SPECS_ROOT.glob("*/spec.md")
        if re.match(r"^\d{3}-", path.parent.name)
    )


def _raw_status_line(spec_path: Path) -> str | None:
    """The raw text after ``Status:`` in the spec header, or ``None``."""
    lines = spec_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES]
    for line in lines:
        match = _STATUS_LINE.match(line)
        if match:
            return match.group("value").strip()
    return None


def status_phrase(raw_status: str) -> str:
    """Normalize a raw status line down to its leading verdict phrase.

    ``"**DONE — merged to `main` 2026-07-13 in `58aaf2a`**"`` -> ``"DONE"``
    ``"**MEASURED — PREMISE DISPROVEN (2026-07-21).**"``      -> ``"MEASURED"``
    """
    text = raw_status.replace("**", " ").replace("__", " ").strip().lstrip("*_ ")
    cut = min(
        (text.index(char) for char in _NARRATIVE_DELIMITERS if char in text),
        default=len(text),
    )
    head = " ".join(text[:cut].split()).upper().strip("*_ ")
    return head


def classify_status(raw_status: str) -> tuple[str | None, str]:
    """Return ``(category, matched_phrase)`` for a raw status line.

    ``category`` is ``"closed"``, ``"open"`` or ``None`` when the wording is not in
    the controlled vocabulary. Dashed phrases are matched longest-first, so
    ``"CLOSED — NOT NEEDED"`` is tried before ``"CLOSED"``.
    """
    head = status_phrase(raw_status)
    segments = [segment for segment in _DASH_SPLIT.split(head) if segment]
    for length in range(len(segments), 0, -1):
        candidate = " — ".join(segments[:length])
        if candidate in CLOSED_STATUSES:
            return "closed", candidate
        if candidate in OPEN_STATUSES:
            return "open", candidate
    return None, head


def _open_section_text() -> str:
    """The body of the "Что открыто" section of docs/WHERE_WE_ARE.md."""
    text = WHERE_WE_ARE_PATH.read_text(encoding="utf-8")
    start = text.find(OPEN_SECTION_HEADING)
    if start == -1:
        return ""
    after_heading = text[start + len(OPEN_SECTION_HEADING) :]
    end = after_heading.find("\n## ")
    return after_heading if end == -1 else after_heading[:end]


def _is_mentioned(spec_dir_name: str, section_text: str) -> bool:
    """Is this spec referenced in the given navigation text?

    Accepts the directory name, a ``specs/NNN-`` path, or a prose reference such as
    "Спека 050" / "спеки 017" / "spec 050".
    """
    number = spec_dir_name[:3]
    if spec_dir_name in section_text:
        return True
    patterns = (
        rf"specs/{number}-",
        rf"(?:спек\w*|spec)\s*[`*_]*{number}\b",
    )
    return any(re.search(pattern, section_text, re.IGNORECASE) for pattern in patterns)


def _known_statuses_help() -> str:
    closed = ", ".join(sorted(CLOSED_STATUSES))
    opened = ", ".join(sorted(OPEN_STATUSES))
    return f"work-is-closed values: {closed}\nwork-is-open values: {opened}"


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def test_specs_are_discovered() -> None:
    """Anti-vacuum: the two guards below must never pass because they found nothing."""
    spec_files = _spec_files()
    assert len(spec_files) >= 40, (
        f"only {len(spec_files)} spec.md files found under {SPECS_ROOT} — the status "
        "guard would be vacuously green. Check the layout of specs/NNN-*/spec.md."
    )
    assert WHERE_WE_ARE_PATH.is_file(), (
        f"{WHERE_WE_ARE_PATH.relative_to(REPO_ROOT).as_posix()} is missing — it is the "
        "navigation document this guard cross-checks the spec statuses against."
    )
    assert OPEN_SECTION_HEADING in WHERE_WE_ARE_PATH.read_text(encoding="utf-8"), (
        f"docs/WHERE_WE_ARE.md must keep the '{OPEN_SECTION_HEADING}' section: it is "
        "where every spec whose status means 'work is open' has to be listed. If the "
        "section is renamed, update OPEN_SECTION_HEADING in this file too."
    )


def test_every_spec_declares_a_status_from_the_controlled_vocabulary() -> None:
    """Each spec must carry a status line whose value this repo recognizes."""
    missing: list[str] = []
    unknown: list[str] = []

    for spec_path in _spec_files():
        spec_name = spec_path.parent.name
        raw_status = _raw_status_line(spec_path)
        if raw_status is None:
            missing.append(spec_name)
            continue
        category, phrase = classify_status(raw_status)
        if category is None:
            unknown.append(f"{spec_name}: status reads {phrase!r} (raw: {raw_status[:80]!r})")

    problems: list[str] = []
    if missing:
        problems.append(
            "these specs have no status line in their first "
            f"{_HEADER_SCAN_LINES} lines: {', '.join(missing)}.\n"
            "Fix: add `Status: <value>` (or `**Status**: <value>`) to the spec header."
        )
    if unknown:
        problems.append(
            "these specs use a status wording that is not in the controlled "
            "vocabulary:\n  " + "\n  ".join(unknown) + "\n"
            "Fix: either reword the spec header to an accepted value, or — if the new "
            "wording is deliberate — add it to CLOSED_STATUSES or OPEN_STATUSES in "
            f"{Path(__file__).name} together with the category it belongs to.\n"
            + _known_statuses_help()
        )

    assert not problems, "\n\n".join(problems)


def test_specs_with_open_work_are_listed_in_where_we_are() -> None:
    """Any spec whose status means "work is open" must appear in the navigation doc.

    This is the link that stops ``docs/WHERE_WE_ARE.md`` from drifting away from the
    specs: an open spec cannot hide, and a spec that is silently finished cannot keep
    an open-sounding status without being listed as open work.
    """
    section_text = _open_section_text()
    unlisted: list[str] = []
    open_specs: list[str] = []

    for spec_path in _spec_files():
        spec_name = spec_path.parent.name
        raw_status = _raw_status_line(spec_path)
        if raw_status is None:
            continue  # reported by the vocabulary guard above
        category, phrase = classify_status(raw_status)
        if category != "open":
            continue
        open_specs.append(f"{spec_name} ({phrase})")
        if not _is_mentioned(spec_name, section_text):
            unlisted.append(
                f"- specs/{spec_name}/spec.md declares status {phrase!r} "
                f"(raw: {raw_status[:80]!r}) but is not mentioned in the "
                f"'{OPEN_SECTION_HEADING}' section of docs/WHERE_WE_ARE.md"
            )

    assert not unlisted, (
        "docs/WHERE_WE_ARE.md has drifted away from the spec statuses.\n"
        + "\n".join(unlisted)
        + "\n\nFix ONE of these, whichever is true:\n"
        "  (a) the work really is open -> add a short paragraph for the spec under "
        f"'{OPEN_SECTION_HEADING}' in docs/WHERE_WE_ARE.md (say what is left and what "
        "blocks it);\n"
        "  (b) the work is finished or was dropped -> correct the `Status:` line in the "
        "spec itself to a closed value (DONE / IMPLEMENTED / CLOSED — NOT NEEDED / "
        "NOT MERGED / ...). Verify with `git log --oneline main --grep=\"spec NNN\"` "
        "before you claim it is done.\n"
        f"Specs currently classified as open: {', '.join(open_specs) or 'none'}"
    )


def test_status_vocabulary_categories_do_not_overlap() -> None:
    """A status wording must mean exactly one thing."""
    overlap = sorted(set(CLOSED_STATUSES) & set(OPEN_STATUSES))
    assert not overlap, (
        "these status values are listed as BOTH closed and open, so the guard cannot "
        f"classify them: {overlap}. Pick one category."
    )


@pytest.mark.parametrize(
    ("raw_status", "expected_category", "expected_phrase"),
    [
        # The real header shapes found across specs 001-051. This doubles as the
        # format documentation and as a regression test for the parser itself.
        ("Implemented (2026-07-10). Verified on all four books.", "closed", "IMPLEMENTED"),
        ("**IMPLEMENTED (detection, advisory) 2026-07-11.**", "closed", "IMPLEMENTED"),
        ("DONE — merged to `main` 2026-07-11 in `21cf9d0`.", "closed", "DONE"),
        ("**DONE — implemented and merged to `main` 2026-07-17.**", "closed", "DONE"),
        ("**CLOSED — NOT NEEDED (2026-07-14).** Diagnosis reversed.", "closed", "CLOSED"),
        ("NOT MERGED (2026-07-11). Shelved after verification proved impossible.", "closed", "NOT MERGED"),
        ("DECISION RECORD (2026-07-11). No code change.", "closed", "DECISION RECORD"),
        ("**MEASURED — PREMISE DISPROVEN (2026-07-21).**", "closed", "MEASURED"),
        ("**PARTIALLY IMPLEMENTED — round-4 review reopened gaps (2026-07-16).**", "closed", "PARTIALLY IMPLEMENTED"),
        ("**IMPLEMENTED then SUPERSEDED — landed on `main` 2026-07-17.**", "closed", "IMPLEMENTED THEN SUPERSEDED"),
        ("BACKLOG — logged, not scheduled.", "open", "BACKLOG"),
        ("**CONCEPT — NOT A SOLUTION SPEC.**", "open", "CONCEPT"),
        ("PLANNED", "open", "PLANNED"),
        ("Draft", "open", "DRAFT"),
        # Unrecognized wording must be reported, never silently treated as closed.
        ("Mostly fine probably", None, "MOSTLY FINE PROBABLY"),
    ],
)
def test_status_parser_handles_the_real_header_shapes(
    raw_status: str, expected_category: str | None, expected_phrase: str
) -> None:
    assert classify_status(raw_status) == (expected_category, expected_phrase)
