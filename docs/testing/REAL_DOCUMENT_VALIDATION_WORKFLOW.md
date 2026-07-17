# Real Document Validation Workflow

Canonical full-tier real-document regression target: `tests/sources/book/Rethinking-money_-How-new-currencies-turn-scarcity-into-prosperity-Bernard-Lietaer-Jacqui-Dunne.pdf` (profile `lietaer-pdf-full-benchmark`).

Canonical registry for universal real-document validation: `corpus_registry.toml`. The corpus now contains only the real full books under `tests/sources/book/`.

Current default mapping:

- default document profile: `lietaer-pdf-full-benchmark`
- additional full-book document profiles: `mazzucato-pdf-full-benchmark`, `creatingwealth-pdf-full-benchmark`, held-out `money-sustainability-pdf-full-heldout`
- full run profile: `ui-parity-default`
- soak run profile: `ui-parity-soak-3x`
- structural run profile: `ui-parity-translate-benchmark-advisory`
- audiobook postprocess run profile: `ui-parity-translate-audiobook-postprocess`
- benchmark-only advisory run profile: `ui-parity-translate-benchmark-advisory`

NOTE (2026-06-22): the AI structure-recognition stage (#2) and its profiles
(`ui-parity-ai-default`, `structural-ai-first-default`, `structural-passthrough-default`,
`*topology-advisory`) have been removed. Preparation is now deterministic: importer-provided
roles flow straight to planning, so there is no `structure_recognition_mode` contract to track.

Current corpus notes:

- `lietaer-pdf-full-benchmark` is the default full-book PDF profile for structure-model comparison on the full Lietaer source.
- `mazzucato-pdf-full-benchmark` is the non-Lietaer full-book PDF benchmark for WS-2 role-aware formatting-transfer generalization.
- `creatingwealth-pdf-full-benchmark` is the epub-derived full-book PDF benchmark.
- `money-sustainability-pdf-full-heldout` is the held-out full-book PDF benchmark for Stage 2 baseline validation.
- All four are full-book profiles in `tests/sources/book/`; the benchmark-only ones use `ui-parity-translate-benchmark-advisory` and are excluded from mandatory full gates by policy.

## Structure Diagnostic Workflow

The AI-first structure-recognition stage (#2) was removed (2026-06-22); structure roles
now come deterministically from the importer. The structure-scoped diagnostic loop below
remains useful for inspecting importer-produced structure on the PDF slices.

Use this structure-scoped order:

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

The quality-gate script runs the maintained real-document corpus selector `tests/test_real_document_validation_corpus.py` with `-vv -s` under `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1`, so the terminal shows the live pytest stream and the capability-sensitive corpus extraction/structural checks fail the gate (instead of skipping) when a required conversion capability, real-document source, or structural expectation is missing.

The manual `Real Document Validation` workflow is the Phase 4 system-deps path. It installs `system-requirements.apt`, forces `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1`, runs the no-skip full-book PDF extraction selectors for `mazzucato-pdf-full-benchmark` and `lietaer-pdf-full-benchmark`, and uploads `.run/` plus `tests/artifacts/real_document_pipeline/` for inspection.

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

## AI Structure Recognition Smoke (removed)

The AI structure-recognition stage (#2) and its real-document smoke test
(`tests/test_real_document_structure_recognition_integration.py`) were removed
(2026-06-22). Structure roles are now produced deterministically by the importer, so
there is no AI structure-recognition smoke path or `DOCXAI_RUN_REAL_DOCUMENT_STRUCTURE_RECOGNITION`
toggle. The `Real Document AI Structure Smoke` GitHub Actions workflow that invoked the
removed test has also been retired; there is no active AI structure-recognition smoke
workflow, task, or pytest selector.

Use the maintained user-visible real-document paths instead:

```text
Tasks: Run Task -> Run Lietaer Real Validation
Tasks: Run Task -> Run Lietaer Real Validation AI
```

## Environment Contract

- Use the WSL project environment in `.venv`.
- Do not run the validator through a Windows virtualenv from WSL.
- Do not assume the standalone validator inherits the correct import root from the shell.
- The validator now self-bootstraps the repository root into `sys.path`, but the canonical runtime remains WSL `.venv`.
- Legacy `.doc` validation requires either LibreOffice (`soffice`) or the fallback pair `antiword` + `pandoc` inside WSL.
- PDF import validation uses the deterministic text-layer importer for
  selectable-text PDFs. LibreOffice `writer_pdf_import` is no longer the runtime
  fallback for PDF input.

## CI-Parity Notes For Corpus Debugging

The full-book corpus profiles are PDF sources under `tests/sources/book/`, so corpus extraction and structural passthrough depend on the PDF text-layer importer plus `pandoc` being available in the runner.

Consequences for debugging:

- green local pytest in a developer WSL environment does not automatically prove green CI;
- CI may fail only because a clean Ubuntu runner lacks `pandoc` or the PDF toolchain;
- extraction-tier and structural-tier corpus tests for the PDF corpus profiles should be treated as capability-sensitive, not as pure business-logic tests.

When a CI run fails on corpus extraction or structural passthrough for a PDF profile, check capability first:

```bash
python -c "import pdfminer, docx"
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
