# Testing

## Running Tests

Default terminal is WSL Debian. All test commands run directly in bash — no PowerShell wrappers.

```bash
# All tests (quiet)
bash scripts/test.sh tests/ -q

# One file (verbose)
bash scripts/test.sh tests/test_config.py -vv

# One test node (stop on first failure)
bash scripts/test.sh tests/test_config.py::test_name -vv -x

# With extra pytest flags
bash scripts/test.sh tests/ -q -x --tb=short
```

Never use PowerShell `.ps1` wrappers to run tests. They pipe output through WSL→PowerShell bridge which causes hangs and lost output.

Before concluding that imports are broken, dependencies are missing, or Pandoc/LibreOffice is unavailable, first verify the project runtime contract in WSL and prefer the canonical path `bash scripts/test.sh ...` over Windows `py`/`python`.

For fresh WSL/server setup, use `bash scripts/setup-wsl.sh` or the VS Code task `Setup Project`. System dependencies live in `system-requirements.apt`; Python dependencies live in `requirements.txt`. PDF import requires LibreOffice (`soffice` or `libreoffice`) in WSL and uses `--infilter=writer_pdf_import` before DOCX export.

Critical distinction:

- `bash scripts/test.sh ...`, `bash scripts/run-real-document-validation.sh`, `bash scripts/run-real-document-quality-gate.sh`, and the matching VS Code tasks are **canonical contract paths**.
- Direct `python -m pytest ...` without those shell entry points is only a **debug path**.
- If the workspace factually has a working Windows `.venv\Scripts\python.exe`, agents may use it only for debugging ordinary pytest selectors that do not themselves depend on a shell-bound contract.
- For `real`, `spec`, `ui-parity`, `validation`, `quality-gate`, or any shell-driven scenario, a debug path does not count as executing the requested canonical verification path.
- If the canonical shell path is unavailable, state that limitation explicitly instead of silently substituting an underlying Python runner and reporting it as equivalent verification.
- For structural preparation snapshots from `real_document_validation_structural.py`, prefer the module's own CLI through `bash scripts/run-structural-preparation-diagnostic.sh ...` or the VS Code task `Run Structural Preparation Diagnostic` instead of building nested `python -c` commands.

Verified command set for structural preparation snapshots:

```bash
# Preferred user-visible task path
# Task: Run Structural Preparation Diagnostic
# Prompt 1: end-times-pdf-core
# Prompt 2: leave blank to use the profile declared on the document profile

# Direct WSL shell path with explicit override
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery

# File-capture fallback when terminal stdout capture is unreliable
bash scripts/run-structural-preparation-diagnostic.sh end-times-pdf-core --run-profile-id ui-parity-pdf-structural-recovery > .run/end_times_structural_snapshot.json 2>&1

# Inspect the saved payload from the same WSL shell
tail -n 40 .run/end_times_structural_snapshot.json
```

When an AI agent runs tests for verification inside VS Code, the final user-facing verification path must be user-visible:

- use the existing VS Code tasks `Run Full Pytest`, `Run Current Test File`, or `Run Current Test Node` whenever one of them matches the requested scope;
- do not treat agent-side shell output, even from a foreground tool terminal, as equivalent to the user's visible VS Code terminal panel;
- do not rely on hidden/background terminal capture as the final source of truth for reporting test results;
- if a hidden or isolated rerun is needed for debugging, repeat the final verification in a visible user-facing path before claiming success;
- if no existing VS Code task fits the requested visible verification scope, say so explicitly instead of silently substituting agent-only terminal capture as the final proof.

Clarification for AI agents:

- output seen only through agent-side tool capture is not the same thing as a visible VS Code terminal run;
- foreground agent shell output is also not the same thing as the user's visible VS Code terminal panel;
- before any ad-hoc shell test command, identify the current shell with `uname` and `pwd` instead of assuming it is WSL or Git Bash;
- if the shell is already Linux inside `/mnt/d/www/projects/2025/DocxAICorrector`, run `bash scripts/test.sh ...` directly and do not nest `wsl.exe` inside that shell;
- if the shell is MSYS/Git Bash or PowerShell, use `wsl.exe -d Debian ...` only as a transport wrapper into the project WSL runtime, and treat that path as debugging rather than final proof;
- if the requested output is a structural preparation diagnostic snapshot, prefer the dedicated script/task entrypoint and do not hand-roll JSON printing with inline imports unless you are debugging the CLI itself;
- for `Run Structural Preparation Diagnostic`, leave the optional second prompt blank for the default profile on the document; if you need an explicit `--run-profile-id ...`, prefer the direct shell command instead of relying on task quoting;
- if the user explicitly wants to see the test run in the VS Code terminal, the final verification MUST use the existing VS Code tasks rather than agent-only shell capture or foreground tool terminals;
- if an agent uses shell test runs for debugging, run exactly one selector per command and wait for its full output; do not chain multiple pytest invocations with `&&` or other collapsed command patterns that make the result partial or ambiguous;
- do not start overlapping pytest runs for the same investigation in multiple terminals; keep one active selector, wait for completion, then narrow or broaden intentionally;
- if a `wsl.exe ... pytest ...` run returns only partial output, treat that first as a transport/capture failure, not as a completed pytest result;
- do not report pass/fail from a truncated run; rerun the same scope or a narrower single selector until the output is complete enough to establish an exit status;
- if a file-level selector still produces partial capture, narrow further to the most directly affected node selector instead of retrying a broader run;
- when a direct WSL shell or an existing VS Code pytest task is available for the same selector, prefer that path over repeated retries through the same fragile bridge;
- do not use background terminals for pytest verification, because that hides the live result stream from both the agent and the user;
- log-file recovery, hidden reruns, and foreground agent shell runs may be used for debugging, but never as the final user-facing proof when the user asked for visible terminal output.
- when using ad-hoc shell commands in WSL for debugging, verify the command exists first if availability is uncertain; avoid assuming helper utilities like `unzip` are installed.
- do not invoke Windows Python executables from WSL bash using mixed `d:/...` paths; prefer VS Code Python tools or a verified environment-native command path.
- if a Python snippet or file inspection can be done with workspace Python tools, prefer that over cross-environment shell invocation.
- when reproducing GitHub Actions, verify the failing run SHA first; if the local worktree is dirty or no longer matches that commit, use a clean worktree or the Docker CI-parity path before trusting the result.
- when validating a specific GitHub Actions run, do not report pass/fail until that exact run is explicitly shown as completed with a final conclusion.
- if Actions pages are fetched without authentication and job logs are unavailable, treat web status as provisional and confirm failures via the canonical local command path.
- if fetched web content says a run is still queued/in progress, never claim that the run is fixed or failed; report it as pending and continue with local reproduction.
- when user-provided evidence (for example email/job summary) conflicts with fetched page snapshots, prioritize reproducing the failing scope locally and report the discrepancy explicitly.
- do not hardcode a Windows-only virtualenv such as `.venv-win` in shared static-analysis config consumed by Linux CI; pass interpreter paths explicitly or keep editor-only environments opt-in.

## Project Lifecycle (app start/stop)

App lifecycle uses PowerShell tasks — those are fine:
- **Setup Project** / **Start Project** / **Stop Project** / **Project Status** — VS Code tasks

## Integrated Browser Debugging

Use VS Code integrated browser workflows for UI-facing investigation of the local Streamlit app.

- Preferred debug entrypoint: `.vscode/launch.json` configurations that use debug type `editor-browser`.
- Default local app URL for this repo: `http://localhost:8501`.
- Default health endpoint: `http://localhost:8501/_stcore/health`.
- If the task is to inspect or reproduce UI behavior in the app, prefer the integrated browser inside VS Code over an external browser.

Use the integrated browser when the task involves:

- visual UI verification inside VS Code;
- reproducing click, form, focus, drag, or navigation flows in the Streamlit app;
- checking browser console errors, network behavior, cookies, storage, or auth/session behavior for the local app;
- inspecting DOM/CSS/layout issues;
- sharing a page with the agent or using browser tools on an already-open page.

For Streamlit UI, spacing, width, responsiveness, or layout-only changes:

- verify the result in the integrated browser before claiming success;
- prefer browser validation plus code inspection over running the full pytest suite;
- do not run the full pytest suite as the default verification step for CSS-only or layout-only tweaks;
- run targeted tests only if the UI change also modifies Python behavior that is already covered by tests.

Prefer these repo configs when available:

- `Start Project and Launch Streamlit in Integrated Browser` when the app may not already be running;
- `Launch Streamlit in Integrated Browser` when the app is already running and you only need a fresh tab;
- `Attach to Streamlit Integrated Browser Tab` when a matching integrated browser tab is already open.

Do not use the integrated browser as the primary tool for:

- Python backend exceptions, import failures, Pandoc issues, or OpenAI configuration problems;
- Streamlit startup failures or health-check failures;
- pytest verification or any other test-running workflow;
- non-UI code investigation where reading code, logs, tasks, or Python tools is more direct.

For those cases, prefer the existing repo workflows:

- `Project Status`, `Start Project`, `Stop Project`, `Tail Streamlit Log` for runtime state and diagnostics;
- VS Code pytest tasks for test verification;
- code search, file reads, and Python-aware tools for backend investigation.

Important limits for agents:

- The integrated browser is for browser/UI work; it does not replace the WSL-first runtime contract.
- If interactive breakpoint stepping in the browser is required, use the `editor-browser` launch configuration rather than improvising a different browser workflow.
- If the task only requires reading or clicking through the page, agent browser tools or an integrated browser page are appropriate without reframing the task as a test run.

## UI Result Artifact Contract

For normal interactive UI processing runs, AI agents must distinguish between persisted input caches and final user-visible outputs.

- `.run/completed_*` files are not final output artifacts. They cache the original uploaded source bytes for restart/reuse after a successful run.
- Final UI-visible outputs are written under `.run/ui_results/` as paired `.result.md` and `.result.docx` files sharing the same stem.
- The canonical log event for those final outputs is `ui_result_artifacts_saved`; prefer its `artifact_paths` over guessing by filename in `.run/` root.
- When reconciling what the user saw in the UI versus what exists on disk, inspect `.run/ui_results/` first, then `ui_result_artifacts_saved`, and only then intermediate diagnostics such as `.run/formatting_diagnostics/*.json`.

## Real Document Validation

Canonical real-document validation target: `tests/sources/Лиетар глава1.docx`.

AI agents must follow these rules for the Lietaer real-document harness:

- Preferred visible verification path in VS Code: task `Run Lietaer Real Validation`.
- Preferred visible registry-driven verification path in VS Code: task `Run Real Document Validation Profile`.
- Preferred exceptional automated quality-gate path in VS Code: task `Run Real Document Quality Gate`.
- Canonical shell entry point in WSL: `bash scripts/run-real-document-validation.sh`.
- Canonical exceptional quality-gate shell entry point in WSL: `bash scripts/run-real-document-quality-gate.sh`.
- Do not invoke `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` through a Windows Python path from WSL.
- Do not spend time rediscovering the environment contract: the canonical runtime for this validator is WSL `.venv`, with `PYTHONPATH=.` rooted at the repository.
- The validator script is self-bootstrapping for imports and now records run metadata plus run-scoped artifact paths; prefer reading the latest manifest, progress snapshot, and run-specific report over guessing from overwritten root artifacts.
- Current-run artifacts live under `tests/artifacts/real_document_pipeline/runs/<run_id>/` and the latest aliases are updated in `tests/artifacts/real_document_pipeline/`.
- When reporting real-document results, include the `run_id`, latest manifest `status`, acceptance outcome, and the exact report/summary paths from the latest manifest.

## Startup Performance Contract

Startup performance is a protected repository contract.

Canonical source of truth: `docs/STARTUP_PERFORMANCE_CONTRACT.md`.

AI agents must follow these rules:

- Do not add heavy synchronous cleanup, preload, environment bootstrap, or directory scanning back into the early startup path in `app.py` unless the user explicitly asked for a startup contract change.
- Do not remove one-time caching for app config, system prompt loading, Pandoc availability checks, or the process-wide OpenAI client without an explicit startup/performance task.
- Do not re-enable Streamlit file watching or `runOnSave` in `.streamlit/config.toml` as part of unrelated work.
- Do not change the WSL-first runtime contract for the app lifecycle as part of unrelated work.

If the user explicitly asks to change the startup contract, update the code, tests, and canonical docs together, then run `bash scripts/test.sh tests/test_startup_performance_contract.py -q` and `bash scripts/test.sh tests/test_app.py -q`.

## Architectural Solution Contract

AI agents must not default to literal patch-style implementation just because the user proposed a local fix.

Rules:

- Treat user-suggested fixes as hints, not implementation requirements, unless the user explicitly requires that exact approach.
- Before implementing a local UI/CSS/runtime workaround, first evaluate whether the root cause comes from a broader architectural constraint such as iframe isolation, Streamlit rerun behavior, Pandoc generation boundaries, or OOXML/theme resolution.
- When a requested patch would create brittle behavior, hidden coupling, style drift, or repeated one-off fixes, prefer a cleaner architectural alternative even if the user originally asked for the patch form.
- In user-facing responses, explicitly present the durable options first and explain why the literal patch is weaker.
- For UI issues, prefer one of these paths over one-off CSS fixes when applicable:
	- revert to native Streamlit widgets/components when their built-in behavior matches the desired styling/inheritance contract;
	- for Streamlit width/spacing/layout problems, prefer `st.set_page_config`, `st.columns`, `st.container`, `st.sidebar`, and built-in `use_container_width` behavior before any DOM-targeting CSS;
	- introduce a single centralized component-level theme/layout contract for isolated surfaces such as `components.html(...)` if iframe inheritance is the real boundary;
	- only use local CSS as a component contract when isolation makes true inheritance impossible.
- If the user explicitly asks for no custom styles, do not add or suggest CSS selectors against Streamlit DOM nodes; solve it with native Streamlit layout primitives only.
- Do not claim CSS inheritance should work across `components.html(...)` boundaries; treat iframe isolation as a first-class architectural constraint.
- For markdown preview or similar `about:srcdoc` iframe surfaces, the durable default is: sync computed styles from the parent Streamlit DOM during render, instead of assuming Streamlit theme inheritance will occur automatically.
- If the final implementation must use local component CSS, keep it minimal, centralized, and free of font overrides unless the task explicitly requires font customization.
- Avoid solving the same class of UI problem repeatedly in separate call sites; consolidate the behavior into one helper or one component contract.

Default decision rule:

- First propose the robust architecture.
- Then implement the narrowest solution that preserves that architecture.
- Only implement the user's literal patch idea when it is also the cleanest technical option.

## Key Directories

- `tests/` — all test files
- `scripts/test.sh` — test entry point (activates venv, runs pytest)
- `.run/` — runtime artifacts (logs, PID files)
- `.venv/` — WSL Python venv

## Test Conventions

- Unit tests: `tests/test_<module>.py`
- Markers: `@pytest.mark.integration` for tests needing external tools
- Fixtures: `tests/conftest.py`
- Test artifacts: `tests/artifacts/`

## Protected Test Quality Contract

AI agents must not add or restore low-value tests that weaken the signal of the main regression suite.

- Do not create or restore spec-like tests that assert headings, wording, or section presence inside archived markdown/spec documents as part of the main `tests/` regression suite unless the user explicitly asks for documentation-guard coverage.
- Do not create or restore thin-wiring tests that only verify wrapper delegation or argument pass-through to mocked implementations, especially for façade modules such as `app_runtime.py`, unless the user explicitly asks for that wiring layer to be tested.
- Prefer tests that protect user-visible behavior, runtime outcomes, emitted events, failure contracts, and real output artifacts.

## Protected Refactoring Contract

AI agents must not begin large-scale refactoring without a written specification and explicit user approval.

Rules:

- Before starting any refactoring that moves, renames, splits, or merges modules, functions across files, or changes public API boundaries, write a specification document first.
- The specification must describe: the problem being solved, current state of affected code, proposed changes with module boundaries and dependency direction, consumer update plan, what does not change, and verification criteria.
- Place new and active specifications in `docs/` following the naming convention `DESCRIPTIVE_NAME_SPEC_YYYY-MM-DD.md`.
- Use `docs/archive/` only for historical, superseded, or already-realized materials; do not place new plans or active specs there.
- Present the specification to the user and wait for explicit approval before making any code changes.
- Do not treat a user's exploratory question about possible refactoring as permission to start implementing it.
- Small, localized changes (renaming a variable, extracting a single helper within the same file, fixing a bug) do not require a specification.
- The threshold is: if the change touches more than one module's public API or moves code between files, it requires a spec.

## Protected Test Workflow Contract

The WSL/bash test workflow is a protected repository contract.

AI agents must follow these rules:

- Do not add or restore PowerShell `.ps1` wrappers for test execution.
- Do not route tests through PowerShell, `ForEach-Object`, or any WSL to PowerShell output bridge.
- Do not change `.vscode/tasks.json` test tasks away from direct `wsl.exe` plus `bash scripts/test.sh` unless the user explicitly asked to redesign the test workflow.
- Do not change `scripts/test.sh`, `.vscode/tasks.json` test tasks, `tests/test_script_workflow_smoke.py`, or the test-workflow docs as part of unrelated work.
- If the user explicitly asks to change the test workflow contract, update all of these in the same change: `scripts/test.sh`, `.vscode/tasks.json`, `tests/test_script_workflow_smoke.py`, `README.md`, `CONTRIBUTING.md`, and `docs/WORKFLOW_AND_IMAGE_MODES.md`.
- After any intentional test-workflow change, run the canonical verification command `bash scripts/test.sh tests/test_script_workflow_smoke.py -q` and then `bash scripts/test.sh tests/ -q`.
