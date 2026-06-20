# Architectural Audit — DocxAICorrector

Date: 2026-06-20
Status: Active. Input for prioritised remediation work.
Scope: Production Python codebase, `src/docxaicorrector/` (~67k lines, 18 subpackages).
Method: Static analysis + manual code walk of the 6 heaviest modules (~19k lines combined).

Companion docs:
- `docs/specs/GLOBAL_PLAN_2026-06-16.md` — forward plan for the pipeline
- `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md`

---

## Scope and Audit Methodology

Focus was on defects with **real practical consequences**: data loss, silent incorrect
output, runtime AttributeError, maintenance fragility in hot paths. Academic pattern
violations without measurable impact were excluded.

Files examined in detail:

| File | Lines |
|------|-------|
| `reader_cleanup_mvp/service.py` | 4 932 |
| `pipeline/late_phases.py` | 4 321 |
| `processing/preparation.py` | 3 415 |
| `generation/formatting_transfer.py` | 3 379 |
| `validation/structural.py` | 3 162 |
| `core/config.py` + 4 sibling config modules | ~4 000 |

---

## Findings

---
### [CRITICAL] Silent exception swallowing in quality-gate import path

**Location:** `pipeline/late_phases.py`, lines 2944-2948,
function `_build_quality_gate_extra_fields`

**Defect:**
The deferred import of `validation.structural` is wrapped in a bare
`except Exception: return fields` with no `log_event` call and no re-raise:

```python
try:
    from docxaicorrector.validation import structural as structural_validation_runtime
except Exception:
    return fields   # no logging, no signal to caller or user
```

If `structural.py` fails to import (import cycle at runtime, missing transitive
dependency, AttributeError in its module body), the function silently returns an
empty `fields` dict. Every boolean quality-gate check defaults to False / absent,
and the pipeline treats the output as "validated — nothing to report."

**Real risk:**
The user receives a translated DOCX whose quality gate did not actually execute.
TOC-concat, heading density, and untranslated-body gates all silently pass.
Nothing appears in logs or in the UI result notice. Invisible correctness regression.

**Recommendation:**
Distinguish by exception type:

```python
try:
    from docxaicorrector.validation import structural as structural_validation_runtime
except ImportError as exc:
    log_event(logging.WARNING, "quality_gate_import_failed",
              "validation.structural import failed; quality gate fields skipped.",
              error=str(exc))
    return fields
# let other exceptions propagate — do not swallow
```

Long-term: resolve the pipeline-validation import cycle so the import moves to
module level (see next finding).

---
### [HIGH] Circular dependency between `pipeline` and `validation`

**Location:**
- `pipeline/late_phases.py:2944` — deferred `from docxaicorrector.validation import structural`
- `validation/structural.py:2408` — deferred `from docxaicorrector.pipeline._pipeline import run_document_processing`
- `validation/structural.py:18,28,43` — **module-level** imports of `pipeline.output_validation`,
  `pipeline.display_hygiene`, `processing.processing_service`

**Defect:**
Both packages import each other, with the cycle resolved only by pushing one direction
into function bodies to avoid Python's ImportError at startup. The deferred imports are
invisible to static analysis tools (`pyright`, AST dependency-graph scripts). A
module-level import added anywhere in the cycle instantly converts a deferred cycle
into a blocking import failure at startup.

The effective cross-package graph includes:
`processing -> pipeline -> validation -> pipeline` (cycle)

**Real risk:**
- Renaming `run_document_processing` in `_pipeline.py` does not produce a `pyright`
  error in `structural.py` — only a runtime `ImportError`.
- New module-level code in either `late_phases.py` or `structural.py` can silently
  turn the deferred cycle into a startup crash.

**Recommendation:**
1. Extract `run_document_processing` into `pipeline/runner.py` (thin public facade
   with no back-imports to `validation`).
2. Pass the runner to `structural.py` via a `Protocol` or DI rather than a direct import.
3. Add `tests/test_import_cycles.py` that AST-walks the package and asserts no mutual
   top-level imports between `pipeline` and `validation`.

---
### [HIGH] `reader_cleanup_mvp/service.py` — 4 932-line God Object with permanent MVP debt

**Location:** `reader_cleanup_mvp/service.py`, full file; single file in the subpackage

**Defect:**
One module carries 7+ unrelated responsibilities:

1. **Data types and serialisation** — `CleanupBlock`, `CleanupChunk`, `CleanupOperation`,
   `ReaderCleanupResult`, `AnchorRepairChunk`, …
2. **Prompt building** — four `build_reader_cleanup_*_system_prompt` functions
   (~400 lines of embedded prompt text)
3. **Chunk construction and selection** — `build_cleanup_blocks`, `_build_cleanup_chunks`,
   `_select_cleanup_blocks`
4. **AI call orchestration** — global plan pass, per-chunk operation pass,
   schema-repair pass, reannotation pass, anchor-repair pass
5. **Response parsing and validation** — `_parse_cleanup_response`,
   `_load_cleanup_response_object`, `_load_cleanup_response_payload`
6. **Schema repair** — second AI call when JSON is structurally invalid
7. **Diagnostic artifact writing** — `write_reader_cleanup_diagnostics`,
   `_write_quality_report_artifact`, `_write_reader_cleanup_lineage_artifact`

The `MVP` suffix in the package name is historically accurate: the module was intended
as a temporary implementation but has become the architectural centre of gravity for
all post-processing cleanup. Its only consumer is `pipeline/late_phases.py`.

Note: the module has **zero internal imports** from `docxaicorrector` — a strength for
isolation, but a symptom that all helpers are private to the file rather than reusable.

**Real risk:**
- Changing a prompt (semantically independent concern) requires opening the file that
  also contains AI retry logic and JSON parsing — merge conflicts are unavoidable.
- Adding a new operation type requires touching 10+ places across 4 900 lines.
- Unit tests must mock the entire `operation_provider` callback instead of isolating
  individual layers.

**Recommendation:**
Split into cohesive modules within the existing subpackage (no `__init__.py` API change):

```
reader_cleanup_mvp/
    blocks.py         # CleanupBlock, CleanupChunk, CleanupOperation, type aliases
    prompts.py        # all system-prompt builder functions
    chunking.py       # build_cleanup_blocks, _build_cleanup_chunks, _select_cleanup_blocks
    operations.py     # AI orchestration, response parsing, schema repair
    diagnostics.py    # artifact writing helpers
    service.py        # thin public facade, re-exports __all__
```

---
### [HIGH] `context / dependencies / emitters / state: Any` in 30+ functions in `late_phases.py`

**Location:** `pipeline/late_phases.py`, ~30 function signatures.
Representative: `_run_reader_cleanup_postprocess` (lines 1057-1060),
`_rebuild_docx_for_markdown` (lines 235-237).

**Defect:**
`ProcessingContext`, `ProcessingDependencies`, `ProcessingEmitters`, and `ProcessingState`
are fully typed frozen dataclasses in `pipeline/contracts.py`. `late_phases.py` does not
import them and annotates the corresponding parameters as `Any`. There are 89+ attribute
accesses on `context` alone (`context.app_config`, `context.model`,
`context.uploaded_filename`, `context.max_retries`, `context.processing_operation`, …).
None are type-checked.

```python
# current state — not type-checked by pyright
def _run_reader_cleanup_postprocess(
    *, context: Any, dependencies: Any, emitters: Any, state: Any, ...
) -> ReaderCleanupPostprocessResult:
    config = resolve_reader_cleanup_config(
        app_config=context.app_config, fallback_model=context.model
    )
```

**Real risk:**
A typo or renamed field in `ProcessingContext` produces an `AttributeError` at runtime
in production, only on the branch where that attribute is accessed. `pyright` reports
zero errors for these call sites today.

**Recommendation:**
```python
# Add to late_phases.py imports
from docxaicorrector.pipeline.contracts import (
    ProcessingContext, ProcessingDependencies, ProcessingEmitters, ProcessingState,
)
```
Replace all `Any` on pipeline-boundary parameters with the concrete types.
For test callers that pass lightweight mocks, introduce a `Protocol` with the
minimum required attribute surface.

---
### [MEDIUM] Non-atomic writes to restart store — risk of silent corruption

**Location:** `processing/restart_store.py:36`, `runtime/artifacts.py:152`

**Defect — restart store:**
```python
storage_path.write_bytes(source_bytes)      # direct write, no tmp + rename
if previous_storage_path != str(storage_path):
    clear_restart_source(previous_source)   # old file deleted after write
```
If the process is killed mid-write, `storage_path` exists but contains truncated bytes.
`load_restart_source_bytes` reads it without an integrity check — `OSError` is not raised
for a valid-but-short file, so the truncated buffer is returned as if valid. `python-docx`
then raises a cryptic `zipfile.BadZipFile` deep in the pipeline.

**Defect — result artifacts (`runtime/artifacts.py`):**
`markdown_path.write_text(...)` is on line 152, **outside** the `try` block. If that
write itself raises `OSError`, the rollback block (which starts at line 177) is never
reached, leaving a partially-written `.md` file. The rollback only covers failures that
occur after `.md` has already been written successfully.

**Real risk:**
A crash mid-way through storing a restart file for a 500-page book means the user cannot
resume processing. The corrupted restart file passes the `OSError` guard and causes a
downstream crash on reload. The user must re-upload and restart from scratch.

**Recommendation:**
```python
# restart_store.py — atomic write pattern
tmp_path = storage_path.with_suffix(".tmp")
tmp_path.write_bytes(source_bytes)
tmp_path.replace(storage_path)   # atomic on POSIX; os.replace() on Windows
```

Lightweight integrity sidecar:
```python
import hashlib
meta = {"size": len(source_bytes),
        "sha256": hashlib.sha256(source_bytes).hexdigest()}
storage_path.with_suffix(".meta.json").write_text(json.dumps(meta))
```

For `artifacts.py`: move `markdown_path.write_text(...)` inside the `try` block so the
rollback covers the full stem-group atomically.

---
### [MEDIUM] `load_app_config()` called without caching outside the UI layer

**Location:**
`document/boundaries.py:46`, `document/boundary_review.py:23`,
`document/relations.py:466`, `validation/structural.py:1423`,
`processing/preparation.py:3297`

**Defect:**
Each of these modules calls `load_app_config()` unconditionally inside its entry point.
`load_app_config()` reads `config.toml` from disk via `tomllib.load()` and re-evaluates
all environment variables on every call. Only `ui/_app.py` wraps it in
`@st.cache_resource`. During a single document preparation run, 4-5 redundant config
reads occur at different stages of the call chain.

**Real risk:**
1. **Correctness:** if an environment variable changes between calls within one run
   (e.g., via `python-dotenv` hot-reload in dev mode), different pipeline stages operate
   on diverging config snapshots.
2. **Performance:** 4-5 blocking TOML-parses + env-var lookups per document, all in the
   Streamlit main thread.

**Recommendation:**
Apply `functools.cache` directly on `load_app_config`:

```python
# core/config.py
import functools

@functools.cache
def load_app_config() -> AppConfig:
    ...
```

All existing call sites that already accept `app_config: Mapping | None = None` will
automatically short-circuit on subsequent calls within the same process lifetime.
For test isolation, reset with `load_app_config.cache_clear()`.

---

### [MEDIUM] No jitter in API retry backoff — thundering herd under concurrent load

**Location:** `generation/_generation.py:1019`, `image/shared.py:186`

**Defect:**
```python
time.sleep(min(2 ** (attempt - 1), 8))   # deterministic, no jitter
```
When multiple Streamlit sessions hit a `RateLimitError` simultaneously, all retry with
identical sleep durations (1 s, 2 s, 4 s, 8 s, 8 s, …) and wake up together,
reproducing the rate-limit spike. The two retry paths use different caps
(`_generation.py` = 8 s, `image/shared.py` default = 4 s), making cross-subsystem
behaviour inconsistent.

**Real risk:**
Under two or more concurrent user sessions, rate-limit recovery time is systematically
longer than necessary. All retries past attempt 3 sleep for the same fixed 8 s with no
load spreading.

**Recommendation:**
```python
import random
delay = min(2 ** (attempt - 1), max_backoff_seconds)
time.sleep(delay * random.uniform(0.75, 1.25))
```
Centralise the backoff formula in `call_responses_create_with_retry` (`image/shared.py`)
and have `_generation.py` delegate to that utility instead of its own sleep loop.

---
### [MEDIUM] `processing/preparation.py` — 3 415-line orchestration monolith

**Location:** `processing/preparation.py`, full file

**Defect:**
The file mixes five distinct concerns:

1. **Pipeline orchestration** — `prepare_document_for_processing()` and three
   `_run_*_stage()` functions (~1 500 lines total)
2. **Cache management** — 8 functions (`_read_cached_*`, `_store_cached_*`,
   `_build_*_cache_key`)
3. **Diagnostic artifact writing** — 12 `_write_*_debug_artifact` functions
4. **Business utility functions** — `humanize_quality_gate_reasons`,
   `build_structure_repair_status_note`, `build_layout_cleanup_status_note`
5. **Cache key construction** — `_build_structure_map_cache_key`,
   `_build_document_map_cache_key`, `build_prepared_source_key`

**Real risk:**
Changing the cache key schema (e.g., adding a new config flag that affects preparation
output) requires manually tracking all 6+ cache read/write sites and their key-builder
functions across 3 400 lines. A missed call site produces a silent cache invalidation
miss: the pipeline uses stale prepared structure on changed settings, with no error or
warning to the user.

**Recommendation:**
Extract by concern:

```
processing/
    preparation.py           # thin orchestrator (~300 lines)
    preparation_cache.py     # all _read/_store/_build_cache_key functions
    preparation_artifacts.py # all _write_*_debug_artifact functions
    stages/
        structure.py         # _run_structure_recognition
        document_map.py      # _run_document_map_stage
        topology.py          # _run_document_topology_projection_stage
```

Each stage module takes its dependencies as explicit arguments rather than reading from
closure-captured variables.

---
## Prioritised Top-5 for First-Fix

| # | Finding | Severity | Why first |
|---|---------|----------|-----------|
| 1 | Silent quality-gate import swallowing | CRITICAL | Actively degrades output correctness with zero signal. Fix is 3 lines. |
| 2 | `Any`-typed pipeline params in `late_phases.py` | HIGH | 89+ unchecked attribute accesses on the hot path. Any `ProcessingContext` API change silently breaks production. Fix is one import + type substitution. |
| 3 | `reader_cleanup_mvp` God Object | HIGH | Every cleanup iteration risks unintended regressions across 4 900 lines. Split is a prerequisite for safe future development of this subsystem. |
| 4 | Non-atomic restart store writes | MEDIUM | User-visible data loss on crash. Fix is a 3-line tmp+replace pattern change. |
| 5 | Repeated `load_app_config()` without caching | MEDIUM | Consistency risk (diverging config mid-run) + redundant disk I/O. One `@functools.cache` decorator fixes all call sites at once. |

---

## Out of Scope (confirmed non-issues after investigation)

- `session_state` usage in `runtime/state.py`: reads are encapsulated in typed
  snapshots (`ProcessingSessionSnapshot`, `PreparationStateSnapshot`); writes are
  consolidated in named mutator functions. Pattern is adequate for Streamlit.
- `restart_store.py` delete-before-write ordering: old file is deleted only after the
  new write completes; no TOCTOU window for the delete step itself.
- `call_responses_create_with_retry` in `image/shared.py`: correctly strips unsupported
  parameters on `TypeError` before retrying; logic is sound.
- `reader_cleanup_mvp/service.py` having zero internal imports: intentional isolation
  pattern, not an oversight.