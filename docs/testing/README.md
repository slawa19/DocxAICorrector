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
| `unit-contract` | fast unit and contract behavior without external binaries or secrets | `bash scripts/test.sh tests/ -q -m "not integration"` after marker rollout |
| `compat-legacy` | legacy aliases, tuple-shape guards, rollback compatibility | targeted pytest selectors or `-m compat_legacy` |
| `static-workflow` | CI/tasks/scripts/docs workflow contracts that should stay cheap and deterministic | targeted static workflow file selectors |
| `typecheck` | pyright and typing gates | `bash scripts/test.sh tests/test_typecheck.py -q` |
| `integration-local` | broader local integrations without mandatory external API secrets | targeted file selectors |
| `system-deps` | real conversion paths that need Pandoc/LibreOffice/antiword | targeted corpus or generation selectors in prepared WSL runtime |
| `browser-ui` | real browser-backed Streamlit smoke | missing in the current suite; planned follow-up tier |
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
- scope: no-skip legacy DOC extraction, no-skip PDF extraction, structural passthrough, and structural diagnostic artifact capture.

Если документ описывает point-in-time review, handoff или snapshot состояния, ему не место в этой папке.
