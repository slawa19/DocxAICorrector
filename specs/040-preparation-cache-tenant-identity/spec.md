# Feature Specification: Preparation cache key incorporates client/credential identity (tenant isolation)

Date: 2026-07-17
Status: **PLANNED (2026-07-17).** Round-6 P1 follow-up (owner chose "bounded fix now"). The shared
preparation cache is process-global and its key omits client/credential identity, so in a multi-tenant
deployment two tenants uploading the SAME document (content-hash `uploaded_file_token`) with the SAME
settings collide on one cache entry — and the AI-boundary-review portion of the prepared document was
computed with ONE tenant's client/credentials. Fold a secret-safe client-identity fingerprint into the
cache key so cross-credential runs do not share a client-dependent prepared document. Backward-compatible:
identity is empty (key byte-identical to today) when AI review is off OR no distinguishing credential is
resolvable — single-tenant behavior and existing cache entries are unchanged.

Verified surfaces: `_shared_preparation_cache` is a module-global `OrderedDict`
(`processing/preparation.py:782`); `uploaded_file_token` is a sha256 content hash
(`processing_runtime.py:1265`); `build_prepared_source_key` (`preparation.py:295`) has no identity axis;
the shared hit is read (`:855`) / returned (`:982`) before `client_factory` is used (miss-path `:1031`).
The client that matters is the AI-boundary-review client, resolved from the `ai_review_model` selector
(`provider:model`) + provider config (`base_url`, `api_key_env`) + `os.environ[api_key_env]`.

## Scope

1. `build_prepared_source_key` (`preparation.py:295`): add a `client_identity: str = ""` keyword param.
   Fold it into the returned key ONLY when non-empty (append a stable `:cid=<identity>` segment). When
   empty, the key MUST be byte-identical to the current output (no cache invalidation, no behavior change).
2. At the call site (`preparation.py:959`, inside `prepare_document_for_processing`, where
   `resolved_config`, `client_factory`, and the resolved `ai_review_*` settings are in scope): compute
   `client_identity` via a NEW helper and pass it. The helper returns `""` UNLESS the prepared output is
   client-dependent — i.e. `ai_review_effective_enabled` is True. When enabled, the identity is a 16-hex
   `sha256` over a stable tuple derived from the AI-review client resolution:
   `(canonical_selector, provider_base_url, api_key_env_name, sha256(os.environ.get(api_key_env,"")))`.
   The raw API-key value MUST NEVER appear in the key — only its sha256. Resolve the provider config for
   the `ai_review_model` selector via the EXISTING config parsing (`core/config.py` selector parser +
   provider registry — grep `_parse_model_selector` / provider lookup near line 635/661); do NOT hardcode
   provider field names beyond what that resolution exposes.
3. If the selector/provider cannot be resolved (misconfig, bare/default), the helper returns `""`
   (fail-open to today's behavior — never raise from cache-key construction).

## Non-goals

- NO raw secret in the cache key (only a hash). NO logging of the identity material.
- NO change to the per-session cache semantics, the trim/LRU, or the miss-path client injection.
- NO key change (byte-identical) when AI review is off, or when the credential fingerprint is identical
  (single-tenant / same creds) — existing cached entries stay valid, sharing is preserved where it is safe.
- NOT a general multi-tenant identity system — this is scoped to the ONE client that influences the
  prepared output (AI boundary review). Extraction uses the same `client_factory`; if any other
  client-dependent output is folded into the prepared document, note it but do not expand scope without
  evidence it differs by tenant.

## Anti-regression (Constitution VII + the post-verification-rigor lesson)

- Two `resolve`-equivalent inputs with DIFFERENT `os.environ[api_key_env]` values AND AI review ON →
  `build_prepared_source_key` returns DIFFERENT keys (cross-credential no-share). Same creds → SAME key.
- AI review OFF → `client_identity == ""` → key byte-identical to a run without the param (sharing
  preserved; existing cache entries not invalidated). Assert byte-identity against the pre-change key for
  a representative input.
- End-to-end shared-cache test: prime `_shared_preparation_cache` under identity A (review on), then a
  second `prepare_document_for_processing` with the SAME token/settings but a DIFFERENT api-key value must
  NOT return identity A's cached prepared document (no cross-identity bleed); a THIRD call with identity A
  again DOES hit the cache.
- The raw key value never appears in the produced key string (assert the secret substring is absent).
- Existing `tests/test_preparation.py` / `test_application_flow.py` cache tests stay green; pyright ≤246.

## SaaS rationale

Closes a confirmed cross-tenant reuse path: a client-dependent prepared document is no longer served
across differing credentials. No-op for the current single-tenant UI, so it is hardening without cost or
behavior change today, and it isolates automatically the moment per-tenant credentials differ.
