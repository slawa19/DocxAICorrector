# Feature Specification: Environment wins over on-disk .env (secrets precedence)

Date: 2026-07-15
Status: **PLANNED (Wave 1 / S3).** Config/deploy safety. Flip `.env` loading from clobbering process env to
respecting it, matching the conventional precedence environment > `.env` > config defaults.
Owner surface: `core/config.py` (`load_project_dotenv`), its call sites, and `core/config_loader_layers.py`.

## Problem (verified against HEAD d27c137)

[config.py:310-311](/D:/www/Projects/2025/DocxAICorrector/src/docxaicorrector/core/config.py#L310-L311):

```python
def load_project_dotenv() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
```

`override=True` means an on-disk `.env` overwrites already-set process environment. The function is invoked
repeatedly: during app-config load (`config_loader_layers.py:198,201`), before every provider-availability check
(`config.py:736`, before reading `os.getenv(api_key_env)`), and before every client creation (`config.py:1430`,
before reading the key at `:1431`). In a container/CI/deploy where secrets and selectors (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `DOCX_AI_*` model/provider selectors) are injected as real env vars, a
`.env` shipped alongside the code silently overrides them on each call. The clobber only bites when a `.env` file
exists next to the deployed code; with none it is a no-op.

## Scope (planned)

1. **`override=False`.** `load_project_dotenv` loads `.env` without overriding already-present process env. Result:
   real environment wins; `.env` fills only unset keys; config defaults remain the final fallback.
2. **Preserve local DX.** For a local dev workflow with no exported vars, behaviour is unchanged (`.env` still
   populates the empty environment). No change to `ENV_PATH` resolution.
3. **Document the precedence** in README (one line: `environment > .env > config defaults`).

## Test plan

- With `OPENAI_API_KEY` pre-set in `os.environ` and a different value in a temp `.env`, after `load_project_dotenv()`
  the process value is retained (env wins).
- With `OPENAI_API_KEY` absent from `os.environ` and present in `.env`, after the call the `.env` value is loaded
  (`.env` fills the gap).
- Idempotent: calling `load_project_dotenv()` multiple times never changes an already-set value.

## Out of scope

- Any secret-management/vault integration.
- Changing which keys are read or the provider-resolution logic.

## SaaS rationale

Hosted deploys inject Stripe/Clerk/DB and model-provider secrets via real env vars. `override=True` would let a
stray checked-in `.env` shadow production secrets; `override=False` makes the deployment environment authoritative.
