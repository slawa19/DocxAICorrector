"""Which code built an artifact: the git head of the checkout (spec 073 FR-007, research R18).

Moved here from the real-document runner (``tests/artifacts/real_document_pipeline/run_lietaer_validation.py``,
``_safe_git_head`` / ``_resolve_git_pointer_path`` / ``_read_git_head_from_files``) so the product and the runner read
the version through ONE copy: the book file for the narration tool writes it as ``producer.version``. Outside a git
checkout the answer is ``None`` -- never an invented "unknown".
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_GIT_SHORT_HEAD_LENGTH = 7
_WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^([A-Za-z]):[\\/](.*)$")
_GIT_OBJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")


def resolve_git_head(project_root: Path | None = None) -> str | None:
    """The short SHA of the commit checked out at ``project_root`` (default: this code's checkout), or ``None``."""

    root = PROJECT_ROOT if project_root is None else Path(project_root)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        )
    except Exception:
        return _read_git_head_from_files(root)
    return result.stdout.strip() or _read_git_head_from_files(root)


def _resolve_git_pointer_path(raw: str, *, relative_to: Path) -> Path:
    """A path written by git into a pointer file (``gitdir:``, ``commondir``).

    A side worktree created from Windows records its ``gitdir`` as a Windows path
    (``D:/Work/…/.git/worktrees/<name>``), which a Linux process reads as RELATIVE. Under
    WSL the drive maps to ``/mnt/<drive>/``, the documented mount of this runtime.
    """

    drive_path = _WINDOWS_DRIVE_PATH_PATTERN.match(raw)
    if drive_path is not None and os.name != "nt":
        drive, rest = drive_path.groups()
        return Path("/mnt") / drive.lower() / rest.replace("\\", "/")
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (relative_to / candidate)


def _read_git_head_from_files(project_root: Path) -> str | None:
    """The checked-out commit read straight from the git files, no git subprocess.

    Fallback for ``resolve_git_head``: under WSL, ``git`` cannot open a side worktree whose
    ``.git`` FILE points at a Windows path (``AGENTS.md``, «Боковые worktree для агентов»),
    and the 2026-11-07 run summaries recorded ``git_head=None`` — a run whose commit nobody
    can name. ``.git`` (directory, or file with ``gitdir:``) → ``HEAD`` → the ref file in
    the common dir, or ``packed-refs``. Any unreadable step returns ``None``, as before.
    """

    try:
        dot_git = project_root / ".git"
        if dot_git.is_file():
            pointer = dot_git.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir:"):
                return None
            git_dir = _resolve_git_pointer_path(pointer[len("gitdir:") :].strip(), relative_to=project_root)
        elif dot_git.is_dir():
            git_dir = dot_git
        else:
            return None
        common_dir = git_dir
        commondir_file = git_dir / "commondir"
        if commondir_file.is_file():
            common_dir = _resolve_git_pointer_path(
                commondir_file.read_text(encoding="utf-8").strip(), relative_to=git_dir
            )
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head[len("ref:") :].strip()
            object_id = None
            for ref_root in (git_dir, common_dir):
                ref_file = ref_root / ref
                if ref_file.is_file():
                    object_id = ref_file.read_text(encoding="utf-8").strip()
                    break
            if object_id is None:
                packed_refs = common_dir / "packed-refs"
                if packed_refs.is_file():
                    for line in packed_refs.read_text(encoding="utf-8").splitlines():
                        parts = line.split()
                        if len(parts) == 2 and parts[1] == ref:
                            object_id = parts[0]
                            break
        else:
            object_id = head
    except OSError:
        return None
    if not object_id or not _GIT_OBJECT_ID_PATTERN.match(object_id):
        return None
    return object_id[:_GIT_SHORT_HEAD_LENGTH]


__all__ = ["PROJECT_ROOT", "resolve_git_head"]
