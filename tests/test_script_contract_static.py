from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.static_workflow


def _load_vscode_tasks() -> list[dict[str, Any]]:
    tasks_path = REPO_ROOT / ".vscode" / "tasks.json"
    return json.loads(tasks_path.read_text(encoding="utf-8"))["tasks"]


def _assert_src_bootstrap_results_in_src_first(script_path: Path) -> None:
    source_lines = script_path.read_text(encoding="utf-8").splitlines()
    source_text = "\n".join(source_lines)
    start_index: int | None = None
    helper_index: int | None = None
    invocation_index: int | None = None
    invocation_line: str | None = None

    for index, line in enumerate(source_lines):
        stripped = line.strip()
        if start_index is None and stripped.startswith(("SCRIPT_PATH =", "PROJECT_ROOT =", "REPO_ROOT =", "ROOT_DIR =")):
            start_index = index
        if helper_index is None and stripped.startswith("def _ensure_src_first_import_order("):
            helper_index = index
        if stripped in {
            "_ensure_src_first_import_order(SRC_ROOT)",
            "_ensure_src_first_import_order(PROJECT_ROOT, SRC_ROOT)",
            "_ensure_src_first_import_order(REPO_ROOT, SRC_ROOT)",
            "_ensure_src_first_import_order(ROOT_DIR, SRC_ROOT)",
        }:
            invocation_index = index
            invocation_line = stripped

    assert start_index is not None, script_path
    assert helper_index is not None and helper_index >= start_index, script_path
    assert invocation_index is not None and invocation_index >= helper_index, script_path
    assert invocation_line is not None, script_path

    helper_name = None
    if "REPO_ROOT = _resolve_repo_root()" in source_text:
        helper_name = "_resolve_repo_root"

    bootstrap_snippet = "\n".join(source_lines[start_index : invocation_index + 1])
    fake_sys = SimpleNamespace(path=[])
    namespace = {
        "__file__": str(script_path),
        "Path": Path,
        "sys": fake_sys,
    }
    if helper_name is not None:
        namespace[helper_name] = lambda: script_path.parents[2]
    exec(bootstrap_snippet, namespace)

    expected_prefix = [str(namespace["SRC_ROOT"])]
    if invocation_line != "_ensure_src_first_import_order(SRC_ROOT)":
        root_name = next(name for name in ("PROJECT_ROOT", "REPO_ROOT", "ROOT_DIR") if name in invocation_line)
        expected_prefix.append(str(namespace[root_name]))

    assert fake_sys.path[: len(expected_prefix)] == expected_prefix


def test_vscode_test_tasks_normalize_windows_relative_paths() -> None:
    tasks_by_label = {task["label"]: task for task in _load_vscode_tasks()}

    setup_task = tasks_by_label["Setup Project"]
    tail_log_task = tasks_by_label["Tail Streamlit Log"]
    full_task = tasks_by_label["Run Full Pytest"]
    docker_parity_task = tasks_by_label["Run Docker CI Parity Pytest"]
    file_task = tasks_by_label["Run Current Test File"]
    node_task = tasks_by_label["Run Current Test Node"]
    lietaer_task = tasks_by_label["Run Lietaer Real Validation"]
    lietaer_ai_task = tasks_by_label["Run Lietaer Real Validation AI"]
    real_document_task = tasks_by_label["Run Real Document Validation Profile"]

    assert setup_task["command"].endswith("scripts\\setup-project.ps1")
    assert tail_log_task["command"].endswith("scripts\\tail-streamlit-log.ps1")
    assert tail_log_task["args"] == ["-Lines", "${input:streamlitLogLines}"]

    assert full_task["command"] == "bash scripts/test.sh"

    assert docker_parity_task["command"].startswith(
        'bash -lc \'docker run --rm -v "$(pwd)":/src -w /src python:3.12 bash -lc "'
    )
    assert docker_parity_task.get("args", []) == []
    assert "pip install -r requirements.txt" in docker_parity_task["command"]
    assert "pytest tests/ -q" in docker_parity_task["command"]

    assert file_task["command"] == 'bash scripts/test.sh "${relativeFile}"'
    assert file_task.get("args", []) == []

    assert node_task["command"] == (
        'bash scripts/test.sh "${relativeFile}::${input:pytestNodeSuffix}"'
    )
    assert node_task.get("args", []) == []

    assert lietaer_task["command"] == "bash"
    assert lietaer_task["args"] == [
        "-lc",
        "export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-full-benchmark; export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-default; bash scripts/run-real-document-validation.sh",
    ]

    assert lietaer_ai_task["command"] == "bash"
    assert lietaer_ai_task["args"] == [
        "-lc",
        "export DOCXAI_REAL_DOCUMENT_PROFILE=lietaer-pdf-full-benchmark; export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-advisory; bash scripts/run-real-document-validation.sh",
    ]

    assert real_document_task["command"] == "bash"
    real_document_args = real_document_task["args"]
    assert real_document_args[0] == "-lc"
    assert 'profile="$1"' in real_document_args[1]
    assert 'run_profile="$2"' in real_document_args[1]
    assert 'export DOCXAI_REAL_DOCUMENT_PROFILE="$profile"' in real_document_args[1]
    assert 'export DOCXAI_REAL_DOCUMENT_RUN_PROFILE="$run_profile"' in real_document_args[1]
    assert 'bash scripts/run-real-document-validation.sh' in real_document_args[1]
    assert real_document_args[2:] == ["_", "${input:realDocumentProfileId}", "${input:realDocumentRunProfileId}"]


def test_setup_contract_declares_required_system_packages() -> None:
    apt_requirements = (REPO_ROOT / "system-requirements.apt").read_text(encoding="utf-8")
    setup_script = (REPO_ROOT / "scripts" / "setup-wsl.sh").read_text(encoding="utf-8")
    status_script = (REPO_ROOT / "scripts" / "project-control-wsl.sh").read_text(encoding="utf-8")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    workflow_doc = (REPO_ROOT / "docs" / "WORKFLOW_AND_IMAGE_MODES.md").read_text(encoding="utf-8")
    agent_rules = (REPO_ROOT / "docs" / "AI_AGENT_DEVELOPMENT_RULES.md").read_text(encoding="utf-8")
    copilot_instructions = (REPO_ROOT / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")

    assert "pandoc" in apt_requirements
    assert "libreoffice" in apt_requirements
    assert "antiword" in apt_requirements
    assert "apt-get install" in setup_script
    assert "DOCXAI_APT_TIMEOUT_SECONDS" in setup_script
    assert "system-requirements.apt" in setup_script
    assert "libreoffice_ok" in status_script
    assert "bash scripts/setup-wsl.sh" in readme
    assert "bash scripts/setup-wsl.sh" in contributing
    assert "system-requirements.apt" in workflow_doc
    assert "system-requirements.apt" in agent_rules
    assert "Setup Project" in copilot_instructions


def test_repository_shell_scripts_have_valid_bash_syntax() -> None:
    if platform.system() == "Windows":
        pytest.skip("bash cannot resolve Windows-style script paths; the check runs on the Linux/WSL runner")
    failures: list[str] = []
    for script_path in sorted((REPO_ROOT / "scripts").glob("*.sh")):
        result = subprocess.run(
            ["bash", "-n", str(script_path)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            failures.append(f"{script_path.name}: {result.stderr or result.stdout}")

    assert not failures, "\n".join(failures)


def test_legacy_powershell_test_wrappers_are_removed() -> None:
    for script_name in ["run-tests.ps1", "run-test-file.ps1", "run-test-node.ps1"]:
        assert not (REPO_ROOT / "scripts" / script_name).exists()


def test_ci_exposes_editable_install_and_static_workflow_jobs() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    tests_job_text = ci_text.split("tests:", 1)[1]

    assert "editable-install:" in ci_text
    assert "pip install -e \".[dev]\"" in ci_text
    assert "python -c \"import docxaicorrector\"" in ci_text
    assert "bash scripts/test.sh tests/test_typecheck.py -q" in ci_text
    assert "tests:" in ci_text
    assert "needs: [editable-install]" in ci_text
    assert tests_job_text.index("Clean working tree before tests") < tests_job_text.index("Install dependencies")
    assert "Run static workflow checks" in ci_text
    assert "bash scripts/test.sh tests/test_script_contract_static.py -q" in ci_text


def test_manual_real_document_workflow_installs_system_deps_and_uploads_artifacts() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "real-document-validation.yml").read_text(encoding="utf-8")
    workflow_doc = (REPO_ROOT / "docs" / "testing" / "REAL_DOCUMENT_VALIDATION_WORKFLOW.md").read_text(encoding="utf-8")
    testing_readme = (REPO_ROOT / "docs" / "testing" / "README.md").read_text(encoding="utf-8")

    assert "name: Real Document Validation" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES: \"1\"" in workflow_text
    assert "system-requirements.apt" in workflow_text
    assert "tests/test_real_document_validation_corpus.py::test_corpus_extraction[mazzucato-pdf-full-benchmark]" in workflow_text
    assert "tests/test_real_document_validation_corpus.py::test_corpus_extraction[lietaer-pdf-full-benchmark]" in workflow_text
    assert "actions/upload-artifact@v4" in workflow_text
    assert "tests/artifacts/real_document_pipeline/**" in workflow_text
    assert "GitHub Actions -> Real Document Validation" in workflow_doc
    assert "Real Document Validation" in testing_readme


def test_manual_ai_heavy_workflows_are_documented_and_upload_artifacts() -> None:
    structure_workflow_text = (REPO_ROOT / ".github" / "workflows" / "real-document-ai-structure-smoke.yml").read_text(encoding="utf-8")
    workflow_doc = (REPO_ROOT / "docs" / "testing" / "REAL_DOCUMENT_VALIDATION_WORKFLOW.md").read_text(encoding="utf-8")
    testing_readme = (REPO_ROOT / "docs" / "testing" / "README.md").read_text(encoding="utf-8")

    assert "name: Real Document AI Structure Smoke" in structure_workflow_text
    assert "workflow_dispatch:" in structure_workflow_text
    assert 'DOCXAI_RUN_REAL_DOCUMENT_STRUCTURE_RECOGNITION: "1"' in structure_workflow_text
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in structure_workflow_text
    assert "system-requirements.apt" in structure_workflow_text
    assert "bash scripts/test.sh tests/test_real_document_structure_recognition_integration.py -vv" in structure_workflow_text
    assert "actions/upload-artifact@v4" in structure_workflow_text
    assert "tests/artifacts/real_document_pipeline/**" in structure_workflow_text

    assert "GitHub Actions -> Real Document AI Structure Smoke" in workflow_doc
    assert "Real Document AI Structure Smoke" in testing_readme


def test_codeowners_protects_workflow_and_startup_contract_files() -> None:
    codeowners_text = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "/.github/workflows/real-document-ai-structure-smoke.yml @slawa19" in codeowners_text
    assert "/scripts/test.sh @slawa19" in codeowners_text
    assert "/.vscode/tasks.json @slawa19" in codeowners_text
    assert "/tests/test_script_contract_static.py @slawa19" in codeowners_text
    assert "/tests/test_script_workflow_smoke.py @slawa19" in codeowners_text
    assert "/docs/STARTUP_PERFORMANCE_CONTRACT.md @slawa19" in codeowners_text
    assert "/tests/test_startup_performance_contract.py @slawa19" in codeowners_text


def test_ci_uses_canonical_bash_test_contract() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "runs-on: ubuntu-latest" in ci_text
    assert "python -m venv .venv" in ci_text
    assert ". .venv/bin/activate" in ci_text
    assert "bash scripts/test.sh tests/test_script_contract_static.py -q" in ci_text
    assert (
        'bash scripts/test.sh tests/ -q -m "not static_workflow and not typecheck and not system_deps and not manual_ai_heavy and not browser_ui"'
        in ci_text
    )


def test_inventory_lists_every_top_level_test_file_exactly_once() -> None:
    inventory_text = (REPO_ROOT / "docs" / "testing" / "TEST_TIER_INVENTORY.md").read_text(encoding="utf-8")
    tier_headers = {
        "## Unit-Contract",
        "## Compat-Legacy",
        "## Static-Workflow",
        "## Typecheck",
        "## Integration-Local",
        "## System-Deps",
        "## Manual-AI-Heavy",
        "## Browser-UI",
    }
    current_tier = None
    inventory_entries: dict[str, str] = {}
    duplicates: list[str] = []

    for raw_line in inventory_text.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_tier = line if line in tier_headers else None
            continue
        if not line.startswith("- `tests/test_") or current_tier is None:
            continue
        test_path = line.split("`", 2)[1]
        if test_path in inventory_entries:
            duplicates.append(test_path)
            continue
        inventory_entries[test_path] = current_tier

    actual_test_files = {
        str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        for path in (REPO_ROOT / "tests").glob("test_*.py")
    }

    assert not duplicates
    assert set(inventory_entries) == actual_test_files


def test_special_tier_files_have_file_level_markers_for_pytest_selection() -> None:
    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    typecheck_text = (REPO_ROOT / "tests" / "test_typecheck.py").read_text(encoding="utf-8")
    system_deps_text = (REPO_ROOT / "tests" / "test_real_document_validation_corpus.py").read_text(encoding="utf-8")

    assert "pytest.mark.typecheck" in typecheck_text
    assert "pytest.mark.system_deps" in system_deps_text
    assert "bash scripts/test.sh tests/ -q" in ci_text
    assert "python -m pytest tests -q" not in ci_text


def test_source_path_bootstrap_prefers_src_before_repo_root() -> None:
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    test_sh = (REPO_ROOT / "scripts" / "test.sh").read_text(encoding="utf-8")
    validation_sh = (REPO_ROOT / "scripts" / "run-real-document-validation.sh").read_text(encoding="utf-8")
    structural_sh = (REPO_ROOT / "scripts" / "run-structural-preparation-diagnostic.sh").read_text(encoding="utf-8")

    assert 'pythonpath = ["src", "."]' in pyproject_text
    expected_pythonpath = 'export PYTHONPATH="$PWD/src:$PWD${PYTHONPATH:+:$PYTHONPATH}"'
    assert expected_pythonpath in test_sh
    assert expected_pythonpath in validation_sh
    assert expected_pythonpath in structural_sh
    _assert_src_bootstrap_results_in_src_first(REPO_ROOT / "tests" / "conftest.py")
    _assert_src_bootstrap_results_in_src_first(
        REPO_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    )
    _assert_src_bootstrap_results_in_src_first(
        REPO_ROOT / "benchmark_projects" / "pdf_candidate_benchmark" / "benchmark_runner.py"
    )
    _assert_src_bootstrap_results_in_src_first(REPO_ROOT / "scripts" / "run_pic1_modes.py")
    _assert_src_bootstrap_results_in_src_first(REPO_ROOT / "scripts" / "_run_cleanup_now.py")


def test_log_event_inventory_scans_migrated_implementation_paths() -> None:
    script_text = (REPO_ROOT / "scripts" / "_list_log_events.py").read_text(encoding="utf-8")

    expected_targets = [
        "src/docxaicorrector/core/config.py",
        "src/docxaicorrector/document/layout_cleanup.py",
        "src/docxaicorrector/generation/_generation.py",
        "src/docxaicorrector/image/generation.py",
        "src/docxaicorrector/pipeline/_pipeline.py",
        "src/docxaicorrector/pipeline/block_execution.py",
        "src/docxaicorrector/pipeline/block_failures.py",
        "src/docxaicorrector/pipeline/late_phases.py",
        "src/docxaicorrector/pipeline/narration_postprocess.py",
        "src/docxaicorrector/pipeline/setup.py",
        "src/docxaicorrector/processing/preparation.py",
        "src/docxaicorrector/runtime/artifact_retention.py",
        "src/docxaicorrector/runtime/state.py",
        "src/docxaicorrector/ui/_app.py",
        "src/docxaicorrector/ui/application_flow.py",
        "src/docxaicorrector/validation/structural.py",
    ]

    for expected_target in expected_targets:
        assert f'"{expected_target}"' in script_text


def test_codeowners_protects_moved_production_implementation_paths() -> None:
    codeowners_text = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")

    assert "/app.py @slawa19" in codeowners_text
    assert "/app.pyi @slawa19" in codeowners_text
    assert "/src/docxaicorrector/ui/_app.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/core/constants.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/core/logger.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/core/config.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/core/models.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/runtime/state.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/processing/preparation.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/processing/processing_runtime.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/processing/processing_service.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/_generation.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/formatting_transfer.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/formatting_diagnostics_retention.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/message_formatting.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/openai_response_utils.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/generation/search.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/validation/common.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/validation/profiles.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/validation/structural.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/real_image/manifest.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/ui/_ui.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/ui/app_runtime.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/ui/application_flow.py @slawa19" in codeowners_text
    assert "/src/docxaicorrector/ui/compare_panel.py @slawa19" in codeowners_text