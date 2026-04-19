# Real Document Validation Workflow

Canonical real-document regression target: `tests/sources/Лиетар глава1.docx`.

Canonical registry for universal real-document validation: `corpus_registry.toml`.

Current default mapping:

- document profile: `lietaer-core`
- additional document profile: `religion-wealth-core`
- full run profile: `ui-parity-default`
- full AI run profile: `ui-parity-ai-default`
- soak run profile: `ui-parity-soak-3x`
- structural run profile: `structural-passthrough-default`

Current structure-recognition mode contract across run profiles:

- `ui-parity-default` inherits the repository UI default, which is currently `structure_recognition_mode = "auto"`
- `ui-parity-ai-default` forces `structure_recognition_mode = "always"`
- `structural-passthrough-default` forces `structure_recognition_mode = "off"` so the structural tier remains deterministic and does not silently pick up AI escalation from UI defaults

Current corpus notes:

- `lietaer-core` is now back on strict deterministic structural thresholds.
- `religion-wealth-core` now points at the original legacy `.doc` source and exercises the project-level auto-conversion path during corpus validation; it currently remains deterministic-structural `tolerant` because one page-separator artifact still produces a bounded restore diagnostic.

## Canonical Entry Points

Visible VS Code path:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Real Document Validation Profile
```

Exceptional automated quality-gate path:

```text
Tasks: Run Task -> Run Real Document Quality Gate
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

## Validation Tiers

The repository now distinguishes three reusable real-document validation tiers:

1. `extraction` — corpus-backed extractability and coarse structural expectations.
2. `structural` — deterministic passthrough through Markdown -> Pandoc -> formatting restore, without LLM calls.
3. `full` — model-backed UI-parity execution used by the Lietaer validator and the exceptional quality gate.

Ordinary pytest coverage is expected to exercise `extraction` and `structural`. The dedicated task/script path remains the user-visible path for `full` validation.

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
