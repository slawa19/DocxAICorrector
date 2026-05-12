# Спецификация: поэтапный рефакторинг тестового покрытия

Дата: 2026-05-11
Статус: черновик для внедрения
Цель: превратить текущий большой набор тестов в понятную tiered-систему, где быстрые unit/contract tests, legacy guards, integration tests, system-deps проверки и manual AI-heavy gates дают разные, явно обозначенные сигналы.

## 1. Контекст

В проекте уже больше 1000 тестов. Фактическая проблема не в объеме, а в качестве сигнала:

- часть тестов проверяет исторические legacy/heuristic-first контракты и может направлять новые фиксы против текущей AI-first архитектуры;
- значительная доля UI/app/preparation тестов проверяет приватную реализацию, exact Streamlit call order и внутренние словари вместо пользовательского поведения;
- CI запускает Python-only suite и не доказывает real PDF/DOC/system dependency paths;
- workflow smoke tests выключены в CI целиком через `DOCXAI_SKIP_WORKFLOW_SMOKE=1`, поэтому вместе с env-sensitive smoke выключаются и дешевые static workflow checks;
- real-document heavy paths существуют как local/operator tasks, но не как явные CI/manual tiers с artifact upload;
- документация по test workflow и `corpus_registry.toml` частично разошлись.

Текущий suite остается ценным. Эта спецификация не предлагает массовое удаление тестов. Основная задача: классифицировать тесты, повысить достоверность CI-сигнала, добавить недостающие сквозные проверки и постепенно уменьшить хрупкость.

## 2. Цели

1. Ввести явные test tiers и правила, что именно доказывает каждый tier.
2. Отделить CI-safe static/contract checks от env-heavy smoke checks.
3. Сделать real-document PDF/DOC checks честными: либо system dependencies есть и selected profiles реально выполняются, либо skip считается failure в соответствующем tier.
4. Сохранить legacy tests как compatibility guards, но убрать их из mental model текущего AI-first happy path.
5. Снизить хрупкость UI/preparation tests за счет перехода от private call-order assertions к behavior/integration assertions.
6. Добавить недостающие UI/runtime/pipeline, browser, real PDF conversion, race и malformed-document tests.
7. Синхронизировать docs, registry и CI workflows.
8. Сохранить canonical runtime contract из `AGENTS.md`: финальная pytest/runtime verification для shell-bound сценариев идет через WSL/project entrypoints и существующие scripts/tasks.

## 3. Non-Goals

- Не переписывать весь test suite сразу.
- Не удалять legacy tests без предварительной маркировки, quarantine и проверки, что они не являются единственным regression guard.
- Не превращать ordinary PR CI в full AI/API real-document validation.
- Не требовать API secrets для mandatory PR checks.
- Не заменять unit tests browser tests; browser tests должны закрыть только ключевые user journeys.
- Не подменять canonical shell-bound validation debug-only Windows/pytest path.
- Не менять бизнес-логику pipeline, structure recovery или UI в рамках этой спецификации, кроме минимальных testability seams при необходимости.

## 4. Target Test Tier Model

Итоговая система должна иметь такие tiers:

| Tier | Назначение | Пример запуска | CI policy |
|---|---|---|---|
| `unit-contract` | Быстрые pure/unit и contract tests без внешних tools | `bash scripts/test.sh tests/ -q -m "not integration"` или текущий full pytest после маркировки | Mandatory PR |
| `compat-legacy` | Legacy/rollback guards, старые tuple aliases, heuristic-first compatibility | selected pytest markers/files | Mandatory или scheduled, но явно помечено |
| `static-workflow` | CI/tasks/scripts/docs/static contracts без WSL/PowerShell/process smoke | dedicated test file + `bash -n scripts/*.sh` | Mandatory PR |
| `typecheck` | Pyright no-errors gate | `bash scripts/test.sh tests/test_typecheck.py -q` или direct pyright job | Mandatory PR, fail-hard |
| `integration-local` | Mocked service integration and real small DOCX without system deps | selected pytest files | Mandatory PR or split job |
| `system-deps` | LibreOffice/Pandoc/antiword/PDF/DOC real conversion | selected corpus tests in Ubuntu/WSL with apt deps | Scheduled/manual or protected branch |
| `browser-ui` | Real Streamlit/browser smoke | Playwright/Streamlit smoke path | Scheduled/manual initially |
| `manual-ai-heavy` | API/secrets real-document quality gates | quality gate scripts/tasks | workflow_dispatch only |

Marker naming can be adjusted during implementation, but the distinction must be explicit in files, docs and CI.

## 5. Current High-Value Tests To Preserve

These tests are core assets and should not be deleted during tiering:

- AI-first Stage 1/2/3 contracts: `tests/test_document_map.py`, `tests/test_structure_recognition.py`, `tests/test_structure_reconciliation.py`.
- Preparation orchestration contracts: current AI-first sections in `tests/test_preparation.py`.
- Stage 0 signal-only and post-AI authority boundaries: `tests/test_document_structure_repair.py`, `tests/test_document_layout_cleanup.py`, `tests/test_document_extraction.py`, `tests/test_structure_validation.py`, `tests/test_document_structure_blocks.py`.
- Pipeline/output validation: `tests/test_document_pipeline.py`, `tests/test_document_pipeline_failures.py`, `tests/test_document_pipeline_output_validation.py`.
- Image XML/policy coverage: `tests/test_image_*.py`, especially reinsertion/reconstruction/validation/generation.
- Config/model registry: `tests/test_config.py`, `tests/test_model_registry_sweep.py`.
- Real-document corpus and runner schema: `tests/test_real_document_validation_corpus.py`, `tests/test_real_document_pipeline_validation.py`.
- Runtime artifact retention and result artifact contracts: `tests/test_runtime_artifacts.py`, `tests/test_runtime_artifact_retention.py`.

## 6. Compatibility/Quarantine Candidates

These tests should remain initially, but be marked or grouped so they are not mistaken for current happy-path architecture:

- Legacy heuristic-first structure recovery tests where Stage 0 heuristics bind final TOC/heading/body authority.
- Legacy extraction tests around `structure_recovery_mode = "legacy"`.
- UI tuple compatibility tests such as legacy sidebar tuple lengths.
- Legacy prompt-loader fallback tests for removed/old settings.
- Old semantic image path tests when reconstruction is disabled.
- Compare panel no-op tests, if compare-all manual apply is intended to become user-facing.
- Exact full-string cache-key tests where only parameter sensitivity matters.

Target location can be either markers (`@pytest.mark.compat_legacy`) or folder grouping (`tests/compat/`) depending on how invasive the move would be. Start with markers to minimize churn.

## 7. Phase 0: Inventory And Marking

### Objective

Create a factual map of the current suite without behavior changes.

### Required Work

1. Add a lightweight generated or manually maintained test inventory document, for example `docs/testing/TEST_TIER_INVENTORY.md`.
2. Classify existing files into provisional tiers:
   - unit/contract;
   - integration-local;
   - compat-legacy;
   - system-deps;
   - manual-ai-heavy;
   - static-workflow;
   - browser-ui missing.
3. Add pytest markers in `pyproject.toml` for the new taxonomy.
4. Mark obvious opt-in tests consistently:
   - real AI/API tests;
   - live image API tests;
   - real-document quality gate;
   - audiobook sanity;
   - legacy compatibility tests.
5. Add a short section to `docs/testing/README.md` explaining the tiers.

### Acceptance Criteria

- Every top-level test file has an assigned primary tier in the inventory.
- `pyproject.toml` lists all introduced markers.
- No test behavior changes are required in this phase.
- Full ordinary pytest still collects the same mandatory tests as before, except explicitly opt-in tests remain opt-in.

### Verification

Use canonical project path after checking worktree state:

```bash
git status --porcelain
bash scripts/test.sh tests/test_config.py -q
bash scripts/test.sh tests/test_script_workflow_smoke.py -q -k "not run_test_file_smoke and not run_test_node_smoke"
```

If the shell is not WSL, use the repository-approved `wsl.exe -d Debian ...` transport from `AGENTS.md` for canonical proof.

## 8. Phase 1: Static Workflow Checks Split

### Objective

Stop losing cheap workflow/CI/static coverage when env-heavy smoke tests are disabled.

### Required Work

1. Split `tests/test_script_workflow_smoke.py` into at least two files:
   - `tests/test_script_contract_static.py` for CI-safe static checks;
   - `tests/test_script_workflow_smoke.py` for subprocess/PowerShell/WSL/process smoke.
2. Move these checks to the static file:
   - `.vscode/tasks.json` command contract;
   - `.github/workflows/ci.yml` canonical command contract;
   - CODEOWNERS/script ownership checks;
   - docs mention canonical setup/test scripts;
   - source bootstrap snippets for Python runner scripts;
   - rejection of legacy workflow wrappers when check is static-only.
3. Keep actual subprocess smoke tests behind env-sensitive markers or `DOCXAI_SKIP_WORKFLOW_SMOKE`.
4. Add shell syntax checks for scripts:
   - `bash -n scripts/*.sh` in CI or via pytest wrapper;
   - line-ending/executable-bit checks if needed.
5. Update CI so static workflow checks run even when workflow smoke is skipped.

### Acceptance Criteria

- `DOCXAI_SKIP_WORKFLOW_SMOKE=1` no longer disables static workflow/CI/tasks/script contract tests.
- CI fails if `scripts/test.sh` is no longer the canonical pytest entrypoint.
- CI fails on shell syntax errors in repository shell scripts.
- Env-heavy smoke remains available locally/operator-side.

### Verification

```bash
git status --porcelain
bash scripts/test.sh tests/test_script_contract_static.py -q
bash -n scripts/test.sh scripts/setup-wsl.sh scripts/project-control-wsl.sh scripts/run-real-document-validation.sh scripts/run-structural-preparation-diagnostic.sh scripts/clean-stale-run-artifacts.sh
```

## 9. Phase 2: Registry, Docs And Skip Policy Hardening

### Objective

Make `corpus_registry.toml`, testing docs and real-document skip policy consistent and auditable.

### Required Work

1. Add registry schema tests:
   - every document has `id`, `source_path`, `artifact_prefix`, `output_basename`, `default_run_profile`, `tags`, `provenance`;
   - every `default_run_profile` and `structural_run_profile` exists;
   - every `structural_expected_result` is `pass` or `fail`;
   - every tolerant/non-strict profile has `tolerance_reason` or an explicit documented exception;
   - benchmark-only profiles are tagged `benchmark-only` and excluded from mandatory full gates by policy;
   - real source paths resolve under allowed repository source locations.
2. Resolve docs drift:
   - either add `expected_acceptance_policy` to registry or remove/update that requirement from `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`;
   - update `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md` so current profiles and mappings are not stale.
3. Add docs/registry consistency tests:
   - scripts mentioned in testing docs exist;
   - VS Code tasks mentioned in testing docs exist;
   - run profiles mentioned in testing docs exist in `corpus_registry.toml`.
4. Add explicit skip policy tests:
   - missing LibreOffice/Pandoc/provider key produces controlled skip in ordinary tier;
   - prepared system-deps tier can invert that policy and fail on skip.

### Acceptance Criteria

- Registry schema is validated independently of running real documents.
- Testing docs no longer require fields absent from registry.
- Current canonical profiles are discoverable from docs or generated inventory.
- Skip reasons for capability-sensitive corpus tests are controlled and specific.

### Verification

```bash
git status --porcelain
bash scripts/test.sh tests/test_real_document_validation_corpus.py -q -k "registry or profile or runtime_resolution"
bash scripts/test.sh tests/test_script_contract_static.py -q
```

## 10. Phase 3: Typecheck And Model-Literal Gates

### Objective

Make static correctness gates fail hard in CI and broaden model drift protection.

### Required Work

1. Keep `tests/test_typecheck.py` for local proof, but make CI typecheck fail-hard:
   - pyright missing is CI failure;
   - pyright timeout is CI failure;
   - baseline remains `0`.
2. Optionally add a direct CI pyright command before or instead of pytest wrapper.
3. Expand `tests/test_model_registry_sweep.py` beyond image modules:
   - `src/docxaicorrector/processing`;
   - `src/docxaicorrector/pipeline`;
   - `src/docxaicorrector/validation`;
   - `src/docxaicorrector/ui`;
   - real-document runner scripts where model literals can drift.
4. Maintain an explicit whitelist for test fixtures, docs examples and config defaults.

### Acceptance Criteria

- CI cannot pass typecheck by skipping pyright.
- New hardcoded canonical model literals outside config/fixtures are caught.
- Local behavior remains understandable if pyright is absent, but CI semantics are strict.

### Verification

```bash
git status --porcelain
bash scripts/test.sh tests/test_typecheck.py -q
bash scripts/test.sh tests/test_model_registry_sweep.py -q
```

## 11. Phase 4: System-Deps Real-Document CI Tier

### Objective

Separate Python-only PR checks from real conversion/proof checks that require LibreOffice/Pandoc/antiword.

### Required Work

1. Add a CI job or manual workflow that installs `system-requirements.apt`.
2. Run selected corpus checks with no-skip enforcement:
   - `religion-wealth-core` extraction for legacy `.doc` conversion;
   - `end-times-pdf-core` extraction for PDF conversion;
   - `lietaer-pdf-first-20-structure-core` structural diagnostic/passthrough.
3. Upload artifacts on failure:
   - validation report JSON;
   - summary TXT;
   - progress JSON;
   - markdown/docx output when produced;
   - formatting diagnostics.
4. Keep mandatory PR CI Python-only unless runtime cost is acceptable.
5. Add a helper or marker option such as `DOCXAI_REQUIRE_REAL_DOCUMENT_CAPABILITIES=1` to convert selected skips into failures.

### Acceptance Criteria

- There is at least one automated path where PDF/legacy DOC conversion is actually exercised, not skipped.
- Selected canonical profiles fail if source files or required system tools are unavailable.
- Failure artifacts are available from CI/manual workflow.

### Verification

Canonical local/system path:

```bash
git status --porcelain
bash scripts/test.sh tests/test_real_document_validation_corpus.py::test_corpus_extraction -vv
bash scripts/run-structural-preparation-diagnostic.sh lietaer-pdf-first-20-structure-core
```

For agent-side WSL transport, use `wsl.exe -d Debian` only when current shell is not already WSL.

## 12. Phase 5: AI-First Integration Test Simplification

### Objective

Reduce over-mocking in `tests/test_preparation.py` while preserving its valuable contracts.

### Required Work

1. Add small helpers for repeated AI-first config setup, if not already sufficient:
   - `_make_ai_first_config(**overrides)`;
   - minimal fake model registry builder;
   - compact fake client/response builders.
2. Add one compact non-real-document integration test:
   - construct a small document with front matter, TOC and body headings;
   - run extraction/preparation with fake Stage 1 DocumentMap and fake Stage 2 output;
   - apply Stage 3 reconciliation;
   - assert final relations/semantic blocks/jobs use post-AI authority.
3. Convert only the most brittle preparation tests from deep monkeypatch orchestration to helper-based behavior tests.
4. Leave detailed edge-case unit tests for Stage 1/2/3 modules in their existing files.

### Acceptance Criteria

- At least one AI-first preparation path is tested end-to-end on a compact deterministic fixture without real API calls.
- New AI-first tests assert final behavior, not just that private functions were called.
- `tests/test_preparation.py` starts shrinking or at least stops growing in boilerplate per scenario.

### Verification

```bash
git status --porcelain
bash scripts/test.sh tests/test_preparation.py -q -k "ai_first or document_map or reconciliation"
bash scripts/test.sh tests/test_document_map.py tests/test_structure_recognition.py tests/test_structure_reconciliation.py -q
```

## 13. Phase 6: UI/Runtime/Pipeline Integration Tests

### Objective

Close the gap between isolated UI branch tests and isolated pipeline tests.

### Required Work

1. Add a full local integration test on a tiny DOCX:
   - application flow creates prepared context;
   - runtime events are emitted and drained;
   - processing service runs with fake model client;
   - final session state contains result bundle;
   - `.run/ui_results/*.result.md` and `.result.docx` are saved or captured through real artifact writer.
2. Add malformed document UI boundary tests:
   - corrupted DOCX;
   - broken relationships;
   - encrypted/protected input if feasible;
   - oversized or suspicious embedded image metadata;
   - PDF without conversion capability produces user-facing error or controlled skip depending tier.
3. Add race/stale-event tests:
   - upload changes during preparation;
   - stale worker event with old file token is ignored;
   - stop during PDF materialization;
   - stop during image generation/validation;
   - completed source cache is not confused with output artifacts.
4. Keep exact Streamlit call-order tests only where widget key/order is a real user-visible contract.

### Acceptance Criteria

- There is a single non-browser integration test proving UI/runtime/pipeline handoff to final artifacts.
- Malformed input failures do not surface as uncaught Streamlit exceptions.
- Stale worker events cannot mutate the active file/session result.

### Verification

```bash
git status --porcelain
bash scripts/test.sh tests/test_application_flow.py tests/test_processing_runtime.py tests/test_document_pipeline.py -q
bash scripts/test.sh tests/test_runtime_artifacts.py -q
```

## 14. Phase 7: Browser UI Smoke

### Objective

Add at least one real Streamlit/browser journey that proves the app frame works outside mocked `st.*` calls.

### Required Work

1. Choose tool and harness:
   - Playwright is preferred if accepted as dev dependency;
   - otherwise a minimal Streamlit subprocess plus HTTP/browser smoke can be introduced.
2. Implement a single smoke journey:
   - app starts;
   - upload small DOCX;
   - preparation completes;
   - processing starts with fake/no-network model path;
   - result bundle is visible;
   - download controls exist for Markdown/DOCX.
3. Keep this tier opt-in or scheduled initially.
4. Record screenshots/logs/artifacts on failure.

### Acceptance Criteria

- At least one test exercises real Streamlit runtime and browser/page interaction.
- The test is not required for every local edit loop.
- Failure output is actionable: app log, browser trace/screenshot, relevant `.run` artifacts.

### Verification

Use the eventual browser tier command documented in `docs/testing/README.md`. Until the harness exists, this phase has no canonical command.

## 15. Phase 8: Compare-All, Image Visual And Manual AI Gates

### Objective

Cover product-quality surfaces that unit tests cannot prove.

### Required Work

1. Replace compare panel no-op tests once UI behavior exists:
   - render completed compare variants;
   - select variant;
   - apply selected variant;
   - result state/artifact updates correctly;
   - incomplete compare assets are hidden or shown with explicit status.
2. Add deterministic visual/image checks where feasible:
   - reconstructed diagram dimensions/layout do not regress;
   - reinsertion placement survives DOCX openability check;
   - compare-all multi-variant payload renders expected metadata.
3. Add manual GitHub Actions workflows:
   - real-document quality gate with secrets;
   - AI structure smoke;
   - audiobook sanity;
   - artifact upload on failure and success.
4. Document when maintainers should run each manual gate.

### Acceptance Criteria

- Compare-all user-facing mode is covered at UI level if it is shipped.
- Heavy AI/API gates are executable through `workflow_dispatch`, not only local tribal knowledge.
- Manual workflows publish the same artifacts described in testing docs.

## 16. Refactoring Rules

During implementation:

1. Prefer adding markers and moving tests gradually over mass deletion.
2. Do not weaken assertions without replacing them with behavior-level coverage.
3. When converting a brittle exact-call UI test, preserve the user-visible contract being tested: visible label, action returned, session state transition, artifact saved, or event emitted.
4. Keep legacy compatibility assertions, but mark them as compatibility so they do not drive current design decisions.
5. Do not add new real API requirements to mandatory PR CI.
6. Do not use Windows debug-only pytest runs as proof for shell-bound specs, real-document validation, quality gates or system-deps scenarios.
7. Before final verification claims, check dirty worktree with `git status --porcelain`.

## 17. Proposed File/CI Changes Summary

Expected new or changed files over the whole refactor:

- `pyproject.toml`: pytest markers.
- `docs/testing/TEST_TIER_INVENTORY.md`: tier map.
- `docs/testing/README.md`: tier overview and commands.
- `docs/testing/REAL_DOCUMENT_VALIDATION_WORKFLOW.md`: current profile mapping update.
- `docs/testing/UNIVERSAL_TEST_SYSTEM_MAINTENANCE_GUIDE_2026-03-21.md`: registry field policy correction.
- `tests/test_script_contract_static.py`: static workflow checks split out of smoke.
- `tests/test_registry_contract.py` or equivalent: corpus registry schema/docs consistency.
- `tests/test_shell_script_contract.py` or CI step: `bash -n`/line ending/executable checks.
- `.github/workflows/ci.yml`: static workflow, typecheck and possibly shell syntax jobs.
- `.github/workflows/real-document-validation.yml`: optional/manual system-deps and AI-heavy gates.
- Focused additions to `tests/test_preparation.py`, `tests/test_application_flow.py`, `tests/test_processing_runtime.py`, `tests/test_runtime_artifacts.py`.
- Optional browser harness files once Phase 7 starts.

## 18. Rollout Order

Recommended order:

1. Phase 0 inventory and markers.
2. Phase 1 static workflow split.
3. Phase 2 registry/docs/skip policy.
4. Phase 3 typecheck/model literal hardening.
5. Phase 4 system-deps real-document tier.
6. Phase 5 AI-first integration simplification.
7. Phase 6 UI/runtime/pipeline integration.
8. Phase 7 browser smoke.
9. Phase 8 compare-all/image/manual AI gates.

This order intentionally improves CI truthfulness before broad test rewrites.

## 19. Completion Criteria

The refactor can be considered complete when:

- mandatory PR CI has explicit static workflow, typecheck, unit/contract and integration-local signals;
- system-deps profile checks can be run automatically or manually with no-skip enforcement;
- testing docs and registry agree;
- legacy/compatibility tests are clearly marked;
- at least one compact AI-first integration test covers preparation through final downstream authority;
- at least one UI/runtime/pipeline integration test proves final user artifacts;
- at least one browser smoke exists or a documented decision explicitly defers it;
- heavy real-document/API gates are available as manual workflows with artifact upload.
