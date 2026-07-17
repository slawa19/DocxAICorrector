# Feature Specification: Explicit package contract and single dependency source of truth

Date: 2026-07-15
Status: **IMPLEMENTED (2026-07-16).** Packaging + dependency hygiene. Two coupled decisions: (A) what installable
surface the project actually promises, and (B) making `pyproject.toml` the single source of dependency truth.
Owner surface: `pyproject.toml`, `requirements.txt`, `core/constants.py` (`resolve_repo_root`),
`tests/test_docxaicorrector_bootstrap_package.py`, and a new consistency test.

Verification: tests/test_dependency_consistency.py gates the single source of truth (requirements.txt ↔ pyproject runtime deps); tests/test_package_install_smoke.py proves the A2 wheel installs into a clean venv and imports with default config; tests/test_docxaicorrector_bootstrap_package.py keeps the repo-root import path green.
Changelog: 2026-07-16 — implemented; status + Non-goals/Anti-regression added to meet the constitution spec-format contract. Decision A2 (genuinely installable core) taken; `pdfplumber` removed as unused while `pdfminer.six` was found to be used by `pdf_import/images.py` and kept (audit corrected).

## Problem A — install contract is broken (verified against HEAD d27c137)

[constants.py:4-12](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/core/constants.py#L4-L12)
`resolve_repo_root` walks parents requiring `config.toml` + `prompts/` + `pyproject.toml` to co-exist, and runs at
import time (`BASE_DIR = resolve_repo_root(...)`). Those resources are NOT declared as package data —
`pyproject.toml` has only `[tool.setuptools.packages.find] where = ["src"]` (L25-26), no `package-data`/`MANIFEST.in`.
So a wheel installed outside a checkout raises `RuntimeError` on import. The existing test
[test_docxaicorrector_bootstrap_package.py:28](/D:/www/Projects/2025/DocxAICorrector/tests/test_docxaicorrector_bootstrap_package.py#L28)
only exercises import from the repo root (`cwd=REPO_ROOT`, `PYTHONPATH` popped), never an installed wheel — so the
break is untested.

**Decision (confirmed at review 2026-07-15): A2 — genuinely installable core.** Package `prompts/` + default
`config.toml` as package data and load them via `importlib.resources`, so `resolve_repo_root` is no longer required
for imported use (checkout still works for dev). Add a smoke test: build wheel → install into a clean venv →
`import docxaicorrector` + load default config. This is what a future FastAPI backend / worker importing the core as
a dependency needs.

**A2 implementation shape (contained blast radius — verified):** the only resource-path resolution in `src/` is
`core/constants.py` and `real_image/manifest.py:10` (both via `resolve_repo_root`); everything else consumes the
`PROMPTS_DIR`/`CONFIG_PATH`/`SYSTEM_PROMPT_PATH` symbols. So:
- Relocate canonical resources into the package: `prompts/` → `src/docxaicorrector/resources/prompts/`,
  `config.toml` → `src/docxaicorrector/resources/config.toml`. Declare them as package data in `pyproject.toml`.
- Split the two roots in `constants.py`: **resource root** (read-only prompts/config) resolves to the packaged
  location (works in checkout via `__file__` and in a wheel via `importlib.resources`); **working root**
  (`RUN_DIR`, `ENV_PATH`, logs) resolves to the repo root in a checkout and to `DOCX_AI_HOME` (default `Path.cwd()`)
  when installed. Keep every existing constant NAME stable.
- Change the `resolve_repo_root` marker away from `prompts/` (which leaves the root) to `pyproject.toml` + a stable
  root marker (e.g. `scripts/` or `.git`); make it best-effort (return `None`/fallback instead of raising when not
  in a checkout).
- Update dev-side references to root `prompts/`/`config.toml` in scripts/tests/benchmarks to the new location.

The dependency sync (Problem B) is implemented unconditionally.

## Problem B — dependencies diverge across two sources (verified)

- `anthropic` is imported at runtime ([config.py:1397](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/core/config.py#L1397))
  and is the reader-cleanup role default (`config.toml:66-67`), but is ABSENT from `pyproject.toml` dependencies
  (L6-13); it exists only in `requirements.txt`. A `pyproject`-only install `ImportError`s when the anthropic
  provider is selected. (Note: the true text-model default is `openrouter:google/...`, not anthropic — anthropic is
  the reader-cleanup default and a provider option.)
- `pytest`/`pyright` are correctly in `[project.optional-dependencies].dev` (L16-19) but ALSO duplicated into the
  runtime-named `requirements.txt`, mixing runtime and dev tooling.
- `pdfplumber` is declared but not imported anywhere in `src/`/`tests/` — remove it.
  **Correction to the audit:** `pdfminer.six` IS used — `pdf_import/images.py` lazy-imports `pdfminer.high_level`
  / `pdfminer.layout` (raises `optional_dependency_missing:pdfminer.six` when absent). It stays in `pdf-import`.

## Scope (planned)

1. **`pyproject.toml` is the source of truth.** Add `anthropic>=…` to runtime `dependencies` (it is a real runtime
   import). Keep dev tooling only in `[project.optional-dependencies].dev`.
2. **Regenerate/align `requirements.txt`** from pyproject (runtime deps only) OR add a consistency test that fails
   when the two diverge. Prefer the consistency test so drift is caught mechanically.
3. **`pdfplumber`/`pdf-import`:** remove the unused `pdf-import` optional group, OR keep it only if a PDF backend is
   genuinely planned — in which case add a one-line note in pyproject stating it is a not-yet-wired future backend.
   Default: remove `pdfplumber`; decide `pdfminer.six` the same way.
4. **Package contract (A1 or A2)** per the decision above, with the matching test (honest bootstrap note for A1; wheel
   smoke test for A2).

## Test plan

- Consistency test: every runtime dep in `requirements.txt` is present in `pyproject` runtime deps and vice versa
  (dev tools excluded); fails on divergence.
- A2 only: build wheel into a temp dir, `pip install` into a fresh venv, run `python -c "import docxaicorrector; …
  load default config"` — passes with no repo checkout on the path.
- A1 only: bootstrap test explicitly asserts (and documents) repo-root-only import; no installable-wheel claim.

## Out of scope

- Splitting the core into multiple distributables (backend/worker packaging) — that is future backend work.

## Non-goals

(See also `## Out of scope` above.)

- No splitting the core into multiple distributables (backend/worker packaging) — deferred to future backend work.
- No new PDF backend wired up — `pdfplumber` was removed as genuinely unused; `pdfminer.six` was kept ONLY because `pdf_import/images.py` already lazy-imports it, not as a new feature.

## Anti-regression

- Runtime deps stay in sync across the two sources: every runtime dep in requirements.txt is present in pyproject runtime deps and vice versa (dev tools excluded), and `anthropic` (a real runtime import) is present in both — tests/test_dependency_consistency.py (fails on divergence).
- The built wheel installs into a fresh venv with no repo checkout on the path and `import docxaicorrector` + default-config load succeeds (A2) — tests/test_package_install_smoke.py; the repo-root import path remains valid — tests/test_docxaicorrector_bootstrap_package.py.

## SaaS rationale

The planned multi-service topology (FastAPI backend + worker + frontend) needs the core installable as a dependency,
which argues for A2. Even under A1, a single dependency source of truth prevents `ImportError`-on-deploy from the
`anthropic` divergence.
