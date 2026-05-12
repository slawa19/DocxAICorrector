# Testing Docs

В этой папке лежит актуальная тематическая документация по универсальной test system и real-document validation workflow.

Канонические документы здесь:

- `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`
- `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`
- `docs/testing/TEST_TIER_INVENTORY.md`

## Test Tiers

Текущая рабочая taxonomy для suite:

| Tier | Что доказывает | Типичный запуск |
|---|---|---|
| `unit-contract` | fast unit and contract behavior without external binaries or secrets | `bash scripts/test.sh tests/ -q -m "not static_workflow and not typecheck and not system_deps and not manual_ai_heavy and not browser_ui"` for the current PR-safe pytest path |
| `compat-legacy` | legacy aliases, tuple-shape guards, rollback compatibility | targeted pytest selectors or `-m compat_legacy` |
| `static-workflow` | CI/tasks/scripts/docs workflow contracts that should stay cheap and deterministic | targeted static workflow file selectors |
| `typecheck` | pyright and typing gates | `bash scripts/test.sh tests/test_typecheck.py -q` |
| `integration-local` | broader local integrations without mandatory external API secrets | targeted file selectors |
| `system-deps` | real conversion paths that need Pandoc/LibreOffice/antiword but not API secrets | targeted corpus or generation selectors in prepared WSL runtime |
| `browser-ui` | real browser-backed Streamlit smoke | explicitly deferred for now: the repo has no Playwright or `streamlit.testing` harness yet, so browser smoke remains a planned follow-up tier rather than an implied existing signal |
| `manual-ai-heavy` | opt-in real API or operator-visible heavy validation | explicit env-gated selectors and dedicated tasks/scripts |

Marker naming in pytest uses underscores (`unit_contract`, `compat_legacy`, `static_workflow`, `integration_local`, `system_deps`, `browser_ui`, `manual_ai_heavy`) even when docs refer to the tier labels with hyphens.

## Current Phase 0 Scope

Phase 0 does not change test behavior. It establishes:

- marker taxonomy in `pyproject.toml`;
- provisional primary-tier inventory for every top-level `tests/test_*.py` file;
- explicit opt-in markers for real AI/API, live image API, real-document quality gate, audiobook sanity, and obvious legacy compatibility guards.

Phase 1 workflow split starts with a dedicated static contract file:

- `tests/test_script_contract_static.py` carries CI-safe workflow/task/docs/script contract checks plus shell syntax validation;
- `tests/test_script_workflow_smoke.py` keeps env-sensitive subprocess/PowerShell/WSL/process smoke behind `DOCXAI_SKIP_WORKFLOW_SMOKE`.

Phase 4 system-deps validation now also has a manual GitHub Actions path:

- workflow: `Real Document Validation`;
- scope: no-skip legacy DOC extraction and no-skip PDF extraction on repository-backed sources, without relying on API secrets.

Phase 8 manual AI-heavy validation now also has dedicated `workflow_dispatch` paths:

- workflow: `Real Document Quality Gate`;
- scope: `bash scripts/run-real-document-quality-gate.sh` with `DOCXAI_RUN_REAL_DOCUMENT_QUALITY=1` and `OPENAI_API_KEY`;
- workflow: `Real Document AI Structure Smoke`;
- scope: `tests/test_real_document_structure_recognition_integration.py` with explicit `DOCXAI_RUN_REAL_DOCUMENT_STRUCTURE_RECOGNITION=1` and `OPENAI_API_KEY`;
- workflow: `Real Document Audiobook Sanity`;
- scope: `tests/test_real_document_audiobook_spec.py` with explicit `DOCXAI_RUN_REAL_DOCUMENT_AUDIOBOOK_SANITY=1` and `OPENAI_API_KEY`.

## Browser UI Deferral

Phase 7 browser smoke is explicitly deferred until the repository adopts one concrete harness instead of ad-hoc browser usage.

Current decision:

- do not claim a `browser-ui` signal in the suite yet;
- prefer either Playwright as the future automated harness or a clearly documented Streamlit/browser smoke path built on the repo's integrated-browser workflow;
- treat integrated browser debugging and manual UI checks as operator workflows, not as a shipped automated regression tier.

Если документ описывает point-in-time review, handoff или snapshot состояния, ему не место в этой папке.
