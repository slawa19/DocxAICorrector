"""Spec 025 — pyproject.toml is the single source of dependency truth.

requirements.txt is the concrete install set used by scripts/setup-wsl.sh and the
CI jobs; it must not drift from pyproject. These guards catch the class of bug
where a runtime import (e.g. `anthropic`) lives only in requirements.txt and a
wheel/`pip install .` therefore fails at runtime.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.static_workflow


def _normalize(name: str) -> str:
    # PEP 503-ish normalization for comparison (case- and separator-insensitive).
    return re.split(r"[<>=!~; \[]", name.strip(), maxsplit=1)[0].strip().lower().replace("_", "-")


def _requirements_packages() -> set[str]:
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    packages: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        packages.add(_normalize(line))
    return packages


def _pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _pyproject_runtime() -> set[str]:
    return {_normalize(dep) for dep in _pyproject()["project"]["dependencies"]}


def _pyproject_all() -> set[str]:
    data = _pyproject()
    names = set(_pyproject_runtime())
    for group in data["project"].get("optional-dependencies", {}).values():
        names.update(_normalize(dep) for dep in group)
    return names


def test_anthropic_is_a_declared_runtime_dependency() -> None:
    # anthropic is imported at runtime in core/config.py; it must be an install
    # dependency, not requirements-only.
    assert "anthropic" in _pyproject_runtime()


def test_every_runtime_dep_is_installable_via_requirements() -> None:
    missing = _pyproject_runtime() - _requirements_packages()
    assert not missing, f"runtime deps missing from requirements.txt: {sorted(missing)}"


def test_requirements_has_no_package_absent_from_pyproject() -> None:
    # Forces pyproject to be the source of truth: nothing may be installed via
    # requirements.txt that pyproject does not also declare (runtime/dev/optional).
    stray = _requirements_packages() - _pyproject_all()
    assert not stray, f"requirements.txt packages not declared in pyproject: {sorted(stray)}"


def test_pdfplumber_is_removed() -> None:
    assert "pdfplumber" not in _pyproject_all()
    assert "pdfplumber" not in _requirements_packages()
