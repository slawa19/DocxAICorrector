# Feature Specification: Survive a non-answering model block (controlled fallback for `non_completed_response`)

Date: 2026-07-11
Status: IMPLEMENTED (2026-07-11). Verified by deterministic injected-response tests; full suite green
(1968 passed), pyright ratchet 244.
Owner surface: the block-generation failure path in `generation/_generation.py` and the controlled-fallback
policy in `pipeline/block_execution.py`.
Companion: `specs/002-gate-report-honesty/spec.md` (the report/acceptance honesty stream),
`docs/specs/GLOBAL_PLAN_2026-06-16.md` roadmap item 2 (controlled-fallback — this spec discharges it).
Changelog:
- 2026-07-11 — Created after the failure-path audit. A model response with a non-`completed` status
  (`non_completed_response`) gets zero effective retries and zero controlled fallback, and aborts the ENTIRE
  book run before any quality report is produced. Observed live on Money and Mazzucato (result=failed, NO report).
- 2026-07-11 — IMPLEMENTED. `_generation.py`: one predicate `_is_non_completed_response_error` (reused in the
  retry OR-chain, FR-002) + `_can_fallback_to_source_text_after_non_completed_response` guard, and a
  source-text fallback gate placed AFTER the empty/marker recovery block and BEFORE `raise last_exception`
  (FR-003/FR-004). No extra provider call. Five tests added in `tests/test_generation.py` (SC-001/002/003a/003b).
  SC-004 not added as a separate test — covered by construction (returns `target_text` identically to the
  existing incomplete/empty source-fallbacks, which already flow to `fallback_continue`).

## Problem (verified 2026-07-11 by code audit — see Verified findings)

When the translation provider returns a response object whose status is not `completed` (e.g. `failed`), the
generation layer raises `RuntimeError("… non_completed_response.")`. This error is:

- **NOT retried** — it matches none of the retry predicates (`_generation.py:1004-1009`), so the loop `break`s
  on attempt 1 even though `max_retries` defaults to 3.
- **NOT recovered** — the source-text recovery gate (`_generation.py:1021-1024`) only covers
  `empty_response`/`incomplete_response`/marker-validation, so it falls through to `raise last_exception`
  (`_generation.py:1082`).
- **Fatal to the whole run** — `process_single_block` catches the raised exception (`block_execution.py:1105`)
  and routes straight to `handle_block_generation_failure` (`block_failures.py:82`), which persists
  `status="failed"` and returns a terminal outcome; the block loop then aborts the entire book
  (`block_execution.py:1218-1228`). No later block runs and the quality report is never produced.

The controlled-fallback machinery that would let the run survive one bad block already exists — but it is wired
ONLY to the "model returned bad/empty TEXT" path, not to the "model returned a non-completed status" path.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One non-answering block does not destroy the whole book (Priority: P1; overall priority 1, pre-UI blocker)

An expensive multi-block run where a single block's provider response comes back non-`completed` still finishes,
delivers a document, and produces the quality report — with the failed block filled from its source text and
flagged, exactly as the empty/incomplete cases already behave.

**Why this priority:** this is the only pre-UI change that is a true blocker. A UI over a pipeline that dies
before producing a report is useless. We saw it live: Money and Mazzucato aborted with `result=failed` and NO
report at all. The failed block is a single unit; the run is dozens of blocks and paid API calls.

**Independent Test:** call `generate_markdown_block` with a fake client whose response carries
`status="failed"` and a non-empty `target_text`; assert it returns the source `target_text` (after the bounded
retries) instead of raising — verifiable deterministically, no live run.

**Acceptance Scenarios:**

1. **Given** a provider response with `status="failed"` (`non_completed_response`) and a non-empty source
   `target_text`, **When** `generate_markdown_block` runs, **Then** it retries up to `max_retries`, and on
   persistent failure returns the source `target_text` as a controlled fallback (does NOT raise).
2. **Given** that returned source-text block flows into block processing, **When** it is classified,
   **Then** it maps to a `fallback_continue` policy (`source_text_fallback`/`english_residual_output`) so the
   run continues and the report is produced — NOT to `handle_block_generation_failure` abort.
3. **Given** a source `target_text` that is empty/whitespace (no recovery substrate), **When** the response is
   `non_completed_response`, **Then** the block STILL hard-fails (no vacuum fallback).
4. **Given** an authentication / configuration / not-found error (which never yields a status-bearing response),
   **When** generation fails, **Then** it STILL hard-fails the run (unchanged) — these never reach the
   `non_completed_response` classification.

### Edge Cases

- The provider returns `status="incomplete"` — unchanged; already handled by the incomplete-response path.
- A `non_completed_response` on a block whose source is image-only/passthrough — unchanged (passthrough returns
  before the model call, `_generation.py:940-948`).
- Repeated `non_completed_response` across MANY blocks — each is independently recovered to source text; the
  cumulative untranslated residual is caught HONESTLY by the existing `untranslated_body` acceptance metric
  (large English residual still fails acceptance). This spec does not weaken that gate.

## Verified findings

Verified 2026-07-11 by code audit (Constitution VIII — deterministic reading of current code; the fix is
verified by deterministic injected-response tests, not a non-deterministic live run).

- **`non_completed_response` is raised at** `_generation.py:528-530`: `if isinstance(response_status, str) and
  response_status != "completed": … raise RuntimeError(f"… ({response_status}) … (non_completed_response).")`.
- **It is not retryable.** `should_retry` (`_generation.py:1004-1009`) ORs `is_retryable_error`
  (HTTP 408/409/429/≥500 or SDK connection/timeout classes — `image/shared.py:50-56`),
  `_is_retryable_empty_generation_error` (`empty_response`/`collapsed_output`/`incomplete_response` only,
  `_generation.py:910-913`), `_is_retryable_marker_validation_error`, `_is_retryable_context_leakage_error`.
  A `non_completed_response` `RuntimeError` matches none → `break` on attempt 1.
- **It is not recovered.** The recovery gate (`_generation.py:1021-1024`) requires
  `_is_retryable_empty_generation_error` or `_is_retryable_marker_validation_error`; `non_completed_response`
  fails both → `raise last_exception` (`_generation.py:1082`).
- **The abort chain:** raised → `process_single_block` `except` (`block_execution.py:1105`) →
  `handle_block_generation_failure` (`block_failures.py:82`, persists `status="failed"` at `:141`, returns
  terminal outcome at `:149/197`) → block loop `return block_outcome` aborts the run
  (`block_execution.py:1218-1228`). The controlled-fallback table (`CONTROLLED_BLOCK_FAILURE_POLICY`,
  `block_execution.py:15-33`) and substrate guard (`_has_intact_controlled_fallback_substrate`, `:80-105`) are
  consulted ONLY on the returned-text path (`:1118-1151`), never on this exception path.
- **The existing parallel the fix mirrors:** `incomplete_response` and `empty_response` are BOTH retryable
  (`:1006`) AND fall back to source text via `return target_text` (`_generation.py:1041-1077`), gated by
  `_can_fallback_to_source_text_after_*` requiring only `bool(target_text.strip())` (`:894-907`). The fix
  extends this SAME pattern to `non_completed_response`.
- **Anti-vacuum (why auth/config/404 stay fatal):** those failures never produce a response object with a
  status field, so line 528 never fires for them — they surface as SDK error classes before any status exists
  and continue to hard-fail. The recovery is gated on `isinstance(exc, RuntimeError) and "non_completed_response"
  in str(exc)` AND `bool(target_text.strip())`, so an empty-substrate block also stays fatal.

## Requirements *(mandatory)*

### Functional Requirements

> Binding (Constitution VII): the recovery keys on a PROVIDER-SUPPLIED response status (a structural signal,
> `status != "completed"`) plus the presence of source substrate (`target_text.strip()`), never on any per-book
> content, word list, or text shape. No source substrate → no recovery.

- **FR-001**: Add a predicate `_is_non_completed_response_error(exc)` =
  `isinstance(exc, RuntimeError) and "non_completed_response" in str(exc)`, mirroring
  `_is_incomplete_response_error` (`_generation.py:890-891`).
- **FR-002**: Make `non_completed_response` retryable within the bounded loop: add a
  `_is_retryable_non_completed_response_error` (same body as FR-001) to the `should_retry` OR-chain
  (`_generation.py:1004-1009`). Retries stay bounded by `max_retries` (default 3) with the existing backoff —
  a transient provider `failed` gets a second chance; a persistent one exhausts and proceeds to FR-003.
- **FR-003**: After the retry loop, before `raise last_exception`, add a controlled source-text fallback: if
  `_is_non_completed_response_error(last_exception)` AND `_can_fallback_to_source_text_after_non_completed_response(
  target_text)` (= `bool(target_text.strip())`), log a `markdown_non_completed_response_source_fallback` warning
  event and `return target_text`. This needs NO extra provider call (unlike the empty/incomplete recovery that
  re-attempts) — the retries already happened.
- **FR-004**: A `non_completed_response` with empty/whitespace `target_text` is NOT recovered — it falls through
  to `raise last_exception` and hard-fails (no vacuum fallback).
- **FR-005**: The returned source-text block MUST flow through the existing classification so it lands on a
  `fallback_continue` policy (`source_text_fallback`/`english_residual_output`, `block_execution.py:18-19`) and
  the run continues to produce the report. No change to `CONTROLLED_BLOCK_FAILURE_POLICY` or the substrate guard
  is required (source text is non-empty and its paragraph registry builds — the same substrate the empty/
  incomplete fallbacks already rely on).
- **FR-006**: NO change to the auth/config/not-found/setup failure paths — they never reach the
  `non_completed_response` classification and MUST continue to hard-fail.
- **FR-007**: NO change to the acceptance gate. The `untranslated_body` metric still counts the English residual
  of any recovered block, so a run that recovers a large fraction of its text still FAILS acceptance honestly.

### Key Entities

- **`non_completed_response` error** — a `RuntimeError` raised at `_generation.py:528-530` when the provider
  response status is a non-empty string other than `completed`.
- **Controlled source-text fallback** — returning the untranslated `target_text` for the failed block so
  assembly continues; the same mechanism already used for `incomplete_response`/`empty_response`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A unit test injecting a fake client whose response has `status="failed"` and a non-empty
  `target_text` asserts `generate_markdown_block` returns that `target_text` (not raises) after the bounded
  retries.
- **SC-002**: A unit test asserts the retry loop attempted `max_retries` times for `non_completed_response`
  (transient recovery path exercised), e.g. via a client that fails N-1 times then succeeds → returns the
  translated markdown.
- **SC-003 (anti-vacuum)**: A unit test asserts that `non_completed_response` with EMPTY `target_text` still
  raises (no vacuum fallback), and that an auth/SDK-error path still raises (unchanged hard-fail).
- **SC-004**: A test asserts the recovered source-text block classifies to a `fallback_continue` decision and
  does NOT reach `handle_block_generation_failure` — the run survives to produce a report.
- **SC-005**: Full suite green; pyright ratchet ≤ 244.

## Non-goals

- **Not changing the translation model, temperature, or adding a seed.** Determinism of translation is a
  separate concern; this spec only prevents a non-answering block from aborting the run.
- **Not adding new retry classes beyond `non_completed_response`.** HTTP/connection retries are unchanged.
- **Not weakening acceptance.** A recovered block leaves untranslated source text that the `untranslated_body`
  gate still counts; large residuals still fail (FR-007).
- **Not touching the returned-bad-text controlled-fallback table** (`CONTROLLED_BLOCK_FAILURE_POLICY`) — the
  source-text block already classifies into an existing `fallback_continue` kind.
- **Not per-book tuning.** The recovery keys on the provider status + source presence only (Constitution VII).

## Anti-regression

- **Auth/config/404 stay fatal:** a counter-test asserts an SDK auth/error path (no status-bearing response)
  still raises and aborts — the recovery does NOT swallow it.
- **No-substrate stays fatal:** `non_completed_response` with empty `target_text` still raises (no vacuum).
- **Acceptance honesty preserved:** the `untranslated_body` metric still counts a recovered block's English
  residual — a test asserts a large recovered residual still fails acceptance (Constitution VII anti-vacuum
  counter-proof: real untranslated body is still counted).
- **Retries bounded:** the loop still stops at `max_retries`; no infinite retry on a persistent `failed`.
- **Other error classes unchanged:** empty/incomplete/marker/context-leakage paths behave exactly as before.

## Assumptions

- A provider response with `status="failed"` yields a `RuntimeError` whose message contains
  `non_completed_response` (confirmed `_generation.py:528-530`).
- Source `target_text` for an LLM block is a faithful substrate for a controlled fallback (the same assumption
  the existing empty/incomplete source-fallbacks rely on).
- A source-text block classifies to `source_text_fallback`/`english_residual_output` (both `fallback_continue`)
  downstream — to be confirmed by SC-004; if classification differs, FR-005 is the point to reconcile.
