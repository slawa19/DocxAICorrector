# Real Document Validation Workflow

Canonical full-tier real-document regression target: `tests/sources/Лиетар глава1.docx`.

Canonical registry for universal real-document validation: `corpus_registry.toml`.

Current default mapping:

- document profile: `lietaer-core`
- additional document profile: `religion-wealth-core`
- audiobook sanity document profile: `mazzucato-audiobook-core`
- canonical structure-recovery document profile: `lietaer-pdf-first-20-structure-core`
- full run profile: `ui-parity-default`
- full AI run profile: `ui-parity-ai-default`
- soak run profile: `ui-parity-soak-3x`
- structural run profile: `structural-passthrough-default`
- AI-first structural run profile: `structural-ai-first-default`
- audiobook postprocess run profile: `ui-parity-translate-audiobook-postprocess`
- benchmark-only advisory run profile: `ui-parity-translate-benchmark-advisory`

Current structure-recognition mode contract across run profiles:

- `ui-parity-default` inherits the repository UI default, which is currently `structure_recognition_mode = "auto"`
- `ui-parity-ai-default` forces `structure_recognition_mode = "always"`
- `structural-passthrough-default` forces `structure_recognition_mode = "off"` so the structural tier remains deterministic and does not silently pick up AI escalation from UI defaults

Current corpus notes:

- `lietaer-core` is now back on strict deterministic structural thresholds.
- `religion-wealth-core` now points at the original legacy `.doc` source and exercises the project-level auto-conversion path during corpus validation; it currently remains deterministic-structural `tolerant` because one page-separator artifact still produces a bounded restore diagnostic.
- `mazzucato-audiobook-core` is the canonical real-document sample for translate plus audiobook postprocess sanity and maps to `ui-parity-translate-audiobook-postprocess` by default.
- `lietaer-pdf-first-20-structure-core` is the canonical AI-first structure-recovery slice and maps to `structural-ai-first-default` for the structural diagnostic path.
- `lietaer-pdf-first-20-benchmark` and `lietaer-pdf-full-benchmark` are explicitly tagged `benchmark-only` in `corpus_registry.toml`; they use `ui-parity-translate-benchmark-advisory` and are excluded from mandatory full gates by policy.

## AI-First Structure Recovery Workflow

When the active work is specifically AI-first structure recovery, do not use the
general full-validator path as the default debug loop.

Use this structure-scoped order instead:

1. focused local tests for the directly touched structure module or preparation slice;
2. `bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core`
	as the default real-document PDF snapshot path;
3. a full-tier validator only as a late checkpoint, and only when the defect is
	already proven to live in final markdown/DOCX artifacts rather than in
	preparation/structure artifacts.

Corpus policy for this workflow:

1. `lietaer-pdf-first-20-structure-core` (`tests/sources/Rethinking-money-first-20-pages.pdf`) is the canonical fast PDF slice for routine structure iteration.
2. This single PDF slice is sufficient for the ordinary structure-recovery loop because it already contains front matter, TOC, and body headings.
3. `lietaer-core` is not the routine structure-recovery proof document for this workflow.
4. `ui-parity-pdf-structural-recovery` is still a `full` tier translate profile with `structure_recognition_mode = "off"`; despite its name, it is not the default proof path for AI-first structure recognition.
5. `tests/sources/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf` exists in the repository, but it should not be treated as canonical structure evidence until a dedicated corpus entry with explicit structure expectations is registered.

## Canonical Entry Points

Visible VS Code structure path:

```text
Tasks: Run Task -> Run Structure Recovery Diagnostic (First 20 Pages)
```

General full-tier path:

```text
Tasks: Run Task -> Run Lietaer Real Validation
```

Visible VS Code path:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Real Document Validation Profile
```

Exceptional automated quality-gate path:

```text
Tasks: Run Task -> Run Real Document Quality Gate
```

Manual GitHub Actions system-deps path:

```text
GitHub Actions -> Real Document Validation
```

Canonical WSL CLI path:

```bash
bash scripts/run-real-document-validation.sh
```

Exceptional automated pytest gate:

```bash
bash scripts/run-real-document-quality-gate.sh
```

This script does three things for you:

1. runs from the repository root;
2. activates the WSL project environment at `.venv`;
3. exports `PYTHONPATH=.` before launching `tests/artifacts/real_document_pipeline/run_lietaer_validation.py` with unbuffered output.

The quality-gate script runs only the exceptional pytest entry point `tests/test_real_document_quality_gate.py` with `-vv -s`, so the terminal shows the live validator stream and pytest automatically fails the gate when the validator exits non-zero or writes an invalid manifest/report.

The manual `Real Document Validation` workflow is the Phase 4 system-deps path. It installs `system-requirements.apt`, forces `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1`, runs the no-skip legacy DOC and PDF extraction selectors, runs the canonical structural passthrough selector for `lietaer-pdf-first-20-structure-core`, and uploads `.run/`, `tests/artifacts/real_document_pipeline/`, and `tests/artifacts/structural_diagnostics/` artifacts for inspection.

## Validation Tiers

The repository now distinguishes three reusable real-document validation tiers:

1. `extraction` — corpus-backed extractability and coarse structural expectations.
2. `structural` — deterministic passthrough through Markdown -> Pandoc -> formatting restore, without LLM calls.
3. `full` — model-backed UI-parity execution used by the Lietaer validator and the exceptional quality gate.

Ordinary pytest coverage is expected to exercise `extraction` and `structural`. The dedicated task/script path remains the user-visible path for `full` validation.

Benchmark-only policy:

1. Profiles tagged `benchmark-only` are research/evaluation inputs, not mandatory regression gates.
2. Their default run profile is `ui-parity-translate-benchmark-advisory`, which keeps translation quality gate policy advisory for model-comparison runs.
3. They may participate in manual or benchmark workflows, but they are excluded from mandatory full gates by repository policy.

## AI Structure Recognition Smoke

The repository also has a real-document AI structure-recognition smoke test in
`tests/test_real_document_structure_recognition_integration.py`.

This test is intentionally opt-in and is excluded from the ordinary `Run Full Pytest`
path even when `OPENAI_API_KEY` is present. It only runs when both conditions hold:

1. `OPENAI_API_KEY` is available after loading the project `.env`.
2. `DOCXAI_RUN_REAL_DOCUMENT_STRUCTURE_RECOGNITION=1` is set explicitly.

Run it only when a change touches one of these surfaces:

1. `structure_recognition.py` prompt/request/response parsing logic.
2. `preparation.py` integration of the structure-recognition stage.
3. runtime/profile wiring that decides whether AI structure recognition mode resolves to `off`, `auto`, or `always`.
4. real-document validation/reporting logic for AI counters or AI-enabled profiles.

Preferred user-visible execution paths:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Lietaer Real Validation AI
```

Ad-hoc pytest path when an explicit smoke assertion is needed:

```bash
DOCXAI_RUN_REAL_DOCUMENT_STRUCTURE_RECOGNITION=1 \
bash scripts/test.sh tests/test_real_document_structure_recognition_integration.py -vv
```

## Environment Contract

- Use the WSL project environment in `.venv`.
- Do not run the validator through a Windows virtualenv from WSL.
- Do not assume the standalone validator inherits the correct import root from the shell.
- The validator now self-bootstraps the repository root into `sys.path`, but the canonical runtime remains WSL `.venv`.
- Legacy `.doc` validation requires either LibreOffice (`soffice`) or the fallback pair `antiword` + `pandoc` inside WSL.
- PDF import validation requires LibreOffice (`soffice`/`libreoffice`) inside WSL and uses Writer PDF import filter (`--infilter=writer_pdf_import`) before DOCX export.

## CI-Parity Notes For Corpus Debugging

`religion-wealth-core` intentionally points at an original legacy `.doc` source, so this profile exercises the real conversion boundary instead of a pre-normalized `.docx` shortcut.

Consequences for debugging:

- green local pytest in a developer WSL environment does not automatically prove green CI;
- CI may fail only because a clean Ubuntu runner lacks `soffice` or `antiword` + `pandoc`;
- extraction-tier and structural-tier corpus tests for legacy `.doc` and any future PDF corpus profiles should be treated as capability-sensitive, not as pure business-logic tests.

When a CI run fails on corpus extraction or structural passthrough for a legacy `.doc` or PDF profile, check capability first:

```bash
command -v soffice || command -v libreoffice
command -v antiword
pandoc --version
```

If you need CI-parity reproduction, prefer a clean Python 3.12 container:

```bash
docker run --rm -v "$PWD":/src -w /src python:3.12 bash -lc '
	python -m venv /tmp/docxai-venv &&
	. /tmp/docxai-venv/bin/activate &&
	python -m pip install --upgrade pip &&
	pip install -r requirements.txt &&
	pytest tests/test_real_document_validation_corpus.py -vv -x --tb=short
'
```

Use this parity path before concluding that a regression came from Python code. For this class of failures, the missing dependency is often the conversion toolchain rather than the extraction logic itself.

## Artifact Layout

Each validation run now gets a unique run directory:

```text
tests/artifacts/real_document_pipeline/runs/<run_id>/
```

Per-run artifacts include:

- `lietaer_validation_report.json`
- `lietaer_validation_summary.txt`
- `lietaer_validation_progress.json`
- `Лиетар глава1_validated.md`
- `Лиетар глава1_validated.docx`

Latest aliases are still updated in:

```text
tests/artifacts/real_document_pipeline/
```

Use `tests/artifacts/real_document_pipeline/lietaer_validation_latest.json` as the source of truth for the latest run. Its schema is now stable during the full run lifecycle and includes both run-scoped artifact paths and latest alias paths.

Use `tests/artifacts/real_document_pipeline/lietaer_validation_progress.json` to inspect the current run while it is still executing.

## Run Metadata

The JSON report and summary now record:

- `run_id`
- `document_profile_id`
- `run_profile_id`
- `validation_tier`
- start and finish timestamps in UTC
- run duration
- artifact root and run directory
- Python executable and version
- `PYTHONPATH`
- active virtualenv
- whether WSL was detected
- current git head when available
- formatting diagnostics discovery source and counts

The latest manifest and progress snapshot now also record:

- current run `status` (`in_progress`, `completed`, `failed`)
- `document_profile_id`, `run_profile_id`, `validation_tier`
- current phase/stage/detail
- last update timestamp
- current progress value
- acceptance outcome
- final failure classification and `last_error`
- resolved `runtime_config` and explicit runtime overrides relative to UI defaults; `runtime_configuration` больше не считается допустимым report alias

## Live Progress

The validator now emits line-buffered terminal progress for:

- startup and environment bootstrap
- preparation stages from the pre-processing pipeline
- block-level processing status and completion milestones
- formatting diagnostics warnings
- periodic heartbeat lines while the run is still active
- final completed/failed status with the exact report path

This means both the user and the agent can watch the same terminal stream and wait for a deterministic completion state without screenshots or manual polling.

## Diagnostics Scoping

Formatting diagnostics are attributed to the current run in this order:

1. snapshot diff of `.run/formatting_diagnostics/` before vs after the run;
2. explicit artifact paths emitted into the runtime event log;
3. recent-file fallback scan.

Runtime formatting diagnostics now use bounded retention inside `.run/formatting_diagnostics/`: current implementation keeps up to 7 days of history, caps the directory at 100 artifacts, and prunes oldest files first on write. This retention applies only to the runtime `.run/` area.

Validation artifacts under `tests/artifacts/...` remain separate, run-scoped validation/dev outputs and are not cleaned by runtime retention logic.

This prevents ambiguity when multiple old `preserve_*.json`, `normalize_*.json`, or `restore_*.json` files already exist.

## Acceptance Signals

The real-document acceptance contract now checks:

- pipeline success
- output DOCX openability
- placeholder removal
- formatting diagnostics threshold
- captions not promoted to headings
- key headings preserved
- short centered paragraphs preserved
- ordered Word numbering preserved

Current Phase 1 output contract behind those checks:

- Pandoc plus the dynamic reference DOCX are the primary source of heading/body/list styling;
- the post-Pandoc formatter is intentionally minimal and is limited to caption formatting, image-placeholder centering, baseline table styling, and direct paragraph alignment restoration for mapped paragraphs;
- broad source paragraph XML replay and source numbering XML injection are not part of the mainline acceptance path.

The centered-paragraph acceptance check is therefore expected to pass through mapped direct-alignment restoration rather than through a validator-side exception or broad paragraph-XML replay.

The exceptional quality gate and the real-document AI structure-recognition smoke are intentionally excluded from the normal full-suite path. They are available only through dedicated task/script or explicit opt-in env selection so expensive real-document validation does not contaminate ordinary regression runs.

## Corpus Workflow

To add a new reusable real-document regression case:

1. register the document in `corpus_registry.toml` with structural expectations and provenance;
2. bind it to an existing run profile or add a new run profile there;
3. let ordinary pytest pick it up through corpus-backed extraction and structural tests;
4. use the dedicated full-tier task only when model-backed parity or quality-gate coverage is needed.
