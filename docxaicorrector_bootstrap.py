"""Single source of truth for the src-first import bootstrap (finding F5/R29).

Standalone entrypoints — the pytest ``conftest``, the ``scripts/*`` runners, and
the ``benchmark_projects/*`` runners — must import ``docxaicorrector`` from
``src/`` ahead of any same-named module elsewhere on ``sys.path``. Each entrypoint
adds the repo root to ``sys.path`` (so THIS module is importable) and then calls
``ensure_src_first_import_order`` instead of re-defining the helper inline; before
this consolidation the identical helper lived in seven copies.

``ensure_src_first_import_order`` accepts the roots in the same argument shapes the
former inline copies used:

* ``ensure_src_first_import_order(SRC_ROOT)`` pins only ``src`` (conftest).
* ``ensure_src_first_import_order(REPO_ROOT, SRC_ROOT)`` pins the repo root too,
  with ``src`` still searched first (the scripts and benchmark runners).
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["ensure_src_first_import_order"]


def ensure_src_first_import_order(*roots: Path) -> None:
    """Pin ``roots`` at the front of ``sys.path`` with ``src`` searched first.

    Each root is stringified, purged from ``sys.path`` (removing any pre-existing
    duplicate), then re-inserted at position 0 in argument order, so the LAST root
    passed ends up first. Calling with ``(repo_root, src_root)`` therefore yields
    ``[src_root, repo_root, ...]`` — byte-for-byte the ordering the seven inline
    copies produced.
    """
    root_strs = [str(root) for root in roots]
    purge = set(root_strs)
    sys.path[:] = [entry for entry in sys.path if entry not in purge]
    for root_str in root_strs:
        sys.path.insert(0, root_str)
