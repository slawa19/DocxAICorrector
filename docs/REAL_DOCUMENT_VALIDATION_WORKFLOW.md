# Real Document Validation Workflow

Canonical full-tier real-document regression target: `tests/sources/book/Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.pdf` (profile `lietaer-pdf-full-benchmark`).

Canonical registry for universal real-document validation: `corpus_registry.toml`. The corpus now contains only the real full books under `tests/sources/book/`.

Current default mapping:

- default document profile: `lietaer-pdf-full-benchmark`
- additional full-book document profiles: `mazzucato-pdf-full-benchmark`, `creatingwealth-pdf-full-benchmark`, held-out `money-sustainability-pdf-full-heldout`
- full run profile: `ui-parity-default`
- soak run profile: `ui-parity-soak-3x`
- structural run profile: `ui-parity-translate-benchmark-advisory`

Current corpus notes:

- `lietaer-pdf-full-benchmark` is the default full-book PDF profile for structure-model comparison on the full Lietaer source.
- `mazzucato-pdf-full-benchmark`, `creatingwealth-pdf-full-benchmark`, and held-out `money-sustainability-pdf-full-heldout` round out the four-book PDF corpus in `tests/sources/book/`.

## AI-First Structure Recovery Workflow

When the active work is specifically AI-first structure recovery, do not use the
general full-validator path as the default debug loop.

Use this structure-scoped order instead:

1. focused local tests for the directly touched structure module or preparation slice;
2. `bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-full-benchmark`
	as the default real-document PDF snapshot path;
3. `bash scripts/run-structural-preparation-diagnostic.sh mazzucato-pdf-full-benchmark`
	for a non-Lietaer full-book topology cross-check;
4. a full-tier validator only as a late checkpoint, and only when the defect is
	already proven to live in final markdown/DOCX artifacts rather than in
	preparation/structure artifacts.

Corpus policy for this workflow:

1. `lietaer-pdf-full-benchmark` (`tests/sources/book/Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.pdf`) is the canonical full-book PDF for routine structure iteration.
2. `ui-parity-pdf-structural-recovery` is still a `full` tier translate profile; despite its name, structure recognition is deterministic (importer-driven) and there is no AI structure stage.
3. `mazzucato-pdf-full-benchmark` (`tests/sources/book/The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).pdf`) is the non-Lietaer full-book PDF benchmark for WS-2 formatting-transfer generalization.

## Canonical Entry Points

Visible VS Code path:

```text
Tasks: Run Task -> Run Structure Recovery Diagnostic (First 20 Pages)

General full-tier path:

```text
Tasks: Run Task -> Run Lietaer Real Validation
```
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

Use `tests/artifacts/real_document_pipeline/lietaer_validation_latest.json` as the source of truth for the latest run.

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
- resolved runtime config and explicit runtime overrides relative to UI defaults

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

The exceptional quality gate is intentionally excluded from the normal full-suite path. It is available only through the dedicated task/script so expensive real-document validation does not contaminate ordinary regression runs.

## Corpus Workflow

To add a new reusable real-document regression case:

1. register the document in `corpus_registry.toml` with structural expectations and provenance;
2. bind it to an existing run profile or add a new run profile there;
3. let ordinary pytest pick it up through corpus-backed extraction and structural tests;
4. use the dedicated full-tier task only when model-backed parity or quality-gate coverage is needed.
