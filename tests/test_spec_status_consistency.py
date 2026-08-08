"""Static guard: spec ``Status:`` headers must be honest, must agree with the
navigation document ``docs/WHERE_WE_ARE.md``, and must not say "not started" about
work that is already in ``main``.

Why this file exists
--------------------
On 2026-07-31 a session planned the next step from a document that said "next up:
the UI slice" — the UI had in fact shipped a month earlier (spec 013). The root
cause was systemic, not a one-off typo: the ``Status:`` field in
``specs/NNN-*/spec.md`` had been drifting for months (12 specs were marked as not
done while their code was already merged; two literally said "merging is not
recommended"), and nothing checked it. ``tests/test_documentation_links.py`` only
proves links resolve — it says nothing about whether the words are still true.

This guard now DOES look at git (changed 2026-08-07)
----------------------------------------------------
Until 2026-08-07 this module deliberately never touched git, and said so here. The
reasoning was that ``actions/checkout@v4`` in ``.github/workflows/ci.yml`` ran with
the default ``fetch-depth: 1``, so CI had a shallow clone: any history query would
come back empty and a git-based guard would go *vacuously green*. That reasoning
described a fixable CI setting as if it were a law of nature, and the price was
paid twice in three days:

* **spec 055** — status ``MEASURED``, work merged in PR #43/#44, and
  ``docs/WHERE_WE_ARE.md`` kept it under "Что открыто" with the words
  "Измерено 2026-08-04, не начато" for two days. Found by an independent review,
  not by a test.
* **spec 056** — the ``Status:`` line read ``READY — diagnosed and measured
  2026-08-04/05, not started.`` while the work had been merged by PR #41
  (``5393db2``) two days earlier. The two guards below were both green throughout,
  *by construction*: the status said "open", the spec was legitimately listed as
  open work, and the documents lied in agreement.

So the shallow-clone trap is now handled where it belongs — ``fetch-depth: 0`` on
the ``tests`` job in ``.github/workflows/ci.yml``, and
``test_git_history_is_reachable`` below, which FAILS loudly (never skips) when the
history is not there. A guard that quietly passes itself when its evidence is
missing is the very defect this file was written against.

Note on Constitution VII (no word lists)
----------------------------------------
Constitution VII forbids detection keyed on a vocabulary of *content* — words
taken from the books being processed. The phrases matched below ("not started",
"не начато") are not content: they are the repository's own **status metadata**,
the same register as ``PLANNED`` / ``DONE`` in the controlled vocabulary this file
has always enforced. Keying on how a document states its own progress is exactly
what a documentation guard is for; keying on how a book states its own headings is
what VII prohibits. Do not mistake one for the other.

What it enforces
----------------
1. Every ``specs/NNN-*/spec.md`` has a parseable status line whose value is in the
   controlled vocabulary below (the vocabulary was derived from what the specs
   actually say — specs are not rewritten to fit it).
2. Every spec whose status means "work is still OPEN" is mentioned in the
   "Что открыто" section of ``docs/WHERE_WE_ARE.md``.
3. No live document of this repository claims a spec is "not started" when commits
   referencing that spec have already changed ``src/``, ``tests/``, ``scripts/`` or
   ``resources/`` in the reachable history.

Rule 2's reverse direction is deliberately NOT enforced: the navigation section
also mentions closed specs as context (e.g. "spec 049 showed what happens
when...") and that is legitimate. Closing that asymmetry was considered and
rejected as the answer to the two incidents above — it would have caught 055 (a
closed spec listed as open) and missed 056 entirely (an open spec, honestly listed
as open, whose work had nevertheless landed). Rule 3 catches both, and is
deliberately narrow enough to catch little else.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from functools import lru_cache
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


def _status_block(spec_path: Path) -> str:
    """The whole ``Status:`` paragraph — the status line plus its wrapped continuation.

    The verdict is one line, but the sentence that justifies it routinely wraps over
    several ("**READY — diagnosed and measured 2026-08-04/05, not started.** All
    numbers below come from..."). The claim a reader acts on is the paragraph, not
    the first physical line, so the "not started" guard reads the paragraph. It stops
    at the blank line: further down a spec, "X was never started" is ordinary prose
    about a sub-decision and none of this guard's business.
    """
    lines = spec_path.read_text(encoding="utf-8").splitlines()[:_HEADER_SCAN_LINES]
    for index, line in enumerate(lines):
        if _STATUS_LINE.match(line):
            block = [line]
            for following in lines[index + 1 :]:
                if not following.strip():
                    break
                block.append(following)
            return "\n".join(block)
    return ""


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


# --------------------------------------------------------------------------- #
# "Not started" claims, checked against git
# --------------------------------------------------------------------------- #
# A document asserts that nothing has happened yet. Both languages the repository
# writes in are covered because both incidents used one each: spec 056's header said
# "not started", docs/WHERE_WE_ARE.md said "не начато" about spec 055.
#
# This is status metadata, not content vocabulary — see the note on Constitution VII
# in the module docstring.
_NOT_STARTED_CLAIM = re.compile(
    r"not\s+(?:yet\s+)?(?:started|begun)"
    r"|\bне\s+нач(?:ат|ина)\w*",
    re.IGNORECASE,
)

# Reported speech is marked by quotation marks, and every document that CORRECTED one
# of these incidents has to be able to say what the wrong text used to read — spec
# 056's header now carries `This line said "not started" until 2026-08-07`, and
# docs/WHERE_WE_ARE.md carries «не начато» three times for the same reason. A phrase
# inside quotes is a citation of a past claim, not a claim. This is the whole
# assertion/quotation distinction: it is structural (punctuation), not a list of
# excuse words, and the fix it asks for is one a writer can guess — put the quoted
# past wording in quotes.
_QUOTATION = re.compile(
    r"«[^»\n]*»"
    r'|"[^"\n]*"'
    r"|“[^”\n]*”"
    r"|„[^“\n]*“"
    r"|‘[^’\n]*’"
    r"|`[^`\n]*`"
)

# "Спека 055", "спеки 049", "spec 050", "specs/056-": how prose names a spec.
_SPEC_NUMBER_IN_PROSE = re.compile(
    r"(?:specs/|(?:spec|спек\w*)\s*[`*_]*)(\d{3})\b",
    re.IGNORECASE,
)

# A file changed by a commit that means WORK, as opposed to writing the spec that
# proposes the work. Without this distinction the rule is unusable: creating
# `specs/059-foo/spec.md` with an honest "PLANNED — not started" also creates a
# commit referencing 059 (and usually touches docs/WHERE_WE_ARE.md in the same
# breath), so a naive "any commit at all" rule would fail CI on the very first push
# of every new spec. Measured on this repository's 553 non-merge commits: with this
# filter, 9 of 58 specs have no work commits and may legitimately say "not started";
# without it, all 58 have one and the rule refuses everything.
_WORK_PATH_PREFIXES = ("src/", "tests/", "scripts/", "resources/")

# Anti-vacuum floor for the reachable history. A shallow `actions/checkout@v4` clone
# has exactly 1 commit; this repository passed 600 long ago. Set low enough that a
# legitimately truncated clone is the only thing that trips it.
_MIN_REACHABLE_COMMITS = 200

# Specs whose work is merged and cannot become un-merged. They are the fixed point
# the git half is proved live against: if the history query silently returns
# nothing, or the reference matching rots, these go empty and the anti-vacuum test
# fails instead of the whole guard passing for free.
_SPECS_WITH_MERGED_WORK_ANCHORS = ("054", "055", "056")

# Documentation that is dated and historical by nature. `docs/archive/` is declared
# non-binding by AGENTS.md ("документ архивный, расхождение с ним ничего не значит"),
# and the archived plans there legitimately carry "Status: not started" lines frozen
# in 2026-06. Judging them would be judging the past.
_EXCLUDED_DOC_DIRS = ("docs/archive/",)

_HISTORY_FIX_HINT = (
    "Fix: `.github/workflows/ci.yml` must check the repository out with\n"
    "    - uses: actions/checkout@v4\n"
    "      with:\n"
    "        fetch-depth: 0\n"
    "for any job that runs this file (the `tests` job does), and any container that\n"
    "mirrors CI must copy `.git` along with the tree (see scripts/docker-ci-parity.sh).\n"
    "Do NOT make this test skip itself when the history is missing: a guard that\n"
    "passes without its evidence is the exact defect this module was written against."
)


class GitHistoryUnavailable(RuntimeError):
    """The reachable git history could not be read — never swallowed, always fatal."""


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:  # git not installed at all
        raise GitHistoryUnavailable(f"could not run git: {error}") from error
    if completed.returncode != 0:
        raise GitHistoryUnavailable(
            f"`git {' '.join(args)}` failed with exit code {completed.returncode}:\n"
            f"{completed.stderr.strip()}"
        )
    return completed.stdout


def _commit_references_spec(spec_dir_name: str, message: str) -> bool:
    """Does this commit message name the spec ``NNN-slug``?

    Covers every form the repository actually uses: ``feat(055): ...``,
    ``fix(056 P0-3): ...``, ``docs(spec 058): ...``, ``spec 043``, ``спека 055``,
    ``specs/050-...``, and the branch name inside a merge subject (``/056-``).
    """
    number = spec_dir_name[:3]
    patterns = (
        rf"specs/{number}-",
        re.escape(spec_dir_name),
        rf"\(\s*(?:spec\s+)?{number}\b",
        rf"(?:spec|спек\w*)\s*[`*_]*{number}\b",
        rf"/{number}-",
    )
    return any(re.search(pattern, message, re.IGNORECASE) for pattern in patterns)


@lru_cache(maxsize=1)
def _reachable_commits() -> tuple[tuple[str, str, tuple[str, ...]], ...]:
    """``(sha, message, changed_paths)`` for every non-merge commit reachable from HEAD.

    HEAD, not ``main``: on a pull request ``actions/checkout@v4`` builds a merge of
    the branch into its base, so HEAD's ancestry *is* main's history plus whatever
    the branch adds. A branch that lands work and simultaneously writes "not started"
    about it is the same defect and should fail on the branch, not after the merge.
    Merge commits are skipped — they carry no diff of their own and their content is
    already present in the commits they merge.
    """
    raw = _git(
        "log", "--no-merges", "--format=%x00%H%x01%B%x01", "--name-only", "HEAD"
    )
    commits: list[tuple[str, str, tuple[str, ...]]] = []
    for chunk in raw.split("\x00"):
        if not chunk.strip():
            continue
        parts = chunk.split("\x01")
        if len(parts) < 3:
            continue
        sha, message, paths = parts[0], parts[1], parts[2]
        commits.append(
            (sha.strip()[:8], message, tuple(line for line in paths.splitlines() if line))
        )
    return tuple(commits)


def commit_subject(message: str) -> str:
    """The first line of a commit message, or ``""``."""
    stripped = message.strip()
    return stripped.splitlines()[0] if stripped else ""


@lru_cache(maxsize=1)
def _work_commits_by_spec() -> dict[str, tuple[str, ...]]:
    """Spec number -> ``sha subject`` of every commit that DID work on it."""
    index: dict[str, list[str]] = {}
    for spec_path in _spec_files():
        spec_dir_name = spec_path.parent.name
        found: list[str] = []
        for sha, message, paths in _reachable_commits():
            if not any(path.startswith(_WORK_PATH_PREFIXES) for path in paths):
                continue
            subject = commit_subject(message)
            # The SUBJECT decides attribution, not the whole message. A body is prose
            # and mentions other specs for context — including to deny a relation
            # ("this work does not belong to spec 059"), which the matcher cannot read
            # as a denial. That false credit is not hypothetical: it failed CI twice on
            # 2026-08-08 and is why this narrowing exists.
            # Measured over the whole history at that date: specs 054-058 have 47
            # commits naming them in the subject and ZERO naming them only in the body,
            # so nothing true is lost. Escape hatch (c) in the failure message points
            # here on purpose.
            if not _commit_references_spec(spec_dir_name, subject):
                continue
            found.append(f"{sha} {subject}")
        index[spec_dir_name[:3]] = found
    return {number: tuple(found) for number, found in index.items()}


def asserts_not_started(text: str) -> str | None:
    """The first *asserted* "not started" phrase in ``text``, or ``None``.

    A match inside quotation marks is a quotation of a past claim ("this line said
    'not started' until 2026-08-07") and is not an assertion.
    """
    quoted = [match.span() for match in _QUOTATION.finditer(text)]
    for match in _NOT_STARTED_CLAIM.finditer(text):
        start, end = match.span()
        if any(left <= start and end <= right for left, right in quoted):
            continue
        return match.group(0)
    return None


def spec_numbers_in(text: str) -> list[str]:
    """Every spec number this prose names, in order of first appearance."""
    seen: list[str] = []
    for match in _SPEC_NUMBER_IN_PROSE.finditer(text):
        number = match.group(1)
        if number not in seen:
            seen.append(number)
    return seen


def not_started_claims_about_merged_work(
    text: str,
    attributed_to: Sequence[str],
    specs_with_merged_work: Iterable[str],
) -> list[tuple[str, str]]:
    """``(spec_number, offending_phrase)`` for every illegal claim in ``text``.

    Pure: the git half arrives as ``specs_with_merged_work``, so the rule can be
    exercised on synthetic prose without touching a real file. ``attributed_to`` is
    who the text is about — the spec's own number for a spec header, the numbers
    named in the paragraph for a navigation document.
    """
    phrase = asserts_not_started(text)
    if phrase is None:
        return []
    merged = set(specs_with_merged_work)
    return [(number, phrase) for number in attributed_to if number in merged]


def _live_documents() -> list[Path]:
    """Every markdown document of the repository that speaks in the present tense."""
    candidates = sorted(REPO_ROOT.glob("*.md")) + sorted(
        (REPO_ROOT / "docs").rglob("*.md")
    )
    return [
        path
        for path in candidates
        if not path.relative_to(REPO_ROOT).as_posix().startswith(_EXCLUDED_DOC_DIRS)
    ]


def _paragraphs(text: str) -> list[tuple[int, str]]:
    """``(first line number, paragraph)`` for each blank-line-separated block."""
    blocks: list[tuple[int, str]] = []
    current: list[str] = []
    start = 1
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not current:
                start = number
            current.append(line)
        elif current:
            blocks.append((start, "\n".join(current)))
            current = []
    if current:
        blocks.append((start, "\n".join(current)))
    return blocks


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
    documents = _live_documents()
    assert WHERE_WE_ARE_PATH in documents and len(documents) >= 10, (
        f"only {len(documents)} live markdown documents found (WHERE_WE_ARE.md "
        f"{'in' if WHERE_WE_ARE_PATH in documents else 'MISSING from'} the set) — the "
        "'not started' guard sweeps this list, and an empty or truncated list makes it "
        "vacuous. Check _live_documents(): it reads the repository root and docs/, "
        "minus the historical trees in _EXCLUDED_DOC_DIRS."
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


# --------------------------------------------------------------------------- #
# Guard: "not started" versus what is actually in the history
# --------------------------------------------------------------------------- #
def test_git_history_is_reachable() -> None:
    """Anti-vacuum: the guard below must FAIL, never skip, when git is unreadable.

    A shallow ``actions/checkout@v4`` clone (the default, ``fetch-depth: 1``) has one
    commit and no history, so every query would come back empty and the guard would
    pass having checked nothing. That is precisely the false green this whole module
    exists against, so the missing evidence is reported as a failure with the fix.
    """
    try:
        depth = int(_git("rev-list", "--count", "HEAD").strip())
        shallow = _git("rev-parse", "--is-shallow-repository").strip() == "true"
        anchors = {
            number: _work_commits_by_spec().get(number, ())
            for number in _SPECS_WITH_MERGED_WORK_ANCHORS
        }
    except GitHistoryUnavailable as error:
        pytest.fail(
            f"the git history is not reachable from {REPO_ROOT}, so the "
            "'not started' guard below cannot check anything:\n"
            f"  {error}\n\n" + _HISTORY_FIX_HINT
        )

    problems: list[str] = []
    if shallow:
        problems.append("the clone is shallow (`git rev-parse --is-shallow-repository` = true)")
    if depth < _MIN_REACHABLE_COMMITS:
        problems.append(
            f"only {depth} commits are reachable from HEAD "
            f"(expected at least {_MIN_REACHABLE_COMMITS})"
        )
    empty = [number for number, commits in anchors.items() if not commits]
    if empty:
        problems.append(
            "no work commits were found for specs "
            + ", ".join(empty)
            + " — their work is merged and cannot become un-merged, so either the "
            "history is truncated or _commit_references_spec has stopped matching "
            "this repository's commit-message conventions"
        )

    assert not problems, (
        "the 'not started' guard would run vacuously:\n  - "
        + "\n  - ".join(problems)
        + "\n\n"
        + _HISTORY_FIX_HINT
    )


def test_no_live_document_calls_merged_work_not_started() -> None:
    """No document may say "not started" about a spec whose work is in the history.

    This is the rule the two 2026-08 incidents needed and neither existing guard
    could express: spec 056's ``Status:`` line read "not started" two days after PR
    #41 merged its code, and ``docs/WHERE_WE_ARE.md`` said "не начато" about spec
    055 two days after PR #43/#44 merged its code. In both cases the file and the
    history disagreed, and only the history was checkable.
    """
    with_work = {number for number, commits in _work_commits_by_spec().items() if commits}
    offences: list[str] = []

    # Half one: a spec's own header, about itself.
    for spec_path in _spec_files():
        number = spec_path.parent.name[:3]
        block = _status_block(spec_path)
        for _, phrase in not_started_claims_about_merged_work(block, [number], with_work):
            offences.append(
                f"- specs/{spec_path.parent.name}/spec.md, Status: block says "
                f"{phrase!r}, but {len(_work_commits_by_spec()[number])} commit(s) "
                f"have already done work on it, e.g. {_work_commits_by_spec()[number][0]}"
            )

    # Half two: every live document, paragraph by paragraph, about the specs it names.
    for document in _live_documents():
        relative = document.relative_to(REPO_ROOT).as_posix()
        for line_number, paragraph in _paragraphs(document.read_text(encoding="utf-8")):
            named = spec_numbers_in(paragraph)
            for number, phrase in not_started_claims_about_merged_work(
                paragraph, named, with_work
            ):
                offences.append(
                    f"- {relative}:{line_number} says {phrase!r} in a paragraph about "
                    f"spec {number}, whose work is already in the history, e.g. "
                    f"{_work_commits_by_spec()[number][0]}"
                )

    assert not offences, (
        "a document claims work has not started when the history says otherwise:\n"
        + "\n".join(offences)
        + "\n\nFix ONE of these, whichever is true:\n"
        "  (a) the work HAS landed -> rewrite the sentence to say what landed, and "
        "correct the spec's `Status:` line. Check with\n"
        "        git log --oneline --no-merges HEAD --grep='(NNN' --grep='spec NNN'\n"
        "  (b) you are QUOTING what a document used to say wrongly (the corrections "
        "for specs 055 and 056 both have to) -> put the old wording in quotation "
        "marks: «не начато», \"not started\". Quoted text is read as a citation, not "
        "as a claim.\n"
        "  (c) the commits are not about this spec at all -> the reference matching "
        "in _commit_references_spec is too loose; narrow it and say why here."
    )


@pytest.mark.parametrize("number", ["050", "054", "056"])
def test_open_specs_with_merged_work_are_legitimate_and_not_flagged(number: str) -> None:
    """The rule must accept the three shapes that look guilty and are not.

    Without these, a rule that simply refused every open spec with commits would
    look green and be useless:

    * **054** — ``IN PROGRESS`` with 15 work commits. Open work that has visibly
      started is the normal case, not a defect.
    * **050** — ``DEFERRED``, parked by owner decision, with a work commit behind
      it. Parked is not "not started".
    * **056** — ``IN PROGRESS`` after the 2026-08-07 correction. Its header still
      contains the words "not started", now inside quotation marks because it
      records what the header used to say. That is the one case where the
      assertion/quotation distinction carries the whole verdict.
    """
    spec_path = next(path for path in _spec_files() if path.parent.name.startswith(number))
    work_commits = _work_commits_by_spec()[number]
    assert work_commits, (
        f"spec {number} is one of this test's fixtures precisely because its work IS "
        "in the history; finding none means the git half went blind."
    )
    category, phrase = classify_status(_raw_status_line(spec_path) or "")
    assert category == "open", (
        f"spec {number} was chosen as a fixture for an OPEN spec with merged work; "
        f"its status now classifies as {category} ({phrase!r}). Pick another fixture "
        "of the same shape rather than deleting the case."
    )
    with_work = {code for code, commits in _work_commits_by_spec().items() if commits}
    claims = not_started_claims_about_merged_work(
        _status_block(spec_path), [number], with_work
    )
    assert claims == [], (
        f"spec {number} must NOT be flagged — it never claims the work has not "
        f"started. Flagged on: {claims}"
    )


def test_a_not_started_claim_about_merged_work_is_flagged() -> None:
    """The mutation this guard exists for, run against real history, on synthetic text.

    Spec 056's header is reconstructed as it actually read on 2026-08-06 — the day
    before the drift was found — and fed to the rule directly, so the case is proved
    without editing anything under ``specs/``. The counter-case below it is the same
    sentence with the phrase quoted, which must not fire; otherwise the corrected
    documents could never describe what they corrected.
    """
    with_work = {number for number, commits in _work_commits_by_spec().items() if commits}
    assert "056" in with_work, "fixture precondition: spec 056's work is in the history"

    as_it_read = (
        "**Status**: **READY — diagnosed and measured 2026-08-04/05, not started.** "
        "All numbers below come from the first audiobook run."
    )
    assert not_started_claims_about_merged_work(as_it_read, ["056"], with_work) == [
        ("056", "not started")
    ]

    as_where_we_are_read = (
        "**Спека 055 — мост PDF→DOCX выбрасывает то, что импортёр измерил. "
        "Измерено 2026-08-04, не начато.**"
    )
    assert not_started_claims_about_merged_work(
        as_where_we_are_read, spec_numbers_in(as_where_we_are_read), with_work
    ) == [("055", "не начато")]

    as_corrected = (
        "**Status**: **IN PROGRESS (2026-08-05) — the change landed in `main` via "
        'PR #41.** This line said "not started" until 2026-08-07.'
    )
    assert not_started_claims_about_merged_work(as_corrected, ["056"], with_work) == []


def test_a_not_started_claim_about_a_spec_with_no_work_is_allowed() -> None:
    """A brand-new spec that says "not started" and means it must stay green.

    Nine of this repository's specs have no work commits behind them. Writing
    ``Status: PLANNED — not started`` in a spec nobody has begun is honest, and a
    guard that failed on it would be uninstallable — every new spec would break CI
    on its first push.
    """
    header = "**Status**: **PLANNED — not started.**"
    assert not_started_claims_about_merged_work(header, ["059"], {"054", "055", "056"}) == []


def test_work_is_credited_by_the_commit_subject_not_the_body() -> None:
    """A spec number in the BODY of a commit is not a claim of work on that spec.

    A subject follows the convention (``feat(055):``, ``fix(056 P0-3):``,
    ``docs(spec 058):``) and is where work announces itself. A body is prose, and
    prose names other specs for context — including to DENY a relation. The matcher
    cannot read a denial, so crediting the body produced a false positive that failed
    CI twice on 2026-08-08: a commit whose body said "this work does not belong to
    spec 059" was recorded as work on spec 059, against a spec whose status honestly
    said "не начат".

    Measured before narrowing: specs 054-058 carry 47 commits naming them in the
    subject and ZERO naming them only in the body, so no true attribution is lost.
    """
    spec_dir = "059-verdict-never-reaches-the-screen"
    body_only = (
        "fix(ui): a setting change asks before it destroys the paid result\n"
        "\n"
        "Работа defect-driven; к спеке 059 она не относится.\n"
    )
    # The whole message DOES name it — which is exactly why the caller must not read it.
    assert _commit_references_spec(spec_dir, body_only)
    assert not _commit_references_spec(spec_dir, commit_subject(body_only))

    # Anti-vacuum: narrowing must not disable attribution. A subject that names the
    # spec is still credited, in every shape the repository actually uses.
    for subject in (
        "feat(059 E): one bad paragraph stops taking nine good ones with it",
        "docs(spec 059): the ladder and the invariant",
        "Merge pull request #59 from slawa19/docs/059-honesty-channel-spec",
    ):
        assert _commit_references_spec(spec_dir, commit_subject(subject + "\n\nbody\n"))


def test_the_attribution_itself_reads_only_the_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    """The caller, not just the matcher, must ignore the body.

    The test above pins the formula; this one pins that ``_work_commits_by_spec``
    actually applies it. Without this, reverting the caller to the whole message
    would leave the suite green — the real history happens to contain no body-only
    reference today, so a test over real data would pass vacuously.
    """
    synthetic = (
        ("aaaaaaaa", "fix(ui): unrelated work\n\nк спеке 059 она не относится\n", ("src/a.py",)),
        ("bbbbbbbb", "feat(059): the real work\n\nbody\n", ("src/b.py",)),
    )
    monkeypatch.setattr(sys.modules[__name__], "_reachable_commits", lambda: synthetic)
    _work_commits_by_spec.cache_clear()
    try:
        credited = _work_commits_by_spec().get("059", ())
    finally:
        _work_commits_by_spec.cache_clear()

    assert [entry.split(" ", 1)[0] for entry in credited] == ["bbbbbbbb"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # The two sentences that actually shipped the defect.
        ("READY — diagnosed and measured 2026-08-04/05, not started.", "not started"),
        ("Измерено 2026-08-04, не начато.", "не начато"),
        ("PLANNED — not yet started", "not yet started"),
        ("Работа не начиналась", "не начиналась"),
        ("The refactor has not begun.", "not begun"),
        ("Спека не начата, и это правда.", "не начата"),
        # Quotation of a past claim — every corrected document needs these to pass.
        ('This line said "not started" until 2026-08-07.', None),
        ("Этот раздел до 2026-08-07 утверждал «не начато», хотя работа была влита.", None),
        ("ЗАКРЫТА со статусом `MEASURED` 2026-08-05/06, а не «не начата».", None),
        ("Статус спеки 055 двое суток утверждал «не начато» при уже влитой работе.", None),
        # Ordinary prose that must not be mistaken for a progress claim.
        ("IN PROGRESS — step 0 done on 2026-08-04", None),
        ("DEFERRED — parked by owner decision, with no date.", None),
        ("Начато 2026-08-04 и закончено 2026-08-06.", None),
    ],
)
def test_not_started_detector_separates_assertion_from_quotation(
    text: str, expected: str | None
) -> None:
    assert asserts_not_started(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**Спека 055 — мост PDF→DOCX.**", ["055"]),
        ("Прецедент тот же, что у спеки 049", ["049"]),
        ("see specs/056-marker-contract-unsatisfiable/spec.md", ["056"]),
        ("spec 050 showed what happens", ["050"]),
        ("спеки 017 и спека 054 обе открыты", ["017", "054"]),
        # A bare number is not a spec reference: dates and counts are everywhere.
        ("33 ложных повышения из 33 на 2026-08-05", []),
    ],
)
def test_spec_number_extraction_reads_prose_references(
    text: str, expected: list[str]
) -> None:
    assert spec_numbers_in(text) == expected


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
