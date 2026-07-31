# Contract: Persisted Source and Preparation Request Identity

## Persist

- Store normalized working bytes once.
- Retain the authoritative token derived from original upload bytes.
- Store exact normalized payload size/digest and source-format provenance.

## Restore

- Read only from the confined persisted-source path.
- Validate non-empty bytes, size and digest before reuse.
- Restore a frozen payload carrying the persisted authoritative token.
- Never recompute PDF/DOC identity from normalized DOCX bytes.
- Never reconvert a verified normalized payload.
- Treat incomplete/corrupt records as unavailable.

## Preparation request marker

- Axes: source token, chunk size, operation, canonical source language, canonical target language.
- Equivalent normalized values collide; different semantic values do not.
- Both UI lookup/start call sites use the same marker builder arguments.

## Observability

- Integrity/metadata rejection uses existing safe user/activity and structured logging conventions.
- No document bytes or contents are logged.
- `.run/completed_*` remains source cache, not user-visible output.
