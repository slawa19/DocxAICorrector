# Running the Pipeline — Runbook

Date: 2026-06-21. Status: Active, canonical. Verified end-to-end on this date.

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
- `load_project_dotenv(override=True)` reloads `.env` and **overrides** any `export` of these vars.
  So to change a model you must **edit `.env`** — an `export DOCX_AI_MODELS_TEXT_DEFAULT=...` is
  ignored.
- `.env` is **not** safe to `source` in shell. Read values via the project config, not `source .env`.
- Required key: **`OPENROUTER_API_KEY`** (primary, for all `openrouter:*` selectors incl. Gemini and
  the reader-cleanup Claude model).

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
Outputs in `runs/<RUN_ID>/`: `..._report.json`, `..._summary.txt`, and `<output_basename>.docx`.

---

## 5. Common pitfalls (every one of these was hit; avoid them)

| Symptom | Cause | Fix |
|---|---|---|
| Run fails ~80s, OpenAI rate-limit, no DOCX | translation used `gpt-5-mini` (OpenAI), not Gemini | set `.env` `DOCX_AI_MODELS_TEXT_DEFAULT=openrouter:google/gemini-3.1-flash-lite-preview` |
| `export MODEL=...` has no effect | `load_project_dotenv(override=True)` overrides env from `.env` | edit `.env`, not `export` |
| `bash: .../run_lietaer_validation.py\r` | launcher `.sh` written by PowerShell → CRLF | run one `wsl.exe -- bash -lc '...'`; don't generate `.sh` from PowerShell |
| Background run dies / no log | `&` inside `bash -lc` doesn't survive `wsl.exe` exit | foreground python + background at the TOOL level |
| `ModuleNotFoundError` on config | wrong module name | use `docxaicorrector.core.config` |
| `pdfminer` ImportError | ran in `.venv-win` | use WSL `.venv` |
| `rg: command not found` | ripgrep not in WSL | use `grep` |
