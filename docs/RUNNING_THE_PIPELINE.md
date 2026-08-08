# Running the Pipeline — Runbook

Status: Active, canonical. End-to-end verified 2026-06-21; **partially re-verified 2026-08-07**, when
two things were found stale: the `.env`/`export` precedence had been inverted by `12385ad` on
2026-07-15 and this document still taught the old behaviour, and audiobook mode — shipped since — was
absent entirely. Sections 2 and 4a carry the corrections. Section 4 gained a reading guide for the
`model_accounting_*` lines on 2026-08-08, when two counter families started appearing in
`..._summary.txt`. The rest still dates from 2026-06-21: if a command here disagrees with the code, the
code is right, and fix this file in the same PR.

Read this BEFORE running tests, config checks, or a full-book pipeline run. Do **not** re-derive
ad-hoc paths/commands — every command below is tested and copy-paste ready. Most of this exists
because these exact things tripped people up; the "Common pitfalls" section lists each.

---

## 1. Environment (READ FIRST)

- ALL pipeline / PDF-import / full-book runs use **WSL Debian** + its venv **`.venv`** (it has
  `pdfminer` and the project deps).
- **`.venv-win`** is the Windows venv and **does NOT have `pdfminer`** → PDF-import / corpus tests
  fail there (an environment limit, not a bug). Use `.venv-win` ONLY for pure unit tests that do
  not import pdfminer.
- If a sandboxed WSL call fails with **`WSL_E_DISTRO_NOT_FOUND`**, re-run the SAME command **with
  escalation** (non-sandboxed).
- **Do NOT generate `.sh` launchers from PowerShell** (`Set-Content` writes CRLF → `bash: ...\r`
  errors). Run ONE `wsl.exe -d Debian -- bash -lc '...'` command. For a long run, wrap a
  **foreground** wsl-python call in the tool's background mode — do NOT use `&` inside `bash -lc`
  (the background child does not survive the `wsl.exe` exit).

Activate + import path inside WSL:
```
. .venv/bin/activate && export PYTHONPATH=src:.
```
Config module is **`docxaicorrector.core.config`** (NOT `docxaicorrector.config`, NOT
`src.docxaicorrector...`). `rg` is not installed in WSL — use `grep`.

---

## 2. Models / `.env` (the #1 gotcha)

- **Translation model = Gemini via OpenRouter.** In `.env`:
  ```
  DOCX_AI_MODELS_TEXT_DEFAULT=openrouter:google/gemini-3.1-flash-lite-preview
  ```
  Do **NOT** use `gpt-5-mini` (that is OpenAI; it rate-limits and is NOT the translation baseline).
- **Precedence is `environment > .env > config defaults`, and it is the opposite of what this runbook
  said until 2026-08-07.** `load_project_dotenv` has no `override` parameter at all
  (`src/docxaicorrector/core/config.py:340`); it fills a key from `.env` **only when the process
  environment has not already set it** to a non-empty value. So `export DOCX_AI_MODELS_TEXT_DEFAULT=...`
  **wins**, and editing `.env` will not override an exported value. An absent or whitespace-only env
  var counts as unset, so local dev still gets populated from `.env`.
  The old advice ("edit `.env`, an `export` is ignored") was written 2026-06-22 and invalidated by
  `12385ad` on 2026-07-15, which made hosted/CI secrets beat a stray checked-in `.env`. Guards on the
  current behaviour: `tests/test_config.py:1542,1554`.
- `.env` is **not** safe to `source` in shell. Read values via the project config, not `source .env`.
- Keys are **per role, not one key for everything**. `OPENROUTER_API_KEY` covers all `openrouter:*`
  selectors (Gemini translation and the reader-cleanup Claude model), but the defaults also reach other
  providers: `reader_verifier_model` (`src/docxaicorrector/resources/config.toml:75`) wants
  `ANTHROPIC_API_KEY`, and the image roles (`:113-127`) want `OPENAI_API_KEY`. Which ones you actually
  need depends on the profile and the operation you run.

### Verify model + key + a live call (cheap; do this BEFORE an expensive run)
```
wsl.exe -d Debian -- bash -lc 'cd /mnt/d/www/Projects/2025/DocxAICorrector && . .venv/bin/activate && PYTHONPATH=src:. python - <<PY
import os
from docxaicorrector.core.config import load_app_config, load_project_dotenv, get_text_model_config, get_client_for_model_selector, resolve_model_selector
load_project_dotenv(); cfg=load_app_config(); tm=get_text_model_config(cfg)
rs=resolve_model_selector(tm.default,"responses_text",config_like=cfg,source_name="translate")
print("text default:",tm.default,"->",rs.provider,"/",rs.model_id)
print("OPENROUTER key present:", bool(os.environ.get("OPENROUTER_API_KEY")))
c=get_client_for_model_selector(tm.default,"responses_text",config_like=cfg)
print("LIVE:", c.chat.completions.create(model=rs.model_id,messages=[{"role":"user","content":"Reply OK"}],max_tokens=5,temperature=0).choices[0].message.content)
PY'
```
Expect: `text default: openrouter:google/gemini-... -> openrouter / google/gemini-...`, key `True`,
`LIVE: OK`. **If the model is not Gemini, fix `.env` and do NOT run** (do not waste an expensive run).

---

## 3. Tests (canonical runner)

```
bash scripts/test.sh tests/test_<file>.py -q
```
- The selector (`tests/...`) MUST come before pytest options. The runner activates `.venv` and sets
  `PYTHONPATH=src:.` itself.
- `conftest` wipes API keys by design → real-document LLM tests **skip under pytest**. "pytest skip"
  ≠ "cannot run the benchmark" — full-book runs are NOT done through pytest (next section).

---

## 4. Full-book pipeline run (the real translation — NOT pytest)

Standalone runner: **`tests/artifacts/real_document_pipeline/run_lietaer_validation.py`** (the name
says "lietaer" but it is the GENERIC real-document runner, selected by env vars). Driven by:

- `DOCXAI_REAL_DOCUMENT_PROFILE=<document id>` — e.g. `money-sustainability-pdf-full-heldout`
- `DOCXAI_REAL_DOCUMENT_RUN_PROFILE=<run profile id>` — e.g.
  `ui-parity-translate-benchmark-advisory-image-safe-no-cleanup` (baseline translate, image-safe,
  reader-cleanup OFF, advisory gate)
- `DOCXAI_REAL_DOCUMENT_FORCED_RUN_ID=<id>` — artifacts go to
  `tests/artifacts/real_document_pipeline/runs/<id>/`

Document and run profiles are defined in **`corpus_registry.toml`** (look there for the exact ids).

### Verified launch (background at the TOOL level; foreground inside WSL)
```
wsl.exe -d Debian -- bash -lc 'cd /mnt/d/www/Projects/2025/DocxAICorrector && . .venv/bin/activate && export PYTHONPATH=src:. && export DOCXAI_REAL_DOCUMENT_PROFILE=money-sustainability-pdf-full-heldout && export DOCXAI_REAL_DOCUMENT_RUN_PROFILE=ui-parity-translate-benchmark-advisory-image-safe-no-cleanup && export DOCXAI_REAL_DOCUMENT_FORCED_RUN_ID=20260621T_money_gemini && python -u tests/artifacts/real_document_pipeline/run_lietaer_validation.py 2>&1 | tee .run/money_gemini.log'
```
No `&` inside — let python run foreground; background it via the tool's background mode (it keeps the
process alive and notifies on completion).

### Monitor (poll progress.json)
```
wsl.exe -d Debian -- bash -lc 'cd /mnt/d/www/Projects/2025/DocxAICorrector && . .venv/bin/activate && python -c "import json;d=json.load(open(\"tests/artifacts/real_document_pipeline/runs/<RUN_ID>/money_sustainability_pdf_full_heldout_progress.json\"));print({k:d.get(k) for k in [\"status\",\"stage\",\"progress\",\"detail\"]})"'
```
Outputs in `runs/<RUN_ID>/`: `..._report.json`, `..._summary.txt`, and `<output_basename>.docx` — plus
`<output_basename>.md` and, on audiobook runs, `<output_basename>.tts.txt`
(`scripts/run_lietaer_validation.py:3489-3491`, `src/docxaicorrector/runtime/artifacts.py:382`). Five
files, not three. On an audiobook run the `.tts.txt` **is** the product.

### Reading `..._summary.txt`: the `model_accounting_*` lines (added 2026-08-08)

The summary carries the run ledger as flat `model_accounting_<field>=<value>` lines
(`_build_model_accounting_summary_lines`,
`tests/artifacts/real_document_pipeline/run_lietaer_validation.py:4376`). Two families landed on
2026-08-08 and are named here only so that whoever opens a fresh report knows what is in front of them.
The **authoritative** field-by-field meaning lives in `docs/LOGGING_AND_ARTIFACT_RETENTION.md` (event
`model_usage_accounted`) and is deliberately not repeated: one of the two documents has to own it, and
that one does.

- `model_accounting_controlled_block_fallback_*` — the PIPELINE half of prose loss: blocks
  `process_single_block` judged unusable and **delivered anyway** (`fallback_continue`). Blocks and
  characters, with a `_kind_counts` / `_kind_chars` breakdown. Deliberately NOT merged into
  `model_accounting_model_output_discarded_*`, which is the GENERATOR's decision to throw an answer
  away: the same block routinely collects both verdicts, so adding them double-counts it.
- `model_accounting_degradation_ladder_*` — the remedy printed beside the loss it removes: how many
  blocks the generator answered by DIVIDING instead of substituting source text,
  `_model_call_count` (a measured delta, not an estimate — a paragraph that needed two attempts cost
  two calls), and `_translated_paragraph_count` against `_unrescued_paragraph_count`. Those two sum to
  the blocks' paragraph count, so the pair states the whole outcome and not the flattering half.

Zeros here assert something rather than mark a missing field. All-zero `degradation_ladder_*` means the
ladder never fired, which is the expected reading of a clean run — a block that passes first try must
not cost one extra call. `controlled_block_fallback_*` above zero means untranslated text reached the
delivered document, and that is the number worth acting on.

---

## 4a. Audiobook mode (added 2026-08-07; this runbook had no mention of it at all)

The pipeline has a third operation beyond `edit` and `translate`:
`PROCESSING_OPERATION_VALUES = ("edit", "translate", "audiobook")`
(`src/docxaicorrector/core/config.py:75` — one list, against which config, env, run profiles and the UI
all validate).

Two different things are easy to confuse:

- **Standalone audiobook** — `processing_operation = "audiobook"`. The whole run produces narration.
  Run profile: `ui-parity-standalone-audiobook` (`corpus_registry.toml:174`). The registry originally
  had no way to express this operation, and the profile exists so the first audiobook run is
  reproducible — read the comment at `corpus_registry.toml:161-163` before using it.
- **Narration as a post-pass on a translate run** — `audiobook_postprocess_enabled = true`, main
  DOCX/Markdown result unchanged, narration written alongside. Run profile:
  `ui-parity-translate-audiobook-postprocess` (`corpus_registry.toml:151`). Default is `false`; the
  default is overridable via `DOCX_AI_AUDIOBOOK_POSTPROCESS_DEFAULT`
  (`src/docxaicorrector/core/config_runtime_sections.py:568`).

Model selection: there is **no active `[models.audiobook]` section**. `src/docxaicorrector/resources/config.toml:103-104`
carries one only as a commented-out example, so the role inherits `[models.text]` unless you uncomment
and set it. Do not assume a separate audiobook model is in force.

Entry points if you need to trace behaviour: `src/docxaicorrector/pipeline/narration_postprocess.py`,
`src/docxaicorrector/pipeline/late_phases.py`.

---

## 5. Common pitfalls (every one of these was hit; avoid them)

| Symptom | Cause | Fix |
|---|---|---|
| Run fails ~80s, OpenAI rate-limit, no DOCX | translation used `gpt-5-mini` (OpenAI), not Gemini | set `.env` `DOCX_AI_MODELS_TEXT_DEFAULT=openrouter:google/gemini-3.1-flash-lite-preview` |
| `.env` edit has no effect | the variable is already exported in the environment, and **environment wins** (`core/config.py:340`) | `unset` it, or change the exported value |
| `bash: .../run_lietaer_validation.py\r` | launcher `.sh` written by PowerShell → CRLF | run one `wsl.exe -- bash -lc '...'`; don't generate `.sh` from PowerShell |
| Background run dies / no log | `&` inside `bash -lc` doesn't survive `wsl.exe` exit | foreground python + background at the TOOL level |
| `ModuleNotFoundError` on config | wrong module name | use `docxaicorrector.core.config` |
| `pdfminer` ImportError | ran in `.venv-win` | use WSL `.venv` |
| `rg: command not found` | ripgrep not in WSL | use `grep` |
