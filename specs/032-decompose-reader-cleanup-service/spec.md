# Feature Specification: Decompose reader_cleanup_mvp/service.py (behaviour-preserving)

Date: 2026-07-15
Status: **PLANNED (Wave 3 / decomposition, module 2 of 5).** Pure structural refactor of the 4932-line
`reader_cleanup_mvp/service.py` into cohesive `_`-prefixed submodules, one cluster per commit, characterization
golden first. No behaviour change.
Owner surface: `reader_cleanup_mvp/service.py` (shrinks to the orchestrator + re-export shim), new
`reader_cleanup_mvp/_*.py`, and a new characterization test.

## Problem + favourable facts (verified)

The module co-locates config/constants, models, prompt builders, block building, chunking, global-plan/payloads,
operation-planning detectors, reporting/stats, response parsing/recovery, apply/mutation, validation gates, small
utils, and the entry orchestrators. It is **much safer to split than late_phases** (verified by grep):
- **No module-level mutable state / singletons / caches / `global`** — all top-level `_UPPER` names are assign-once
  frozensets / compiled regexes / dicts; all dataclasses `@dataclass(frozen=True)`.
- **No LLM in the module** — the model is reached only via injected `*_provider` callables; no SDK import, no client
  construction. Characterization runs fully offline with fake JSON-returning providers.
- **ZERO `service.<name>` monkeypatch sites** — no test patches any service attribute (verified multi-line, whole
  tree). So there are **no situation-2 repoints** anywhere in this split — re-export alone satisfies every consumer.

**The one re-export constraint:** the (gitignored) `tests/artifacts/real_document_pipeline/run_reader_cleanup_replay_experiment.py`
directly imports `READER_CLEANUP_DEFAULT_SELECTOR` and the private `_GENERIC_RUNNING_HEADER_TOKENS` from `.service`.
Those (both in the constants cluster) must stay re-exported from `service.py`. Public consumers import via the
`reader_cleanup_mvp` package facade (`__init__.py`), which re-exports from service — so re-exports keep them working.

## Mechanism (per step)

Move a cohesive cluster verbatim to `reader_cleanup_mvp/_<name>.py`; in `service.py` add
`from ._<name> import <symbols>  # noqa: F401` so `service.<name>` and `from ...service import <name>` keep resolving.
Function-local imports only where a load-time cycle would otherwise form; bodies byte-identical. No patch-site
repointing needed anywhere (empty monkeypatch surface).

## Scope — staged (13 clusters C0-C13; least-risky leaf first, orchestrator last)

- **Step 0** — characterization golden (no move): `tests/test_reader_cleanup_service_characterization.py` snapshotting
  whole `result.cleaned_markdown` + canonical `result.report_payload` for 2-3 offline fixtures (multi-chunk +
  reannotation + anchor-repair), the 4 prompt-builder strings, and `build_cleanup_blocks` ids/hashes. Commit — safety net.
- **Step 1** — `_constants.py` (C0) — re-export ALL, esp. `_GENERIC_RUNNING_HEADER_TOKENS` +
  `READER_CLEANUP_DEFAULT_SELECTOR`; keep the `|`-merged guidance dicts together.
- **Step 2** — `_models.py` (C1, 9 frozen dataclasses — the spine every later module imports).
- **Step 3** — `_prompts.py` (C3, the 4 `build_*_system_prompt`).
- **Step 4** — `_utils.py` (C13) then `_config.py` (C2, uses utils).
- **Step 5** — `_blocks.py` (C4, `build_cleanup_blocks` + selection + layout signals).
- **Step 6** — `_report.py` (C9, reporting/stats/diagnostics/image-reconciliation — the cluster the payload golden
  most protects).
- **Step 7** — `_detectors.py` (C8, heading/side-heading detector family + `_build_operation_selection_targets`).
- **Step 8** — `_validate.py` (C12, safety gates + noise validators + sequence canonicalization; imports `_detectors`).
- **Step 9** — `_apply.py` (C11, mutation engine; imports `_validate`).
- **Step 10** — `_parse.py` (C10) + `_chunking.py` (C6) + `_planning.py` (C7): the interdependent middle; 2-3 commits
  with function-local imports where cycles threaten.
- **Step 11** — orchestrators (C5: `run_reader_cleanup` + siblings) STAY in `service.py`, which becomes a thin
  orchestrator + re-export shim.

## Test plan

After EVERY step: `tests/test_reader_cleanup_mvp.py` (156), `tests/test_reader_cleanup_structural_matrix.py`,
`tests/test_document_pipeline.py` (build_cleanup_blocks seam), and the new characterization golden — all green, no
golden diff. Import smoke both the package facade (`import docxaicorrector.reader_cleanup_mvp`) and the direct private
import (`from docxaicorrector.reader_cleanup_mvp.service import _GENERIC_RUNNING_HEADER_TOKENS, READER_CLEANUP_DEFAULT_SELECTOR`).

## Out of scope

- Behaviour changes (byte-identical relocation + re-export only).
- The other three large modules (formatting_transfer, structural, output_validation) — specs 033-035.

## SaaS rationale

Neutral; a cohesive, testable reader-cleanup layer is easier for a backend/worker to reuse and maintain.
