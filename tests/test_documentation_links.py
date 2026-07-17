"""Spec 026 — README/doc internal links and repo paths must resolve.

Guards against the documentation drift the audit found: README pointing at a
nonexistent module (`structure_recognition.py`) and at spec files that had moved
into docs/archive/. Checks both markdown links and backtick-quoted repo paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.static_workflow

# Docs whose internal references we own and keep current. The canonical
# validation workflow is intentionally excluded here — it references large test
# data files that are not always present on disk.
#
# Coverage is an explicit allow-list rather than a ``docs/*.md`` glob: two docs
# (``docs/ARCHIVE_INDEX.md`` and the dated ``docs/HANDOFF_2026-07-11.md``) carry
# stale references that are out of scope for this checker — ARCHIVE_INDEX points
# at owner-held monetization drafts that were never committed
# (``docs/archive/drafts/monetization1.md`` / ``monatization2.md``) and HANDOFF
# is a point-in-time snapshot naming a removed ``tests/sources/archive/`` dir.
# Add a doc here only once its in-repo references fully resolve.
DOCS_TO_CHECK = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "REAL_DOCUMENT_VALIDATION_WORKFLOW.md",
    REPO_ROOT / "AGENTS.md",
    REPO_ROOT / "docs" / "COPILOT_CLI_LOOP_USAGE.md",
    REPO_ROOT / "docs" / "WORKFLOW_AND_IMAGE_MODES.md",
    REPO_ROOT / "docs" / "LOGGING_AND_ARTIFACT_RETENTION.md",
]

_MD_LINK = re.compile(r"\]\(([^)]+)\)")
_BACKTICK = re.compile(r"`([^`]+)`")

_PATHLIKE_EXT = (".md", ".py", ".toml", ".txt", ".json", ".sh", ".ps1", ".cfg")


def _is_pathlike(token: str) -> bool:
    if not token or token != token.strip():
        return False
    if token.startswith(("http://", "https://", "mailto:", "#", ".run")):
        return False
    if any(ch in token for ch in "<>*() \t\r\n") or "::" in token or "..." in token:
        return False
    if "/" not in token:
        return False
    return token.startswith(
        ("docs/", "src/", "tests/", "scripts/", "specs/", "benchmark_projects/", ".github/", ".streamlit/")
    ) or token.endswith(_PATHLIKE_EXT)


def _candidates(doc: Path) -> set[str]:
    text = doc.read_text(encoding="utf-8")
    # Drop fenced code blocks: their contents are illustrative examples, not links.
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    found: set[str] = set()
    for raw in [*_MD_LINK.findall(text), *_BACKTICK.findall(text)]:
        token = raw.split("#", 1)[0].strip().strip("`").rstrip("/")
        if _is_pathlike(token):
            found.add(token)
    return found


def _resolves(doc: Path, token: str) -> bool:
    # Accept resolution relative to the doc's own directory OR the repo root.
    return (doc.parent / token).exists() or (REPO_ROOT / token).exists()


@pytest.mark.parametrize("doc", DOCS_TO_CHECK, ids=lambda p: p.name)
def test_doc_internal_paths_resolve(doc: Path) -> None:
    dangling = sorted(tok for tok in _candidates(doc) if not _resolves(doc, tok))
    assert not dangling, f"{doc.name} references non-existent paths: {dangling}"


def test_readme_does_not_reference_removed_structure_recognition_module() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "structure_recognition.py" not in text, (
        "README must not reference the removed structure_recognition.py module"
    )
