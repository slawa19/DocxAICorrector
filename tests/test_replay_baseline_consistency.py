"""Static guard: spec 052's replay criterion must agree with the replay evidence it cites.

Why this file exists
--------------------
An external review (Codex, gpt-5.6-sol, 2026-08-02) found spec 052's anti-regression
section demanding something the repository's own versioned evidence says is false:
"byte-identical accepted sets" and "the same accepted-operation sets as before,
minus the 1/2/0 reclassifications", measured against the June 2026 recording.
``artifacts/reader_cleanup_replay/faithful_replay_summary.json`` reports
``reproduces_recorded_accepted: false`` for all three books (9/39/6 accepted now
against 34/44/12 recorded).

The criterion was not merely unmeetable, it was **dangerous**: the divergence is
today's code correctly refusing operations that destroyed image anchors, plus a
``reclassify_role`` operation that no longer exists. Anyone who took the criterion
seriously would have been working to restore the image-anchor P0.

What this guard checks
----------------------
1. The evidence artifact still says the replay does NOT reproduce the recording —
   if that ever becomes true again, this guard is the wrong shape and says so.
2. While it says that, spec 052 does not claim the opposite, in any of the three
   wordings it used to.
3. The numbers spec 052 quotes for the divergence are the numbers in the artifact.
   This is the anti-vacuum part: without it the guard would pass on a spec that
   merely deleted the offending sentences and explained nothing.

It deliberately does not judge the surrounding prose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = REPO_ROOT / "artifacts" / "reader_cleanup_replay" / "faithful_replay_summary.json"
SPEC_PATH = REPO_ROOT / "specs" / "052-reader-cleanup-first-production-run" / "spec.md"
REPLAY_SCRIPT_PATH = REPO_ROOT / "scripts" / "run-reader-cleanup-faithful-replay.py"

pytestmark = pytest.mark.static_workflow

# The exact claims the review found. Each is a statement that the replay reproduces the
# recorded accepted set; the artifact says it does not.
_CONTRADICTED_CLAIMS = (
    "byte-identical accepted-operation sets",
    "byte-identical accepted sets",
    "the same accepted-operation sets as before",
)


def _summary() -> dict[str, dict[str, object]]:
    return dict(json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))["books"])


def _spec_text() -> str:
    return SPEC_PATH.read_text(encoding="utf-8")


def _anti_regression_section() -> str:
    """The ``## Anti-regression`` section body.

    Anchored to a heading at the start of a line: the spec also *mentions*
    ``## Anti-regression`` mid-sentence, and a plain ``str.index`` picks up the
    mention, silently widening the "section" to most of the document. That made an
    earlier version of this guard pass on a spec that still carried the withdrawn
    criterion.
    """
    text = _spec_text()
    start = re.search(r"^## Anti-regression\s*$", text, flags=re.MULTILINE)
    assert start is not None, "spec 052 has no `## Anti-regression` heading of its own."
    end = re.search(r"^## Changelog\s*$", text[start.end():], flags=re.MULTILINE)
    assert end is not None, "spec 052 has no `## Changelog` heading after `## Anti-regression`."
    return text[start.end(): start.end() + end.start()]


def _anti_regression_criteria() -> str:
    """The numbered criteria only, without the ``###`` prose that explains them.

    The explanation is allowed — required, even — to quote the withdrawn criterion
    verbatim; that is how the next reader learns why it was withdrawn rather than
    re-deriving it. What must not come back is the demand itself.
    """
    section = _anti_regression_section()
    explanation = section.find("\n### ")
    return section if explanation == -1 else section[:explanation]


def test_replay_summary_still_reports_the_divergence_this_guard_is_about() -> None:
    """Anti-vacuum: if the replay ever reproduced the recording, rewrite this guard."""
    assert SUMMARY_PATH.is_file(), f"{SUMMARY_PATH} is the versioned replay evidence; it is missing."
    diverging = {
        book: data
        for book, data in _summary().items()
        if not data["reproduces_recorded_accepted"]
    }
    assert diverging, (
        "faithful_replay_summary.json now reports reproduces_recorded_accepted=true for every "
        "book. That would be a genuine change in the world, and spec 052's anti-regression "
        "section plus this guard both need rewriting rather than quietly passing."
    )


def test_spec_052_does_not_demand_reproducing_the_recorded_accepted_set() -> None:
    criteria = _anti_regression_criteria()
    offenders = [claim for claim in _CONTRADICTED_CLAIMS if claim in criteria]
    assert not offenders, (
        "specs/052-reader-cleanup-first-production-run/spec.md still requires the replay to "
        f"reproduce the recorded accepted set ({offenders!r}), while "
        "artifacts/reader_cleanup_replay/faithful_replay_summary.json reports "
        "reproduces_recorded_accepted=false for all three books. The divergence is today's "
        "code correctly refusing operations that destroyed image anchors, plus the removed "
        "reclassify_role operation — so this criterion is an instruction to restore the "
        "image-anchor P0. Measure stability against the committed summary (the previous state "
        "of the CODE) instead."
    )


def test_replay_summary_says_whether_toc_blocks_reached_the_model() -> None:
    """The tool must measure what it claims.

    ``toc_like_block_count`` was documented as "the size of the pass's blind spot",
    i.e. blocks the model never sees. With ``keep_toc`` true — the default, and what
    these runs used — ``_select_cleanup_blocks`` returns every block: the ``toc_like``
    ones are serialised into the payload and paid for in tokens, and are refused only
    later, by ``_build_protected_block_ids``. The count is real; the saving was not.
    ``tests/test_reader_cleanup_mvp.py`` pins the behaviour; this pins the reporting.
    """
    for book, data in sorted(_summary().items()):
        assert "toc_like_blocks_sent_to_model" in data, (
            f"{book}: the replay summary reports toc_like_block_count without saying "
            "whether those blocks reached the model. keep_toc=True (the default) sends "
            "them and protects them only at validation, so a bare count reads as a "
            "token saving that is never made. Re-run "
            "scripts/run-reader-cleanup-faithful-replay.py to refresh the summary."
        )

    script = REPLAY_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "size of the pass's blind spot" not in script, (
        "scripts/run-reader-cleanup-faithful-replay.py again describes toc_like blocks "
        "as a blind spot the model never sees. They are sent under keep_toc=True."
    )


def test_spec_052_quotes_the_real_divergence_numbers() -> None:
    """The correction has to carry the evidence, not just delete the false claim."""
    section = _anti_regression_section()
    for book, data in sorted(_summary().items()):
        accepted = int(data["accepted_count"])  # type: ignore[arg-type]
        recorded = int(data["recorded_accepted_count"])  # type: ignore[arg-type]
        row = re.compile(
            rf"^\|\s*{re.escape(book)}\s*\|\s*{accepted}\s*\|\s*{recorded}\s*\|\s*$",
            re.MULTILINE,
        )
        assert row.search(section), (
            f"spec 052's anti-regression section does not carry the measured divergence for "
            f"{book!r}: expected a table row '| {book} | {accepted} | {recorded} |' matching "
            "artifacts/reader_cleanup_replay/faithful_replay_summary.json. Re-run "
            "scripts/run-reader-cleanup-faithful-replay.py and quote what it reports — a "
            "criterion that says 'the recording is not the baseline' without showing by how "
            "much is an assertion, not evidence."
        )
