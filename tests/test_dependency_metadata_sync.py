from __future__ import annotations

import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _parse_requirement_lines(path: Path) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ">=" not in line:
            continue
        name, spec = line.split(">=", 1)
        requirements[name.strip().lower()] = f">={spec.strip()}"
    return requirements


def _parse_project_dependencies(pyproject_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    runtime_deps: dict[str, str] = {}
    dev_deps: dict[str, str] = {}

    for item in project.get("dependencies", []):
        if ">=" not in item:
            continue
        name, spec = item.split(">=", 1)
        runtime_deps[name.strip().lower()] = f">={spec.strip()}"

    optional_deps = project.get("optional-dependencies", {})
    for item in optional_deps.get("dev", []):
        if ">=" not in item:
            continue
        name, spec = item.split(">=", 1)
        dev_deps[name.strip().lower()] = f">={spec.strip()}"

    return runtime_deps, dev_deps


def test_requirements_and_pyproject_dependency_constraints_stay_in_sync() -> None:
    requirements = _parse_requirement_lines(PROJECT_ROOT / "requirements.txt")
    runtime_deps, dev_deps = _parse_project_dependencies(PROJECT_ROOT / "pyproject.toml")

    expected_runtime = {
        "openai",
        "streamlit",
        "python-docx",
        "pypandoc",
        "python-dotenv",
        "pillow",
    }
    expected_dev = {
        "pytest",
        "pyright",
    }

    assert set(runtime_deps) == expected_runtime
    assert set(dev_deps) == expected_dev

    for name in sorted(expected_runtime | expected_dev):
        expected_spec = requirements[name]
        actual_spec = runtime_deps.get(name, dev_deps.get(name))
        assert actual_spec == expected_spec, name
