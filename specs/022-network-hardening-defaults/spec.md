# Feature Specification: Safe-by-default network binding for the Streamlit surface

Date: 2026-07-15
Status: **PLANNED (Wave 1 / S1).** Security hardening. No behaviour change for the local single-user workflow;
tightens defaults so the app is not silently exposed on all interfaces.
Owner surface: `.streamlit/config.toml`, `scripts/_shared.ps1`, `scripts/project-control-wsl.sh`,
`scripts/start-project.ps1`.
Companion: prerequisite for the envisioned hosted SaaS (`plans/monetization*.md`) where a FastAPI/auth layer — not
Streamlit — is the trust boundary. This spec does NOT introduce auth; it removes the open-by-default posture that
would let an unauthenticated caller spend paid API budget.

## Problem (verified against HEAD d27c137)

The Streamlit surface is configured open-by-default with web protections disabled and no authentication layer:

- [.streamlit/config.toml](/D:/www/Projects/2025/DocxAICorrector/.streamlit/config.toml#L4-L6): `enableCORS = false`
  (L4), `enableXsrfProtection = false` (L5), `address = "0.0.0.0"` (L6).
- [scripts/_shared.ps1](/D:/www/Projects/2025/DocxAICorrector/scripts/_shared.ps1#L22): `$serverHost = '0.0.0.0'`
  is the only default; it flows through `Start-ManagedProject` → `start-project.ps1` →
  `scripts/project-control-wsl.sh` → `streamlit run ... --server.address "$server_host"`. No start path overrides
  it to loopback.
- No authentication exists anywhere in `src/` (verified: the only `auth`-matching code classifies upstream LLM
  provider credential errors, not app user access).

The app processes confidential documents and calls paid APIs. Bound to `0.0.0.0` with XSRF and CORS off, any host on
the LAN (or any routed network if port-forwarded) can drive it, exhausting the operator's API budget and exercising
CSRF / WebSocket-origin vectors.

## Scope (planned)

1. **Loopback by default.** `.streamlit/config.toml` → `address = "127.0.0.1"`. `scripts/_shared.ps1` →
   `$serverHost = '127.0.0.1'`.
2. **Web protections on by default.** `.streamlit/config.toml` → `enableXsrfProtection = true`. Leave CORS at
   Streamlit's protective default (`enableCORS = true`) unless a concrete same-origin regression is proven, in which
   case document why in the file.
3. **Remote mode is explicit opt-in.** Add a single documented switch (env var `DOCX_AI_BIND_HOST`, default
   `127.0.0.1`) honoured by `scripts/_shared.ps1` / `project-control-wsl.sh`. Setting it to `0.0.0.0` is allowed but
   MUST print a one-line startup warning that the surface has no built-in auth and should sit behind a reverse proxy
   that terminates authentication.
4. **Docs.** README run instructions state the default is local-only and that `DOCX_AI_BIND_HOST=0.0.0.0` requires an
   authenticating reverse proxy.

## Test plan

- Static config test: assert `.streamlit/config.toml` has `address = "127.0.0.1"`, `enableXsrfProtection = true`, and
  that `enableCORS` is not `false` while XSRF is on (Streamlit rejects that combination).
- Script test: `scripts/_shared.ps1` default host is `127.0.0.1`; with `DOCX_AI_BIND_HOST` unset the launcher binds
  loopback; with `DOCX_AI_BIND_HOST=0.0.0.0` the warning line is emitted (assert on the launcher's echoed command /
  warning string).

## Out of scope

- Building authentication, sessions, or the reverse proxy itself (belongs to the future backend/SaaS work).
- Any change to upload normalization, archive guards, or the processing pipeline.

## SaaS rationale

Every monetization draft puts identity/billing in front of the core and treats Streamlit as a frontend, not the
authority. Shipping loopback-by-default closes the window where a pre-auth hosted deploy is an open money-spending
endpoint, without pre-committing to any specific auth vendor.
