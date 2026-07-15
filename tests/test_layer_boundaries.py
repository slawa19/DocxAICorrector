"""Spec 027 — the processing/runtime/domain layers must not depend on ui.

Pins the layering so the processing→ui cycle (PreparedRunContext + preparation
orchestration formerly living in ui.application_flow) cannot reappear.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "docxaicorrector"

pytestmark = pytest.mark.static_workflow


def _imports_ui(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "docxaicorrector.ui" or a.name.startswith("docxaicorrector.ui.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "docxaicorrector.ui" or mod.startswith("docxaicorrector.ui."):
                return True
    return False


def test_lower_layers_do_not_import_ui() -> None:
    offenders = [
        str(path.relative_to(SRC)).replace("\\", "/")
        for path in SRC.rglob("*.py")
        if path.parent.name != "ui" and "/ui/" not in path.as_posix()
        if _imports_ui(path)
    ]
    assert not offenders, f"non-ui modules import docxaicorrector.ui (layering violation): {offenders}"


def test_processing_core_imports_without_ui_package() -> None:
    # Importing the processing core (including PreparedRunContext + preparation
    # orchestration) must not pull the ui package. A future FastAPI backend/worker
    # relies on this.
    probe = (
        "import docxaicorrector.processing.processing_service;"
        "import docxaicorrector.processing.application_flow;"
        "import sys;"
        "ui=[m for m in sys.modules if m=='docxaicorrector.ui' or m.startswith('docxaicorrector.ui.')];"
        "assert not ui, ui;"
        "print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
        env={**__import__("os").environ, "PYTHONPATH": str(SRC.parent)},
    )
    assert result.returncode == 0, f"processing core pulled ui or failed to import:\n{result.stderr[-800:]}"
    assert "OK" in result.stdout


def test_flow_message_defaults_match_ru_catalog() -> None:
    from docxaicorrector.processing import application_flow as paf

    ru = json.loads((SRC / "ui" / "locales" / "ru.json").read_text(encoding="utf-8"))
    expected = {key: ru[key] for key in paf._DEFAULT_FLOW_MESSAGES}
    assert paf._DEFAULT_FLOW_MESSAGES == expected, (
        "processing default flow messages drifted from the ru catalog; keep them byte-identical"
    )
